const DEFAULT_DEV_API = "http://127.0.0.1:5000";
const DEFAULT_PRODUCTION_API = "https://api.angkorvibe.com";
const LANGUAGE_STORAGE_KEY = "ytCollectorLanguage";
const YOUTUBE_WATCH_PREFIX = "https://www.youtube.com/watch?v=";
const YOUTUBE_VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;

const TRANSLATIONS = {
  en: {
    shareTitle: "Receiving share",
    shareSubtitle: "Processing the YouTube link...",
    statusPreparing: "Preparing to send...",
    statusSuccess: "✅ Video added successfully",
    backHome: "Back to home",
    errorConnection: "❌ Unable to reach the server",
    errorHttpLocalhost:
      "❌ The API is still pointing to localhost over HTTP. From this HTTPS page, the browser blocks the request. Put your backend HTTPS URL in config.js, republish, then try again.",
    errorInvalidResponse:
      "❌ Invalid server response (HTTP {status}). Check backend logs and redeploy if needed.",
    errorInvalidUrl: "❌ Invalid YouTube link",
    errorInvalidApiKey: "❌ Invalid API key",
    errorInvalidLink: "❌ Invalid link",
    errorNoLink: "❌ No link received"
  },
  fr: {
    shareTitle: "Réception du partage",
    shareSubtitle: "Traitement du lien YouTube...",
    statusPreparing: "Préparation de l'envoi...",
    statusSuccess: "✅ Vidéo ajoutée avec succès",
    backHome: "Retour à l'accueil",
    errorConnection: "❌ Impossible de joindre le serveur",
    errorHttpLocalhost:
      "❌ L’API pointe encore vers localhost en HTTP. Depuis cette page (HTTPS), le navigateur bloque l’appel. Mets l’URL HTTPS de ton backend dans config.js, republie, puis réessaie.",
    errorInvalidResponse:
      "❌ Réponse serveur invalide (HTTP {status}). Vérifie les logs du backend et redéploie si besoin.",
    errorInvalidUrl: "❌ Lien YouTube invalide",
    errorInvalidApiKey: "❌ Clé API invalide",
    errorInvalidLink: "❌ Lien invalide",
    errorNoLink: "❌ Aucun lien reçu"
  }
};

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
const clientLog = window.YT_CLIENT_LOG;
clientLog?.init(API_BASE_URL);

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

function cleanYoutubeWatchUrl(rawUrl) {
  const trimmedUrl = rawUrl.trim();
  if (!trimmedUrl.startsWith(YOUTUBE_WATCH_PREFIX)) {
    return "";
  }

  try {
    const url = new URL(trimmedUrl);
    const videoId = url.searchParams.get("v");
    if (
      url.protocol !== "https:" ||
      url.hostname !== "www.youtube.com" ||
      url.pathname !== "/watch" ||
      !YOUTUBE_VIDEO_ID_PATTERN.test(videoId || "")
    ) {
      return "";
    }
    return `${YOUTUBE_WATCH_PREFIX}${videoId}`;
  } catch {
    return "";
  }
}

function getYoutubeVideoId(url) {
  try {
    return new URL(url).searchParams.get("v") || "";
  } catch {
    return "";
  }
}

function connectionErrorMessage() {
  if (window.location.protocol !== "https:") {
    return t("errorConnection");
  }
  try {
    const u = new URL(API_BASE_URL, window.location.href);
    if (u.protocol === "http:" && (u.hostname === "localhost" || u.hostname === "127.0.0.1")) {
      return t("errorHttpLocalhost");
    }
  } catch {
    // ignore
  }
  return t("errorConnection");
}

const statusBox = document.getElementById("status");
let currentLanguage = resolveLanguage();

function resolveLanguage() {
  const savedLanguage = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  return savedLanguage === "en" ? "en" : "fr";
}

function t(key, values = {}) {
  const template = TRANSLATIONS[currentLanguage][key] || TRANSLATIONS.fr[key] || key;
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replace(`{${name}}`, String(value)),
    template
  );
}

function applyTranslations() {
  document.documentElement.lang = currentLanguage;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-language]").forEach((button) => {
    const isActive = button.dataset.language === currentLanguage;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function setLanguage(language) {
  currentLanguage = language === "en" ? "en" : "fr";
  localStorage.setItem(LANGUAGE_STORAGE_KEY, currentLanguage);
  applyTranslations();
}

function initLanguageSwitcher() {
  document.querySelectorAll("[data-language]").forEach((button) => {
    button.addEventListener("click", () => setLanguage(button.dataset.language));
  });
  applyTranslations();
}

function showStatus(message, type = "info") {
  statusBox.removeAttribute("data-i18n");
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
    return t("errorInvalidResponse", { status: response.status });
  }
  if (data.error === "invalid_youtube_url") {
    return t("errorInvalidUrl");
  }
  if (typeof data.detail === "string" && data.detail.trim()) {
    const detail = data.detail.trim();
    return detail === "Invalid API key" ? t("errorInvalidApiKey") : `❌ ${detail}`;
  }
  if (typeof data.message === "string" && data.message.trim()) {
    return `❌ ${data.message.trim()}`;
  }
  return t("errorInvalidLink");
}

async function submitSharedUrl(url) {
  const cleanedUrl = cleanYoutubeWatchUrl(url);
  if (!cleanedUrl) {
    clientLog?.write("share_invalid_url", {
      receivedLength: String(url || "").length
    });
    showStatus(t("errorInvalidUrl"), "error");
    return;
  }

  clientLog?.write("share_submit_start", {
    videoId: getYoutubeVideoId(cleanedUrl)
  });

  try {
    const response = await fetch(`${API_BASE_URL}/youtube`, {
      method: "POST",
      headers: buildYoutubeSubmitHeaders(),
      body: JSON.stringify({ youtube_url: cleanedUrl })
    });
    clientLog?.write("share_submit_response", {
      videoId: getYoutubeVideoId(cleanedUrl),
      status: response.status,
      ok: response.ok,
      contentType: response.headers.get("content-type") || ""
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

    showStatus(t("statusSuccess"), "success");
  } catch (error) {
    clientLog?.write("share_fetch_error", {
      videoId: getYoutubeVideoId(cleanedUrl),
      errorName: error?.name || "",
      errorMessage: error?.message || ""
    });
    showStatus(connectionErrorMessage(), "error");
  }
}

(async function boot() {
  initLanguageSwitcher();

  const sharedUrl = getSharedUrl();
  if (!sharedUrl) {
    clientLog?.write("share_no_link");
    showStatus(t("errorNoLink"), "error");
    return;
  }

  await submitSharedUrl(sharedUrl);
})();
