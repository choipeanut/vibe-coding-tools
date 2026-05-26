"""
parse_transcript.py — Claude Code session JSONL → Korean markdown blog draft
Usage: python parse_transcript.py <jsonl_path>
"""

import json
import os
import sys
from datetime import datetime, timezone

from filters import (
    STUCK_WORDS,
    MIN_PROMPTS,
    MIN_EDITS,
    TOOLS_THAT_EDIT,
    SLASH_COMMAND_PREFIXES,
    INTERRUPTED_PREFIX,
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_records(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                # Last line mid-write — silently drop
                break
            raise

    return records


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def is_real_user_prompt(record: dict) -> bool:
    if record.get("type") != "user":
        return False
    # isMeta=True marks slash-command skill injections — not typed by the user
    if record.get("isMeta"):
        return False
    text = _extract_text(record.get("message", {}).get("content", ""))
    if not text:
        return False
    for prefix in SLASH_COMMAND_PREFIXES:
        if text.startswith(prefix):
            return False
    if text.startswith(INTERRUPTED_PREFIX):
        return False
    return True


# ---------------------------------------------------------------------------
# Build sequences
# ---------------------------------------------------------------------------

def build_sequences(records: list[dict]) -> dict:
    user_prompts = []
    file_edits = []
    tool_uses_by_uuid = {}
    summary_text = None

    for rec in records:
        rtype = rec.get("type")

        if rtype == "summary":
            summary_text = rec.get("summary", "")

        elif rtype == "system":
            continue

        elif rtype == "user" and is_real_user_prompt(rec):
            text = _extract_text(rec.get("message", {}).get("content", ""))
            user_prompts.append({
                "ts": rec.get("timestamp", ""),
                "text": text,
                "idx": len(user_prompts),
                "uuid": rec.get("uuid", ""),
            })

        elif rtype == "assistant":
            content = rec.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    tool_id = block.get("id", "")
                    tool_uses_by_uuid[tool_id] = {
                        "ts": rec.get("timestamp", ""),
                        "tool_name": tool_name,
                        "input": block.get("input", {}),
                        "uuid": tool_id,
                    }
                    if tool_name in TOOLS_THAT_EDIT:
                        inp = block.get("input", {})
                        fpath = inp.get("file_path") or inp.get("path") or ""
                        file_edits.append({
                            "ts": rec.get("timestamp", ""),
                            "tool_name": tool_name,
                            "path": fpath,
                        })

        elif rtype == "tool_result":
            # tool_result records carry tool_use_id to link back
            pass

    return {
        "user_prompts": user_prompts,
        "file_edits": file_edits,
        "tool_uses_by_uuid": tool_uses_by_uuid,
        "summary_text": summary_text,
        "prompt_timeline": _build_prompt_timeline(user_prompts, file_edits),
    }


def _ts_to_seconds(ts: str) -> float:
    """Convert ISO timestamp string to float seconds for comparison."""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.timestamp()
    except Exception:
        return 0.0


def _build_prompt_timeline(user_prompts: list, file_edits: list) -> list:
    """
    For each user prompt, collect the files edited between that prompt
    and the next one. Returns a list of dicts with 'prompt' and 'files_changed'.
    """
    timeline = []
    for i, prompt in enumerate(user_prompts):
        ts_start = _ts_to_seconds(prompt["ts"])
        ts_end = (
            _ts_to_seconds(user_prompts[i + 1]["ts"])
            if i + 1 < len(user_prompts)
            else float("inf")
        )
        edits_in_range = [
            e for e in file_edits
            if ts_start <= _ts_to_seconds(e["ts"]) < ts_end
        ]
        unique_paths = list(dict.fromkeys(
            os.path.basename(e["path"]) for e in edits_in_range if e["path"]
        ))
        timeline.append({
            "prompt": prompt,
            "files_changed": unique_paths,
        })
    return timeline


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_features(seqs: dict) -> dict:
    user_prompts = seqs["user_prompts"]
    file_edits = seqs["file_edits"]

    prompt_count = len(user_prompts)
    edit_count = len(file_edits)
    unique_files = list(dict.fromkeys(e["path"] for e in file_edits if e["path"]))
    hottest_file = None
    if unique_files:
        path_counts = {}
        for e in file_edits:
            p = e["path"]
            if p:
                path_counts[p] = path_counts.get(p, 0) + 1
        hottest_file = max(path_counts, key=path_counts.get)
        hottest_count = path_counts[hottest_file]
    else:
        hottest_count = 0

    # Stuck pairs: consecutive prompts where the LATER one contains a stuck word
    stuck_pairs = []
    for i in range(1, len(user_prompts)):
        text = user_prompts[i]["text"].lower()
        if any(w in text for w in STUCK_WORDS):
            stuck_pairs.append((user_prompts[i - 1], user_prompts[i]))

    # Turning point: after a stuck pair ending at index i, next 3 prompts have no stuck words
    turning_point = None
    for _, stuck_prompt in stuck_pairs:
        i = stuck_prompt["idx"]
        following = user_prompts[i + 1 : i + 4]
        if following and not any(
            any(w in p["text"].lower() for w in STUCK_WORDS) for p in following
        ):
            turning_point = user_prompts[i + 1] if i + 1 < len(user_prompts) else None
            break

    return {
        "prompt_count": prompt_count,
        "edit_count": edit_count,
        "unique_files": unique_files,
        "hottest_file": hottest_file,
        "hottest_count": hottest_count,
        "stuck_pairs": stuck_pairs,
        "turning_point": turning_point,
    }


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _truncate_prompt(text: str, max_lines: int = 5) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n..."


def _quote_block(text: str) -> str:
    truncated = _truncate_prompt(text)
    return "\n".join("> " + line for line in truncated.splitlines())


def _format_duration(ts_first: str, ts_last: str) -> str:
    try:
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        t1 = datetime.strptime(ts_first, fmt).replace(tzinfo=timezone.utc)
        t2 = datetime.strptime(ts_last, fmt).replace(tzinfo=timezone.utc)
        total = int((t2 - t1).total_seconds())
        h, rem = divmod(total, 3600)
        m, _ = divmod(rem, 60)
        return f"{h:02d}:{m:02d}"
    except Exception:
        return "??:??"


def _first_line_summary(text: str, max_chars: int = 40) -> str:
    first = text.splitlines()[0] if text else ""
    if len(first) > max_chars:
        return first[:max_chars - 1] + "…"
    return first


def _infer_tags(unique_files: list[str]) -> list[str]:
    ext_map = {
        ".py": "python",
        ".tsx": "react",
        ".jsx": "react",
        ".html": "web",
        ".md": "docs",
        ".ipynb": "notebook",
    }
    tags = {"vibe-coding"}
    for path in unique_files:
        _, ext = os.path.splitext(path)
        if ext.lower() in ext_map:
            tags.add(ext_map[ext.lower()])
    return sorted(tags)


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_markdown(records: list[dict], seqs: dict, features: dict, path: str) -> str:
    user_prompts = seqs["user_prompts"]
    summary_text = seqs["summary_text"]

    session_id = records[0].get("sessionId", "") if records else ""
    cwd = next((r.get("cwd", "") for r in records if r.get("cwd")), "")
    project_name = os.path.basename(cwd.rstrip("/\\")) if cwd else "프로젝트"

    ts_first = user_prompts[0]["ts"] if user_prompts else (records[0].get("timestamp", "") if records else "")
    ts_last = records[-1].get("timestamp", "") if records else ""

    try:
        dt = datetime.strptime(ts_first, "%Y-%m-%dT%H:%M:%S.%fZ")
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_str = ts_first[:16]

    first_prompt_text = user_prompts[0]["text"] if user_prompts else ""
    title_summary = _first_line_summary(first_prompt_text)
    duration = _format_duration(ts_first, ts_last)

    lines = []

    # Header
    lines.append(f"# {project_name} — {title_summary}")
    lines.append("")
    lines.append(
        f"> {date_str} · 프롬프트 {features['prompt_count']}개 · "
        f"수정 파일 {features['edit_count']}개 · 소요 {duration}"
    )
    lines.append("")

    # §1 목표
    lines.append("## 1. 목표")
    if summary_text:
        lines.append(summary_text)
    elif user_prompts:
        lines.append(_first_line_summary(user_prompts[0]["text"], 80))
    else:
        lines.append("(프롬프트 없음)")
    lines.append("")

    # §2 개발 흐름 — prompt → files changed timeline
    lines.append("## 2. 개발 흐름")
    lines.append("")
    timeline = seqs.get("prompt_timeline", [])
    for i, entry in enumerate(timeline, 1):
        prompt_text = entry["prompt"]["text"]
        files = entry["files_changed"]
        # Raw prompt (verbatim, single-line summary for table)
        lines.append(f"**[{i}]** 원본 프롬프트")
        lines.append(_quote_block(prompt_text))
        lines.append("")
        # ☆ polishing placeholder — blog.md command rewrites this
        lines.append(f"✏️ *전문가 버전: (아래 /blog 단계에서 자동 작성)*")
        lines.append("")
        if files:
            lines.append(f"📁 변경된 파일: `{'`, `'.join(files)}`")
        else:
            lines.append("📁 변경된 파일: (없음)")
        lines.append("")
        if i < len(timeline):
            lines.append("---")
            lines.append("")

    # §3 막혔던 지점
    lines.append("## 3. 막혔던 지점")
    if features["stuck_pairs"]:
        for before, stuck in features["stuck_pairs"]:
            lines.append("")
            lines.append(f"- **상황**: {_first_line_summary(before['text'], 80)}")
            lines.append("- **막힌 프롬프트**:")
            lines.append(_quote_block(stuck["text"]))
    else:
        lines.append("")
        lines.append("(막힌 지점 없음 — 순조롭게 진행)")
    lines.append("")

    # §4 전환점
    lines.append("## 4. 전환점")
    if features["turning_point"]:
        tp = features["turning_point"]
        lines.append("")
        lines.append(_quote_block(tp["text"]))
        lines.append("")
        text = tp["text"]
        if "/" in text and any(c in text for c in "._"):
            reason = "파일을 명시했다"
        elif "```" in text or len(text) > 200:
            reason = "예시를 줬다"
        elif len(text) < 60:
            reason = "범위를 좁혔다"
        else:
            reason = "더 구체적이었다"
        lines.append(f"**왜 통했나**: {reason}")
    else:
        lines.append("")
        lines.append("(전환점 없음)")
    lines.append("")

    # §5 결과
    lines.append("## 5. 결과")
    unique_files = features["unique_files"]
    if unique_files:
        display = unique_files[:10]
        extra = len(unique_files) - 10
        file_list = ", ".join(os.path.basename(f) for f in display)
        if extra > 0:
            file_list += f" 외 {extra}개"
        lines.append(f"- 최종 수정/생성된 파일: {file_list}")
    else:
        lines.append("- 최종 수정/생성된 파일: (없음)")
    if features["hottest_file"]:
        lines.append(
            f"- 가장 많이 수정된 파일: {os.path.basename(features['hottest_file'])} "
            f"({features['hottest_count']}회)"
        )
    lines.append("")

    # §6 회고
    lines.append("## 6. 회고 — 다음에 같은 작업 시작한다면")
    if features["turning_point"]:
        tp_text = features["turning_point"]["text"]
        lines.append("전환점 프롬프트 패턴을 활용한 시작 방법:")
        lines.append("")
        lines.append("```")
        reuse = _truncate_prompt(tp_text, 8)
        lines.append(reuse)
        lines.append("```")
    elif user_prompts:
        lines.append("첫 프롬프트를 더 구체적으로 작성한 버전:")
        lines.append("")
        lines.append("```")
        lines.append(_first_line_summary(user_prompts[0]["text"], 120))
        lines.append("구체적인 조건: [파일명], [기대 동작], [제약]을 포함해서 요청")
        lines.append("```")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*세션 ID: `{session_id}` · 원본 transcript: `{path}`*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Short-session stub
# ---------------------------------------------------------------------------

def render_short_session(records: list[dict], path: str) -> str:
    session_id = records[0].get("sessionId", "") if records else ""
    cwd = next((r.get("cwd", "") for r in records if r.get("cwd")), "")
    project_name = os.path.basename(cwd.rstrip("/\\")) if cwd else "프로젝트"
    ts = records[0].get("timestamp", "") if records else ""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_str = ts[:16]

    seqs = build_sequences(records)
    prompts = seqs["user_prompts"]
    summary = prompts[0]["text"][:80] if prompts else "(프롬프트 없음)"

    return (
        f"# {project_name} — {date_str}\n\n"
        f"이 세션은 블로그용으로는 너무 짧습니다\n\n"
        f"요약: {summary}\n\n"
        f"---\n\n"
        f"*세션 ID: `{session_id}` · 원본 transcript: `{path}`*\n"
    )


# ---------------------------------------------------------------------------
# JSON data extractor (for /blog Claude-writing mode)
# ---------------------------------------------------------------------------

def extract_session_data(jsonl_path: str) -> dict:
    """
    Extract structured session data as a dict.
    Used by /blog command so Claude can write the final blog post.
    Returns None if session is too short.
    """
    records = load_records(jsonl_path)
    seqs = build_sequences(records)
    user_prompts = seqs["user_prompts"]
    file_edits = seqs["file_edits"]

    session_id = records[0].get("sessionId", "") if records else ""
    # cwd may be missing from the first record; scan for the first record that has it
    cwd = next((r.get("cwd", "") for r in records if r.get("cwd")), "")
    project = os.path.basename(cwd.rstrip("/\\")) if cwd else "프로젝트"

    ts_first = user_prompts[0]["ts"] if user_prompts else (records[0].get("timestamp", "") if records else "")
    ts_last = records[-1].get("timestamp", "") if records else ""

    try:
        dt = datetime.strptime(ts_first, "%Y-%m-%dT%H:%M:%S.%fZ")
        date_str = dt.strftime("%Y-%m-%d")
        datetime_str = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_str = ts_first[:10]
        datetime_str = ts_first[:16]

    duration = _format_duration(ts_first, ts_last)
    too_short = len(user_prompts) < MIN_PROMPTS or len(file_edits) < MIN_EDITS

    if too_short:
        return {
            "too_short": True,
            "session_id": session_id,
            "project": project,
            "cwd": cwd,
            "date": date_str,
            "datetime": datetime_str,
            "summary": user_prompts[0]["text"][:80] if user_prompts else "",
        }

    features = compute_features(seqs)
    timeline = seqs.get("prompt_timeline", [])

    # Build path_counts for all_files
    path_counts: dict[str, int] = {}
    for e in file_edits:
        p = e["path"]
        if p:
            path_counts[p] = path_counts.get(p, 0) + 1

    all_files_unique = list(dict.fromkeys(e["path"] for e in file_edits if e["path"]))

    return {
        "too_short": False,
        "session_id": session_id,
        "project": project,
        "cwd": cwd,
        "date": date_str,
        "datetime": datetime_str,
        "duration": duration,
        "prompt_count": features["prompt_count"],
        "edit_count": features["edit_count"],
        # Each step: raw prompt text + files changed immediately after
        "steps": [
            {
                "idx": i + 1,
                "prompt": entry["prompt"]["text"],
                "files_changed": entry["files_changed"],
            }
            for i, entry in enumerate(timeline)
        ],
        # Stuck moments: before-prompt → stuck-prompt pairs
        "stuck_pairs": [
            {
                "before": before["text"],
                "stuck": stuck["text"],
            }
            for before, stuck in features["stuck_pairs"]
        ],
        "turning_point": features["turning_point"]["text"] if features["turning_point"] else None,
        # Full file list (basename only, deduped)
        "all_files": [os.path.basename(p) for p in all_files_unique],
        "hottest_file": os.path.basename(features["hottest_file"]) if features["hottest_file"] else None,
        "hottest_file_count": features["hottest_count"],
        "transcript_path": jsonl_path,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_transcript(jsonl_path: str) -> str:
    records = load_records(jsonl_path)

    seqs = build_sequences(records)
    user_prompts = seqs["user_prompts"]
    file_edits = seqs["file_edits"]

    # Short-session guard
    if len(user_prompts) < MIN_PROMPTS or len(file_edits) < MIN_EDITS:
        return render_short_session(records, jsonl_path)

    features = compute_features(seqs)
    return render_markdown(records, seqs, features, jsonl_path)


if __name__ == "__main__":
    import argparse as _ap
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    _parser = _ap.ArgumentParser()
    _parser.add_argument("jsonl_path")
    _parser.add_argument("--json", action="store_true", help="Output structured JSON for Claude-writing mode")
    _args = _parser.parse_args()

    if _args.json:
        data = extract_session_data(_args.jsonl_path)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(parse_transcript(_args.jsonl_path))
