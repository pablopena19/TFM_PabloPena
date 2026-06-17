"""
gnomad_client.py - Cliente para la API GraphQL de gnomAD v4
"""

import json
import logging
import ssl
import time
import urllib.request
from typing import Optional

from modules.utils import VariantInput

ssl._create_default_https_context = ssl._create_unverified_context
logger = logging.getLogger(__name__)

GNOMAD_API = "https://gnomad.broadinstitute.org/api"
BA1_THRESHOLD = 0.05
BS1_THRESHOLD = 0.01

QUERY = """
query GeneVariants($geneSymbol: String!, $datasetId: DatasetId!) {
  gene(gene_symbol: $geneSymbol, reference_genome: GRCh38) {
    variants(dataset: $datasetId) {
      variantId
      hgvsc
      exome { ac an af ac_hom }
      genome { ac an af ac_hom }
    }
  }
}
"""


def _graphql_query(variables: dict) -> dict:
    payload = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GNOMAD_API, data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.error("gnomAD error: %s", e)
        return {}


def _match(variants: list, v: VariantInput) -> Optional[dict]:
    pos = v.numeric_pos()
    cdna_clean = v.cdna.lower().replace("c.", "")
    change = v.change_type()
    best, best_score = None, -1
    for var in variants:
        hgvsc = (var.get("hgvsc") or "").lower()
        score = 0
        if cdna_clean in hgvsc:
            score += 5
        elif pos and pos in hgvsc:
            score += 3
        if change and change in hgvsc:
            score += 2
        if score > best_score:
            best_score = score
            best = var
    return best if best_score >= 3 else None


class GnomADClient:

    def get_population_frequency(self, v: VariantInput) -> dict:
        result = {
            "found": False, "variant_id": None,
            "af_exome": None, "af_genome": None, "af_max": None,
            "ac_hom_max": None, "acmg_criteria": {},
            "gnomad_url": f"https://gnomad.broadinstitute.org/gene/{v.gene}",
            "note": None,
        }

        resp = _graphql_query({"geneSymbol": v.gene, "datasetId": "gnomad_r4"})
        if not resp.get("data"):
            resp = _graphql_query({"geneSymbol": v.gene, "datasetId": "gnomad_r2_1"})
            time.sleep(0.3)

        variants = resp.get("data", {}).get("gene", {}).get("variants", [])
        if not variants:
            result["note"] = f"Gen {v.gene} no encontrado en gnomAD"
            return result

        matched = _match(variants, v)
        if not matched:
            result["note"] = f"{v.cdna} no encontrada en gnomAD para {v.gene}"
            return result

        result["found"] = True
        result["variant_id"] = matched.get("variantId")
        result["gnomad_url"] = f"https://gnomad.broadinstitute.org/variant/{matched.get('variantId')}"

        exome  = matched.get("exome") or {}
        genome = matched.get("genome") or {}
        result["af_exome"]  = exome.get("af")
        result["af_genome"] = genome.get("af")

        freqs = [f for f in [result["af_exome"], result["af_genome"]] if f is not None]
        result["af_max"] = max(freqs) if freqs else None

        homs = [h for h in [exome.get("ac_hom"), genome.get("ac_hom")] if h is not None]
        result["ac_hom_max"] = max(homs) if homs else None

        af = result["af_max"]
        ac_hom = result["ac_hom_max"]
        criteria = {"BA1": False, "BS1": False, "BS2": False,
                    "interpretation": None, "reason": None}

        if af is not None:
            if af >= BA1_THRESHOLD:
                criteria["BA1"] = True
                criteria["interpretation"] = "benign"
                criteria["reason"] = f"BA1: AF={af:.4f} ({af*100:.2f}%) supera el 5%"
            elif af >= BS1_THRESHOLD:
                criteria["BS1"] = True
                criteria["interpretation"] = "likely_benign"
                criteria["reason"] = f"BS1: AF={af:.4f} ({af*100:.2f}%) supera el 1%"
            else:
                criteria["interpretation"] = "frecuencia_baja"
                criteria["reason"] = f"AF={af:.6f} — no activa criterios de benignidad"
            if ac_hom and ac_hom >= 5 and not criteria["BA1"]:
                criteria["BS2"] = True
                if criteria["interpretation"] == "frecuencia_baja":
                    criteria["interpretation"] = "likely_benign"
                    criteria["reason"] += f". BS2: {ac_hom} homocigotos"
        else:
            criteria["interpretation"] = "sin_datos"
            criteria["reason"] = "Frecuencia no disponible"

        result["acmg_criteria"] = criteria
        logger.info("gnomAD: %s %s AF=%.4f interpretation=%s",
                    v.gene, v.cdna, af or 0, criteria["interpretation"])
        return result
