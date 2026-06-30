"""Normalize extracted candidate data to canonical formats."""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import phonenumbers
    HAS_PHONENUMBERS = True
except ImportError:
    HAS_PHONENUMBERS = False
    logger.warning("phonenumbers not installed; phone normalization disabled")

try:
    import pycountry
    HAS_PYCOUNTRY = True
except ImportError:
    HAS_PYCOUNTRY = False
    logger.warning("pycountry not installed; country normalization disabled")

# ── Skill alias map ──────────────────────────────────────────────────────────
SKILL_ALIASES = {
    'js': 'javascript',
    'typescript': 'typescript',
    'ts': 'typescript',
    'ml': 'machine learning',
    'k8s': 'kubernetes',
    'react.js': 'react',
    'reactjs': 'react',
    'react js': 'react',
    'node': 'node.js',
    'nodejs': 'node.js',
    'node js': 'node.js',
    'postgres': 'postgresql',
    'psql': 'postgresql',
    'tf': 'tensorflow',
    'gcp': 'google cloud',
    'aws': 'aws',
    'amazon web services': 'aws',
    'ci/cd': 'ci/cd',
    'ci cd': 'ci/cd',
    'cicd': 'ci/cd',
    'docker': 'docker',
    'go': 'go',
    'golang': 'go',
    'py': 'python',
    'cpp': 'c++',
    'c plus plus': 'c++',
    'csharp': 'c#',
    'c sharp': 'c#',
}

# ── US state name → abbreviation ─────────────────────────────────────────────
STATE_NAMES_TO_ABBR = {
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
    'district of columbia': 'DC',
}

# ── Month names ──────────────────────────────────────────────────────────────
MONTH_MAP = {
    'jan': '01', 'january': '01', 'feb': '02', 'february': '02',
    'mar': '03', 'march': '03', 'apr': '04', 'april': '04',
    'may': '05', 'jun': '06', 'june': '06',
    'jul': '07', 'july': '07', 'aug': '08', 'august': '08',
    'sep': '09', 'sept': '09', 'september': '09',
    'oct': '10', 'october': '10', 'nov': '11', 'november': '11',
    'dec': '12', 'december': '12',
}

# ── Country aliases ──────────────────────────────────────────────────────────
COUNTRY_ALIASES = {
    'us': 'US', 'usa': 'US', 'united states': 'US', 'united states of america': 'US',
    'uk': 'GB', 'united kingdom': 'GB', 'great britain': 'GB',
    'canada': 'CA', 'india': 'IN', 'germany': 'DE', 'france': 'FR',
    'australia': 'AU', 'japan': 'JP', 'china': 'CN', 'brazil': 'BR',
    'mexico': 'MX', 'spain': 'ES', 'italy': 'IT', 'netherlands': 'NL',
    'south korea': 'KR', 'singapore': 'SG', 'israel': 'IL',
}


def normalize_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a RawCandidate dict in place and return it."""
    result = dict(raw)  # shallow copy

    # Name
    if result.get('full_name'):
        result['full_name'] = _normalize_name(result['full_name'])

    # Emails
    if result.get('emails'):
        result['emails'] = list({e.strip().lower() for e in result['emails'] if e and e.strip()})

    # Phones — normalize and filter invalid
    if result.get('phones'):
        normalized_phones = []
        for p in result['phones']:
            if p:
                norm = _normalize_phone(p)
                if norm and norm.startswith('+'):
                    normalized_phones.append(norm)
                else:
                    logger.debug(f"Dropping unparseable phone: {p}")
        result['phones'] = normalized_phones

    # Location
    if result.get('location') and isinstance(result['location'], dict):
        loc = result['location']
        for k in ['city', 'region', 'country']:
            if loc.get(k) and isinstance(loc[k], str):
                loc[k] = loc[k].strip(',. ')
        if loc.get('region'):
            loc['region'] = _normalize_region(loc['region'])
        if loc.get('country'):
            loc['country'] = _normalize_country(loc['country'])
        elif loc.get('region'):
            # Default to US if region looks like a US state
            loc['country'] = 'US'

    # Skills
    if result.get('skills'):
        result['skills'] = _normalize_skills(result['skills'])

    # Experience dates
    if result.get('experience'):
        for exp in result['experience']:
            if exp.get('start'):
                exp['start'] = _normalize_date(exp['start'])
            if exp.get('end'):
                exp['end'] = _normalize_date(exp['end'])

    # Education end_year
    if result.get('education'):
        for edu in result['education']:
            if edu.get('end_year') and isinstance(edu['end_year'], str):
                try:
                    edu['end_year'] = int(edu['end_year'])
                except (ValueError, TypeError):
                    edu['end_year'] = None

    # Headline
    if result.get('headline'):
        result['headline'] = result['headline'].strip()

    return result


def _normalize_name(name: str) -> str:
    """Title-case and strip extra whitespace."""
    return ' '.join(name.strip().split()).title()


def _normalize_phone(phone: str) -> str:
    """Parse and format phone to E.164 using phonenumbers lib."""
    if not phone or not phone.strip():
        return phone

    raw = phone.strip()

    if HAS_PHONENUMBERS:
        try:
            parsed = phonenumbers.parse(raw, 'US')
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            else:
                logger.debug(f"Invalid phone number: {raw}")
                return raw
        except phonenumbers.NumberParseException:
            logger.debug(f"Cannot parse phone number: {raw}")
            return raw

    # Fallback: strip non-digits, prepend +1 if 10 digits
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f'+1{digits}'
    elif len(digits) == 11 and digits[0] == '1':
        return f'+{digits}'
    return raw


def _normalize_date(date_str: str) -> str | None:
    """Normalize various date formats to YYYY-MM."""
    if not date_str:
        return None

    s = date_str.strip()

    # Handle 'Present', 'Current', etc.
    if s.lower() in ('present', 'current', 'now', 'ongoing', ''):
        return None

    # Already YYYY-MM
    if re.match(r'^\d{4}-(0[1-9]|1[0-2])$', s):
        return s

    # YYYY-MM-DD → YYYY-MM
    m = re.match(r'^(\d{4})-(0[1-9]|1[0-2])-\d{2}$', s)
    if m:
        return f'{m.group(1)}-{m.group(2)}'

    # Month YYYY (e.g., "Mar 2022", "March 2022")
    m = re.match(r'^([A-Za-z]+)\s+(\d{4})$', s)
    if m:
        month_str = m.group(1).lower()
        year = m.group(2)
        month = MONTH_MAP.get(month_str)
        if month:
            return f'{year}-{month}'

    # MM/YYYY
    m = re.match(r'^(\d{1,2})/(\d{4})$', s)
    if m:
        month = int(m.group(1))
        year = m.group(2)
        if 1 <= month <= 12:
            return f'{year}-{month:02d}'

    # YYYY only → YYYY-01
    m = re.match(r'^(\d{4})$', s)
    if m:
        return f'{m.group(1)}-01'

    logger.debug(f"Cannot parse date: {s}")
    return s  # Return as-is rather than losing data


def _normalize_skills(skills: list[str]) -> list[str]:
    """Canonicalize skill names, deduplicate."""
    normalized = []
    seen = set()
    for skill in skills:
        if not skill or not skill.strip():
            continue
        canonical = skill.strip().lower()
        canonical = SKILL_ALIASES.get(canonical, canonical)
        if canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)
    return normalized


def _normalize_region(region: str) -> str:
    """Normalize state/region to abbreviation."""
    if not region:
        return region
    r = region.strip()
    # Already an abbreviation (2 uppercase letters)
    if re.match(r'^[A-Z]{2}$', r):
        return r
    # Look up full name
    abbr = STATE_NAMES_TO_ABBR.get(r.lower())
    if abbr:
        return abbr
    return r


def _normalize_country(country: str) -> str:
    """Normalize country to ISO-3166 alpha-2."""
    if not country:
        return country
    c = country.strip()

    # Already alpha-2
    if re.match(r'^[A-Z]{2}$', c):
        return c

    # Check aliases
    alias = COUNTRY_ALIASES.get(c.lower())
    if alias:
        return alias

    # Try pycountry
    if HAS_PYCOUNTRY:
        try:
            result = pycountry.countries.lookup(c)
            return result.alpha_2
        except LookupError:
            pass

    return c.upper()[:2] if len(c) >= 2 else c
