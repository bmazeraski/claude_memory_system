"""
Setup script for claude_memory_system.

Configures Claude Code hooks in the target project's .claude/settings.json
and installs Python dependencies via uv.

Usage:
    python claude_memory_system/setup.py       # from project root
    python setup.py                            # from within claude_memory_system/
"""

import json
import subprocess
import sys
from pathlib import Path

SELF_DIR = Path(__file__).resolve().parent  # claude_memory_system/

# The hooks template lives alongside this script
TEMPLATE_FILE = SELF_DIR / ".claude" / "settings.json.template"

# Hook definitions to install
HOOK_EVENTS = {
    "SessionStart": {
        "type": "command",
        "command": "uv run --project claude_memory_system python claude_memory_system/hooks/session-start.py",
        "timeout": 15,
    },
    "PreCompact": {
        "type": "command",
        "command": "uv run --project claude_memory_system python claude_memory_system/hooks/pre-compact.py",
        "timeout": 10,
    },
    "SessionEnd": {
        "type": "command",
        "command": "uv run --project claude_memory_system python claude_memory_system/hooks/session-end.py",
        "timeout": 10,
    },
}


def find_project_root() -> Path:
    """Walk up from SELF_DIR looking for .git/ to find the project root."""
    # The project root is the parent of claude_memory_system/
    candidate = SELF_DIR.parent

    # Verify it looks like a project root
    if (candidate / ".git").exists():
        return candidate

    # Walk up further in case of nested structures
    for parent in candidate.parents:
        if (parent / ".git").exists():
            return parent

    # Fall back to immediate parent
    print(f"Warning: No .git directory found. Using {candidate} as project root.")
    return candidate


def install_hooks(project_root: Path) -> None:
    """Create or merge hook configuration into .claude/settings.json."""
    claude_dir = project_root / ".claude"
    settings_file = claude_dir / "settings.json"

    if settings_file.exists():
        # Merge hooks into existing settings
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
        hooks = settings.setdefault("hooks", {})

        added = 0
        for event_name, hook_def in HOOK_EVENTS.items():
            event_hooks = hooks.setdefault(event_name, [])

            # Check if this hook command is already registered
            already_exists = False
            for matcher_group in event_hooks:
                for h in matcher_group.get("hooks", []):
                    if h.get("command", "") == hook_def["command"]:
                        already_exists = True
                        break

            if not already_exists:
                event_hooks.append({
                    "matcher": "",
                    "hooks": [hook_def],
                })
                added += 1

        settings_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        if added > 0:
            print(f"  Added {added} hook(s) to existing {settings_file}")
        else:
            print(f"  All hooks already configured in {settings_file}")
    else:
        # Create new settings file from template
        claude_dir.mkdir(parents=True, exist_ok=True)
        if TEMPLATE_FILE.exists():
            template = TEMPLATE_FILE.read_text(encoding="utf-8")
            settings_file.write_text(template, encoding="utf-8")
        else:
            # Build from HOOK_EVENTS
            settings = {"hooks": {}}
            for event_name, hook_def in HOOK_EVENTS.items():
                settings["hooks"][event_name] = [{
                    "matcher": "",
                    "hooks": [hook_def],
                }]
            settings_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        print(f"  Created {settings_file}")


def run_uv_sync() -> bool:
    """Install Python dependencies via uv."""
    try:
        result = subprocess.run(
            ["uv", "sync", "--project", str(SELF_DIR)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  Dependencies installed successfully.")
            return True
        else:
            print(f"  Warning: uv sync failed: {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("  Warning: 'uv' not found. Install it from https://docs.astral.sh/uv/")
        print("  Then run: uv sync --project claude_memory_system")
        return False


def main() -> None:
    print("Claude Memory System - Setup")
    print("=" * 40)

    project_root = find_project_root()
    print(f"\nProject root: {project_root}")
    print(f"Memory system: {SELF_DIR}")

    # Step 1: Install hooks
    print("\n1. Configuring Claude Code hooks...")
    install_hooks(project_root)

    # Step 2: Install dependencies
    print("\n2. Installing Python dependencies...")
    run_uv_sync()

    # Step 3: Verify directory structure
    print("\n3. Verifying directory structure...")
    for subdir in ["journal", "knowledge/concepts", "knowledge/connections", "knowledge/qa"]:
        path = SELF_DIR / subdir
        path.mkdir(parents=True, exist_ok=True)
    print("  All directories present.")

    # Done
    print("\n" + "=" * 40)
    print("Setup complete!")
    print("\nNext steps:")
    print("  1. Start a Claude Code session in your project")
    print("  2. The memory system will automatically capture your conversations")
    print("  3. Knowledge articles compile automatically after 6 PM (configurable)")
    print("\nOptional configuration (environment variables):")
    print("  CLAUDE_MEMORY_TZ=America/Chicago        # Set your timezone (default: UTC)")
    print("  CLAUDE_MEMORY_COMPILE_HOUR=18            # Auto-compile hour (default: 18)")
    print("\nManual commands:")
    print(f"  uv run --project {SELF_DIR.name} python {SELF_DIR.name}/scripts/compile.py")
    print(f"  uv run --project {SELF_DIR.name} python {SELF_DIR.name}/scripts/query.py \"your question\"")
    print(f"  uv run --project {SELF_DIR.name} python {SELF_DIR.name}/scripts/lint.py")


if __name__ == "__main__":
    main()
