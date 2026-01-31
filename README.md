# Next Caltrain?

Caltrain next departures — pick From/To stations and direction, see trains and travel time.

## Project layout

- **backend/** — FastAPI API only. All routes under `/api` (e.g. `/api/stops`, `/api/next_trains`). Credentials in `backend/.env` (local dev) or root `.env` (Docker).
- **frontend/** — Static HTML/CSS/JS. Flat layout: `index.html`, `css/style.css`, `js/app.js`. Served by nginx (or any static server) in production.
- **nginx/** — nginx config for Docker (HTTP, HTTPS templates, Let's Encrypt).
- **docs/** — Reference materials (e.g. 511 API spec).

## Run locally

### Backend (API)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # add your 511 API key (https://511.org/open-data/token)
uvicorn server:app --reload
# API: http://127.0.0.1:8000/api/stops, /api/next_trains, etc.
```

### Frontend (static)

Serve the `frontend/` directory so the app can call the API on the same origin (or configure CORS). For example:

```bash
# From repo root, serve frontend and proxy /api to backend, or:
cd frontend
python3 -m http.server 8080
# Then open http://127.0.0.1:8080 — API calls go to /api/* (same host); run backend on 8000 and use nginx to serve frontend + proxy /api, or run both and set a proxy.
```

For a single command: run the backend, then use nginx (or a simple proxy) to serve `frontend/` and proxy `/api` to `http://127.0.0.1:8000`. Or run backend and frontend on the same port by having the backend serve the frontend in dev (see below).

**Quick dev (backend serves frontend):** You can temporarily mount the frontend in the backend for local dev (optional). By default the repo is set up for full separation: nginx serves `frontend/` and proxies `/api` to the backend.

### CLI (next trains at a stop)

From repo root (so `backend` is on the path):

```bash
pip install -r backend/requirements.txt
# Put API_KEY in backend/.env
python start.py [stop] [direction]
# e.g. python start.py 70031
#      python start.py "San Francisco" southbound
```

## Deploy

### Docker (nginx + backend)

```bash
cp .env.example .env   # add API_KEY, and DOMAIN/EMAIL for HTTPS
docker compose up -d
# App at http://localhost
```

The backend reads `API_KEY` from root `.env` (via `env_file` in docker-compose).

### Domain + HTTPS (production)

1. Copy `.env.example` to `.env` and set `DOMAIN`, `EMAIL`, and `API_KEY`.
2. Point your domain's DNS A record to this server.
3. Run the one-time setup:
   ```bash
   chmod +x scripts/init-letsencrypt.sh
   ./scripts/init-letsencrypt.sh
   ```
4. Visit `https://your-domain.com`.

**Automatic config:** nginx auto-generates the HTTPS config from the template when certs exist, so `git pull` + `docker compose up` keeps HTTPS working without manual steps.

### GitHub Actions auto-deploy

On push to `main`, a workflow SSHs into your server, runs `git pull`, then `docker compose up -d --build`.

1. Add these **GitHub repository secrets** (Settings → Secrets and variables → Actions):
   - **SERVER_HOST** — Server IP or hostname (e.g. `138.68.43.227`)
   - **SERVER_USER** — SSH user (e.g. `root`)
   - **SSH_PRIVATE_KEY** — Private key for SSH (the full PEM content, no passphrase)
   - **SERVER_PATH** — Path to the app on the server (e.g. `/root/app`)

2. Ensure the server has the repo cloned and the deploy key (or your SSH key) can `git pull` from the remote.

### Request logging

nginx logs requests to stdout. View logs with:

```bash
docker compose logs -f nginx
```

Log format: `$remote_addr - [$time_local] "$request" $status ... rt=$request_time`.

### Other platforms

- **Backend:** Use the `Procfile` (e.g. Render, Railway): `cd backend && uvicorn server:app --host 0.0.0.0 --port $PORT`. Set `API_KEY` in the host’s environment (or use `backend/.env` where supported).
- **Frontend:** Serve the `frontend/` directory and proxy `/api` to your backend URL.

## API docs

With the app running, FastAPI's interactive docs are available at:

- **Swagger UI:** `/api/docs` — try endpoints in the browser
- **ReDoc:** `/api/redoc` — alternative docs view

(e.g. https://nextcaltrain.live/api/docs)

## API base path

All API routes use the `/api` prefix so nginx can proxy `location /api { ... }` to the backend.
