# Contributing to Model Council

Thanks for your interest! This guide covers forking, extending, and contributing back.

## Quick Links

- [Fork & Setup](#fork--setup)
- [Development Workflow](#development-workflow)
- [Adding a New Task](#adding-a-new-task)
- [Adding a New Model](#adding-a-new-model)
- [Running Tests](#running-tests)
- [Pull Request Guidelines](#pull-request-guidelines)

---

## Fork & Setup

### 1. Fork the Repository

Click "Fork" on GitHub, then:

```bash
git clone https://github.com/YOUR_USERNAME/model-council-applications.git
cd model-council-applications
```

### 2. Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
# Edit .env with your API keys
```

### 3. Verify Setup

```bash
# Check installation
council --help
council models

# Run tests
pytest tests/ -v
```

### 4. Keep Your Fork Updated

```bash
git remote add upstream https://github.com/kraghavan/model-council-applications.git
git fetch upstream
git merge upstream/main
```

---

## Development Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes...

# Run linting
ruff check council/ tests/
ruff format council/ tests/

# Run tests
pytest tests/ -v

# Commit
git add .
git commit -m "feat: add my feature"

# Push and create PR
git push origin feature/my-feature
```

---

## Adding a New Task

Tasks define what the council reviews. Each task specifies how to fetch input, build prompts, and parse responses.

### Step 1: Create Task File

Create `council/tasks/your_task.py`:

```python
"""Your task description."""

from council.tasks.base import BaseTask, TaskResult


class YourTask(BaseTask):
    """One-line description."""

    name = "your-task"  # CLI command name
    description = "What this task does"

    async def fetch_input(self, source: str) -> dict:
        """Fetch and prepare input data.
        
        Args:
            source: User-provided input (URL, file path, text, etc.)
            
        Returns:
            Dictionary with data needed for the prompt
        """
        # Example: read file, fetch URL, or use source directly
        return {
            "content": source,
            "metadata": {},
        }

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Build prompts for the models.
        
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = """You are an expert at [your domain].
Analyze the following and provide your assessment.
Respond with ONLY valid JSON."""

        user_prompt = f"""Analyze this:

{input_data['content']}

Respond with JSON:
{{
    "score": <float 0.0-1.0>,
    "verdict": "<APPROVE|REJECT|COMMENT>",
    "summary": "<your assessment>",
    "issues": [
        {{"severity": "<critical|major|minor>", "description": "<issue>"}}
    ]
}}"""

        return system_prompt, user_prompt

    def parse_response(self, model_name: str, response: str) -> TaskResult:
        """Parse model's response into TaskResult."""
        data = self.parse_json_response(model_name, response)
        
        if data is None:
            return TaskResult.from_error(model_name, "Could not parse JSON")
        
        return TaskResult(
            model_name=model_name,
            score=float(data.get("score", 0.5)),
            decision=data.get("verdict", "COMMENT"),
            summary=data.get("summary", ""),
            issues=data.get("issues", []),
        )
```

### Step 2: Register the Task

Edit `council/tasks/__init__.py`:

```python
from council.tasks.your_task import YourTask

TASKS: dict[str, type[BaseTask]] = {
    "pr-review": PRReviewTask,
    "architecture": ArchitectureTask,
    "your-task": YourTask,  # Add this
}
```

### Step 3: Add CLI Command (optional)

Edit `council/cli.py`:

```python
@main.command("your-task")
@click.argument("source")
@click.option("--models", "-m", help="Comma-separated list of models")
@click.option("--json", "output_json", is_flag=True, help="Output JSON")
def your_task(source: str, models: str | None, output_json: bool):
    """Your task description.
    
    SOURCE: Input for the task
    """
    _run_task("your-task", source, models, output_json)
```

### Step 4: Add Tests

Create `tests/test_your_task.py`:

```python
import pytest
from council.tasks.your_task import YourTask

class TestYourTask:
    
    def test_build_prompt(self):
        task = YourTask()
        input_data = {"content": "test input", "metadata": {}}
        system, user = task.build_prompt(input_data)
        assert "test input" in user

    def test_parse_response(self):
        task = YourTask()
        response = '{"score": 0.8, "verdict": "APPROVE", "summary": "Good", "issues": []}'
        result = task.parse_response("test", response)
        assert result.score == 0.8
```

### Task Ideas

| Task | Input | Use Case |
|------|-------|----------|
| `doc-review` | Markdown file | Review docs for clarity |
| `security` | Code diff | Security-focused review |
| `explain` | Code file | Multi-perspective explanation |
| `debate` | Proposal | Generate counterarguments |
| `translate` | Text | Consensus translation |

---

## Adding a New Model

### Step 1: Add Client Class

Edit `council/core/models.py`:

```python
class NewModelClient(ModelClient):
    """Your new model client."""

    name = "newmodel"

    def __init__(self):
        from some_sdk import Client  # Import inside __init__
        settings = get_settings()
        self.client = Client(api_key=settings.newmodel_api_key)
        self.model = settings.newmodel_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return ModelResponse(
                model_name=self.name,
                content=response.text,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))
```

### Step 2: Register Client

In `council/core/models.py`, add to `CLIENTS`:

```python
CLIENTS = {
    # ... existing clients ...
    "newmodel": NewModelClient,
}
```

### Step 3: Add Config

Edit `council/config.py`:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    newmodel_api_key: str | None = None
    newmodel_model: str = "default-model-name"
```

Update `get_available_models()`:

```python
model_keys = {
    # ... existing ...
    "newmodel": self.newmodel_api_key,
}
```

### Step 4: Update Files

Add to `.env.example`:
```bash
NEWMODEL_API_KEY=
NEWMODEL_MODEL=default-model-name
```

Add to `requirements.txt`:
```
newmodel-sdk>=1.0
```

### Step 5: Add Tests

```python
class TestNewModelClient:
    
    @pytest.mark.asyncio
    async def test_generate(self):
        # Mock the SDK and test
        ...
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Specific file
pytest tests/test_models.py -v

# With coverage
pytest tests/ --cov=council --cov-report=term-missing

# Only fast tests (no network)
pytest tests/ -v -m "not slow"
```

### Test Structure

```
tests/
├── test_core.py          # Voting, aggregation
├── test_models.py        # Model clients
├── test_tasks.py         # Task parsing (PR review)
├── test_architecture.py  # Architecture task
└── test_integration.py   # End-to-end tests
```

---

## Pull Request Guidelines

### Before Submitting

1. **Open an issue first** for major changes
2. **Run linting**: `ruff check council/ tests/`
3. **Run tests**: `pytest tests/ -v`
4. **Update docs** if needed

### PR Checklist

- [ ] Tests pass locally
- [ ] New code has tests
- [ ] Linting passes
- [ ] Docs updated (if applicable)
- [ ] Descriptive commit messages

### Commit Style

```
feat: add document review task
fix: handle empty PR descriptions
docs: update contributing guide
refactor: simplify voting logic
test: add integration tests
chore: update dependencies
```

### What Happens on PR

GitHub Actions will automatically:
1. Run `ruff check` (linting)
2. Run `pytest` on Python 3.10, 3.11, 3.12
3. Report coverage

---

## Project Philosophy

1. **Simple > Complex** — easy to understand and extend
2. **Pluggable** — tasks and models are independent
3. **Minimal dependencies** — only what's needed
4. **Good defaults** — works out of the box
5. **Test everything** — CI must pass

---

## Getting Help

- **Questions?** Open a GitHub issue
- **Bug?** Open an issue with reproduction steps
- **Feature idea?** Open an issue to discuss first

Thanks for contributing! 🎉
