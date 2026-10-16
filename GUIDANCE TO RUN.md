# How to run Solar Market Reality

Full documentation (data, method, assistant, limitations) is in the "Implementation" section of
[README.md](README.md).

```bash
# 1. Backend (Python 3.11+)
cd backend
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # optional: set ANTHROPIC_API_KEY to enable the AI assistant
uvicorn app.main:app --reload   # http://localhost:8000/docs

# 2. Frontend (Node 18+), second terminal
cd frontend
npm install
npm run dev                     # http://localhost:5173

# 3. Tests
cd backend && python -m pytest -q
cd frontend && npm test && npm run build
```

The processed real dataset is committed, so no downloads are needed to run the app. To refresh inputs,
see "Refresh and rebuild data" in the README. Docker: `docker compose up --build`.
