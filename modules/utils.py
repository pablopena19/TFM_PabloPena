"""utils.py - Estructuras de datos y utilidades compartidas."""

import logging
import re
import sys
import io
from dataclasses import dataclass, field, asdict
from typing import Optional

# Forzar UTF-8 en Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

CLASSIFICATIONS = {
    "pathogenic":             "Patogenica",
    "likely_pathogenic":      "Probablemente patogenica",
    "benign":                 "Benigna",
    "likely_benign":          "Probablemente benigna",
    "uncertain_significance": "Significado incierto (VUS)",
    "unknown":                "Desconocida",
    "conflicting":            "Interpretaciones conflictivas",
    "not_found":              "No encontrada en ClinVar",
}

ICONS = {
    "pathogenic":             "[PATOGENICA]",
    "likely_pathogenic":      "[PROB. PATOGENICA]",
    "benign":                 "[BENIGNA]",
    "likely_benign":          "[PROB. BENIGNA]",
    "uncertain_significance": "[VUS]",
    "unknown":                "[DESCONOCIDA]",
    "conflicting":            "[CONFLICTIVA]",
    "not_found":              "[NO EN CLINVAR]",
}


def normalize_classification(raw: str) -> str:
    if not raw:
        return "unknown"
    r = raw.lower().strip()
    if "pathogenic" in r and "likely" in r:
        return "likely_pathogenic"
    if "pathogenic" in r:
        return "pathogenic"
    if "benign" in r and "likely" in r:
        return "likely_benign"
    if "benign" in r:
        return "benign"
    if "uncertain" in r or "vus" in r:
        return "uncertain_significance"
    if "conflicting" in r:
        return "conflicting"
    return "unknown"


@dataclass
class VariantInput:
    gene: str
    cdna: str
    protein: str = ""

    def __post_init__(self):
        self.gene = self.gene.upper().strip()
        self.cdna = self.cdna.strip()
        self.protein = self.protein.strip()

    def to_dict(self):
        return asdict(self)

    def hgvs(self):
        if self.protein:
            return f"{self.gene}:{self.cdna} ({self.protein})"
        return f"{self.gene}:{self.cdna}"

    def numeric_pos(self):
        m = re.search(r'(\d+)', self.cdna)
        return m.group(1) if m else ""

    def change_type(self):
        m = re.search(r'(dup|del|ins|>)', self.cdna.lower())
        return m.group(1) if m else ""


@dataclass
class Article:
    pmid: str
    title: str
    abstract: str = ""
    journal: str = ""
    year: Optional[int] = None
    authors: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    def to_text(self):
        parts = [f"Titulo: {self.title}"]
        if self.year:
            parts.append(f"Ano: {self.year} | Revista: {self.journal}")
        if self.abstract:
            parts.append(f"Abstract: {self.abstract}")
        return "\n".join(parts)


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    for lib in ["httpx", "httpcore", "urllib3", "chromadb", "sentence_transformers",
                "huggingface_hub", "transformers"]:
        logging.getLogger(lib).setLevel(logging.ERROR)
