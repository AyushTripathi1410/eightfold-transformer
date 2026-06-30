import re
import os
import logging
from typing import Any
from .base import BaseExtractor

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(
    r'(?:\+?1[\s.-]?)?'
    r'(?:\(?\d{3}\)?[\s.-]?)'
    r'\d{3}[\s.-]?\d{4}'
)
LINKEDIN_RE = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+', re.IGNORECASE)
GITHUB_RE = re.compile(r'(?:https?://)?(?:www\.)?github\.com/[\w\-]+', re.IGNORECASE)
YEARS_EXP_RE = re.compile(r'(\d+)\+?\s*years?\s+(?:of\s+)?experience', re.IGNORECASE)
DATE_RANGE_RE = re.compile(
    r'((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|\d{4}-\d{2}|\d{2}/\d{4})'
    r'\s*[-\u2013\u2014]+\s*'
    r'((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|\d{4}-\d{2}|\d{2}/\d{4}|[Pp]resent|[Cc]urrent)',
    re.IGNORECASE
)

SECTION_HEADERS = re.compile(
    r'^\s*(SUMMARY|OBJECTIVE|SKILLS|TECHNICAL SKILLS|EXPERIENCE|WORK EXPERIENCE|'
    r'PROFESSIONAL EXPERIENCE|EDUCATION|PROJECTS|CERTIFICATIONS|AWARDS|PUBLICATIONS)\s*$',
    re.IGNORECASE | re.MULTILINE
)

# Pattern for "COMPANY — Title" or "COMPANY - Title" (experience header)
COMPANY_TITLE_RE = re.compile(
    r'^([A-Z][A-Z\s,\.&]+?)\s*[\u2014\u2013\-]+\s*(.+)$'
)

# Pattern for education: "INSTITUTION NAME" on its own line (all caps)
EDU_INSTITUTION_RE = re.compile(r'^([A-Z][A-Z\s,\.]+)$')

# Pattern for degree lines: "Master of Science in Computer Science | 2019"
DEGREE_RE = re.compile(
    r"^(Bachelor|Master|Doctor|Associate|B\.?S\.?|M\.?S\.?|Ph\.?D\.?|B\.?A\.?|M\.?A\.?|M\.?B\.?A\.?)\w*\s+(?:of\s+\w+\s+)?(?:in\s+)?(.+?)(?:\s*\|\s*(\d{4}))?$",
    re.IGNORECASE
)


class ResumeExtractor(BaseExtractor):
    """Extract candidate data from free-text resume files."""
    
    def extract(self, filepath: str) -> list[dict[str, Any]]:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read resume file {filepath}: {e}")
            return []
        
        candidate = self._empty_candidate('resume_txt', os.path.basename(filepath))
        
        lines = content.strip().split('\n')
        sections = self._split_sections(content)
        
        emails = EMAIL_RE.findall(content)
        candidate['emails'] = list(dict.fromkeys(emails))
        
        phones = PHONE_RE.findall(content)
        candidate['phones'] = list(dict.fromkeys(phones))
        
        candidate['full_name'] = self._extract_name(lines)
        
        linkedin = LINKEDIN_RE.findall(content)
        github = GITHUB_RE.findall(content)
        candidate['links'] = {
            'linkedin': ('https://' + linkedin[0] if linkedin and not linkedin[0].startswith('http') else linkedin[0]) if linkedin else None,
            'github': ('https://' + github[0] if github and not github[0].startswith('http') else github[0]) if github else None,
            'portfolio': None,
            'other': [],
        }
        
        summary_text = sections.get('summary') or sections.get('objective')
        if summary_text:
            # Get first meaningful paragraph as headline
            para = summary_text.strip().split('\n')[0].strip()
            candidate['headline'] = para[:200] if para else None
        
        yoe_match = YEARS_EXP_RE.search(content)
        if yoe_match:
            candidate['years_experience'] = int(yoe_match.group(1))
        
        skills_text = sections.get('skills') or sections.get('technical skills')
        if skills_text:
            candidate['skills'] = self._parse_skills(skills_text)
        
        exp_text = (sections.get('experience') or sections.get('work experience') 
                    or sections.get('professional experience'))
        if exp_text:
            candidate['experience'] = self._parse_experience(exp_text)
        
        edu_text = sections.get('education')
        if edu_text:
            candidate['education'] = self._parse_education(edu_text)
        
        if candidate['years_experience'] is None and candidate['experience']:
            candidate['years_experience'] = self._calc_years(candidate['experience'])
        
        return [candidate]
    
    def _extract_name(self, lines: list[str]) -> str | None:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip separator lines
            if re.match(r'^[=\-_]{5,}$', line):
                continue
            if EMAIL_RE.search(line) or PHONE_RE.search(line):
                continue
            if line.lower().startswith(('email:', 'phone:', 'linkedin:', 'github:', 'http')):
                continue
            if SECTION_HEADERS.match(line):
                continue
            # First non-header, non-contact line is likely the name
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
            # Strip separator lines (---, ===)
            section_text = re.sub(r'^[\-=]{3,}\s*\n?', '', section_text).strip()
            sections[header] = section_text
        return sections
    
    def _parse_skills(self, text: str) -> list[str]:
        """Parse skills from lines like 'Languages: Python, Java, Go'."""
        skills = []
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or re.match(r'^[=\-]{3,}$', line):
                continue
            # Strip category prefix like "Languages:", "Cloud & DevOps:"
            if ':' in line:
                line = line.split(':', 1)[1].strip()
            
            # First, expand parenthetical sub-skills:
            # "AWS (EC2, S3, Lambda, SageMaker)" → "AWS, EC2, S3, Lambda, SageMaker"
            def expand_parens(match):
                main = match.group(1).strip()
                subs = match.group(2).strip()
                return f"{main}, {subs}"
            
            line = re.sub(r'(\w[\w\s\+\#\.]*?)\s*\(([^)]+)\)', expand_parens, line)
            
            # Split by commas, pipes, bullets
            parts = re.split(r'[,|;\u2022\u00b7]', line)
            for part in parts:
                s = part.strip()
                # Clean up any remaining parens
                s = s.strip('()').strip()
                if s and len(s) > 1 and len(s) < 50:
                    skills.append(s)
        return skills
    
    def _parse_experience(self, text: str) -> list[dict]:
        """Parse experience entries in format:
        COMPANY — Title
        Location | Date Range
        - bullet points
        """
        entries = []
        lines = text.strip().split('\n')
        current_entry = None
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            
            if not line or re.match(r'^[=\-]{3,}$', line):
                continue
            
            # Check for "COMPANY — Title" pattern
            company_match = COMPANY_TITLE_RE.match(line)
            if company_match:
                if current_entry:
                    entries.append(current_entry)
                
                company = company_match.group(1).strip().title()
                title = company_match.group(2).strip()
                
                start = None
                end = None
                
                # Look at the next line for location and dates
                if i < len(lines):
                    next_line = lines[i].strip()
                    date_match = DATE_RANGE_RE.search(next_line)
                    if date_match:
                        start = date_match.group(1)
                        end_str = date_match.group(2)
                        end = None if end_str.lower() in ('present', 'current') else end_str
                        i += 1  # consume the date line
                
                current_entry = {
                    'company': company,
                    'title': title,
                    'start': start,
                    'end': end,
                    'summary': '',
                }
            elif line.startswith('-') or line.startswith('•'):
                if current_entry:
                    bullet = line.lstrip('-•· ').strip()
                    # Handle multi-line bullets (continuation on next line)
                    while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(('-', '•')) and not COMPANY_TITLE_RE.match(lines[i].strip()):
                        next_line = lines[i].strip()
                        if re.match(r'^[=\-]{3,}$', next_line):
                            break
                        if next_line and not next_line[0].isupper() or (next_line and next_line[0].islower()):
                            bullet += ' ' + next_line
                            i += 1
                        else:
                            break
                    if current_entry['summary']:
                        current_entry['summary'] += '; ' + bullet
                    else:
                        current_entry['summary'] = bullet
        
        if current_entry:
            entries.append(current_entry)
        
        return entries
    
    def _parse_education(self, text: str) -> list[dict]:
        """Parse education entries in format:
        INSTITUTION NAME
        Degree in Field | Year
        - bullet points
        """
        entries = []
        lines = text.strip().split('\n')
        
        current_institution = None
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or line.startswith('•') or re.match(r'^[=\-]{3,}$', line):
                continue
            
            # Check if this is an institution name (all caps, no degree keywords)
            if EDU_INSTITUTION_RE.match(line) and len(line) > 3:
                current_institution = line.title()
                continue
            
            # Check for degree line
            degree_match = DEGREE_RE.match(line)
            if degree_match and current_institution:
                degree = degree_match.group(1).strip()
                field = degree_match.group(2).strip()
                year_str = degree_match.group(3)
                end_year = int(year_str) if year_str else None
                
                # Also check for year with pipe separator
                if end_year is None:
                    pipe_match = re.search(r'\|\s*(\d{4})', line)
                    if pipe_match:
                        end_year = int(pipe_match.group(1))
                        # Clean field of pipe and year
                        field = re.sub(r'\s*\|\s*\d{4}', '', field).strip()
                
                entries.append({
                    'institution': current_institution,
                    'degree': degree,
                    'field': field,
                    'end_year': end_year,
                })
                current_institution = None  # reset after consuming
                continue
            
            # Fallback: line with a year and institution context
            year_match = re.search(r'\b(19|20)\d{2}\b', line)
            if year_match and current_institution is None:
                # This might be an institution line with year
                year = int(year_match.group(0))
                inst = re.sub(r'\|\s*\d{4}', '', line).strip()
                if inst and len(inst) > 3:
                    entries.append({
                        'institution': inst.title(),
                        'degree': None,
                        'field': None,
                        'end_year': year,
                    })
        
        return entries
    
    def _calc_years(self, experience: list[dict]) -> int | None:
        from dateutil import parser as date_parser
        from datetime import datetime
        
        min_start = None
        for exp in experience:
            start = exp.get('start')
            if start:
                try:
                    dt = date_parser.parse(start, fuzzy=True)
                    if min_start is None or dt < min_start:
                        min_start = dt
                except Exception:
                    continue
        
        if min_start:
            years = (datetime.now() - min_start).days // 365
            return max(1, years)
        return None
