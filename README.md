# Wen Train? (Caltrain)

Caltrain next departures — pick a station and direction, see trains.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # add your 511 API key
uvicorn server:app --reload
# open http://127.0.0.1:8000
```

## Deploy (hosting the server)

**Netlify does not run Python servers.** It only hosts static sites and serverless functions. This app is a FastAPI server that must run continuously, so you need a platform that runs Python:

### Option A: Render (recommended, free tier)

1. Push your repo to GitHub.
2. Go to [render.com](https://render.com) → New → **Web Service**.
3. Connect the repo, choose **Python**.
4. Set:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. In **Environment**, add `API_KEY` with your 511 API key (same as in `.env`).
6. Deploy. Your site will be at `https://your-app-name.onrender.com`.

### Option B: Railway

1. Push your repo to GitHub.
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub.
3. Select the repo. Railway will detect the `Procfile` and run the server.
4. In **Variables**, add `API_KEY` with your 511 API key.
5. Deploy, then use **Generate Domain** to get a public URL.

### Option C: Netlify (frontend only) + separate API

If you want to keep using Netlify:

1. Deploy the **API** to Render or Railway (steps above) and note the URL (e.g. `https://your-api.onrender.com`).
2. Change the frontend to call that API URL instead of relative `/stops` and `/next_trains` (requires code changes to use an env/config base URL).
3. Deploy only the `static/` folder to Netlify as a static site.

For a single app, **Option A or B is simpler** — one URL for both the site and the API.

---

Observations: all southbound stops are even, all northbound stops are odd.
