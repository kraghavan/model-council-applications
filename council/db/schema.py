"""Database schema for Model Council.

Tables:
- sources: PRs, architecture docs, any reviewed content
- sessions: A complete review session (may have multiple rounds)
- rounds: Individual deliberation rounds within a session
- round_opinions: Each model's opinion per round
- verdicts: Final consolidated verdicts
- observations: Tracking model behavior (tokens, latency, cost)
- opinion_changes: Tracking how opinions change between rounds
"""

import sqlite3
from pathlib import Path
from typing import Optional

# Try to import sqlite-vec, gracefully degrade if not available
# Note: macOS system Python doesn't support enable_load_extension
SQLITE_VEC_AVAILABLE = False
try:
    import sqlite3 as _sqlite3
    _test_conn = _sqlite3.connect(":memory:")
    _test_conn.enable_load_extension(True)  # Test if supported
    _test_conn.close()
    
    import sqlite_vec
    SQLITE_VEC_AVAILABLE = True
except (ImportError, AttributeError):
    # sqlite-vec not installed or extensions not supported (macOS)
    pass


SCHEMA_VERSION = 2

SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sources: What we're reviewing (PRs, architecture docs, etc.)
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,              -- 'pr-review', 'architecture', etc.
    source_ref TEXT NOT NULL,             -- URL, file path, or identifier
    scope TEXT,                           -- 'owner/repo' or project name
    title TEXT,
    content_hash TEXT,                    -- SHA256 for deduplication
    raw_content TEXT,
    metadata TEXT,                        -- JSON: task-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Source Embeddings: Vector embeddings for similarity search
CREATE TABLE IF NOT EXISTS source_embeddings (
    source_id TEXT PRIMARY KEY,
    embedding TEXT,                       -- JSON array of floats
    provider TEXT,                        -- 'openai', 'google', 'fallback'
    dimensions INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Long-term Memory: Insights learned across reviews
CREATE TABLE IF NOT EXISTS long_term_memory (
    id TEXT PRIMARY KEY,
    scope TEXT,                           -- 'owner/repo' or project name
    memory_type TEXT,                     -- 'pattern', 'issue', 'decision'
    content TEXT,
    source_session_id TEXT,               -- Session that created this memory
    relevance_score REAL DEFAULT 1.0,     -- How relevant/useful this memory is
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Code Contexts: Cached deep analysis results
CREATE TABLE IF NOT EXISTS code_contexts (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    session_id TEXT,
    context_text TEXT,                    -- Formatted context for prompts
    imports TEXT,                         -- JSON: parsed imports
    related_files TEXT,                   -- JSON: fetched related files
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Sessions: A complete review (may span multiple rounds)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    models TEXT NOT NULL,                 -- JSON array of model names
    max_rounds INTEGER DEFAULT 2,
    status TEXT DEFAULT 'in_progress',    -- 'in_progress', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Rounds: Individual deliberation rounds
CREATE TABLE IF NOT EXISTS rounds (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',        -- 'pending', 'running', 'completed'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    UNIQUE (session_id, round_number)
);

-- Round Opinions: Each model's opinion per round
CREATE TABLE IF NOT EXISTS round_opinions (
    id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    model TEXT NOT NULL,
    score REAL,
    verdict TEXT,                         -- 'APPROVE', 'REQUEST_CHANGES', 'COMMENT'
    summary TEXT,
    issues TEXT,                          -- JSON array
    extras TEXT,                          -- JSON: task-specific extras
    raw_response TEXT,                    -- Full model response
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (round_id) REFERENCES rounds(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    UNIQUE (round_id, model)
);

-- Verdicts: Final consolidated output
CREATE TABLE IF NOT EXISTS verdicts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    consolidator_model TEXT,              -- Which model did final consolidation
    final_score REAL,
    final_verdict TEXT,
    consensus_level TEXT,                 -- 'full', 'partial', 'split', 'none'
    summary TEXT,
    issues TEXT,                          -- JSON array (deduplicated)
    total_rounds INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Observations: Track model behavior
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    round_number INTEGER,
    model TEXT NOT NULL,
    action TEXT NOT NULL,                 -- 'review', 'read_opinions', 'consolidate'
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    cost_estimate REAL,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Opinion Changes: Track how opinions evolve between rounds
CREATE TABLE IF NOT EXISTS opinion_changes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    model TEXT NOT NULL,
    round_from INTEGER NOT NULL,
    round_to INTEGER NOT NULL,
    score_before REAL,
    score_after REAL,
    verdict_before TEXT,
    verdict_after TEXT,
    change_reason TEXT,                   -- Model's explanation (if provided)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sources_scope ON sources(scope);
CREATE INDEX IF NOT EXISTS idx_sources_task_type ON sources(task_type);
CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_rounds_session ON rounds(session_id);
CREATE INDEX IF NOT EXISTS idx_round_opinions_session ON round_opinions(session_id);
CREATE INDEX IF NOT EXISTS idx_round_opinions_model ON round_opinions(model);
CREATE INDEX IF NOT EXISTS idx_verdicts_source ON verdicts(source_id);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_opinion_changes_session ON opinion_changes(session_id);
CREATE INDEX IF NOT EXISTS idx_long_term_memory_scope ON long_term_memory(scope);
CREATE INDEX IF NOT EXISTS idx_long_term_memory_type ON long_term_memory(memory_type);
CREATE INDEX IF NOT EXISTS idx_code_contexts_source ON code_contexts(source_id);
"""


def get_db_path(custom_path: Optional[str] = None) -> Path:
    """Get the database file path.
    
    Priority:
    1. custom_path argument
    2. COUNCIL_STORAGE_PATH env var
    3. Default: ~/.council/data/council.db
    """
    import os
    
    if custom_path:
        path = Path(custom_path)
    elif os.environ.get("COUNCIL_STORAGE_PATH"):
        path = Path(os.environ["COUNCIL_STORAGE_PATH"])
    else:
        path = Path.home() / ".council" / "data" / "council.db"
    
    return path


def init_db(db_path: Optional[str] = None, force: bool = False) -> Path:
    """Initialize the database with schema.
    
    Args:
        db_path: Custom path for database file
        force: If True, recreate tables (WARNING: destroys data)
        
    Returns:
        Path to the database file
    """
    path = get_db_path(db_path)
    
    # Create directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect and initialize
    conn = sqlite3.connect(str(path))
    
    try:
        # Load sqlite-vec extension if available (not on macOS system Python)
        if SQLITE_VEC_AVAILABLE:
            try:
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except AttributeError:
                pass  # Extension loading not supported
        
        cursor = conn.cursor()
        
        # Check if already initialized
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        exists = cursor.fetchone() is not None
        
        if exists and not force:
            # Check version
            cursor.execute("SELECT MAX(version) FROM schema_version")
            current_version = cursor.fetchone()[0] or 0
            
            if current_version >= SCHEMA_VERSION:
                return path
        
        if force:
            # Drop all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            for (table,) in tables:
                if table != "sqlite_sequence":
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
        
        # Create schema
        conn.executescript(SCHEMA_SQL)
        
        # Record version
        cursor.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,)
        )
        
        conn.commit()
        
    finally:
        conn.close()
    
    return path


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a database connection.
    
    Args:
        db_path: Custom path for database file
        
    Returns:
        SQLite connection with row factory set
    """
    path = get_db_path(db_path)
    
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Run 'council init' first."
        )
    
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row  # Access columns by name
    
    # Load sqlite-vec if available (not on macOS system Python)
    if SQLITE_VEC_AVAILABLE:
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except AttributeError:
            pass  # Extension loading not supported
    
    return conn
