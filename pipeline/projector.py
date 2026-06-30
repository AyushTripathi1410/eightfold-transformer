"""Project canonical profiles to custom output shapes via runtime config."""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


def project_output(canonical: dict[str, Any], config: dict | None = None) -> dict[str, Any]:
    """Apply runtime config to reshape canonical output.

    If config is None, returns the full canonical profile (stripped of internal fields).
    """
    # Strip internal fields
    result = {k: v for k, v in canonical.items() if not k.startswith('_')}

    if config is None:
        return result

    fields = config.get('fields')
    if not fields:
        return result

    include_confidence = config.get('include_confidence', True)
    on_missing = config.get('on_missing', 'null')

    projected: dict[str, Any] = {}

    for field_spec in fields:
        path = field_spec.get('path')
        from_path = field_spec.get('from', path)
        required = field_spec.get('required', False)
        normalize = field_spec.get('normalize')

        if not path:
            continue

        # Resolve the value from the canonical record
        value = _resolve_path(result, from_path)

        # Apply normalization if specified
        if value is not None and normalize:
            value = _apply_normalize(value, normalize)

        # Handle missing values
        if value is None or (isinstance(value, (list, dict)) and not value):
            if required:
                raise ValueError(f"Required field '{path}' is missing in candidate {result.get('candidate_id', '?')}")
            if on_missing == 'null':
                projected[path] = None
            elif on_missing == 'omit':
                continue
            elif on_missing == 'error':
                raise ValueError(f"Field '{path}' is missing (on_missing=error)")
            else:
                projected[path] = None
        else:
            projected[path] = value

    # Optionally include confidence and provenance
    if include_confidence:
        if 'overall_confidence' in result:
            projected['overall_confidence'] = result['overall_confidence']
        if 'provenance' in result:
            projected['provenance'] = result['provenance']

    # Always include candidate_id
    if 'candidate_id' not in projected and 'candidate_id' in result:
        projected['candidate_id'] = result['candidate_id']

    return projected


def _resolve_path(data: dict, path: str) -> Any:
    """Resolve a dotted/indexed path like 'emails[0]', 'skills[].name', 'location.city'."""
    if not path or not data:
        return None

    try:
        # Handle array element extraction: 'skills[].name' → list of skill names
        if '[].' in path:
            parts = path.split('[].', 1)
            array_path = parts[0]
            sub_field = parts[1]
            array = _resolve_simple_path(data, array_path)
            if not isinstance(array, list):
                return None
            return [_resolve_simple_path(item, sub_field) for item in array if isinstance(item, dict)]

        # Handle single array index: 'emails[0]'
        m = re.match(r'^(.+)\[(\d+)\]$', path)
        if m:
            array_path = m.group(1)
            index = int(m.group(2))
            array = _resolve_simple_path(data, array_path)
            if isinstance(array, list) and 0 <= index < len(array):
                return array[index]
            return None

        # Simple dotted path: 'location.city'
        return _resolve_simple_path(data, path)

    except (KeyError, IndexError, TypeError):
        return None


def _resolve_simple_path(data: Any, path: str) -> Any:
    """Resolve a simple dotted path like 'location.city'."""
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _apply_normalize(value: Any, normalize: str) -> Any:
    """Apply a normalization strategy to a value."""
    if normalize == 'E164':
        # Phone normalization — should already be E.164 from normalizer
        return value
    elif normalize == 'canonical':
        # Skills — should already be canonical from normalizer
        if isinstance(value, list):
            return [v.lower() if isinstance(v, str) else v for v in value]
        elif isinstance(value, str):
            return value.lower()
        return value
    elif normalize == 'titlecase':
        if isinstance(value, str):
            return value.title()
        return value
    elif normalize == 'lowercase':
        if isinstance(value, str):
            return value.lower()
        return value
    elif normalize == 'uppercase':
        if isinstance(value, str):
            return value.upper()
        return value
    else:
        return value
