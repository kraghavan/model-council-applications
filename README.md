# Model Council 🏛️

A framework for running multiple AI models on the same task and aggregating their verdicts. Get consensus from Claude, Gemini, and local Ollama models.

## Why Multiple Models?

- **Different blind spots** — models catch different issues
- **Confidence through consensus** — agreement = higher trust
- **Surface disagreements** — split verdicts need human attention
- **Cost flexibility** — mix cloud APIs with local models

## Quick Start

```bash
git clone https://github.com/kraghavan/model-council-applications.git
cd model-council-applications
cp .env.example .env        # Add your API keys
pip install -e .
council pr-review https://github.com/owner/repo/pull/123
```

## Installation

### Prerequisites

- Python 3.10+
- [GitHub Personal Access Token](https://github.com/settings/tokens) (for PR review)
- At least one of:
  - [Anthropic API key](https://console.anthropic.com/)
  - [Google AI API key](https://makersuite.google.com/app/apikey)
  - [Ollama](https://ollama.ai/) running locally

### Setup

```bash
# Clone
git clone https://github.com/kraghavan/model-council-applications.git
cd model-council-applications

# Virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your API keys
```

### Optional: Ollama Setup (Local Models)

```bash
# Install - https://ollama.ai
brew install ollama        # Mac
# or download from ollama.ai

# Start server & pull model
ollama serve
ollama pull llama3.2       # In another terminal
```

## Configuration

Edit `.env`:

```bash
# Required for PR review
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# At least one model API key
ANTHROPIC_API_KEY=sk-ant-xxxxx   # https://console.anthropic.com/
GOOGLE_API_KEY=AI-xxxxx          # https://makersuite.google.com/

# Optional: Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Settings
COUNCIL_MODELS=claude,gemini,ollama  # Which models to use
APPROVAL_THRESHOLD=0.7               # Score threshold (0.0-1.0)
```

## Usage

```bash
# Check configured models
council models

# Review a PR (various URL formats work)
council pr-review https://github.com/owner/repo/pull/123
council pr-review owner/repo#123

# Specify models
council pr-review owner/repo#123 --models claude,gemini

# JSON output (for scripts/CI)
council pr-review owner/repo#123 --json

# List available tasks
council tasks
```

## Example Output

```
🤖 Council: claude, gemini, ollama/llama3.2

📋 Add user authentication
   https://github.com/owner/repo/pull/123
   Author: developer | main ← feature/auth

╭──────────────────────────────────────────────╮
│ ✅ APPROVE — Score: 85% (full consensus)     │
╰──────────────────────────────────────────────╯

Individual Results:
  ✅ claude (87%): Well-structured implementation...
  ✅ gemini (84%): Good practices, minor suggestions...
  ✅ ollama/llama3.2 (83%): Clean code, tests pass...

Key Issues:
┌──────────┬─────────────┬────────────────────────┐
│ Severity │ Location    │ Issue                  │
├──────────┼─────────────┼────────────────────────┤
│ minor    │ auth.py:42  │ Consider adding timeout│
│ nit      │ tests/      │ Missing edge case      │
└──────────┴─────────────┴────────────────────────┘
```

## Architecture

```
┌──────────┐
│  Input   │  (PR URL, document, code, etc.)
└────┬─────┘
     │
     ▼
┌──────────┐
│   Task   │  (defines prompt, schema, aggregation)
└────┬─────┘
     │
  ┌──┴──┬──────┐
  ▼     ▼      ▼
Claude Gemini Ollama   ← parallel execution
  │     │      │
  └──┬──┴──────┘
     │
┌────▼─────┐
│  Voting  │  (consensus, scores, issues)
└────┬─────┘
     │
     ▼
┌──────────┐
│ Verdict  │  (APPROVE / REQUEST_CHANGES / COMMENT)
└──────────┘
```

## Project Structure

```
model-council-applications/
├── council/
│   ├── core/              # Generic, reusable
│   │   ├── models.py      # Claude, Gemini, Ollama clients
│   │   ├── runner.py      # Parallel execution
│   │   └── voting.py      # Consensus/aggregation logic
│   ├── tasks/             # Pluggable applications
│   │   ├── base.py        # Abstract task interface
│   │   └── pr_review.py   # PR review implementation
│   ├── config.py          # Settings from .env
│   └── cli.py             # Command-line interface
├── tests/
├── CLAUDE.md              # Claude Code context
├── CONTRIBUTING.md        # How to contribute
└── pyproject.toml
```

## Fork & Extend

Want to build on this? See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to add new tasks
- How to add new models  
- Development setup
- Pull request guidelines

## Available Tasks

| Task | Description | Status |
|------|-------------|--------|
| `pr-review` | Review GitHub pull requests | ✅ Ready |
| `doc-review` | Review documents for clarity | 🔜 Planned |
| `architecture` | Evaluate design decisions | 🔜 Planned |
| `explain` | Explain code with multiple perspectives | 🔜 Planned |

## Roadmap

- [ ] GitHub Action for automated PR reviews
- [ ] Post review comments directly to PR
- [ ] More tasks: doc review, architecture review
- [ ] Track model accuracy over time
- [ ] Custom voting strategies

## License

MIT — fork it, extend it, make it yours.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).
