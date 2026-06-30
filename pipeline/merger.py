"""Merge normalized candidates from multiple sources into unified profiles."""

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from thefuzz import fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False
    logger.warning("thefuzz not installed; fuzzy name matching disabled")

# Source priority (higher = more trusted)
SOURCE_PRIORITY = {
    'ats_json': 4,
    'recruiter_csv': 3,
    'resume_txt': 2,
    'resume_pdf': 2,     # PDF/DOCX resumes same priority as text
    'github_url': 2,     # GitHub is self-reported
    'notes_txt': 1,
}

# Method mapping by source type
SOURCE_METHOD = {
    'ats_json': 'direct_mapping',
    'recruiter_csv': 'direct_mapping',
    'resume_txt': 'regex_extraction',
    'resume_pdf': 'pdf_text_extraction',
    'notes_txt': 'regex_extraction',
    'github_url': 'api_fetch',
}

FUZZY_NAME_THRESHOLD = 85


def _canonicalize_degree(deg: str) -> str:
    if not deg:
        return ""
    d = deg.strip().lower().replace('.', '')
    if 'phd' in d or 'doctor' in d:
        return 'phd'
    if d == 'ms' or 'master' in d or d == 'ma' or d == 'mba' or d == 'msc':
        return 'master'
    if d == 'bs' or 'bachelor' in d or d == 'ba' or d == 'bsc':
        return 'bachelor'
    if d == 'as' or 'associate' in d:
        return 'associate'
    return d


def _is_same_experience(exp1: dict, exp2: dict) -> bool:
    c1 = (exp1.get('company') or '').strip().lower()
    c2 = (exp2.get('company') or '').strip().lower()
    if not c1 or not c2:
        return False
        
    # Company similarity
    if fuzz.ratio(c1, c2) < 80 and c1 not in c2 and c2 not in c1:
        return False
        
    t1 = (exp1.get('title') or '').strip().lower()
    t2 = (exp2.get('title') or '').strip().lower()
    if not t1 or not t2:
        return False
        
    def clean_title(t):
        t = t.replace('sr.', 'senior').replace('jr.', 'junior').replace('swe', 'software engineer')
        t = t.replace('eng.', 'engineer').replace('developer', 'engineer').replace('sr ', 'senior ')
        return ' '.join(t.split())
        
    t1_clean = clean_title(t1)
    t2_clean = clean_title(t2)
    
    if fuzz.ratio(t1_clean, t2_clean) >= 75 or t1_clean in t2_clean or t2_clean in t1_clean:
        return True
        
    s1, s2 = exp1.get('start'), exp2.get('start')
    if s1 and s2 and s1 == s2:
        return True
        
    return False


# ── Union-Find ───────────────────────────────────────────────────────────────
class UnionFind:
    """Disjoint-set data structure for transitive candidate grouping."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


# ── Public API ───────────────────────────────────────────────────────────────
def merge_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group and merge candidate records that refer to the same person."""
    if not candidates:
        return []

    n = len(candidates)
    uf = UnionFind(n)

    # Build indexes for fast matching
    email_index: dict[str, list[int]] = {}
    phone_index: dict[str, list[int]] = {}

    for i, c in enumerate(candidates):
        for email in (c.get('emails') or []):
            key = email.strip().lower()
            email_index.setdefault(key, []).append(i)
        for phone in (c.get('phones') or []):
            key = phone.strip()
            phone_index.setdefault(key, []).append(i)

    # Union by shared email
    for indices in email_index.values():
        for j in range(1, len(indices)):
            uf.union(indices[0], indices[j])

    # Union by shared phone
    for indices in phone_index.values():
        for j in range(1, len(indices)):
            uf.union(indices[0], indices[j])

    # Union by fuzzy name match (only check across different groups)
    if HAS_FUZZ:
        for i in range(n):
            name_i = (candidates[i].get('full_name') or '').strip().lower()
            if not name_i:
                continue
            for j in range(i + 1, n):
                if uf.find(i) == uf.find(j):
                    continue  # already in the same group
                name_j = (candidates[j].get('full_name') or '').strip().lower()
                if not name_j:
                    continue
                if fuzz.ratio(name_i, name_j) >= FUZZY_NAME_THRESHOLD:
                    uf.union(i, j)

    # Group candidates by root
    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = uf.find(i)
        groups.setdefault(root, []).append(i)

    # Merge each group
    merged = []
    for indices in groups.values():
        group = [candidates[i] for i in indices]
        merged.append(_merge_group(group))

    return merged


def _merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge a group of candidate records into one canonical profile."""
    # Sort by source priority (highest first)
    group.sort(key=lambda c: SOURCE_PRIORITY.get(c.get('source_type', ''), 0), reverse=True)

    provenance = []
    result: dict[str, Any] = {}

    # ── Scalars (pick from highest-priority source) ──────────────────────
    # full_name
    for c in group:
        if c.get('full_name'):
            result['full_name'] = c['full_name']
            provenance.append({
                'field': 'full_name',
                'source': c.get('source_file', 'unknown'),
                'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
            })
            break
    if 'full_name' not in result:
        result['full_name'] = 'Unknown'

    # headline
    for c in group:
        if c.get('headline'):
            result['headline'] = c['headline']
            provenance.append({
                'field': 'headline',
                'source': c.get('source_file', 'unknown'),
                'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
            })
            break
    if 'headline' not in result:
        result['headline'] = None

    # years_experience
    for c in group:
        if c.get('years_experience') is not None:
            result['years_experience'] = c['years_experience']
            provenance.append({
                'field': 'years_experience',
                'source': c.get('source_file', 'unknown'),
                'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
            })
            break
    if 'years_experience' not in result:
        result['years_experience'] = None

    # ── Arrays (union-merge, deduplicate) ────────────────────────────────
    # emails
    all_emails = []
    seen_emails = set()
    for c in group:
        for e in (c.get('emails') or []):
            key = e.strip().lower()
            if key and key not in seen_emails:
                seen_emails.add(key)
                all_emails.append(key)
                provenance.append({
                    'field': f'emails',
                    'source': c.get('source_file', 'unknown'),
                    'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
                })
    result['emails'] = all_emails

    # phones
    all_phones = []
    seen_phones = set()
    for c in group:
        for p in (c.get('phones') or []):
            key = p.strip()
            if key and key not in seen_phones:
                seen_phones.add(key)
                all_phones.append(key)
                provenance.append({
                    'field': f'phones',
                    'source': c.get('source_file', 'unknown'),
                    'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
                })
    result['phones'] = all_phones

    # ── Location (prefer highest-priority, fill missing sub-fields) ──────
    merged_location = {'city': None, 'region': None, 'country': None}
    for c in group:
        loc = c.get('location')
        if not loc or not isinstance(loc, dict):
            continue
        for key in ('city', 'region', 'country'):
            if merged_location[key] is None and loc.get(key):
                merged_location[key] = loc[key]
                provenance.append({
                    'field': f'location.{key}',
                    'source': c.get('source_file', 'unknown'),
                    'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
                })
    result['location'] = merged_location

    # ── Links (merge, prefer non-null from higher-priority) ──────────────
    merged_links = {'linkedin': None, 'github': None, 'portfolio': None, 'other': []}
    other_set = set()
    for c in group:
        links = c.get('links')
        if not links or not isinstance(links, dict):
            continue
        for key in ('linkedin', 'github', 'portfolio'):
            if merged_links[key] is None and links.get(key):
                merged_links[key] = links[key]
                provenance.append({
                    'field': f'links.{key}',
                    'source': c.get('source_file', 'unknown'),
                    'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
                })
        for url in (links.get('other') or []):
            if url and url not in other_set:
                other_set.add(url)
                merged_links['other'].append(url)
    result['links'] = merged_links

    # ── Skills (union-merge, track sources per skill) ────────────────────
    skill_map: dict[str, dict] = {}  # canonical_name -> {sources: set}
    for c in group:
        source_file = c.get('source_file', 'unknown')
        for skill in (c.get('skills') or []):
            key = skill.strip().lower()
            if not key:
                continue
            if key not in skill_map:
                skill_map[key] = {'name': skill, 'sources': set(), 'source_types': set()}
            skill_map[key]['sources'].add(source_file)
            skill_map[key]['source_types'].add(c.get('source_type', 'unknown'))

    result['skills'] = []
    for key, info in sorted(skill_map.items()):
        result['skills'].append({
            'name': key,
            'confidence': 0.0,  # Will be set by confidence scorer
            'sources': sorted(info['sources']),
            '_source_types': sorted(info['source_types']),  # internal, stripped later
        })

    # ── Experience (merge similar roles, deduplicate) ─────────────────────
    exp_list = []
    for c in group:
        for exp in (c.get('experience') or []):
            matched = False
            for existing in exp_list:
                if _is_same_experience(existing, exp):
                    # Keep longer/more descriptive title (e.g. 'Senior Software Engineer' over 'Sr. SWE')
                    t_ext = existing.get('title') or ""
                    t_new = exp.get('title') or ""
                    if len(t_new) > len(t_ext) and 'swe' not in t_new.lower() and 'sr.' not in t_new.lower():
                        existing['title'] = t_new
                    elif 'swe' in t_ext.lower() or 'sr.' in t_ext.lower():
                        if len(t_new) > 3:
                            existing['title'] = t_new
                    
                    # Fill missing fields
                    for f in ('start', 'end', 'summary'):
                        if not existing.get(f) and exp.get(f):
                            existing[f] = exp[f]
                    matched = True
                    break
            
            if not matched:
                exp_list.append(dict(exp))
                provenance.append({
                    'field': 'experience',
                    'source': c.get('source_file', 'unknown'),
                    'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
                })

    # Sort experience by start date (most recent first)
    exp_list.sort(key=lambda e: e.get('start') or '0000-00', reverse=True)

    # Clean up: ensure company/title are properly cased
    for exp in exp_list:
        if exp.get('company'):
            exp['company'] = exp['company'].strip()
            if exp['company'] == exp['company'].lower():
                exp['company'] = exp['company'].title()
        if exp.get('title'):
            exp['title'] = exp['title'].strip()
            if exp['title'] == exp['title'].lower():
                exp['title'] = exp['title'].title()
    result['experience'] = exp_list

    # ── Education (merge matching degree/institution) ────────────────────
    edu_list = []
    for c in group:
        for edu in (c.get('education') or []):
            inst = (edu.get('institution') or '').strip().lower()
            degree = (edu.get('degree') or '').strip().lower()
            if not inst:
                continue
                
            matched = False
            for existing in edu_list:
                exist_inst = (existing.get('institution') or '').strip().lower()
                
                # Check institution match
                if fuzz.ratio(inst, exist_inst) >= 85 or inst in exist_inst or exist_inst in inst:
                    # Check degree match
                    d1 = _canonicalize_degree(degree)
                    d2 = _canonicalize_degree(existing.get('degree') or '')
                    if d1 == d2 and d1 != "":
                        # Keep longer degree title
                        deg_ext = existing.get('degree') or ""
                        deg_new = edu.get('degree') or ""
                        if len(deg_new) > len(deg_ext):
                            existing['degree'] = deg_new
                            
                        # Fill missing fields
                        for f in ('field', 'end_year'):
                            if not existing.get(f) and edu.get(f):
                                existing[f] = edu[f]
                        matched = True
                        break
            
            if not matched:
                edu_list.append(dict(edu))
                provenance.append({
                    'field': 'education',
                    'source': c.get('source_file', 'unknown'),
                    'method': SOURCE_METHOD.get(c.get('source_type', ''), 'direct_mapping'),
                })

    # Clean up education strings
    for edu in edu_list:
        if edu.get('institution'):
            inst = edu['institution'].strip()
            if inst == inst.upper() or inst == inst.lower():
                inst = inst.title()
            edu['institution'] = inst
        if edu.get('degree'):
            deg = edu['degree'].strip()
            deg_clean = {
                'ms': 'MS', 'bs': 'BS', 'ba': 'BA', 'ma': 'MA', 'mba': 'MBA', 'phd': 'PhD'
            }
            if deg.lower() in deg_clean:
                edu['degree'] = deg_clean[deg.lower()]
            elif deg == deg.lower() or deg == deg.upper():
                edu['degree'] = deg.title()
                
    result['education'] = edu_list

    # ── candidate_id (SHA-256 of sorted emails + phones) ─────────────────
    id_parts = sorted(result['emails']) + sorted(result['phones'])
    if id_parts:
        result['candidate_id'] = hashlib.sha256('|'.join(id_parts).encode()).hexdigest()[:16]
    else:
        # Fallback: hash the name
        name_key = (result.get('full_name') or 'unknown').lower()
        result['candidate_id'] = hashlib.sha256(name_key.encode()).hexdigest()[:16]

    result['provenance'] = provenance
    result['overall_confidence'] = 0.0  # Set by confidence scorer

    return result
