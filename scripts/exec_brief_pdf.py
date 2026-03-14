#!/usr/bin/env python3
"""
The Tribunal — Executive Brief (2-page PDF).

Reads a session-summary.md and distills it into a dense, two-page PDF
designed for a smart, busy reader who needs the signal without the noise.

Page 1: What was asked, what was decided, and why — the analytical core.
Page 2: How the panel got there, what's still open, and what to do next.

Standalone usage:
    python exec_brief_pdf.py /path/to/session-summary.md [output.pdf]

Programmatic usage:
    from exec_brief_pdf import generate_exec_brief
    pdf_path = generate_exec_brief("/path/to/session-summary.md")

Requires: reportlab>=4.0
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    Frame, PageTemplate, BaseDocTemplate, Flowable,
)

# Re-use the session-summary parser from the full PDF generator
from summary_pdf import (
    parse_session_summary, _md_inline_to_xml, _escape_xml,
    _parse_table, _parse_bullets,
)

# ---------------------------------------------------------------------------
# Color palette — same academic aesthetic as the full PDF
# ---------------------------------------------------------------------------
NAVY       = HexColor("#0D1B2A")
DARK_BLUE  = HexColor("#1B2A4A")
MED_BLUE   = HexColor("#2C3E6B")
ACCENT     = HexColor("#8B1A1A")   # Deep crimson
ACCENT2    = HexColor("#B8860B")   # Dark goldenrod
LIGHT_GRAY = HexColor("#F5F5F0")
MED_GRAY   = HexColor("#E8E6E0")
DARK_GRAY  = HexColor("#4A4A4A")
TEXT_COLOR  = HexColor("#1A1A1A")
MUTED      = HexColor("#6B6B6B")
TABLE_HEAD = HexColor("#1B2A4A")
TABLE_ALT  = HexColor("#F0EDE6")
RULE_COLOR = HexColor("#C0B8A8")
WHITE      = HexColor("#FFFFFF")

PAGE_W, PAGE_H = letter
LEFT_MARGIN = 0.7 * inch
RIGHT_MARGIN = 0.7 * inch
TOP_MARGIN = 0.65 * inch
BOTTOM_MARGIN = 0.6 * inch
CONTENT_W = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN


# ---------------------------------------------------------------------------
# Custom flowables
# ---------------------------------------------------------------------------

class ThinRule(Flowable):
    def __init__(self, width, color=RULE_COLOR, thickness=0.5):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 4

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 2, self.width, 2)


class AccentBar(Flowable):
    def __init__(self, width=30, color=ACCENT, thickness=2.5):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 5

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 2.5, self.width, 2.5)


class CalloutBox(Flowable):
    """Compact callout box with left accent bar."""
    def __init__(self, text, width, style, bg_color=LIGHT_GRAY, accent_color=ACCENT):
        Flowable.__init__(self)
        self.text = text
        self.box_width = width
        self.style = style
        self.bg_color = bg_color
        self.accent_color = accent_color
        p = Paragraph(text, style)
        w, h = p.wrap(width - 20, 1000)
        self.box_height = h + 14

    def wrap(self, availWidth, availHeight):
        return self.box_width, self.box_height

    def draw(self):
        self.canv.setFillColor(self.bg_color)
        self.canv.roundRect(0, 0, self.box_width, self.box_height, 2, fill=1, stroke=0)
        self.canv.setFillColor(self.accent_color)
        self.canv.rect(0, 0, 3, self.box_height, fill=1, stroke=0)
        p = Paragraph(self.text, self.style)
        p.wrap(self.box_width - 20, self.box_height)
        p.drawOn(self.canv, 14, 7)


# ---------------------------------------------------------------------------
# Styles — tighter than the full PDF for density
# ---------------------------------------------------------------------------

def build_styles():
    s = {}

    s['title'] = ParagraphStyle(
        'BriefTitle', fontName='Helvetica-Bold', fontSize=16, leading=19,
        textColor=NAVY, spaceAfter=1, alignment=TA_LEFT,
    )
    s['subtitle'] = ParagraphStyle(
        'BriefSubtitle', fontName='Helvetica', fontSize=8.5, leading=11,
        textColor=MUTED, spaceAfter=1, alignment=TA_LEFT,
    )
    s['h1'] = ParagraphStyle(
        'BriefH1', fontName='Helvetica-Bold', fontSize=11.5, leading=14,
        textColor=NAVY, spaceBefore=8, spaceAfter=3, alignment=TA_LEFT,
    )
    s['h2'] = ParagraphStyle(
        'BriefH2', fontName='Helvetica-Bold', fontSize=9.5, leading=12,
        textColor=DARK_BLUE, spaceBefore=6, spaceAfter=2, alignment=TA_LEFT,
    )
    s['body'] = ParagraphStyle(
        'BriefBody', fontName='Helvetica', fontSize=8.5, leading=12,
        textColor=TEXT_COLOR, spaceAfter=4, alignment=TA_JUSTIFY,
    )
    s['body_small'] = ParagraphStyle(
        'BriefBodySmall', fontName='Helvetica', fontSize=8, leading=11,
        textColor=TEXT_COLOR, spaceAfter=3, alignment=TA_JUSTIFY,
    )
    s['ruling'] = ParagraphStyle(
        'BriefRuling', fontName='Helvetica-Bold', fontSize=9, leading=13,
        textColor=TEXT_COLOR, spaceAfter=4, alignment=TA_LEFT,
    )
    s['bullet'] = ParagraphStyle(
        'BriefBullet', fontName='Helvetica', fontSize=8.5, leading=11.5,
        textColor=TEXT_COLOR, spaceAfter=2, leftIndent=12, bulletIndent=2,
        alignment=TA_LEFT,
    )
    s['bullet_small'] = ParagraphStyle(
        'BriefBulletSmall', fontName='Helvetica', fontSize=8, leading=11,
        textColor=TEXT_COLOR, spaceAfter=2, leftIndent=12, bulletIndent=2,
        alignment=TA_LEFT,
    )
    s['callout'] = ParagraphStyle(
        'BriefCallout', fontName='Helvetica', fontSize=8.5, leading=12,
        textColor=TEXT_COLOR, alignment=TA_LEFT,
    )
    s['meta'] = ParagraphStyle(
        'BriefMeta', fontName='Helvetica', fontSize=7, leading=9,
        textColor=MUTED, spaceAfter=1, alignment=TA_LEFT,
    )
    s['table_header'] = ParagraphStyle(
        'BriefTH', fontName='Helvetica-Bold', fontSize=7.5, leading=10,
        textColor=WHITE, alignment=TA_LEFT,
    )
    s['table_cell'] = ParagraphStyle(
        'BriefTC', fontName='Helvetica', fontSize=7.5, leading=10,
        textColor=TEXT_COLOR, alignment=TA_LEFT,
    )
    s['table_cell_bold'] = ParagraphStyle(
        'BriefTCB', fontName='Helvetica-Bold', fontSize=7.5, leading=10,
        textColor=TEXT_COLOR, alignment=TA_LEFT,
    )
    s['footer'] = ParagraphStyle(
        'BriefFooter', fontName='Helvetica', fontSize=6.5, leading=8,
        textColor=MUTED, alignment=TA_CENTER,
    )

    return s


# ---------------------------------------------------------------------------
# Document template
# ---------------------------------------------------------------------------

class ExecBriefTemplate(BaseDocTemplate):
    """Two-page executive brief with branded header/footer."""

    def __init__(self, filename, session_meta=None, **kwargs):
        BaseDocTemplate.__init__(self, filename, **kwargs)
        self.session_meta = session_meta or {}

        frame = Frame(
            LEFT_MARGIN, BOTTOM_MARGIN,
            CONTENT_W, PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
            id='brief',
        )
        template = PageTemplate(id='Brief', frames=[frame], onPage=self._draw_page)
        self.addPageTemplates([template])

    def _draw_page(self, canvas, doc):
        canvas.saveState()

        # Top rule
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(1.5)
        canvas.line(LEFT_MARGIN, PAGE_H - TOP_MARGIN + 10,
                    PAGE_W - RIGHT_MARGIN, PAGE_H - TOP_MARGIN + 10)

        # Header text
        canvas.setFont('Helvetica-Bold', 7)
        canvas.setFillColor(NAVY)
        canvas.drawString(LEFT_MARGIN, PAGE_H - TOP_MARGIN + 14,
                          "THE TRIBUNAL — EXECUTIVE BRIEF")

        session_id = self.session_meta.get("session_id", "")
        if session_id:
            canvas.setFont('Helvetica', 6.5)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(PAGE_W - RIGHT_MARGIN, PAGE_H - TOP_MARGIN + 14,
                                   session_id)

        # Bottom rule
        canvas.setStrokeColor(RULE_COLOR)
        canvas.setLineWidth(0.5)
        canvas.line(LEFT_MARGIN, BOTTOM_MARGIN - 6,
                    PAGE_W - RIGHT_MARGIN, BOTTOM_MARGIN - 6)

        # Page number (dynamic total via second pass)
        page_num = canvas.getPageNumber()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(PAGE_W / 2, BOTTOM_MARGIN - 16,
                                 "Page %d" % page_num)

        # Attribution
        canvas.setFont('Helvetica', 5.5)
        canvas.setFillColor(HexColor("#999999"))
        canvas.drawRightString(PAGE_W - RIGHT_MARGIN, BOTTOM_MARGIN - 16,
                               "The Tribunal — github.com/mdm-sfo/tribunal")

        canvas.restoreState()


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def _truncate_text(text, max_chars=600):
    """Truncate text to max_chars, breaking at sentence boundary."""
    if not text or len(text) <= max_chars:
        return text
    # Try to break at a sentence boundary
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.5:
        return truncated[:last_period + 1]
    return truncated.rstrip() + "..."


def _extract_ruling(bottom_line_text):
    """Extract the **Ruling:** line and the explanation separately."""
    if not bottom_line_text:
        return "", ""

    lines = bottom_line_text.strip().split("\n")
    ruling_lines = []
    explanation_lines = []
    in_ruling = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("**Ruling:**") or stripped.startswith("**Ruling**:"):
            in_ruling = True
            # Extract text after the Ruling: prefix
            after = re.sub(r'^\*\*Ruling\*?\*?:?\s*', '', stripped).strip()
            if after:
                ruling_lines.append(after)
        elif in_ruling and stripped and not stripped.startswith("**") and not stripped.startswith("#"):
            # Continuation of ruling (still in the bold intro)
            ruling_lines.append(stripped)
        else:
            in_ruling = False
            if stripped:
                explanation_lines.append(stripped)

    ruling = " ".join(ruling_lines).strip()
    explanation = "\n".join(explanation_lines).strip()

    # If no explicit Ruling: prefix found, use first paragraph as ruling
    if not ruling:
        paragraphs = bottom_line_text.strip().split("\n\n")
        if paragraphs:
            ruling = paragraphs[0].replace("\n", " ").strip()
            explanation = "\n\n".join(paragraphs[1:]).strip()

    return ruling, explanation


def _render_compact_markdown(text, styles, max_paragraphs=None):
    """Render markdown text as compact flowables."""
    flowables = []
    if not text:
        return flowables

    paragraphs = re.split(r'\n\n+', text.strip())
    if max_paragraphs:
        paragraphs = paragraphs[:max_paragraphs]

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Bullet list
        if para.startswith("- ") or para.startswith("* "):
            for bullet in _parse_bullets(para):
                flowables.append(Paragraph(
                    "<bullet>&bull;</bullet> " + _md_inline_to_xml(bullet),
                    styles['bullet_small'],
                ))
            continue

        # Numbered list
        if re.match(r'^\d+\.\s+', para):
            for bullet in _parse_bullets(para):
                flowables.append(Paragraph(
                    "<bullet>&bull;</bullet> " + _md_inline_to_xml(bullet),
                    styles['bullet_small'],
                ))
            continue

        # Regular paragraph
        flowables.append(Paragraph(
            _md_inline_to_xml(para.replace("\n", " ")),
            styles['body_small'],
        ))

    return flowables


def _make_compact_table(headers, rows, col_widths, styles):
    """Build a compact styled table."""
    header_cells = [Paragraph(_escape_xml(h), styles['table_header']) for h in headers]
    data_rows = []
    for row in rows:
        cells = []
        for idx, cell in enumerate(row):
            style = styles['table_cell_bold'] if idx == 0 else styles['table_cell']
            cells.append(Paragraph(_md_inline_to_xml(cell), style))
        data_rows.append(cells)

    table_data = [header_cells] + data_rows
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEAD),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, 0), 1, NAVY),
        ('LINEBELOW', (0, -1), (-1, -1), 0.75, NAVY),
        ('LINEBELOW', (0, 1), (-1, -2), 0.3, RULE_COLOR),
    ]
    for idx in range(1, len(table_data)):
        if idx % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, idx), (-1, idx), TABLE_ALT))
    t.setStyle(TableStyle(style_cmds))
    return t


# ---------------------------------------------------------------------------
# Story builder — the 2-page layout
# ---------------------------------------------------------------------------

def _build_brief_story(parsed, styles):
    """Build the two-page executive brief story."""
    story = []
    meta = parsed["header_meta"]

    # ==================================================================
    # PAGE 1: The Decision
    # ==================================================================

    # --- Header block ---
    story.append(Paragraph("Executive Brief", styles['title']))
    story.append(Spacer(1, 1))

    # Meta line
    meta_parts = []
    if meta.get("depth"):
        meta_parts.append("Depth: %s" % meta["depth"])
    if meta.get("advocates"):
        meta_parts.append("Advocates: %s" % meta["advocates"])
    if meta.get("judges"):
        meta_parts.append("Judges: %s" % meta["judges"])
    elif meta.get("cardinals"):
        meta_parts.append("Judges: %s" % meta["cardinals"])
    if meta.get("cost"):
        meta_parts.append("Cost: %s" % meta["cost"])
    if meta.get("time"):
        meta_parts.append("Time: %s" % meta["time"])
    date = meta.get("date", "")
    if date:
        meta_parts.insert(0, date)
    if meta_parts:
        story.append(Paragraph(_escape_xml(" | ".join(meta_parts)), styles['subtitle']))

    story.append(Spacer(1, 4))
    story.append(ThinRule(CONTENT_W, NAVY, 1))
    story.append(Spacer(1, 6))

    # --- The Question ---
    story.append(Paragraph("The Question", styles['h1']))
    story.append(AccentBar())
    story.append(Spacer(1, 4))

    if parsed["the_prompt"]:
        prompt_text = _truncate_text(parsed["the_prompt"], max_chars=500)
        story.append(CalloutBox(
            _md_inline_to_xml(prompt_text),
            CONTENT_W, styles['callout'], LIGHT_GRAY, MED_BLUE,
        ))
    story.append(Spacer(1, 6))

    # --- Bottom Line ---
    story.append(Paragraph("Bottom Line", styles['h1']))
    story.append(AccentBar(color=ACCENT))
    story.append(Spacer(1, 4))

    ruling, explanation = _extract_ruling(parsed["recommended_outcome"])

    if ruling:
        story.append(Paragraph(
            "<b>Ruling:</b> " + _md_inline_to_xml(ruling),
            styles['ruling'],
        ))
        story.append(Spacer(1, 2))

    if explanation:
        # Render explanation paragraphs — limit to keep within page 1
        explanation_flowables = _render_compact_markdown(
            explanation, styles, max_paragraphs=4,
        )
        story.extend(explanation_flowables)

    # --- Dissenting Opinions (compact, on page 1 if present) ---
    if parsed.get("dissenting_opinions"):
        story.append(Spacer(1, 4))
        story.append(Paragraph("Dissent", styles['h2']))
        story.append(Spacer(1, 2))
        dissent_text = _truncate_text(parsed["dissenting_opinions"], max_chars=400)
        story.extend(_render_compact_markdown(dissent_text, styles, max_paragraphs=2))

    # ==================================================================
    # PAGE 2: How We Got Here + Next Steps
    # ==================================================================

    # We don't force a page break — ReportLab will flow naturally.
    # But we add a thin rule to visually separate if it lands on the same page.
    story.append(Spacer(1, 8))
    story.append(ThinRule(CONTENT_W, RULE_COLOR, 0.5))
    story.append(Spacer(1, 6))

    # --- Key Moments ---
    story.append(Paragraph("Key Moments", styles['h1']))
    story.append(AccentBar(color=MED_BLUE))
    story.append(Spacer(1, 4))

    if parsed.get("key_moments"):
        # Limit to 5 key moments
        moments = parsed["key_moments"][:5]
        for moment in moments:
            story.append(Paragraph(
                "<bullet>&bull;</bullet> " + _md_inline_to_xml(moment),
                styles['bullet'],
            ))
        story.append(Spacer(1, 4))

    # --- Scorecard ---
    perf = parsed.get("council_performance")
    if perf:
        story.append(Paragraph("Scorecard", styles['h2']))
        story.append(Spacer(1, 3))

        if isinstance(perf, list) and perf and isinstance(perf[0], dict):
            # Convert advocate cards to a compact table
            headers = ["Model", "Opening", "Final", "Rank"]
            rows = []
            for adv in perf:
                rank_str = adv.get("rank", "")
                if rank_str and rank_str != "-":
                    rank_display = "#%s" % rank_str
                elif rank_str == "-":
                    rank_display = "W/D"
                else:
                    rank_display = ""
                opening = _truncate_text(adv.get("opening", ""), 80)
                final = _truncate_text(adv.get("final", ""), 80)
                rows.append([adv.get("model", ""), opening, final, rank_display])

            col_widths = [
                CONTENT_W * 0.18,
                CONTENT_W * 0.33,
                CONTENT_W * 0.33,
                CONTENT_W * 0.10,
            ]
            # Adjust if widths don't sum properly
            remainder = CONTENT_W - sum(col_widths)
            col_widths[-1] += remainder

            table = _make_compact_table(headers, rows, col_widths, styles)
            story.append(table)
            story.append(Spacer(1, 4))

        elif isinstance(perf, tuple):
            headers, rows = perf
            if headers and rows:
                n_cols = len(headers)
                col_widths = [CONTENT_W / n_cols] * n_cols
                table = _make_compact_table(headers, rows, col_widths, styles)
                story.append(table)
                story.append(Spacer(1, 4))

    # --- Convergence ---
    if parsed.get("convergence_assessment"):
        story.append(Paragraph("Convergence", styles['h2']))
        story.append(Spacer(1, 2))
        conv_text = _truncate_text(parsed["convergence_assessment"], max_chars=400)
        story.append(Paragraph(
            _md_inline_to_xml(conv_text.replace("\n", " ")),
            styles['body_small'],
        ))
        story.append(Spacer(1, 4))

    # --- Next Steps ---
    if parsed.get("next_steps"):
        story.append(Paragraph("Next Steps", styles['h1']))
        story.append(AccentBar(color=ACCENT2))
        story.append(Spacer(1, 3))
        next_steps_flowables = _render_compact_markdown(
            parsed["next_steps"], styles, max_paragraphs=6,
        )
        story.extend(next_steps_flowables)

    # --- Build This (compact pointer, not the full spec) ---
    if parsed.get("build_this"):
        story.append(Spacer(1, 4))
        story.append(Paragraph("Build This", styles['h2']))
        story.append(Spacer(1, 2))
        # Just the first paragraph or blockquote — point to full summary for details
        build_text = parsed["build_this"].strip()
        # Extract blockquote intro if present
        bq_lines = []
        for line in build_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(">"):
                bq_lines.append(stripped.lstrip("> ").strip())
            elif bq_lines:
                break
        if bq_lines:
            story.append(Paragraph(
                _md_inline_to_xml(" ".join(bq_lines)),
                styles['body_small'],
            ))
        else:
            story.append(Paragraph(
                _md_inline_to_xml(_truncate_text(build_text, 300)),
                styles['body_small'],
            ))
        story.append(Paragraph(
            "<i>See full session summary for complete implementation spec.</i>",
            styles['meta'],
        ))

    return story


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_exec_brief(md_path, output_path=None):
    """Generate a 2-page executive brief PDF from a session-summary.md file.

    Args:
        md_path: Path to session-summary.md.
        output_path: Where to write the PDF. Defaults to same directory,
            named *-exec-brief-*.pdf.

    Returns:
        The absolute path to the generated PDF.
    """
    md_path = str(md_path)
    md_text = Path(md_path).read_text(encoding="utf-8")
    parsed = parse_session_summary(md_text)

    if output_path is None:
        # Derive name from the summary file: replace "session-summary" with "exec-brief"
        md_name = Path(md_path).stem
        brief_name = md_name.replace("session-summary", "exec-brief")
        if brief_name == md_name:
            brief_name = md_name + "-exec-brief"
        output_path = str(Path(md_path).parent / (brief_name + ".pdf"))

    meta = parsed["header_meta"]
    session_id = meta.get("session", "")

    doc = ExecBriefTemplate(
        output_path,
        session_meta={"session_id": session_id},
        pagesize=letter,
        title="Tribunal Executive Brief",
        author="The Tribunal",
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
    )

    styles = build_styles()
    story = _build_brief_story(parsed, styles)
    doc.build(story)
    return os.path.abspath(output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python exec_brief_pdf.py <session-summary.md> [output.pdf]")
        sys.exit(1)

    md_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(md_path):
        print("Error: file not found: %s" % md_path)
        sys.exit(1)

    pdf_path = generate_exec_brief(md_path, output_path)
    print("Executive brief generated: %s" % pdf_path)


if __name__ == "__main__":
    main()
