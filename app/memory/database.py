import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.config import DB_PATH

logger = logging.getLogger("database")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

# Additive, idempotent column migrations: (table, column, SQL type).
# Never drop or rename here; existing databases must keep working.
COLUMN_MIGRATIONS = [
    # Compact record of the tools used in an assistant answer, so the model
    # can still see what a tool returned in later turns.
    ("messages", "tool_trace_json", "TEXT"),
    # Claude Code session resumed by each conversation in claude-code mode.
    ("conversations", "claude_session_id", "TEXT"),
    # Profile customization: avatar (emoji or initials) and emoji usage 1-3.
    ("personalities", "avatar", "TEXT"),
    ("personalities", "emoji_level", "INTEGER DEFAULT 2"),
    # Casos (projects) can be archived instead of deleted.
    ("projects", "archived", "INTEGER DEFAULT 0"),
]


def _apply_column_migrations(cur: sqlite3.Cursor) -> None:
    for table, column, sql_type in COLUMN_MIGRATIONS:
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
            logger.info("Migração: coluna %s.%s adicionada.", table, column)


def init_db():
    """Initializes database schema and default records."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    -- System & User Settings
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Configurable Personalities
    CREATE TABLE IF NOT EXISTS personalities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        system_instructions TEXT NOT NULL,
        tone TEXT DEFAULT 'prestativo',
        formality INTEGER DEFAULT 3,       -- 1 (informal) to 5 (formal)
        objectivity INTEGER DEFAULT 4,     -- 1 (conversador) to 5 (direto)
        detail_level INTEGER DEFAULT 3,    -- 1 (conciso) to 5 (detalhado)
        is_default INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Independent Projects
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        instructions TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Conversations
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        project_id TEXT,
        personality_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
        FOREIGN KEY (personality_id) REFERENCES personalities(id) ON DELETE SET NULL
    );

    -- Messages
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,                -- 'user', 'assistant', 'system'
        content TEXT NOT NULL,
        sources_json TEXT,                 -- Citations/references for RAG & Web
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    );

    -- Long-term Persistent Memories
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,            -- 'decision', 'preference', 'project', 'fact'
        content TEXT NOT NULL,
        project_id TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- Document Library (RAG)
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT NOT NULL,           -- 'pdf', 'txt', 'md'
        total_pages INTEGER DEFAULT 1,
        total_chunks INTEGER DEFAULT 0,
        collection TEXT DEFAULT 'Geral',
        project_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- Document Chunks with Vectors
    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        page_number INTEGER DEFAULT 1,
        content TEXT NOT NULL,
        embedding_json TEXT NOT NULL,      -- Dense vector representation
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );

    -- Security Audit Trail
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        action_type TEXT NOT NULL,         -- 'file_read', 'file_write', 'web_access', 'tool_exec'
        category TEXT NOT NULL,            -- 'free', 'requires_auth', 'external'
        resource TEXT NOT NULL,
        authorized INTEGER NOT NULL,       -- 1 = yes, 0 = blocked/denied
        details TEXT
    );
    """)

    _apply_column_migrations(cur)

    # Populate default personality if none exists
    cur.execute("SELECT COUNT(*) FROM personalities")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO personalities (id, name, description, system_instructions, tone, formality, objectivity, detail_level, is_default)
        VALUES (
            'default',
            'Assistente Pessoal',
            'Assistente inteligente, objetivo e prestativo, otimizado para o seu computador.',
            'Você é um assistente virtual pessoal independente, inteligente e prestativo. Você roda localmente no computador do usuário. Suas respostas devem ser claras, precisas, bem formatadas e em português. Quando consultar documentos do usuário, cite sempre o nome do documento e a página. Nunca invente dados.',
            'prestativo',
            3,
            4,
            3,
            1
        )
        """)

    _seed_victorique(cur)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")


def _seed_victorique(cur: sqlite3.Cursor) -> None:
    """
    Creates the Victorique profile once. Only on that first insertion, and
    only when the user has no profiles of their own, it becomes the default;
    later runs never touch which profile is the default.
    """
    from app.core import victorique_persona as vp

    row = cur.execute(
        "SELECT system_instructions, description, tone FROM personalities WHERE id = ?",
        (vp.VICTORIQUE_ID,),
    ).fetchone()
    if row:
        _upgrade_victorique(cur, row)
        return
    user_profiles = cur.execute(
        "SELECT COUNT(*) FROM personalities WHERE id != 'default'"
    ).fetchone()[0]
    make_default = user_profiles == 0
    if make_default:
        cur.execute("UPDATE personalities SET is_default = 0")
    style = vp.VICTORIQUE_STYLE
    cur.execute(
        """
        INSERT INTO personalities (id, name, description, system_instructions, tone,
                                   formality, objectivity, detail_level, emoji_level, is_default)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            vp.VICTORIQUE_ID, vp.VICTORIQUE_NAME, vp.VICTORIQUE_DESCRIPTION,
            vp.VICTORIQUE_INSTRUCTIONS, vp.VICTORIQUE_TONE,
            style["formality"], style["objectivity"], style["detail_level"], style["emoji_level"],
            1 if make_default else 0,
        ),
    )


def _upgrade_victorique(cur: sqlite3.Cursor, row: sqlite3.Row) -> None:
    """
    Moves an unedited Victorique profile to the current persona text. A profile
    whose instructions the user changed is never touched.
    """
    from app.core import victorique_persona as vp

    if row["system_instructions"] not in vp.LEGACY_INSTRUCTIONS:
        return
    style = vp.VICTORIQUE_STYLE
    cur.execute(
        """
        UPDATE personalities SET system_instructions = ?, description = ?, tone = ?,
               formality = ?, objectivity = ?, detail_level = ?, emoji_level = ?
        WHERE id = ?
        """,
        (
            vp.VICTORIQUE_INSTRUCTIONS, vp.VICTORIQUE_DESCRIPTION, vp.VICTORIQUE_TONE,
            style["formality"], style["objectivity"], style["detail_level"], style["emoji_level"],
            vp.VICTORIQUE_ID,
        ),
    )
    logger.info("Perfil Victorique atualizado para a versão %s da persona.", vp.VICTORIQUE_VERSION)


if __name__ == "__main__":
    init_db()
