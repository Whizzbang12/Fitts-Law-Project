"""Download the online study into the local SQLite files and rebuild Excel.

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from .env in fitts_program.
The service role key stays on this computer. Do not commit .env.

    python src/pull_results.py

Sessions marked excluded in Supabase are stored, then left out of the workbook.
Their numbers are not reused.
"""

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from analysis import build_results
from database import Database


def load_env(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fetch_all(base_url, service_key, table):
    rows = []
    start = 0
    page_size = 1000
    while True:
        request = urllib.request.Request(
            f"{base_url}/rest/v1/{table}?select=*&order=id.asc" if table == "trials"
            else f"{base_url}/rest/v1/{table}?select=*",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Range": f"{start}-{start + page_size - 1}",
            },
        )
        with urllib.request.urlopen(request) as response:
            batch = json.load(response)
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        start += page_size


def rebuild(mode, sessions, trials, demographics):
    paths = config.paths_for(mode)
    if paths["db"].exists():
        paths["db"].unlink()
    database = Database(paths["db"], mode)
    database.conn.execute(
        "CREATE TABLE IF NOT EXISTS excluded_sessions (session INTEGER PRIMARY KEY)"
    )
    for session in sessions:
        number = int(session["session_number"])
        if session.get("excluded"):
            database.conn.execute(
                "INSERT OR REPLACE INTO excluded_sessions (session) VALUES (?)",
                (number,),
            )
        info = {
            "os_name": session.get("os_name"),
            "os_release": session.get("os_release"),
            "os_version": session.get("os_version"),
            "machine": session.get("machine"),
            "screen_width": session.get("screen_width"),
            "screen_height": session.get("screen_height"),
            "scale": session.get("scale"),
        }
        if any(value is not None for value in info.values()):
            database.save_session_info(number, info)
        for row in trials:
            if int(row["session_number"]) != number:
                continue
            database.insert_target(number, {
                "trial_number": row["trial_number"],
                "target_number": row["target_number"],
                "direction": row["direction"],
                "distance_px": row["distance_px"],
                "diameter_px": row["diameter_px"],
                "id_bits": row["id_bits"],
                "mt_ms": row["mt_ms"],
                "path_length_px": row["path_length_px"],
                "hit": row["hit"],
                "error_distance_px": row["error_distance_px"],
                "scale": row["scale"],
                "path_length_raw_px": row.get("path_length_raw_px"),
                "error_distance_raw_px": row.get("error_distance_raw_px"),
            })
    if mode == config.MODE_PARTICIPANT:
        for row in demographics:
            database.save_demographics(int(row["session_number"]), row)
    database.conn.commit()
    database.close()
    return build_results(mode)


def main():
    env = load_env(ROOT / ".env")
    base_url = env.get("SUPABASE_URL", "").rstrip("/")
    service_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base_url or not service_key or "YOUR_" in service_key:
        print("Copy .env.example to .env and set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    sessions = fetch_all(base_url, service_key, "sessions")
    trials = fetch_all(base_url, service_key, "trials")
    demographics = fetch_all(base_url, service_key, "demographics")
    for mode in (config.MODE_PARTICIPANT, config.MODE_TEST):
        mode_sessions = [row for row in sessions if row["mode"] == mode]
        mode_trials = [row for row in trials if row["mode"] == mode]
        workbook = rebuild(mode, mode_sessions, mode_trials, demographics)
        print(workbook)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
