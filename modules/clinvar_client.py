"""
clinvar_client.py - Cliente ClinVar via NCBI E-utilities
Comportamiento verificado:
  - esearch devuelve IDs pero puede incluir variantes cercanas
  - esummary con retmode=json da germline_classification.description
  - Hay que elegir el ID cuyo title mejor coincide con la variante buscada
"""

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import List, Optional

from modules.utils import VariantInput, normalize_classification

logger = logging.getLogger(__name__)
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "VariantClassifierTFM"
EMAIL = "tfm@university.es"


def _get(endpoint: str, params: dict, retries: int = 3) -> Optional[dict]:
    base = {"tool": TOOL, "email": EMAIL, "retmode": "json"}
    url = f"{EUTILS}/{endpoint}?" + urllib.parse.urlencode({**base, **params})
    logger.debug("ClinVar GET: %s", url)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(attempt * 5)
            else:
                logger.error("ClinVar HTTP %s", e.code)
                return None
        except Exception as e:
            if attempt < retries:
                time.sleep(5)
            else:
                logger.error("ClinVar error: %s", e)
                return None
    return None


def _search(term: str) -> List[str]:
    result = _get("esearch.fcgi", {"db": "clinvar", "term": term, "retmax": "10"})
    time.sleep(0.4)
    if result:
        return result.get("esearchresult", {}).get("idlist", [])
    return []


def _summaries(ids: List[str]) -> dict:
    if not ids:
        return {}
    result = _get("esummary.fcgi", {"db": "clinvar", "id": ",".join(ids)})
    time.sleep(0.4)
    if result:
        return result.get("result", {})
    return {}


def _score_doc(doc: dict, v: VariantInput) -> int:
    """Puntúa cuánto coincide un docsum de ClinVar con la variante buscada."""
    title = doc.get("title", "").lower()
    score = 0
    pos = v.numeric_pos()
    if pos and pos in title:
        score += 3
    change = v.change_type()
    if change and change in title:
        score += 3
    if v.gene.lower() in title:
        score += 1
    # Penalizar si la posición es muy diferente
    title_pos = re.search(r'(\d+)', title)
    if pos and title_pos and abs(int(pos) - int(title_pos.group(1))) > 50:
        score -= 2
    return score


def _parse_doc(doc: dict, vid: str) -> dict:
    result = {
        "variation_id": vid,
        "clinvar_url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{vid}/",
        "variant_name": doc.get("title", ""),
        "classification": None,
        "classification_normalized": None,
        "review_stars": None,
        "review_status": None,
        "conditions": [],
        "last_evaluated": None,
    }
    germline = doc.get("germline_classification", {})
    if isinstance(germline, dict):
        desc = germline.get("description", "")
        result["classification"] = desc or None
        if desc:
            result["classification_normalized"] = normalize_classification(desc)
        result["review_status"] = germline.get("review_status", "")
        result["last_evaluated"] = germline.get("last_evaluated", "")
        result["review_stars"] = _stars(result["review_status"])
        traits = germline.get("trait_set", [])
        if isinstance(traits, list):
            result["conditions"] = [
                t.get("trait_name", "") for t in traits[:5]
                if isinstance(t, dict) and t.get("trait_name")
            ]
    return result


def _stars(status: str) -> int:
    if not status:
        return 0
    s = status.lower()
    if "practice guideline" in s:
        return 4
    if "expert panel" in s:
        return 3
    if "multiple submitters" in s:
        return 2
    if "single submitter" in s:
        return 1
    return 0


NOT_FOUND = {
    "variation_id": None,
    "classification": None,
    "classification_normalized": "not_found",
    "review_stars": None,
    "review_status": None,
    "conditions": [],
    "last_evaluated": None,
    "variant_name": None,
    "clinvar_url": None,
}


class ClinVarClient:

    def get_classification(self, v: VariantInput) -> dict:
        # Construir queries de búsqueda
        queries = []
        queries.append(f"{v.gene}[gene] AND {v.cdna}")
        if v.protein:
            queries.append(f"{v.gene}[gene] AND {v.protein}")
        pos = v.numeric_pos()
        if pos:
            queries.append(f"{v.gene}[gene] AND {pos}")

        # Recopilar IDs únicos
        all_ids: List[str] = []
        seen: set = set()
        for q in queries:
            logger.debug("ClinVar search: %s", q)
            for vid in _search(q):
                if vid not in seen:
                    seen.add(vid)
                    all_ids.append(vid)
            if len(all_ids) >= 10:
                break

        if not all_ids:
            NOT_FOUND["clinvar_url"] = (
                f"https://www.ncbi.nlm.nih.gov/clinvar/?term="
                f"{urllib.parse.quote(v.gene + ' ' + v.cdna)}"
            )
            return dict(NOT_FOUND)

        # Obtener summaries y elegir el mejor match
        docs = _summaries(all_ids[:10])
        best_doc = None
        best_score = -99
        best_vid = None

        for vid in all_ids[:10]:
            doc = docs.get(vid, {})
            if not doc or vid == "uids":
                continue
            germline = doc.get("germline_classification", {})
            desc = germline.get("description", "") if isinstance(germline, dict) else ""
            if not desc:
                continue
            score = _score_doc(doc, v)
            logger.debug("  ID %s score=%d title=%s", vid, score, doc.get("title","")[:50])
            if score > best_score:
                best_score = score
                best_doc = doc
                best_vid = vid

        if best_doc:
            return _parse_doc(best_doc, best_vid)

        NOT_FOUND["clinvar_url"] = (
            f"https://www.ncbi.nlm.nih.gov/clinvar/?term="
            f"{urllib.parse.quote(v.gene + ' ' + v.cdna)}"
        )
        return dict(NOT_FOUND)
