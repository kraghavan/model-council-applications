# Model Council Skill

## Description

Run multiple AI models (Claude, Gemini, Ollama) on the same task and aggregate their verdicts. Useful for code review, document analysis, architecture decisions, and any task where multiple perspectives add value.

## When to Use

- Reviewing pull requests with multi-model consensus
- Getting diverse perspectives on technical decisions  
- Validating outputs across different models
- Building ensemble AI workflows

## Available Tasks

### pr-review
Review GitHub pull requests with multiple models.

```bash
council pr-review https://github.com/owner/repo/pull/123
council pr-review owner/repo#123
council pr-review owner/repo#123 --models claude,gemini
council pr-review owner/repo#123 --json
```

## Extending

Create new tasks by implementing `BaseTask`:

```python
from council.tasks.base import BaseTask, TaskResult

class MyTask(BaseTask):
    name = "my-task"
    description = "What this task does"
    
    async def fetch_input(self, source: str) -> dict:
        # Get input data
        ...
    
    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        # Return (system_prompt, user_prompt)
        ...
    
    def parse_response(self, model_name: str, response: str) -> TaskResult:
        # Parse model output
        ...
    
    def aggregate(self, results: list[TaskResult]) -> dict:
        # Combine verdicts
        ...
```

## Configuration

Set in `.env`:

```bash
GITHUB_TOKEN=ghp_xxx           # Required for pr-review
ANTHROPIC_API_KEY=sk-ant-xxx   # Optional
GOOGLE_API_KEY=AI-xxx          # Optional  
OLLAMA_HOST=http://localhost:11434
COUNCIL_MODELS=claude,gemini   # Which models to use
APPROVAL_THRESHOLD=0.7         # Score threshold
```
