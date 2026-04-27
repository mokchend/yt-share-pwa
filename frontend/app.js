// Si config.js ne charge pas (cache SW, 404), ne pas retomber sur localhost en HTTPS.
const DEFAULT_DEV_API = "http://127.0.0.1:5000";
const DEFAULT_PRODUCTION_API = "https://api.angkorvibe.com";
const LANGUAGE_STORAGE_KEY = "ytCollectorLanguage";
const YOUTUBE_WATCH_PREFIX = "https://www.youtube.com/watch?v=";
const YOUTUBE_VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;

const TRANSLATIONS = {
  en: {
    appTitle: "Send a video",
    appSubtitle: "Share a YouTube video to this app, or paste a link here.",
    youtubeLabel: "YouTube link",
    pasteButton: "📋 Paste from clipboard",
    submitButton: "📥 Send",
    submitLoading: "⏳ Sending...",
    simpleModeLabel: "Simple mode:",
    simpleModeText: "YouTube → Share → YT Collector",
    statusPreparing: "Preparing to send...",
    statusSuccess: "✅ Video added successfully",
    statusPasted: "📋 Link pasted",
    errorConnection: "❌ Unable to reach the server",
    errorHttpLocalhost:
      "❌ The API is still pointing to localhost over HTTP. From this HTTPS page, the browser blocks the request. Put your backend HTTPS URL in config.js, republish, then try again.",
    errorInvalidResponse:
      "❌ Invalid server response (HTTP {status}). This is often an API error returning HTML instead of JSON: check backend logs and redeploy if needed.",
    errorInvalidUrl: "❌ Invalid YouTube link",
    errorInvalidApiKey: "❌ Invalid API key",
    errorSend: "❌ Error while sending",
    errorMissingLink: "❌ Please paste a link",
    errorClipboard: "❌ Clipboard is not accessible"
  },
  fr: {
    appTitle: "Envoyer une vidéo",
    appSubtitle: "Partage une vidéo YouTube vers cette app, ou colle un lien ici.",
    youtubeLabel: "Lien YouTube",
    pasteButton: "📋 Coller depuis le presse-papiers",
    submitButton: "📥 Envoyer",
    submitLoading: "⏳ Envoi...",
    simpleModeLabel: "Mode simple :",
    simpleModeText: "YouTube → Partager → YT Collector",
    statusPreparing: "Préparation de l'envoi...",
    statusSuccess: "✅ Vidéo ajoutée avec succès",
    statusPasted: "📋 Lien collé",
    errorConnection: "❌ Impossible de joindre le serveur",
    errorHttpLocalhost:
      "❌ L’API pointe encore vers localhost en HTTP. Depuis cette page (HTTPS), le navigateur bloque l’appel. Mets l’URL HTTPS de ton backend dans config.js, republie, puis réessaie.",
    errorInvalidResponse:
      "❌ Réponse serveur invalide (HTTP {status}). Souvent une erreur côté API (page HTML au lieu de JSON) : vérifie les logs du backend et redéploie si besoin.",
    errorInvalidUrl: "❌ Lien YouTube invalide",
    errorInvalidApiKey: "❌ Clé API invalide",
    errorSend: "❌ Erreur pendant l'envoi",
    errorMissingLink: "❌ Merci de coller un lien",
    errorClipboard: "❌ Presse-papiers non accessible"
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

const form = document.getElementById("submit-form");
const urlInput = document.getElementById("url");
const statusBox = document.getElementById("status");
const submitButton = document.getElementById("submit-button");
const pasteButton = document.getElementById("paste-button");
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
  if (!submitButton.disabled) {
    submitButton.textContent = t("submitButton");
  }
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

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? t("submitLoading") : t("submitButton");
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
  return t("errorSend");
}

async function submitUrl(url) {
  setLoading(true);
  showStatus(t("statusPreparing"), "info");

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

    showStatus(t("statusSuccess"), "success");
    form.reset();
  } catch (error) {
    showStatus(connectionErrorMessage(), "error");
  } finally {
    setLoading(false);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = cleanYoutubeWatchUrl(urlInput.value);
  if (!url) {
    showStatus(t("errorInvalidUrl"), "error");
    return;
  }
  urlInput.value = url;
  await submitUrl(url);
});

pasteButton?.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    const cleanedUrl = cleanYoutubeWatchUrl(text || "");
    urlInput.value = cleanedUrl || text || "";
    if (cleanedUrl) {
      showStatus(t("statusPasted"), "info");
    }
  } catch {
    showStatus(t("errorClipboard"), "error");
  }
});

initLanguageSwitcher();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      await navigator.serviceWorker.register("./service-worker.js");
    } catch (error) {
      console.error("Service worker registration failed", error);
    }
  });
}
