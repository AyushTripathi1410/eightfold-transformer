"""Tests for the full pipeline and individual components."""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.detector import detect_source_type
from pipeline.extractors.csv_extractor import CSVExtractor
from pipeline.extractors.json_extractor import JSONExtractor
from pipeline.extractors.pdf_resume_extractor import PDFResumeExtractor
from pipeline.extractors.notes_extractor import NotesExtractor
from pipeline.normalizer import normalize_candidate, _normalize_phone, _normalize_date, _normalize_skills
from pipeline.merger import merge_candidates
from pipeline.confidence import score_confidence
from pipeline.projector import project_output
from pipeline.validator import validate_output
from pipeline import run_pipeline

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_inputs')


# ── Detector Tests ───────────────────────────────────────────────────────────
class TestDetector:
    def test_csv_detection(self):
        assert detect_source_type(os.path.join(SAMPLE_DIR, 'recruiter_export.csv')) == 'recruiter_csv'

    def test_json_detection(self):
        assert detect_source_type(os.path.join(SAMPLE_DIR, 'ats_dump.json')) == 'ats_json'

    def test_pdf_resume_detection(self):
        assert detect_source_type(os.path.join(SAMPLE_DIR, 'resume_alice.pdf')) == 'resume_pdf'

    def test_notes_detection(self):
        assert detect_source_type(os.path.join(SAMPLE_DIR, 'notes_alice.txt')) == 'notes_txt'

    def test_github_detection(self):
        assert detect_source_type(os.path.join(SAMPLE_DIR, 'github_alice.github')) == 'github_url'


# ── CSV Extractor Tests ──────────────────────────────────────────────────────
class TestCSVExtractor:
    def test_extract_candidates(self):
        ext = CSVExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'recruiter_export.csv'))
        assert len(candidates) == 3

    def test_extract_fields(self):
        ext = CSVExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'recruiter_export.csv'))
        alice = candidates[0]
        assert alice['full_name'] is not None
        assert len(alice['emails']) > 0
        assert len(alice['phones']) > 0
        assert len(alice['skills']) > 0
        assert alice['source_type'] == 'recruiter_csv'


# ── JSON Extractor Tests ────────────────────────────────────────────────────
class TestJSONExtractor:
    def test_extract_candidates(self):
        ext = JSONExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'ats_dump.json'))
        assert len(candidates) == 2

    def test_field_mapping(self):
        ext = JSONExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'ats_dump.json'))
        alice = candidates[0]
        assert alice['full_name'] == 'Alice Johnson'
        assert 'alice.johnson@gmail.com' in alice['emails']
        assert len(alice['skills']) >= 4
        assert len(alice['experience']) >= 2
        assert len(alice['education']) >= 1
        assert alice['source_type'] == 'ats_json'


# ── PDF Resume Extractor Tests ──────────────────────────────────────────────
class TestPDFResumeExtractor:
    def test_extract_basic(self):
        ext = PDFResumeExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'resume_alice.pdf'))
        assert len(candidates) == 1

    def test_extract_email_phone(self):
        ext = PDFResumeExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'resume_alice.pdf'))
        alice = candidates[0]
        assert 'alice.johnson@gmail.com' in alice['emails']
        assert len(alice['phones']) > 0

    def test_extract_skills(self):
        ext = PDFResumeExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'resume_alice.pdf'))
        alice = candidates[0]
        assert len(alice['skills']) >= 5

    def test_extract_experience(self):
        ext = PDFResumeExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'resume_alice.pdf'))
        alice = candidates[0]
        assert len(alice['experience']) >= 2

    def test_extract_education(self):
        ext = PDFResumeExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'resume_alice.pdf'))
        alice = candidates[0]
        assert len(alice['education']) >= 1


# ── Notes Extractor Tests ───────────────────────────────────────────────────
class TestNotesExtractor:
    def test_extract_partial_data(self):
        ext = NotesExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'notes_alice.txt'))
        assert len(candidates) == 1
        alice = candidates[0]
        assert alice['full_name'] is not None
        assert 'Alice' in (alice['full_name'] or '')
        assert alice['source_type'] == 'notes_txt'

    def test_extract_skills_from_notes(self):
        ext = NotesExtractor()
        candidates = ext.extract(os.path.join(SAMPLE_DIR, 'notes_alice.txt'))
        alice = candidates[0]
        assert len(alice['skills']) > 0


# ── Normalizer Tests ────────────────────────────────────────────────────────
class TestNormalizer:
    def test_phone_normalization(self):
        assert _normalize_phone('+14155551234') == '+14155551234'
        assert _normalize_phone('(415) 555-1234') == '+14155551234'
        assert _normalize_phone('+1-415-555-1234') == '+14155551234'
        assert _normalize_phone('4155551234') == '+14155551234'

    def test_date_normalization(self):
        assert _normalize_date('2022-03') == '2022-03'
        assert _normalize_date('Mar 2022') == '2022-03'
        assert _normalize_date('March 2022') == '2022-03'
        assert _normalize_date('Present') is None
        assert _normalize_date('') is None

    def test_skill_canonicalization(self):
        result = _normalize_skills(['Python', 'JS', 'k8s', 'React.js', 'golang'])
        assert 'python' in result
        assert 'javascript' in result
        assert 'kubernetes' in result
        assert 'react' in result
        assert 'go' in result

    def test_normalize_candidate_full(self):
        raw = {
            'source_type': 'recruiter_csv', 'source_file': 'test.csv',
            'full_name': 'alice  johnson',
            'emails': ['Alice.Johnson@Gmail.com'],
            'phones': ['(415) 555-1234'],
            'location': {'city': 'San Francisco', 'region': 'California', 'country': 'US'},
            'skills': ['Python', 'JS', 'k8s'],
            'experience': [], 'education': [],
            'links': None, 'headline': None, 'years_experience': None,
        }
        result = normalize_candidate(raw)
        assert result['full_name'] == 'Alice Johnson'
        assert 'alice.johnson@gmail.com' in result['emails']
        assert result['phones'][0] == '+14155551234'
        assert result['location']['region'] == 'CA'
        assert 'python' in result['skills']


# ── Merger Tests ─────────────────────────────────────────────────────────────
class TestMerger:
    def test_merge_by_email(self):
        c1 = {
            'source_type': 'recruiter_csv', 'source_file': 'a.csv',
            'full_name': 'Alice Johnson', 'emails': ['alice@test.com'],
            'phones': [], 'skills': ['python'], 'experience': [],
            'education': [], 'location': None, 'links': None,
            'headline': None, 'years_experience': None,
        }
        c2 = {
            'source_type': 'ats_json', 'source_file': 'b.json',
            'full_name': 'Alice Johnson', 'emails': ['alice@test.com'],
            'phones': ['+11234567890'], 'skills': ['java'], 'experience': [],
            'education': [], 'location': None, 'links': None,
            'headline': 'Engineer', 'years_experience': 5,
        }
        merged = merge_candidates([c1, c2])
        assert len(merged) == 1
        assert 'alice@test.com' in merged[0]['emails']

    def test_no_merge_different_people(self):
        c1 = {
            'source_type': 'recruiter_csv', 'source_file': 'a.csv',
            'full_name': 'Alice Johnson', 'emails': ['alice@test.com'],
            'phones': [], 'skills': [], 'experience': [],
            'education': [], 'location': None, 'links': None,
            'headline': None, 'years_experience': None,
        }
        c2 = {
            'source_type': 'recruiter_csv', 'source_file': 'a.csv',
            'full_name': 'Bob Smith', 'emails': ['bob@test.com'],
            'phones': [], 'skills': [], 'experience': [],
            'education': [], 'location': None, 'links': None,
            'headline': None, 'years_experience': None,
        }
        merged = merge_candidates([c1, c2])
        assert len(merged) == 2


# ── Confidence Tests ─────────────────────────────────────────────────────────
class TestConfidence:
    def test_confidence_range(self):
        profile = {
            'full_name': 'Alice', 'emails': ['a@b.com'], 'phones': ['+11234567890'],
            'skills': [{'name': 'python', 'confidence': 0.0, 'sources': ['a.csv'], '_source_types': ['recruiter_csv']}],
            'experience': [], 'education': [], 'location': None, 'links': None,
            'headline': None, 'years_experience': None,
            'provenance': [{'field': 'full_name', 'source': 'a.csv', 'method': 'direct_mapping'}],
            'overall_confidence': 0.0,
        }
        scored = score_confidence(profile)
        assert 0.0 <= scored['overall_confidence'] <= 1.0


# ── Projector Tests ──────────────────────────────────────────────────────────
class TestProjector:
    def test_no_config_returns_full(self):
        profile = {'full_name': 'Alice', 'emails': ['a@b.com'], 'candidate_id': 'abc'}
        result = project_output(profile, None)
        assert result == profile

    def test_config_selects_fields(self):
        profile = {
            'full_name': 'Alice', 'emails': ['a@b.com', 'b@c.com'],
            'phones': ['+11234567890'], 'candidate_id': 'abc',
            'overall_confidence': 0.8, 'provenance': [],
        }
        config = {
            'fields': [
                {'path': 'full_name', 'type': 'string', 'required': True},
                {'path': 'primary_email', 'from': 'emails[0]', 'type': 'string'},
            ],
            'include_confidence': False,
            'on_missing': 'null',
        }
        result = project_output(profile, config)
        assert result['full_name'] == 'Alice'
        assert result['primary_email'] == 'a@b.com'
        assert 'overall_confidence' not in result


# ── Full Pipeline Tests ──────────────────────────────────────────────────────
class TestFullPipeline:
    def test_end_to_end_default(self):
        results = run_pipeline(SAMPLE_DIR)
        assert len(results) == 3  # Alice, Bob, Charlie

        names = {r['full_name'] for r in results}
        assert 'Alice Johnson' in names
        assert 'Bob Smith' in names
        assert 'Charlie Davis' in names

    def test_end_to_end_with_config(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'configs', 'minimal_config.json'
        )
        results = run_pipeline(SAMPLE_DIR, config_path)
        assert len(results) == 3
        for r in results:
            assert 'full_name' in r
            assert 'candidate_id' in r

    def test_output_validation(self):
        results = run_pipeline(SAMPLE_DIR)
        is_valid, errors = validate_output(results)
        assert is_valid, f"Validation errors: {errors}"

    def test_alice_merged_across_sources(self):
        results = run_pipeline(SAMPLE_DIR)
        alice = next(r for r in results if r['full_name'] == 'Alice Johnson')
        assert len(alice['emails']) >= 2
        assert len(alice['skills']) >= 5
        assert len(alice['experience']) >= 2
        assert len(alice['education']) >= 1
        assert alice['overall_confidence'] > 0.5
