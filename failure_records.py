"""Allowlisted failure metadata; no prompt, response, exception text or keys."""
CATEGORIES = {"hate", "sexual", "violence", "self_harm", "jailbreak", "indirect_attack",
              "protected_material_text", "protected_material_code", "custom_blocklists",
              "profanity", "pii", "groundedness"}


def safe_diagnostics(error):
    out = {}
    if type(getattr(error, "status", None)) is int:
        out["http_status"] = error.status
    diagnostic = getattr(error, "diagnostics", {})
    if not isinstance(diagnostic, dict):
        return out
    if diagnostic.get("phase") in ("request", "response", "completion"):
        out["phase"] = diagnostic["phase"]
    filters = []
    values = diagnostic.get("filters", [])
    for entry in values[:24] if isinstance(values, list) else []:
        if not isinstance(entry, dict) or entry.get("category") not in CATEGORIES:
            continue
        clean = {"category": entry["category"]}
        for flag in ("filtered", "detected", "blocked"):
            if type(entry.get(flag)) is bool:
                clean[flag] = entry[flag]
        if entry.get("severity") in ("safe", "low", "medium", "high"):
            clean["severity"] = entry["severity"]
        if clean not in filters:
            filters.append(clean)
    if filters:
        out["filters"] = filters
    return out
