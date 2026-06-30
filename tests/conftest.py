import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

SAMPLE_DIR = os.path.join(PROJECT_ROOT, 'sample_inputs')
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'configs', 'default_config.json')
SCHEMA_PATH = os.path.join(PROJECT_ROOT, 'schema', 'canonical_schema.json')


@pytest.fixture
def sample_dir():
    return SAMPLE_DIR


@pytest.fixture
def config_path():
    return CONFIG_PATH


@pytest.fixture
def schema_path():
    return SCHEMA_PATH


@pytest.fixture
def sample_csv_path():
    return os.path.join(SAMPLE_DIR, 'recruiter_export.csv')


@pytest.fixture
def sample_json_path():
    return os.path.join(SAMPLE_DIR, 'ats_export.json')


@pytest.fixture
def sample_resume_path():
    return os.path.join(SAMPLE_DIR, 'alice_resume.txt')


@pytest.fixture
def sample_notes_path():
    return os.path.join(SAMPLE_DIR, 'alice_notes.txt')
