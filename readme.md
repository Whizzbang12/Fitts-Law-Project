# Fitts' Law Pointing Study

Fullscreen Python app for a Fitts' Law target-acquisition experiment. Participants complete consent and a short survey, then 10 trials of 32 pointing tasks. Test runs skip consent/survey and store data separately.

## Features

- **Participant** or **Test** mode (separate folders and databases)
- Auto-numbered sessions (`participant_N` / `test_N` SQLite tables)
- Consent, demographics survey, and task instructions (participant mode only)
- Design amplitudes and widths with uniform scale-to-fit (same ID on every screen)
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
- Excel regressions use **completed sessions only** (all 10 trials). Incomplete sessions are listed as excluded. Each completed session gets equal weight when averaging MT per ID. Sheets report the fit, Pearson’s *r*, and **R²**.

## Task parameters

- Distances A (px): 150, 380, 620, 884  
- Diameters W (px): 24, 48, 84, 120  
- Directions: left, right  
- ID: log₂(A/W + 1)  
- 10 trials × 32 targets  

### Screen size and scaling

The design layout fits exactly 1920 px wide. On smaller screens every distance, every diameter, and the center circle are multiplied by the same scale factor (`scale = min(1, screen_width / 1920, ...)`). Because A and W shrink together, A/W and ID are identical on every screen, so all participants share the same ID bins in one regression.

Path length and miss distance are stored both in design units (drawn pixels ÷ scale) and as raw drawn pixels. Each trial row stores its `scale`, and the `session_info` table records OS, machine, screen size, and scale for each session. Menu/survey UI also scales with screen size (factor between 0.5 and 2.0).

## Website

The `web` folder is the same study in the browser. GitHub Pages can host that folder. Results are stored in Supabase, not in this repository.

1. In Supabase, run `supabase/schema.sql` in the SQL editor.
2. Put the project URL and anon key in `web/supabase-config.js`.
3. Copy `.env.example` to `.env` and put the service role key there. `.env` is not committed.
4. Publish the `web` folder with GitHub Pages.
5. On this computer, download results and rebuild Excel:

```bash
python src/pull_results.py
```

To leave an unreliable participant out of Excel without changing later numbers, set `excluded` on that session in the Supabase `sessions` table, then run the download again. The rows stay in the database.

## License / course use

Built for CIS 582 coursework. Adapt as needed for your study protocol.
