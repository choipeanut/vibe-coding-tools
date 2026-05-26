"""
archive_session.py — Claude Code SessionEnd hook
Reads JSON from stdin, copies the transcript to ~/vibe-coding-archive/.
Always exits 0 to avoid blocking Claude Code shutdown.
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone


ARCHIVE_DIR = os.path.expanduser("~/vibe-coding-archive")
ERROR_LOG = os.path.join(os.path.expanduser("~/.claude/hooks"), "errors.log")


def log_error(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts}\tarchive_session_error\t{msg}\n")
    except Exception:
        pass


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception as e:
        log_error(f"stdin parse failed: {e}")
        sys.exit(0)

    transcript_path = data.get("transcript_path", "")
    if not transcript_path:
        log_error("no transcript_path in hook payload")
        sys.exit(0)

    if not os.path.isfile(transcript_path):
        log_error(f"transcript not found: {transcript_path}")
        sys.exit(0)

    try:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        cwd_basename = os.path.basename(
            data.get("cwd", "unknown").rstrip("/\\")
        ) or "unknown"
        dest_name = f"{ts}_{cwd_basename}.jsonl"
        dest_path = os.path.join(ARCHIVE_DIR, dest_name)
        shutil.copy2(transcript_path, dest_path)
    except Exception as e:
        log_error(f"copy failed: {e} | src={transcript_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()
