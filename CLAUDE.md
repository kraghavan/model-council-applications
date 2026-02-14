# Model Council

Multi-model AI consensus framework. Runs tasks across Claude, Gemini, and Ollama, then aggregates verdicts.

## Commands

```bash
council pr-review <url>      # Review a GitHub PR
council tasks                # List available tasks
council models               # Check configured models
council run <task> <input>   # Run any task
```

## Structure

```
council/
├── core/           # Generic infrastructure (don't modify often)
│   ├── models.py   # Model clients (Claude, Gemini, Ollama)
│   ├── runner.py   # Parallel execution
│   └── voting.py   # Consensus logic
├── tasks/          # Task implementations (extend here)
│   ├── base.py     # Abstract interface
│   └── pr_review.py
├── config.py       # Settings from .env
└── cli.py          # Entry point
```

## Key Files

- `council/tasks/base.py` — `BaseTask` class to inherit from
- `council/tasks/__init__.py` — Task registry (add new tasks here)
- `council/core/models.py` — Model clients (add new models here)
- `.env` — API keys and settings

## Adding a Task

1. Create `council/tasks/new_task.py` inheriting `BaseTask`
2. Implement: `fetch_input()`, `build_prompt()`, `parse_response()`
3. Register in `council/tasks/__init__.py`

## Adding a Model

1. Create new `ModelClient` subclass in `council/core/models.py`
2. Register in `get_model_client()` factory
3. Add config to `council/config.py` and `.env.example`

## Environment

```bash
GITHUB_TOKEN=...           # Required for pr-review
ANTHROPIC_API_KEY=...      # Claude
GOOGLE_API_KEY=...         # Gemini  
OLLAMA_HOST=...            # Local Ollama
COUNCIL_MODELS=claude,gemini,ollama
```

## Testing

```bash
pytest                           # Run all tests
pytest tests/test_core.py       # Core tests
pytest tests/test_tasks.py      # Task tests
```

## Code Style

- Python 3.10+, type hints everywhere
- Async for all model/network calls
- Pydantic for config validation
- `ruff` for formatting/linting
