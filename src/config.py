"""Pixel layout and paths for the Fitts' Law study."""

from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PARTICIPANT_DIR = DATA_DIR / "participants"
TEST_DIR = DATA_DIR / "test"

# Design sizes in pixels at scale 1.0 (fits exactly 1920 px wide).
# Smaller screens draw every A, W, and the center circle multiplied by one
# scale factor, so A/W and therefore ID stay identical for every participant.
DISTANCES = (150, 380, 620, 884)
DIAMETERS = (24, 48, 84, 120)
DIRECTIONS = ("left", "right")
TRIAL_COUNT = 10
TARGETS_PER_TRIAL = len(DISTANCES) * len(DIAMETERS) * len(DIRECTIONS)
CENTER_DIAMETER = 80
EDGE_MARGIN = 16

BACKGROUND = (18, 18, 18)
CENTER_COLOR = (255, 255, 255)
TARGET_COLOR = (255, 193, 7)
TEXT_COLOR = (255, 255, 255)
MUTED_TEXT = (190, 190, 190)
BUTTON_COLOR = (255, 193, 7)
BUTTON_TEXT = (18, 18, 18)
FIELD_COLOR = (40, 40, 40)
FIELD_BORDER = (255, 255, 255)

MODE_PARTICIPANT = "participant"
MODE_TEST = "test"


def paths_for(mode):
    """Database, Excel, and plot folder for participant or test runs."""
    root = PARTICIPANT_DIR if mode == MODE_PARTICIPANT else TEST_DIR
    return {
        "root": root,
        "db": root / "fitts_results.sqlite",
        "xlsx": root / "fitts_results.xlsx",
        "plots": root / "plots",
    }


def mode_label(mode):
    return "Participant" if mode == MODE_PARTICIPANT else "Test"


def index_of_difficulty(distance, diameter):
    """Shannon formulation: log2(A / W + 1). W is the diameter."""
    return math.log2(distance / diameter + 1)


def all_targets():
    """The 32 distinct tasks. Distances and diameters are fixed pixels."""
    return [
        (direction, distance, diameter)
        for direction in DIRECTIONS
        for distance in DISTANCES
        for diameter in DIAMETERS
    ]


def required_half_width():
    return max(DISTANCES) + max(DIAMETERS) / 2 + EDGE_MARGIN


def required_half_height():
    return max(DIAMETERS) / 2 + EDGE_MARGIN


UI_DESIGN_SIZE = (1920, 1080)
UI_SCALE_LIMITS = (0.5, 2.0)


def ui_scale(width, height):
    """Size factor for menu and survey text, buttons, and spacing (not the task)."""
    factor = min(width / UI_DESIGN_SIZE[0], height / UI_DESIGN_SIZE[1])
    low, high = UI_SCALE_LIMITS
    return max(low, min(high, factor))


def layout_scale(width, height):
    """One factor applied to every distance and diameter; never above 1.0."""
    return min(
        1.0,
        width / (2 * required_half_width()),
        height / (2 * required_half_height()),
    )
