"""Player model, XP curve, and persistence."""
import uuid
import json
import os
from datetime import datetime, timezone

from app.db import get_conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def xp_required_for_level(level):
    """xp_required(level) = 100 * level^1.5, rounded."""
    return round(100 * (level ** 1.5))


def calculate_xp_award(base_xp, hint_level_used):
    """Hint penalty curve — preserves mastery incentive without punishing asking."""
    multipliers = {0: 1.0, 1: 0.85, 2: 0.85, 3: 0.65, 4: 0.40, 5: 0.15}
    mult = multipliers.get(hint_level_used, 0.15)
    return round(base_xp * mult)


class Player:
    def __init__(self, name, player_id=None):
        self.player_id = player_id or str(uuid.uuid4())
        self.name = name
        self.level = 1
        self.xp_total = 0
        self.modules_completed = []
        self.flags_captured = []
        self.hint_usage = {}
        self.created_at = now_iso()

    @staticmethod
    def create(db_path, name):
        player = Player(name=name)
        conn = get_conn(db_path)
        conn.execute(
            """INSERT INTO players (player_id, name, level, xp_total, created_at, last_login)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (player.player_id, player.name, player.level, player.xp_total,
             player.created_at, now_iso()),
        )
        conn.commit()
        conn.close()
        return player

    @staticmethod
    def load(db_path, player_id):
        conn = get_conn(db_path)
        row = conn.execute(
            "SELECT * FROM players WHERE player_id = ?", (player_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        player = Player(name=row["name"], player_id=row["player_id"])
        player.level = row["level"]
        player.xp_total = row["xp_total"]
        player.created_at = row["created_at"]

        # progress + flags
        conn = get_conn(db_path)
        completed = conn.execute(
            "SELECT module_id FROM player_progress WHERE player_id = ? AND completed = 1",
            (player_id,),
        ).fetchall()
        player.modules_completed = [r["module_id"] for r in completed]

        flags = conn.execute(
            "SELECT mission_id, flag_value FROM flags_captured WHERE player_id = ?",
            (player_id,),
        ).fetchall()
        player.flags_captured = [dict(r) for r in flags]
        conn.close()
        return player

    def add_xp(self, db_path, amount):
        self.xp_total += amount
        leveled_up = False
        while self.xp_total >= xp_required_for_level(self.level + 1):
            self.level += 1
            leveled_up = True

        conn = get_conn(db_path)
        conn.execute(
            "UPDATE players SET xp_total = ?, level = ?, last_login = ? WHERE player_id = ?",
            (self.xp_total, self.level, now_iso(), self.player_id),
        )
        conn.commit()
        conn.close()
        return leveled_up

    def record_mission_attempt(self, db_path, mission_id, status, hint_level_used, attempts_count):
        conn = get_conn(db_path)
        conn.execute(
            """INSERT INTO mission_attempts
               (player_id, mission_id, status, hint_level_used, attempts_count, completed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (self.player_id, mission_id, status, hint_level_used, attempts_count,
             now_iso() if status == "completed" else None),
        )
        conn.commit()
        conn.close()

    def capture_flag(self, db_path, mission_id, flag_value):
        conn = get_conn(db_path)
        conn.execute(
            """INSERT OR REPLACE INTO flags_captured (player_id, mission_id, flag_value, captured_at)
               VALUES (?, ?, ?, ?)""",
            (self.player_id, mission_id, flag_value, now_iso()),
        )
        conn.commit()
        conn.close()

    def mark_module_complete(self, db_path, module_id):
        conn = get_conn(db_path)
        conn.execute(
            """INSERT INTO player_progress (player_id, module_id, completed, unlocked_at, completed_at)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT(player_id, module_id) DO UPDATE SET completed=1, completed_at=excluded.completed_at""",
            (self.player_id, module_id, now_iso(), now_iso()),
        )
        conn.commit()
        conn.close()

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "name": self.name,
            "level": self.level,
            "xp_total": self.xp_total,
            "xp_to_next_level": xp_required_for_level(self.level + 1) - self.xp_total,
            "modules_completed": self.modules_completed,
            "flags_captured": self.flags_captured,
        }
