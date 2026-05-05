import uuid
from datetime import datetime, timezone
from typing import Optional


def build(question: str, entity: Optional[str], evidence: list[dict], missing: list[str]) -> dict:
    cf_id = f"cf_{uuid.uuid4().hex[:12]}"
    confidence = _compute_confidence(evidence, missing)
    return {
        "id": cf_id,
        "question": question,
        "entity": entity,
        "evidence": evidence,
        "missing": missing,
        "confidence": confidence,
        "sources_queried": [e["source_id"] for e in evidence],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _compute_confidence(evidence: list[dict], missing: list[str]) -> str:
    if not evidence:
        return "low"
    evidence_count = len(evidence)
    missing_count = len(missing)
    if evidence_count >= 2 and missing_count == 0:
        return "high"
    if evidence_count >= 1 and missing_count <= 2:
        return "medium"
    return "low"
