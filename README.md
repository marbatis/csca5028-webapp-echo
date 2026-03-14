# The '87 Land Cruiser Finder - Web Application

Production-ready Flask web app for the CSCA 5028 final project.

## Features

- Reporting UI backed by persisted inventory data.
- REST API endpoints:
  - `GET /api/v1/inventory`
  - `GET /api/v1/summary`
- Monitoring and metrics endpoints:
  - `GET /health`
  - `GET /metrics`
- Interaction demo (`POST /echo`) for request/response behavior validation.
- SQLite persistence for local and Heroku demo environments.

## Architecture role

- This app is the stateless web process.
- Data collection and analysis are independent processes in the collector repository.
- The app reads persisted records and exposes filtered reporting and rollups.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flask --app src.app run
```

Open: `http://127.0.0.1:5000`

## Run tests

```bash
pytest -q
```

## Continuous integration and delivery

- CI workflow: `.github/workflows/ci.yml`
- CD workflow: `.github/workflows/cd.yml`

To enable CD, configure repository secrets:

- `HEROKU_API_KEY`
- `HEROKU_APP_NAME`
- `HEROKU_EMAIL`

## Deploy to Heroku (CLI)

```bash
heroku login

# Deploy (optionally pass preferred app name)
./deploy_heroku.sh csca5028-echo-yourname
```

The script outputs the public URL when deployment completes.
