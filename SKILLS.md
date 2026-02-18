# Model Council Skill

## Description

Run multiple AI models (Claude, GPT-4o, Gemini, Mistral, DeepSeek, Groq, Ollama) on the same task and aggregate their verdicts. Useful for code review, architecture review, and any task where consensus adds value.

## When to Use

- Reviewing pull requests with multi-model consensus
- Evaluating system architecture designs
- Getting diverse perspectives on technical decisions
- Validating outputs across different models

---

## Available Tasks

### pr-review

Review GitHub pull requests with multiple models.

```bash
council pr-review https://github.com/owner/repo/pull/123
council pr-review owner/repo#123 --models claude,openai,deepseek
council pr-review owner/repo#123 --json
council pr-review owner/repo#123 --deep  # Deep analysis mode
```

**What it analyzes:**
- Code correctness and potential bugs
- Security vulnerabilities
- Performance concerns
- Code clarity and maintainability
- Test coverage gaps

**Deep analysis (`--deep`) adds:**
- Import parsing and dependency tracking
- Related source file context
- Design pattern recommendations
- Context caching for faster subsequent reviews

### Issue Tracking

Model Council automatically tracks issues across reviews:

- **Fingerprinting** — Issues identified by function + type, not line number
- **Recurring detection** — "This issue was seen 3x before"
- **Fixed detection** — Automatically marks resolved issues
- **Prompt injection** — Models see previous unresolved issues

### architecture

Review system architecture from diagrams, docs, or repo structure.

```bash
council architecture ./docs/design.md
council architecture ./architecture.mermaid
council architecture ./my-project/
council architecture "Client -> API -> DB"
```

**Supported file types:**
- Mermaid (`.mermaid`, `.mmd`)
- PlantUML (`.puml`, `.plantuml`)
- Draw.io (`.drawio`, `.dio`)
- Markdown (`.md`)
- Config files (`.yaml`, `.json`)

---

## Key Features

### Multi-Round Deliberation

Models review, read each other's opinions, then re-review.

```bash
council pr-review owner/repo#123 --rounds 2
```

**How it works:**

```
Round 1: Independent review
         ├── Claude: APPROVE (85%)
         ├── Gemini: COMMENT (70%)
         └── GPT-4:  APPROVE (90%)

Round 2: Read others → Re-review
         ├── Claude: APPROVE (85%)  [no change]
         ├── Gemini: APPROVE (80%)  [changed: +10%]
         └── GPT-4:  APPROVE (88%)  [slight adjust]

Final: Full consensus, APPROVE (84%)
```

### Selective File Review

Focus review on specific files from a PR or directory.

```bash
# PR: review only these files
council pr-review owner/repo#123 --files "src/auth.py,src/utils.py"

# Architecture: review only these diagrams
council architecture ./docs --files "system.mermaid"
```

### Session History

View past reviews and statistics.

```bash
council history              # View recent sessions
council stats <session_id>   # View specific session stats
```

### Consensus Aggregation

Combines multiple model opinions into a single verdict.

| Consensus | Meaning |
|-----------|---------|
| `full` | All models agree |
| `partial` | Majority agrees |
| `split` | No clear majority |

---

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

---

## Configuration

```bash
COUNCIL_MODELS=claude,openai,deepseek
APPROVAL_THRESHOLD=0.7
```

Or via `council.yaml`:

```yaml
models:
  default: [claude, gemini]

storage:
  enabled: true

deliberation:
  enabled: true
  rounds: 2
```

---

## Common Use Cases

| Use Case | Command |
|----------|---------|
| Quick review | `council pr-review url` |
| Deep consensus | `council pr-review url --rounds 3` |
| Focused review | `council pr-review url --files "critical.py"` |
| Multi-model | `council pr-review url -m claude,gemini,openai` |
| Deep analysis | `council pr-review url --deep` |
| Fresh context | `council pr-review url --deep --fresh` |
| Full analysis | `council pr-review url --deep --rounds 2` |
| Architecture | `council architecture ./docs` |

---

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

Register in `council/tasks/__init__.py`:

```python
from council.tasks.my_task import MyTask
TASKS["my-task"] = MyTask
```
