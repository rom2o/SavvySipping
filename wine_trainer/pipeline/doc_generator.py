"""
doc_generator.py – PDF generation for SavvySipping wine training documents.
"""

import os
import re
import zipfile
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, HRFlowable,
)

# ── Brand colours ─────────────────────────────────────────────────────────────
BURGUNDY   = colors.HexColor("#722F37")
GOLD       = colors.HexColor("#C5A028")
CREAM      = colors.HexColor("#FFF9F0")
MID_GREY   = colors.HexColor("#CCCCCC")
DARK_TEXT  = colors.HexColor("#1A1A1A")
WHITE      = colors.white

# ── Page geometry ──────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_LEFT  = 2.0 * cm
MARGIN_RIGHT = 2.0 * cm
MARGIN_TOP   = 3.2 * cm
MARGIN_BOT   = 2.5 * cm
HEADER_STRIP_H = 1.4 * cm
FOOTER_STRIP_H = 0.8 * cm
CONTENT_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT


# ── Header / Footer ───────────────────────────────────────────────────────────
def _make_header_footer(doc_title, restaurant_name):
    def draw(canvas_obj, doc):
        canvas_obj.saveState()
        w, h = canvas_obj._pagesize
        strip_y = h - HEADER_STRIP_H
        canvas_obj.setFillColor(BURGUNDY)
        canvas_obj.rect(0, strip_y, w, HEADER_STRIP_H, stroke=0, fill=1)
        canvas_obj.setStrokeColor(GOLD)
        canvas_obj.setLineWidth(1.5)
        canvas_obj.line(0, strip_y, w, strip_y)
        canvas_obj.setFillColor(WHITE)
        canvas_obj.setFont("Helvetica-Bold", 9)
        canvas_obj.drawString(MARGIN_LEFT, strip_y + 0.38 * cm, doc_title)
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawRightString(w - MARGIN_RIGHT, strip_y + 0.38 * cm, restaurant_name)
        canvas_obj.setFillColor(BURGUNDY)
        canvas_obj.rect(0, 0, w, FOOTER_STRIP_H, stroke=0, fill=1)
        canvas_obj.setFillColor(WHITE)
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.drawString(MARGIN_LEFT, 0.22 * cm, "© SavvySipping | Confidential Staff Training Material")
        canvas_obj.setFont("Helvetica-Bold", 7)
        canvas_obj.drawRightString(w - MARGIN_RIGHT, 0.22 * cm, f"Page {doc.page}")
        canvas_obj.restoreState()
    return draw


# ── Styles ────────────────────────────────────────────────────────────────────
def _build_styles():
    base = getSampleStyleSheet()

    def s(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    return {
        "h1":           s("H1", "Heading1", fontSize=18, textColor=BURGUNDY,
                          spaceAfter=8, spaceBefore=6, fontName="Helvetica-Bold", leading=22),
        "h2":           s("H2", "Heading2", fontSize=14, textColor=BURGUNDY,
                          spaceAfter=6, spaceBefore=10, fontName="Helvetica-Bold", leading=18),
        "h3":           s("H3", "Heading3", fontSize=12, textColor=GOLD,
                          spaceAfter=4, spaceBefore=8, fontName="Helvetica-Bold", leading=16),
        "body":         s("Body", fontSize=10, textColor=DARK_TEXT, spaceAfter=5, leading=15),
        "bullet":       s("Bullet", fontSize=10, textColor=DARK_TEXT, spaceAfter=3,
                          leading=14, leftIndent=16, bulletIndent=6),
        "quote":        s("Quote", fontSize=10, textColor=colors.HexColor("#555555"),
                          fontName="Helvetica-Oblique", spaceAfter=4, leading=14,
                          leftIndent=20, rightIndent=20, backColor=CREAM),
        "table_header": s("TH", fontSize=9, textColor=WHITE, fontName="Helvetica-Bold",
                          alignment=TA_CENTER, leading=12),
        "table_cell":   s("TC", fontSize=9, textColor=DARK_TEXT, leading=12, spaceAfter=2),
    }


# ── Inline markdown → ReportLab XML ──────────────────────────────────────────
# Uses a SINGLE-PASS regex to avoid cross-tag contamination that causes
# invalid nesting like <b>text <i>word</b></i>.
# Fix: _([^_\n]+?)_ excludes underscore sequences (fill-in lines like _______)
_INLINE_PATTERN = re.compile(
    r'\*\*\*(.+?)\*\*\*'        # bold-italic ***text***
    r'|\*\*(.+?)\*\*'           # bold **text**
    r'|\*(.+?)\*'               # italic *text*
    r'|_([^_\n]+?)_'            # italic _text_  (excludes fill-in sequences)
    r'|`(.+?)`',                # code `text`
    re.DOTALL
)

def _inline(text: str) -> str:
    """Convert markdown inline markup to ReportLab XML in a single pass."""
    # Escape XML special characters first
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Unescape \_ → _ so Claude's fill-in lines (\_____) render as plain underscores
    text = re.sub(r'\\(_+)', r'\1', text)

    def replacer(m):
        if m.group(1):  # ***bold-italic***
            return f'<b><i>{m.group(1)}</i></b>'
        if m.group(2):  # **bold**
            return f'<b>{m.group(2)}</b>'
        if m.group(3):  # *italic*
            return f'<i>{m.group(3)}</i>'
        if m.group(4):  # _italic_
            return f'<i>{m.group(4)}</i>'
        if m.group(5):  # `code`
            return f"<font name='Courier'>{m.group(5)}</font>"
        return m.group(0)

    return _INLINE_PATTERN.sub(replacer, text)


def _safe_para(text: str, style) -> Paragraph:
    """
    Create a Paragraph safely. If ReportLab rejects the markup,
    strip all tags and fall back to plain text.
    """
    try:
        return Paragraph(text, style)
    except Exception:
        # Strip all XML tags and retry as plain text
        clean = re.sub(r'<[^>]+>', '', text)
        try:
            return Paragraph(clean, style)
        except Exception:
            return Paragraph('', style)


# ── Table renderer ────────────────────────────────────────────────────────────
def _is_sep(cells):
    return all(re.match(r'^[-: ]+$', c.strip()) for c in cells if c.strip())


def _col_widths(n):
    presets = {5: [.28,.22,.22,.16,.12], 4: [.30,.25,.25,.20],
               3: [.40,.35,.25], 2: [.55,.45]}
    return [CONTENT_W * r for r in presets.get(n, [1/n]*n)[:n]]


def _render_table(lines, styles):
    rows = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if _is_sep(cells):
            continue
        rows.append(cells)
    if not rows:
        return None
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    data = [
        [_safe_para(_inline(c), styles["table_header"] if i == 0 else styles["table_cell"])
         for c in row]
        for i, row in enumerate(rows)
    ]
    tbl = Table(data, colWidths=_col_widths(n), repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  BURGUNDY),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [CREAM, WHITE]),
        ("GRID",          (0,0), (-1,-1), 0.5, MID_GREY),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
    ]))
    return tbl


# ── Markdown → flowables ──────────────────────────────────────────────────────
def _md_to_flowables(md_text, styles):
    flowables = []
    lines = md_text.splitlines()
    i = 0
    sections_seen = 0

    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if not s:
            i += 1
            continue

        if re.match(r'^[-*_]{3,}$', s):
            flowables.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=6))
            i += 1
            continue

        if s.startswith("|"):
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            tbl = _render_table(tbl_lines, styles)
            if tbl:
                flowables.append(Spacer(1, 6))
                flowables.append(tbl)
                flowables.append(Spacer(1, 8))
            continue

        if s.startswith("# ") and not s.startswith("## "):
            if sections_seen > 0:
                flowables.append(PageBreak())
            sections_seen += 1
            flowables.append(_safe_para(_inline(s[2:].strip()), styles["h1"]))
            flowables.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6))
            i += 1
            continue

        if s.startswith("## ") and not s.startswith("### "):
            flowables.append(Spacer(1, 4))
            flowables.append(_safe_para(_inline(s[3:].strip()), styles["h2"]))
            i += 1
            continue

        if s.startswith("### "):
            flowables.append(_safe_para(_inline(s[4:].strip()), styles["h3"]))
            i += 1
            continue

        if s.startswith("> "):
            flowables.append(Spacer(1, 3))
            flowables.append(_safe_para(_inline(s[2:].strip()), styles["quote"]))
            flowables.append(Spacer(1, 3))
            i += 1
            continue

        if re.match(r'^[-*•]\s+', s):
            flowables.append(_safe_para("• " + _inline(re.sub(r'^[-*•]\s+', '', s)), styles["bullet"]))
            i += 1
            continue

        if re.match(r'^\d+[.)]\s+', s):
            num = re.match(r'^(\d+)[.)]\s+', s).group(1)
            flowables.append(_safe_para(f"{num}. " + _inline(re.sub(r'^\d+[.)]\s+', '', s)), styles["bullet"]))
            i += 1
            continue

        text = _inline(s)
        if text:
            flowables.append(_safe_para(text, styles["body"]))
        i += 1

    return flowables


# ── Cover page ────────────────────────────────────────────────────────────────
def _cover_page(title, subtitle, restaurant_name, styles):
    return [
        Spacer(1, 2.5 * cm),
        HRFlowable(width="60%", thickness=3, color=BURGUNDY, hAlign="CENTER", spaceAfter=20),
        _safe_para(title, ParagraphStyle("Cv", fontSize=26, textColor=BURGUNDY,
                                         fontName="Helvetica-Bold", alignment=TA_CENTER,
                                         spaceAfter=10, leading=30)),
        _safe_para(subtitle, ParagraphStyle("CvS", fontSize=14, textColor=GOLD,
                                             fontName="Helvetica-Bold", alignment=TA_CENTER,
                                             spaceAfter=6, leading=18)),
        Spacer(1, 0.5 * cm),
        HRFlowable(width="40%", thickness=1.5, color=GOLD, hAlign="CENTER", spaceAfter=12),
        _safe_para(restaurant_name, ParagraphStyle("CvR", fontSize=12, textColor=DARK_TEXT,
                                                    fontName="Helvetica", alignment=TA_CENTER,
                                                    spaceAfter=6, leading=16)),
        _safe_para("Prepared by SavvySipping",
                   ParagraphStyle("CvP", fontSize=9, textColor=MID_GREY, alignment=TA_CENTER)),
        PageBreak(),
    ]


# ── PDF builder ───────────────────────────────────────────────────────────────
def _build_pdf(flowables, title, restaurant_name):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=MARGIN_LEFT, rightMargin=MARGIN_RIGHT,
                            topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOT,
                            title=title, author="SavvySipping")
    doc.build(flowables,
              onFirstPage=_make_header_footer(title, restaurant_name),
              onLaterPages=_make_header_footer(title, restaurant_name))
    return buf.getvalue()


# ── Split helpers ─────────────────────────────────────────────────────────────
def _split_cheat(text):
    marker = "<<<CHEAT_SHEET>>>"
    if marker in text:
        parts = text.split(marker, 1)
        if parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    m = re.compile(r'^#{1,2}\s+.*?(cheat\s*sheet|quick[\s-]?ref)',
                   re.IGNORECASE | re.MULTILINE).search(text)
    if m:
        return text[:m.start()].strip(), text[m.start():].strip()
    return text.strip(), ""


def _split_key(text):
    m = re.compile(r'^#{1,2}\s+answer\s+key',
                   re.IGNORECASE | re.MULTILINE).search(text)
    if m:
        return text[:m.start()].strip(), text[m.start():].strip()
    return text.strip(), ""


# ── Main entry points ─────────────────────────────────────────────────────────
def generate_all_pdfs(content, restaurant_name, output_dir):
    """
    Accept the dict returned by analyze_wine_list().
    Keys: training_guide, cheat_sheet, knowledge_test, answer_key
    """
    training_md = content.get("training_guide", "")
    cheat_md    = content.get("cheat_sheet", "")
    mcq_md      = content.get("knowledge_test", "")
    key_md      = content.get("answer_key", "")

    # Strip any leading "# Answer Key" heading from key_md to prevent a double
    # heading (and the blank page it causes) when generate_pdfs prepends its own.
    key_md_clean = re.sub(
        r'^#{1,2}\s+answer\s+key[^\n]*\n*', '', key_md, count=1, flags=re.IGNORECASE
    ).strip()

    return generate_pdfs(
        call1_text=training_md + ("\n\n<<<CHEAT_SHEET>>>\n\n" + cheat_md if cheat_md else ""),
        call2_text=mcq_md + ("\n\n# Answer Key\n\n" + key_md_clean if key_md_clean else ""),
        restaurant_name=restaurant_name,
        output_dir=output_dir,
    )


def generate_pdfs(call1_text, call2_text, restaurant_name, output_dir):
    """Legacy interface: accepts raw text strings."""
    os.makedirs(output_dir, exist_ok=True)
    styles = _build_styles()

    training_md, cheat_md = _split_cheat(call1_text)
    mcq_md,      key_md   = _split_key(call2_text)

    safe = re.sub(r'[^\w\s-]', '', restaurant_name).strip().replace(' ', '_')

    training_pdf = _build_pdf(
        _cover_page("Wine Mastery Training Guide", "Staff Training Programme", restaurant_name, styles)
        + _md_to_flowables(training_md, styles),
        "Wine Mastery Training Guide", restaurant_name)

    mcq_pdf = _build_pdf(
        _cover_page("Wine Knowledge Test", "21 Questions + Service Scenarios", restaurant_name, styles)
        + (_md_to_flowables(mcq_md, styles) if mcq_md else []),
        "Wine Knowledge Test", restaurant_name)

    cheat_content = (_md_to_flowables(cheat_md, styles) if cheat_md
                     else [_safe_para("See the Training Guide for full wine list details.", styles["body"])])
    cheat_pdf = _build_pdf(
        _cover_page("Wine Cheat Sheet", "Quick-Reference Guide", restaurant_name, styles) + cheat_content,
        "Wine Cheat Sheet", restaurant_name)

    key_pdf = _build_pdf(
        _cover_page("Answer Key", "Manager Copy — Confidential", restaurant_name, styles)
        + (_md_to_flowables(key_md, styles) if key_md else []),
        "Answer Key", restaurant_name)

    paths = {
        "training_guide": os.path.join(output_dir, f"{safe}_Training_Guide.pdf"),
        "knowledge_test":  os.path.join(output_dir, f"{safe}_Knowledge_Test.pdf"),
        "cheat_sheet":     os.path.join(output_dir, f"{safe}_Cheat_Sheet.pdf"),
        "answer_key":      os.path.join(output_dir, f"{safe}_Answer_Key.pdf"),
    }
    with open(paths["training_guide"], "wb") as f: f.write(training_pdf)
    with open(paths["knowledge_test"],  "wb") as f: f.write(mcq_pdf)
    with open(paths["cheat_sheet"],     "wb") as f: f.write(cheat_pdf)
    with open(paths["answer_key"],      "wb") as f: f.write(key_pdf)
    return paths


def create_zip(pdf_paths, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, path in pdf_paths.items():
            if os.path.exists(path):
                zf.write(path, os.path.basename(path))
    return zip_path
