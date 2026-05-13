"""Zennify-branded PPTX renderer for the Quarterly Strategic Digest.

Per spec §11 / ARCHITECTURE Batch 7.

Layout:

    1. Title slide          — Zennify wordmark, period, subvertical
    2. Executive overview   — summary paragraph + KPI strip
    3. Per-priority slides  — one per priority with state badge, narrative,
                              recommendation, top SOW excerpt, top benchmark
    4. Watchlist slide      — RISING/EMERGING subcaps to watch next quarter

The render keeps everything self-contained (no Drive image fetches) so it
runs hermetically. Brand colours are pulled from the spec §14 palette
verified through the Tailwind tokens already used in the frontend.
"""

from __future__ import annotations

import io
import logging

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

logger = logging.getLogger(__name__)

# Zennify brand palette — exact mirror of frontend/tailwind.config.ts.
# These 8 tokens are locked per spec §14; the icon teal (#27BBAF) is the
# brand-defining accent used for state badges + buttons.
ZEN_DARK_GREEN = RGBColor(0x1C, 0x4A, 0x4D)
ZEN_DARK_TEAL = RGBColor(0x18, 0x5F, 0x60)
ZEN_TEAL = RGBColor(0x27, 0xBB, 0xAF)        # icon teal — brand accent
ZEN_LIGHT_TEAL = RGBColor(0x62, 0xD7, 0xB8)
ZEN_LIGHT_GREEN = RGBColor(0xB0, 0xEE, 0xD3)
ZEN_LIGHT_ORANGE = RGBColor(0xFF, 0xCB, 0x99)
ZEN_ORANGE = RGBColor(0xFE, 0x97, 0x32)
ZEN_WHITE_GREEN = RGBColor(0xE8, 0xF7, 0xF6)

STATE_COLOR = {
    "RISING": ZEN_TEAL,
    "STABLE": ZEN_LIGHT_GREEN,
    "EMERGING": ZEN_LIGHT_ORANGE,
    "DECLINING": ZEN_LIGHT_ORANGE,
    "FADING": ZEN_ORANGE,
    "DEAD": ZEN_DARK_TEAL,
}


def render(digest: dict) -> bytes:
    """Return PPTX bytes for the given digest dict."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9 widescreen
    prs.slide_height = Inches(7.5)

    _add_title_slide(prs, digest)
    _add_summary_slide(prs, digest)
    for priority in digest.get("priorities", []):
        _add_priority_slide(prs, digest, priority)
    _add_watchlist_slide(prs, digest)

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


# ─── Slide builders ─────────────────────────────────────────────────────────


def _blank_slide(prs: Presentation):
    blank_layout = prs.slide_layouts[6]  # blank layout in the default theme
    return prs.slides.add_slide(blank_layout)


def _add_title_slide(prs: Presentation, digest: dict) -> None:
    slide = _blank_slide(prs)
    _set_background(slide, ZEN_DARK_GREEN)

    # Optional logo asset — drop a PNG / SVG into static/brand/ and the
    # title slide picks it up automatically. Falls back to wordmark only.
    _add_logo_if_present(slide)

    # Brand wordmark — uses the light-teal token for the wordmark + the
    # icon teal (#27BBAF) is reserved for the actual logo glyph.
    _add_text(
        slide, "ZENNIFY",
        left=0.6, top=0.5, width=4, height=0.6,
        size=20, bold=True, color=ZEN_LIGHT_TEAL,
    )
    _add_text(
        slide, "Capability Intelligence",
        left=0.6, top=1.05, width=8, height=0.5,
        size=11, color=ZEN_LIGHT_GREEN,
    )

    # Headline
    _add_text(
        slide, "Quarterly Strategic Digest",
        left=0.6, top=2.4, width=12, height=1,
        size=44, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF),
    )
    _add_text(
        slide, f"{digest.get('subvertical', '?')} · {digest.get('period', '?')}",
        left=0.6, top=3.6, width=12, height=0.7,
        size=24, color=ZEN_LIGHT_GREEN,
    )

    # Footer
    _add_text(
        slide,
        f"Generated {digest.get('generated_at', '?')[:10]} · model: {digest.get('model', '?')} · "
        f"{digest.get('sources_count', 0)} sources cited",
        left=0.6, top=6.7, width=12, height=0.4,
        size=10, color=ZEN_LIGHT_GREEN,
    )


def _add_summary_slide(prs: Presentation, digest: dict) -> None:
    slide = _blank_slide(prs)
    _set_background(slide, ZEN_WHITE_GREEN)

    _add_text(
        slide, "Executive Overview",
        left=0.6, top=0.4, width=12, height=0.6,
        size=28, bold=True, color=ZEN_DARK_GREEN,
    )

    _add_text(
        slide, digest.get("summary", "(no summary)"),
        left=0.6, top=1.4, width=12, height=2.2,
        size=14, color=ZEN_DARK_TEAL,
    )

    # KPI strip
    priorities = digest.get("priorities", [])
    rising = sum(1 for p in priorities if p.get("state") == "RISING")
    stable = sum(1 for p in priorities if p.get("state") == "STABLE")
    emerging = sum(1 for p in priorities if p.get("state") == "EMERGING")
    cost = digest.get("total_cost_usd", 0.0)
    kpis = [
        ("Priorities", str(len(priorities))),
        ("Rising", str(rising)),
        ("Stable", str(stable)),
        ("Emerging", str(emerging)),
        ("Sources", str(digest.get("sources_count", 0))),
        ("LLM cost", f"${cost:.2f}"),
    ]
    cell_w = 11.5 / len(kpis)
    for i, (label, value) in enumerate(kpis):
        left = 0.6 + i * cell_w
        _add_text(
            slide, value,
            left=left, top=4.5, width=cell_w, height=0.8,
            size=24, bold=True, color=ZEN_TEAL, align=PP_ALIGN.CENTER,
        )
        _add_text(
            slide, label,
            left=left, top=5.4, width=cell_w, height=0.4,
            size=10, color=ZEN_DARK_TEAL, align=PP_ALIGN.CENTER,
        )


def _add_priority_slide(prs: Presentation, digest: dict, priority: dict) -> None:
    slide = _blank_slide(prs)
    _set_background(slide, RGBColor(0xFF, 0xFF, 0xFF))

    state = (priority.get("state") or "EMERGING").upper()
    state_fill = STATE_COLOR.get(state, ZEN_TEAL)

    _add_text(
        slide, priority.get("sub_cap_id", "?"),
        left=0.6, top=0.4, width=3, height=0.4,
        size=11, bold=True, color=ZEN_DARK_TEAL,
    )

    _add_state_badge(slide, state, state_fill, left=4, top=0.42)

    _add_text(
        slide, priority.get("sub_cap_name", "(unnamed)"),
        left=0.6, top=0.95, width=12, height=0.7,
        size=24, bold=True, color=ZEN_DARK_GREEN,
    )

    score_txt = f"score {priority.get('score', 0):.0f}"
    confidence_txt = f"confidence {(priority.get('confidence') or 0) * 100:.0f}%"
    delta = priority.get("delta") or {}
    delta_txt = ""
    if delta.get("previous_state"):
        delta_txt = (
            f"  ·  {delta['previous_state']} → {state} "
            f"vs {delta.get('previous_period', '?')}"
        )
    _add_text(
        slide, f"{score_txt}  ·  {confidence_txt}{delta_txt}",
        left=0.6, top=1.7, width=12, height=0.4,
        size=11, color=ZEN_DARK_TEAL,
    )

    # Narrative
    _add_text(
        slide, "Narrative",
        left=0.6, top=2.2, width=6, height=0.4,
        size=12, bold=True, color=ZEN_DARK_GREEN,
    )
    _add_text(
        slide, priority.get("narrative", ""),
        left=0.6, top=2.6, width=6, height=2.2,
        size=11, color=ZEN_DARK_TEAL,
    )

    _add_text(
        slide, "Recommendation",
        left=0.6, top=4.9, width=6, height=0.4,
        size=12, bold=True, color=ZEN_DARK_GREEN,
    )
    _add_text(
        slide, priority.get("recommendation", ""),
        left=0.6, top=5.3, width=6, height=1.5,
        size=11, color=ZEN_DARK_TEAL,
    )

    # Evidence column (right)
    _add_text(
        slide, "Evidence",
        left=7.0, top=2.2, width=6, height=0.4,
        size=12, bold=True, color=ZEN_DARK_GREEN,
    )
    y = 2.6
    for s in priority.get("evidence_sows", [])[:2]:
        _add_text(
            slide,
            f"• SOW {s.get('client', '?')} ({s.get('status', '?')}): "
            f"{(s.get('excerpt') or '')[:140]}",
            left=7.0, top=y, width=6, height=0.6,
            size=10, color=ZEN_DARK_TEAL,
        )
        y += 0.7
    for b in priority.get("evidence_benchmarks", [])[:2]:
        _add_text(
            slide,
            f"• Benchmark {b.get('metric_id', '?')} / {b.get('cohort_id', '?')} "
            f"p50={b.get('p50')} (verdict {b.get('verdict')})",
            left=7.0, top=y, width=6, height=0.6,
            size=10, color=ZEN_DARK_TEAL,
        )
        y += 0.7
    for n in priority.get("evidence_news", [])[:1]:
        _add_text(
            slide,
            f"• News [{n.get('source', '?')}] {(n.get('title') or '')[:140]}",
            left=7.0, top=y, width=6, height=0.6,
            size=10, color=ZEN_DARK_TEAL,
        )
        y += 0.7


def _add_watchlist_slide(prs: Presentation, digest: dict) -> None:
    slide = _blank_slide(prs)
    _set_background(slide, ZEN_DARK_GREEN)

    _add_text(
        slide, "Watchlist for next quarter",
        left=0.6, top=0.4, width=12, height=0.6,
        size=28, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF),
    )

    rising = [
        p for p in digest.get("priorities", [])
        if p.get("state") in ("RISING", "EMERGING")
    ]
    if not rising:
        _add_text(
            slide,
            "No RISING / EMERGING subcaps; watchlist is empty.  "
            "Re-run the lifecycle engine after the next ingest cycle.",
            left=0.6, top=1.5, width=12, height=1,
            size=14, color=ZEN_LIGHT_GREEN,
        )
        return

    y = 1.4
    for p in rising[:8]:
        _add_text(
            slide,
            f"·  {p.get('sub_cap_id', '?')}  —  {p.get('sub_cap_name', '?')}  "
            f"(score {p.get('score', 0):.0f}, {p.get('state', '?')})",
            left=0.6, top=y, width=12, height=0.5,
            size=14, color=ZEN_LIGHT_GREEN,
        )
        y += 0.55


# ─── Helpers ────────────────────────────────────────────────────────────────


def _add_text(
    slide,
    text: str,
    *,
    left: float, top: float, width: float, height: float,
    size: int, bold: bool = False,
    color: RGBColor = ZEN_DARK_TEAL,
    align=PP_ALIGN.LEFT,
) -> None:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Arial"


def _add_state_badge(slide, state: str, fill: RGBColor, *, left: float, top: float) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left), Inches(top), Inches(1.2), Inches(0.35),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    tf = shape.text_frame
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = state
    run.font.size = Pt(10)
    run.font.bold = True
    run.font.color.rgb = (
        ZEN_DARK_GREEN if state in ("STABLE", "EMERGING") else RGBColor(0xFF, 0xFF, 0xFF)
    )
    run.font.name = "Arial"


def _set_background(slide, color: RGBColor) -> None:
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_logo_if_present(slide) -> None:
    """Place the Zennify icon teal logo top-right when a static asset exists."""
    from pathlib import Path

    # Search both the runtime static path (Docker image) and the in-repo
    # brand/ folder (dev / mounted via volume).
    backend_dir = Path(__file__).resolve().parents[2]
    repo_brand = backend_dir.parent / "brand"
    candidates = [
        backend_dir / "static" / "brand" / "logo.png",
        backend_dir / "static" / "brand" / "logo.svg",
        repo_brand / "logo.png",
        repo_brand / "logo.svg",
    ]
    for path in candidates:
        if path.exists():
            try:
                slide.shapes.add_picture(
                    str(path),
                    Inches(11.6), Inches(0.4),
                    height=Inches(0.7),
                )
            except Exception:  # noqa: BLE001
                logger.warning("could not embed brand logo from %s", path)
            return
