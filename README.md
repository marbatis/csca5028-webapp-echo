# CSCA 5028 Web App Echo

Minimal Flask web app for the peer-graded assignment requirement:
- Public URL
- Takes user input
- Echoes input to screen

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flask --app src.app run
```

Open: `http://127.0.0.1:5000`

## Heroku deploy files included
- `Procfile`
- `requirements.txt`
- `.python-version`
