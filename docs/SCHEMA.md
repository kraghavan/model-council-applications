# Model Council Database Schema

This document describes the SQLite database schema used by Model Council for storing review sessions, deliberations, and observations.

## Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              council.db                                    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌───────────┐       ┌───────────┐       ┌─────────────────┐               │
│  │  sources  │──────▶│  sessions │──────▶│     rounds      │               │
│  │           │       │           │       │                 │               │
│  │ PR/arch   │       │ models    │       │ round_number    │               │
│  │ content   │       │ status    │       │ status          │               │
│  └─────┬─────┘       └─────┬─────┘       └────────┬────────┘               │
│        │                   │                      │                        │
│        │                   │                      ▼                        │
│        │                   │             ┌─────────────────┐               │
│        │                   │             │ round_opinions  │               │
│        │                   │             │                 │               │
│        │                   │             │ model, score    │               │
│        │                   │             │ verdict, issues │               │
│        │                   │             └─────────────────┘               │
│        │                   │                                               │
│        │                   ▼                                               │
│        │           ┌───────────────┐     ┌─────────────────┐               │
│        │           │   verdicts    │     │ opinion_changes │               │
│        │           │               │     │                 │               │
│        └──────────▶│ final_score   │     │ score_before    │               │
│        │           │ final_verdict │     │ score_after     │               │
│        │           └───────────────┘     └─────────────────┘               │
│        │                                                                   │
│        │           ┌───────────────┐     ┌─────────────────┐               │
│        │           │ observations  │     │ code_contexts   │               │
│        │           │               │     │ (deep analysis) │               │
│        │           │ tokens, cost  │     │ cached context  │               │
│        │           │ latency       │     │ imports, files  │               │
│        │           └───────────────┘     └─────────────────┘               │
│        │                                          ▲                        │
│        └──────────────────────────────────────────┘                        │
│                                                                            │
│        ┌───────────────────┐     ┌─────────────────┐                       │
│        │ source_embeddings │     │ long_term_memory│                       │
│        │ (vector search)   │     │ patterns, issues│                       │
│        └───────────────────┘     └─────────────────┘                       │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Tables

### `sources`

Stores the content being reviewed (PRs, architecture docs, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `task_type` | TEXT | Task type: `pr-review`, `architecture`, etc. |
| `source_ref` | TEXT | URL, file path, or identifier |
| `scope` | TEXT | Scope like `owner/repo` or project name |
| `title` | TEXT | Human-readable title |
| `content_hash` | TEXT | SHA256 hash for deduplication (16 chars) |
| `raw_content` | TEXT | Original full content (diff, doc, etc.) |
| `metadata` | TEXT | JSON with task-specific data |
| `created_at` | TIMESTAMP | When created |

**Example:**
```sql
INSERT INTO sources (id, task_type, source_ref, scope, title, content_hash)
VALUES ('a1b2c3d4', 'pr-review', 'https://github.com/owner/repo/pull/123', 
        'owner/repo', 'Add authentication', 'abc123def456');
```

---

### `sessions`

A complete review session (may span multiple deliberation rounds).

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `source_id` | TEXT | FK → `sources.id` |
| `models` | TEXT | JSON array of model names |
| `max_rounds` | INTEGER | Maximum deliberation rounds (default: 2) |
| `status` | TEXT | `in_progress`, `completed`, `failed` |
| `started_at` | TIMESTAMP | When session started |
| `completed_at` | TIMESTAMP | When session ended |

**Example:**
```sql
INSERT INTO sessions (id, source_id, models, max_rounds, status)
VALUES ('x1y2z3w4', 'a1b2c3d4', '["claude", "gemini"]', 2, 'in_progress');
```

---

### `rounds`

Individual deliberation rounds within a session.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `session_id` | TEXT | FK → `sessions.id` |
| `round_number` | INTEGER | Round number (1, 2, 3...) |
| `status` | TEXT | `pending`, `running`, `completed` |
| `started_at` | TIMESTAMP | When round started |
| `completed_at` | TIMESTAMP | When round ended |

**Constraints:**
- `UNIQUE (session_id, round_number)`

---

### `round_opinions`

Each model's opinion for a specific round.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `round_id` | TEXT | FK → `rounds.id` |
| `session_id` | TEXT | FK → `sessions.id` |
| `round_number` | INTEGER | Round number |
| `model` | TEXT | Model name (claude, gemini, etc.) |
| `score` | REAL | Score 0.0 - 1.0 |
| `verdict` | TEXT | `APPROVE`, `REQUEST_CHANGES`, `COMMENT` |
| `summary` | TEXT | Model's summary |
| `issues` | TEXT | JSON array of issues |
| `extras` | TEXT | JSON with task-specific extras |
| `raw_response` | TEXT | Full model response |
| `created_at` | TIMESTAMP | When created |

**Constraints:**
- `UNIQUE (round_id, model)`

**Example `issues` JSON:**
```json
[
  {
    "severity": "major",
    "file": "auth.py",
    "line": 42,
    "description": "Missing input validation"
  }
]
```

---

### `verdicts`

Final consolidated verdict for a session.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `session_id` | TEXT | FK → `sessions.id` |
| `source_id` | TEXT | FK → `sources.id` |
| `consolidator_model` | TEXT | Model that did consolidation |
| `final_score` | REAL | Final aggregated score |
| `final_verdict` | TEXT | `APPROVE`, `REQUEST_CHANGES`, `COMMENT` |
| `consensus_level` | TEXT | `full`, `partial`, `split`, `none` |
| `summary` | TEXT | Consolidated summary |
| `issues` | TEXT | JSON array (deduplicated issues) |
| `total_rounds` | INTEGER | How many rounds were run |
| `created_at` | TIMESTAMP | When created |

---

### `observations`

Track model behavior for analytics (tokens, latency, cost).

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `session_id` | TEXT | FK → `sessions.id` |
| `round_number` | INTEGER | Which round (nullable) |
| `model` | TEXT | Model name |
| `action` | TEXT | `review`, `re-review`, `consolidate` |
| `input_tokens` | INTEGER | Input tokens used |
| `output_tokens` | INTEGER | Output tokens used |
| `latency_ms` | INTEGER | Response time in milliseconds |
| `cost_estimate` | REAL | Estimated cost in USD |
| `error` | TEXT | Error message if failed |
| `created_at` | TIMESTAMP | When recorded |

---

### `opinion_changes`

Track how opinions evolve between rounds.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `session_id` | TEXT | FK → `sessions.id` |
| `model` | TEXT | Model name |
| `round_from` | INTEGER | Previous round number |
| `round_to` | INTEGER | Current round number |
| `score_before` | REAL | Score in previous round |
| `score_after` | REAL | Score in current round |
| `verdict_before` | TEXT | Verdict in previous round |
| `verdict_after` | TEXT | Verdict in current round |
| `change_reason` | TEXT | Model's explanation (if provided) |
| `created_at` | TIMESTAMP | When recorded |

---

### `source_embeddings` (v2.1.0)

Vector embeddings for similarity search.

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | TEXT | Primary key, FK → `sources.id` |
| `embedding` | TEXT | JSON array of floats |
| `provider` | TEXT | `openai`, `google`, or `fallback` |
| `dimensions` | INTEGER | Vector dimensions (384, 768, or 1536) |
| `created_at` | TIMESTAMP | When created |

---

### `code_contexts` (v2.1.0)

Cached deep analysis results for faster subsequent reviews.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `source_id` | TEXT | FK → `sources.id` |
| `session_id` | TEXT | Session that created this |
| `context_text` | TEXT | Formatted context for prompts |
| `imports` | TEXT | JSON: parsed imports |
| `related_files` | TEXT | JSON: fetched related files |
| `summary` | TEXT | Context summary |
| `created_at` | TIMESTAMP | When created |

**Usage:** When `--deep` is used, context is cached here. Subsequent reviews of same repo reuse cached context.

---

### `long_term_memory` (v2.1.0)

Insights learned across reviews.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `scope` | TEXT | Scope (e.g., `owner/repo`) |
| `memory_type` | TEXT | `pattern`, `issue`, `decision` |
| `content` | TEXT | Memory content |
| `source_session_id` | TEXT | Session that created this |
| `relevance_score` | REAL | Relevance (0-1) |
| `created_at` | TIMESTAMP | When created |

---

### `issue_fingerprints` (v2.1.0)

Tracks issues across reviews with stable fingerprints.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (8-char UUID) |
| `scope` | TEXT | Repository scope (e.g., `owner/repo`) |
| `fingerprint` | TEXT | Unique hash (file + function + type + description) |
| `file_path` | TEXT | File containing the issue |
| `function_name` | TEXT | Function containing issue (nullable) |
| `issue_type` | TEXT | Categorized type (e.g., `sql_injection`, `null_check`) |
| `issue_description` | TEXT | Description of the issue |
| `snippet` | TEXT | Code snippet around issue |
| `snippet_hash` | TEXT | Hash of snippet |
| `severity` | TEXT | `critical`, `major`, `minor`, `nit` |
| `line_number` | INTEGER | Last known line number |
| `first_seen_session` | TEXT | Session that first detected this |
| `last_seen_session` | TEXT | Most recent session |
| `first_seen_pr` | INTEGER | PR number when first seen |
| `last_seen_pr` | INTEGER | PR number when last seen |
| `status` | TEXT | `open`, `fixed`, `wont_fix` |
| `occurrences` | INTEGER | How many times seen |
| `created_at` | TIMESTAMP | When created |
| `updated_at` | TIMESTAMP | When last updated |

**Fingerprint Stability:** Issues are tracked by fingerprint (hash of file + function + type), not line number. This means issues are still tracked even when line numbers change due to code modifications.

---

## Indexes

```sql
CREATE INDEX idx_sources_scope ON sources(scope);
CREATE INDEX idx_sources_task_type ON sources(task_type);
CREATE INDEX idx_sessions_source ON sessions(source_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_rounds_session ON rounds(session_id);
CREATE INDEX idx_round_opinions_session ON round_opinions(session_id);
CREATE INDEX idx_round_opinions_model ON round_opinions(model);
CREATE INDEX idx_verdicts_source ON verdicts(source_id);
CREATE INDEX idx_observations_session ON observations(session_id);
CREATE INDEX idx_opinion_changes_session ON opinion_changes(session_id);
CREATE INDEX idx_code_contexts_source ON code_contexts(source_id);
CREATE INDEX idx_long_term_memory_scope ON long_term_memory(scope);
CREATE INDEX idx_issue_fingerprints_scope ON issue_fingerprints(scope);
CREATE INDEX idx_issue_fingerprints_file ON issue_fingerprints(file_path);
CREATE INDEX idx_issue_fingerprints_status ON issue_fingerprints(status);
```

---

## Common Queries

### Get recent sessions with verdicts

```sql
SELECT 
    s.id,
    s.started_at,
    src.title,
    src.source_ref,
    v.final_verdict,
    v.final_score,
    v.consensus_level
FROM sessions s
JOIN sources src ON s.source_id = src.id
LEFT JOIN verdicts v ON s.id = v.session_id
ORDER BY s.started_at DESC
LIMIT 10;
```

### Get all opinions for a session

```sql
SELECT 
    ro.round_number,
    ro.model,
    ro.score,
    ro.verdict,
    ro.summary
FROM round_opinions ro
WHERE ro.session_id = ?
ORDER BY ro.round_number, ro.model;
```

### Get opinion changes in a session

```sql
SELECT 
    model,
    round_from,
    round_to,
    score_before,
    score_after,
    verdict_before,
    verdict_after
FROM opinion_changes
WHERE session_id = ?
ORDER BY round_from, model;
```

### Get session statistics

```sql
SELECT 
    COUNT(*) as total_calls,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(latency_ms) as total_latency_ms,
    SUM(cost_estimate) as total_cost,
    COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as error_count
FROM observations
WHERE session_id = ?;
```

### Find similar past reviews (by scope)

```sql
SELECT 
    s.id,
    src.title,
    v.final_verdict,
    v.final_score
FROM sessions s
JOIN sources src ON s.source_id = src.id
JOIN verdicts v ON s.id = v.session_id
WHERE src.scope = 'owner/repo'
ORDER BY s.started_at DESC
LIMIT 5;
```

### Get open issues for a repository

```sql
SELECT 
    file_path,
    function_name,
    issue_type,
    severity,
    issue_description,
    occurrences,
    first_seen_pr,
    last_seen_pr
FROM issue_fingerprints
WHERE scope = 'owner/repo' AND status = 'open'
ORDER BY 
    CASE severity 
        WHEN 'critical' THEN 1 
        WHEN 'major' THEN 2 
        WHEN 'minor' THEN 3 
        ELSE 4 
    END,
    occurrences DESC;
```

### Get recurring issues (seen more than once)

```sql
SELECT 
    file_path,
    function_name,
    issue_description,
    severity,
    occurrences,
    first_seen_pr,
    last_seen_pr
FROM issue_fingerprints
WHERE scope = 'owner/repo' 
    AND status = 'open' 
    AND occurrences > 1
ORDER BY occurrences DESC;
```

### Get issue statistics for a repository

```sql
SELECT 
    status,
    COUNT(*) as count,
    COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical,
    COUNT(CASE WHEN severity = 'major' THEN 1 END) as major,
    COUNT(CASE WHEN severity = 'minor' THEN 1 END) as minor
FROM issue_fingerprints
WHERE scope = 'owner/repo'
GROUP BY status;
```

---

## Entity Relationships

```
sources (1) ──────< sessions (N)
    │                   │
    │                   ├──────< rounds (N)
    │                   │           │
    │                   │           └──────< round_opinions (N)
    │                   │
    │                   ├──────< verdicts (1)
    │                   │
    │                   ├──────< observations (N)
    │                   │
    │                   └──────< opinion_changes (N)
    │
    ├──────< verdicts (N)
    │
    ├──────< source_embeddings (1)
    │
    └──────< code_contexts (N)

issue_fingerprints ──────< sessions (via first/last_seen_session)
    │
    └── Tracks issues across PRs with stable fingerprints
```

---

## Database Location

Default: `~/.council/data/council.db`

Override via:
- Environment: `COUNCIL_STORAGE_PATH=/path/to/db`
- Config: `council.yaml` → `storage.path`

---

## Inspecting the Database

```bash
# Open with sqlite3
sqlite3 ~/.council/data/council.db

# List tables
.tables

# Show schema
.schema sources

# Query sessions
SELECT id, status, started_at FROM sessions LIMIT 5;

# Exit
.quit
```
