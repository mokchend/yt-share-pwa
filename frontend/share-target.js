const API_BASE_URL = window.APP_CONFIG?.API_BASE_URL || "http://127.0.0.1:5000";

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

function getSharedUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("url") || params.get("text") || "";
}

async function submitSharedUrl(url) {
  try {
    const response = await fetch(`${API_BASE_URL}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, source: "pwa_share" })
    });
    const data = await response.json();

    if (!response.ok) {
      showStatus("❌ Lien invalide", "error");
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
