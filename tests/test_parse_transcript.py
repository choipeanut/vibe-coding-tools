"""Tests for parse_transcript.py"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from parse_transcript import (
    build_sequences,
    compute_features,
    is_real_user_prompt,
    load_records,
    parse_transcript,
    render_short_session,
)
from filters import MIN_EDITS, MIN_PROMPTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_session.jsonl")


def _write_jsonl(records: list[dict]) -> str:
    tf = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".jsonl", delete=False
    )
    for r in records:
        tf.write(json.dumps(r, ensure_ascii=False) + "\n")
    tf.close()
    return tf.name


def _make_user(text: str, idx: int = 0) -> dict:
    return {
        "type": "user",
        "message": {"role": "user", "content": text},
        "uuid": f"u{idx}",
        "timestamp": f"2026-04-29T10:0{idx}:00.000Z",
        "cwd": "C:\\Users\\<user>\\<project>",
        "sessionId": "test-session",
    }


def _make_assistant_edit(file_path: str, tool_id: str = "t0") -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "Edit",
                    "input": {"file_path": file_path, "old_string": "x", "new_string": "y"},
                }
            ],
        },
        "uuid": f"a{tool_id}",
        "timestamp": "2026-04-29T10:01:00.000Z",
        "cwd": "C:\\Users\\<user>\\<project>",
        "sessionId": "test-session",
    }


# ---------------------------------------------------------------------------
# Test 1: Prompt extraction filters slash-command internals
# ---------------------------------------------------------------------------

class TestPromptExtraction:
    def test_real_prompt_passes(self):
        rec = _make_user("꽃 모양 만들어줘")
        assert is_real_user_prompt(rec)

    def test_slash_command_filtered(self):
        rec = _make_user("<command-name>blog</command-name>")
        assert not is_real_user_prompt(rec)

    def test_interrupted_filtered(self):
        rec = _make_user("[Request interrupted by user] something")
        assert not is_real_user_prompt(rec)

    def test_system_type_filtered(self):
        rec = {"type": "system", "content": "something"}
        assert not is_real_user_prompt(rec)

    def test_fixture_prompt_count(self):
        records = load_records(FIXTURE)
        seqs = build_sequences(records)
        # Fixture must have enough real user prompts to exercise full-blog path (≥MIN_PROMPTS)
        assert len(seqs["user_prompts"]) >= MIN_PROMPTS


# ---------------------------------------------------------------------------
# Test 2: Stuck-pair detection
# ---------------------------------------------------------------------------

class TestStuckPairDetection:
    def test_detects_stuck_pair(self):
        prompts_data = [
            _make_user("코드 작성해줘", 0),
            _make_user("에러가 났어 다시 해줘", 1),
            _make_user("이번엔 됐어", 2),
        ]
        edits = [
            _make_assistant_edit("foo.py", "t0"),
            _make_assistant_edit("bar.py", "t1"),
        ]
        path = _write_jsonl(prompts_data + edits)
        try:
            records = load_records(path)
            seqs = build_sequences(records)
            features = compute_features(seqs)
            assert len(features["stuck_pairs"]) >= 1
        finally:
            os.unlink(path)

    def test_no_stuck_pair_clean_session(self):
        prompts_data = [
            _make_user("파일 만들어줘", 0),
            _make_user("내용 추가해줘", 1),
            _make_user("확인해줘", 2),
        ]
        edits = [_make_assistant_edit("foo.py", "t0"), _make_assistant_edit("bar.py", "t1")]
        path = _write_jsonl(prompts_data + edits)
        try:
            records = load_records(path)
            seqs = build_sequences(records)
            features = compute_features(seqs)
            assert features["stuck_pairs"] == []
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Test 3: Final-result section rendering and 6-section output
# ---------------------------------------------------------------------------

class TestSectionRendering:
    def test_full_session_has_six_sections(self):
        md = parse_transcript(FIXTURE)
        section_headers = [l for l in md.splitlines() if l.startswith("## ")]
        assert len(section_headers) >= 6, f"Got {len(section_headers)} sections: {section_headers}"

    def test_short_session_returns_stub(self):
        records = [
            _make_user("안녕", 0),
            _make_user("ok", 1),
        ]
        path = _write_jsonl(records)
        try:
            result = parse_transcript(path)
            assert "너무 짧습니다" in result
            # Should NOT have full 6-section structure
            section_headers = [l for l in result.splitlines() if l.startswith("## ")]
            assert len(section_headers) < 6
        finally:
            os.unlink(path)

    def test_results_section_lists_files(self):
        prompts_data = [_make_user(f"작업 {i}", i) for i in range(4)]
        edits = [
            _make_assistant_edit("alpha.py", "t0"),
            _make_assistant_edit("beta.py", "t1"),
            _make_assistant_edit("gamma.py", "t2"),
        ]
        path = _write_jsonl(prompts_data + edits)
        try:
            md = parse_transcript(path)
            assert "alpha.py" in md or "beta.py" in md
        finally:
            os.unlink(path)
