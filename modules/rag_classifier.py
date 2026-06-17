"""
rag_classifier.py - Clasificacion via RAG
Pipeline: articulos -> chunks -> ChromaDB -> recuperar chunks -> Groq
"""

import hashlib
import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import List, Optional

from modules.utils import VariantInput, Article, normalize_classification

logger = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
CHROMA_DIR = "./chroma_db"
COLLECTION = "variant_literature"
CHUNK_SIZE = 450
OVERLAP = 80
TOP_K = 6


def _call_groq(system: str, user: str, api_key: str) -> Optional[str]:
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        GROQ_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        logger.error("Groq HTTP %s: %s", e.code, body[:200])
        if e.code == 429:
            logger.warning("Rate limit Groq, esperando 35s...")
            time.sleep(35)
            return _call_groq(system, user, api_key)
    except Exception as e:
        logger.error("Groq error: %s", e)
    return None


def _parse_json(raw: str) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {}


def _chunk(text: str) -> List[str]:
    text = text[:3000]
    if len(text) <= CHUNK_SIZE:
        return [text.strip()] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < 20:
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            bp = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if bp > start + CHUNK_SIZE // 2:
                end = bp + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - OVERLAP
    return chunks


def _articles_to_chunks(articles: List[Article]) -> List[dict]:
    chunks = []
    for art in articles:
        text = art.to_text()
        for i, chunk_text in enumerate(_chunk(text)):
            cid = hashlib.md5(f"{art.pmid}_{i}_{chunk_text[:40]}".encode()).hexdigest()
            chunks.append({
                "id": cid,
                "text": chunk_text,
                "meta": {
                    "pmid": art.pmid or "",
                    "title": art.title[:150],
                    "year": str(art.year or ""),
                },
            })
    return chunks


class VectorStore:

    def __init__(self):
        self._client = None
        self._col = None
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Cargando modelo de embeddings...")
            self._model = SentenceTransformer("paraphrase-MiniLM-L3-v2")
            logger.info("Modelo cargado.")
        return self._model

    def _get_col(self):
        if self._col is None:
            import chromadb
            Path(CHROMA_DIR).mkdir(exist_ok=True)
            self._client = chromadb.PersistentClient(path=CHROMA_DIR)
            self._col = self._client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        return self._col

    def index(self, articles: List[Article]):
        if not articles:
            return 0
        chunks = _articles_to_chunks(articles)
        if not chunks:
            return 0
        chunks = chunks[:30]
        model = self._get_model()
        col = self._get_col()
        try:
            existing = col.get()["ids"]
            if existing:
                col.delete(ids=existing)
        except Exception:
            pass
        texts = [c["text"] for c in chunks]
        ids = [c["id"] for c in chunks]
        metas = [c["meta"] for c in chunks]
        embeddings = model.encode(texts, show_progress_bar=False, batch_size=8).tolist()
        col.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
        logger.info("Indexados %d chunks en ChromaDB", len(chunks))
        return len(chunks)

    def retrieve(self, query: str, k: int = TOP_K) -> List[dict]:
        model = self._get_model()
        col = self._get_col()
        count = col.count()
        if count == 0:
            return []
        k = min(k, count)
        qemb = model.encode([query], show_progress_bar=False).tolist()[0]
        res = col.query(query_embeddings=[qemb], n_results=k,
                        include=["documents", "metadatas", "distances"])
        out = []
        for i, (doc, meta, dist) in enumerate(zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        )):
            out.append({
                "rank": i + 1,
                "text": doc,
                "similarity": round(1 - dist, 4),
                "source": meta.get("title", "")[:80],
            })
        return out


SYSTEM = (
    "Eres un experto en genetica clinica. Clasifica variantes geneticas "
    "basandote PRINCIPALMENTE en los fragmentos de literatura recuperados "
    "y en los datos de frecuencia poblacional de gnomAD cuando esten disponibles. "
    "REGLAS ESTRICTAS:\n"
    "CRITERIOS DE PATOGENICIDAD:\n"
    "- Usa 'pathogenic' SOLO si hay PVS1 + evidencia adicional, o >=2 PS, o 1 PS + >=2 PM.\n"
    "- Usa 'likely_pathogenic' si hay 1 PS + 1 PM, o >=3 PM, o 1 PM + >=2 PP.\n"
    "- PVS1 se activa UNICAMENTE en frameshift, nonsense o splicing canonico +/-1,2 "
    "en gen donde perdida de funcion ES el mecanismo conocido. NO en missense.\n"
    "CRITERIOS DE BENIGNIDAD:\n"
    "- Usa 'benign' si BA1=SI (AF>5%) o >=2 BS.\n"
    "- Usa 'likely_benign' si BS1=SI (AF>1%) o 1 BS + 1 BP o >=2 BP.\n"
    "CRITERIOS DE INCERTIDUMBRE:\n"
    "- Usa 'uncertain_significance' si la evidencia es insuficiente o contradictoria.\n"
    "- NO uses 'pathogenic' como opcion por defecto.\n"
    "- Responde SIEMPRE en JSON valido, sin texto adicional."
)

PROMPT_TEMPLATE = """# CLASIFICACION RAG DE VARIANTE GENETICA

## VARIANTE
- Gen: {gene}
- cDNA: {cdna}
- Proteina: {protein}

{gnomad_section}

## FRAGMENTOS RECUPERADOS (ordenados por relevancia semantica)
{chunks_text}

## TAREA
Clasifica esta variante basandote PRINCIPALMENTE en los fragmentos anteriores y los datos gnomAD.
Aplica criterios ACMG/AMP e indica que fragmentos apoyan tu decision.

## CRITERIOS DE DECISION OBLIGATORIOS
1. Tipo de variante (frameshift/nonsense/splicing/missense/etc)
2. Si BA1=SI en gnomAD: clasificar como benign obligatoriamente
3. Si BS1=SI en gnomAD: clasificar como likely_benign salvo evidencia fuerte de patogenicidad
4. Si es frameshift/nonsense/splicing canonico en gen supresor tumoral: PVS1 activo
5. Aplica reglas de combinacion ACMG/AMP para la clase final

## RESPUESTA JSON
{{
  "classification": "<pathogenic|likely_pathogenic|uncertain_significance|likely_benign|benign|conflicting|unknown>",
  "confidence": "<alta|media|baja>",
  "acmg_criteria": {{
    "pathogenic": ["criterios aplicados"],
    "benign": ["criterios aplicados"]
  }},
  "key_evidence": ["evidencia extraida de los fragmentos"],
  "top_sources": ["titulos de articulos mas relevantes"],
  "reasoning": "Explicacion basada en fragmentos recuperados y datos gnomAD",
  "limitations": "Que evidencia adicional aumentaria la confianza",
  "method": "rag"
}}"""


class RAGClassifier:

    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.store = VectorStore()

    def classify(self, v: VariantInput, articles: List[Article], gnomad: dict = None) -> dict:
        # 1. Indexar
        n_chunks = self.store.index(articles)
        logger.debug("RAG: indexados %d chunks", n_chunks)

        # 2. Recuperar
        change_type = v.change_type()
        change_term = {
            "dup": "duplication frameshift truncation",
            "del": "deletion frameshift truncation",
            ">":   "missense substitution amino acid",
            "ins": "insertion frameshift truncation",
        }.get(change_type, "variant")
        query = (
            f"{v.gene} {v.cdna} {v.protein} "
            f"{change_term} pathogenicity ACMG classification "
            f"benign pathogenic uncertain"
        )
        retrieved = self.store.retrieve(query, k=TOP_K)

        if not retrieved and articles:
            fallback_query = f"{v.gene} variant pathogenicity classification ACMG germline"
            retrieved = self.store.retrieve(fallback_query, k=TOP_K)

        # 3. Formatear contexto
        if retrieved:
            lines = []
            for c in retrieved:
                lines.append(f"--- [Similitud: {c['similarity']:.3f}] Fuente: {c['source']}")
                lines.append(c["text"])
            chunks_text = "\n".join(lines)
        else:
            chunks_text = (
                "No se recuperaron fragmentos especificos para esta variante. "
                "Clasifica basandote en los datos gnomAD y tu conocimiento del gen."
            )

        # 4. Formatear seccion gnomAD
        if gnomad and gnomad.get("found"):
            af = gnomad.get("af_max") or 0
            af_pct = round(af * 100, 4)
            af_val = round(af, 6)
            acmg_g = gnomad.get("acmg_criteria", {})
            ba1 = "SI — clasificar como benign" if acmg_g.get("BA1") else "NO"
            bs1 = "SI — clasificar como likely_benign" if acmg_g.get("BS1") else "NO"
            bs2 = "SI — homocigotos en poblacion sana" if acmg_g.get("BS2") else "NO"
            hom = str(gnomad.get("ac_hom_max", "N/A"))
            gnomad_section = (
                "## DATOS DE FRECUENCIA POBLACIONAL (gnomAD)\n"
                "Frecuencia alelica maxima (AF): " + str(af_val) + " (" + str(af_pct) + "%)\n"
                "Homocigotos observados: " + hom + "\n"
                "Criterio BA1 activado: " + ba1 + "\n"
                "Criterio BS1 activado: " + bs1 + "\n"
                "Criterio BS2 activado: " + bs2
            )
        else:
            gnomad_section = "## DATOS GNOMAD: No disponibles para esta variante."

        prompt = PROMPT_TEMPLATE.format(
            gene=v.gene, cdna=v.cdna,
            protein=v.protein or "No especificada",
            gnomad_section=gnomad_section,
            chunks_text=chunks_text,
        )

        raw = _call_groq(SYSTEM, prompt, self.api_key)
        data = _parse_json(raw)

        if not data:
            return {
                "classification": "unknown", "confidence": "baja",
                "acmg_criteria": {"pathogenic": [], "benign": []},
                "key_evidence": [], "reasoning": "Error al obtener respuesta",
                "limitations": "Sin respuesta del LLM", "method": "rag",
                "chunks_retrieved": len(retrieved), "error": True,
            }

        data["classification"] = normalize_classification(data.get("classification", "unknown"))
        data["method"] = "rag"
        data["chunks_retrieved"] = len(retrieved)
        data["retrieval_details"] = [
            {"rank": c["rank"], "similarity": c["similarity"], "source": c["source"]}
            for c in retrieved[:3]
        ]
        logger.info("RAG: %s -> %s (%d chunks)", v.hgvs(), data["classification"], len(retrieved))
        return data