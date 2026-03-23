from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as discoveryengine

from app.config import PROJECT_ID, LOCATION, APP_ID


# ----------------------------
# Resource paths / clients
# ----------------------------

def _to_plain_value(value):
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _to_plain_value(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_plain_value(v) for v in value]

    if hasattr(value, "items"):
        try:
            return {str(k): _to_plain_value(v) for k, v in value.items()}
        except Exception:
            pass

    try:
        return [_to_plain_value(v) for v in value]
    except Exception:
        pass

    if hasattr(value, "__dict__"):
        try:
            return {
                str(k): _to_plain_value(v)
                for k, v in vars(value).items()
                if not k.startswith("_")
            }
        except Exception:
            pass

    return str(value)


def _plain_list(value) -> list:
    plain = _to_plain_value(value)
    return plain if isinstance(plain, list) else []


def _plain_dict(value) -> dict:
    plain = _to_plain_value(value)
    return plain if isinstance(plain, dict) else {}

def _client_options() -> Optional[ClientOptions]:
    if LOCATION != "global":
        return ClientOptions(api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com")
    return None


def _search_serving_config() -> str:
    return (
        f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
        f"engines/{APP_ID}/servingConfigs/default_search"
    )


def _answer_serving_config() -> str:
    return (
        f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
        f"engines/{APP_ID}/servingConfigs/default_serving_config"
    )


def _session_path(session_id: str = "-") -> str:
    return (
        f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
        f"engines/{APP_ID}/sessions/{session_id}"
    )


# ----------------------------
# Query helpers
# ----------------------------

def normalize_query(query: str) -> str:
    q = query.strip()
    q = re.sub(r"\s+", " ", q)
    return q


def is_opinion_like_query(query: str) -> bool:
    q = query.lower()
    triggers = [
        "do you think",
        "would you",
        "should i",
        "is it a good idea",
        "do you recommend",
        "would it be better",
        "which is better",
        "what do you prefer",
        "would you say",
    ]
    return any(t in q for t in triggers)


def _important_terms(query: str) -> List[str]:
    stop = {
        "what", "which", "when", "where", "who", "why", "how",
        "does", "would", "could", "should", "can", "tell",
        "think", "about", "please", "there", "their", "them",
        "this", "that", "with", "from", "into", "have", "will",
        "your", "than", "then", "they", "them", "you", "are",
        "for", "and", "the", "any",
    }
    words = re.findall(r"[a-zA-Z]+", query.lower())
    return [w for w in words if len(w) > 2 and w not in stop]


# ----------------------------
# Grounding helpers
# ----------------------------

def _collect_result_text(result: Dict[str, Any]) -> str:
    parts: List[str] = []

    title = result.get("title", "")
    if title:
        parts.append(title)

    for s in result.get("snippets", []) or []:
        if isinstance(s, dict):
            snippet = s.get("snippet", "")
            if snippet:
                parts.append(snippet)

    for a in result.get("extractive_answers", []) or []:
        if isinstance(a, dict):
            content = a.get("content", "")
            if content:
                parts.append(content)

    for seg in result.get("extractive_segments", []) or []:
        if isinstance(seg, dict):
            content = seg.get("content", "")
            if content:
                parts.append(content)

    return " ".join(parts).lower()


def grounding_score(query: str, results: List[Dict[str, Any]]) -> Tuple[int, bool]:
    if not results:
        return 0, False

    terms = _important_terms(query)
    if not terms:
        return 0, False

    best_overlap = 0
    has_extractive = False

    for result in results:
        text = _collect_result_text(result)
        overlap = sum(1 for term in terms if term in text)
        best_overlap = max(best_overlap, overlap)

        if result.get("extractive_answers") or result.get("extractive_segments"):
            has_extractive = True

    return best_overlap, has_extractive


def _grounding_status(query: str, results: List[Dict[str, Any]]) -> str:
    if not results:
        return "weak"

    best_overlap, has_extractive = grounding_score(query, results)

    if best_overlap >= 2 and has_extractive:
        return "strong"

    if best_overlap >= 1:
        return "partial"

    return "weak"


# ----------------------------
# Search
# ----------------------------

def search_documents(query: str, user_pseudo_id: str = "local-user") -> List[Dict[str, Any]]:
    client = discoveryengine.SearchServiceClient(client_options=_client_options())

    content_search_spec = discoveryengine.SearchRequest.ContentSearchSpec(
        snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
            return_snippet=True
        ),
        extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
            max_extractive_answer_count=3,
            max_extractive_segment_count=2,
        ),
    )

    request = discoveryengine.SearchRequest(
        serving_config=_search_serving_config(),
        query=query,
        page_size=8,
        user_pseudo_id=user_pseudo_id,
        content_search_spec=content_search_spec,
    )

    response = client.search(request=request)

    results: List[Dict[str, Any]] = []

    for item in response:
        doc = item.document
        derived = getattr(doc, "derived_struct_data", None)
        struct_data = getattr(doc, "struct_data", None)

        title = ""
        link = ""
        snippets: List[Dict[str, Any]] = []
        extractive_answers: List[Dict[str, Any]] = []
        extractive_segments: List[Dict[str, Any]] = []

        if derived and hasattr(derived, "get"):
            title = str(derived.get("title", "") or "")
            link = str(derived.get("link", "") or "")
            snippets = _plain_list(derived.get("snippets", []))
            extractive_answers = _plain_list(derived.get("extractive_answers", []))
            extractive_segments = _plain_list(derived.get("extractive_segments", []))

        results.append(
            {
                "id": str(getattr(doc, "id", "")),
                "title": title or str(getattr(doc, "id", "")),
                "link": link,
                "snippets": _plain_list(snippets),
                "extractive_answers": _plain_list(extractive_answers),
                "extractive_segments": _plain_list(extractive_segments),
                "struct_data": _plain_dict(struct_data),
            }
        )

    return results


# ----------------------------
# Citation enrichment
# ----------------------------

def _map_citations_to_results(
    citations: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id = {result.get("id", ""): result for result in results}

    enriched: List[Dict[str, Any]] = []

    for citation in citations:
        enriched_entry = {
            "start_index": citation.get("start_index"),
            "end_index": citation.get("end_index"),
            "sources": [],
        }

        for src in citation.get("sources", []):
            reference_id = src.get("reference_id", "")
            matched = by_id.get(reference_id, {})

            enriched_entry["sources"].append(
                {
                    "reference_id": reference_id,
                    "title": matched.get("title", ""),
                    "link": matched.get("link", ""),
                    "snippets": _plain_list(matched.get("snippets", [])),
                    "extractive_answers": _plain_list(matched.get("extractive_answers", [])),
                    "extractive_segments": _plain_list(matched.get("extractive_segments", [])),
                }
            )

        enriched.append(enriched_entry)

    return enriched


# ----------------------------
# Answer generation
# ----------------------------

def _build_preamble(opinion_like: bool) -> str:
    preamble = (
        "Answer only from the indexed documents. "
        "If the documents directly support the answer, answer clearly and concisely. "
        "If the documents provide only indirect support, say that the answer is a cautious inference. "
        "If support is insufficient, say so explicitly. "
        "Do not present weak support as certainty."
    )

    if opinion_like:
        preamble += (
            " For subjective or preference-based questions, you may provide a short cautious inference, "
            "but you must clearly label it as an inference rather than a directly supported fact."
        )

    return preamble


def answer_question(
    query: str,
    user_pseudo_id: str = "local-user",
    session_id: str = "-",
) -> Dict[str, Any]:
    cleaned_query = normalize_query(query)

    # Step 1: retrieve first
    search_results = search_documents(
        query=cleaned_query,
        user_pseudo_id=user_pseudo_id,
    )

    if not search_results:
        return {
            "answer": "I couldn't find relevant support in the indexed documents.",
            "citations": [],
            "references": [],
            "grounding_status": "weak",
        }

    grounding_status = _grounding_status(cleaned_query, search_results)
    opinion_like = is_opinion_like_query(query)

    # Step 2: answer generation
    client = discoveryengine.ConversationalSearchServiceClient(
        client_options=_client_options()
    )

    query_understanding_spec = (
        discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec(
            query_rephraser_spec=discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec.QueryRephraserSpec(
                disable=False,
                max_rephrase_steps=1,
            )
        )
    )

    answer_generation_spec = discoveryengine.AnswerQueryRequest.AnswerGenerationSpec(
        include_citations=True,
        answer_language_code="en",
        ignore_adversarial_query=False,
        ignore_non_answer_seeking_query=False,
        ignore_low_relevant_content=False,
        prompt_spec=discoveryengine.AnswerQueryRequest.AnswerGenerationSpec.PromptSpec(
            preamble=_build_preamble(opinion_like)
        ),
    )

    request = discoveryengine.AnswerQueryRequest(
        serving_config=_answer_serving_config(),
        query=discoveryengine.Query(text=cleaned_query),
        session=_session_path(session_id),
        query_understanding_spec=query_understanding_spec,
        answer_generation_spec=answer_generation_spec,
        user_pseudo_id=user_pseudo_id,
    )

    response = client.answer_query(request=request)

    answer_text = ""
    raw_citations: List[Dict[str, Any]] = []

    if getattr(response, "answer", None):
        answer_text = getattr(response.answer, "answer_text", "") or ""

        for citation in getattr(response.answer, "citations", []) or []:
            raw_citations.append(
                {
                    "start_index": getattr(citation, "start_index", None),
                    "end_index": getattr(citation, "end_index", None),
                    "sources": [
                        {"reference_id": getattr(src, "reference_id", "")}
                        for src in getattr(citation, "sources", []) or []
                    ],
                }
            )

    enriched_citations = _map_citations_to_results(raw_citations, search_results)

    if not answer_text.strip():
        if grounding_status == "partial":
            return {
                "answer": (
                    "I found related content, but only enough for a cautious inference, "
                    "not a direct grounded answer."
                ),
                "citations": enriched_citations,
                "references": search_results,
                "grounding_status": grounding_status,
            }

        return {
            "answer": (
                "I found related documents, but I couldn't produce a reliable grounded answer."
            ),
            "citations": enriched_citations,
            "references": search_results,
            "grounding_status": grounding_status,
        }

    return {
        "answer": answer_text,
        "citations": enriched_citations,
        "references": search_results,
        "grounding_status": grounding_status,
    }