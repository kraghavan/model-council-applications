# Model Council

A framework for running multiple AI models on the same task and aggregating their responses.

## Project Structure

```
model-council/
├── council/
│   ├── core/           # Generic model runners & voting
│   │   ├── models.py   # Claude, Gemini, Ollama clients
│   │   ├── runner.py   # Parallel execution
│   │   └── voting.py   # Consensus/aggregation
│   ├── tasks/          # Pluggable applications
│   │   ├── base.py     # Abstract task interface
│   │   └── pr_review.py # PR review implementation
│   └── cli.py          # Entry point
└── tests/
```

## Key Concepts

- **Task**: Defines what problem the council solves (input, prompt, schema, aggregation)
- **Runner**: Executes all models in parallel on a task
- **Voting**: Combines model responses into a single verdict

## Adding a New Task

1. Create `council/tasks/your_task.py`
2. Inherit from `BaseTask`
3. Implement: `fetch_input()`, `build_prompt()`, `parse_response()`, `aggregate()`
4. Register in `council/tasks/__init__.py`

## Commands

```bash
# Install
pip install -e .

# Run PR review
council pr-review https://github.com/owner/repo/pull/123

# List available tasks
council --help

# Check configured models
council models
```

## Environment Variables

Required in `.env`:
- `GITHUB_TOKEN` - for PR review task
- At least one of: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or Ollama running locally

## Code Style

- Python 3.10+
- Type hints everywhere
- Async for all model calls
- Pydantic for config/validation
