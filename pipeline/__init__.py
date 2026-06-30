import os
import json
import logging
from .detector import detect_source_type
from .extractors.csv_extractor import CSVExtractor
from .extractors.json_extractor import JSONExtractor
from .extractors.resume_extractor import ResumeExtractor
from .extractors.notes_extractor import NotesExtractor
from .extractors.pdf_resume_extractor import PDFResumeExtractor
from .extractors.github_extractor import GitHubExtractor
from .normalizer import normalize_candidate
from .merger import merge_candidates
from .confidence import score_confidence
from .projector import project_output

logger = logging.getLogger(__name__)

EXTRACTOR_MAP = {
    'recruiter_csv': CSVExtractor(),
    'ats_json': JSONExtractor(),
    'resume_txt': ResumeExtractor(),
    'resume_pdf': PDFResumeExtractor(),
    'notes_txt': NotesExtractor(),
    'github_url': GitHubExtractor(),
}

def run_pipeline(input_dir: str, config_path: str | None = None) -> list[dict]:
    """Run the full candidate data transformation pipeline."""
    config = None
    if config_path:
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise

    # Discover files
    files = []
    if os.path.isdir(input_dir):
        for fname in sorted(os.listdir(input_dir)):
            fpath = os.path.join(input_dir, fname)
            if os.path.isfile(fpath):
                files.append(fpath)
    else:
        logger.warning(f"Input directory does not exist: {input_dir}")
        return []

    if not files:
        logger.warning(f"No files found in {input_dir}")
        return []

    # Detect and extract
    all_raw = []
    for fpath in files:
        source_type = detect_source_type(fpath)
        if source_type == 'unknown':
            logger.warning(f"Skipping unrecognized file: {fpath}")
            continue
        extractor = EXTRACTOR_MAP.get(source_type)
        if not extractor:
            logger.warning(f"No extractor for source type '{source_type}': {fpath}")
            continue
        try:
            candidates = extractor.extract(fpath)
            all_raw.extend(candidates)
            logger.info(f"Extracted {len(candidates)} candidate(s) from {fpath} [{source_type}]")
        except Exception as e:
            logger.warning(f"Failed to extract from {fpath}: {e}")
            continue

    if not all_raw:
        logger.warning("No candidates extracted from any source")
        return []

    # Normalize
    normalized = []
    for raw in all_raw:
        try:
            normalized.append(normalize_candidate(raw))
        except Exception as e:
            logger.warning(f"Failed to normalize candidate: {e}")
            continue

    # Merge
    merged = merge_candidates(normalized)

    # Score confidence
    scored = [score_confidence(m) for m in merged]

    # Project output
    projected = [project_output(s, config) for s in scored]

    return projected
