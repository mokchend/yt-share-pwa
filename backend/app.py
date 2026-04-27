import os
import re
import smtplib
import sqlite3
from contextlib import closing
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "videos.db")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")

SMTP_ENABLED = os.getenv("SMTP_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USERNAME)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

YOUTUBE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{11}$")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                source TEXT DEFAULT 'unknown',
                sender TEXT DEFAULT 'anonymous',
                submitted_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def normalize_url(url: str) -> str:
    return url.strip()


def extract_video_id(url: str) -> str | None:
    if not url:
        return None

    url = normalize_url(url)

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if "youtu.be" in host:
        candidate = path.lstrip("/").split("/")[0]
        return candidate if YOUTUBE_ID_REGEX.match(candidate or "") else None

    if "youtube.com" in host or "m.youtube.com" in host or "www.youtube.com" in host:
        if path == "/watch":
            query = parse_qs(parsed.query)
            candidate = (query.get("v") or [None])[0]
            return candidate if YOUTUBE_ID_REGEX.match(candidate or "") else None
        if path.startswith("/shorts/"):
            candidate = path.split("/shorts/")[-1].split("/")[0]
            return candidate if YOUTUBE_ID_REGEX.match(candidate or "") else None
        if path.startswith("/embed/"):
            candidate = path.split("/embed/")[-1].split("/")[0]
            return candidate if YOUTUBE_ID_REGEX.match(candidate or "") else None

    return None


def send_email_notification(video_id: str, url: str, source: str):
    if not SMTP_ENABLED:
        return

    if not all([SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_TO, EMAIL_FROM]):
        raise RuntimeError("SMTP is enabled but configuration is incomplete.")

    subject = f"Nouvelle vidéo YouTube: {video_id}"
    body = (
        f"Une nouvelle vidéo a été ajoutée.\n\n"
        f"Video ID: {video_id}\n"
        f"URL: {url}\n"
        f"Source: {source}\n"
        f"Date: {datetime.utcnow().isoformat()}Z\n"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = EMAIL_FROM
    message["To"] = EMAIL_TO
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def get_video(video_id: str):
    with closing(get_db_connection()) as conn:
        return conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()


def insert_video(video_id: str, url: str, source: str, sender: str):
    submitted_at = datetime.utcnow().isoformat() + "Z"
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            INSERT INTO videos (video_id, url, source, sender, submitted_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (video_id, url, source, sender, submitted_at),
        )
        conn.commit()


def create_video_submission(url: str, source: str, sender: str):
    if not url:
        return {"ok": False, "error": "missing_url"}, 400

    video_id = extract_video_id(url)
    if not video_id:
        return {"ok": False, "error": "invalid_youtube_url"}, 400

    existing = get_video(video_id)
    if existing:
        return {"ok": True, "status": "duplicate", "video_id": video_id}, 200

    insert_video(video_id, url, source, sender)

    email_status = "disabled"
    try:
        send_email_notification(video_id, url, source)
        email_status = "sent" if SMTP_ENABLED else "disabled"
    except Exception as exc:
        email_status = f"error:{exc.__class__.__name__}"

    return {
        "ok": True,
        "status": "created",
        "video_id": video_id,
        "email": email_status,
    }, 200


@app.get("/")
def root():
    """Évite un 404 Flask quand on ouvre l’URL de l'API dans le navigateur."""
    return jsonify(
        {
            "ok": True,
            "service": "yt-share-backend",
            "endpoints": {
                "health": "/health",
                "youtube": "POST /youtube (JSON: youtube_url)",
                "submit": "POST /submit (JSON: url, source)",
                "videos": "/videos",
            },
        }
    )


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "yt-share-backend"})


@app.get("/videos")
def videos():
    limit = min(int(request.args.get("limit", 50)), 200)
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM videos ORDER BY submitted_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return jsonify(
        {
            "ok": True,
            "count": len(rows),
            "items": [dict(r) for r in rows],
        }
    )


@app.post("/submit")
def submit():
    data = request.get_json(silent=True) or {}
    url = normalize_url(data.get("url", ""))
    source = data.get("source", "unknown")
    sender = data.get("sender", "anonymous")

    body, status = create_video_submission(url, source, sender)
    return jsonify(body), status


@app.post("/youtube")
def youtube():
    data = request.get_json(silent=True) or {}
    url = normalize_url(data.get("youtube_url", ""))

    body, status = create_video_submission(url, "pwa_youtube", "anonymous")
    return jsonify(body), status


# Gunicorn (Render, etc.) importe ce module sans exécuter __main__ : la base doit exister.
init_db()

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
