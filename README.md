# Model Council 🏛️

A framework for running multiple AI models on the same task and aggregating their verdicts.

## Why?

- **Different blind spots** — models catch different issues
- **Confidence through consensus** — agreement = higher trust
- **Surface disagreements** — split verdicts need human attention
- **Cost flexibility** — mix local and cloud models

## Quick Start

```bash
git clone https://github.com/kraghavan/model-council-applications.git
cd model-council-applications
cp .env.example .env        # Add your API keys
pip install -e .
council pr-review https://github.com/owner/repo/pull/123
```

## Installation

```bash
# Clone
git clone https://github.com/kraghavan/model-council-applications.git
cd model-council-applications

# Virtual environment (recommended)
python -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

Edit `.env`:

```bash
# Required for PR review
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# At least one model (or Ollama running locally)
ANTHROPIC_API_KEY=sk-ant-xxxxx
GOOGLE_API_KEY=AI-xxxxx

# Ollama (optional)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Settings
COUNCIL_MODELS=claude,gemini,ollama
APPROVAL_THRESHOLD=0.7
```

## Usage

### PR Review

```bash
# Full URL
council pr-review https://github.com/owner/repo/pull/123

# Short format
council pr-review owner/repo#123

# Specific models
council pr-review owner/repo#123 --models claude,gemini

# JSON output
council pr-review owner/repo#123 --json
```

### Check Models

```bash
council models
```

## Available Tasks

| Task | Description | Status |
|------|-------------|--------|
| `pr-review` | Review GitHub pull requests | ✅ Ready |
| `doc-review` | Review documents | 🔜 Planned |
| `architecture` | Evaluate design decisions | 🔜 Planned |
| `explain` | Explain code with multiple perspectives | 🔜 Planned |

## How It Works

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
│  Voting  │  (consensus, scores, key issues)
└────┬─────┘
     │
     ▼
┌──────────┐
│ Verdict  │  (APPROVE / REQUEST_CHANGES / COMMENT)
└──────────┘
```

## Adding a New Task

Create `council/tasks/my_task.py`:

```python
from council.tasks.base import BaseTask, TaskResult

class MyTask(BaseTask):
    name = "my-task"
    description = "What this task does"
    
    async def fetch_input(self, source: str) -> dict:
        """Fetch/parse the input data."""
        ...
    
    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Return (system_prompt, user_prompt)."""
        ...
    
    def parse_response(self, model_name: str, response: str) -> TaskResult:
        """Parse model's response into structured result."""
        ...
    
    def aggregate(self, results: list[TaskResult]) -> dict:
        """Combine all model results into final verdict."""
        ...
```

Register in `council/tasks/__init__.py`:

```python
from council.tasks.my_task import MyTask
TASKS = {"my-task": MyTask, ...}
```

## Example Output

```
🤖 Council: claude, gemini, ollama/llama3.2

📋 Task: pr-review
   https://github.com/owner/repo/pull/123

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

## License

MIT
