"""What the API accepts and returns."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=300)
    limit: int | None = Field(default=None, ge=1, le=200)


class MediaOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    event: str | None
    kind: str
    width: int | None
    height: int | None
    duration_s: float | None
    shot_at: datetime | None
    place: str | None
    activity: str | None
    alcohol_visible: bool


class HitOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    media: MediaOut
    # The second inside a video that matched best. 0 for a photo.
    timestamp_s: float
    rrf_score: float


class Interpretation(BaseModel):
    """What the engine understood from the query, sent back so the interface can show it."""

    model_config = ConfigDict(frozen=True)

    query: str
    searched_for: str
    kind: str | None
    excluded_concepts: tuple[str, ...]
    applied_rules: tuple[str, ...]
    safety_floor: bool
    dropped_words: tuple[str, ...]


class SearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    interpretation: Interpretation
    hits: tuple[HitOut, ...]
    took_ms: int
    cached: bool = False


class TagOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    term: str
    source: str
    weight: float


class ProbeScoreOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    p: float
    roc_auc: float
    # True when the probe is too weak to be shown without a warning next to it.
    weak: bool


class MediaDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    media: MediaOut
    description: str | None
    indoor_outdoor: str | None
    time_of_day: str | None
    people_count: str | None
    emotion: str | None
    uses: tuple[str, ...]
    avoid: tuple[str, ...]
    tags: tuple[TagOut, ...]
    probes: tuple[ProbeScoreOut, ...]


class ProbeOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    roc_auc: float
    average_precision: float
    n_positive: int
    weak: bool
