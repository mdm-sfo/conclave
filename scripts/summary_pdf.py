#!/usr/bin/env python3
"""
The Tribunal — Session Summary PDF Generator.

Reads a session-summary.md file (the canonical output from council_orchestrator.py)
and renders it as a polished, academic-style PDF using ReportLab.

Standalone usage:
    python summary_pdf.py /path/to/session-summary.md [output.pdf]

Programmatic usage:
    from summary_pdf import generate_summary_pdf
    pdf_path = generate_summary_pdf("/path/to/session-summary.md")

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
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, Frame, PageTemplate,
    BaseDocTemplate, NextPageTemplate, Flowable,
)


# ---------------------------------------------------------------------------
# Color palette — dark academic aesthetic (Navy + Crimson + Goldenrod)
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
LEFT_MARGIN = 1.0 * inch
RIGHT_MARGIN = 1.0 * inch
TOP_MARGIN = 0.85 * inch
BOTTOM_MARGIN = 0.9 * inch
CONTENT_W = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN


# ---------------------------------------------------------------------------
# Custom flowables
# ---------------------------------------------------------------------------

class ThinRule(Flowable):
    """A thin horizontal rule."""
    def __init__(self, width, color=RULE_COLOR, thickness=0.5):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 6

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 3, self.width, 3)


class ThickRule(Flowable):
    """A thick horizontal rule for major sections."""
    def __init__(self, width, color=NAVY, thickness=2):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 10

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 5, self.width, 5)


class AccentBar(Flowable):
    """A small accent bar for visual emphasis."""
    def __init__(self, width=40, color=ACCENT, thickness=3):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 8

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 4, self.width, 4)


class CalloutBox(Flowable):
    """A highlighted callout box with left accent bar."""
    def __init__(self, text, width, style, bg_color=LIGHT_GRAY, accent_color=ACCENT):
        Flowable.__init__(self)
        self.text = text
        self.box_width = width
        self.style = style
        self.bg_color = bg_color
        self.accent_color = accent_color
        # Calculate height
        p = Paragraph(text, style)
        w, h = p.wrap(width - 24, 1000)
        self.box_height = h + 20

    def wrap(self, availWidth, availHeight):
        return self.box_width, self.box_height

    def draw(self):
        # Background
        self.canv.setFillColor(self.bg_color)
        self.canv.roundRect(0, 0, self.box_width, self.box_height, 3, fill=1, stroke=0)
        # Left accent bar
        self.canv.setFillColor(self.accent_color)
        self.canv.rect(0, 0, 4, self.box_height, fill=1, stroke=0)
        # Text
        p = Paragraph(self.text, self.style)
        p.wrap(self.box_width - 24, self.box_height)
        p.drawOn(self.canv, 16, 10)


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def build_styles():
    # type: () -> dict
    styles = {}

    styles['title'] = ParagraphStyle(
        'Title',
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=28,
        textColor=NAVY,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    styles['subtitle'] = ParagraphStyle(
        'Subtitle',
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=MUTED,
        spaceAfter=2,
        alignment=TA_LEFT,
    )

    styles['h1'] = ParagraphStyle(
        'H1',
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=22,
        textColor=NAVY,
        spaceBefore=18,
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    styles['h2'] = ParagraphStyle(
        'H2',
        fontName='Helvetica-Bold',
        fontSize=12.5,
        leading=17,
        textColor=DARK_BLUE,
        spaceBefore=14,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    styles['h3'] = ParagraphStyle(
        'H3',
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=MED_BLUE,
        spaceBefore=10,
        spaceAfter=3,
        alignment=TA_LEFT,
    )

    styles['body'] = ParagraphStyle(
        'Body',
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=TEXT_COLOR,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )

    styles['body_bold'] = ParagraphStyle(
        'BodyBold',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=14,
        textColor=TEXT_COLOR,
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    styles['bullet'] = ParagraphStyle(
        'Bullet',
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=TEXT_COLOR,
        spaceAfter=3,
        leftIndent=16,
        bulletIndent=4,
        alignment=TA_LEFT,
    )

    styles['sub_bullet'] = ParagraphStyle(
        'SubBullet',
        fontName='Helvetica',
        fontSize=9,
        leading=12.5,
        textColor=DARK_GRAY,
        spaceAfter=2,
        leftIndent=32,
        bulletIndent=20,
        alignment=TA_LEFT,
    )

    styles['callout'] = ParagraphStyle(
        'Callout',
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=TEXT_COLOR,
        alignment=TA_LEFT,
    )

    styles['callout_bold'] = ParagraphStyle(
        'CalloutBold',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=14,
        textColor=ACCENT,
        alignment=TA_LEFT,
    )

    styles['table_header'] = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=WHITE,
        alignment=TA_LEFT,
    )

    styles['table_cell'] = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_COLOR,
        alignment=TA_LEFT,
    )

    styles['table_cell_bold'] = ParagraphStyle(
        'TableCellBold',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_COLOR,
        alignment=TA_LEFT,
    )

    styles['quote'] = ParagraphStyle(
        'Quote',
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=13,
        textColor=DARK_GRAY,
        leftIndent=20,
        rightIndent=20,
        spaceBefore=4,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    styles['build_this'] = ParagraphStyle(
        'BuildThis',
        fontName='Courier',
        fontSize=8.5,
        leading=12,
        textColor=TEXT_COLOR,
        leftIndent=8,
        rightIndent=8,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    styles['meta'] = ParagraphStyle(
        'Meta',
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=MUTED,
        spaceAfter=2,
        alignment=TA_LEFT,
    )

    styles['footer'] = ParagraphStyle(
        'Footer',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=MUTED,
        alignment=TA_CENTER,
    )

    return styles


# ---------------------------------------------------------------------------
# Document template with Tribunal-branded header/footer
# ---------------------------------------------------------------------------

class TribunalDocTemplate(BaseDocTemplate):
    """PDF document template with Tribunal branding on every page."""

    def __init__(self, filename, session_meta=None, **kwargs):
        # type: (str, Optional[dict], ...) -> None
        BaseDocTemplate.__init__(self, filename, **kwargs)
        self.session_meta = session_meta or {}

        frame = Frame(
            LEFT_MARGIN, BOTTOM_MARGIN,
            CONTENT_W, PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
            id='normal'
        )

        cover_template = PageTemplate(
            id='Cover',
            frames=[frame],
            onPage=self._cover_page,
        )
        normal_template = PageTemplate(
            id='Normal',
            frames=[frame],
            onPage=self._normal_page,
        )
        self.addPageTemplates([cover_template, normal_template])

    def _cover_page(self, canvas, doc):
        """Minimal cover page — no header/footer."""
        canvas.saveState()
        canvas.restoreState()

    def _normal_page(self, canvas, doc):
        """Header rule + page number footer, Tribunal branded."""
        canvas.saveState()

        # Top rule
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(1.5)
        canvas.line(LEFT_MARGIN, PAGE_H - TOP_MARGIN + 12,
                    PAGE_W - RIGHT_MARGIN, PAGE_H - TOP_MARGIN + 12)

        # Thin rule under header
        canvas.setStrokeColor(RULE_COLOR)
        canvas.setLineWidth(0.5)
        canvas.line(LEFT_MARGIN, PAGE_H - TOP_MARGIN + 8,
                    PAGE_W - RIGHT_MARGIN, PAGE_H - TOP_MARGIN + 8)

        # Header text
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(LEFT_MARGIN, PAGE_H - TOP_MARGIN + 16,
                          "The Tribunal — Session Summary")
        session_id = self.session_meta.get("session_id", "")
        if session_id:
            canvas.drawRightString(PAGE_W - RIGHT_MARGIN, PAGE_H - TOP_MARGIN + 16,
                                   session_id)

        # Bottom rule
        canvas.setStrokeColor(RULE_COLOR)
        canvas.setLineWidth(0.5)
        canvas.line(LEFT_MARGIN, BOTTOM_MARGIN - 8,
                    PAGE_W - RIGHT_MARGIN, BOTTOM_MARGIN - 8)

        # Page number
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(MUTED)
        page_num = canvas.getPageNumber()
        canvas.drawCentredString(PAGE_W / 2, BOTTOM_MARGIN - 22, str(page_num))

        # Classification
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(HexColor("#999999"))
        canvas.drawRightString(PAGE_W - RIGHT_MARGIN, BOTTOM_MARGIN - 22,
                               "Generated by The Tribunal — github.com/mdm-sfo/tribunal")

        canvas.restoreState()


# ---------------------------------------------------------------------------
# Markdown parser — targeted at the session-summary.md format
# ---------------------------------------------------------------------------

def _escape_xml(text):
    # type: (str) -> str
    """Escape characters that break ReportLab XML paragraphs."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _md_inline_to_xml(text):
    # type: (str) -> str
    """Convert markdown inline formatting to ReportLab XML.

    Handles **bold**, *italic*, `code`, and leaves everything else escaped.
    """
    # Escape XML-unsafe characters first, but preserve markdown markers
    # We do this carefully: escape & < > but not * or `
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    # Bold: **text** -> <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Italic: *text* -> <i>\1</i>  (must come after bold)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # Inline code: `text` -> <font face="Courier" size="8">text</font>
    text = re.sub(r'`(.+?)`', r'<font face="Courier" size="8">\1</font>', text)

    return text


def _parse_header_meta(header_block):
    # type: (str) -> dict
    """Extract metadata from the deterministic header block.

    Expected format:
        # Conclave Session Summary
        **Session: ABC123 | Depth: T3 | Advocates: 5 | Judges: 3 | Cost: $1.2345 | Time: 4m 30s**
        *Full logs: ... | Audit trail: ... | Narrative: ...*
    """
    meta = {}  # type: dict
    for line in header_block.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            meta["title"] = line[2:].strip()
        elif line.startswith("**") and "Session:" in line:
            # Strip ** wrappers
            inner = line.strip("*").strip()
            for part in inner.split("|"):
                part = part.strip()
                if ":" in part:
                    key, val = part.split(":", 1)
                    meta[key.strip().lower()] = val.strip()
        elif line.startswith("*") and "Full logs:" in line:
            meta["logs_line"] = line.strip("*").strip()
        elif line.startswith("*Note:") or line.startswith("*note:"):
            meta["anonymization_note"] = line.strip("*").strip()
    return meta


def _parse_table(lines):
    # type: (list) -> tuple
    """Parse a markdown table into (headers, rows).

    Returns (list[str], list[list[str]]).
    """
    headers = []  # type: list
    rows = []  # type: list
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]  # skip empty first/last
        if not cells:
            continue
        # Skip separator rows (all dashes/colons)
        if all(re.match(r'^[-:]+$', c) for c in cells):
            continue
        if not headers:
            headers = cells
        else:
            rows.append(cells)
    return headers, rows


def _parse_council_subsections(text):
    # type: (str) -> list
    """Parse council performance subsections into list of dicts.

    Expects markdown like:
        #### GPT-5 — Rank #1
        **Opening Position:** ...
        **Final Position:** ...
        **Key Catalyst:** ...

    Returns list of dicts with keys: model, rank, opening, final, catalyst.
    Returns empty list if no #### headings found (e.g., old table format).
    """
    advocates = []  # type: list
    current = None  # type: Optional[dict]

    for line in text.split("\n"):
        stripped = line.strip()

        # Detect #### heading like "#### GPT-5 — Rank #1"
        if stripped.startswith("#### "):
            if current:
                advocates.append(current)
            heading = stripped[5:].strip()
            # Parse "Model Name — Rank #N" or "Model Name - Rank #N"
            parts = re.split(r'\s*[—–-]\s*Rank\s*', heading, maxsplit=1)
            model = parts[0].strip() if parts else heading
            rank = ""
            if len(parts) > 1:
                rank_match = re.search(r'#?(\d+)', parts[1])
                if rank_match:
                    rank = rank_match.group(1)
                elif "-" in parts[1]:
                    rank = "-"
            current = {"model": model, "rank": rank, "opening": "", "final": "", "catalyst": ""}
            continue

        if current is None:
            continue

        # Parse bold-prefixed fields
        if stripped.startswith("**Opening Position:**"):
            current["opening"] = stripped.replace("**Opening Position:**", "").strip()
        elif stripped.startswith("**Final Position:**"):
            current["final"] = stripped.replace("**Final Position:**", "").strip()
        elif stripped.startswith("**Key Catalyst:**"):
            current["catalyst"] = stripped.replace("**Key Catalyst:**", "").strip()

    if current:
        advocates.append(current)

    return advocates


def _strip_yaml_frontmatter(md_text):
    # type: (str) -> tuple
    """Strip YAML frontmatter from markdown text.

    Returns (frontmatter_dict, remaining_text). If no frontmatter, returns
    ({}, original_text).
    """
    stripped = md_text.lstrip()
    if not stripped.startswith("---"):
        return {}, md_text
    # Find the closing ---
    lines = stripped.split("\n")
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, md_text
    # Parse simple key: value pairs from frontmatter
    meta = {}
    for line in lines[1:end_idx]:
        line = line.strip()
        if ":" in line and not line.startswith("-") and not line.startswith("#"):
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()
    remaining = "\n".join(lines[end_idx + 1:]).lstrip("\n")
    return meta, remaining


def parse_session_summary(md_text):
    # type: (str) -> dict
    """Parse session-summary.md into structured sections.

    Handles optional YAML frontmatter (skipped during parsing, metadata
    merged into header_meta).

    Backward-compatible: accepts both old names (Recommended Outcome,
    Council Performance) and new names (Bottom Line, Scorecard).

    Returns a dict with keys:
        header_meta: dict of session metadata
        the_prompt: str
        recommended_outcome: str (also accepts "Bottom Line")
        majority_opinion: str or None
        council_performance: list[dict] or (headers, rows) (also accepts "Scorecard")
        convergence_assessment: str or None
        key_moments: list[str]
        next_steps: str or None
        dissenting_opinions: str or None
        build_this: str or None
        how_tribunal_works: str or None
        glossary: str or None
        inline_appendices: list of (title, content) tuples
    """
    result = {
        "header_meta": {},
        "the_prompt": "",
        "recommended_outcome": "",  # also accepts "Bottom Line"
        "majority_opinion": None,
        "council_performance": ([], []),  # also accepts "Scorecard"
        "convergence_assessment": None,
        "key_moments": [],
        "next_steps": None,  # new: accepts "Next Steps"
        "dissenting_opinions": None,
        "build_this": None,
        "how_tribunal_works": None,
        "glossary": None,
        "inline_appendices": [],
    }

    # Strip YAML frontmatter if present
    yaml_meta, md_text = _strip_yaml_frontmatter(md_text)

    lines = md_text.split("\n")
    current_section = "header"
    current_subsection = None
    buffer = []  # type: list

    def flush_buffer():
        # type: () -> str
        text = "\n".join(buffer).strip()
        buffer.clear()
        return text

    def _is_heading(stripped_line, *labels):
        # type: (str, *str) -> bool
        """Match a heading with or without ## / ### prefix.

        Handles LLMs that occasionally drop markdown heading markers.
        Matches: "## Bottom Line", "### Scorecard", or bare "Bottom Line".
        Only matches bare text if it's on its own line (already stripped).
        """
        for label in labels:
            # With markdown prefix
            if stripped_line.startswith("## " + label) or stripped_line.startswith("### " + label):
                return True
            # Bare heading (exact match, case-insensitive)
            if stripped_line.lower() == label.lower():
                return True
        return False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect section headers
        if _is_heading(stripped, "The Question", "The Prompt"):
            if current_section == "header":
                result["header_meta"] = _parse_header_meta(flush_buffer())
            else:
                flush_buffer()
            current_section = "the_prompt"
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "Recommended Outcome", "Bottom Line"):
            if current_section == "the_prompt":
                result["the_prompt"] = flush_buffer()
            else:
                flush_buffer()
            current_section = "recommended_outcome"
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "Opinion of the Court", "Majority Opinion"):
            if current_section == "recommended_outcome":
                result["recommended_outcome"] = flush_buffer()
            else:
                flush_buffer()
            current_section = "majority_opinion"
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "How We Got Here"):
            if current_section == "majority_opinion":
                result["majority_opinion"] = flush_buffer()
            elif current_section == "recommended_outcome":
                result["recommended_outcome"] = flush_buffer()
            else:
                flush_buffer()
            current_section = "how_we_got_here"
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "Council Performance", "Scorecard"):
            if current_subsection == "key_moments":
                moments_text = flush_buffer()
                result["key_moments"] = _parse_bullets(moments_text)
            else:
                flush_buffer()
            current_section = "how_we_got_here"
            current_subsection = "council_performance"
            i += 1
            continue

        if _is_heading(stripped, "Convergence Assessment"):
            if current_subsection == "council_performance":
                perf_text = flush_buffer()
                advocates = _parse_council_subsections(perf_text)
                if advocates:
                    result["council_performance"] = advocates
                else:
                    result["council_performance"] = _parse_table(perf_text.split("\n"))
            else:
                flush_buffer()
            current_section = "how_we_got_here"
            current_subsection = "convergence_assessment"
            i += 1
            continue

        if _is_heading(stripped, "Key Moments"):
            if current_subsection == "convergence_assessment":
                result["convergence_assessment"] = flush_buffer()
            elif current_subsection == "council_performance":
                perf_text = flush_buffer()
                advocates = _parse_council_subsections(perf_text)
                if advocates:
                    result["council_performance"] = advocates
                else:
                    result["council_performance"] = _parse_table(perf_text.split("\n"))
            else:
                flush_buffer()
            current_section = "how_we_got_here"
            current_subsection = "key_moments"
            i += 1
            continue

        if _is_heading(stripped, "Next Steps"):
            # Flush whatever subsection came before
            if current_subsection == "key_moments":
                moments_text = flush_buffer()
                result["key_moments"] = _parse_bullets(moments_text)
            elif current_subsection == "convergence_assessment":
                result["convergence_assessment"] = flush_buffer()
            elif current_subsection == "council_performance":
                perf_text = flush_buffer()
                advocates = _parse_council_subsections(perf_text)
                if advocates:
                    result["council_performance"] = advocates
                else:
                    result["council_performance"] = _parse_table(perf_text.split("\n"))
            else:
                flush_buffer()
            current_section = "next_steps"
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "Dissenting Opinions"):
            if current_section == "next_steps":
                result["next_steps"] = flush_buffer()
            elif current_subsection == "key_moments":
                moments_text = flush_buffer()
                result["key_moments"] = _parse_bullets(moments_text)
            else:
                flush_buffer()
            current_section = "dissenting_opinions"
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "Build This"):
            if current_section == "next_steps":
                result["next_steps"] = flush_buffer()
            elif current_subsection == "key_moments":
                moments_text = flush_buffer()
                result["key_moments"] = _parse_bullets(moments_text)
            elif current_section == "dissenting_opinions":
                result["dissenting_opinions"] = flush_buffer()
            else:
                flush_buffer()
            current_section = "build_this"
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "How The Tribunal Works", "How the Tribunal Works"):
            # Flush whatever section came before
            if current_section == "next_steps":
                result["next_steps"] = flush_buffer()
            elif current_section == "build_this":
                result["build_this"] = flush_buffer()
            elif current_subsection == "key_moments":
                moments_text = flush_buffer()
                result["key_moments"] = _parse_bullets(moments_text)
            elif current_section == "dissenting_opinions":
                result["dissenting_opinions"] = flush_buffer()
            else:
                flush_buffer()
            current_section = "how_tribunal_works"
            current_subsection = None
            i += 1
            continue

        # Generic appendix detection: ## Appendix A: Title, or bare Appendix A: Title
        appendix_match = re.match(r'^(?:#{1,3}\s+)?Appendix\s+([A-Z]):\s*(.*)', stripped)
        if appendix_match:
            appendix_title = appendix_match.group(2).strip()
            # Flush whatever section came before
            if current_section == "how_tribunal_works":
                result["how_tribunal_works"] = flush_buffer()
            elif current_section == "build_this":
                result["build_this"] = flush_buffer()
            elif current_section == "inline_appendix":
                result["inline_appendices"].append((_current_appendix_title, flush_buffer()))
            elif current_section == "glossary":
                result["glossary"] = flush_buffer()
            else:
                flush_buffer()
            # If the appendix is "Glossary", treat it as the glossary section
            if "glossary" in appendix_title.lower():
                current_section = "glossary"
            else:
                current_section = "inline_appendix"
                _current_appendix_title = appendix_title
            current_subsection = None
            i += 1
            continue

        if _is_heading(stripped, "Glossary"):
            if current_section == "how_tribunal_works":
                result["how_tribunal_works"] = flush_buffer()
            elif current_section == "build_this":
                result["build_this"] = flush_buffer()
            elif current_section == "inline_appendix":
                result["inline_appendices"].append((_current_appendix_title, flush_buffer()))
            else:
                flush_buffer()
            current_section = "glossary"
            current_subsection = None
            i += 1
            continue

        # Skip the --- separator after the header
        if stripped == "---" and current_section == "header":
            i += 1
            continue

        buffer.append(line)
        i += 1

    # Flush remaining buffer
    remaining = flush_buffer()
    if current_section == "glossary":
        result["glossary"] = remaining
    elif current_section == "inline_appendix":
        result["inline_appendices"].append((_current_appendix_title, remaining))
    elif current_section == "how_tribunal_works":
        result["how_tribunal_works"] = remaining
    elif current_section == "next_steps":
        result["next_steps"] = remaining
    elif current_section == "build_this":
        result["build_this"] = remaining
    elif current_section == "dissenting_opinions":
        result["dissenting_opinions"] = remaining
    elif current_section == "majority_opinion":
        result["majority_opinion"] = remaining
    elif current_subsection == "convergence_assessment":
        result["convergence_assessment"] = remaining
    elif current_subsection == "key_moments":
        result["key_moments"] = _parse_bullets(remaining)
    elif current_subsection == "council_performance":
        advocates = _parse_council_subsections(remaining)
        if advocates:
            result["council_performance"] = advocates
        else:
            result["council_performance"] = _parse_table(remaining.split("\n"))
    elif current_section == "the_prompt":
        result["the_prompt"] = remaining
    elif current_section == "recommended_outcome":
        result["recommended_outcome"] = remaining

    # Merge YAML frontmatter into header_meta (YAML takes precedence)
    if yaml_meta:
        for k, v in yaml_meta.items():
            if k not in result["header_meta"]:
                result["header_meta"][k] = v

    return result


def _parse_bullets(text):
    # type: (str) -> list
    """Parse markdown bullet or numbered list into list of strings."""
    bullets = []
    current = []  # type: list
    for line in text.split("\n"):
        stripped = line.strip()
        # Match "- ", "* ", or "1. ", "2. ", etc.
        is_bullet = stripped.startswith("- ") or stripped.startswith("* ")
        numbered_match = re.match(r'^(\d+)\.\s+', stripped) if not is_bullet else None
        if is_bullet:
            if current:
                bullets.append(" ".join(current))
            current = [stripped[2:]]
        elif numbered_match:
            if current:
                bullets.append(" ".join(current))
            current = [stripped[numbered_match.end():]]
        elif stripped and current:
            # Continuation line
            current.append(stripped)
        elif not stripped and current:
            bullets.append(" ".join(current))
            current = []
    if current:
        bullets.append(" ".join(current))
    return bullets


# ---------------------------------------------------------------------------
# Table builder
# ---------------------------------------------------------------------------

def make_data_table(headers, rows, col_widths=None, styles_dict=None):
    # type: (list, list, Optional[list], Optional[dict]) -> Table
    """Create a styled data table matching the academic aesthetic."""
    s = styles_dict

    header_cells = [Paragraph(_escape_xml(h), s['table_header']) for h in headers]

    data_rows = []
    for row in rows:
        cells = []
        for idx, cell in enumerate(row):
            if idx == 0:
                cells.append(Paragraph(_md_inline_to_xml(cell), s['table_cell_bold']))
            else:
                cells.append(Paragraph(_md_inline_to_xml(cell), s['table_cell']))
        data_rows.append(cells)

    table_data = [header_cells] + data_rows

    if col_widths is None:
        n_cols = len(headers)
        if n_cols > 0:
            col_widths = [CONTENT_W / n_cols] * n_cols
        else:
            col_widths = [CONTENT_W]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEAD),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), TEXT_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, NAVY),
        ('LINEBELOW', (0, -1), (-1, -1), 1, NAVY),
        ('LINEBELOW', (0, 1), (-1, -2), 0.5, RULE_COLOR),
    ]

    for idx in range(1, len(table_data)):
        if idx % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, idx), (-1, idx), TABLE_ALT))

    t.setStyle(TableStyle(style_cmds))
    return t


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------

def _render_markdown_content(md_text, styles):
    # type: (str, dict) -> list
    """Render generic markdown content as a list of ReportLab flowables.

    Handles: headings (##, ###), bullet lists, tables, blockquotes,
    and plain paragraphs. Used for appendix content.
    """
    flowables = []
    lines = md_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            i += 1
            continue

        # Skip horizontal rules
        if stripped in ("---", "***", "___"):
            flowables.append(ThinRule(CONTENT_W))
            flowables.append(Spacer(1, 6))
            i += 1
            continue

        # Headings (check deeper levels first to avoid prefix matching)
        if stripped.startswith("#### "):
            # Strip all leading # and whitespace for ####+ headings
            heading_text = stripped.lstrip("#").strip()
            flowables.append(Paragraph(_md_inline_to_xml(heading_text), styles['h3']))
            flowables.append(Spacer(1, 4))
            i += 1
            continue
        if stripped.startswith("### "):
            flowables.append(Paragraph(_md_inline_to_xml(stripped[4:]), styles['h3']))
            flowables.append(Spacer(1, 4))
            i += 1
            continue
        if stripped.startswith("## "):
            flowables.append(Paragraph(_md_inline_to_xml(stripped[3:]), styles['h2']))
            flowables.append(Spacer(1, 4))
            i += 1
            continue
        if stripped.startswith("# "):
            # Skip the top-level title (already rendered as appendix header)
            i += 1
            continue

        # Tables — collect contiguous lines starting with |
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            headers, rows = _parse_table(table_lines)
            if headers and rows:
                n_cols = len(headers)
                col_widths = [CONTENT_W / n_cols] * n_cols
                table = make_data_table(headers, rows, col_widths=col_widths, styles_dict=styles)
                flowables.append(table)
                flowables.append(Spacer(1, 8))
            continue

        # Bullet lists — collect contiguous bullet lines (with sub-bullet support)
        # Note: "* " is a bullet, but "**" (bold) is NOT a bullet
        if stripped.startswith("- ") or (stripped.startswith("* ") and not stripped.startswith("**")):
            bullet_items = []  # list of (indent_level, text)
            while i < len(lines):
                raw = lines[i]
                s = raw.strip()
                # Detect indentation level for sub-bullets
                leading_spaces = len(raw) - len(raw.lstrip())
                is_bullet = s.startswith("- ") or (s.startswith("* ") and not s.startswith("**"))
                if is_bullet:
                    indent_level = 1 if leading_spaces >= 2 else 0
                    bullet_items.append((indent_level, s[2:]))
                    i += 1
                elif s and bullet_items and not s.startswith("#") and not s.startswith("|"):
                    # Continuation line
                    prev_level, prev_text = bullet_items[-1]
                    bullet_items[-1] = (prev_level, prev_text + " " + s)
                    i += 1
                else:
                    break
            for level, bl in bullet_items:
                if level >= 1:
                    flowables.append(Paragraph(
                        "<bullet>&#8211;</bullet> " + _md_inline_to_xml(bl),
                        styles['sub_bullet'],
                    ))
                else:
                    flowables.append(Paragraph(
                        "<bullet>&bull;</bullet> " + _md_inline_to_xml(bl),
                        styles['bullet'],
                    ))
            flowables.append(Spacer(1, 4))
            continue

        # Numbered lists: 1. text, 2. text, etc.
        num_match = re.match(r'^(\d+)\.[\s]+', stripped)
        if num_match:
            numbered_items = []  # list of (indent_level, number, text)
            while i < len(lines):
                raw = lines[i]
                s = raw.strip()
                nm = re.match(r'^(\d+)\.[\s]+', s)
                leading_spaces = len(raw) - len(raw.lstrip())
                if nm:
                    indent_level = 1 if leading_spaces >= 2 else 0
                    numbered_items.append((indent_level, nm.group(1), s[nm.end():]))
                    i += 1
                elif s and numbered_items and not s.startswith("#") and not s.startswith("|"):
                    # Continuation line
                    prev_level, prev_num, prev_text = numbered_items[-1]
                    numbered_items[-1] = (prev_level, prev_num, prev_text + " " + s)
                    i += 1
                else:
                    break
            for level, num, text in numbered_items:
                style = styles['sub_bullet'] if level >= 1 else styles['bullet']
                flowables.append(Paragraph(
                    "<bullet>%s.</bullet> " % _escape_xml(num) + _md_inline_to_xml(text),
                    style,
                ))
            flowables.append(Spacer(1, 4))
            continue

        # Blockquotes
        if stripped.startswith(">"):
            bq_parts = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                bq_parts.append(lines[i].strip().lstrip("> ").strip())
                i += 1
            flowables.append(Paragraph(
                _md_inline_to_xml(" ".join(bq_parts)),
                styles['quote'],
            ))
            flowables.append(Spacer(1, 4))
            continue

        # Plain paragraph — collect lines until blank or structural element
        # Note: lines starting with ** (bold) or * followed by non-space (italic)
        # are inline formatting, NOT bullets or structural elements
        para_parts = []
        while i < len(lines):
            s = lines[i].strip()
            if not s or s.startswith("#") or s.startswith("|") or s.startswith(">"):
                break
            # "- " is a bullet, but "-word" is not
            if s.startswith("- ") or s.startswith("---"):
                break
            # "* " is a bullet (but NOT "**bold**" or "*italic*")
            if s.startswith("* ") and not s.startswith("**"):
                break
            # Numbered lists: "1. text", "2. text", etc.
            if re.match(r'^\d+\.\s+', s):
                break
            para_parts.append(s)
            i += 1
        if para_parts:
            flowables.append(Paragraph(
                _md_inline_to_xml(" ".join(para_parts)),
                styles['body'],
            ))

    return flowables


def _render_glossary_tables(md_text, styles):
    # type: (str, dict) -> list
    """Render glossary markdown as tables (Term/Definition).

    Handles:
    - ### subsection headings (Domain Terms, Tribunal Terms)
    - Markdown table format (| Term | Definition |)
    - Bullet-list fallback (- **Term**: Definition) for backward compatibility
    """
    flowables = []
    lines = md_text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped:
            i += 1
            continue

        # Subsection headings (### Domain Terms, ### Tribunal Terms)
        if stripped.startswith("### "):
            title = stripped[4:].strip()
            flowables.append(Spacer(1, 8))
            flowables.append(Paragraph(_escape_xml(title), styles['h2']))
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # Markdown table block
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            headers, rows = _parse_table(table_lines)
            if headers and rows:
                col_widths = [CONTENT_W * 0.30, CONTENT_W * 0.70]
                table = make_data_table(headers, rows, col_widths=col_widths,
                                        styles_dict=styles)
                flowables.append(table)
                flowables.append(Spacer(1, 8))
            continue

        # Bullet-list fallback: - **Term**: Definition
        if stripped.startswith("- **"):
            bullet_rows = []
            while i < len(lines) and lines[i].strip().startswith("- **"):
                bline = lines[i].strip()[2:]  # strip "- "
                # Parse **Term**: Definition or **Term** — Definition
                m = re.match(r'\*\*(.+?)\*\*[:\s—–-]+\s*(.*)', bline)
                if m:
                    bullet_rows.append([m.group(1).strip(), m.group(2).strip()])
                else:
                    bullet_rows.append([bline.strip("* "), ""])
                i += 1
            if bullet_rows:
                col_widths = [CONTENT_W * 0.30, CONTENT_W * 0.70]
                table = make_data_table(["Term", "Definition"], bullet_rows,
                                        col_widths=col_widths, styles_dict=styles)
                flowables.append(table)
                flowables.append(Spacer(1, 8))
            continue

        # Skip any other lines (instructions, etc.)
        i += 1

    return flowables


def _build_story(parsed, styles, appendices=None):
    # type: (dict, dict, Optional[list]) -> list
    """Convert parsed session summary into a ReportLab story (list of flowables).

    Args:
        parsed: Output of parse_session_summary().
        styles: Output of build_styles().
        appendices: Optional list of (title, md_text) tuples to append.
    """
    story = []
    meta = parsed["header_meta"]

    # ========================================================================
    # COVER PAGE
    # ========================================================================
    story.append(Spacer(1, 1.8 * inch))
    story.append(ThickRule(CONTENT_W, NAVY, 3))
    story.append(Spacer(1, 12))

    # Title
    story.append(Paragraph(
        "Tribunal Session Summary",
        styles['title'],
    ))

    # Session metadata subtitle
    session_id = meta.get("session", "")
    depth = meta.get("depth", "")
    if session_id:
        story.append(Paragraph(
            _escape_xml("Session: %s" % session_id),
            ParagraphStyle('SessionID', parent=styles['subtitle'], fontSize=10,
                           leading=14, textColor=DARK_BLUE),
        ))
    if depth:
        story.append(Paragraph(
            _escape_xml("Depth: %s" % depth),
            styles['subtitle'],
        ))

    story.append(Spacer(1, 8))
    story.append(ThinRule(CONTENT_W * 0.4, ACCENT, 1.5))
    story.append(Spacer(1, 14))

    # Build meta line from parsed header
    meta_parts = []
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
    if meta_parts:
        story.append(Paragraph(
            _escape_xml(" | ".join(meta_parts)),
            styles['subtitle'],
        ))

    # Anonymization note on cover page
    if meta.get("anonymization_note"):
        story.append(Spacer(1, 8))
        anon_style = ParagraphStyle(
            'AnonNote', fontName='Helvetica-Oblique', fontSize=8,
            leading=11, textColor=MUTED, alignment=TA_LEFT,
        )
        story.append(Paragraph(
            _escape_xml(meta["anonymization_note"]),
            anon_style,
        ))

    story.append(Spacer(1, 30))
    story.append(ThickRule(CONTENT_W, NAVY, 1.5))
    story.append(Spacer(1, 20))

    # Question preview on cover
    if parsed["the_prompt"]:
        story.append(CalloutBox(
            "<b>THE PROMPT:</b> " + _md_inline_to_xml(parsed["the_prompt"]),
            CONTENT_W, styles['callout'], LIGHT_GRAY, ACCENT,
        ))
        story.append(Spacer(1, 30))

    # ========================================================================
    # HOW THE TRIBUNAL WORKS (front-matter — between cover and contents)
    # ========================================================================
    if parsed.get("how_tribunal_works"):
        story.append(PageBreak())
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("How The Tribunal Works", styles['h1']))
        story.append(AccentBar(color=MED_BLUE))
        story.append(Spacer(1, 10))

        htw_text = parsed["how_tribunal_works"]
        for para in htw_text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            story.append(Paragraph(
                _md_inline_to_xml(para.replace("\n", " ")),
                styles['body'],
            ))

    # ========================================================================
    # CONTENTS PAGE (separate page after cover / How The Tribunal Works)
    # ========================================================================
    story.append(PageBreak())

    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph("Contents", styles['h1']))
    story.append(AccentBar())
    story.append(Spacer(1, 14))

    toc_style = ParagraphStyle(
        'MiniTOC', fontName='Helvetica', fontSize=10, leading=20,
        textColor=DARK_GRAY, leftIndent=4,
    )

    toc_items = [
        "1. The Prompt",
        "2. Bottom Line",
    ]
    if parsed.get("majority_opinion"):
        toc_items.append("%d. Opinion of the Court" % (len(toc_items) + 1))
    toc_items.append("%d. How We Got Here" % (len(toc_items) + 1))
    if parsed.get("next_steps"):
        toc_items.append("%d. Next Steps" % (len(toc_items) + 1))
    if parsed.get("dissenting_opinions"):
        toc_items.append("%d. Dissenting Opinions" % (len(toc_items) + 1))
    if parsed.get("build_this"):
        toc_items.append("%d. Build This" % (len(toc_items) + 1))
    # Inline appendices from the markdown itself (e.g., Appendix A: The Arguments)
    all_appendices = list(parsed.get("inline_appendices", []))
    if appendices:
        all_appendices.extend(appendices)
    for idx, (title, _) in enumerate(all_appendices):
        letter_label = chr(ord("A") + idx)
        toc_items.append("Appendix %s. %s" % (letter_label, title))
    if parsed.get("glossary"):
        glossary_letter = chr(ord("A") + len(all_appendices))
        toc_items.append("Appendix %s. Glossary" % glossary_letter)
    for item in toc_items:
        story.append(Paragraph(_escape_xml(item), toc_style))

    story.append(NextPageTemplate('Normal'))
    story.append(PageBreak())

    # ========================================================================
    # Anonymization note before content
    # ========================================================================
    if meta.get("anonymization_note"):
        anon_body_style = ParagraphStyle(
            'AnonNoteBody', fontName='Helvetica-Oblique', fontSize=7.5,
            leading=10, textColor=MUTED,
        )
        story.append(Paragraph(
            _escape_xml(meta["anonymization_note"]),
            anon_body_style,
        ))
        story.append(Spacer(1, 4))
        story.append(ThinRule(CONTENT_W, RULE_COLOR, 0.5))
        story.append(Spacer(1, 10))

    # ========================================================================
    # SECTION: THE QUESTION
    # ========================================================================
    story.append(Paragraph("The Prompt", styles['h1']))
    story.append(AccentBar())
    story.append(Spacer(1, 8))

    if parsed["the_prompt"]:
        story.append(Paragraph(
            _md_inline_to_xml(parsed["the_prompt"]),
            styles['body'],
        ))
    story.append(Spacer(1, 12))

    # ========================================================================
    # SECTION: RECOMMENDED OUTCOME
    # ========================================================================
    story.append(Paragraph("Bottom Line", styles['h1']))
    story.append(AccentBar())
    story.append(Spacer(1, 8))

    if parsed["recommended_outcome"]:
        story.extend(_render_markdown_content(parsed["recommended_outcome"], styles))
    story.append(Spacer(1, 12))

    # ========================================================================
    # SECTION: MAJORITY OPINION (optional — between Recommended Outcome and How We Got Here)
    # ========================================================================
    if parsed.get("majority_opinion"):
        story.append(Paragraph("Opinion of the Court (Majority Opinion)", styles['h1']))
        story.append(AccentBar(color=ACCENT))
        story.append(Spacer(1, 8))

        maj_text = parsed["majority_opinion"]
        story.extend(_render_markdown_content(maj_text, styles))
        story.append(Spacer(1, 12))

    # ========================================================================
    # SECTION: HOW WE GOT HERE
    # ========================================================================
    story.append(Paragraph("How We Got Here", styles['h1']))
    story.append(AccentBar())
    story.append(Spacer(1, 8))

    # Sub-section: Scorecard (formerly Council Performance)
    perf = parsed["council_performance"]

    # New subsection format: list of dicts (legacy per-advocate cards)
    if isinstance(perf, list) and perf and isinstance(perf[0], dict):
        story.append(Paragraph("Scorecard", styles['h2']))
        story.append(Spacer(1, 6))

        for adv in perf:
            rank_str = adv.get("rank", "")
            model_name = adv.get("model", "Unknown")
            if rank_str and rank_str != "-":
                heading = "%s — Rank #%s" % (model_name, rank_str)
            elif rank_str == "-":
                heading = "%s — Withdrawn" % model_name
            else:
                heading = model_name
            story.append(Paragraph(_md_inline_to_xml(heading), styles['h3']))
            story.append(Spacer(1, 3))

            if adv.get("opening"):
                story.append(Paragraph(
                    "<b>Opening Position:</b> " + _md_inline_to_xml(adv["opening"]),
                    styles['body'],
                ))
            if adv.get("final"):
                story.append(Paragraph(
                    "<b>Final Position:</b> " + _md_inline_to_xml(adv["final"]),
                    styles['body'],
                ))
            if adv.get("catalyst"):
                story.append(Paragraph(
                    "<b>Key Catalyst:</b> " + _md_inline_to_xml(adv["catalyst"]),
                    styles['body'],
                ))
            story.append(Spacer(1, 8))
            story.append(ThinRule(CONTENT_W * 0.3, RULE_COLOR, 0.5))
            story.append(Spacer(1, 6))

    # Table format: tuple of (headers, rows) — new Scorecard matrix or legacy
    elif isinstance(perf, tuple):
        headers, rows = perf
        if headers and rows:
            story.append(Paragraph("Scorecard", styles['h2']))
            story.append(Spacer(1, 4))

            n_cols = len(headers)
            col_widths = [CONTENT_W / n_cols] * n_cols

            table = make_data_table(headers, rows, col_widths=col_widths, styles_dict=styles)
            story.append(table)
            story.append(Spacer(1, 12))

    # Sub-section: Convergence Assessment (new)
    if parsed.get("convergence_assessment"):
        story.append(Paragraph("Convergence Assessment", styles['h2']))
        story.append(Spacer(1, 4))
        story.extend(_render_markdown_content(parsed["convergence_assessment"], styles))
        story.append(Spacer(1, 12))

    # Sub-section: Key Moments
    if parsed["key_moments"]:
        story.append(Paragraph("Key Moments", styles['h2']))
        story.append(Spacer(1, 4))
        for moment in parsed["key_moments"]:
            story.append(Paragraph(
                "<bullet>&bull;</bullet> " + _md_inline_to_xml(moment),
                styles['bullet'],
            ))
        story.append(Spacer(1, 12))

    # ========================================================================
    # SECTION: NEXT STEPS (optional — new section)
    # ========================================================================
    if parsed.get("next_steps"):
        story.append(Paragraph("Next Steps", styles['h1']))
        story.append(AccentBar())
        story.append(Spacer(1, 8))
        story.extend(_render_markdown_content(parsed["next_steps"], styles))
        story.append(Spacer(1, 12))

    # ========================================================================
    # SECTION: DISSENTING OPINIONS (optional)
    # ========================================================================
    if parsed.get("dissenting_opinions"):
        story.append(PageBreak())
        story.append(Paragraph("Dissenting Opinions", styles['h1']))
        story.append(AccentBar(color=ACCENT2))
        story.append(Spacer(1, 8))

        # Render dissent content with full markdown support (headings, bullets, etc.)
        dissent = parsed["dissenting_opinions"]
        story.extend(_render_markdown_content(dissent, styles))
        story.append(Spacer(1, 12))

    # ========================================================================
    # SECTION: BUILD THIS (optional)
    # ========================================================================
    if parsed.get("build_this"):
        story.append(PageBreak())
        story.append(Paragraph("Build This", styles['h1']))
        story.append(AccentBar())
        story.append(Spacer(1, 8))

        build_text = parsed["build_this"]

        # Handle the blockquote intro line
        bq_lines = []
        body_lines = []
        in_blockquote = True
        for line in build_text.split("\n"):
            stripped = line.strip()
            if in_blockquote and stripped.startswith(">"):
                bq_lines.append(stripped.lstrip("> ").strip())
            elif in_blockquote and stripped == "":
                if bq_lines:
                    in_blockquote = False
            else:
                in_blockquote = False
                body_lines.append(line)

        if bq_lines:
            bq_text = " ".join(bq_lines)
            story.append(CalloutBox(
                _md_inline_to_xml(bq_text),
                CONTENT_W, styles['callout'], LIGHT_GRAY, ACCENT,
            ))
            story.append(Spacer(1, 10))

        # Render the build spec as monospace-ish text for paste-ready feel
        body_text = "\n".join(body_lines).strip()
        if body_text:
            for para in body_text.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                # Check if it's a bullet list
                para_lines = para.split("\n")
                if all(l.strip().startswith("- ") or l.strip().startswith("* ") or l.strip() == "" for l in para_lines if l.strip()):
                    for bl in _parse_bullets(para):
                        story.append(Paragraph(
                            "<bullet>&bull;</bullet> " + _md_inline_to_xml(bl),
                            styles['bullet'],
                        ))
                else:
                    story.append(Paragraph(
                        _md_inline_to_xml(para.replace("\n", " ")),
                        styles['build_this'],
                    ))

    # ========================================================================
    # APPENDICES (inline from markdown + auto-discovered from files)
    # ========================================================================
    all_appendices = list(parsed.get("inline_appendices", []))
    if appendices:
        all_appendices.extend(appendices)
    if all_appendices:
        for idx, (title, md_text) in enumerate(all_appendices):
            letter_label = chr(ord("A") + idx)
            story.append(PageBreak())
            story.append(Paragraph(
                "Appendix %s: %s" % (letter_label, _escape_xml(title)),
                styles['h1'],
            ))
            story.append(AccentBar(color=MED_BLUE))
            story.append(Spacer(1, 8))
            story.extend(_render_markdown_content(md_text, styles))

    # ========================================================================
    # GLOSSARY (absolute last — page break, table layout, appendix lettered)
    # ========================================================================
    if parsed.get("glossary"):
        glossary_letter = chr(ord("A") + len(all_appendices))
        story.append(PageBreak())
        story.append(Paragraph(
            "Appendix %s: Glossary" % glossary_letter,
            styles['h1'],
        ))
        story.append(AccentBar(color=MED_BLUE))
        story.append(Spacer(1, 10))

        story.extend(_render_glossary_tables(parsed["glossary"], styles))

    return story


def _keep_headings_with_content(story):
    # type: (list) -> list
    """Post-process flowables to keep headings with their following content.

    Wraps each heading (Paragraph with h1/h2/h3 style) together with the next
    1-2 flowables in a KeepTogether block, preventing orphaned headings at
    the bottom of a page.
    """
    heading_style_names = {'H1', 'H2', 'H3'}
    result = []
    i = 0
    while i < len(story):
        item = story[i]
        # Check if this is a heading paragraph
        is_heading = (
            isinstance(item, Paragraph) and
            hasattr(item, 'style') and
            item.style.name in heading_style_names
        )
        if is_heading:
            # Gather the heading + accent bar/spacer + first content element
            group = [item]
            j = i + 1
            # Collect up to 3 following non-PageBreak elements to keep together
            while j < len(story) and len(group) < 4:
                nxt = story[j]
                if isinstance(nxt, PageBreak):
                    break
                # Don't include Tables in KeepTogether — they can be very
                # large (e.g. glossary) and would push the heading to the
                # next page, leaving the previous page blank.
                if isinstance(nxt, Table):
                    break
                group.append(nxt)
                j += 1
                # Stop after we've got the heading + decorations + first real content
                if isinstance(nxt, (Paragraph, CalloutBox)):
                    break
            result.append(KeepTogether(group))
            i = j
        else:
            result.append(item)
            i += 1
    return result


def generate_summary_pdf(md_path, output_path=None):
    # type: (str, Optional[str]) -> str
    """Generate a styled PDF from a session-summary.md file.

    Automatically discovers and includes appendices from the same directory:
    - Appendix A: Play-by-Play (play-by-play.md)

    Args:
        md_path: Path to session-summary.md.
        output_path: Where to write the PDF. Defaults to same directory
            as the .md file, named session-summary.pdf.

    Returns:
        The absolute path to the generated PDF.
    """
    md_path = str(md_path)
    md_text = Path(md_path).read_text(encoding="utf-8")
    parsed = parse_session_summary(md_text)

    if output_path is None:
        output_path = str(Path(md_path).with_suffix(".pdf"))

    # Auto-discovered appendices from session directory (currently none)
    appendices = []

    meta = parsed["header_meta"]

    doc = TribunalDocTemplate(
        output_path,
        session_meta={"session_id": meta.get("session", "")},
        pagesize=letter,
        title="Tribunal Session Summary",
        author="The Tribunal",
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
    )

    styles = build_styles()
    story = _build_story(parsed, styles, appendices=appendices)
    story = _keep_headings_with_content(story)

    doc.build(story)
    return os.path.abspath(output_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    # type: () -> None
    if len(sys.argv) < 2:
        print("Usage: python summary_pdf.py <session-summary.md> [output.pdf]")
        sys.exit(1)

    md_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(md_path):
        print("Error: file not found: %s" % md_path)
        sys.exit(1)

    pdf_path = generate_summary_pdf(md_path, output_path)
    print("PDF generated: %s" % pdf_path)


if __name__ == "__main__":
    main()
