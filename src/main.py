"""Start the Fitts' Law task, or rebuild Excel from one of the databases.

Run the task:
    python main.py

Rebuild the participant spreadsheet:
    python main.py --analyze

Rebuild the test spreadsheet:
    python main.py --analyze-test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    if "--analyze-test" in sys.argv:
        from analysis import build_results
        import config

        print(build_results(config.MODE_TEST))
        return
    if "--analyze" in sys.argv:
        from analysis import build_results
        import config

        print(build_results(config.MODE_PARTICIPANT))
        return
    from experiment import run

    run()


if __name__ == "__main__":
    main()
