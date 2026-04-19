const API_BASE_URL = window.APP_CONFIG?.API_BASE_URL || "http://127.0.0.1:5000";

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

async function submitUrl(url, source = "manual") {
  setLoading(true);
  showStatus("Préparation de l'envoi...", "info");

  try {
    const response = await fetch(`${API_BASE_URL}/submit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ url, source })
    });

    const data = await response.json();

    if (!response.ok) {
      const errorMessage = data.error === "invalid_youtube_url"
        ? "❌ Lien YouTube invalide"
        : "❌ Erreur pendant l'envoi";
      showStatus(errorMessage, "error");
      return;
    }

    if (data.status === "duplicate") {
      showStatus("⚠️ Cette vidéo a déjà été envoyée", "warning");
      return;
    }

    showStatus("✅ Vidéo ajoutée avec succès", "success");
    form.reset();
  } catch (error) {
    showStatus("❌ Impossible de joindre le serveur", "error");
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
  await submitUrl(url, "manual_form");
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
