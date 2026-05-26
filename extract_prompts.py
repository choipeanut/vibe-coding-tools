"""
extract_prompts.py — Claude Code history.jsonl → best-prompts CLI
Usage: python extract_prompts.py --project <substring> --top <N> [--format md|json] [--since YYYY-MM-DD]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HISTORY_PATH = os.path.expanduser("~/.claude/history.jsonl")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
SESSION_GAP_SECONDS = 30 * 60  # 30 min = new session

sys.path.insert(0, os.path.dirname(__file__))
from filters import STUCK_WORDS


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def parse_ts(raw) -> float:
    """Return UTC timestamp as float seconds. Handles ISO string or Unix ms int."""
    if isinstance(raw, (int, float)):
        # Unix milliseconds
        return raw / 1000.0
    if isinstance(raw, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                continue
    return 0.0


def ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts_to_display(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Load history
# ---------------------------------------------------------------------------

def load_history(since_ts: float = 0.0) -> list[dict]:
    if not os.path.isfile(HISTORY_PATH):
        return []
    entries = []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(obj.get("timestamp", 0))
            if ts < since_ts:
                continue
            # Normalise: support both 'cwd' and 'project' field names
            if "cwd" not in obj and "project" in obj:
                obj["cwd"] = obj["project"]
            entries.append({**obj, "_ts": ts})
    return sorted(entries, key=lambda e: e["_ts"])


# ---------------------------------------------------------------------------
# Filter + cluster into sessions
# ---------------------------------------------------------------------------

def filter_by_project(entries: list[dict], project: str) -> list[dict]:
    return [e for e in entries if project.lower() in e.get("cwd", "").lower()]


def cluster_sessions(entries: list[dict]) -> list[list[dict]]:
    if not entries:
        return []
    sessions = []
    current = [entries[0]]
    for e in entries[1:]:
        if e["_ts"] - current[-1]["_ts"] > SESSION_GAP_SECONDS:
            sessions.append(current)
            current = [e]
        else:
            current.append(e)
    sessions.append(current)
    return sessions


# ---------------------------------------------------------------------------
# Cross-reference transcript for tool-use count
# ---------------------------------------------------------------------------

def _find_transcript(session_id: str, cwd: str) -> str | None:
    """Find the JSONL transcript for a given sessionId."""
    # Encode cwd the same way Claude Code does on Windows
    encoded = cwd.replace("\\", "-").replace("/", "-").replace(":", "-").replace(" ", "-")
    # Collapse multiple dashes
    import re
    encoded = re.sub(r"-+", "-", encoded).strip("-")
    candidate_dirs = [
        os.path.join(PROJECTS_DIR, encoded),
        PROJECTS_DIR,
    ]
    for d in candidate_dirs:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if session_id in fname and fname.endswith(".jsonl"):
                return os.path.join(d, fname)
    # Brute-force search all project dirs
    for proj_dir in os.listdir(PROJECTS_DIR):
        full = os.path.join(PROJECTS_DIR, proj_dir)
        if not os.path.isdir(full):
            continue
        for fname in os.listdir(full):
            if session_id in fname and fname.endswith(".jsonl"):
                return os.path.join(full, fname)
    return None


def _count_successful_tool_uses_after(transcript_path: str, prompt_ts: float, window: int = 5) -> int:
    """Count successful tool uses in the next `window` assistant turns after prompt_ts."""
    try:
        records = []
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        count = 0
        after = False
        turns = 0
        for rec in records:
            ts = parse_ts(rec.get("timestamp", 0))
            if not after and ts >= prompt_ts:
                after = True
            if not after:
                continue
            if rec.get("type") == "tool_result":
                # Check success: no obvious error in content
                content = rec.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )
                lower = content.lower()
                if not any(w in lower for w in ("error", "fail", "traceback", "exception")):
                    count += 1
                turns += 1
                if turns >= window:
                    break
        return count
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_entry(entry: dict, session_entries: list[dict], idx_in_session: int) -> int:
    text = entry.get("display", "")
    score = 0

    # +1 if prompt length > 200 chars
    if len(text) > 200:
        score += 1

    # +1 if contains fenced code block or file path token
    if "```" in text or (
        "/" in text and any(
            t for t in text.split() if "/" in t and "." in t.split("/")[-1]
        )
    ) or (
        "\\" in text and any(
            t for t in text.split() if "\\" in t and "." in t.split("\\")[-1]
        )
    ):
        score += 1

    # −3 if next prompt in same session contains a STUCK_WORD
    if idx_in_session + 1 < len(session_entries):
        next_text = session_entries[idx_in_session + 1].get("display", "").lower()
        if any(w in next_text for w in STUCK_WORDS):
            score -= 3

    # +2 if followed within same session by ≥2 successful tool uses
    session_id = entry.get("sessionId", "")
    cwd = entry.get("cwd", "")
    if session_id:
        transcript = _find_transcript(session_id, cwd)
        if transcript:
            n_ok = _count_successful_tool_uses_after(transcript, entry["_ts"])
            if n_ok >= 2:
                score += 2

    return score


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _truncate(text: str, max_lines: int = 10) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n..."


def format_md(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"## #{i} — 점수 {r['score']:+d} · {r['timestamp']} · {r['project']}")
        parts.append(f"세션 ID: `{r['session_id']}`")
        parts.append("")
        for line in _truncate(r["text"]).splitlines():
            parts.append(f"> {line}")
        parts.append("")
    return "\n".join(parts)


def format_json(results: list[dict]) -> str:
    return json.dumps(results, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Best prompts from ~/.claude/history.jsonl")
    parser.add_argument("--project", required=True, help="cwd substring filter")
    parser.add_argument("--top", type=int, default=10, help="number of results")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--since", default=None, help="YYYY-MM-DD lower bound")
    args = parser.parse_args()

    since_ts = 0.0
    if args.since:
        try:
            dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            since_ts = dt.timestamp()
        except ValueError:
            print(f"--since 형식 오류: {args.since} (YYYY-MM-DD 필요)", file=sys.stderr)
            sys.exit(1)

    entries = load_history(since_ts)
    entries = filter_by_project(entries, args.project)

    if not entries:
        print(f"'{args.project}' 프로젝트 관련 프롬프트를 찾지 못했습니다.", file=sys.stderr)
        sys.exit(0)

    sessions = cluster_sessions(entries)

    scored = []
    for session in sessions:
        for idx, entry in enumerate(session):
            text = entry.get("display", "").strip()
            if not text:
                continue
            s = score_entry(entry, session, idx)
            scored.append({
                "score": s,
                "timestamp": ts_to_display(entry["_ts"]),
                "cwd": entry.get("cwd", ""),
                "project": os.path.basename(entry.get("cwd", "").rstrip("/\\")),
                "session_id": entry.get("sessionId", ""),
                "text": text,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[: args.top]

    if args.format == "json":
        print(format_json(top))
    else:
        print(format_md(top))


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
