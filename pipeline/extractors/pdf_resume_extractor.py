"""Extract candidate data from PDF/DOCX resume files."""

import re
import os
import logging
from typing import Any
from .base import BaseExtractor

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed; PDF resume extraction disabled")

try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    logger.warning("python-docx not installed; DOCX resume extraction disabled")

# Reuse regex patterns from resume_extractor
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(
    r'(?:\+?1[\s.-]?)?'
    r'(?:\(?\d{3}\)?[\s.-]?)'
    r'\d{3}[\s.-]?\d{4}'
)
LINKEDIN_RE = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+', re.IGNORECASE)
GITHUB_RE = re.compile(r'(?:https?://)?(?:www\.)?github\.com/[\w\-]+', re.IGNORECASE)
YEARS_EXP_RE = re.compile(r'(\d+)\+?\s*years?\s+(?:of\s+)?experience', re.IGNORECASE)

SECTION_HEADERS = re.compile(
    r'^\s*(SUMMARY|OBJECTIVE|SKILLS|TECHNICAL SKILLS|EXPERIENCE|WORK EXPERIENCE|'
    r'PROFESSIONAL EXPERIENCE|EDUCATION|PROJECTS|CERTIFICATIONS|AWARDS|PUBLICATIONS)\s*$',
    re.IGNORECASE | re.MULTILINE
)

COMPANY_TITLE_RE = re.compile(r'^([A-Z][A-Z\s,\.&]+?)\s*[\u2014\u2013\-]+\s*(.+)$')

DATE_RANGE_RE = re.compile(
    r'((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|\d{4}-\d{2})'
    r'\s*[-\u2013\u2014]+\s*'
    r'((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|\d{4}-\d{2}|[Pp]resent|[Cc]urrent)',
    re.IGNORECASE
)

EDU_INSTITUTION_RE = re.compile(r'^([A-Z][A-Z\s,\.]+)$')

DEGREE_RE = re.compile(
    r"^(Bachelor|Master|Doctor|Associate|B\.?S\.?|M\.?S\.?|Ph\.?D\.?|B\.?A\.?|M\.?A\.?|M\.?B\.?A\.?)\w*\s+(?:of\s+\w+\s+)?(?:in\s+)?(.+?)(?:\s*\|\s*(\d{4}))?$",
    re.IGNORECASE
)


class PDFResumeExtractor(BaseExtractor):
    """Extract candidate data from PDF resume files."""

    def extract(self, filepath: str) -> list[dict[str, Any]]:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pdf':
            text = self._extract_pdf_text(filepath)
        elif ext == '.docx':
            text = self._extract_docx_text(filepath)
        else:
            logger.warning(f"Unsupported resume format: {ext}")
            return []

        if not text or not text.strip():
            logger.warning(f"No text extracted from {filepath}")
            return []

        return self._parse_resume_text(text, filepath)

    def _extract_pdf_text(self, filepath: str) -> str:
        """Extract text from PDF using pdfplumber."""
        if not HAS_PDFPLUMBER:
            logger.error("pdfplumber not installed, cannot read PDF")
            return ""
        try:
            text_parts = []
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return '\n'.join(text_parts)
        except Exception as e:
            logger.error(f"Failed to extract text from PDF {filepath}: {e}")
            return ""

    def _extract_docx_text(self, filepath: str) -> str:
        """Extract text from DOCX using python-docx."""
        if not HAS_DOCX:
            logger.error("python-docx not installed, cannot read DOCX")
            return ""
        try:
            doc = docx.Document(filepath)
            return '\n'.join(para.text for para in doc.paragraphs)
        except Exception as e:
            logger.error(f"Failed to extract text from DOCX {filepath}: {e}")
            return ""

    def _parse_resume_text(self, content: str, filepath: str) -> list[dict[str, Any]]:
        """Parse extracted text using regex patterns (same logic as text resume)."""
        candidate = self._empty_candidate('resume_pdf', os.path.basename(filepath))

        lines = content.strip().split('\n')
        sections = self._split_sections(content)

        # Emails
        emails = EMAIL_RE.findall(content)
        candidate['emails'] = list(dict.fromkeys(emails))

        # Phones
        phones = PHONE_RE.findall(content)
        candidate['phones'] = list(dict.fromkeys(phones))

        # Name — first non-empty, non-contact line
        candidate['full_name'] = self._extract_name(lines)

        # Links
        linkedin = LINKEDIN_RE.findall(content)
        github = GITHUB_RE.findall(content)
        candidate['links'] = {
            'linkedin': ('https://' + linkedin[0] if linkedin and not linkedin[0].startswith('http') else linkedin[0]) if linkedin else None,
            'github': ('https://' + github[0] if github and not github[0].startswith('http') else github[0]) if github else None,
            'portfolio': None,
            'other': [],
        }

        # Headline
        summary_text = sections.get('summary') or sections.get('objective')
        if summary_text:
            candidate['headline'] = summary_text.strip().split('\n')[0].strip()[:200]

        # Years of experience
        yoe_match = YEARS_EXP_RE.search(content)
        if yoe_match:
            candidate['years_experience'] = int(yoe_match.group(1))

        # Skills
        skills_text = sections.get('skills') or sections.get('technical skills')
        if skills_text:
            candidate['skills'] = self._parse_skills(skills_text)

        # Experience
        exp_text = (sections.get('experience') or sections.get('work experience')
                    or sections.get('professional experience'))
        if exp_text:
            candidate['experience'] = self._parse_experience(exp_text)

        # Education
        edu_text = sections.get('education')
        if edu_text:
            candidate['education'] = self._parse_education(edu_text)

        return [candidate]

    def _extract_name(self, lines: list[str]) -> str | None:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.match(r'^[=\-_]{5,}$', line):
                continue
            if EMAIL_RE.search(line) or PHONE_RE.search(line):
                continue
            if line.lower().startswith(('email:', 'phone:', 'linkedin:', 'github:', 'http')):
                continue
            if SECTION_HEADERS.match(line):
                continue
            name = re.sub(r'[|\u2022\u00b7]', ' ', line).strip()
            name = re.sub(r'\s+', ' ', name).strip()
            if name and 1 < len(name) < 60:
                return name
        return None

    def _split_sections(self, content: str) -> dict[str, str]:
        sections = {}
        matches = list(SECTION_HEADERS.finditer(content))
        for i, match in enumerate(matches):
            header = match.group(1).strip().lower()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_text = content[start:end].strip()
            section_text = re.sub(r'^[\-=]{3,}\s*\n?', '', section_text).strip()
            sections[header] = section_text
        return sections

    def _parse_skills(self, text: str) -> list[str]:
        skills = []
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or re.match(r'^[=\-]{3,}$', line):
                continue
            if ':' in line:
                line = line.split(':', 1)[1].strip()

            def expand_parens(match):
                main = match.group(1).strip()
                subs = match.group(2).strip()
                return f"{main}, {subs}"

            line = re.sub(r'(\w[\w\s\+\#\.]*?)\s*\(([^)]+)\)', expand_parens, line)
            parts = re.split(r'[,|/;\u2022\u00b7]', line)
            for part in parts:
                s = part.strip('() ').strip()
                if s and len(s) > 1 and len(s) < 50:
                    skills.append(s)
        return skills

    def _parse_experience(self, text: str) -> list[dict]:
        entries = []
        lines = text.strip().split('\n')
        current_entry = None
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or re.match(r'^[=\-]{3,}$', line):
                continue

            company_match = COMPANY_TITLE_RE.match(line)
            if company_match:
                if current_entry:
                    entries.append(current_entry)
                company = company_match.group(1).strip().title()
                title = company_match.group(2).strip()
                start, end = None, None
                if i < len(lines):
                    next_line = lines[i].strip()
                    date_match = DATE_RANGE_RE.search(next_line)
                    if date_match:
                        start = date_match.group(1)
                        end_str = date_match.group(2)
                        end = None if end_str.lower() in ('present', 'current') else end_str
                        i += 1
                current_entry = {
                    'company': company, 'title': title,
                    'start': start, 'end': end, 'summary': '',
                }
            elif line.startswith('-') or line.startswith('\u2022'):
                if current_entry:
                    bullet = line.lstrip('-\u2022\u00b7 ').strip()
                    if current_entry['summary']:
                        current_entry['summary'] += '; ' + bullet
                    else:
                        current_entry['summary'] = bullet

        if current_entry:
            entries.append(current_entry)
        return entries

    def _parse_education(self, text: str) -> list[dict]:
        entries = []
        lines = text.strip().split('\n')
        current_institution = None

        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or line.startswith('\u2022') or re.match(r'^[=\-]{3,}$', line):
                continue
            
            # Check if this line is a school/institution
            is_inst = False
            if any(kw in line.lower() for kw in ['university', 'college', 'institute', 'school', 'academy', 'stanford', 'berkeley', 'polytechnic', 'uc ']):
                is_inst = True
            elif EDU_INSTITUTION_RE.match(line) and len(line) > 3:
                is_inst = True
                
            if is_inst:
                current_institution = line.title()
                continue
                
            degree_match = DEGREE_RE.match(line)
            if degree_match and current_institution:
                degree = degree_match.group(1).strip()
                field = degree_match.group(2).strip()
                year_str = degree_match.group(3)
                end_year = int(year_str) if year_str else None
                if end_year is None:
                    pipe_match = re.search(r'\|\s*(\d{4})', line)
                    if pipe_match:
                        end_year = int(pipe_match.group(1))
                        field = re.sub(r'\s*\|\s*\d{4}', '', field).strip()
                entries.append({
                    'institution': current_institution,
                    'degree': degree, 'field': field,
                    'end_year': end_year,
                })
                current_institution = None
                continue
            # Fallback: institution name not all-caps (PDF text extraction may vary)
            year_match = re.search(r'\b(19|20)\d{2}\b', line)
            if year_match and '|' in line:
                parts = line.split('|')
                deg_field = parts[0].strip()
                year = int(year_match.group(0))
                if current_institution:
                    deg_parts = deg_field.split(None, 1)
                    entries.append({
                        'institution': current_institution,
                        'degree': deg_parts[0] if deg_parts else None,
                        'field': deg_parts[1] if len(deg_parts) > 1 else None,
                        'end_year': year,
                    })
                    current_institution = None

        return entries
