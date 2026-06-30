"""Extract candidate data from GitHub profile URL using the public REST API."""

import re
import os
import json
import logging
from typing import Any
from .base import BaseExtractor

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not installed; GitHub API extraction disabled")

GITHUB_API_BASE = 'https://api.github.com'


class GitHubExtractor(BaseExtractor):
    """Extract candidate data from a GitHub profile via the public REST API.
    
    Reads a .github file containing a GitHub profile URL or username,
    then fetches profile info, repos, and languages from the API.
    """

    def extract(self, filepath: str) -> list[dict[str, Any]]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
        except Exception as e:
            logger.error(f"Failed to read GitHub URL file {filepath}: {e}")
            return []

        username = self._parse_username(content)
        if not username:
            logger.warning(f"Could not parse GitHub username from {filepath}")
            return []

        if not HAS_REQUESTS:
            logger.warning("requests not installed; cannot fetch GitHub API")
            return []

        candidate = self._empty_candidate('github_url', os.path.basename(filepath))
        
        # Fetch user profile
        profile = self._fetch_profile(username)
        if not profile:
            logger.warning(f"Failed to fetch GitHub profile for {username}")
            return []
        
        candidate['full_name'] = profile.get('name')
        
        # If GitHub profile has no public name, we can't merge it reliably
        if not candidate['full_name']:
            logger.warning(f"GitHub user '{username}' has no public name; skipping")
            return []
        
        email = profile.get('email')
        if email:
            candidate['emails'] = [email]
        
        bio = profile.get('bio')
        if bio:
            candidate['headline'] = bio.strip()[:200]

        location = profile.get('location')
        if location:
            candidate['location'] = self._parse_location(location)

        candidate['links'] = {
            'linkedin': None,
            'github': profile.get('html_url') or f'https://github.com/{username}',
            'portfolio': profile.get('blog') or None,
            'other': [],
        }

        # Fetch repos to extract languages/skills
        languages = self._fetch_languages(username)
        if languages:
            candidate['skills'] = list(languages)

        return [candidate]

    def _parse_username(self, content: str) -> str | None:
        """Extract GitHub username from URL or raw username."""
        content = content.strip()
        # URL format: https://github.com/username
        match = re.match(r'(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9\-]+)', content)
        if match:
            return match.group(1)
        # Raw username
        if re.match(r'^[a-zA-Z0-9\-]+$', content):
            return content
        return None

    def _fetch_profile(self, username: str) -> dict | None:
        """Fetch user profile from GitHub REST API."""
        try:
            url = f'{GITHUB_API_BASE}/users/{username}'
            resp = requests.get(url, timeout=10, headers={'Accept': 'application/vnd.github.v3+json'})
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                logger.warning(f"GitHub user not found: {username}")
            elif resp.status_code == 403:
                logger.warning(f"GitHub API rate limited for {username}")
            else:
                logger.warning(f"GitHub API returned {resp.status_code} for {username}")
            return None
        except requests.RequestException as e:
            logger.warning(f"GitHub API request failed for {username}: {e}")
            return None

    def _fetch_languages(self, username: str) -> set[str]:
        """Fetch programming languages from user's repos."""
        languages = set()
        try:
            url = f'{GITHUB_API_BASE}/users/{username}/repos'
            resp = requests.get(url, params={'sort': 'updated', 'per_page': 30},
                              timeout=10, headers={'Accept': 'application/vnd.github.v3+json'})
            if resp.status_code == 200:
                repos = resp.json()
                for repo in repos:
                    lang = repo.get('language')
                    if lang:
                        languages.add(lang)
            return languages
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch repos for {username}: {e}")
            return languages

    def _parse_location(self, location_str: str) -> dict[str, str | None]:
        """Parse location string from GitHub profile."""
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if parts else None
        region = parts[1] if len(parts) > 1 else None
        country = parts[2] if len(parts) > 2 else None
        # Default to US if looks like a US city/state
        if not country and region and len(region) == 2 and region.isupper():
            country = 'US'
        return {'city': city, 'region': region, 'country': country}
