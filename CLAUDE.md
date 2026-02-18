# CLAUDE.md

> Context file for Claude Code and AI assistants working on this project.

## Project Overview

**Model Council** is a multi-model AI consensus framework that brings multiple LLMs together to review code and architecture through deliberation.

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Council** | Multiple AI models reviewing the same content |
| **Deliberation** | Multi-round review where models read each other's opinions |
| **Consensus** | Aggregated verdict from all models |
| **Task** | A specific review type (pr-review, architecture) |

## Architecture

```
council/
├── cli.py              # Click CLI commands
├── config.py           # Settings (ENV + council.yaml)
├── core/
│   ├── models.py       # Model clients (Claude, Gemini, etc.)
│   ├── runner.py       # Parallel model execution
│   ├── voting.py       # Consensus aggregation
│   └── deliberation.py # Multi-round orchestration
├── db/
│   ├── schema.py       # SQLite table definitions
│   └── storage.py      # CRUD operations
└── tasks/
    ├── base.py         # Abstract BaseTask
    ├── pr_review.py    # GitHub PR review
    └── architecture.py # Architecture review
```

## Database Schema

See [docs/SCHEMA.md](docs/SCHEMA.md) for full documentation.

**Core tables:**
- `sources` — Content being reviewed
- `sessions` — Review sessions
- `rounds` — Deliberation rounds
- `round_opinions` — Model opinions per round
- `verdicts` — Final decisions
- `observations` — Token/latency tracking
- `opinion_changes` — How opinions evolved

## Key Files to Understand

| File | Purpose |
|------|---------|
| `council/core/deliberation.py` | Multi-round logic, opinion injection |
| `council/db/storage.py` | All database operations |
| `council/tasks/base.py` | Task interface (fetch_input, build_prompt, parse_response) |
| `council/cli.py` | All CLI commands |

## Adding a New Task

1. Create `council/tasks/my_task.py`:
```python
from council.tasks.base import BaseTask, TaskResult

class MyTask(BaseTask):
    name = "my-task"
    description = "Does something useful"
    
    async def fetch_input(self, source: str, **kwargs) -> dict:
        # Fetch and prepare input
        return {"content": "..."}
    
    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        # Return (system_prompt, user_prompt)
        return "You are...", f"Review: {input_data['content']}"
    
    def parse_response(self, model_name: str, response: str) -> TaskResult:
        # Parse JSON response into TaskResult
        data = self.parse_json_response(model_name, response)
        return TaskResult(...)
```

2. Register in `council/tasks/__init__.py`:
```python
from council.tasks.my_task import MyTask
TASKS["my-task"] = MyTask
```

## Adding a New Model

1. Add client in `council/core/models.py`:
```python
class NewModelClient(ModelClient):
    name = "newmodel"
    
    def __init__(self):
        settings = get_settings()
        self.client = ...
        self.model = settings.get_model_version("newmodel")
    
    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        # Call API and return ModelResponse
        ...

CLIENTS["newmodel"] = NewModelClient
```

2. Add config in `council/config.py`:
```python
# In Settings class
newmodel_api_key: Optional[str] = None

# In DEFAULT_CONFIG
"newmodel": {"version": "model-name"}
```

## Common Commands

```bash
# Development
pip install -e ".[dev]"
pytest tests/ -v
ruff check council/

# Usage
council init                          # Initialize DB
council pr-review owner/repo#123      # Review PR
council pr-review url --rounds 2      # Multi-round
council architecture ./docs           # Review architecture
council history                        # Past reviews
council stats <session_id>            # Session details
```

## Configuration Priority

```
CLI flags > ENV vars > council.yaml > defaults
```

## Roadmap

| Version | Features | Status |
|---------|----------|--------|
| v1.0.0 | Core multi-model review | ✅ |
| v1.2.0 | Selective file review | ✅ |
| v2.0.0 | Memory DB + deliberation | ✅ |
...

## Testing

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_storage.py -v

# With coverage
pytest tests/ --cov=council
```

## Code Style

- Python 3.10+
- Type hints required
- Async/await for I/O
- Ruff for linting # disabled TBFL
- Dataclasses for models
