# Model Council 🏛️

A framework for running multiple AI models on the same task and aggregating their verdicts. Get consensus from Claude, GPT-4o, Gemini, Mistral, DeepSeek, Groq, and local Ollama models.

## Why Multiple Models?

- **Different blind spots** — models catch different issues
- **Confidence through consensus** — agreement = higher trust
- **Surface disagreements** — split verdicts need human attention
- **Cost flexibility** — mix cloud APIs with free/local models

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
- At least one model API key (see Supported Models below)

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

# Model API keys (at least one required)
ANTHROPIC_API_KEY=sk-ant-xxxxx   # Claude
OPENAI_API_KEY=sk-xxxxx          # GPT-4o
GOOGLE_API_KEY=AIzaSyxxxxx       # Gemini
MISTRAL_API_KEY=xxxxx            # Mistral
DEEPSEEK_API_KEY=sk-xxxxx        # DeepSeek (cheap!)
GROQ_API_KEY=gsk_xxxxx           # Groq (free tier!)

# Local models (no API key needed)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Which models to use
COUNCIL_MODELS=claude,openai,gemini

# Score threshold for approval (0.0-1.0)
APPROVAL_THRESHOLD=0.7
```

## Usage

### Check Models

```bash
council models
```

### PR Review

```bash
council pr-review https://github.com/owner/repo/pull/123
council pr-review owner/repo#123
council pr-review owner/repo#123 --models claude,openai,deepseek
council pr-review owner/repo#123 --json
```

### Architecture Review

```bash
# Review a design document
council architecture ./docs/design.md

# Review a mermaid diagram
council architecture ./docs/architecture.mermaid

# Analyze a repo structure
council architecture ./my-project/

# Review from URL
council architecture https://raw.githubusercontent.com/org/repo/main/ARCHITECTURE.md

# Review raw text diagram
council architecture "Client -> LoadBalancer -> [API1, API2] -> Database"
```

### List Tasks

```bash
council tasks
```

## Example Output

```
🤖 Council: claude, openai, deepseek

📋 Add user authentication
   https://github.com/owner/repo/pull/123
   Author: developer | main ← feature/auth

╭──────────────────────────────────────────────╮
│ ✅ APPROVE — Score: 87% (full consensus)     │
╰──────────────────────────────────────────────╯

Individual Results:
  ✅ claude (89%): Well-structured implementation with good error handling...
  ✅ openai (85%): Clean code, follows best practices...
  ✅ deepseek (86%): Solid implementation, consider adding rate limiting...

Key Issues:
┌──────────┬─────────────┬────────────────────────────────────────┬───────────┐
│ Severity │ Location    │ Issue                                  │ Flagged By│
├──────────┼─────────────┼────────────────────────────────────────┼───────────┤
│ minor    │ auth.py:42  │ Consider adding request timeout        │ claude    │
│ nit      │ tests/      │ Missing edge case for expired tokens   │ openai    │
└──────────┴─────────────┴────────────────────────────────────────┴───────────┘
```

## Architecture

```
┌──────────┐
│  Input   │  (PR URL, design doc, diagram, repo)
└────┬─────┘
     │
     ▼
┌──────────┐
│   Task   │  (pr-review, architecture, etc.)
└────┬─────┘
     │
  ┌──┴───┬───────┬────────┬──────────┬───────┐
  ▼      ▼       ▼        ▼          ▼       ▼
Claude OpenAI Gemini DeepSeek     Groq   Ollama
  │      │       │        │          │       │
  └──┬───┴───────┴────────┴──────────┴───────┘
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
├── .github/
│   └── workflows/
│       └── test.yml       # CI: runs tests on every PR
├── council/
│   ├── core/
│   │   ├── models.py      # All model clients
│   │   ├── runner.py      # Parallel execution
│   │   └── voting.py      # Consensus/aggregation
│   ├── tasks/
│   │   ├── base.py        # Abstract task interface
│   │   ├── pr_review.py   # PR review task
│   │   └── architecture.py # Architecture review task
│   ├── config.py          # Settings from .env
│   └── cli.py             # Command-line interface
├── tests/
│   ├── test_core.py
│   ├── test_models.py
│   ├── test_tasks.py
│   ├── test_architecture.py
│   └── test_integration.py
├── CLAUDE.md              # Claude Code context
├── CONTRIBUTING.md        # How to contribute
├── requirements.txt
└── pyproject.toml
```

## Supported Models

| Model | Provider | Type | Cost | Get API Key |
|-------|----------|------|------|-------------|
| Claude | Anthropic | Cloud | $$ | [console.anthropic.com](https://console.anthropic.com/) |
| GPT-4o | OpenAI | Cloud | $$ | [platform.openai.com](https://platform.openai.com/) |
| Gemini | Google | Cloud | $ | [aistudio.google.com](https://aistudio.google.com/) |
| Mistral | Mistral AI | Cloud | $ | [console.mistral.ai](https://console.mistral.ai/) |
| DeepSeek | DeepSeek | Cloud | ¢ | [platform.deepseek.com](https://platform.deepseek.com/) |
| Groq | Groq | Cloud | FREE | [console.groq.com](https://console.groq.com/) |
| Ollama | Local | Local | FREE | [ollama.ai](https://ollama.ai/) |

**Budget-friendly combo:** `COUNCIL_MODELS=deepseek,groq,ollama`

## Available Tasks

| Task | Command | Description | Status |
|------|---------|-------------|--------|
| PR Review | `council pr-review <url>` | Review GitHub pull requests | ✅ Ready |
| Architecture | `council architecture <source>` | Evaluate system design | ✅ Ready |
| Doc Review | `council doc-review <file>` | Review documentation | 🔜 Planned |
| Explain | `council explain <code>` | Explain code | 🔜 Planned |

## CI/CD

Every pull request automatically runs:
- **Linting** with ruff
- **Tests** on Python 3.10, 3.11, 3.12
- **Coverage** report

See `.github/workflows/test.yml`

## Roadmap

- [x] Multi-model PR review
- [x] Architecture review task
- [x] GitHub Actions CI
- [ ] GitHub Action for automated PR reviews
- [ ] Post review comments directly to PR
- [ ] More tasks: doc review, code explanation
- [ ] Web UI dashboard
- [ ] Custom voting strategies

## Fork & Extend

Want to build on this? See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to add new tasks
- How to add new models
- Development setup
- Pull request guidelines

## License

MIT — fork it, extend it, make it yours.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).
