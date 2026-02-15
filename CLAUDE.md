# Model Council

Multi-model AI consensus framework. Runs tasks across Claude, GPT-4o, Gemini, Mistral, DeepSeek, Groq, and Ollama, then aggregates verdicts.

## Commands

```bash
council pr-review <url>          # Review a GitHub PR
council architecture <source>    # Review system design
council tasks                    # List available tasks
council models                   # Check configured models
council run <task> <input>       # Run any task
```

## Project Structure

```
council/
├── core/              # Generic infrastructure
│   ├── models.py      # Model clients (Claude, GPT-4o, Gemini, etc.)
│   ├── runner.py      # Parallel execution
│   └── voting.py      # Consensus logic
├── tasks/             # Task implementations
│   ├── base.py        # Abstract interface
│   ├── pr_review.py   # PR review task
│   └── architecture.py # Architecture review task
├── config.py          # Settings from .env
└── cli.py             # Entry point
```

## Key Extension Points

| To Add | Edit |
|--------|------|
| New task | `council/tasks/` + register in `__init__.py` |
| New model | `council/core/models.py` + `config.py` |
| CLI command | `council/cli.py` |

## Supported Models

- `claude` — Anthropic Claude
- `openai` — OpenAI GPT-4o
- `gemini` — Google Gemini
- `mistral` — Mistral AI
- `deepseek` — DeepSeek (cheap)
- `groq` — Groq/Llama (free tier)
- `ollama` — Local models

## Environment Variables

```bash
# Required for PR review
GITHUB_TOKEN=

# Model API keys
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
MISTRAL_API_KEY=
DEEPSEEK_API_KEY=
GROQ_API_KEY=

# Local
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Settings
COUNCIL_MODELS=claude,openai,gemini
APPROVAL_THRESHOLD=0.7
```

## Adding a Task

1. Create `council/tasks/new_task.py` inheriting `BaseTask`
2. Implement: `fetch_input()`, `build_prompt()`, `parse_response()`
3. Register in `council/tasks/__init__.py`
4. Add tests in `tests/test_new_task.py`

## Adding a Model

1. Create `ModelClient` subclass in `council/core/models.py`
2. Add to `CLIENTS` dict
3. Add config in `council/config.py`
4. Update `.env.example`
5. Add dependency to `requirements.txt`

## Testing

```bash
pytest tests/ -v                    # All tests
pytest tests/test_models.py -v      # Model tests
pytest tests/ --cov=council         # With coverage
```

## CI/CD

GitHub Actions runs on every PR:
- Linting: `ruff check`
- Tests: `pytest` on Python 3.10, 3.11, 3.12
- Coverage report

## Code Style

- Python 3.10+
- Type hints everywhere
- Async for all model/network calls
- Pydantic for config validation
- `ruff` for formatting/linting
