import csv
import os
import re
import logging
from typing import Any
from .base import BaseExtractor

logger = logging.getLogger(__name__)

US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
}

STATE_NAMES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN',
    'mississippi': 'MS', 'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE',
    'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
    'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC',
    'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK', 'oregon': 'OR',
    'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA',
    'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
    'district of columbia': 'DC'
}


class CSVExtractor(BaseExtractor):
    """Extract candidate data from recruiter CSV exports."""
    
    def extract(self, filepath: str) -> list[dict[str, Any]]:
        candidates = []
        try:
            with open(filepath, 'r', encoding='utf-8-sig', errors='replace') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        candidate = self._parse_row(row, filepath)
                        candidates.append(candidate)
                    except Exception as e:
                        logger.warning(f"Failed to parse CSV row in {filepath}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to read CSV file {filepath}: {e}")
        return candidates
    
    def _parse_row(self, row: dict, filepath: str) -> dict[str, Any]:
        candidate = self._empty_candidate('recruiter_csv', os.path.basename(filepath))
        
        name = row.get('name', '').strip()
        if name:
            candidate['full_name'] = name
        
        email = row.get('email', '').strip()
        if email:
            candidate['emails'] = [email]
        
        phone = row.get('phone', '').strip()
        if phone:
            candidate['phones'] = [phone]
        
        location_str = row.get('location', '').strip()
        if location_str:
            candidate['location'] = self._parse_location(location_str)
        
        skills_str = row.get('skills', '').strip()
        if skills_str:
            candidate['skills'] = [s.strip() for s in re.split(r'[,/|;]', skills_str) if s.strip()]
        
        company = row.get('current_company', '').strip()
        title = row.get('title', '').strip()
        if company or title:
            candidate['experience'] = [{
                'company': company or None,
                'title': title or None,
                'start': None,
                'end': None,
                'summary': None,
            }]
            if title:
                candidate['headline'] = title
        
        return candidate
    
    def _parse_location(self, location_str: str) -> dict[str, str | None]:
        """Parse location string like 'San Francisco CA' or 'Palo Alto California'."""
        parts = location_str.strip().split()
        city = None
        region = None
        country = 'US'
        
        if not parts:
            return {'city': None, 'region': None, 'country': country}
        
        last = parts[-1]
        if last.upper() in US_STATES:
            region = last.upper()
            city = ' '.join(parts[:-1]) if len(parts) > 1 else None
        elif last.lower() in STATE_NAMES:
            region = STATE_NAMES[last.lower()]
            city = ' '.join(parts[:-1]) if len(parts) > 1 else None
        else:
            for n_words in range(3, 0, -1):
                if len(parts) >= n_words + 1:
                    potential_state = ' '.join(parts[-n_words:]).lower()
                    if potential_state in STATE_NAMES:
                        region = STATE_NAMES[potential_state]
                        city = ' '.join(parts[:-n_words])
                        break
            if region is None:
                city = location_str.strip()
        
        return {'city': city or None, 'region': region, 'country': country}
