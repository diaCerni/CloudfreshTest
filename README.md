# Enterprise Policy Search Agent

**Formal documentation (Word and PDF):** see the [`docs/`](docs/) folder — `Enterprise_Policy_Search_Agent.docx` and `Enterprise_Policy_Search_Agent.pdf`. Regenerate with `python docs/generate_documentation.py` (requires `python-docx` and `reportlab`).

A small **FastAPI** web app that searches and answers questions over your indexed content using **Google Cloud Vertex AI Search** (Discovery Engine). An optional **ingestion** pipeline pulls files from **Google Drive**, stores them in **Cloud Storage**, and uses **Document AI** OCR when PDFs look scanned.

## What it does

- **Search** (`POST /api/search`) — Returns ranked document hits with snippets and extractive segments from your Vertex AI Search app.
- **Ask** (`POST /api/ask`) — Uses conversational search with answer generation, citations mapped back to the retrieved documents, and a simple **grounding** signal (`strong` / `partial` / `weak`) based on overlap between the query and retrieved text.

The home page (`GET /`) serves a Jinja2 template with static assets for interactive use.

## Prerequisites

- Python 3.10+ recommended  
- A Google Cloud project with:
  - **Vertex AI Search** (Discovery Engine) app configured and connected to a datastore (e.g. documents in GCS).
  - APIs enabled as needed: Discovery Engine, Document AI, Storage, Drive (for ingestion).
- **Application Default Credentials** for the APIs the app calls (for example `gcloud auth application-default login` for local development, or a service account with the right roles in production).

## Configuration

Create a `.env` file in the project root (same level as this README):

| Variable       | Description |
|----------------|-------------|
| `PROJECT_ID`   | GCP project ID (required). |
| `APP_ID`       | Vertex AI Search **engine** ID (required). |
| `LOCATION`     | Engine location, e.g. `global` (default) or a regional code used by your engine. |
| `PORT`         | HTTP port for the web app (default `8000`). |

`app/config.py` loads these with `python-dotenv` and validates that `PROJECT_ID` and `APP_ID` are set.

Serving configs used in code:

- Search: `.../engines/{APP_ID}/servingConfigs/default_search`
- Answers: `.../engines/{APP_ID}/servingConfigs/default_serving_config`

Rename or adjust these in `app/vertex_search.py` if your engine uses different serving config names.

## Install and run

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

From the project root:

```bash
python -m app.main
```

Or with uvicorn directly:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` (or your configured port). Health check: `GET /health`.

## API (summary)

| Method & path      | Body (JSON) | Response highlights |
|--------------------|-------------|----------------------|
| `POST /api/search` | `question`, optional `user_pseudo_id` | `{ "results": [ ... ] }` |
| `POST /api/ask`    | `question`, optional `user_pseudo_id`, `session_id` | `answer`, `citations`, `references`, `grounding_status` |

## Ingestion (optional)

Scripts under `app/ingestion/` implement a **Drive folder → GCS** flow:

1. OAuth to Drive (`credentials.json`, cached `token.json` in project root).
2. Download or export files; archive raw copies under `archive/processed/`.
3. For PDFs, **detect** image-based (scanned) vs text-based PDFs (`detect_scanned_pdf.py`).
4. Scanned PDFs: **Document AI** OCR to `.txt` in `processed/`; text PDFs and non-PDFs are uploaded as-is to `processed/`.

Constants such as folder ID, bucket name, and Document AI processor ID are defined at the top of `app/ingestion/ingest_drive_to_gcs.py` — edit them for your environment before running:

```bash
python -m app.ingestion.ingest_drive_to_gcs
```

## Project layout

```
app/
  main.py              # FastAPI routes and static/templates
  config.py            # Env-based settings
  vertex_search.py     # Discovery Engine search + answer_query
  templates/           # index.html
  static/              # CSS/JS for the UI
  ingestion/           # Drive → GCS + OCR helpers
```

## Security notes

- Do not commit `.env`, `credentials.json`, `token.json`, or service account keys.
- Treat `user_pseudo_id` and `session_id` as identifiers you control for analytics/session features in Vertex AI Search.
