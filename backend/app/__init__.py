import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    app = Flask(__name__)

    # Lock CORS down to the Next.js origin only.
    CORS(
        app,
        resources={r"/api/*": {"origins": [
            "http://localhost:3000",
            os.getenv("FRONTEND_ORIGIN", ""),
        ]}},
    )

    from .routes import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    return app