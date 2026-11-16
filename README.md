# Resale Radar — deploy from GitHub to Render

This repository runs **both the webpage and Python API** as one Render Web Service. Do **not** use GitHub Pages for this configuration: it cannot run Python.

## 1. Upload to GitHub
Create a new GitHub repository, select **Add file → Upload files**, and upload `index.html`, `server.py`, `README.md` and `.gitignore` into the **repository root** (not a nested folder). Commit them. Do not upload any credentials.

## 2. Deploy on Render
1. Visit https://dashboard.render.com/ and select **New → Web Service**.
2. Connect GitHub and choose the repository.
3. Select **Python** as runtime (if prompted), and an available instance type.
4. **Build command:** `echo Ready` (standard library only; no dependencies to install).
5. **Start command:** `python server.py`
6. Add environment variables:
   - `ADMIN_TOKEN`: a long, random password **you choose**, used to stop strangers from adding products.
   - `EBAY_CLIENT_ID`: optional real eBay App ID.
   - `EBAY_CLIENT_SECRET`: optional eBay secret. **Never put these in GitHub.**
7. Deploy and visit the URL Render gives you, e.g. `https://your-project.onrender.com`.

Render supplies a `PORT` environment variable; `server.py` listens on `0.0.0.0` by default so Render can reach it. The HTML fetches `/api/feed` and `/api/price` from the **same host**, so no separate frontend API URL or CORS setting is needed.

**When you add a TikTok/Instagram observation**, the page asks for your `ADMIN_TOKEN`. It remembers it in the current browser tab session. Never share this password.

## Limitations
- Google Trends RSS updates are checked at most every five minutes **while the server is active**. This is not a verified TikTok/Instagram purchase feed.
- eBay live asking prices and corresponding listing photos require working eBay production API access. Vinted completed sales and age-specific purchase data are not connected.
- The manual observations are saved to a local `signals.json`. On typical ephemeral cloud instances, **they can disappear when the service restarts or redeploys**. A persistent database is required for dependable retention.
- A free Render instance, if available, can sleep when idle and may take time to wake. A continuously active paid instance may be necessary for uptime.
- This is an initial personal-use prototype, not a production-hardened multiuser application.
