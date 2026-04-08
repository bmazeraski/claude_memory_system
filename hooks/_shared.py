"""
Shared logic for SessionEnd and PreCompact hooks.

Both hooks follow the same pattern:
1. Parse hook input from stdin (JSON with session_id, transcript_path)
2. Extract conversation context from JSONL transcript
3. Write context to a temp file
4. Spawn flush.py as a background process

The only differences are the hook name, minimum turn threshold,
and context file naming prefix.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_TURNS = 30
MAX_CONTEXT_CHARS = 15_000


def extract_conversation_context(transcript_path: Path) -> tuple[str, int]:
    """Read JSONL transcript and extract last ~N conversation turns as markdown."""
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


def parse_hook_input() -> dict:
    """Read and parse hook input JSON from stdin.

    Handles Windows backslash escaping issues in transcript paths.
    """
    raw_input = sys.stdin.read()
    try:
        return json.loads(raw_input)
    except json.JSONDecodeError:
        fixed_input = re.sub(r'(?<!\\)\\(?!["\\])', r'\\\\', raw_input)
        return json.loads(fixed_input)


def spawn_flush(root: Path, scripts_dir: Path, context_file: Path, session_id: str) -> None:
    """Spawn flush.py as a background process."""
    flush_script = scripts_dir / "flush.py"

    cmd = [
        "uv",
        "run",
        "--directory",
        str(root),
        "python",
        str(flush_script),
        str(context_file),
        session_id,
    ]

    # On Windows, use CREATE_NO_WINDOW to avoid flash console window.
    # Do NOT use DETACHED_PROCESS — it breaks the Agent SDK's subprocess I/O.
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
