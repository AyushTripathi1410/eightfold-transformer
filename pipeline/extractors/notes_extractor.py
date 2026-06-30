import re
import os
import logging
from typing import Any
from .base import BaseExtractor

logger = logging.getLogger(__name__)

KNOWN_SKILLS = {
    'python', 'java', 'javascript', 'typescript', 'go', 'golang', 'rust', 'c++', 'c#',
    'ruby', 'php', 'swift', 'kotlin', 'scala', 'r', 'matlab',
    'react', 'angular', 'vue', 'django', 'flask', 'fastapi', 'spring',
    'node.js', 'nodejs', 'express', 'next.js', 'nextjs',
    'docker', 'kubernetes', 'k8s', 'aws', 'gcp', 'azure',
    'terraform', 'ansible', 'jenkins', 'ci/cd',
    'postgresql', 'postgres', 'mysql', 'mongodb', 'redis', 'elasticsearch',
    'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy',
    'machine learning', 'ml', 'deep learning', 'nlp', 'computer vision',
    'sql', 'nosql', 'graphql', 'rest', 'grpc',
    'git', 'linux', 'agile', 'scrum',
    'html', 'css', 'sass', 'webpack',
    'spark', 'hadoop', 'kafka', 'airflow',
    'system design', 'microservices', 'distributed systems',
}

LINKEDIN_RE = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+', re.IGNORECASE)
GITHUB_RE = re.compile(r'(?:https?://)?(?:www\.)?github\.com/[\w\-]+', re.IGNORECASE)
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(
    r'(?:\+?1[\s.-]?)?'
    r'(?:\(?\d{3}\)?[\s.-]?)'
    r'\d{3}[\s.-]?\d{4}'
)


class NotesExtractor(BaseExtractor):
    """Extract candidate data from informal recruiter notes."""
    
    def extract(self, filepath: str) -> list[dict[str, Any]]:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read notes file {filepath}: {e}")
            return []
        
        candidate = self._empty_candidate('notes_txt', os.path.basename(filepath))
        
        candidate['full_name'] = self._extract_name(content)
        
        emails = EMAIL_RE.findall(content)
        candidate['emails'] = list(dict.fromkeys(emails))
        
        phones = PHONE_RE.findall(content)
        candidate['phones'] = list(dict.fromkeys(phones))
        
        linkedin = LINKEDIN_RE.findall(content)
        github = GITHUB_RE.findall(content)
        candidate['links'] = {
            'linkedin': linkedin[0] if linkedin else None,
            'github': github[0] if github else None,
            'portfolio': None,
            'other': [],
        }
        
        candidate['skills'] = self._extract_skills(content)
        
        years_match = re.search(r'(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience|exp)', content, re.IGNORECASE)
        if not years_match:
            years_match = re.search(r'(\d+)\s*years\s+experience', content, re.IGNORECASE)
        if years_match:
            candidate['years_experience'] = int(years_match.group(1))
        
        candidate['location'] = self._extract_location(content)
        
        return [candidate]
    
    def _extract_name(self, content: str) -> str | None:
        patterns = [
            r'[Cc]andidate:\s*(.+?)(?:\n|$)',
            r'[Nn]ame:\s*(.+?)(?:\n|$)',
            r'[Nn]otes?\s*[\u2014\u2013\-]+\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',  # "Notes — Alice Johnson"
            r'[Ss]poke\s+with\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'[Mm]et\s+with\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'[Ii]nterviewed\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                name = match.group(1).strip()
                name = re.sub(r'[.;,]+$', '', name).strip()
                if name and len(name) > 1:
                    return name
        return None
    
    def _extract_skills(self, content: str) -> list[str]:
        found_skills = []
        content_lower = content.lower()
        
        for skill in KNOWN_SKILLS:
            if len(skill) <= 2:
                pattern = r'\b' + re.escape(skill) + r'\b'
                if re.search(pattern, content_lower):
                    found_skills.append(skill)
            else:
                if skill in content_lower:
                    found_skills.append(skill)
        
        return list(dict.fromkeys(found_skills))
    
    def _extract_location(self, content: str) -> dict[str, str | None] | None:
        city_map = {
            'sf': 'San Francisco', 'san francisco': 'San Francisco',
            'nyc': 'New York', 'new york': 'New York',
            'la': 'Los Angeles', 'los angeles': 'Los Angeles',
            'sf bay area': 'San Francisco',
        }
        
        content_lower = content.lower()
        for key, city in city_map.items():
            if key in content_lower:
                region = None
                if 'san francisco' in city.lower() or 'los angeles' in city.lower():
                    region = 'CA'
                elif 'new york' in city.lower():
                    region = 'NY'
                return {'city': city, 'region': region, 'country': 'US'}
        
        return None
