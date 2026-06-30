from abc import ABC, abstractmethod
from typing import Any


class BaseExtractor(ABC):
    """Abstract base class for candidate data extractors."""
    
    @abstractmethod
    def extract(self, filepath: str) -> list[dict[str, Any]]:
        """Extract candidate data from a file.
        
        Returns a list of RawCandidate dicts.
        """
        pass
    
    def _empty_candidate(self, source_type: str, source_file: str) -> dict[str, Any]:
        """Return a blank RawCandidate dict with all fields initialized."""
        return {
            'source_type': source_type,
            'source_file': source_file,
            'full_name': None,
            'emails': [],
            'phones': [],
            'location': None,
            'links': None,
            'headline': None,
            'years_experience': None,
            'skills': [],
            'experience': [],
            'education': [],
        }
