"""Settings and the logging setup."""

import json
import logging

import structlog

from esn_engine.core.config import Settings
from esn_engine.core.logging import configure_logging


def test_the_defaults_match_the_query_the_search_runs():
    settings = Settings()
    assert settings.rrf_k == 60
    assert settings.candidate_limit == 200
    assert settings.result_limit == 40


def test_redis_is_optional():
    """Without it the search still answers, it just recomputes every time."""
    assert Settings().redis_url is None


def test_the_safety_floor_covers_the_flags_that_matter():
    assert "reputational" in Settings().safety_floor_flags


def test_a_setting_can_be_overridden():
    assert Settings(result_limit=5).result_limit == 5


def test_log_lines_come_out_as_json(capsys):
    configure_logging("INFO")
    structlog.get_logger("test").info("searched", hits=3)
    captured = capsys.readouterr()
    line = (captured.out + captured.err).strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["message"] == "searched"
    assert parsed["hits"] == 3


def test_the_level_is_applied():
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
    configure_logging("INFO")
