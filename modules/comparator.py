"""comparator.py - Compara clasificaciones LLM, RAG y ClinVar."""

from modules.utils import CLASSIFICATIONS, ICONS

PATHOGENIC = {"pathogenic", "likely_pathogenic"}
BENIGN = {"benign", "likely_benign"}


def _group(c):
    if c in PATHOGENIC:
        return "pathogenic_spectrum"
    if c in BENIGN:
        return "benign_spectrum"
    return "uncertain_spectrum"


def compare(clinvar: dict, llm: dict, rag: dict) -> dict:
    cv = clinvar.get("classification_normalized") or "not_found"
    lm = llm.get("classification", "unknown")
    rg = rag.get("classification", "unknown")

    has_cv = cv not in ("not_found", "unknown", None)

    exact_lm = (cv == lm) if has_cv else None
    exact_rg = (cv == rg) if has_cv else None
    flex_lm = (_group(cv) == _group(lm)) if has_cv else None
    flex_rg = (_group(cv) == _group(rg)) if has_cv else None

    if not has_cv:
        agreement = "full_agreement" if lm == rg else "llm_rag_disagree"
    elif cv == lm == rg:
        agreement = "full_agreement"
    elif _group(cv) == _group(lm) == _group(rg):
        agreement = "flexible_agreement"
    elif cv == lm or cv == rg:
        agreement = "partial_agreement"
    else:
        agreement = "full_disagreement"

    if not has_cv:
        winner = "sin_ground_truth"
    elif exact_lm and exact_rg:
        winner = "ambos_correctos"
    elif exact_lm:
        winner = "llm_mas_preciso"
    elif exact_rg:
        winner = "rag_mas_preciso"
    else:
        winner = "ninguno_exacto"

    discrepancies = []
    if has_cv and cv != lm:
        discrepancies.append(f"LLM difiere de ClinVar: {lm} vs {cv}")
    if has_cv and cv != rg:
        discrepancies.append(f"RAG difiere de ClinVar: {rg} vs {cv}")
    if lm != rg:
        discrepancies.append(f"LLM y RAG discrepan: {lm} vs {rg}")

    return {
        "clinvar_classification": cv,
        "llm_classification": lm,
        "rag_classification": rg,
        "exact_match": {"llm_vs_clinvar": exact_lm, "rag_vs_clinvar": exact_rg, "llm_vs_rag": lm == rg},
        "flexible_match": {"llm_vs_clinvar": flex_lm, "rag_vs_clinvar": flex_rg},
        "agreement_level": agreement,
        "winner": winner,
        "discrepancies": discrepancies,
        "clinvar_available": has_cv,
    }
