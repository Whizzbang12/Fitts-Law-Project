# Fitts' Law Pointing Study

Fullscreen Python app for a Fitts' Law target-acquisition experiment. Participants complete consent and a short survey, then 10 trials of 32 pointing tasks. Test runs skip consent/survey and store data separately.

## Features

- **Participant** or **Test** mode (separate folders and databases)
- Auto-numbered sessions (`participant_N` / `test_N` SQLite tables)
- Consent, demographics survey, and task instructions (participant mode only)
- Fixed pixel amplitudes and widths (same ID on every screen)
- Hits, misses, movement time, path length, and error distance logged per target
- Excel regressions (all / left / right) with MT = a + b·ID, correlation *r*, plots, and average active pointing time
- Resume unfinished sessions; empty abandoned sessions are not kept

## Project layout

```
fitts_program/
├── readme.md
├── requirement.md
├── .gitignore
├── src/
│   ├── main.py          # entry point
│   ├── config.py        # distances, diameters, paths, colors
│   ├── experiment.py    # pygame task UI
│   ├── survey.py        # consent, questions, instructions text
│   ├── database.py      # SQLite logging
│   └── analysis.py      # Excel + plots
└── data/                # created at runtime (gitignored)
    ├── participants/
    └── test/
```

## Setup

```bash
cd fitts_program
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install pygame==2.6.1 numpy==2.5.4 matplotlib==3.11.2 openpyxl==3.1.5
```

See [requirement.md](requirement.md) for dependency details.

## Run

From the `src` folder (or with that folder on `PYTHONPATH`):

```bash
cd src
python main.py
```

### Analyze without running the task

```bash
python main.py --analyze        # rebuild participant Excel
python main.py --analyze-test   # rebuild test Excel
```

Close the Excel file before analyzing if it is open, or saving will fail.

## Session flow

1. Choose **Participant** or **Test**.
2. **Participant only:** Consent → survey → Instructions → Begin Trial.
3. Each trial: click the white center circle, then the yellow target (32 tasks).
4. After 10 trials, results are saved and Excel is updated for that mode.

Press **Esc** to exit. During consent or the survey, Esc exits with **no** participant record.

## Data outputs

| Mode        | Folder                 | Database              | Spreadsheet           |
|-------------|------------------------|-----------------------|-----------------------|
| Participant | `data/participants/`   | `fitts_results.sqlite`| `fitts_results.xlsx`  |
| Test        | `data/test/`           | `fitts_results.sqlite`| `fitts_results.xlsx`  |

- Trial rows live in one SQLite table per session.
- Survey answers are in a `demographics` table (participants only; not written to Excel).
- Excel sheets: `Regression_All`, `Regression_Left`, `Regression_Right`.

## Task parameters

- Distances A (px): 150, 380, 620, 888  
- Diameters W (px): 24, 48, 84, 120  
- Directions: left, right  
- ID: log₂(A/W + 1)  
- 10 trials × 32 targets  

## License / course use

Built for CIS 582 coursework. Adapt as needed for your study protocol.
