// Copie ce fichier vers config.js et mets l’URL réelle du backend.
// Sur GitHub Pages (HTTPS), l’URL doit être en https://. Ici, on utilise le DNS Cloudflare.
// L’appel d’envoi est POST {API_BASE_URL}/youtube avec le corps { "youtube_url": "..." } et l’en-tête X-API-Key.
window.APP_CONFIG = {
  API_BASE_URL: "https://api.angkorvibe.com",
  API_KEY: "your-secret-key"
};
