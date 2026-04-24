import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from .database import init_db          # NEW


def create_app():
    load_dotenv()
    app = Flask(__name__)
    
    CORS(
        app,
        resources={r"/api/*": {"origins": [
            "http://localhost:3000",
            os.getenv("FRONTEND_ORIGIN", ""),
        ]}},
    )

    init_db()                          # NEW — creates tables on first run

    from .routes import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    return app