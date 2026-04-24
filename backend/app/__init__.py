import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from .database import init_db          # NEW


def create_app():
    load_dotenv()
    app = Flask(__name__)

    # Whitelist localhost for dev plus any origins listed in FRONTEND_ORIGIN
    # (comma-separated, so you can list both production and preview URLs).
    extra = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "").split(",") if o.strip()]
    origins = ["http://localhost:3000", "http://127.0.0.1:3000", *extra]
    CORS(app, resources={r"/api/*": {"origins": origins}})

    # Fail fast if a required secret is missing — saves debugging mid-request.
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    init_db()                          # creates tables on first run

    from .routes import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    return app