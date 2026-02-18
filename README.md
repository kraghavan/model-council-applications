# Model Council

> Multi-model AI consensus framework with deliberation and memory

[![Tests](https://github.com/kraghavan/model-council-applications/actions/workflows/test.yml/badge.svg)](https://github.com/kraghavan/model-council-applications/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Model Council brings multiple AI models together to review code, architecture, and documents through **multi-round deliberation** — models discuss, reconsider, and reach consensus.

## What's Different?

| Other Tools | Model Council |
|-------------|---------------|
| Single model | Multiple models vote |
| One-shot review | Multi-round deliberation |
| Stateless | Remembers past reviews |
| Generic advice | Repo-aware insights |

## Features

- 🤖 **Multi-Model Consensus** — Claude, GPT-4, Gemini, Mistral, and more
- 🔄 **Deliberation** — Models read each other's opinions and reconsider
- 💾 **Memory** — Tracks reviews, opinions, and how they change
- 📊 **Observability** — Token usage, latency, and cost tracking
- 🎯 **Selective Review** — Focus on specific files

## Quick Start

### Installation

```bash
# Clone and install
git clone https://github.com/kraghavan/model-council-applications.git
cd model-council-applications
pip install -e .

# Initialize storage
council init
```

### Configuration

1. **Create `.env`** (API keys — keep secret):

```bash
# Required: At least one model
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=xxx

# Optional: More models
OPENAI_API_KEY=sk-xxx
MISTRAL_API_KEY=xxx
GROQ_API_KEY=xxx

# Required for PR review
GITHUB_TOKEN=ghp_xxx
```

2. **Create `council.yaml`** (optional, can commit to repo):

```yaml
models:
  default: [claude, gemini]

storage:
  enabled: true
  path: ~/.council/data/council.db

deliberation:
  enabled: true
  rounds: 2
```

### Usage

```bash
# Review a PR (single round)
council pr-review owner/repo#123

# Review with deliberation (models discuss)
council pr-review owner/repo#123 --rounds 2

# Review specific files only
council pr-review owner/repo#123 --files "auth.py,utils.py"

# Deep analysis (fetches code context)
council pr-review owner/repo#123 --deep

# Combine all options
council pr-review owner/repo#123 --deep --rounds 2 --files "auth.py"

# Review architecture
council architecture ./design.mermaid
council architecture ./docs --files "system.mermaid,api.mermaid"

# Check status
council models    # Show configured models
council history   # Show past reviews
council stats     # Show statistics
```

## Deep Analysis Mode

Use `--deep` for enhanced reviews with code context:

```bash
council pr-review owner/repo#123 --deep
```

### Flag Behavior

| Command | What Happens |
|---------|--------------|
| `council pr-review url` | Basic review — just the diff, no context fetching |
| `council pr-review url --deep` | Deep analysis — use cache if fresh, else fetch new |
| `council pr-review url --deep --fresh` | Deep analysis — always fetch new, ignore cache |
| `council pr-review url --rounds 2` | Multi-round deliberation, no deep analysis |
| `council pr-review url --deep --rounds 2` | Both — deep + multi-round |

**Key point:** Without `--deep`, no context fetching happens at all.

### What Deep Analysis Does

```
┌─────────────────────────────────────────────────────────────────┐
│  DEEP ANALYSIS FLOW                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Parse diff → Extract imports                                │
│  2. Identify dependencies (non-stdlib)                          │
│  3. Check cache: Have we analyzed this repo before?             │
│     └── YES: Reuse cached context (faster, no extra API calls)  │
│     └── NO:  Fetch related source files from GitHub             │
│  4. Store context in DB for future use                          │
│  5. Inject context into prompt                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Context Caching

Deep analysis context is **cached per repository** with a configurable TTL:

| PR # | What Happens |
|------|--------------|
| First PR | Fetches related files → Stores in DB |
| Second PR (within TTL) | Reuses cached context → Faster |
| PR after TTL expires | Fetches fresh → Updates cache |
| Any PR with `--fresh` | Always fetches fresh → Updates cache |

**Configure TTL:**

```bash
# .env (Docker-friendly)
COUNCIL_CONTEXT_CACHE_TTL=3600   # Seconds (default: 1 hour)
```

Or in `council.yaml`:

```yaml
cache:
  context_ttl_seconds: 3600  # 1 hour
```

### Enhanced Output

With `--deep`, models also suggest:
- Design patterns observed or recommended
- Performance optimizations
- Code consistency with existing patterns

## Issue Tracking

Model Council tracks issues across reviews using **fingerprinting** — issues are identified by function and type, not just line number.

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  PR #10: First Review                                          │
├─────────────────────────────────────────────────────────────────┤
│  Model finds: "SQL injection in login()"                        │
│  → Generate fingerprint: hash(file + function + type)          │
│  → Store as: status='open', occurrences=1                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PR #15: Second Review                                         │
├─────────────────────────────────────────────────────────────────┤
│  Inject previous issues into prompt:                           │
│  "Please verify if these issues are still present..."          │
│                                                                 │
│  Model finds: Same issue still there                           │
│  → Update: occurrences=2                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PR #20: Issue Fixed                                           │
├─────────────────────────────────────────────────────────────────┤
│  Model: Issue NOT found in this PR                             │
│  → Mark as: status='fixed'                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Example Output

```
Issues: 2 new, 1 recurring, 1 fixed
```

### Why Fingerprinting?

| Without Fingerprinting | With Fingerprinting |
|------------------------|---------------------|
| Issue at line 45 | Issue in `login()` function |
| Code changes → Line 55 | Code changes → Still tracked |
| System: "New issue" | System: "Recurring (3x)" |

## How Deliberation Works

```
┌─────────────────────────────────────────────────────────────────┐
│  ROUND 1: Independent Review                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│    PR Diff ──┬──▶ Claude ──▶ "APPROVE (85%)" ──┐               │
│              ├──▶ Gemini ──▶ "COMMENT (70%)"  ──┼──▶ Store     │
│              └──▶ GPT-4  ──▶ "APPROVE (90%)"  ──┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ROUND 2: Informed Re-review                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│    Each model reads others' opinions:                          │
│    "Claude approved, Gemini had concerns about X..."           │
│                                                                 │
│    PR + Opinions ──┬──▶ Claude ──▶ "APPROVE (85%)" ──┐         │
│                    ├──▶ Gemini ──▶ "APPROVE (80%)"  ──┼──▶ ✓   │
│                    └──▶ GPT-4  ──▶ "APPROVE (88%)"  ──┘         │
│                                                                 │
│    Gemini reconsidered after seeing Claude's reasoning!        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  VERDICT: Consolidated                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│    ✅ APPROVE — Score: 84% (full consensus)                    │
│                                                                 │
│    Opinion Changes:                                            │
│    • Gemini: COMMENT → APPROVE (+10%)                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Example Output

```
🤖 Council: claude, gemini, openai

📋 Add authentication middleware
   https://github.com/owner/repo/pull/123
   Author: developer | main ← feature/auth
   🔄 Deliberation: 2 rounds

╭──────────────────────────────────────────────────────────────────╮
│ ✅ APPROVE — Score: 84% (full consensus) | 2 round(s)           │
╰──────────────────────────────────────────────────────────────────╯

Individual Results:
  ✅ claude (85%): Clean implementation with proper error handling
  ✅ gemini (80%): Good security practices, minor suggestions
  ✅ openai (88%): Well-structured middleware

Opinion Changes:
┌─────────┬───────────┬─────────────────┬─────────────────────┐
│ Model   │ Round     │ Score Change    │ Verdict Change      │
├─────────┼───────────┼─────────────────┼─────────────────────┤
│ gemini  │ 1 → 2     │ 70% → 80% (+10%)│ COMMENT → APPROVE   │
└─────────┴───────────┴─────────────────┴─────────────────────┘

Session: a1b2c3d4 | Calls: 6 | Tokens: 12,450 | Time: 8.2s
```

## Configuration Reference

### `.env` (Secrets)

```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=xxx
OPENAI_API_KEY=sk-xxx
MISTRAL_API_KEY=xxx
DEEPSEEK_API_KEY=xxx
GROQ_API_KEY=xxx
GITHUB_TOKEN=ghp_xxx

# Overrides (optional)
COUNCIL_STORAGE_ENABLED=true
COUNCIL_STORAGE_PATH=~/.council/data/council.db
COUNCIL_DELIBERATION_ROUNDS=2
COUNCIL_MODELS=claude,gemini
```

### `council.yaml` (Settings)

```yaml
models:
  default: [claude, gemini]
  
  claude:
    version: claude-sonnet-4-20250514
  gemini:
    version: gemini-2.0-flash
  openai:
    version: gpt-4o
  ollama:
    version: llama3.2
    host: http://localhost:11434

storage:
  enabled: true
  path: ~/.council/data/council.db

deliberation:
  enabled: true
  rounds: 2
  max_rounds: 5
  early_stop_on_consensus: true

review:
  approval_threshold: 0.7
```

### Priority Order

```
CLI flags > Environment variables > council.yaml > Defaults
```

## Commands

| Command | Description |
|---------|-------------|
| `council init` | Initialize database |
| `council pr-review <url>` | Review a GitHub PR |
| `council architecture <source>` | Review architecture |
| `council models` | Show model status |
| `council tasks` | List available tasks |
| `council history` | Show past reviews |
| `council stats [session_id]` | Show statistics |

### Flags

| Flag | Description |
|------|-------------|
| `--models, -m` | Models to use (comma-separated) |
| `--files, -f` | Files to review (comma-separated) |
| `--rounds, -r` | Deliberation rounds |
| `--json` | Output as JSON |

## Storage

Model Council uses SQLite with [sqlite-vec](https://github.com/asg017/sqlite-vec) for persistent storage.

```bash
# Default location
~/.council/data/council.db

# Or per-project
./council.db
```

### What's Stored

- **Sources** — PRs, architecture docs reviewed
- **Sessions** — Review sessions with rounds
- **Opinions** — Each model's opinion per round
- **Changes** — How opinions evolved
- **Observations** — Token usage, latency, costs
- **Verdicts** — Final consolidated decisions

📖 **See [docs/SCHEMA.md](docs/SCHEMA.md) for full database schema documentation.**

## Supported Models

| Model | Provider | Requires |
|-------|----------|----------|
| Claude | Anthropic | `ANTHROPIC_API_KEY` |
| Gemini | Google | `GOOGLE_API_KEY` |
| GPT-4 | OpenAI | `OPENAI_API_KEY` |
| Mistral | Mistral | `MISTRAL_API_KEY` |
| DeepSeek | DeepSeek | `DEEPSEEK_API_KEY` |
| Groq | Groq | `GROQ_API_KEY` |
| Ollama | Local | Ollama running locally |

## Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | Quick start and overview |
| [SKILLS.md](SKILLS.md) | Capabilities and use cases |
| [CLAUDE.md](CLAUDE.md) | Project context for AI assistants |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [docs/SCHEMA.md](docs/SCHEMA.md) | Database schema reference |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture diagrams |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check council/ tests/
```

## License

MIT
