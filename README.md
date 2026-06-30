# Eightfold Multi-Source Candidate Data Transformer

A deterministic, configurable pipeline that ingests candidate data from multiple structured and unstructured sources, normalizes fields, merges duplicate candidates, and outputs schema-valid JSON with provenance and confidence tracking.

## Architecture

```
┌─────────┐   ┌─────────┐   ┌───────────┐   ┌─────────┐   ┌──────────┐   ┌─────────┐   ┌──────────┐
│ Detect  │──▶│ Extract │──▶│ Normalize │──▶│  Merge  │──▶│  Score   │──▶│ Project │──▶│ Validate │
│         │   │         │   │           │   │         │   │Confidence│   │         │   │          │
└─────────┘   └─────────┘   └───────────┘   └─────────┘   └──────────┘   └─────────┘   └──────────┘
 File ext +     Source-      Phones→E.164    Union-Find     Per-field     Runtime       JSON Schema
 content       specific      Dates→YYYY-MM   grouping by    & overall     config        validation
 heuristics    parsers       Skills→canon.   email/phone/   confidence    projection
                             Country→ISO     fuzzy name
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run with default config (full output)
python main.py --input-dir sample_inputs/ --verbose --validate

# 3. Run with custom config (minimal output)
python main.py --input-dir sample_inputs/ --config configs/minimal_config.json --output output.json

# 4. Run tests
python -m pytest tests/ -v
```

## CLI Usage

```
python main.py --input-dir <DIR> [--config <CONFIG>] [--output <FILE>] [--validate] [--verbose]

Arguments:
  --input-dir   Directory containing source files (CSV, JSON, PDF, DOCX, etc.) [required]
  --config      Path to runtime config JSON for output projection              [optional]
  --output      Output file path (default: stdout)                             [optional]
  --validate    Validate output against canonical JSON schema                  [optional]
  --verbose     Print pipeline progress and debug info                         [optional]
```

## Source Types

| Group | Source | Format | Priority |
|-------|--------|--------|----------|
| **Structured** | Recruiter CSV | `.csv` (name, email, phone, company, title, location, skills) | 3 |
| **Structured** | ATS JSON blob | `.json` (non-canonical field names) | 4 (highest) |
| **Unstructured/API** | GitHub Profile URL | `.github` (fetches public REST API for name, bio, repos/languages) | 2 |
| **Unstructured** | Resume file | `.pdf`, `.docx`, `.txt` (parsed text with sections) | 2 |
| **Unstructured** | Recruiter notes | `.txt` (informal observations) | 1 |

## Sample Output (Default Config)

```json
{
  "full_name": "Alice Johnson",
  "emails": ["alice.johnson@gmail.com", "a.johnson@google.com"],
  "phones": ["+14155551234"],
  "location": {"city": "San Francisco", "region": "CA", "country": "US"},
  "skills": [
    {"name": "python", "confidence": 0.85, "sources": ["ats_dump.json", "recruiter_export.csv", "resume_alice.txt"]},
    {"name": "kubernetes", "confidence": 0.675, "sources": ["ats_dump.json", "recruiter_export.csv"]}
  ],
  "experience": [
    {"company": "Google", "title": "Senior Software Engineer", "start": "2022-03", "end": null},
    {"company": "Amazon", "title": "Software Engineer", "start": "2019-06", "end": "2022-02"}
  ],
  "education": [
    {"institution": "Stanford University", "degree": "MS", "field": "Computer Science", "end_year": 2019}
  ],
  "provenance": [
    {"field": "full_name", "source": "ats_dump.json", "method": "direct_mapping"},
    {"field": "location.city", "source": "ats_dump.json", "method": "direct_mapping"}
  ],
  "overall_confidence": 0.591,
  "candidate_id": "bbe9665df433876a"
}
```

## Configurable Output

Runtime config reshapes the output without code changes:

```json
{
  "fields": [
    {"path": "full_name", "type": "string", "required": true},
    {"path": "primary_email", "from": "emails[0]", "type": "string", "required": true},
    {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
    {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
  ],
  "include_confidence": false,
  "on_missing": "null"
}
```

## Design Decisions

1. **Union-Find for transitive matching**: If A shares email with B, and B shares phone with C, all three merge. More robust than pairwise-only.
2. **Priority-based conflict resolution**: ATS (structured, curated) > CSV (structured, bulk) > Resume (self-reported) > Notes (second-hand). Scalars take highest-priority source; arrays union-merge.
3. **Provenance tracking**: Every field traces back to its source file and extraction method. No invented data.
4. **Drop invalid phones**: Rather than storing unparseable strings that violate E.164 schema, invalid phones are filtered out and logged.
5. **Fuzzy name threshold at 85%**: Balances false positives (merging different people) vs. false negatives (missing duplicates). Tested with common name variants.

## Edge Cases

- **Garbage/binary files** → Detected as `unknown`, skipped with warning
- **Empty input directory** → Returns `[]` gracefully
- **Conflicting names** → Highest-priority source wins
- **Malformed phone numbers** → Filtered out, not included in output
- **Missing CSV columns** → Graceful extraction of available fields
- **on_missing=error + missing required field** → Raises `ValueError`

## Testing

```bash
# Run all 37 tests
python -m pytest tests/ -v

# Tests cover:
# - Source type detection (4 types + unknown)
# - Each extractor (CSV, JSON, resume, notes)
# - Phone/date/skill normalization
# - Merge by email/phone/fuzzy name
# - Confidence scoring ranges
# - Config projection + field selection
# - Full end-to-end pipeline
# - Edge cases (empty dirs, garbage files, conflicts, malformed data)
```

## Project Structure

```
eightfold-transformer/
├── main.py                         # CLI entry point
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── pipeline/
│   ├── __init__.py                 # Pipeline orchestrator
│   ├── detector.py                 # Source type detection
│   ├── normalizer.py               # Phone/date/skill/country normalization
│   ├── merger.py                   # Cross-source merge + conflict resolution
│   ├── confidence.py               # Confidence scoring
│   ├── projector.py                # Runtime config projection
│   ├── validator.py                # JSON Schema validation
│   └── extractors/
│       ├── base.py                 # Abstract base extractor
│       ├── csv_extractor.py        # Recruiter CSV parser
│       ├── json_extractor.py       # ATS JSON parser
│       ├── resume_extractor.py     # Free-text resume parser
│       └── notes_extractor.py      # Recruiter notes parser
├── schema/
│   ├── canonical_schema.json       # JSON Schema for canonical output
│   └── config_schema.json          # JSON Schema for runtime config
├── configs/
│   ├── default_config.json         # Full output config
│   └── minimal_config.json         # Minimal field selection
├── sample_inputs/                  # Sample source files
├── sample_outputs/                 # Generated outputs
├── tests/
│   ├── test_pipeline.py            # Component + integration tests
│   └── test_edge_cases.py          # Edge case coverage
└── design/
    └── technical_design.html       # One-page design document (→ PDF)
```
