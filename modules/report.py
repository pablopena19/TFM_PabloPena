"""report.py - Imprime resultados en consola."""

from modules.utils import CLASSIFICATIONS, ICONS


def _label(code):
    return CLASSIFICATIONS.get(code, code or "N/A")


def _icon(code):
    return ICONS.get(code, "[?]")


def print_summary(results: dict):
    v = results["variant"]
    comp = results.get("comparison", {})
    llm = results.get("llm_classification", {})
    rag = results.get("rag_classification", {})
    cv = results.get("clinvar", {})

    SEP = "=" * 62
    sep = "-" * 62

    print()
    print(SEP)
    print("  RESULTADOS DE CLASIFICACION")
    print(SEP)
    print(f"  Variante : {v['gene']} {v['cdna']}  {v.get('protein','')}")
    print(sep)

    # ClinVar
    cv_code = comp.get("clinvar_classification", "not_found")
    stars = cv.get("review_stars")
    stars_str = ("*" * stars) if stars else "sin revision"
    print(f"\n  [GROUND TRUTH] ClinVar:")
    print(f"    {_icon(cv_code)} {_label(cv_code)}  [{stars_str}]")
    if cv.get("variant_name"):
        print(f"    Nombre ClinVar: {cv['variant_name']}")
    if cv.get("conditions"):
        print(f"    Condiciones: {', '.join(cv['conditions'][:3])}")
    if cv.get("clinvar_url"):
        print(f"    URL: {cv['clinvar_url']}")

    # LLM
    lm_code = comp.get("llm_classification", "unknown")
    lm_conf = llm.get("confidence", "?")
    match_lm = comp.get("exact_match", {}).get("llm_vs_clinvar")
    match_str = " [COINCIDE]" if match_lm else (" [DIFIERE]" if match_lm is False else "")
    print(f"\n  [LLM PURO] Groq LLaMA 3.3 70B:")
    print(f"    {_icon(lm_code)} {_label(lm_code)}  [confianza: {lm_conf}]{match_str}")
    if llm.get("reasoning"):
        print(f"    Razonamiento: {llm['reasoning'][:220]}")
    criteria = llm.get("acmg_criteria", {})
    path_c = criteria.get("pathogenic", [])
    ben_c = criteria.get("benign", [])
    if path_c:
        print(f"    Criterios patog.: {', '.join(path_c)}")
    if ben_c:
        print(f"    Criterios benigno: {', '.join(ben_c)}")

    # RAG
    rg_code = comp.get("rag_classification", "unknown")
    rg_conf = rag.get("confidence", "?")
    match_rg = comp.get("exact_match", {}).get("rag_vs_clinvar")
    match_str_r = " [COINCIDE]" if match_rg else (" [DIFIERE]" if match_rg is False else "")
    chunks = rag.get("chunks_retrieved", 0)
    print(f"\n  [RAG] ChromaDB + sentence-transformers + Groq:")
    print(f"    {_icon(rg_code)} {_label(rg_code)}  [confianza: {rg_conf}]{match_str_r}")
    print(f"    Chunks recuperados: {chunks}")
    if rag.get("retrieval_details"):
        for d in rag["retrieval_details"][:2]:
            print(f"      #{d['rank']} sim={d['similarity']:.3f}  {d['source'][:55]}")
    if rag.get("reasoning"):
        print(f"    Razonamiento: {rag['reasoning'][:220]}")

    # Comparacion
    print(f"\n  Nivel de acuerdo : {comp.get('agreement_level','?')}")
    print(f"  Resultado        : {comp.get('winner','?')}")
    if comp.get("discrepancies"):
        for d in comp["discrepancies"]:
            print(f"    ! {d}")

    # Articulos
    arts = results.get("articles", [])
    print(f"\n  Articulos recuperados: {len(arts)}")
    for a in arts[:3]:
        print(f"    [{a.get('year','?')}] {a.get('title','')[:70]}")

    print(SEP)
    print()


def print_batch_summary(all_results: list):
    total = len(all_results)
    errors = sum(1 for r in all_results if "error" in r)
    with_cv = sum(1 for r in all_results if r.get("comparison", {}).get("clinvar_available"))
    llm_ok = sum(1 for r in all_results if r.get("comparison", {}).get("exact_match", {}).get("llm_vs_clinvar"))
    rag_ok = sum(1 for r in all_results if r.get("comparison", {}).get("exact_match", {}).get("rag_vs_clinvar"))

    print()
    print("=" * 62)
    print("  RESUMEN BATCH")
    print("=" * 62)
    print(f"  Total variantes   : {total}")
    print(f"  Errores           : {errors}")
    print(f"  Con ClinVar       : {with_cv}")
    if with_cv:
        print(f"  LLM exacto        : {llm_ok}/{with_cv} ({100*llm_ok//with_cv}%)")
        print(f"  RAG exacto        : {rag_ok}/{with_cv} ({100*rag_ok//with_cv}%)")
    print("=" * 62)
