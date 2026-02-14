# Contributing to Model Council

Thanks for your interest! This guide covers forking, extending, and contributing back.

## Quick Links

- [Fork & Setup](#fork--setup)
- [Adding a New Task](#adding-a-new-task)
- [Adding a New Model](#adding-a-new-model)
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
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run Tests

```bash
pytest
```

### 4. Keep Your Fork Updated

```bash
git remote add upstream https://github.com/kraghavan/model-council-applications.git
git fetch upstream
git merge upstream/main
```

---

## Adding a New Task

Tasks are pluggable applications that define what the council reviews.

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
        # Example: fetch from URL, read file, or just use source directly
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
    "your-task": YourTask,  # Add this line
}
```

### Step 3: Test It

```bash
council your-task "some input"
council your-task path/to/file.txt
council your-task https://example.com/something
```

### Task Ideas

| Task | Input | Use Case |
|------|-------|----------|
| `doc-review` | Markdown/text file | Review documentation for clarity |
| `architecture` | Design doc URL | Evaluate system design decisions |
| `explain` | Code file | Get multiple explanations of complex code |
| `debate` | Proposal text | Generate counterarguments |
| `security` | Code diff | Security-focused review |

---

## Adding a New Model

### Step 1: Create Client

Edit `council/core/models.py`, add a new class:

```python
class NewModelClient(ModelClient):
    """Your new model client."""

    name = "newmodel"

    def __init__(self):
        settings = get_settings()
        # Initialize your client
        self.api_key = settings.newmodel_api_key
        
    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            # Call your model's API
            response = await your_api_call(
                system=system_prompt,
                prompt=user_prompt,
            )
            return ModelResponse(
                model_name=self.name,
                content=response.text,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))
```

### Step 2: Register the Client

In the same file, update `get_model_client()`:

```python
def get_model_client(name: str) -> ModelClient:
    clients = {
        "claude": ClaudeClient,
        "gemini": GeminiClient,
        "ollama": OllamaClient,
        "newmodel": NewModelClient,  # Add this
    }
    ...
```

### Step 3: Add Config

Edit `council/config.py`:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    newmodel_api_key: str | None = None
```

Update `.env.example`:

```bash
# New Model
NEWMODEL_API_KEY=xxx
```

---

## Pull Request Guidelines

### Before Submitting

1. **Open an issue first** for major changes
2. **Run tests**: `pytest`
3. **Format code**: `ruff format .`
4. **Check linting**: `ruff check .`

### PR Checklist

- [ ] Tests pass
- [ ] New code has tests (if applicable)
- [ ] Updated README/docs (if applicable)
- [ ] Descriptive commit messages

### Commit Style

```
feat: add document review task
fix: handle empty PR descriptions
docs: update contributing guide
refactor: simplify voting logic
```

---

## Project Philosophy

1. **Simple > Complex** — Easy to understand and extend
2. **Pluggable** — Tasks and models are independent
3. **Minimal dependencies** — Only what's needed
4. **Good defaults** — Works out of the box

---

## Questions?

Open an issue or discussion on GitHub!
