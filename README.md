# Claude Memory System

Persistent memory for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Automatically captures, compiles, and retrieves knowledge from your AI coding sessions.

> Adapted from [Cole Medin's claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) with hierarchical journal structure and subdirectory installation support.

## How It Works

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Claude Code    │────>│  Hooks       │────>│  flush.py       │
│  Session        │     │  (auto-fire) │     │  (background)   │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                      │
                                                      v
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  knowledge/     │<────│  compile.py  │<────│  journal/       │
│  (wiki articles)│     │  (LLM)       │     │  (daily logs)   │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

1. **Capture**: Hooks fire at session start, end, and before context compaction. They extract conversation context and spawn a background flush process.
2. **Flush**: `flush.py` uses the Claude Agent SDK to decide what's worth saving, then appends structured entries to `journal/YYYY/MM/YYYY-MM-DD.md`.
3. **Compile**: `compile.py` reads journal logs and produces structured wiki articles in `knowledge/`. This runs automatically after the configured hour (default: 6 PM) or manually on demand.

At personal scale (50-500 articles), a structured markdown index outperforms vector similarity search — no RAG needed.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** package manager
- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** CLI with hooks support
- **Anthropic API credentials** (automatically available via Claude Code at `~/.claude/.credentials.json`)

## Installation

### Option 1: Clone as a subdirectory

```bash
cd your-project
git clone https://github.com/bmazeraski/claude_memory_system.git claude_memory_system
python claude_memory_system/setup.py
```

### Option 2: Add as a git submodule

```bash
cd your-project
git submodule add https://github.com/bmazeraski/claude_memory_system.git claude_memory_system
python claude_memory_system/setup.py
```

The setup script will:
- Install Python dependencies via `uv`
- Configure Claude Code hooks in `.claude/settings.json` (creates or merges)
- Verify the directory structure

## Configuration

Set these environment variables to customize behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_MEMORY_TZ` | `UTC` | Timezone for timestamps in journal logs |
| `CLAUDE_MEMORY_COMPILE_HOUR` | `18` | Hour (24h) after which auto-compilation triggers |

Example (add to your shell profile):

```bash
export CLAUDE_MEMORY_TZ="America/Chicago"
export CLAUDE_MEMORY_COMPILE_HOUR="20"
```

## Manual Operations

All commands are run from your **project root** (the parent of `claude_memory_system/`).

### Compile journal logs into knowledge articles

```bash
# Compile new/changed logs only
uv run --project claude_memory_system python claude_memory_system/scripts/compile.py

# Force recompile everything
uv run --project claude_memory_system python claude_memory_system/scripts/compile.py --all

# Compile a specific log
uv run --project claude_memory_system python claude_memory_system/scripts/compile.py --file journal/2026/04/2026-04-01.md

# Preview what would be compiled
uv run --project claude_memory_system python claude_memory_system/scripts/compile.py --dry-run
```

### Query the knowledge base

```bash
# Ask a question
uv run --project claude_memory_system python claude_memory_system/scripts/query.py "What auth patterns do I use?"

# Ask and save the answer as a Q&A article
uv run --project claude_memory_system python claude_memory_system/scripts/query.py "What's my error handling strategy?" --file-back
```

### Lint the knowledge base

```bash
# Run all checks (includes LLM-based contradiction detection)
uv run --project claude_memory_system python claude_memory_system/scripts/lint.py

# Structural checks only (free, instant)
uv run --project claude_memory_system python claude_memory_system/scripts/lint.py --structural-only
```

## Architecture

### Directory Structure

```
your-project/
├── .claude/
│   └── settings.json              # Hook configuration (auto-created by setup.py)
└── claude_memory_system/          # This repo
    ├── AGENTS.md                  # Schema + full technical reference
    ├── pyproject.toml             # Python dependencies
    ├── setup.py                   # Installation script
    ├── hooks/                     # Claude Code lifecycle hooks
    │   ├── _shared.py             # Shared hook logic
    │   ├── session-start.py       # Injects KB context at session start
    │   ├── session-end.py         # Captures context at session end
    │   └── pre-compact.py         # Captures context before auto-compaction
    ├── scripts/                   # CLI tools
    │   ├── config.py              # Path constants + configuration
    │   ├── utils.py               # Shared utilities
    │   ├── compile.py             # Journal -> knowledge compiler
    │   ├── flush.py               # Conversation -> journal extractor
    │   ├── query.py               # Knowledge base query engine
    │   └── lint.py                # 7 health checks
    ├── journal/                   # Daily conversation logs (YYYY/MM/YYYY-MM-DD.md)
    └── knowledge/                 # Compiled knowledge (LLM-owned)
        ├── index.md               # Master catalog
        ├── log.md                 # Build log
        ├── concepts/              # Atomic knowledge articles
        ├── connections/           # Cross-cutting insights
        └── qa/                    # Filed Q&A answers
```

### Hook Lifecycle

| Hook | When | What It Does |
|------|------|-------------|
| `SessionStart` | Session begins | Injects KB index + recent log into conversation context |
| `PreCompact` | Before auto-compaction | Captures context that would be lost to summarization |
| `SessionEnd` | Session ends | Captures final conversation context |

Both `PreCompact` and `SessionEnd` spawn `flush.py` as a background process. `flush.py` uses the Claude Agent SDK to extract key decisions, lessons, and insights, then appends them to the daily journal log.

### Three-Stage Pipeline

1. **Capture** (hooks) - Pure local I/O, no API calls, < 1 second
2. **Flush** (flush.py) - Background LLM call, ~$0.02-0.05 per session
3. **Compile** (compile.py) - Background LLM call, ~$0.45-0.65 per journal log

## Costs

| Operation | Approximate Cost |
|-----------|-----------------|
| Memory flush (per session) | $0.02-0.05 |
| Compile one journal log | $0.45-0.65 |
| Query (no file-back) | $0.15-0.25 |
| Query (with file-back) | $0.25-0.40 |
| Full lint (with contradictions) | $0.15-0.25 |
| Structural lint only | Free |

## Obsidian Integration

The knowledge base uses `[[wikilinks]]` throughout — it works natively in [Obsidian](https://obsidian.md/). Point a vault at `knowledge/` for graph view, backlinks, and search.

## Troubleshooting

### Hooks not firing
- Verify `.claude/settings.json` exists in your project root (not inside `claude_memory_system/`)
- Check that Claude Code supports hooks in your version
- Run `python claude_memory_system/setup.py` to reconfigure

### "uv not found"
- Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux)
- Or: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows)

### Dependencies not installing
- Run manually: `uv sync --project claude_memory_system`
- Ensure Python 3.12+ is available

### Flush/compile not running
- Check `claude_memory_system/scripts/flush.log` for errors
- Verify API credentials exist at `~/.claude/.credentials.json`

## Attribution

Based on [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) by [Cole Medin](https://github.com/coleam00).

## License

MIT - See [LICENSE](LICENSE) for details.
