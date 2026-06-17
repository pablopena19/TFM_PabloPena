"""
europepmc_client.py - Cliente EuropePMC
Comportamiento verificado:
  - resultType=lite sin sort devuelve resultados
  - Para abstracts: segunda llamada con EXT_ID:{pmid} AND SRC:MED y resultType=core
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import List, Optional

from modules.utils import VariantInput, Article

logger = logging.getLogger(__name__)
BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _get(params: dict, retries: int = 3) -> Optional[dict]:
    """GET a EuropePMC con reintentos. No añade 'sort'."""
    params["format"] = "json"
    url = BASE + "?" + urllib.parse.urlencode(params)
    logger.debug("EuropePMC GET: %s", url)
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504) and attempt < retries:
                time.sleep(attempt * 4)
            else:
                logger.error("EuropePMC HTTP %s", e.code)
                return None
        except Exception as e:
            if attempt < retries:
                time.sleep(4)
            else:
                logger.error("EuropePMC error: %s", e)
                return None
    return None


def _fetch_abstract(pmid: str) -> str:
    """Obtiene el abstract de un PMID via segunda llamada con resultType=core."""
    if not pmid:
        return ""
    result = _get({
        "query": f"EXT_ID:{pmid} AND SRC:MED",
        "resultType": "core",
        "pageSize": "1",
    })
    if result:
        hits = result.get("resultList", {}).get("result", [])
        if hits:
            return hits[0].get("abstractText", "")
    return ""


def _parse_hit(hit: dict) -> Optional[Article]:
    title = hit.get("title", "").strip()
    if not title:
        return None
    # Limpiar HTML entities
    title = title.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    year = None
    try:
        year = int(hit.get("pubYear", 0)) or None
    except (ValueError, TypeError):
        pass
    authors = []
    for a in hit.get("authorString", "").split(",")[:5]:
        a = a.strip()
        if a:
            authors.append(a)
    return Article(
        pmid=hit.get("pmid", ""),
        title=title,
        abstract=hit.get("abstractText", ""),
        journal=hit.get("journalTitle", ""),
        year=year,
        authors=authors,
    )


class EuropePMCClient:

    def __init__(self, sleep: float = 0.5):
        self.sleep = sleep

    def _queries(self, v: VariantInput) -> List[str]:
        """Queries de búsqueda en orden de especificidad, sin comillas."""
        qs = []
        # Específicas
        if v.protein:
            qs.append(f"{v.gene} {v.cdna} {v.protein}")
        qs.append(f"{v.gene} {v.cdna}")
        if v.protein:
            qs.append(f"{v.gene} {v.protein}")
        # Posición numérica
        pos = v.numeric_pos()
        if pos:
            qs.append(f"{v.gene} {pos} variant")
        # Fallback
        qs.append(f"{v.gene} variant pathogenicity classification")
        return qs

    def search(self, v: VariantInput, max_results: int = 10) -> List[Article]:
        seen_pmids: set = set()
        seen_titles: set = set()
        articles: List[Article] = []

        for q in self._queries(v):
            if len(articles) >= max_results * 2:
                break
            logger.debug("EuropePMC query: %s", q)
            result = _get({"query": q, "resultType": "lite", "pageSize": str(min(max_results, 25))})
            time.sleep(self.sleep)
            if not result:
                continue
            hits = result.get("resultList", {}).get("result", [])
            logger.debug("  -> %d hits", len(hits))
            for hit in hits:
                art = _parse_hit(hit)
                if not art:
                    continue
                if art.pmid and art.pmid in seen_pmids:
                    continue
                title_key = art.title.lower()[:60]
                if title_key in seen_titles:
                    continue
                seen_pmids.add(art.pmid)
                seen_titles.add(title_key)
                articles.append(art)

        # Obtener abstracts para los primeros max_results artículos
        for art in articles[:max_results]:
            if not art.abstract and art.pmid:
                art.abstract = _fetch_abstract(art.pmid)
                time.sleep(self.sleep)

        # Priorizar los que tienen abstract
        with_abs = [a for a in articles if a.abstract]
        without_abs = [a for a in articles if not a.abstract]
        return (with_abs + without_abs)[:max_results]
