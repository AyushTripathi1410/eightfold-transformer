import os
import re
import logging

logger = logging.getLogger(__name__)

def detect_source_type(filepath: str) -> str:
    """Detect the source type of a candidate data file.
    
    Returns one of: 'recruiter_csv', 'ats_json', 'resume_txt', 'resume_pdf',
                     'notes_txt', 'github_url', 'unknown'
    """
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == '.csv':
        return 'recruiter_csv'
    elif ext == '.json':
        return 'ats_json'
    elif ext == '.pdf':
        return 'resume_pdf'
    elif ext == '.docx':
        return 'resume_pdf'  # Same extractor handles both PDF and DOCX
    elif ext == '.github':
        return 'github_url'
    elif ext == '.txt':
        return _classify_text_file(filepath)
    else:
        return 'unknown'

def _classify_text_file(filepath: str) -> str:
    """Classify a .txt file as resume or notes using heuristics."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        logger.warning(f"Cannot read file {filepath}: {e}")
        return 'unknown'
    
    lines = content.strip().split('\n')
    
    # Resume indicators: look for section HEADERS (standalone lines)
    resume_section_re = re.compile(
        r'^\s*(EDUCATION|EXPERIENCE|WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|'
        r'SKILLS|TECHNICAL SKILLS|SUMMARY|OBJECTIVE|PROJECTS|CERTIFICATIONS)\s*$',
        re.IGNORECASE
    )
    resume_score = sum(1 for line in lines if resume_section_re.match(line.strip()))
    
    # Notes indicators: look for conversational patterns
    notes_patterns = [
        r'(?i)\brecruiter\s+notes?\b',
        r'(?i)\bspoke\s+with\b',
        r'(?i)\bmet\s+with\b',
        r'(?i)\binterviewer?\s+observations?\b',
        r'(?i)\bphone\s+screen\b',
        r'(?i)\bon-?site\b',
        r'(?i)\bhire\s+candidate\b',
        r'(?i)\bfollow[\s-]?up\b',
        r'(?i)\brecommend\s+moving\b',
        r'(?i)\boverall\s+impression\b',
        r'(?i)\bsalary\b',
        r'(?i)\bnext\s+round\b',
        r'(?i)\bfeedback\b',
        r'(?i)\bcandidate:\b',
    ]
    notes_score = sum(1 for pattern in notes_patterns if re.search(pattern, content))
    
    if resume_score >= 3:
        return 'resume_txt'
    if notes_score >= 3:
        return 'notes_txt'
    if resume_score >= 2 and notes_score <= 1:
        return 'resume_txt'
    if notes_score >= 2 and resume_score <= 1:
        return 'notes_txt'
    if resume_score > notes_score:
        return 'resume_txt'
    elif notes_score > resume_score:
        return 'notes_txt'
    
    # Filename hint as tiebreaker
    basename = os.path.basename(filepath).lower()
    if 'resume' in basename or 'cv' in basename:
        return 'resume_txt'
    if 'note' in basename or 'feedback' in basename or 'interview' in basename:
        return 'notes_txt'
    
    return 'unknown'
