# PR Council 🏛️

A multi-model AI council for reviewing pull requests. Get perspectives from Claude, Gemini, and local Ollama models — then aggregate their verdicts.

## Why Multiple Models?

- **Different blind spots** — models catch different issues
- **Confidence through consensus** — if all agree, you can trust it more
- **Interesting disagreements** — split verdicts surface areas needing human attention
- **Cost flexibility** — use local models for simple PRs, cloud for complex ones

## Quick Start

```bash
git clone https://github.com/kraghavan/model-council-applications.git
cd model-council-applications
cp .env.example .env        # Add your API keys
pip install -e .
council review https://github.com/owner/repo/pull/123
```

## Installation

### Prerequisites

- Python 3.10+
- GitHub Personal Access Token ([create one](https://github.com/settings/tokens))
- At least one of:
  - [Anthropic API key](https://console.anthropic.com/)
  - [Google AI API key](https://makersuite.google.com/app/apikey)
  - [Ollama](https://ollama.ai/) running locally

### Setup

```bash
# Clone the repo
git clone https://github.com/kraghavan/model-council-applications.git
cd model-council-applications

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

Edit `.env` with your settings:

```bash
# Required
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# At least one model API key
ANTHROPIC_API_KEY=sk-ant-xxxxx
GOOGLE_API_KEY=AI-xxxxx

# Optional: Ollama (if running locally)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Which models to use
COUNCIL_MODELS=claude,gemini,ollama

# Score threshold for approval (0.0-1.0)
APPROVAL_THRESHOLD=0.7
```

## Usage

### Review a PR

```bash
# Basic usage
council review https://github.com/owner/repo/pull/123

# Short format works too
council review owner/repo#123

# Specify models
council review https://github.com/owner/repo/pull/123 --models claude,gemini

# JSON output (for CI/scripts)
council review https://github.com/owner/repo/pull/123 --json
```

### Check available models

```bash
council models
```

## How It Works

```
┌─────────────┐
│  PR URL     │
└──────┬──────┘
       │
       ▼
┌──────────────┐
│ Fetch Diff   │◄── GitHub API
└──────┬───────┘
       │
  ┌────┴────┬────────┐
  ▼         ▼        ▼
Claude   Gemini   Ollama
  │         │        │
  └────┬────┴────────┘
       │
 ┌─────▼─────┐
 │ Aggregate │──► Weighted scores
 └─────┬─────┘    Consensus level
       │          Key issues
       ▼
 ┌───────────┐
 │  Verdict  │──► APPROVE / REQUEST_CHANGES / COMMENT
 └───────────┘
```

### Scoring

Each model scores the PR from 0.0 to 1.0:

| Score | Meaning |
|-------|---------|
| 0.9 - 1.0 | Excellent, ready to merge |
| 0.7 - 0.9 | Good, minor issues only |
| 0.5 - 0.7 | Needs work |
| 0.3 - 0.5 | Major concerns |
| 0.0 - 0.3 | Critical issues |

### Consensus Levels

- **Full** — All models agree on the verdict
- **Partial** — Majority agrees
- **Split** — No clear majority

## Example Output

```
🤖 Council members: claude, gemini, ollama

📋 Reviewing: Add user authentication
   https://github.com/owner/repo/pull/123
   Author: developer | main ← feature/auth

╭─────────────────────────────────────────╮
│ ✅ APPROVE — Score: 85% (full consensus)│
╰─────────────────────────────────────────╯

Individual Reviews:
  ✅ claude (87%): Well-structured auth implementation...
  ✅ gemini (84%): Good security practices, consider...
  ✅ ollama/llama3.2 (83%): Clean code, tests look good...

Key Issues:
┌──────────┬─────────────────┬─────────────────────────┬───────────┐
│ Severity │ File            │ Issue                   │ Flagged By│
├──────────┼─────────────────┼─────────────────────────┼───────────┤
│ minor    │ auth/session.py │ Consider adding timeout │ claude    │
│ nit      │ tests/test_auth │ Missing edge case test  │ gemini    │
└──────────┴─────────────────┴─────────────────────────┴───────────┘
```

## Roadmap

- [ ] GitHub Action for automated reviews
- [ ] Post review comments directly to PR
- [ ] Webhook server for real-time reviews
- [ ] Track model accuracy over time
- [ ] Custom review criteria per repo

## Contributing

Contributions welcome! Please open an issue first to discuss.

## License

MIT
