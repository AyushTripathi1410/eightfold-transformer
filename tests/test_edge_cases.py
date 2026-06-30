"""Edge case tests for the pipeline."""
import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import run_pipeline
from pipeline.detector import detect_source_type
from pipeline.normalizer import normalize_candidate
from pipeline.projector import project_output
from pipeline.validator import validate_output

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestEdgeCases:
    def test_empty_input_directory(self, tmp_path):
        """Empty directory → empty output list."""
        results = run_pipeline(str(tmp_path))
        assert results == []

    def test_garbage_binary_file(self, tmp_path):
        """Binary/garbage file → skipped with warning, not a crash."""
        garbage = tmp_path / "garbage.xyz"
        garbage.write_bytes(b'\x00\x01\x02\xff\xfe\xfd' * 100)
        results = run_pipeline(str(tmp_path))
        assert results == []

    def test_single_csv_source(self, tmp_path):
        """Single source only → still produces valid profiles."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,email,phone,current_company,title,location,skills\n"
                          "Jane Doe,jane@test.com,+15551234567,Acme,Engineer,Boston MA,Python/Java\n")
        results = run_pipeline(str(tmp_path))
        assert len(results) == 1
        assert results[0]['full_name'] == 'Jane Doe'
        is_valid, errors = validate_output(results)
        assert is_valid, f"Validation errors: {errors}"

    def test_name_conflict_priority(self, tmp_path):
        """When sources disagree on name, highest priority wins."""
        # Create CSV with one name
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,email,phone,current_company,title,location,skills\n"
                          "Jane Smith,jane@test.com,,,,Boston MA,\n")
        # Create JSON with different name but same email
        json_file = tmp_path / "ats.json"
        json_file.write_text(json.dumps({
            "candidates": [{
                "applicant_name": "Jane Doe",
                "contact_email": "jane@test.com",
                "city": "Boston", "state": "MA", "country_code": "US",
                "tech_stack": ["Python"]
            }]
        }))
        results = run_pipeline(str(tmp_path))
        assert len(results) == 1
        # ATS JSON has higher priority (4) than CSV (3)
        assert results[0]['full_name'] == 'Jane Doe'

    def test_malformed_phone(self, tmp_path):
        """Malformed phone → filtered out, not in output."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,email,phone,current_company,title,location,skills\n"
                          "Test User,test@test.com,not-a-phone,,,New York NY,\n")
        results = run_pipeline(str(tmp_path))
        assert len(results) == 1
        # Malformed phone should be filtered out
        assert len(results[0]['phones']) == 0

    def test_config_on_missing_error(self):
        """Config with on_missing='error' + missing required field → raises."""
        profile = {
            'full_name': 'Alice', 'candidate_id': 'abc',
            'emails': [], 'phones': [],
        }
        config = {
            'fields': [
                {'path': 'full_name', 'type': 'string', 'required': True},
                {'path': 'primary_email', 'from': 'emails[0]', 'type': 'string', 'required': True},
            ],
            'include_confidence': False,
            'on_missing': 'null',
        }
        with pytest.raises(ValueError, match="Required field"):
            project_output(profile, config)

    def test_unknown_file_extension(self, tmp_path):
        """Unknown file type → detected as 'unknown', skipped."""
        f = tmp_path / "data.xlsx"
        f.write_bytes(b'fake excel content')
        assert detect_source_type(str(f)) == 'unknown'
        results = run_pipeline(str(tmp_path))
        assert results == []

    def test_empty_csv(self, tmp_path):
        """Empty CSV (headers only) → no candidates."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("name,email,phone,current_company,title,location,skills\n")
        results = run_pipeline(str(tmp_path))
        assert results == []

    def test_missing_csv_columns(self, tmp_path):
        """CSV with missing columns → graceful extraction."""
        csv_file = tmp_path / "partial.csv"
        csv_file.write_text("name,email\nAlice,alice@test.com\n")
        results = run_pipeline(str(tmp_path))
        assert len(results) == 1
        assert results[0]['full_name'] == 'Alice'
        assert 'alice@test.com' in results[0]['emails']
