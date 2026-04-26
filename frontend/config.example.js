// Copie ce fichier vers config.js et mets l’URL réelle du backend.
// Sur GitHub Pages (HTTPS), l’URL doit être en https:// (ex. tunnel ou Render), pas http://127.0.0.1.
// L’appel d’envoi est POST {API_BASE_URL}/youtube avec le corps { "youtube_url": "..." } et l’en-tête X-API-Key.
window.APP_CONFIG = {
  API_BASE_URL: "https://your-backend.example.com",
  API_KEY: "your-secret-key"
};
