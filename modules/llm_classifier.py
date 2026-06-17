"""
llm_classifier.py - Clasificacion con LLM puro via Groq API
Modelo: llama-3.3-70b-versatile (gratuito)
Registro: https://console.groq.com
"""

import json
import logging
import os
import re
import time
import urllib.request
from typing import List, Optional

from modules.utils import VariantInput, Article, normalize_classification

logger = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


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
        GROQ_URL,
        data=payload,
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


SYSTEM = (
    "Eres un experto en genetica clinica y clasificacion de variantes segun las guias ACMG/AMP. "
    "Clasifica variantes geneticas con rigor cientifico. "
    "REGLAS ESTRICTAS — debes seguirlas obligatoriamente:\n"
    "CRITERIOS DE PATOGENICIDAD:\n"
    "- Usa 'pathogenic' SOLO si hay PVS1 + cualquier evidencia adicional, o >=2 PS, o 1 PS + >=2 PM.\n"
    "- Usa 'likely_pathogenic' si hay 1 PS + 1 PM, o >=3 PM, o 1 PM + >=2 PP.\n"
    "- PVS1 se activa UNICAMENTE en frameshift, nonsense o splicing canonico +/-1,2 "
    "en gen donde perdida de funcion ES el mecanismo conocido. "
    "NO actives PVS1 en variantes missense.\n"
    "CRITERIOS DE BENIGNIDAD — son igual de importantes:\n"
    "- Usa 'benign' si hay BA1 (frecuencia >5% en poblacion general) o >=2 criterios BS.\n"
    "- Usa 'likely_benign' si hay 1 BS + 1 BP, o >=2 BP.\n"
    "- BS1: frecuencia alelica alta en gnomAD para la enfermedad en cuestion.\n"
    "- BP4: predictores computacionales (SIFT, PolyPhen) indican sin efecto.\n"
    "- BP7: variante sinonima sin efecto en splicing.\n"
    "CRITERIOS DE INCERTIDUMBRE:\n"
    "- Usa 'uncertain_significance' si la evidencia es insuficiente o contradictoria.\n"
    "- NO uses 'pathogenic' como opcion por defecto cuando tengas dudas.\n"
    "- Responde SIEMPRE en formato JSON valido, sin texto adicional fuera del JSON."
)

PROMPT_TEMPLATE = """# CLASIFICACION DE VARIANTE GENETICA

## VARIANTE
- Gen: {gene}
- cDNA: {cdna}
- Proteina: {protein}

{gnomad_section}

{literature}

## TAREA
Clasifica esta variante aplicando criterios ACMG/AMP (PVS1, PS1-4, PM1-6, PP1-5, BA1, BS1-4, BP1-7).
Considera: tipo de variante, impacto funcional, frecuencia poblacional, estudios funcionales, co-segregacion.

## CRITERIOS DE DECISION OBLIGATORIOS
Antes de responder, razona explicitamente:
1. Tipo de variante (frameshift/nonsense/splicing/missense/etc)
2. El gen es supresor tumoral, reparacion ADN, o haploinsuficiencia conocida?
3. Si es frameshift/nonsense/splicing canonico en gen de los anteriores: PVS1 activo
4. Si hay datos gnomAD con BA1=SI: clasificar como benign obligatoriamente
5. Si hay datos gnomAD con BS1=SI: clasificar como likely_benign salvo evidencia fuerte de patogenicidad
6. Cuantos criterios PS, PM, PP puedes aplicar con la evidencia disponible?
7. Aplica las reglas de combinacion ACMG/AMP para determinar la clase final

## RESPUESTA JSON
{{
  "classification": "<pathogenic|likely_pathogenic|uncertain_significance|likely_benign|benign|conflicting|unknown>",
  "confidence": "<alta|media|baja>",
  "acmg_criteria": {{
    "pathogenic": ["criterios aplicados"],
    "benign": ["criterios aplicados"]
  }},
  "key_evidence": ["evidencia 1", "evidencia 2", "evidencia 3"],
  "reasoning": "Explicacion del razonamiento en 2-3 frases",
  "limitations": "Limitaciones o incertidumbres",
  "method": "llm_only"
}}"""


class LLMClassifier:

    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")

    def classify(self, v: VariantInput, articles: List[Article], gnomad: dict = None) -> dict:
        # Formatear seccion gnomAD
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

        # Formatear literatura
        if articles:
            lit_lines = ["## LITERATURA RECUPERADA"]
            for i, a in enumerate(articles[:8], 1):
                lit_lines.append(f"\n### Articulo {i}: {a.title}")
                if a.year:
                    lit_lines.append(f"Ano: {a.year} | Revista: {a.journal}")
                if a.abstract:
                    lit_lines.append(f"Abstract: {a.abstract[:600]}")
            literature = "\n".join(lit_lines)
        else:
            literature = "## LITERATURA: No se encontraron articulos especificos."

        prompt = PROMPT_TEMPLATE.format(
            gene=v.gene, cdna=v.cdna,
            protein=v.protein or "No especificada",
            gnomad_section=gnomad_section,
            literature=literature,
        )

        raw = _call_groq(SYSTEM, prompt, self.api_key)
        data = _parse_json(raw)

        if not data:
            return {
                "classification": "unknown", "confidence": "baja",
                "acmg_criteria": {"pathogenic": [], "benign": []},
                "key_evidence": [], "reasoning": "Error al obtener respuesta del LLM",
                "limitations": "Sin respuesta", "method": "llm_only", "error": True,
            }

        data["classification"] = normalize_classification(data.get("classification", "unknown"))
        data["method"] = "llm_only"
        logger.info("LLM: %s -> %s", v.hgvs(), data["classification"])
        return data
