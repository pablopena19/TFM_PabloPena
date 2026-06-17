"""
pdf_report.py - Generador de informes PDF con reportlab
Genera un informe por variante y un informe batch con tabla comparativa.
Instalar: pip install reportlab
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
from reportlab.pdfgen import canvas as rl_canvas
from datetime import datetime
from typing import List
import os

# ── Colores ────────────────────────────────────────────────────────────────────
C_BLUE      = colors.HexColor("#1a3a5c")
C_BLUE_LIGHT= colors.HexColor("#2e6da4")
C_GREEN     = colors.HexColor("#1a7a3c")
C_RED       = colors.HexColor("#a41a1a")
C_ORANGE    = colors.HexColor("#b35900")
C_GRAY      = colors.HexColor("#f4f6f9")
C_GRAY_DARK = colors.HexColor("#6c757d")
C_WHITE     = colors.white
C_BORDER    = colors.HexColor("#dee2e6")

CLASSIF_COLORS = {
    "pathogenic":             C_RED,
    "likely_pathogenic":      C_ORANGE,
    "benign":                 C_GREEN,
    "likely_benign":          colors.HexColor("#2e7d32"),
    "uncertain_significance": colors.HexColor("#555555"),
    "conflicting":            colors.HexColor("#7b1fa2"),
    "unknown":                C_GRAY_DARK,
    "not_found":              C_GRAY_DARK,
}

CLASSIF_LABELS = {
    "pathogenic":             "PATOGENICA",
    "likely_pathogenic":      "PROB. PATOGENICA",
    "benign":                 "BENIGNA",
    "likely_benign":          "PROB. BENIGNA",
    "uncertain_significance": "SIGNIFICADO INCIERTO (VUS)",
    "conflicting":            "INTERPRETACIONES CONFLICTIVAS",
    "unknown":                "DESCONOCIDA",
    "not_found":              "NO EN CLINVAR",
}

# ── Estilos ────────────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    s = {}

    s["title"] = ParagraphStyle("title",
        fontName="Helvetica-Bold", fontSize=18,
        textColor=C_BLUE, alignment=TA_CENTER, spaceAfter=4)

    s["subtitle"] = ParagraphStyle("subtitle",
        fontName="Helvetica", fontSize=11,
        textColor=C_GRAY_DARK, alignment=TA_CENTER, spaceAfter=16)

    s["section"] = ParagraphStyle("section",
        fontName="Helvetica-Bold", fontSize=12,
        textColor=C_WHITE, spaceAfter=6, spaceBefore=14,
        leftIndent=0)

    s["label"] = ParagraphStyle("label",
        fontName="Helvetica-Bold", fontSize=9,
        textColor=C_GRAY_DARK, spaceAfter=2)

    s["value"] = ParagraphStyle("value",
        fontName="Helvetica", fontSize=10,
        textColor=colors.black, spaceAfter=4)

    s["value_bold"] = ParagraphStyle("value_bold",
        fontName="Helvetica-Bold", fontSize=10,
        textColor=colors.black, spaceAfter=4)

    s["small"] = ParagraphStyle("small",
        fontName="Helvetica", fontSize=8,
        textColor=C_GRAY_DARK, spaceAfter=2)

    s["reasoning"] = ParagraphStyle("reasoning",
        fontName="Helvetica-Oblique", fontSize=9,
        textColor=colors.HexColor("#333333"),
        spaceAfter=4, leftIndent=8, rightIndent=8)

    s["footer"] = ParagraphStyle("footer",
        fontName="Helvetica", fontSize=7,
        textColor=C_GRAY_DARK, alignment=TA_CENTER)

    s["table_header"] = ParagraphStyle("table_header",
        fontName="Helvetica-Bold", fontSize=9,
        textColor=C_WHITE, alignment=TA_CENTER)

    s["table_cell"] = ParagraphStyle("table_cell",
        fontName="Helvetica", fontSize=8,
        textColor=colors.black, alignment=TA_CENTER)

    s["table_cell_left"] = ParagraphStyle("table_cell_left",
        fontName="Helvetica", fontSize=8,
        textColor=colors.black, alignment=TA_LEFT)

    return s


# ── Header/Footer ──────────────────────────────────────────────────────────────
def _add_header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4

    # Header bar
    canvas.setFillColor(C_BLUE)
    canvas.rect(0, h - 1.5*cm, w, 1.5*cm, fill=True, stroke=False)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(1.5*cm, h - 1.0*cm, "Variant Classifier - TFM")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 1.5*cm, h - 1.0*cm,
        datetime.now().strftime("%d/%m/%Y"))

    # Footer
    canvas.setFillColor(C_GRAY_DARK)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(1.5*cm, 0.6*cm,
        "Generado automaticamente. No sustituye evaluacion clinica especializada.")
    canvas.drawRightString(w - 1.5*cm, 0.6*cm, f"Pagina {doc.page}")

    canvas.restoreState()


# ── Helpers ────────────────────────────────────────────────────────────────────
def _section_header(text: str, s: dict) -> Table:
    """Cabecera de sección con fondo azul."""
    p = Paragraph(text.upper(), s["section"])
    t = Table([[p]], colWidths=[17*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
    ]))
    return t


def _classif_badge(code: str, s: dict) -> Table:
    """Badge de color con la clasificación."""
    label = CLASSIF_LABELS.get(code, code.upper())
    col = CLASSIF_COLORS.get(code, C_GRAY_DARK)
    p = Paragraph(f"<b>{label}</b>",
        ParagraphStyle("badge", fontName="Helvetica-Bold", fontSize=11,
                       textColor=C_WHITE, alignment=TA_CENTER))
    t = Table([[p]], colWidths=[8*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), col),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _stars(n) -> str:
    if not n:
        return "Sin revision"
    return "*" * int(n) + " (" + str(n) + " estrella" + ("s" if n > 1 else "") + ")"


def _kv_table(rows: list, s: dict, col_widths=None) -> Table:
    """Tabla de pares clave-valor con fondo alternado."""
    if col_widths is None:
        col_widths = [5*cm, 12*cm]
    data = []
    for label, value in rows:
        data.append([
            Paragraph(label, s["label"]),
            Paragraph(str(value) if value else "-", s["value"]),
        ])
    t = Table(data, colWidths=col_widths)
    style = [
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, C_BORDER),
    ]
    for i in range(0, len(data), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), C_GRAY))
    t.setStyle(TableStyle(style))
    return t


# ── Informe individual ─────────────────────────────────────────────────────────
def generate_variant_report(result: dict, output_path: str):
    """Genera un PDF detallado para una variante."""
    s = _styles()
    v = result["variant"]
    cv = result.get("clinvar", {})
    llm = result.get("llm_classification", {})
    rag = result.get("rag_classification", {})
    comp = result.get("comparison", {})
    arts = result.get("articles", [])

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=2.2*cm, bottomMargin=1.5*cm,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
    )

    story = []

    # ── Portada / cabecera ───────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("Informe de Clasificacion de Variante Genetica", s["title"]))
    story.append(Paragraph(
        f"Gen <b>{v['gene']}</b> &nbsp;|&nbsp; {v['cdna']} &nbsp;|&nbsp; {v.get('protein') or 'Sin cambio proteico'}",
        s["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=C_BLUE_LIGHT))
    story.append(Spacer(1, 0.3*cm))

    # ── 1. Datos de la variante ──────────────────────────────────────
    story.append(_section_header("1. Datos de la Variante", s))
    story.append(Spacer(1, 0.2*cm))
    story.append(_kv_table([
        ("Gen",              v["gene"]),
        ("Cambio cDNA",      v["cdna"]),
        ("Cambio proteico",  v.get("protein") or "No especificado"),
        ("Fecha analisis",   result.get("timestamp", "")[:19].replace("T", "  ")),
    ], s))
    story.append(Spacer(1, 0.3*cm))

    # ── 2. ClinVar (ground truth) ────────────────────────────────────
    story.append(_section_header("2. Clasificacion ClinVar (Ground Truth)", s))
    story.append(Spacer(1, 0.2*cm))

    cv_code = comp.get("clinvar_classification", "not_found")
    badge_cv = _classif_badge(cv_code, s)

    cv_rows = [
        ("Clasificacion",  CLASSIF_LABELS.get(cv_code, cv_code)),
        ("Nombre variante", cv.get("variant_name") or "-"),
        ("Revision",       _stars(cv.get("review_stars"))),
        ("Estado revision", cv.get("review_status") or "-"),
        ("Ultima eval.",   cv.get("last_evaluated") or "-"),
        ("Condiciones",    ", ".join(cv.get("conditions", [])) or "-"),
        ("URL ClinVar",    cv.get("clinvar_url") or "-"),
    ]

    inner = Table(
        [[badge_cv, Spacer(1, 1)], [_kv_table(cv_rows, s), ""]],
        colWidths=[8*cm, 9*cm]
    )
    inner.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("SPAN", (0, 1), (1, 1))]))
    story.append(inner)
    story.append(Spacer(1, 0.3*cm))


    # ── 3. gnomAD (frecuencia poblacional) ──────────────────────────
    story.append(_section_header("3. Frecuencia Poblacional (gnomAD v4)", s))
    story.append(Spacer(1, 0.2*cm))

    gnomad = result.get("gnomad", {})
    if gnomad and gnomad.get("found"):
        af = gnomad.get("af_max") or 0
        acmg_g = gnomad.get("acmg_criteria", {})
        ba1 = "ACTIVADO" if acmg_g.get("BA1") else "No activado"
        bs1 = "ACTIVADO" if acmg_g.get("BS1") else "No activado"
        bs2 = "ACTIVADO" if acmg_g.get("BS2") else "No activado"
        gnomad_rows = [
            ("Variante encontrada",    "Si"),
            ("Frecuencia alelica (AF)", f"{af:.6f}  ({af*100:.4f}%)"),
            ("Homocigotos observados",  str(gnomad.get("ac_hom_max", "N/D"))),
            ("Criterio BA1 (AF > 5%)",  ba1),
            ("Criterio BS1 (AF > 1%)",  bs1),
            ("Criterio BS2 (homocig.)", bs2),
            ("Interpretacion",          acmg_g.get("reason", "-") or "-"),
            ("URL gnomAD",              gnomad.get("gnomad_url", "-") or "-"),
        ]
        # Colorear BA1/BS1 si activos
        story.append(_kv_table(gnomad_rows, s))
        if acmg_g.get("BA1"):
            story.append(Paragraph(
                "BA1 ACTIVO: Frecuencia superior al 5% — criterio de benignidad autonoma aplicado.",
                ParagraphStyle("ba1", fontName="Helvetica-Bold", fontSize=9,
                               textColor=C_GREEN, spaceAfter=4, leftIndent=6)))
        elif acmg_g.get("BS1"):
            story.append(Paragraph(
                "BS1 ACTIVO: Frecuencia superior al 1% — evidencia fuerte de benignidad aplicada.",
                ParagraphStyle("bs1", fontName="Helvetica-Bold", fontSize=9,
                               textColor=C_GREEN, spaceAfter=4, leftIndent=6)))
    else:
        note = gnomad.get("note", "Variante no encontrada en gnomAD") if gnomad else "No consultado"
        story.append(_kv_table([
            ("Estado", "No disponible"),
            ("Nota",   note),
        ], s))
    story.append(Spacer(1, 0.3*cm))

    # ── 4. Clasificacion LLM ─────────────────────────────────────────
    story.append(_section_header("4. Clasificacion LLM Puro (Groq LLaMA 3.3 70B)", s))
    story.append(Spacer(1, 0.2*cm))

    lm_code = comp.get("llm_classification", "unknown")
    match_lm = comp.get("exact_match", {}).get("llm_vs_clinvar")
    match_txt = " - COINCIDE CON CLINVAR" if match_lm else (" - DIFIERE DE CLINVAR" if match_lm is False else "")
    match_col = C_GREEN if match_lm else (C_RED if match_lm is False else C_GRAY_DARK)

    story.append(Table([[
        _classif_badge(lm_code, s),
        Paragraph(f"Confianza: <b>{llm.get('confidence','?').upper()}</b><br/>"
                  f"<font color='{'green' if match_lm else 'red'}'>{match_txt}</font>",
                  ParagraphStyle("m", fontName="Helvetica", fontSize=10,
                                 textColor=match_col, leftIndent=10)),
    ]], colWidths=[8*cm, 9*cm]))
    story.append(Spacer(1, 0.15*cm))

    # Criterios ACMG
    acmg = llm.get("acmg_criteria", {})
    pc = acmg.get("pathogenic", [])
    bc = acmg.get("benign", [])
    if pc or bc:
        criteria_rows = []
        if pc:
            criteria_rows.append(("Criterios patog.", "\n".join(f"- {x}" for x in pc[:5])))
        if bc:
            criteria_rows.append(("Criterios benigno", "\n".join(f"- {x}" for x in bc[:5])))
        story.append(_kv_table(criteria_rows, s))
        story.append(Spacer(1, 0.1*cm))

    # Evidencia clave
    evidence = llm.get("key_evidence", [])
    if evidence:
        story.append(Paragraph("Evidencia clave:", s["label"]))
        for ev in evidence[:4]:
            story.append(Paragraph(f"• {ev}", s["value"]))

    # Razonamiento
    if llm.get("reasoning"):
        story.append(Spacer(1, 0.1*cm))
        story.append(Paragraph("Razonamiento:", s["label"]))
        story.append(Paragraph(llm["reasoning"][:500], s["reasoning"]))

    story.append(Spacer(1, 0.3*cm))

    # ── 4. Clasificacion RAG ─────────────────────────────────────────
    story.append(_section_header("5. Clasificacion RAG (ChromaDB + Sentence-Transformers + Groq)", s))
    story.append(Spacer(1, 0.2*cm))

    rg_code = comp.get("rag_classification", "unknown")
    match_rg = comp.get("exact_match", {}).get("rag_vs_clinvar")
    match_txt_r = " - COINCIDE CON CLINVAR" if match_rg else (" - DIFIERE DE CLINVAR" if match_rg is False else "")

    chunks = rag.get("chunks_retrieved", 0)
    story.append(Table([[
        _classif_badge(rg_code, s),
        Paragraph(f"Confianza: <b>{rag.get('confidence','?').upper()}</b><br/>"
                  f"Chunks recuperados: <b>{chunks}</b><br/>"
                  f"<font color='{'green' if match_rg else 'red'}'>{match_txt_r}</font>",
                  ParagraphStyle("mr", fontName="Helvetica", fontSize=10,
                                 textColor=(C_GREEN if match_rg else C_RED if match_rg is False else C_GRAY_DARK),
                                 leftIndent=10)),
    ]], colWidths=[8*cm, 9*cm]))
    story.append(Spacer(1, 0.15*cm))

    # Fuentes recuperadas
    details = rag.get("retrieval_details", [])
    if details:
        story.append(Paragraph("Fragmentos mas relevantes recuperados:", s["label"]))
        for d in details[:3]:
            story.append(Paragraph(
                f"  #{d['rank']}  Similitud: {d['similarity']:.3f}  |  {d['source'][:70]}",
                s["small"]))

    if rag.get("reasoning"):
        story.append(Spacer(1, 0.1*cm))
        story.append(Paragraph("Razonamiento:", s["label"]))
        story.append(Paragraph(rag["reasoning"][:500], s["reasoning"]))

    story.append(Spacer(1, 0.3*cm))

    # ── 5. Comparacion ───────────────────────────────────────────────
    story.append(_section_header("6. Comparacion y Resultado", s))
    story.append(Spacer(1, 0.2*cm))

    agreement = comp.get("agreement_level", "?")
    winner = comp.get("winner", "?")

    # Tabla comparativa
    comp_data = [
        [Paragraph("Sistema", s["table_header"]),
         Paragraph("Clasificacion", s["table_header"]),
         Paragraph("Confianza", s["table_header"]),
         Paragraph("Coincide ClinVar", s["table_header"])],
        [Paragraph("ClinVar", s["table_cell"]),
         Paragraph(CLASSIF_LABELS.get(cv_code, cv_code), s["table_cell"]),
         Paragraph("Ground truth", s["table_cell"]),
         Paragraph("-", s["table_cell"])],
        [Paragraph("LLM puro", s["table_cell"]),
         Paragraph(CLASSIF_LABELS.get(lm_code, lm_code), s["table_cell"]),
         Paragraph(llm.get("confidence", "?"), s["table_cell"]),
         Paragraph("SI" if match_lm else ("NO" if match_lm is False else "-"), s["table_cell"])],
        [Paragraph("RAG", s["table_cell"]),
         Paragraph(CLASSIF_LABELS.get(rg_code, rg_code), s["table_cell"]),
         Paragraph(rag.get("confidence", "?"), s["table_cell"]),
         Paragraph("SI" if match_rg else ("NO" if match_rg is False else "-"), s["table_cell"])],
    ]
    comp_table = Table(comp_data, colWidths=[3.5*cm, 6*cm, 3*cm, 4.5*cm])
    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE),
        ("BACKGROUND",    (0, 1), (-1, 1), colors.HexColor("#e8f0fe")),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ])
    # Colorear SI/NO
    for row_idx, match in [(2, match_lm), (3, match_rg)]:
        if match is True:
            ts.add("BACKGROUND", (3, row_idx), (3, row_idx), colors.HexColor("#d4edda"))
        elif match is False:
            ts.add("BACKGROUND", (3, row_idx), (3, row_idx), colors.HexColor("#f8d7da"))
    comp_table.setStyle(ts)
    story.append(comp_table)
    story.append(Spacer(1, 0.2*cm))

    story.append(_kv_table([
        ("Nivel de acuerdo", agreement.replace("_", " ").upper()),
        ("Resultado",        winner.replace("_", " ").upper()),
        ("Discrepancias",    "; ".join(comp.get("discrepancies", [])) or "Ninguna"),
    ], s))
    story.append(Spacer(1, 0.3*cm))

    # ── 6. Literatura recuperada ─────────────────────────────────────
    if arts:
        story.append(_section_header(f"7. Literatura Recuperada ({len(arts)} articulos)", s))
        story.append(Spacer(1, 0.2*cm))
        art_data = [[
            Paragraph("PMID", s["table_header"]),
            Paragraph("Titulo", s["table_header"]),
            Paragraph("Revista", s["table_header"]),
            Paragraph("Ano", s["table_header"]),
        ]]
        for a in arts[:10]:
            art_data.append([
                Paragraph(a.get("pmid", "-") or "-", s["table_cell"]),
                Paragraph(a.get("title", "")[:65], s["table_cell_left"]),
                Paragraph(a.get("journal", "-")[:25], s["table_cell"]),
                Paragraph(str(a.get("year", "-")), s["table_cell"]),
            ])
        art_table = Table(art_data, colWidths=[2*cm, 9.5*cm, 3.5*cm, 2*cm])
        art_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_BLUE),
            ("GRID",       (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_GRAY]),
        ]))
        story.append(art_table)

    doc.build(story, onFirstPage=_add_header_footer, onLaterPages=_add_header_footer)


# ── Informe batch ──────────────────────────────────────────────────────────────
def generate_batch_report(all_results: list, output_path: str):
    """Genera un PDF resumen para un batch de variantes."""
    s = _styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=2.2*cm, bottomMargin=1.5*cm,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
    )
    story = []

    # Titulo
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("Informe Batch - Clasificacion de Variantes Geneticas", s["title"]))
    story.append(Paragraph(
        f"Analisis comparativo LLM vs RAG vs ClinVar  |  {len(all_results)} variantes",
        s["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=C_BLUE_LIGHT))
    story.append(Spacer(1, 0.4*cm))

    # Estadisticas generales
    story.append(_section_header("1. Resumen Estadistico", s))
    story.append(Spacer(1, 0.2*cm))

    ok = [r for r in all_results if "error" not in r]
    with_cv = [r for r in ok if r.get("comparison", {}).get("clinvar_available")]
    llm_exact = [r for r in with_cv if r.get("comparison", {}).get("exact_match", {}).get("llm_vs_clinvar")]
    rag_exact = [r for r in with_cv if r.get("comparison", {}).get("exact_match", {}).get("rag_vs_clinvar")]
    llm_flex  = [r for r in with_cv if r.get("comparison", {}).get("flexible_match", {}).get("llm_vs_clinvar")]
    rag_flex  = [r for r in with_cv if r.get("comparison", {}).get("flexible_match", {}).get("rag_vs_clinvar")]

    n = len(with_cv)
    pct = lambda x: f"{100*len(x)//n}%" if n else "-"

    stat_data = [
        [Paragraph("Metrica", s["table_header"]),
         Paragraph("LLM Puro", s["table_header"]),
         Paragraph("RAG", s["table_header"])],
        [Paragraph("Precision exacta vs ClinVar", s["table_cell_left"]),
         Paragraph(f"{len(llm_exact)}/{n} ({pct(llm_exact)})", s["table_cell"]),
         Paragraph(f"{len(rag_exact)}/{n} ({pct(rag_exact)})", s["table_cell"])],
        [Paragraph("Precision flexible (espectro)", s["table_cell_left"]),
         Paragraph(f"{len(llm_flex)}/{n} ({pct(llm_flex)})", s["table_cell"]),
         Paragraph(f"{len(rag_flex)}/{n} ({pct(rag_flex)})", s["table_cell"])],
        [Paragraph("Variantes procesadas", s["table_cell_left"]),
         Paragraph(str(len(all_results)), s["table_cell"]),
         Paragraph(str(len(all_results)), s["table_cell"])],
        [Paragraph("Con clasificacion ClinVar", s["table_cell_left"]),
         Paragraph(str(n), s["table_cell"]),
         Paragraph(str(n), s["table_cell"])],
    ]
    stat_table = Table(stat_data, colWidths=[8*cm, 4.5*cm, 4.5*cm])
    stat_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_GRAY]),
    ]))
    story.append(stat_table)
    story.append(Spacer(1, 0.4*cm))

    # Tabla detalle por variante
    story.append(_section_header("2. Detalle por Variante", s))
    story.append(Spacer(1, 0.2*cm))

    headers = [
        Paragraph("Gen", s["table_header"]),
        Paragraph("cDNA", s["table_header"]),
        Paragraph("ClinVar", s["table_header"]),
        Paragraph("LLM", s["table_header"]),
        Paragraph("RAG", s["table_header"]),
        Paragraph("Acuerdo", s["table_header"]),
    ]
    rows = [headers]
    row_styles = []

    for i, r in enumerate(all_results, 1):
        if "error" in r:
            rows.append([
                Paragraph(r["variant"]["gene"], s["table_cell"]),
                Paragraph(r["variant"]["cdna"], s["table_cell_left"]),
                Paragraph("ERROR", s["table_cell"]),
                Paragraph("-", s["table_cell"]),
                Paragraph("-", s["table_cell"]),
                Paragraph("-", s["table_cell"]),
            ])
            continue

        comp = r.get("comparison", {})
        cv_c = comp.get("clinvar_classification", "not_found")
        lm_c = comp.get("llm_classification", "unknown")
        rg_c = comp.get("rag_classification", "unknown")
        agreement = comp.get("agreement_level", "?")
        match_lm = comp.get("exact_match", {}).get("llm_vs_clinvar")
        match_rg = comp.get("exact_match", {}).get("rag_vs_clinvar")

        short = lambda c: CLASSIF_LABELS.get(c, c)[:12]

        rows.append([
            Paragraph(r["variant"]["gene"], s["table_cell"]),
            Paragraph(r["variant"]["cdna"], s["table_cell_left"]),
            Paragraph(short(cv_c), s["table_cell"]),
            Paragraph(short(lm_c) + (" *" if match_lm else ""), s["table_cell"]),
            Paragraph(short(rg_c) + (" *" if match_rg else ""), s["table_cell"]),
            Paragraph(agreement.replace("_", " ")[:15], s["table_cell"]),
        ])

        # Color por acuerdo
        bg = C_WHITE if i % 2 == 0 else C_GRAY
        row_styles.append(("BACKGROUND", (0, i), (-1, i), bg))
        if agreement == "full_agreement":
            row_styles.append(("BACKGROUND", (5, i), (5, i), colors.HexColor("#d4edda")))
        elif agreement == "full_disagreement":
            row_styles.append(("BACKGROUND", (5, i), (5, i), colors.HexColor("#f8d7da")))

    detail_table = Table(rows, colWidths=[2.2*cm, 3.8*cm, 3*cm, 3*cm, 3*cm, 2*cm])
    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
    ])
    for st in row_styles:
        ts.add(*st)
    detail_table.setStyle(ts)
    story.append(detail_table)

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("* Coincide exactamente con ClinVar", s["small"]))

    doc.build(story, onFirstPage=_add_header_footer, onLaterPages=_add_header_footer)