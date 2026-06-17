"""
Variant Classifier - TFM
Compara LLM puro vs RAG para clasificacion de variantes geneticas,
usando ClinVar como ground truth.

Uso:
    python main.py --gene BRCA2 --cdna "c.8168A>G" --protein "p.Asp2723Gly"
    python main.py --gene BRCA1 --cdna "c.5266dupC" --protein "p.Gln1756ProfsTer74"
    python main.py --batch variants.csv
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Cargar .env antes de importar modulos
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from modules.utils import VariantInput, setup_logging
from modules.clinvar_client import ClinVarClient
from modules.gnomad_client import GnomADClient
from modules.europepmc_client import EuropePMCClient
from modules.llm_classifier import LLMClassifier
from modules.rag_classifier import RAGClassifier
from modules.comparator import compare
from modules import report
from modules.pdf_report import generate_variant_report, generate_batch_report

logger = logging.getLogger(__name__)


def check_env():
    if not os.environ.get("GROQ_API_KEY"):
        print()
        print("ERROR: No se encontro GROQ_API_KEY en el archivo .env")
        print()
        print("Pasos:")
        print("  1. Ve a https://console.groq.com")
        print("  2. Registrate gratis y ve a API Keys -> Create API key")
        print("  3. Crea o edita el archivo .env en esta carpeta con:")
        print("       GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx")
        print()
        sys.exit(1)


def process(v: VariantInput, max_articles: int) -> dict:
    print()
    print("=" * 62)
    print(f"  Gen    : {v.gene}")
    print(f"  cDNA   : {v.cdna}")
    print(f"  Proteina: {v.protein or 'No especificada'}")
    print("=" * 62)

    result = {
        "variant": v.to_dict(),
        "timestamp": datetime.now().isoformat(),
        "clinvar": None,
        "articles": [],
        "llm_classification": None,
        "rag_classification": None,
        "comparison": None,
    }

    # 1. ClinVar
    print("\n[1/5] Consultando ClinVar...")
    cv_result = ClinVarClient().get_classification(v)
    result["clinvar"] = cv_result
    if cv_result.get("classification"):
        stars = cv_result.get("review_stars", 0) or 0
        print(f"      [OK] ClinVar: {cv_result['classification']}  "
              f"(revision: {'*'*stars if stars else 'sin revision'})")
    else:
        print("      [!] Variante no encontrada en ClinVar")

    # 2. gnomAD
    print("\n[2/5] Consultando gnomAD (frecuencia poblacional)...")
    gnomad_result = {"found": False, "note": "No consultado", "acmg_criteria": {}}
    try:
        gnomad_result = GnomADClient().get_population_frequency(v) or gnomad_result
    except Exception as e:
        logger.warning("gnomAD no disponible: %s", e)
    if not isinstance(gnomad_result, dict):
        gnomad_result = {"found": False, "note": "Respuesta invalida", "acmg_criteria": {}}
    result["gnomad"] = gnomad_result
    if gnomad_result.get("found"):
        af = gnomad_result.get("af_max")
        acmg = gnomad_result.get("acmg_criteria", {})
        af_str = f"AF={af:.6f}" if af is not None else "AF=no disponible"
        print(f"      [OK] gnomAD: {af_str} → {acmg.get('interpretation','sin_datos')}")
        if acmg.get("BA1"):
            print("      [!] BA1 activado: frecuencia >5%")
        elif acmg.get("BS1"):
            print("      [!] BS1 activado: frecuencia >1%")
    else:
        print(f"      [!] {gnomad_result.get('note', 'No encontrada en gnomAD')}")

    # 3. EuropePMC
    print(f"\n[3/5] Recuperando articulos de EuropePMC (max {max_articles})...")
    articles = EuropePMCClient().search(v, max_results=max_articles)
    result["articles"] = [a.to_dict() for a in articles]
    print(f"      [OK] {len(articles)} articulos recuperados")
    if not articles:
        print("      [!] Sin literatura. Las clasificaciones usaran solo conocimiento parametrico.")

    # 4. LLM
    print("\n[4/5] Clasificacion con LLM puro (Groq LLaMA 3.3 70B)...")
    llm_result = LLMClassifier().classify(v, articles, gnomad=gnomad_result)
    result["llm_classification"] = llm_result
    print(f"      [OK] LLM: {llm_result['classification']}  "
          f"(confianza: {llm_result.get('confidence','?')})")

    # 5. RAG
    print("\n[5/5] Clasificacion con RAG (ChromaDB + sentence-transformers + Groq)...")
    rag_result = RAGClassifier().classify(v, articles, gnomad=gnomad_result)
    result["rag_classification"] = rag_result
    chunks = rag_result.get("chunks_retrieved", 0)
    print(f"      [OK] RAG: {rag_result['classification']}  "
          f"(confianza: {rag_result.get('confidence','?')}, "
          f"chunks: {chunks})")

    # 6. Comparacion
    result["comparison"] = compare(cv_result, llm_result, rag_result)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Clasificador de variantes geneticas: LLM vs RAG vs ClinVar",
    )
    parser.add_argument("--gene", type=str)
    parser.add_argument("--cdna", type=str)
    parser.add_argument("--protein", type=str, default="")
    parser.add_argument("--batch", type=str, help="CSV con columnas: gene,cdna,protein")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--max-articles", type=int, default=10)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-report", action="store_true", help="No imprimir resumen en consola")
    parser.add_argument("--no-pdf", action="store_true", help="No generar PDF")
    args = parser.parse_args()

    setup_logging(args.verbose)
    check_env()
    Path("results").mkdir(exist_ok=True)

    # ── Modo batch ──────────────────────────────────────────────
    if args.batch:
        import csv
        variants = []
        with open(args.batch, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                variants.append(VariantInput(
                    gene=row["gene"].strip(),
                    cdna=row["cdna"].strip(),
                    protein=row.get("protein", "").strip(),
                ))
        print(f"\nProcesando {len(variants)} variantes en modo batch...")
        all_results = []
        for v in variants:
            try:
                r = process(v, args.max_articles)
                all_results.append(r)
                if not args.no_report:
                    report.print_summary(r)
            except Exception as e:
                logger.error("Error procesando %s: %s", v.hgvs(), e)
                all_results.append({"variant": v.to_dict(), "error": str(e)})

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = args.output or f"results/batch_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        report.print_batch_summary(all_results)
        print(f"Resultados guardados en: {out}")
        if not args.no_pdf:
            pdf_batch = out.replace(".json", ".pdf")
            try:
                generate_batch_report(all_results, pdf_batch)
                print(f"PDF batch guardado en: {pdf_batch}")
            except Exception as e:
                print(f"[!] No se pudo generar PDF batch: {e}")

    # ── Modo individual ─────────────────────────────────────────
    else:
        if not args.gene or not args.cdna:
            print("ERROR: Proporciona --gene y --cdna, o usa --batch")
            print("Ejemplo: python main.py --gene BRCA2 --cdna \"c.8168A>G\" --protein \"p.Asp2723Gly\"")
            sys.exit(1)

        v = VariantInput(gene=args.gene, cdna=args.cdna, protein=args.protein)
        result = process(v, args.max_articles)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = args.output or f"results/{v.gene}_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nJSON guardado en: {out}")

        if not args.no_report:
            report.print_summary(result)
        if not args.no_pdf:
            pdf_path = out.replace(".json", ".pdf")
            try:
                generate_variant_report(result, pdf_path)
                print(f"PDF guardado en:  {pdf_path}")
            except Exception as e:
                print(f"[!] No se pudo generar PDF: {e}")


if __name__ == "__main__":
    main()
