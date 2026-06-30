"""Score confidence for merged candidate profiles."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Source reliability weights
SOURCE_WEIGHTS = {
    'ats_json': 1.0,
    'recruiter_csv': 0.85,
    'resume_txt': 0.70,
    'resume_pdf': 0.70,
    'notes_txt': 0.50,
    'github_url': 0.40,
}

# Source count → confidence factor
SOURCE_COUNT_FACTOR = {
    1: 0.5,
    2: 0.75,
    3: 0.9,
    4: 1.0,
}

# Field importance weights for overall score
FIELD_WEIGHTS = {
    'full_name': 1.0,
    'emails': 0.9,
    'phones': 0.8,
    'skills': 0.7,
    'experience': 0.8,
    'education': 0.6,
    'location': 0.5,
    'headline': 0.3,
    'years_experience': 0.4,
    'links': 0.3,
}


def score_confidence(merged: dict[str, Any]) -> dict[str, Any]:
    """Compute per-skill and overall confidence scores for a merged profile.

    Mutates and returns the input dict.
    """
    result = dict(merged)

    # ── Per-skill confidence ─────────────────────────────────────────────
    for skill in result.get('skills', []):
        source_types = skill.pop('_source_types', [])
        sources = skill.get('sources', [])
        count = len(sources)
        count_factor = SOURCE_COUNT_FACTOR.get(min(count, 4), 1.0)

        # Average priority weight of contributing sources
        if source_types:
            weight_sum = sum(SOURCE_WEIGHTS.get(st, 0.5) for st in source_types)
            avg_weight = weight_sum / len(source_types)
        else:
            avg_weight = 0.5

        skill['confidence'] = round(count_factor * avg_weight, 3)

    # ── Overall confidence ───────────────────────────────────────────────
    weighted_sum = 0.0
    weight_total = 0.0

    # Count contributing sources from provenance
    provenance = result.get('provenance', [])
    field_sources: dict[str, set] = {}
    for p in provenance:
        field_name = p['field'].split('.')[0].split('[')[0]  # top-level field
        field_sources.setdefault(field_name, set()).add(p['source'])

    for field, importance in FIELD_WEIGHTS.items():
        value = result.get(field)
        # Check if field has meaningful data
        has_data = False
        if value is None:
            has_data = False
        elif isinstance(value, list):
            has_data = len(value) > 0
        elif isinstance(value, dict):
            has_data = any(v is not None for v in value.values())
        elif isinstance(value, str):
            has_data = bool(value.strip())
        elif isinstance(value, (int, float)):
            has_data = True

        if not has_data:
            continue  # Don't penalize for absent optional fields

        # How many sources contributed?
        n_sources = len(field_sources.get(field, set()))
        if n_sources == 0:
            n_sources = 1  # At least one source if data exists

        source_factor = SOURCE_COUNT_FACTOR.get(min(n_sources, 4), 1.0)
        field_confidence = source_factor
        weighted_sum += field_confidence * importance
        weight_total += importance

    overall = round(weighted_sum / weight_total, 3) if weight_total > 0 else 0.0
    result['overall_confidence'] = overall

    return result
