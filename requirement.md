# Requirements

## Runtime

- Python 3.10 or newer (developed with Python 3.13)

## Python packages

| Package    | Version used | Purpose                                      |
|------------|--------------|----------------------------------------------|
| pygame     | 2.6.1        | Fullscreen Fitts' Law pointing task          |
| numpy      | 2.5.4        | Regression fit and correlation               |
| matplotlib | 3.11.2       | ID vs MT scatter plots                       |
| openpyxl   | 3.1.5        | Excel workbook with regression tables/charts |

Install:

```bash
pip install pygame==2.6.1 numpy==2.5.4 matplotlib==3.11.2 openpyxl==3.1.5
```

## System notes

- A display large enough for the fixed target layout is required (largest distance 888 px, largest diameter 120 px).
- On Windows, the app uses per-monitor DPI awareness so fullscreen matches the real pixel size of the monitor.
