"""Pixel layout and paths for the Fitts' Law study."""

from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PARTICIPANT_DIR = DATA_DIR / "participants"
TEST_DIR = DATA_DIR / "test"

# Fixed pixel sizes used on every screen. ID is based on these values.
DISTANCES = (150, 380, 620, 888)
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


def screen_can_show_targets(width, height):
    """True when every fixed-size target fits on this screen."""
    return width / 2 >= required_half_width() and height / 2 >= required_half_height()
