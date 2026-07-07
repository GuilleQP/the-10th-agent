"""Minimal dependency-free SVG line charts for conversion-over-epochs.

Kept hand-rolled (no matplotlib / JS lib) so charts can be baked straight into
the static ``docs/index.html`` and standalone local files, matching the rest of
the viewer's "everything is inlined at agg time" approach.
"""

from __future__ import annotations

from dataclasses import dataclass

# Categorical palette (GitHub-ish), distinguishable up to ~10 series.
PALETTE = [
    "#2da44e", "#0969da", "#cf222e", "#bf3989", "#9a6700",
    "#1b7c83", "#8250df", "#bc4c00", "#57606a", "#d4a72c",
]


def color_for(i: int) -> str:
    return PALETTE[i % len(PALETTE)]


@dataclass
class Series:
    label: str
    color: str
    # One value in [0, 1] per x position (aligned to x_labels). ``None`` leaves
    # a gap (e.g. an N that a sweep skipped); may be shorter than x_labels.
    points: list[float | None]


def line_chart_svg(
    series: list[Series],
    x_labels: list[str],
    *,
    width: int = 720,
    height: int = 360,
    y_label: str = "Majority holding truth",
    x_title: str = "Epoch",
) -> str:
    """Render a multi-line chart (y = 0–100%) as an inline ``<svg>``.

    x positions are categorical and evenly spaced, so powers-of-two labels
    (1, 2, 4, 8, 16) read as a log axis for free.
    """
    ml, mr, mt, mb = 52, 18, 16, 40
    pw = width - ml - mr
    ph = height - mt - mb
    n = max(len(x_labels), 1)

    def x_at(i: int) -> float:
        # Evenly spaced categorical x; single point sits at the left edge.
        return ml + (pw * i / (n - 1) if n > 1 else 0)

    def y_at(v: float) -> float:
        return mt + ph * (1 - v)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'role="img" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" '
        f'style="max-width:{width}px">'
    ]

    # Horizontal gridlines + y tick labels at 0/25/50/75/100%.
    for pct in (0, 25, 50, 75, 100):
        y = y_at(pct / 100)
        parts.append(
            f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" '
            f'stroke="#eaeef2" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ml - 8}" y="{y + 3:.1f}" text-anchor="end" '
            f'font-size="11" fill="#8c959f">{pct}%</text>'
        )

    # X axis tick labels (epochs).
    for i, lbl in enumerate(x_labels):
        parts.append(
            f'<text x="{x_at(i):.1f}" y="{mt + ph + 18}" text-anchor="middle" '
            f'font-size="11" fill="#656d76">{lbl}</text>'
        )
    parts.append(
        f'<text x="{ml + pw / 2:.1f}" y="{height - 4}" text-anchor="middle" '
        f'font-size="11" fill="#656d76">{x_title}</text>'
    )
    # Y axis title (rotated).
    parts.append(
        f'<text transform="translate(13,{mt + ph / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle" font-size="11" fill="#656d76">{y_label}</text>'
    )

    # One polyline (+ dots) per series; split into segments across None gaps.
    for s in series:
        if not s.points:
            continue
        segment: list[str] = []
        for i, v in enumerate(s.points):
            if v is None:
                if len(segment) > 1:
                    parts.append(
                        f'<polyline fill="none" stroke="{s.color}" stroke-width="2" '
                        f'stroke-linejoin="round" stroke-linecap="round" '
                        f'points="{" ".join(segment)}"/>'
                    )
                segment = []
                continue
            segment.append(f"{x_at(i):.1f},{y_at(v):.1f}")
        if len(segment) > 1:
            parts.append(
                f'<polyline fill="none" stroke="{s.color}" stroke-width="2" '
                f'stroke-linejoin="round" stroke-linecap="round" '
                f'points="{" ".join(segment)}"/>'
            )
        for i, v in enumerate(s.points):
            if v is None:
                continue
            xlbl = x_labels[i] if i < len(x_labels) else i + 1
            parts.append(
                f'<circle cx="{x_at(i):.1f}" cy="{y_at(v):.1f}" r="2.5" '
                f'fill="{s.color}"><title>{s.label} · {xlbl}: {v:.0%}</title></circle>'
            )

    parts.append("</svg>")
    return "".join(parts)


def legend_html(series: list[Series]) -> str:
    """Color-chip legend matching the viewer's pill style."""
    chips = "".join(
        '<span class="inline-flex items-center mr-3 mb-2 text-xs text-[#1f2328]">'
        f'<span class="inline-block w-3 h-3 rounded-sm mr-1.5" style="background:{s.color}"></span>'
        f"{s.label}</span>"
        for s in series
    )
    return f'<div class="flex flex-wrap">{chips}</div>'
