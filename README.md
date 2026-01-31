# Next Caltrain?

Caltrain next departures — pick From/To stations and direction, see trains and travel time.

## Project layout

- **backend/** — FastAPI API only. All routes under `/api` (e.g. `/api/stops`, `/api/next_trains`). Credentials in `backend/.env` (copy `backend/.env.example` to `backend/.env` and add your 511 API key; if you had a root `.env`, move it to `backend/.env`).
- **frontend/** — Static HTML/CSS/JS. Flat layout: `index.html`, `css/style.css`, `js/app.js`. Served by nginx (or any static server) in production.
- **infra/** — (you add) Dockerfile, nginx config for hosting and deployment.

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

- **Backend:** Use the `Procfile` (e.g. Render, Railway): `cd backend && uvicorn server:app --host 0.0.0.0 --port $PORT`. Set `API_KEY` in the host’s environment (or use `backend/.env` where supported).
- **Frontend:** Serve the `frontend/` directory and proxy `/api` to your backend URL. Add `infra/` with Dockerfile and nginx config as needed.

## API base path

All API routes use the `/api` prefix so nginx can proxy `location /api { ... }` to the backend.
