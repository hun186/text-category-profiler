"""Bounded, explicitly injected semantic-review provider contract.

A provider is trusted caller-supplied code, not a sandboxed model. No default
provider, network client, credentials, retries or authorization are supplied.
All model outputs are advisory, even when their evidence spans are verified.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json

MAX_SEMANTIC_REQUESTS = 25
MAX_SEMANTIC_ARTICLE_CHARS = 20_000
MAX_SEMANTIC_TOTAL_CHARS = 150_000
MAX_REQUEST_METADATA_CHARS = 8_000
MAX_RATIONALE_CHARS = 1_000
MAX_MODEL_CHARS = 120
MAX_SPANS = 3
MAX_SPAN_CHARS = 500
VERDICTS = ("RELEVANT", "IRRELEVANT", "UNCERTAIN")


@dataclass(frozen=True)
class SemanticReviewRequest:
    request_id: str
    class_label: str
    chinese_name: str
    explanation: str
    notes: str
    source: str
    article_sha256: str
    normalized_sha256: str
    normalized_text: str


SemanticReviewer = Callable[[SemanticReviewRequest], object]


def build_semantic_request(label: str, row: dict[str, str], source: str,
                           article_sha256: str, normalized_text: str) -> SemanticReviewRequest:
    """Bind the exact candidate fields and verified source bytes to full normalized text."""
    fields = (label, row["CT"], row["Explanation"], row["Notes"], source)
    if not all(isinstance(field, str) for field in fields):
        raise ValueError("semantic request metadata must be text")
    if sum(map(len, fields)) > MAX_REQUEST_METADATA_CHARS:
        raise ValueError("semantic review exceeds request metadata budget")
    if not 1 <= len(normalized_text) <= MAX_SEMANTIC_ARTICLE_CHARS:
        raise ValueError("semantic review exceeds article character budget")
    normalized_sha = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    payload = ["BL002_SEMANTIC_REVIEW_V1", *fields, article_sha256, normalized_sha]
    request_id = hashlib.sha256(json.dumps(
        payload, ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")).hexdigest()
    return SemanticReviewRequest(
        request_id, *fields, article_sha256, normalized_sha, normalized_text
    )


def _validate_response(request: SemanticReviewRequest, response: object) -> dict:
    """Validate schema, exact request binding and quoted spans; not model truth."""
    if not isinstance(response, dict) or set(response) != {
        "request_id", "model", "verdict", "rationale", "spans"
    }:
        raise ValueError("invalid response fields")
    if response["request_id"] != request.request_id:
        raise ValueError("response request identity mismatch")
    model, verdict, rationale, spans = (
        response["model"], response["verdict"], response["rationale"], response["spans"]
    )
    if not isinstance(model, str) or not 1 <= len(model.strip()) <= MAX_MODEL_CHARS or len(model) > MAX_MODEL_CHARS:
        raise ValueError("invalid reported model")
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        raise ValueError("invalid verdict")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > MAX_RATIONALE_CHARS:
        raise ValueError("invalid rationale")
    if not isinstance(spans, list) or len(spans) > MAX_SPANS or (
        verdict != "UNCERTAIN" and not spans
    ):
        raise ValueError("invalid evidence span count")
    verified = []
    for span in spans:
        if not isinstance(span, dict) or set(span) != {"start", "end", "text"}:
            raise ValueError("invalid evidence span fields")
        start, end, quote = span["start"], span["end"], span["text"]
        if (type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(request.normalized_text)
                or end - start > MAX_SPAN_CHARS or not isinstance(quote, str)
                or not quote.strip() or request.normalized_text[start:end] != quote):
            raise ValueError("evidence span does not match normalized article")
        if (start, end) in {(item["Start"], item["End"]) for item in verified}:
            raise ValueError("duplicate evidence span")
        verified.append({"Start": start, "End": end, "Text": quote})
    return {
        "ReviewStatus": "ADVISORY_RESPONSE" if verdict != "UNCERTAIN" else "MODEL_UNCERTAIN",
        "ReportedModel": model,
        "Verdict": verdict,
        "Rationale": rationale,
        "EvidenceSpans": verified,
        "EvidenceSpanTextMatches": bool(verified),
    }


def run_semantic_review(request: SemanticReviewRequest, reviewer: SemanticReviewer) -> dict:
    """Invoke once; provider failure or invalid response never becomes a verdict."""
    result = {
        "RequestId": request.request_id,
        "ClassLabel": request.class_label,
        "Source": request.source,
        "ArticleSha256": request.article_sha256,
        "NormalizedSha256": request.normalized_sha256,
        "HumanReviewRequired": True,
        "Approved": False,
    }
    try:
        response = reviewer(request)
    except Exception:
        # Do not leak arbitrary provider exceptions, secrets or article bodies.
        return {**result, "ReviewStatus": "PROVIDER_ERROR", "Verdict": None}
    try:
        return {**result, **_validate_response(request, response)}
    except (ValueError, TypeError):
        return {**result, "ReviewStatus": "INVALID_RESPONSE", "Verdict": None}
