"""
Stop hook - sweeps orphaned transcripts that SessionEnd never captured.

The SessionEnd hook only fires on graceful shutdown (`/exit`, `/clear`, clean
close). If a Claude Code session is killed abruptly (terminal closed, process
killed, host reboot), its conversation never reaches the journal.

This hook fires on every Stop event (after each assistant response) and
opportunistically scans the project's JSONL transcript directory for
abandoned sessions, then spawns flush.py for each one. State is tracked in
swept-state.json so a transcript is only re-flushed when it has new content.

The hook itself does NO API calls - only local file I/O (<1s typical).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Recursion guard
if os.environ.get("CLAUDE_INVOKED_BY"):
    sys.exit(0)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
SWEPT_STATE_FILE = SCRIPTS_DIR / "swept-state.json"

logging.basicConfig(
    filename=str(SCRIPTS_DIR / "flush.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [stop] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# A transcript whose mtime is within this window is considered "live" - either
# the current session in this window or another open Claude window. Skip it.
ACTIVE_GRACE_SECONDS = 30 * 60

MAX_TURNS = 30
MAX_CONTEXT_CHARS = 15_000
MIN_TURNS_TO_FLUSH = 5


def extract_conversation_context(transcript_path: Path) -> tuple[str, int]:
    """Read JSONL transcript and extract last ~N conversation turns as markdown.

    Mirrors the helper in session-end.py / pre-compact.py.
    """
    turns: list[str] = []

    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = entry.get("message", {})
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            else:
                role = entry.get("role", "")
                content = entry.get("content", "")

            if role not in ("user", "assistant"):
                continue

            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = "\n".join(text_parts)

            if isinstance(content, str) and content.strip():
                label = "User" if role == "user" else "Assistant"
                turns.append(f"**{label}:** {content.strip()}\n")

    recent = turns[-MAX_TURNS:]
    context = "\n".join(recent)

    if len(context) > MAX_CONTEXT_CHARS:
        context = context[-MAX_CONTEXT_CHARS:]
        boundary = context.find("\n**")
        if boundary > 0:
            context = context[boundary + 1 :]

    return context, len(recent)


def load_swept_state() -> dict:
    if SWEPT_STATE_FILE.exists():
        try:
            return json.loads(SWEPT_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_swept_state(state: dict) -> None:
    SWEPT_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def spawn_flush(
    context_file: Path, session_id: str, target_date: str | None = None
) -> bool:
    """Spawn flush.py as a background process. Returns True on successful launch."""
    flush_script = SCRIPTS_DIR / "flush.py"
    cmd = [
        "uv",
        "run",
        "--directory",
        str(ROOT),
        "python",
        str(flush_script),
        str(context_file),
        session_id,
    ]
    if target_date:
        cmd.append(target_date)

    creation_flags = (
        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        return True
    except Exception as e:
        logging.error("Failed to spawn flush.py for %s: %s", session_id, e)
        return False


def main() -> None:
    try:
        raw_input = sys.stdin.read()
        try:
            hook_input: dict = json.loads(raw_input)
        except json.JSONDecodeError:
            fixed_input = re.sub(r'(?<!\\)\\(?!["\\])', r'\\\\', raw_input)
            hook_input = json.loads(fixed_input)
    except (json.JSONDecodeError, ValueError, EOFError) as e:
        logging.error("Failed to parse stdin: %s", e)
        return

    current_session = hook_input.get("session_id", "")
    transcript_path_str = hook_input.get("transcript_path", "")

    if not transcript_path_str or not isinstance(transcript_path_str, str):
        # No transcript path, can't locate the project's transcript dir.
        return

    current_transcript = Path(transcript_path_str)
    transcripts_dir = current_transcript.parent
    if not transcripts_dir.is_dir():
        return

    swept = load_swept_state()
    now_ts = time.time()
    candidates = []

    for jsonl in transcripts_dir.glob("*.jsonl"):
        session_id = jsonl.stem
        if session_id == current_session:
            continue
        try:
            mtime = jsonl.stat().st_mtime
        except OSError:
            continue

        # Skip recently-touched transcripts - likely a live session in another window
        if now_ts - mtime < ACTIVE_GRACE_SECONDS:
            continue

        # Skip if we've already flushed this transcript at this mtime or later
        prev_mtime = swept.get(session_id, {}).get("mtime", 0.0)
        if mtime <= prev_mtime:
            continue

        candidates.append((jsonl, session_id, mtime))

    if not candidates:
        return

    logging.info(
        "Stop sweep: %d orphan transcript(s) found in %s",
        len(candidates),
        transcripts_dir,
    )

    for jsonl, session_id, mtime in candidates:
        try:
            context, turn_count = extract_conversation_context(jsonl)
        except Exception as e:
            logging.error("Context extraction failed for %s: %s", session_id, e)
            continue

        if not context.strip() or turn_count < MIN_TURNS_TO_FLUSH:
            # Mark as swept anyway so we don't re-scan an empty/tiny transcript every Stop
            swept[session_id] = {"mtime": mtime, "swept_at": _now_iso(), "skipped": True}
            continue

        timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
        context_file = SCRIPTS_DIR / f"sweep-flush-{session_id}-{timestamp}.md"
        context_file.write_text(context, encoding="utf-8")

        # Backfill into the journal for the day the session actually ran
        target_date = datetime.fromtimestamp(mtime).astimezone().strftime("%Y-%m-%d")

        if spawn_flush(context_file, session_id, target_date):
            logging.info(
                "Spawned flush.py for orphan %s (target_date=%s, %d turns, %d chars)",
                session_id,
                target_date,
                turn_count,
                len(context),
            )
            swept[session_id] = {"mtime": mtime, "swept_at": _now_iso()}

    save_swept_state(swept)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
