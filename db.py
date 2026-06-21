"""SQLite schema bootstrap + connection helper."""
import sqlite3


def get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    conn = get_conn(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        player_id TEXT PRIMARY KEY,
        name TEXT,
        level INTEGER DEFAULT 1,
        xp_total INTEGER DEFAULT 0,
        created_at TEXT,
        last_login TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS modules (
        module_id TEXT PRIMARY KEY,
        title TEXT,
        unlock_rule TEXT,
        sequence_order INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS missions (
        mission_id TEXT PRIMARY KEY,
        module_id TEXT,
        title TEXT,
        xp_reward INTEGER,
        difficulty INTEGER,
        sequence_order INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_progress (
        player_id TEXT,
        module_id TEXT,
        completed BOOLEAN DEFAULT 0,
        unlocked_at TEXT,
        completed_at TEXT,
        PRIMARY KEY (player_id, module_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mission_attempts (
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id TEXT,
        mission_id TEXT,
        status TEXT,
        hint_level_used INTEGER DEFAULT 0,
        attempts_count INTEGER DEFAULT 0,
        completed_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS flags_captured (
        player_id TEXT,
        mission_id TEXT,
        flag_value TEXT,
        captured_at TEXT,
        PRIMARY KEY (player_id, mission_id)
    )
    """)

    conn.commit()
    conn.close()
