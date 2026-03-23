from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import PORT
from app.vertex_search import answer_question, search_documents

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Enterprise Policy Search Agent")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ----------------------------
# Request / response models
# ----------------------------

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    user_pseudo_id: Optional[str] = "local-user"
    session_id: Optional[str] = "-"


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]


class AskResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    references: List[Dict[str, Any]]
    grounding_status: str


# ----------------------------
# Helpers
# ----------------------------

def _clean_question(question: str) -> str:
    cleaned = question.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    return cleaned


# ----------------------------
# Routes
# ----------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/search", response_model=SearchResponse)
async def api_search(payload: QueryRequest):
    try:
        cleaned_question = _clean_question(payload.question)

        results = search_documents(
            query=cleaned_question,
            user_pseudo_id=payload.user_pseudo_id or "local-user",
        )
        return {"results": results}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Search failed due to an internal error.",
        )


@app.post("/api/ask", response_model=AskResponse)
async def api_ask(payload: QueryRequest):
    try:
        cleaned_question = _clean_question(payload.question)

        result = answer_question(
            query=cleaned_question,
            user_pseudo_id=payload.user_pseudo_id or "local-user",
            session_id=payload.session_id or "-",
        )
        return result

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Answer generation failed due to an internal error.",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=True)