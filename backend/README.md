# Backend

FastAPI service. Full guide: the "Implementation" section of the root README.

```bash
python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload                       # API docs: http://localhost:8000/docs
python -m pytest -q                                 # tests
python -m app.pipeline.build                        # rebuild data/processed/RW from data/raw/RW
```

Layout: `app/pipeline` (ingestion, cleaning, survey join, build), `app/services` (market gap, data cache,
map layers, cell evidence, locations, reports, assistant), `app/api` (routers; `api/ml` holds model
training), `app/schemas` (Pydantic), `scripts/` (data refresh), `tests/`.

Night-light ingest: `powershell -ExecutionPolicy Bypass -File scripts/schedule/weekly_nightlights.ps1`
(needs `NASA_EARTHDATA_TOKEN`). The API reads `data/processed/RW/cells_with_nightlights.csv` through the
build pipeline and never calls NASA.
