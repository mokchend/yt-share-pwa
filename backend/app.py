import os
import re
import json
from urllib.parse import parse_qs, urlparse

import paho.mqtt.publish as publish
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
API_KEY = os.getenv("YOUTUBE_COLLECTOR_API_KEY", "change-this-secret")
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "youtube/jobs")
YOUTUBE_WATCH_PREFIX = "https://www.youtube.com/watch?v="

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

YOUTUBE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{11}$")


def normalize_url(url: str) -> str:
    return url.strip()


def clean_youtube_watch_url(url: str) -> tuple[str, str] | None:
    if not url:
        return None

    url = normalize_url(url)
    if not url.startswith(YOUTUBE_WATCH_PREFIX):
        return None

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if parsed.scheme != "https" or host != "www.youtube.com" or path != "/watch":
        return None

    video_id = (parse_qs(parsed.query).get("v") or [None])[0]
    if not video_id or not YOUTUBE_ID_REGEX.match(video_id):
        return None

    return video_id, f"https://www.youtube.com/watch?v={video_id}"


def publish_event(event: dict):
    publish.single(
        MQTT_TOPIC,
        payload=json.dumps(event),
        hostname=MQTT_BROKER,
        port=MQTT_PORT,
        qos=1,
    )


def create_video_submission(url: str, source: str, sender: str):
    if not url:
        return {"ok": False, "error": "missing_url"}, 400

    cleaned = clean_youtube_watch_url(url)
    if not cleaned:
        return {"ok": False, "error": "invalid_youtube_url"}, 400
    video_id, cleaned_url = cleaned

    event = {
        "youtube_url": cleaned_url,
        "video_id": video_id,
        "source": source,
        "sender": sender,
    }
    publish_event(event)

    return {
        "status": "queued",
        "youtube_url": cleaned_url,
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
            },
            "queue": {
                "broker": MQTT_BROKER,
                "port": MQTT_PORT,
                "topic": MQTT_TOPIC,
            },
        }
    )


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "yt-share-backend",
            "queue": {
                "broker": MQTT_BROKER,
                "port": MQTT_PORT,
                "topic": MQTT_TOPIC,
            },
        }
    )


@app.post("/youtube")
def youtube():
    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key != API_KEY:
        return jsonify({"detail": "Invalid API key"}), 401

    data = request.get_json(silent=True) or {}
    url = normalize_url(data.get("youtube_url", ""))

    body, status = create_video_submission(url, "pwa_youtube", "anonymous")
    return jsonify(body), status


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
