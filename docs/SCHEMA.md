# Model Council Database Schema

This document describes the SQLite database schema used by Model Council for storing review sessions, deliberations, and observations.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              council.db                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────┐       ┌───────────┐       ┌─────────────────┐               │
│  │  sources  │──────▶│  sessions │──────▶│     rounds      │               │
│  │           │       │           │       │                 │               │
│  │ PR/arch   │       │ models    │       │ round_number    │               │
│  │ content   │       │ status    │       │ status          │               │
│  └───────────┘       └─────┬─────┘       └────────┬────────┘               │
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
│                    │ final_verdict │     │ score_after     │               │
│                    └───────────────┘     └─────────────────┘               │
│                                                                             │
│                    ┌───────────────┐                                       │
│                    │ observations  │                                       │
│                    │               │                                       │
│                    │ tokens, cost  │                                       │
│                    │ latency       │                                       │
│                    └───────────────┘                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
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
    └──────< verdicts (N)
```

