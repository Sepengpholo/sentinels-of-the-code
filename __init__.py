"""App factory — wires up Flask, DB path, and blueprint routes."""
import os
from flask import Flask


def create_app():
    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # Ensure data directory exists (SQLite + JSON saves)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    saves_dir = os.path.join(data_dir, "saves")
    os.makedirs(saves_dir, exist_ok=True)

    app.config["DATA_DIR"] = data_dir
    app.config["SAVES_DIR"] = saves_dir
    app.config["DB_PATH"] = os.path.join(data_dir, "world_state.db")

    from app.db import init_db
    init_db(app.config["DB_PATH"])

    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app
