"""The API, driven end to end against the test library.

The encoder is stubbed. Loading the real 254 MB ONNX model here would make the suite slow and
CI does not have the weights at all.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from esn_engine.api import create_app
from esn_engine.api.deps import Services
from esn_engine.core.cache import NoCache
from esn_engine.db.session import session_factory
from tests import helpers

pytestmark = pytest.mark.needs_postgres

BAR_ITEM = 7
DOG_ITEM = 11


class StubEncoder:
    """Returns the vector of whichever seeded item the test wants to be nearest."""

    def __init__(self, seed: int = 1) -> None:
        self.seed = seed
        self.seen: list[str] = []

    def embed_one(self, text: str) -> list[float]:
        self.seen.append(text)
        return helpers.unit_vector(self.seed)


@pytest_asyncio.fixture
async def client(engine, settings):
    app = create_app(settings)
    encoder = StubEncoder(seed=DOG_ITEM)
    app.state.services = Services(
        settings=settings,
        engine=engine,
        sessions=session_factory(engine),
        encoder=encoder,  # type: ignore[arg-type]
        cache=NoCache(),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as made:
        made.encoder = encoder  # type: ignore[attr-defined]
        yield made


async def test_health_does_not_touch_the_database(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_a_search_returns_hits_and_what_it_understood(client):
    response = await client.post("/search", json={"q": "a volunteer petting a dog"})
    assert response.status_code == 200
    body = response.json()
    assert body["hits"], "no hits at all"
    assert body["interpretation"]["searched_for"]
    assert body["interpretation"]["safety_floor"] is False
    assert body["took_ms"] >= 0


async def test_a_brief_reports_the_rules_it_applied(client):
    response = await client.post("/search", json={"q": "volunteers socialising, no booze"})
    body = response.json()
    interpretation = body["interpretation"]
    assert interpretation["excluded_concepts"] == ["alcohol"]
    assert set(interpretation["applied_rules"]) == {"alcohol", "alcohol-venue", "safety-floor"}
    assert interpretation["safety_floor"] is True
    assert BAR_ITEM not in [h["media"]["id"] for h in body["hits"]]


async def test_the_search_text_reaches_the_encoder_without_the_negation(client):
    await client.post("/search", json={"q": "happy volunteers, no alcohol"})
    assert client.encoder.seen[-1] == "happy volunteers"


async def test_the_limit_in_the_request_is_used(client):
    response = await client.post("/search", json={"q": "volunteers", "limit": 2})
    assert len(response.json()["hits"]) == 2


async def test_an_empty_query_is_rejected(client):
    assert (await client.post("/search", json={"q": ""})).status_code == 422


async def test_one_item_comes_back_with_its_labels_and_probes(client):
    response = await client.get(f"/media/{DOG_ITEM}")
    assert response.status_code == 200
    body = response.json()
    assert body["media"]["name"] == "paws_dog.jpg"
    assert "shelter" in [t["term"] for t in body["tags"]]
    names = {p["name"]: p for p in body["probes"]}
    assert names["animals"]["weak"] is False
    assert names["hero"]["weak"] is True


async def test_an_unknown_item_is_not_found(client):
    assert (await client.get("/media/999999")).status_code == 404


async def test_the_probe_list_marks_the_weak_ones(client):
    response = await client.get("/probes")
    assert response.status_code == 200
    probes = {p["name"]: p for p in response.json()}
    assert probes["good_quality"]["weak"] is True
    assert probes["alcohol"]["weak"] is False
    # Sorted best first, so the useful ones are at the top.
    aucs = [p["roc_auc"] for p in response.json()]
    assert aucs == sorted(aucs, reverse=True)


async def test_suggest_prefers_a_prefix_match(client):
    response = await client.get("/suggest", params={"q": "she"})
    assert response.status_code == 200
    assert "shelter" in response.json()


async def test_suggest_rejects_an_empty_query(client):
    assert (await client.get("/suggest", params={"q": ""})).status_code == 422


async def test_the_openapi_schema_is_generated(client):
    """Free typed docs at /docs is one of the reasons FastAPI is here."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/search" in response.json()["paths"]


async def test_a_repeated_search_comes_back_from_the_cache(engine, settings):
    """With Redis configured the second identical search is served without touching Postgres."""
    from esn_engine.core.cache import key_for

    class Memory:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.store.get(key)

        async def set(self, key: str, value: str, ttl_seconds: int) -> None:
            self.store[key] = value

    cache = Memory()
    app = create_app(settings)
    app.state.services = Services(
        settings=settings,
        engine=engine,
        sessions=session_factory(engine),
        encoder=StubEncoder(seed=DOG_ITEM),  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/search", json={"q": "a volunteer petting a dog"})
        second = await client.post("/search", json={"q": "a volunteer petting a dog"})

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["hits"] == second.json()["hits"]
    assert key_for("a volunteer petting a dog", settings.result_limit) in cache.store
