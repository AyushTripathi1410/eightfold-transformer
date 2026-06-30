"""Validate pipeline output against the canonical JSON schema."""

import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    logger.warning("jsonschema not installed; output validation disabled")

# Default schema path relative to project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCHEMA_PATH = os.path.join(_PROJECT_ROOT, 'schema', 'canonical_schema.json')


def validate_output(output: list[dict] | dict, schema_path: str | None = None) -> tuple[bool, list[str]]:
    """Validate output against the canonical JSON schema.

    Args:
        output: A single profile dict or a list of profile dicts.
        schema_path: Path to the JSON Schema file. Defaults to schema/canonical_schema.json.

    Returns:
        (is_valid, list_of_error_strings)
    """
    if not HAS_JSONSCHEMA:
        logger.warning("jsonschema not available; skipping validation")
        return True, []

    schema_path = schema_path or DEFAULT_SCHEMA_PATH
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except FileNotFoundError:
        msg = f"Schema file not found: {schema_path}"
        logger.error(msg)
        return False, [msg]
    except json.JSONDecodeError as e:
        msg = f"Invalid JSON in schema file: {e}"
        logger.error(msg)
        return False, [msg]

    # Handle both single dict and list of dicts
    profiles = output if isinstance(output, list) else [output]

    all_errors: list[str] = []

    for i, profile in enumerate(profiles):
        candidate_id = profile.get('candidate_id', f'index-{i}')
        try:
            jsonschema.validate(instance=profile, schema=schema)
        except jsonschema.ValidationError as e:
            error_path = '.'.join(str(p) for p in e.absolute_path)
            msg = f"[{candidate_id}] {error_path}: {e.message}" if error_path else f"[{candidate_id}] {e.message}"
            all_errors.append(msg)
            logger.debug(f"Validation error: {msg}")
        except jsonschema.SchemaError as e:
            msg = f"Schema error: {e.message}"
            all_errors.append(msg)
            logger.error(msg)

    is_valid = len(all_errors) == 0
    return is_valid, all_errors
