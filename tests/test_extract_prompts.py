"""Tests for extract_prompts.py"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from extract_prompts import (
    cluster_sessions,
    filter_by_project,
    format_json,
    format_md,
    load_history,
    parse_ts,
    score_entry,
    SESSION_GAP_SECONDS,
)
from filters import STUCK_WORDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_history(entries: list[dict]) -> str:
    tf = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".jsonl", delete=False
    )
    for e in entries:
        tf.write(json.dumps(e, ensure_ascii=False) + "\n")
    tf.close()
    return tf.name


def _entry(display: str, cwd: str, ts_seconds: float, session_id: str = "s1") -> dict:
    return {
        "display": display,
        "cwd": cwd,
        "timestamp": int(ts_seconds * 1000),  # Unix ms
        "sessionId": session_id,
        "pastedContents": {},
        "_ts": ts_seconds,
    }


BASE_TS = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc).timestamp()


# ---------------------------------------------------------------------------
# Test 1: parse_ts handles both formats
# ---------------------------------------------------------------------------

class TestParseTs:
    def test_unix_milliseconds(self):
        ts = parse_ts(1774510621599)
        assert ts == pytest.approx(1774510621.599, rel=1e-6)

    def test_iso_string(self):
        ts = parse_ts("2026-04-29T10:00:00.000Z")
        assert ts > 0

    def test_zero_fallback(self):
        assert parse_ts(None) == 0.0


# ---------------------------------------------------------------------------
# Test 2: filter_by_project
# ---------------------------------------------------------------------------

class TestFilterByProject:
    def test_matches_substring(self):
        entries = [
            _entry("a", "C:\\Users\\user\\asset", BASE_TS),
            _entry("b", "C:\\Users\\user\\other", BASE_TS + 60),
        ]
        result = filter_by_project(entries, "asset")
        assert len(result) == 1
        assert result[0]["display"] == "a"

    def test_case_insensitive(self):
        entries = [_entry("x", "C:\\Users\\user\\MyProject", BASE_TS)]
        assert len(filter_by_project(entries, "myproject")) == 1

    def test_empty_when_no_match(self):
        entries = [_entry("x", "C:\\Users\\user\\asset", BASE_TS)]
        assert filter_by_project(entries, "zzz") == []


# ---------------------------------------------------------------------------
# Test 3: cluster_sessions splits on 30-min gap
# ---------------------------------------------------------------------------

class TestClusterSessions:
    def test_same_session_within_gap(self):
        entries = [
            _entry("a", "/proj", BASE_TS),
            _entry("b", "/proj", BASE_TS + 100),
        ]
        sessions = cluster_sessions(entries)
        assert len(sessions) == 1
        assert len(sessions[0]) == 2

    def test_split_on_30min_gap(self):
        entries = [
            _entry("a", "/proj", BASE_TS),
            _entry("b", "/proj", BASE_TS + SESSION_GAP_SECONDS + 1),
        ]
        sessions = cluster_sessions(entries)
        assert len(sessions) == 2

    def test_empty_input(self):
        assert cluster_sessions([]) == []


# ---------------------------------------------------------------------------
# Test 4: score_entry — stuck-word penalty and length bonus
# ---------------------------------------------------------------------------

class TestScoreEntry:
    def test_long_prompt_gets_plus1(self):
        e = _entry("x" * 201, "/proj", BASE_TS)
        session = [e]
        s = score_entry(e, session, 0)
        assert s >= 1

    def test_stuck_word_next_prompt_minus3(self):
        e1 = _entry("좋은 프롬프트", "/proj", BASE_TS)
        e2 = _entry("에러가 났어 다시 해줘", "/proj", BASE_TS + 60)
        session = [e1, e2]
        s = score_entry(e1, session, 0)
        assert s <= -3

    def test_file_path_token_gets_plus1(self):
        e = _entry("src/components/Button.tsx 파일 수정해줘", "/proj", BASE_TS)
        session = [e]
        s = score_entry(e, session, 0)
        assert s >= 1


# ---------------------------------------------------------------------------
# Test 5: output formatters
# ---------------------------------------------------------------------------

class TestFormatters:
    SAMPLE = [
        {"score": 3, "timestamp": "2026-04-29 10:00", "cwd": "/proj", "project": "proj",
         "session_id": "abc123", "text": "Hello"},
        {"score": 1, "timestamp": "2026-04-29 10:05", "cwd": "/proj", "project": "proj",
         "session_id": "abc123", "text": "World"},
    ]

    def test_md_format_has_headers(self):
        md = format_md(self.SAMPLE)
        headers = [l for l in md.splitlines() if l.startswith("## ")]
        assert len(headers) == 2

    def test_json_format_parseable(self):
        output = format_json(self.SAMPLE)
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["score"] == 3
