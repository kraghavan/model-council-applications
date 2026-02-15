# Model Council Skill

## Description

Run multiple AI models (Claude, GPT-4o, Gemini, Mistral, DeepSeek, Groq, Ollama) on the same task and aggregate their verdicts. Useful for code review, architecture review, and any task where consensus adds value.

## When to Use

- Reviewing pull requests with multi-model consensus
- Evaluating system architecture designs
- Getting diverse perspectives on technical decisions
- Validating outputs across different models

## Available Tasks

### pr-review

Review GitHub pull requests with multiple models.

```bash
council pr-review https://github.com/owner/repo/pull/123
council pr-review owner/repo#123 --models claude,openai,deepseek
council pr-review owner/repo#123 --json
```

### architecture

Review system architecture from diagrams, docs, or repo structure.

```bash
council architecture ./docs/design.md
council architecture ./architecture.mermaid
council architecture ./my-project/
council architecture "Client -> API -> DB"
```

## Supported Models

| Model | Config Key | Notes |
|-------|------------|-------|
| `claude` | `ANTHROPIC_API_KEY` | Anthropic |
| `openai` | `OPENAI_API_KEY` | GPT-4o |
| `gemini` | `GOOGLE_API_KEY` | Google |
| `mistral` | `MISTRAL_API_KEY` | Mistral AI |
| `deepseek` | `DEEPSEEK_API_KEY` | Cheap |
| `groq` | `GROQ_API_KEY` | Free tier |
| `ollama` | No key needed | Local |

## Configuration

```bash
COUNCIL_MODELS=claude,openai,deepseek
APPROVAL_THRESHOLD=0.7
```

## Extending

Create new tasks by implementing `BaseTask`:

```python
from council.tasks.base import BaseTask, TaskResult

class MyTask(BaseTask):
    name = "my-task"
    description = "What this task does"
    
    async def fetch_input(self, source: str) -> dict:
        ...
    
    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        ...
    
    def parse_response(self, model_name: str, response: str) -> TaskResult:
        ...
```
