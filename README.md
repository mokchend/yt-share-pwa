# YouTube Share Collector PWA

Projet complet pour collecter des liens YouTube depuis le menu **Partager** d'un téléphone et les envoyer dans une file MQTT pour le worker karaoke.

## Ce que contient le projet

- `frontend/` : PWA installable
- `backend/` : API Flask qui publie les jobs dans MQTT
- `render.yaml` : configuration de déploiement Render pour le backend
- `.nojekyll` : utile si tu publies le frontend sur GitHub Pages depuis la racine d'un dépôt

## Fonctionnalités

- PWA installable
- Support `share_target` pour recevoir un lien depuis le menu Partager
- Fallback manuel `coller + envoyer`
- Validation du lien YouTube
- Publication MQTT vers le topic `youtube/jobs`
- Protection simple avec l'en-tête `X-API-Key`
- UI mobile très simple

## Important avant la mise en prod

Le frontend peut être déployé facilement sur GitHub Pages car il est 100% statique. GitHub Pages publie les fichiers statiques poussés dans un dépôt ou dans un dossier `/docs`. citeturn721182search1turn721182search7

Le backend ne stocke plus les vidéos dans SQLite et n'envoie plus d'email SMTP. Il publie seulement un message MQTT, puis le worker local traite le téléchargement et la pipeline karaoke.

## Recommandation d'hébergement

### Option A — actuelle avec Cloudflare Tunnel
- Frontend sur GitHub Pages
- Backend FastAPI lancé sur ton PC
- Cloudflare Tunnel expose le backend local avec ton DNS : `https://api.angkorvibe.com`
- La PWA appelle `POST https://api.angkorvibe.com/youtube`

Avec cette option, tu n'as plus besoin de `xxxapi.onrender.com`. Render servait avant à donner une URL publique HTTPS au backend, parce qu'un téléphone ou une PWA hébergée sur GitHub Pages ne peut pas appeler `http://127.0.0.1` sur ton PC. Maintenant, Cloudflare Tunnel fait ce rôle : il reçoit les appels publics sur `https://api.angkorvibe.com`, puis les route vers ton backend local.

Flux actuel :

```text
Phone / PWA
  -> https://api.angkorvibe.com/youtube
  -> Cloudflare Tunnel
  -> backend local
  -> worker / pipeline karaoke
```

### Option B — simple pour tester dans le cloud
- Frontend sur GitHub Pages
- Backend sur Render
- Broker MQTT accessible depuis le backend

### Option C — plus sérieuse dans le cloud
- Frontend sur GitHub Pages
- Backend sur Render
- Broker MQTT managé ou sécurisé

## Développement local

### 1) Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python app.py
```

API par défaut : `http://127.0.0.1:5000`

### 2) Frontend

```bash
cd frontend
copy config.example.js config.js
python -m http.server 8080
```

Puis ouvre `http://127.0.0.1:8080`.

## Configuration du frontend

Le frontend lit l'URL du backend depuis `frontend/config.js`.
En production, utilise ton DNS Cloudflare comme URL de base : `https://api.angkorvibe.com`.

### Pour le local

```js
window.APP_CONFIG = {
  API_BASE_URL: "http://127.0.0.1:5000"
};
```

### Pour la production

```js
window.APP_CONFIG = {
  API_BASE_URL: "https://api.angkorvibe.com",
  API_KEY: "change-this-secret"
};
```

## Déploiement du frontend sur GitHub Pages

### Option la plus simple
1. crée un dépôt GitHub
2. pousse le contenu du dossier `frontend/` dans la racine du dépôt **ou** dans un dossier `docs/`
3. dans les paramètres GitHub Pages, choisis la branche et le dossier publiés
4. attends la publication

GitHub Pages permet précisément de publier soit depuis la racine d'une branche, soit depuis un dossier `/docs`. citeturn721182search7

### Fichiers importants côté frontend
- `manifest.webmanifest`
- `service-worker.js`
- `config.js`
- `share-target.html`

Une PWA doit être servie en HTTPS, ou en localhost/127.0.0.1 pour le développement local, pour être installable. citeturn721182search5turn721182search19

## Déploiement du backend sur Render

### Avec le fichier `render.yaml`
1. crée un dépôt GitHub avec tout le projet
2. connecte le dépôt à Render
3. crée un nouveau Web Service Blueprint ou importe le dépôt
4. Render détectera `render.yaml`
5. renseigne les variables d'environnement manquantes

### Variables d'environnement utiles
- `ALLOWED_ORIGINS=https://ton-site.github.io`
- `YOUTUBE_COLLECTOR_API_KEY=change-this-secret`
- `MQTT_BROKER=localhost`
- `MQTT_PORT=1883`
- `MQTT_TOPIC=youtube/jobs`

### CORS
Ne laisse pas `ALLOWED_ORIGINS=*` en prod. Mets l'URL exacte du frontend.

## Installation utilisateur

Ouvre l'URL publique de la PWA depuis ton téléphone. Si le frontend est publié avec GitHub Pages, utilise l'URL GitHub Pages du dossier `docs/`. L'API appelée par l'app reste `https://api.angkorvibe.com/youtube`.

### Android

1. Ouvre l'URL de la PWA dans **Chrome** sur Android : https://mokchend.github.io/yt-share-pwa/
2. Attends que la page charge complètement.
3. Appuie sur le menu Chrome `⋮`.
4. Choisis **Installer l'application** ou **Ajouter à l'écran d'accueil**.
5. Confirme avec **Installer**.
6. Ouvre l'app **YT Collector** depuis l'écran d'accueil.
7. Pour envoyer une vidéo : ouvre YouTube → vidéo → **Partager** → choisis **YT Collector**.

Si **YT Collector** n'apparaît pas dans le menu de partage, ouvre d'abord l'app une fois depuis l'écran d'accueil, puis réessaie depuis YouTube.

### iPhone

1. Ouvre l'URL de la PWA dans **Safari** sur iPhone.
2. Appuie sur le bouton **Partager** de Safari.
3. Choisis **Ajouter à l'écran d'accueil**.
4. Confirme avec **Ajouter**.
5. Ouvre **YT Collector** depuis l'écran d'accueil.
6. Si le partage direct depuis YouTube n'apparaît pas, copie le lien YouTube puis colle-le dans l'app avec le bouton **Coller depuis le presse-papiers**.

### Utilisation après installation

L'app accepte seulement les liens qui commencent par :

```text
https://www.youtube.com/watch?v=
```

Si YouTube ajoute des paramètres comme `list` ou `start_radio`, l'app nettoie le lien avant l'envoi.

Exemple :

```text
https://www.youtube.com/watch?v=6_pcEt9mPTc&list=RD6_pcEt9mPTc&start_radio=1
-> https://www.youtube.com/watch?v=6_pcEt9mPTc
```

Après l'envoi réussi, tu dois voir le message **Vidéo ajoutée avec succès** ou **Video added successfully** selon la langue sélectionnée.

Le `share_target` permet à une PWA installée de devenir une cible dans le menu de partage système. citeturn721182search2

## Endpoints

- `GET /health`
- `POST https://api.angkorvibe.com/youtube`
- `POST https://api.angkorvibe.com/client-log` (diagnostics frontend)

## Logs locaux

Les services écrivent maintenant des logs dans le dossier du projet `C:\dev\khmer_karaoke\yt-share-pwa` par défaut :

- `backend.log` : démarrage Flask, requêtes HTTP, clé API invalide, erreurs MQTT
- `frontend.log` : diagnostics envoyés par la PWA (`submit_start`, `submit_response`, `submit_fetch_error`, etc.)
- `pipeline.log` : sortie console de `pipeline/karaoke_pipeline.py`

Tu peux changer le dossier avec `YT_SHARE_LOG_DIR`. Exemple dans `backend/.env` :

```text
YT_SHARE_LOG_DIR=C:\dev\khmer_karaoke\yt-share-pwa
```

Important : si l'erreur est **Unable to reach the server** et que `frontend.log` ne reçoit rien au moment du test, cela veut dire que le navigateur n'arrive probablement pas à joindre l'API du tout (DNS, Cloudflare Tunnel, CORS, backend arrêté, mauvais `API_BASE_URL`).

## Payload `/youtube`

Le lien doit commencer par `https://www.youtube.com/watch?v=`. Si l'utilisateur colle un lien avec d'autres paramètres YouTube, l'app et le backend gardent seulement le paramètre `v`.

Exemple nettoyé :

```text
https://www.youtube.com/watch?v=6_pcEt9mPTc&list=RD6_pcEt9mPTc&start_radio=1
-> https://www.youtube.com/watch?v=6_pcEt9mPTc
```

```json
{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

L'appel doit inclure l'en-tête `X-API-Key` configuré dans `config.js`.

Le backend publie ensuite ce message dans MQTT sur `youtube/jobs` :

```json
{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "video_id": "dQw4w9WgXcQ",
  "source": "pwa_youtube",
  "sender": "anonymous"
}
```

## Réponse

```json
{
  "status": "queued",
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

ou

```json
{
  "detail": "Invalid API key"
}
```

## Limite importante

Le backend doit pouvoir joindre le broker MQTT configuré. Dans ton setup Cloudflare Tunnel actuel, le backend tourne sur ton PC et peut publier sur `localhost:1883`, comme dans `khmer_karaoke_ai/api/mqtt_client.py`.
