from __future__ import annotations


def category_list_from_value(category: str) -> list[str]:
    cat = str(category or "").strip()
    if not cat or cat.lower() in ("unassigned", "all"):
        return []
    return [cat]


def normalize_preview_payload(preview: dict | None) -> dict:
    payload = dict(preview) if isinstance(preview, dict) else {}
    payload_jy = str(payload.get("jyutping", "") or "").strip()
    payload_hz = str(payload.get("hanzi", "") or "").strip()
    payload_mn = str(payload.get("meaning", "") or "").strip()
    payload_cat = str(payload.get("category", "") or "").strip()
    payload["jyutping"] = payload_jy
    payload["hanzi"] = payload_hz
    payload["meaning"] = payload_mn
    payload["gloss"] = payload_mn
    payload["category"] = payload_cat
    payload["categories"] = category_list_from_value(payload_cat)
    return payload
