"""Render a report (from report_service.build_report) as PDF. Charts use only values in the report."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

DARK = "#064E3B"
ACCENT = "#84CC16"
LIGHT = "#ECFDF5"
MUTED = "#6B7280"
MAX_BAR_CELLS = 30

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], textColor=colors.HexColor(DARK), alignment=TA_LEFT, fontSize=18)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor(DARK), spaceBefore=8)
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=7.5, leading=9.5, textColor=colors.HexColor(MUTED))
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=7, leading=8.5)


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _image(buf: io.BytesIO, width_mm: float = 170) -> Image:
    img = Image(buf)
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width_mm * mm
    img.drawHeight = width_mm * mm * ratio
    return img


def chart_scores(report: dict) -> io.BytesIO | None:
    scored = [c for c in report["cells"] if c["opportunity_score"] is not None]
    if not scored:
        return None
    scored = sorted(scored, key=lambda c: c["opportunity_score"], reverse=True)[:MAX_BAR_CELLS]
    fig, ax = plt.subplots(figsize=(7, 0.28 * len(scored) + 1.2))
    labels = [c["name"] for c in scored][::-1]
    values = [c["opportunity_score"] for c in scored][::-1]
    bar_colors = [ACCENT if c["flagged"] else "#A7C4B5" for c in scored][::-1]
    ax.barh(labels, values, color=bar_colors)
    ax.axvline(report["threshold_score"], color=DARK, linestyle="--", linewidth=1, label="Priority cut-off")
    if report["national"]["median"] is not None:
        ax.axvline(report["national"]["median"], color=MUTED, linestyle=":", linewidth=1, label="Rwanda median")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Market opportunity score (0-100, relative)")
    ax.legend(loc="lower right", fontsize=7, frameon=False)
    ax.tick_params(labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    return _png(fig)


def chart_density_radiance(report: dict) -> io.BytesIO | None:
    pts = [(c["indicators"]["population_density"]["value"], c["indicators"]["nighttime_radiance"]["value"],
            c["opportunity_score"]) for c in report["cells"]]
    pts = [p for p in pts if p[0] is not None and p[1] is not None and p[0] > 0 and p[1] > 0]
    if not pts:
        return None
    fig, ax = plt.subplots(figsize=(7, 3.4))
    scores = [p[2] if p[2] is not None else 0 for p in pts]
    sc = ax.scatter([p[0] for p in pts], [p[1] for p in pts], c=scores, cmap="YlGn", vmin=0, vmax=100,
                    edgecolor=DARK, linewidth=0.5, s=36)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Population density (people/km², log)")
    ax.set_ylabel("Nighttime radiance (nW/cm²/sr, log)")
    fig.colorbar(sc, ax=ax, label="Opportunity score")
    ax.spines[["top", "right"]].set_visible(False)
    return _png(fig)


def chart_districts(report: dict) -> io.BytesIO | None:
    rows = [d for d in report["summary"]["districts"] if d["solar_share_pct"] is not None]
    if not rows:
        return None
    rows = sorted(rows, key=lambda d: d["solar_share_pct"])
    fig, ax = plt.subplots(figsize=(7, 0.32 * len(rows) + 1.1))
    ax.barh([d["district"] for d in rows], [d["solar_share_pct"] for d in rows], color=DARK)
    for i, d in enumerate(rows):
        ax.text(d["solar_share_pct"] + 0.5, i, f"n={int(d['sampled_solar_households'] or 0)}",
                va="center", fontsize=7, color=MUTED)
    ax.set_xlabel("Estimated households owning a solar device (%, district, MTF survey)")
    ax.tick_params(labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    return _png(fig)


def _table(data: list[list], widths: list[float], header_rows: int = 1) -> Table:
    table = Table(data, colWidths=[w * mm for w in widths], repeatRows=header_rows)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor(DARK)),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _fmt(record: dict) -> str:
    return "–" if record["display_value"] is None else record["formatted"]


def report_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=report["title"],
                            author="Solar Market Reality")
    s = report["summary"]
    story = [
        Paragraph(report["title"], H1),
        Paragraph(f"{report['country']} · generated {report['generated_at']} · dataset built "
                  f"{(report['dataset_built_at'] or '')[:10]}", SMALL),
        Spacer(1, 4 * mm),
        _table([
            ["Selected cells", "Area", "Population (est.)", "Density", "Scored cells", "Score range"],
            [s["n_cells"], f"{s['area_km2']:,.0f} km²",
             "–" if s["population_total"] is None else f"{s['population_total']:,}",
             "–" if s["population_density"] is None else f"{s['population_density']:,} /km²",
             s["n_scored"], "–" if s["score_min"] is None else f"{s['score_min']}–{s['score_max']} / 100"],
        ], [24, 24, 30, 28, 24, 30]),
        Spacer(1, 2 * mm),
        Paragraph("Selected places: " + ", ".join(
            f"{c['name']} ({c['district'] or 'outside districts'})" for c in report["cells"][:60])
            + (" ..." if len(report["cells"]) > 60 else ""), SMALL),
        Paragraph("Key findings", H2),
        *[Paragraph(f"• {line}", BODY) for line in report["interpretation"]],
        Paragraph("Market opportunity score", H2),
        Paragraph(f"<b>{report['method']['formula']}</b>. Energy need: {report['method']['energy_need']}. "
                  f"Solar uptake: {report['method']['solar_uptake']}. {report['method']['interpretation']} "
                  f"Priority cut-off used: {report['threshold_score']}/100. "
                  f"Model status: {report['model_status'].get('reason', '')}", BODY),
    ]
    for title, chart, caption in (
        ("Opportunity score by cell", chart_scores(report),
         f"Top {MAX_BAR_CELLS} scored cells shown; green bars are at or above the cut-off. Cells without a score are listed in the table."),
        ("Population density and nighttime radiance", chart_density_radiance(report),
         "Each point is a selected cell. Dark cells can still have high solar ownership; radiance is a grid proxy."),
        ("District solar-device ownership (survey estimate)", chart_districts(report),
         "District-wide MTF survey estimate; n = sampled solar-owning households. Small samples are uncertain."),
    ):
        if chart is not None:
            story.append(KeepTogether([Paragraph(title, H2), _image(chart), Paragraph(caption, SMALL)]))

    story += [PageBreak(), Paragraph("Location indicators", H2)]
    header = ["Place (cell, sector)", "District", "Density /km²", "Radiance", "Grid km", "Grid in cell", "RWI",
              "District solar %", "Need", "Score", "Evidence"]
    rows = [header]
    for c in report["cells"]:
        ind = c["indicators"]
        rows.append([
            Paragraph(c["name"], CELL), c["district"] or "–", _fmt(ind["population_density"]).replace(" people/km²", ""),
            _fmt(ind["nighttime_radiance"]).replace(" nW/cm²/sr", ""),
            _fmt(ind["distance_to_grid_km"]).replace(" km", ""), _fmt(ind["grid_presence"]),
            _fmt(ind["relative_wealth"]).replace(" RWI (0 = national mean)", ""),
            _fmt(ind["survey_solar_share"]), "–" if c["energy_need"] is None else c["energy_need"],
            "–" if c["opportunity_score"] is None else c["opportunity_score"], c["evidence_level"],
        ])
    story.append(_table(rows, [30, 18, 14, 13, 11, 12, 10, 15, 9, 10, 17]))
    story.append(Paragraph("Places are named after the administrative cell containing the centre of each 5 km "
                           "analysis area. Units: density people/km² (WorldPop 2020); radiance nW/cm²/sr (NASA VNP46A2); "
                           "grid distance km to mapped OSM line; RWI relative index (0 = national mean); "
                           "need and score 0-100 relative.", SMALL))

    story.append(Paragraph("Data sources", H2))
    src_rows = [["Source", "Status", "Date", "Licence"]] + [
        [Paragraph(src["name"], CELL), src["status"], src["date"] or "not recorded", src["licence"] or "–"]
        for src in report["sources"]
    ]
    story.append(_table(src_rows, [90, 18, 40, 26]))
    story.append(Paragraph("Limitations", H2))
    story += [Paragraph(f"• {line}", BODY) for line in report["limitations"]]
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("This report supports field investigation. It is not proof of commercial viability "
                           "and should not be used alone to allocate capital.", SMALL))
    doc.build(story)
    return buf.getvalue()
