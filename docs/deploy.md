# Deploying the live demo

Two options, both free. Streamlit Community Cloud is the fastest path to a public URL.

## Option A — Streamlit Community Cloud (recommended, ~5 minutes)

Prerequisite: the repo is pushed to GitHub (see below).

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **New app** → pick `ashmohdd/helios-cfo-digital-twin`, branch `main`.
3. Set **Main file path** to `app/streamlit_app.py`.
4. Under Advanced settings, set the Python version to 3.11.
5. Click **Deploy**.

One thing to know: the repo's `.gitignore` excludes the generated warehouse files (`data/helios.db`, `data/gold_monthly.parquet`) because they're regenerable. Streamlit Cloud won't run the Makefile for you, so pick one:

- **Simplest:** remove those two lines from `.gitignore`, run `make warehouse` locally, and commit the two data files (~10 MB total). The app boots instantly.
- **Cleaner:** add this to the top of `app/streamlit_app.py` so the app self-builds on first boot:

```python
from pathlib import Path
import subprocess
if not (Path(__file__).resolve().parents[1] / "data" / "gold_monthly.parquet").exists():
    subprocess.run(["python", "-m", "src.warehouse.build_warehouse"], check=True)
```

Your app will be live at `https://ashmohdd-helios-cfo-digital-twin.streamlit.app` (Streamlit shows the exact URL after deploy). Put that URL at the top of the README.

## Option B — Render (runs the API too)

1. Push to GitHub, then go to https://render.com → **New** → **Web Service** → connect the repo.
2. Environment: Python 3. Build command:
   `pip install -r requirements.txt && make warehouse`
3. Start command (dashboard):
   `streamlit run app/streamlit_app.py --server.port $PORT --server.address 0.0.0.0`
   Or, for the API instead:
   `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
4. Free instance type is fine. Deploy.

Note: Render free instances sleep after inactivity; first load after idle takes ~30s. Fine for a portfolio link, just mention it in the README if you use Render.

## Pushing to GitHub (exact commands)

```bash
cd helios-cfo-digital-twin
git init
git add .
git commit -m "HELIOS CFO Digital Twin: three-statement model, warehouse, ensemble forecasting, API, dashboard, automated reporting"
git branch -M main
# create the empty repo on github.com first (no README, no license), then:
git remote add origin https://github.com/ashmohdd/helios-cfo-digital-twin.git
git push -u origin main
```

The CI badge in the README goes green automatically after the first push — `.github/workflows/ci.yml` installs dependencies, rebuilds the warehouse from scratch, and runs the full test suite on every push and pull request. That green badge is itself part of the pitch: the pipeline provably runs end to end on a clean machine.
