const DEFAULT_DEV_API = "http://127.0.0.1:5000";
const DEFAULT_PRODUCTION_API = "https://api.angkorvibe.com";

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

const statusBox = document.getElementById("status");

function showStatus(message, type = "info") {
  statusBox.textContent = message;
  statusBox.className = `status ${type}`;
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

function getSharedUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("url") || params.get("text") || "";
}

function formatSubmitErrorMessage(data, response) {
  if (data === null) {
    return (
      `❌ Réponse serveur invalide (HTTP ${response.status}). ` +
      "Vérifie les logs du backend et redéploie si besoin."
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
  return "❌ Lien invalide";
}

async function submitSharedUrl(url) {
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
  } catch (error) {
    showStatus(connectionErrorMessage(), "error");
  }
}

(async function boot() {
  const sharedUrl = getSharedUrl();
  if (!sharedUrl) {
    showStatus("❌ Aucun lien reçu", "error");
    return;
  }

  await submitSharedUrl(sharedUrl);
})();
