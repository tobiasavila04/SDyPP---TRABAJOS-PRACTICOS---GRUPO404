# SD2026-GRUPO404

REST API built with FastAPI and Python, with CI pipeline via GitHub Actions.

## Requirements

- Python 3.11+

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

API available at `http://localhost:8000` — interactive docs at `http://localhost:8000/docs`.

## Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/health` | Health check |
| GET | `/items` | List all items |
| GET | `/items/{id}` | Get item by ID |
| POST | `/items` | Create item |
| DELETE | `/items/{id}` | Delete item |

## Development

```bash
pytest tests/ -v        # run tests
ruff check .            # lint
ruff format .           # format
```

## CI

GitHub Actions runs on every push to `main`/`develop` and on pull requests to `main`:

1. Lint — `ruff check`
2. Format check — `ruff format --check`
3. Tests — `pytest`
