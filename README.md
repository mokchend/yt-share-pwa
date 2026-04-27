# YouTube Share Collector PWA

Projet complet pour collecter des liens YouTube depuis le menu **Partager** d'un téléphone, supprimer les doublons, et envoyer une notification email côté serveur.

## Ce que contient le projet

- `frontend/` : PWA installable
- `backend/` : API Flask + SQLite + SMTP optionnel
- `render.yaml` : configuration de déploiement Render pour le backend
- `.nojekyll` : utile si tu publies le frontend sur GitHub Pages depuis la racine d'un dépôt

## Fonctionnalités

- PWA installable
- Support `share_target` pour recevoir un lien depuis le menu Partager
- Fallback manuel `coller + envoyer`
- Déduplication par `video_id`
- Stockage SQLite
- Email automatique optionnel via SMTP
- UI mobile très simple

## Important avant la mise en prod

Le frontend peut être déployé facilement sur GitHub Pages car il est 100% statique. GitHub Pages publie les fichiers statiques poussés dans un dépôt ou dans un dossier `/docs`. citeturn721182search1turn721182search7

Le backend Flask peut être déployé sur Render. En revanche, le système de fichiers Render est éphémère par défaut. Sans disque persistant, ton fichier SQLite sera perdu à chaque redéploiement ou redémarrage. Les disques persistants Render sont réservés aux services payants. citeturn721182search0turn721182search6

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
- SQLite pour test ou démo

### Option C — plus sérieuse dans le cloud
- Frontend sur GitHub Pages
- Backend sur Render
- Base Postgres managée au lieu de SQLite

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
- `SMTP_ENABLED=true` si tu veux les emails
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_TO`, `EMAIL_FROM`

### CORS
Ne laisse pas `ALLOWED_ORIGINS=*` en prod. Mets l'URL exacte du frontend.

## Installation utilisateur

### Android
1. ouvrir l'URL de la PWA dans Chrome
2. installer l'application
3. depuis YouTube → Partager → choisir **YT Collector**

### iPhone
1. ouvrir l'URL dans Safari
2. Partager → Ajouter à l'écran d'accueil
3. ouvrir l'app depuis l'écran d'accueil
4. si le partage direct n'apparaît pas, utiliser le fallback manuel coller/envoyer

Le `share_target` permet à une PWA installée de devenir une cible dans le menu de partage système. citeturn721182search2

## Endpoints

- `POST https://api.angkorvibe.com/youtube`

## Payload `/youtube`

```json
{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

L'appel doit inclure l'en-tête `X-API-Key` configuré dans `config.js`.

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

Avec la version actuelle en SQLite :
- local = très bien
- démo = très bien
- production gratuite sur Render = pas fiable dans la durée à cause du filesystem éphémère. citeturn721182search0turn721182search6

## Évolution recommandée

Quand ton MVP marche, passe le backend sur :
- Postgres
- ou Supabase / Neon / autre DB externe

Ainsi tu gardes le même frontend PWA, et tu rends seulement le backend plus robuste.
