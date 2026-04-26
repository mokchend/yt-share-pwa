// Si config.js ne charge pas (cache SW, 404), ne pas retomber sur localhost en HTTPS.
const DEFAULT_DEV_API = "http://127.0.0.1:5000";
const DEFAULT_PRODUCTION_API = "https://yt-share-pwa-api.onrender.com";

function resolveApiBaseUrl() {
  const raw = window.APP_CONFIG?.API_BASE_URL;
  if (typeof raw === "string" && raw.trim()) {
    return raw.trim().replace(/\/$/, "");
  }
  if (window.location.protocol === "https:") {
    return DEFAULT_PRODUCTION_API;
  }
  return DEFAULT_DEV_API;
}

const API_BASE_URL = resolveApiBaseUrl();

function resolveApiKey() {
  const raw = window.APP_CONFIG?.API_KEY;
  if (typeof raw === "string" && raw.trim()) {
    return raw.trim();
  }
  return "";
}

function buildYoutubeSubmitHeaders() {
  const headers = { "Content-Type": "application/json" };
  const key = resolveApiKey();
  if (key) {
    headers["X-API-Key"] = key;
  }
  return headers;
}

function connectionErrorMessage() {
  if (window.location.protocol !== "https:") {
    return "❌ Impossible de joindre le serveur";
  }
  try {
    const u = new URL(API_BASE_URL, window.location.href);
    if (u.protocol === "http:" && (u.hostname === "localhost" || u.hostname === "127.0.0.1")) {
      return "❌ L’API pointe encore vers localhost en HTTP. Depuis cette page (HTTPS), le navigateur bloque l’appel. Mets l’URL HTTPS de ton backend dans config.js (voir config.example.js), republie, puis réessaie.";
    }
  } catch {
    // ignore
  }
  return "❌ Impossible de joindre le serveur";
}

const form = document.getElementById("submit-form");
const urlInput = document.getElementById("url");
const statusBox = document.getElementById("status");
const submitButton = document.getElementById("submit-button");
const pasteButton = document.getElementById("paste-button");

function showStatus(message, type = "info") {
  statusBox.textContent = message;
  statusBox.className = `status ${type}`;
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "⏳ Envoi..." : "📥 Envoyer";
}

async function readSubmitResponseBody(response) {
  const trimmed = (await response.text()).trim();
  if (!trimmed) {
    return {};
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function formatSubmitErrorMessage(data, response) {
  if (data === null) {
    return (
      `❌ Réponse serveur invalide (HTTP ${response.status}). ` +
      "Souvent une erreur côté API (page HTML au lieu de JSON) : vérifie les logs du backend et redéploie si besoin."
    );
  }
  if (data.error === "invalid_youtube_url") {
    return "❌ Lien YouTube invalide";
  }
  if (typeof data.detail === "string" && data.detail.trim()) {
    return `❌ ${data.detail.trim()}`;
  }
  if (typeof data.message === "string" && data.message.trim()) {
    return `❌ ${data.message.trim()}`;
  }
  return "❌ Erreur pendant l'envoi";
}

async function submitUrl(url) {
  setLoading(true);
  showStatus("Préparation de l'envoi...", "info");

  try {
    const response = await fetch(`${API_BASE_URL}/youtube`, {
      method: "POST",
      headers: buildYoutubeSubmitHeaders(),
      body: JSON.stringify({ youtube_url: url })
    });

    const data = await readSubmitResponseBody(response);
    if (data === null) {
      showStatus(formatSubmitErrorMessage(data, response), "error");
      return;
    }

    if (!response.ok) {
      showStatus(formatSubmitErrorMessage(data, response), "error");
      return;
    }

    if (data.status === "duplicate") {
      showStatus("⚠️ Cette vidéo a déjà été envoyée", "warning");
      return;
    }

    showStatus("✅ Vidéo ajoutée avec succès", "success");
    form.reset();
  } catch (error) {
    showStatus(connectionErrorMessage(), "error");
  } finally {
    setLoading(false);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) {
    showStatus("❌ Merci de coller un lien", "error");
    return;
  }
  await submitUrl(url);
});

pasteButton?.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    urlInput.value = text || "";
    if (text) {
      showStatus("📋 Lien collé", "info");
    }
  } catch {
    showStatus("❌ Presse-papiers non accessible", "error");
  }
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      await navigator.serviceWorker.register("./service-worker.js");
    } catch (error) {
      console.error("Service worker registration failed", error);
    }
  });
}
