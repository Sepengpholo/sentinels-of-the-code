"""API routes for Sentinels of the Code.

Session-based: a player's progress lives in the Flask session (cookie) plus
SQLite for durable XP/level/flags. No login system — single-browser-session play.
"""
import sqlite3
from flask import Blueprint, request, jsonify, session, render_template, current_app

from app.player import Player, calculate_xp_award
from app.hint_system import HintSystem
from app.sandbox import run_submission
from app.modules import MODULES, ALL_VALIDATORS, ALL_HINTS, get_mission
from app.modules.m02_sql import SEED_TABLE_SQL, SEED_DATA_SQL
from app.modules.m04_log_analysis import AUTH_LOG, ACCESS_LOG
from app.modules.m05_networking import WELL_KNOWN_PORTS, SCAN_RESULTS
from app.modules.m06_web_security import SIM_USERS, SIM_COMMENTS
from app.modules.m07_owasp import OWASP_CATEGORIES, SIM_FINDINGS, SEVERITY_WEIGHTS

# Seed data injected into the learner's exec namespace, keyed by module_id.
# Plain code_submit missions (m01) get nothing extra; modules with reference
# data (m04 logs, m05 scan results, m06 sim data, m07 owasp tables) get theirs.
MODULE_SEED_GLOBALS = {
    "m04": {"auth_log": AUTH_LOG, "access_log": ACCESS_LOG},
    "m05": {"WELL_KNOWN_PORTS": WELL_KNOWN_PORTS, "SCAN_RESULTS": SCAN_RESULTS},
    "m06": {"SIM_USERS": SIM_USERS, "SIM_COMMENTS": SIM_COMMENTS},
    "m07": {
        "OWASP_CATEGORIES": OWASP_CATEGORIES,
        "SIM_FINDINGS": SIM_FINDINGS,
        "SEVERITY_WEIGHTS": SEVERITY_WEIGHTS,
    },
}

bp = Blueprint("main", __name__)
hint_system = HintSystem(ALL_HINTS)

# In-memory per-session SQL sandbox connections (Module 2 & 3).
# Keyed by player_id. Acceptable for a single-instance Render deployment;
# would need a different strategy (e.g. per-request seeded temp DB) if scaled
# across multiple worker processes.
_sql_sandboxes = {}


def _get_sandbox_conn(player_id):
    if player_id not in _sql_sandboxes:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.execute(SEED_TABLE_SQL)
        conn.executescript(SEED_DATA_SQL)
        conn.commit()
        _sql_sandboxes[player_id] = conn
    return _sql_sandboxes[player_id]


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/api/player/new", methods=["POST"])
def new_player():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not (3 <= len(name) <= 20):
        return jsonify({"error": "Callsign must be 3-20 characters."}), 400

    player = Player.create(current_app.config["DB_PATH"], name)
    session["player_id"] = player.player_id
    return jsonify(player.to_dict())


@bp.route("/api/player/me", methods=["GET"])
def get_me():
    player_id = session.get("player_id")
    if not player_id:
        return jsonify({"error": "No active player session."}), 404
    player = Player.load(current_app.config["DB_PATH"], player_id)
    if not player:
        return jsonify({"error": "Player not found."}), 404
    return jsonify(player.to_dict())


@bp.route("/api/modules", methods=["GET"])
def list_modules():
    out = []
    for module_id, module in MODULES.items():
        out.append({
            "module_id": module_id,
            "title": module["title"],
            "unlock_rule": module["unlock_rule"],
            "mission_count": len(module["missions"]),
        })
    return jsonify(out)


@bp.route("/api/modules/<module_id>/missions", methods=["GET"])
def list_missions(module_id):
    module = MODULES.get(module_id)
    if not module:
        return jsonify({"error": "Module not found."}), 404
    # Strip internal fields (expected_sql / validation_mode) before sending to client
    missions = []
    for m in module["missions"]:
        missions.append({
            "mission_id": m["mission_id"],
            "title": m["title"],
            "story": m["story"],
            "objective": m["objective"],
            "challenge_type": m["challenge_type"],
            "starter_code": m.get("starter_code", ""),
            "xp_reward": m["xp_reward"],
            "difficulty": m["difficulty"],
        })
    return jsonify(missions)


@bp.route("/api/mission/<mission_id>/hint", methods=["POST"])
def request_hint(mission_id):
    player_id = session.get("player_id")
    if not player_id:
        return jsonify({"error": "No active player session."}), 404

    data = request.get_json(force=True)
    level = int(data.get("level", 1))

    hint_key = f"hint_max_{mission_id}"
    prior_max = session.get(hint_key, 0)

    text, new_max, allowed = hint_system.get_hint(mission_id, level, prior_max)
    if allowed:
        session[hint_key] = new_max

    return jsonify({"hint": text, "level": level, "allowed": allowed})


@bp.route("/api/mission/<mission_id>/submit", methods=["POST"])
def submit_mission(mission_id):
    player_id = session.get("player_id")
    if not player_id:
        return jsonify({"error": "No active player session."}), 404

    player = Player.load(current_app.config["DB_PATH"], player_id)
    if not player:
        return jsonify({"error": "Player not found."}), 404

    mission, module_id = get_mission(mission_id)
    if not mission:
        return jsonify({"error": "Mission not found."}), 404

    data = request.get_json(force=True)
    submitted_code = data.get("code", "")

    validator = ALL_VALIDATORS.get(mission_id)
    if not validator:
        return jsonify({"error": "No validator registered for this mission."}), 500

    # Build validation context based on challenge type
    if mission["challenge_type"] == "sql_submit":
        conn = _get_sandbox_conn(player_id)
        context = {
            "conn": conn,
            "submitted_sql": submitted_code,
            "expected_sql": mission["expected_sql"],
        }
        success, message = validator(context)

    elif mission["challenge_type"] == "code_submit" and module_id == "m03":
        conn = _get_sandbox_conn(player_id)
        ok, namespace_or_error = run_submission(submitted_code, extra_globals={"sqlite3": sqlite3})
        if not ok:
            success, message = False, f"Code error: {namespace_or_error}"
        else:
            context = dict(namespace_or_error)
            context["conn"] = conn
            context["db_path"] = current_app.config["DB_PATH"]
            context["source_code"] = submitted_code
            success, message = validator(context)

    elif mission["challenge_type"] == "code_submit":
        # m01, m04, m05, m06, m07 — plain Python, with module-specific seed data injected
        seed_globals = MODULE_SEED_GLOBALS.get(module_id, {})
        ok, namespace_or_error = run_submission(submitted_code, extra_globals=seed_globals)
        if not ok:
            success, message = False, f"Code error: {namespace_or_error}"
        else:
            context = dict(namespace_or_error)
            context["source_code"] = submitted_code
            success, message = validator(context)

    else:  # fallback — should not normally be reached
        ok, namespace_or_error = run_submission(submitted_code)
        if not ok:
            success, message = False, f"Code error: {namespace_or_error}"
        else:
            context = dict(namespace_or_error)
            success, message = validator(context)

    hint_key = f"hint_max_{mission_id}"
    hint_level_used = session.get(hint_key, 0)

    attempts_key = f"attempts_{mission_id}"
    attempts = session.get(attempts_key, 0) + 1
    session[attempts_key] = attempts

    response = {"success": success, "message": message}

    if success:
        xp_awarded = calculate_xp_award(mission["xp_reward"], hint_level_used)
        leveled_up = player.add_xp(current_app.config["DB_PATH"], xp_awarded)
        player.record_mission_attempt(
            current_app.config["DB_PATH"], mission_id, "completed",
            hint_level_used, attempts
        )
        response["xp_awarded"] = xp_awarded
        response["leveled_up"] = leveled_up
        response["player"] = player.to_dict()
    else:
        player.record_mission_attempt(
            current_app.config["DB_PATH"], mission_id, "failed",
            hint_level_used, attempts
        )

    return jsonify(response)
