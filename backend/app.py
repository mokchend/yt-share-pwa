import os
import re
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path
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
SMS_ALERT_ENABLED = os.getenv("SMS_ALERT_ENABLED", "true").lower() == "true"
FREE_MOBILE_SMS_USER = os.getenv("FREE_MOBILE_SMS_USER", "")
FREE_MOBILE_SMS_PASS = os.getenv("FREE_MOBILE_SMS_PASS", "")
SMS_ALERT_TIMEOUT_SECONDS = float(os.getenv("SMS_ALERT_TIMEOUT_SECONDS", "5"))
SMS_ALERT_MESSAGE_TEMPLATE = os.getenv(
    "SMS_ALERT_MESSAGE_TEMPLATE",
    "New YouTube job queued: {youtube_url}",
)
YOUTUBE_WATCH_PREFIX = "https://www.youtube.com/watch?v="
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = Path(os.getenv("YT_SHARE_LOG_DIR", str(PROJECT_ROOT))).resolve()
LOG_MAX_BYTES = int(os.getenv("YT_SHARE_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("YT_SHARE_LOG_BACKUP_COUNT", "3"))


def configure_service_logger(name: str, filename: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / filename
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not any(getattr(handler, "baseFilename", None) == str(log_path) for handler in logger.handlers):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        logger.addHandler(handler)

    return logger


backend_logger = configure_service_logger("yt-share.backend", "backend.log")
frontend_logger = configure_service_logger("yt-share.frontend", "frontend.log")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})
app.logger.handlers.extend(backend_logger.handlers)
app.logger.setLevel(logging.INFO)

YOUTUBE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{11}$")

backend_logger.info(
    "Backend starting host=%s port=%s debug=%s allowed_origins=%s mqtt=%s:%s topic=%s",
    HOST,
    PORT,
    DEBUG,
    ALLOWED_ORIGINS,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
)


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
    backend_logger.info(
        "Publishing video_id=%s source=%s sender=%s to mqtt=%s:%s topic=%s",
        event.get("video_id"),
        event.get("source"),
        event.get("sender"),
        MQTT_BROKER,
        MQTT_PORT,
        MQTT_TOPIC,
    )
    publish.single(
        MQTT_TOPIC,
        payload=json.dumps(event),
        hostname=MQTT_BROKER,
        port=MQTT_PORT,
        qos=1,
    )


def send_sms_alert(event: dict) -> str:
    if not SMS_ALERT_ENABLED:
        return "disabled"
    if not FREE_MOBILE_SMS_USER or not FREE_MOBILE_SMS_PASS:
        backend_logger.warning("SMS alert skipped because Free Mobile credentials are not configured")
        return "not_configured"

    message = SMS_ALERT_MESSAGE_TEMPLATE.format(
        youtube_url=event.get("youtube_url", ""),
        video_id=event.get("video_id", ""),
        source=event.get("source", ""),
        sender=event.get("sender", ""),
    )
    query = urllib.parse.urlencode(
        {
            "user": FREE_MOBILE_SMS_USER,
            "pass": FREE_MOBILE_SMS_PASS,
            "msg": message,
        }
    )
    request_url = f"https://smsapi.free-mobile.fr/sendmsg?{query}"
    request_obj = urllib.request.Request(
        request_url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    with urllib.request.urlopen(request_obj, timeout=SMS_ALERT_TIMEOUT_SECONDS) as response:
        body = response.read(500).decode("utf-8", errors="replace")
        if response.status >= 400:
            raise RuntimeError(f"Free Mobile SMS returned HTTP {response.status}: {body}")

    backend_logger.info("SMS alert sent for video_id=%s", event.get("video_id"))
    return "sent"


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
    try:
        publish_event(event)
    except Exception:
        backend_logger.exception(
            "Failed to publish video_id=%s to mqtt=%s:%s topic=%s",
            video_id,
            MQTT_BROKER,
            MQTT_PORT,
            MQTT_TOPIC,
        )
        return {"ok": False, "error": "mqtt_publish_failed"}, 502

    try:
        sms_alert = send_sms_alert(event)
    except Exception:
        backend_logger.exception("Failed to send SMS alert for video_id=%s", video_id)
        sms_alert = "failed"

    return {
        "status": "queued",
        "youtube_url": cleaned_url,
        "sms_alert": sms_alert,
    }, 200


def client_value(data: dict, key: str, max_len: int = 500) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    return str(value)[:max_len]


@app.before_request
def log_request_start():
    request._yt_share_start_time = time.perf_counter()


@app.after_request
def log_request_end(response):
    elapsed_ms = (time.perf_counter() - getattr(request, "_yt_share_start_time", time.perf_counter())) * 1000
    backend_logger.info(
        "%s %s status=%s elapsed_ms=%.1f origin=%s remote=%s ua=%s",
        request.method,
        request.path,
        response.status_code,
        elapsed_ms,
        request.headers.get("Origin", ""),
        request.remote_addr,
        request.headers.get("User-Agent", "")[:200],
    )
    return response


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


@app.post("/client-log")
def client_log():
    data = request.get_json(silent=True) or {}
    frontend_logger.info(
        "event=%s page=%s origin=%s api_base=%s online=%s video_id=%s status=%s error=%s:%s ua=%s",
        client_value(data, "event", 80),
        client_value(data, "page", 300),
        client_value(data, "origin", 200),
        client_value(data, "apiBaseUrl", 200),
        client_value(data, "online", 20),
        client_value(data, "videoId", 20),
        client_value(data, "status", 20),
        client_value(data, "errorName", 120),
        client_value(data, "errorMessage", 500),
        client_value(data, "userAgent", 300),
    )
    return jsonify({"ok": True}), 200


@app.post("/youtube")
def youtube():
    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key != API_KEY:
        backend_logger.warning(
            "Rejected /youtube request with invalid API key origin=%s remote=%s",
            request.headers.get("Origin", ""),
            request.remote_addr,
        )
        return jsonify({"detail": "Invalid API key"}), 401

    data = request.get_json(silent=True) or {}
    url = normalize_url(data.get("youtube_url", ""))

    body, status = create_video_submission(url, "pwa_youtube", "anonymous")
    backend_logger.info(
        "YouTube submission status=%s ok=%s error=%s url_present=%s",
        status,
        status < 400,
        body.get("error", ""),
        bool(url),
    )
    return jsonify(body), status


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
