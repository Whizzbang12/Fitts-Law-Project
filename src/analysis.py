"""Hit-only movement-time regressions, written to Excel and saved as plots."""

from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, PatternFill, Alignment

import config
from database import Database

SHEETS = (
    ("Regression_All", None, "All directions"),
    ("Regression_Left", "left", "Left only"),
    ("Regression_Right", "right", "Right only"),
)

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True, name="Calibri")
LABEL_FONT = Font(bold=True, name="Calibri")


def _pairs():
    return [(distance, diameter) for distance in config.DISTANCES for diameter in config.DIAMETERS]


def _summarize(rows, direction):
    """One row per distance-diameter pair. Mean MT uses hits only."""
    selected = rows if direction is None else [row for row in rows if row["direction"] == direction]
    grouped = defaultdict(list)
    for row in selected:
        key = (int(row["distance_px"]), int(row["diameter_px"]))
        grouped[key].append(row)

    summary = []
    for distance, diameter in _pairs():
        group = grouped.get((distance, diameter), [])
        hits = [row for row in group if row["hit"]]
        n_trials = len(group)
        n_hits = len(hits)
        summary.append(
            {
                "distance_px": distance,
                "diameter_px": diameter,
                "id_bits": config.index_of_difficulty(distance, diameter),
                "n_trials": n_trials,
                "n_hits": n_hits,
                "mean_mt_ms": (sum(row["mt_ms"] for row in hits) / n_hits) if n_hits else None,
                "mean_error_px": (sum(row["error_distance_px"] for row in group) / n_trials) if n_trials else None,
                "mean_path_px": (sum(row["path_length_px"] for row in hits) / n_hits) if n_hits else None,
            }
        )
    return summary


def _fit(summary):
    points = [row for row in summary if row["mean_mt_ms"] is not None]
    if len(points) < 2:
        return None
    x = np.array([row["id_bits"] for row in points], dtype=float)
    y = np.array([row["mean_mt_ms"] for row in points], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    if np.std(x) == 0 or np.std(y) == 0:
        correlation = float("nan")
    else:
        correlation = float(np.corrcoef(x, y)[0, 1])
    return {"intercept": float(intercept), "slope": float(slope), "r": correlation, "x": x, "y": y}


def _avg_active_time_ms(session_totals):
    if not session_totals:
        return None
    return sum(session_totals.values()) / len(session_totals)


def _write_sheet(workbook, title, summary, fit, sessions, mode, avg_active_ms):
    sheet = workbook.create_sheet(title)
    label = config.mode_label(mode)
    sheet["A1"] = f"{label}s included"
    sheet["B1"] = ", ".join(sessions) if sessions else "None yet"
    sheet["A1"].font = LABEL_FONT
    if fit is None:
        sheet["A2"] = "Fit"
        sheet["B2"] = "Not enough hit data to fit a line"
    else:
        sheet["A2"] = "Fit"
        sheet["B2"] = f"MT = {fit['intercept']:.1f} + {fit['slope']:.1f} ID"
        sheet["A3"] = "Correlation r"
        sheet["B3"] = None if np.isnan(fit["r"]) else round(fit["r"], 4)
    sheet["A4"] = f"Avg active time across {label.lower()}s (ms)"
    sheet["B4"] = None if avg_active_ms is None else round(avg_active_ms, 1)
    sheet["A2"].font = LABEL_FONT
    sheet["A3"].font = LABEL_FONT
    sheet["A4"].font = LABEL_FONT

    headers = [
        "Distance A (px)",
        "Diameter W (px)",
        "ID (bits)",
        "Targets",
        "Hits",
        "Mean MT (ms)",
        "Mean error distance (px)",
        "Mean path of hits (px)",
    ]
    header_row = 6
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, column, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True)
    for offset, row in enumerate(summary, start=1):
        values = [
            row["distance_px"],
            row["diameter_px"],
            round(row["id_bits"], 4),
            row["n_trials"],
            row["n_hits"],
            None if row["mean_mt_ms"] is None else round(row["mean_mt_ms"], 1),
            None if row["mean_error_px"] is None else round(row["mean_error_px"], 1),
            None if row["mean_path_px"] is None else round(row["mean_path_px"], 1),
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(header_row + offset, column, value)
    widths = [36, 18, 14, 12, 12, 18, 26, 24]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    return sheet


def _save_plot(fit, title, path):
    if fit is None:
        return
    plt.figure(figsize=(8, 5.5))
    plt.scatter(fit["x"], fit["y"], color="#1F4E79", zorder=3)
    x_line = np.linspace(float(fit["x"].min()), float(fit["x"].max()), 50)
    plt.plot(x_line, fit["intercept"] + fit["slope"] * x_line, color="#B71C1C")
    r_text = "n/a" if np.isnan(fit["r"]) else f"{fit['r']:.3f}"
    plt.title(f"{title}\nMT = {fit['intercept']:.1f} + {fit['slope']:.1f} ID, r = {r_text}")
    plt.xlabel("Index of difficulty (bits)")
    plt.ylabel("Movement time (ms)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=140)
    plt.close()


def build_results(mode=config.MODE_PARTICIPANT):
    """Rebuild the three Excel tables and plots for one mode only."""
    paths = config.paths_for(mode)
    database = Database(paths["db"], mode)
    try:
        rows = database.fetch_trials()
        session_totals = database.session_totals()
    finally:
        database.close()

    sessions = sorted({row["participant"] for row in rows}, key=lambda value: int(value) if value.isdigit() else value)
    # Only sessions that actually have pointing data contribute to avg active time.
    avg_active_ms = _avg_active_time_ms(session_totals) if session_totals else None
    workbook = Workbook()
    default = workbook.active
    workbook.remove(default)

    for sheet_name, direction, title in SHEETS:
        summary = _summarize(rows, direction)
        fit = _fit(summary)
        sheet = _write_sheet(
            workbook, sheet_name, summary, fit, sessions, mode, avg_active_ms
        )
        image_path = paths["plots"] / f"{sheet_name.lower()}.png"
        if fit is None:
            if image_path.exists():
                image_path.unlink()
        else:
            _save_plot(fit, title, image_path)
            if image_path.exists():
                chart = XLImage(str(image_path))
                chart.width = 520
                chart.height = 360
                sheet.add_image(chart, "J5")

    paths["xlsx"].parent.mkdir(parents=True, exist_ok=True)
    try:
        workbook.save(paths["xlsx"])
    except PermissionError:
        print(f"Close {paths['xlsx'].name} in Excel, then run: python main.py --analyze")
        raise
    return paths["xlsx"]
