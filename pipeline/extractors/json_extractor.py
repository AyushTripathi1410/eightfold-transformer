import json
import os
import logging
from typing import Any
from .base import BaseExtractor

logger = logging.getLogger(__name__)


class JSONExtractor(BaseExtractor):
    """Extract candidate data from ATS JSON exports."""
    
    def extract(self, filepath: str) -> list[dict[str, Any]]:
        candidates = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read JSON file {filepath}: {e}")
            return []
        
        # Handle various JSON structures
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Check for nested candidates key (common ATS pattern)
            if 'candidates' in data and isinstance(data['candidates'], list):
                items = data['candidates']
            elif 'applicants' in data and isinstance(data['applicants'], list):
                items = data['applicants']
            elif 'data' in data and isinstance(data['data'], list):
                items = data['data']
            else:
                items = [data]
        else:
            logger.warning(f"Unexpected JSON structure in {filepath}")
            return []
        
        for item in items:
            try:
                candidate = self._map_candidate(item, filepath)
                candidates.append(candidate)
            except Exception as e:
                logger.warning(f"Failed to map JSON candidate in {filepath}: {e}")
                continue
        
        return candidates
    
    def _map_candidate(self, item: dict, filepath: str) -> dict[str, Any]:
        candidate = self._empty_candidate('ats_json', os.path.basename(filepath))
        
        candidate['full_name'] = (
            item.get('applicant_name') or item.get('name') or item.get('full_name')
        )
        
        email = item.get('contact_email') or item.get('email')
        if email:
            candidate['emails'] = [email] if isinstance(email, str) else list(email)
        
        phone = item.get('contact_phone') or item.get('phone')
        if phone:
            candidate['phones'] = [str(phone)] if not isinstance(phone, list) else [str(p) for p in phone]
        
        city = item.get('city')
        state = item.get('state')
        country = item.get('country_code') or item.get('country')
        if city or state or country:
            candidate['location'] = {
                'city': city,
                'region': state,
                'country': country,
            }
        
        tech_stack = item.get('tech_stack') or item.get('skills', [])
        if isinstance(tech_stack, list):
            candidate['skills'] = [str(s) for s in tech_stack]
        elif isinstance(tech_stack, str):
            candidate['skills'] = [s.strip() for s in tech_stack.split(',') if s.strip()]
        
        role = item.get('role') or item.get('title')
        org = item.get('organization') or item.get('company')
        if role:
            candidate['headline'] = f"{role} at {org}" if org else role
        
        work_history = item.get('work_history') or item.get('experience', [])
        if isinstance(work_history, list):
            for wh in work_history:
                if not isinstance(wh, dict):
                    continue
                exp = {
                    'company': wh.get('company') or wh.get('company_name'),
                    'title': wh.get('title') or wh.get('job_title'),
                    'start': wh.get('start_date') or wh.get('start'),
                    'end': wh.get('end_date') or wh.get('end'),
                    'summary': wh.get('description') or wh.get('summary'),
                }
                candidate['experience'].append(exp)
        
        edu_history = item.get('education_history') or item.get('education', [])
        if isinstance(edu_history, list):
            for eh in edu_history:
                if not isinstance(eh, dict):
                    continue
                edu = {
                    'institution': eh.get('school') or eh.get('institution'),
                    'degree': eh.get('degree') or eh.get('degree_type'),
                    'field': eh.get('major') or eh.get('field'),
                    'end_year': eh.get('graduation_year') or eh.get('end_year'),
                }
                candidate['education'].append(edu)
        
        return candidate
