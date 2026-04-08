"""Path constants and configuration for the personal knowledge base.

Configuration via environment variables:
    CLAUDE_MEMORY_TZ            Timezone for timestamps (default: UTC)
    CLAUDE_MEMORY_COMPILE_HOUR  Hour (24h) after which auto-compilation triggers (default: 18)
"""

import os
from pathlib import Path
from datetime import date, datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
JOURNAL_DIR = ROOT_DIR / "journal"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
CONNECTIONS_DIR = KNOWLEDGE_DIR / "connections"
QA_DIR = KNOWLEDGE_DIR / "qa"
REPORTS_DIR = ROOT_DIR / "reports"
SCRIPTS_DIR = ROOT_DIR / "scripts"
HOOKS_DIR = ROOT_DIR / "hooks"
AGENTS_FILE = ROOT_DIR / "AGENTS.md"

INDEX_FILE = KNOWLEDGE_DIR / "index.md"
LOG_FILE = KNOWLEDGE_DIR / "log.md"
STATE_FILE = SCRIPTS_DIR / "state.json"

# ── Configuration ─────────────────────────────────────────────────────
TIMEZONE = os.environ.get("CLAUDE_MEMORY_TZ", "UTC")
COMPILE_AFTER_HOUR = int(os.environ.get("CLAUDE_MEMORY_COMPILE_HOUR", "18"))


def journal_path(d: date | datetime) -> Path:
    """Return the journal file path for a given date: journal/YYYY/MM/YYYY-MM-DD.md"""
    if isinstance(d, datetime):
        d = d.date()
    return JOURNAL_DIR / f"{d.year}" / f"{d.month:02d}" / f"{d.strftime('%Y-%m-%d')}.md"


def now_iso() -> str:
    """Current time in ISO 8601 format."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    """Current date in ISO 8601 format."""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
