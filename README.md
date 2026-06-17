# TFM_PabloPena
# Variant Classifier — TFM Bioinformatics

> Automated genetic variant classification system comparing **LLM** and **RAG** approaches against ClinVar.  
> *Master's Thesis in Bioinformatics — Pablo Peña*

---

## Overview

This system implements and evaluates two AI-based approaches for automated ACMG/AMP classification of genetic variants:

- **LLM Classifier** — Pure large language model inference using in-context learning with retrieved literature and gnomAD population frequency data
- **RAG Classifier** — Retrieval-Augmented Generation combining semantic search over indexed biomedical literature (ChromaDB + sentence-transformers) with LLM generation

Both systems are evaluated against ClinVar as clinical ground truth across three variant sets (55 variants total).

---

## Features

- Automated ClinVar lookup via NCBI E-utilities API
- Population frequency retrieval from gnomAD v4 (GraphQL API) with automatic BA1/BS1/BS2 criterion application
- Multi-level literature retrieval from EuropePMC + PubMed with progressive fallback strategy
- ACMG/AMP-enriched prompt engineering with explicit decision rules
- Quantitative evaluation: exact/flexible accuracy, weighted F1-score, confusion matrices
- JSON + PDF report generation per variant and batch

---

## Installation

```bash
git clone https://github.com/pablopena19/TFM_PabloPena.git
cd TFM_PabloPena
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux / macOS
pip install -r requirements.txt
```

Create a `.env` file with your Groq API key:

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

Get a free API key at [console.groq.com](https://console.groq.com).

---

## Usage

### Single variant
```bash
python main.py --gene BRCA1 --cdna "c.5266dupC" --protein "p.Gln1756ProfsTer74"
```

### Batch mode
```bash
python main.py --batch tfm_15_variantes.csv --max-articles 10
```

### Options
```
--gene          Gene symbol (e.g. BRCA1)
--cdna          cDNA notation (e.g. c.5266dupC)
--protein       Protein change (optional)
--batch         CSV file with columns: gene, cdna, protein
--max-articles  Maximum articles to retrieve per variant (default: 10)
--verbose       Enable debug logging
--no-pdf        Skip PDF report generation
```

---

## Project Structure

```
TFM_PabloPena/
├── main.py                    # Pipeline orchestrator
├── requirements.txt           # Python dependencies
├── .env.example               # API key template
├── tfm_15_variantes.csv       # Standard batch (15 variants)
├── tfm_15_gold.csv            # Gold standard batch (15 variants)
├── tfm_25_variantes.csv       # Extended batch (25 variants)
└── modules/
    ├── utils.py               # Data structures and shared utilities
    ├── clinvar_client.py      # ClinVar API client (ground truth)
    ├── gnomad_client.py       # gnomAD v4 GraphQL client (population frequency)
    ├── europepmc_client.py    # EuropePMC + PubMed literature retrieval
    ├── llm_classifier.py      # Pure LLM classifier (Groq / LLaMA 3.3 70B)
    ├── rag_classifier.py      # RAG classifier (ChromaDB + sentence-transformers)
    ├── comparator.py          # Classification comparison and metrics
    ├── report.py              # Console output
    └── pdf_report.py          # PDF report generation (ReportLab)
```

---

## System Architecture

The pipeline executes 5 sequential steps for each variant:

1. **ClinVar** — Retrieve reference classification and review stars
2. **gnomAD** — Retrieve allele frequency; apply BA1/BS1/BS2 benignity criteria automatically
3. **EuropePMC + PubMed** — Retrieve up to N articles using multi-level query strategy
4. **LLM Classifier** — Classify using enriched ACMG/AMP prompt with gnomAD data and literature context
5. **RAG Classifier** — Index articles in ChromaDB, retrieve top-6 chunks by cosine similarity, generate conditioned classification

---

## Results Summary

Evaluated on 55 variants across 3 experimental batches:

| Batch | N | LLM Exact Acc. | RAG Exact Acc. | LLM Flex. Acc. | RAG Flex. Acc. |
|-------|---|---------------|---------------|----------------|----------------|
| Standard | 15 | 60.0% | 53.3% | 80.0% | 86.7% |
| Gold | 15 | 73.3% | **80.0%** | 80.0% | **93.3%** |
| Extended | 25 | **64.0%** | 60.0% | 80.0% | **84.0%** |

Key findings:
- gnomAD integration resolved 100% of benign variant misclassifications
- RAG outperforms LLM when literature is abundant and variant-specific (gold batch)
- ACMG/AMP prompt engineering improved exact accuracy by >20 percentage points vs generic prompt

---

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| sentence-transformers | ≥2.2 | Semantic embeddings (all-MiniLM-L6-v2) |
| chromadb | ≥0.4 | Local vector database |
| scikit-learn | ≥1.3 | Evaluation metrics |
| reportlab | ≥4.0 | PDF report generation |

LLM: **LLaMA 3.3 70B** via [Groq API](https://console.groq.com) (free tier: 100k tokens/day)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Author

**Pablo Peña**  
Master's in Bioinformatics  
2025–2026
