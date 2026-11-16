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
    """One row per A/W pair.

    Mean MT gives each completed session equal weight: first average that
    session's hits, then average those session means. Incomplete sessions
    are already filtered out before this function runs.
    """
    selected = rows if direction is None else [row for row in rows if row["direction"] == direction]
    grouped = defaultdict(lambda: defaultdict(list))
    for row in selected:
        key = (int(row["distance_px"]), int(row["diameter_px"]))
        grouped[key][row["participant"]].append(row)

    summary = []
    for distance, diameter in _pairs():
        by_session = grouped.get((distance, diameter), {})
        session_means = []
        n_trials = 0
        n_hits = 0
        error_values = []
        path_means = []
        for session_rows in by_session.values():
            n_trials += len(session_rows)
            hits = [row for row in session_rows if row["hit"]]
            n_hits += len(hits)
            error_values.extend(row["error_distance_px"] for row in session_rows)
            if hits:
                session_means.append(sum(row["mt_ms"] for row in hits) / len(hits))
                path_means.append(sum(row["path_length_px"] for row in hits) / len(hits))
        summary.append(
            {
                "distance_px": distance,
                "diameter_px": diameter,
                "id_bits": config.index_of_difficulty(distance, diameter),
                "n_trials": n_trials,
                "n_hits": n_hits,
                "mean_mt_ms": (sum(session_means) / len(session_means)) if session_means else None,
                "mean_error_px": (sum(error_values) / len(error_values)) if error_values else None,
                "mean_path_px": (sum(path_means) / len(path_means)) if path_means else None,
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


def _write_sheet(workbook, title, summary, fit, sessions, excluded, mode, avg_active_ms):
    sheet = workbook.create_sheet(title)
    label = config.mode_label(mode)
    has_r = fit is not None and not np.isnan(fit["r"])
    labels_values = (
        (
            f"{label}s included (completed all {config.TRIAL_COUNT} trials)",
            ", ".join(sessions) if sessions else "None yet",
        ),
        (
            f"Incomplete {label.lower()}s excluded",
            ", ".join(excluded) if excluded else "None",
        ),
        (
            "Fit",
            "Not enough hit data to fit a line"
            if fit is None
            else f"MT = {fit['intercept']:.1f} + {fit['slope']:.1f} ID",
        ),
        ("Correlation r", round(fit["r"], 4) if has_r else None),
        ("R²", round(fit["r"] ** 2, 4) if has_r else None),
        (
            f"Avg active time across completed {label.lower()}s (ms)",
            None if avg_active_ms is None else round(avg_active_ms, 1),
        ),
    )
    for row_number, (text, value) in enumerate(labels_values, start=1):
        sheet.cell(row_number, 1, text).font = LABEL_FONT
        sheet.cell(row_number, 2, value)

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
    header_row = len(labels_values) + 2
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
    widths = [48, 18, 14, 12, 12, 18, 26, 24]
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
    if np.isnan(fit["r"]):
        stats = "r = n/a, R² = n/a"
    else:
        stats = f"r = {fit['r']:.3f}, R² = {fit['r'] ** 2:.3f}"
    plt.title(f"{title}\nMT = {fit['intercept']:.1f} + {fit['slope']:.1f} ID, {stats}")
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
        completed = database.completed_sessions()
        incomplete = database.incomplete_sessions()
        removed = database.excluded_session_numbers()
        rows = database.fetch_trials(completed)
        session_totals = database.session_totals(completed)
    finally:
        database.close()

    sessions = [str(number) for number in completed]
    removed_ids = set(removed)
    excluded = [str(number) for number in incomplete if number not in removed_ids]
    excluded += [f"{number} removed" for number in removed]
    avg_active_ms = _avg_active_time_ms(session_totals)
    workbook = Workbook()
    default = workbook.active
    workbook.remove(default)

    for sheet_name, direction, title in SHEETS:
        summary = _summarize(rows, direction)
        fit = _fit(summary)
        sheet = _write_sheet(
            workbook, sheet_name, summary, fit, sessions, excluded, mode, avg_active_ms
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
                sheet.add_image(chart, "J8")

    paths["xlsx"].parent.mkdir(parents=True, exist_ok=True)
    try:
        workbook.save(paths["xlsx"])
    except PermissionError:
        print(f"Close {paths['xlsx'].name} in Excel, then run: python main.py --analyze")
        raise
    return paths["xlsx"]
