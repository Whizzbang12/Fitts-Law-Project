"""SQLite log with one table per participant or test session."""

import re
import sqlite3

import config

CREATE_SESSION = """
CREATE TABLE IF NOT EXISTS {table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_number INTEGER NOT NULL,
    target_number INTEGER NOT NULL,
    direction TEXT NOT NULL,
    distance_px REAL NOT NULL,
    diameter_px REAL NOT NULL,
    id_bits REAL NOT NULL,
    mt_ms REAL NOT NULL,
    path_length_px REAL NOT NULL,
    hit INTEGER NOT NULL,
    error_distance_px REAL NOT NULL
)
"""

CREATE_DEMOGRAPHICS = """
CREATE TABLE IF NOT EXISTS demographics (
    participant INTEGER PRIMARY KEY,
    gender TEXT,
    age TEXT,
    handedness TEXT,
    computer_hours TEXT,
    disabilities TEXT
)
"""

TABLE_RE = re.compile(r"^(participant|test)_(\d+)$")


class Database:
    def __init__(self, path, mode):
        self.path = path
        self.mode = mode
        self.prefix = "participant" if mode == config.MODE_PARTICIPANT else "test"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        if mode == config.MODE_PARTICIPANT:
            self.conn.execute(CREATE_DEMOGRAPHICS)
            self._ensure_demographics_columns()
            self.conn.commit()
        self.purge_empty_sessions()

    def _ensure_demographics_columns(self):
        cursor = self.conn.execute("PRAGMA table_info(demographics)")
        existing = {row[1] for row in cursor}
        if "computer_hours" not in existing:
            self.conn.execute("ALTER TABLE demographics ADD COLUMN computer_hours TEXT")

    def close(self):
        self.conn.close()

    def table_name(self, session_number):
        return f"{self.prefix}_{int(session_number)}"

    def ensure_session(self, session_number):
        table = self.table_name(session_number)
        self.conn.execute(CREATE_SESSION.format(table=table))
        self.conn.commit()
        return table

    def delete_session(self, session_number):
        """Remove a reserved session so its number can be reused."""
        table = self.table_name(session_number)
        self.conn.execute(f"DROP TABLE IF EXISTS {table}")
        if self.mode == config.MODE_PARTICIPANT:
            self.conn.execute(
                "DELETE FROM demographics WHERE participant = ?",
                (int(session_number),),
            )
        self.conn.commit()

    def insert_target(self, session_number, row):
        table = self.ensure_session(session_number)
        self.conn.execute(
            f"""
            INSERT INTO {table} (
                trial_number, target_number, direction,
                distance_px, diameter_px, id_bits, mt_ms,
                path_length_px, hit, error_distance_px
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["trial_number"],
                row["target_number"],
                row["direction"],
                row["distance_px"],
                row["diameter_px"],
                row["id_bits"],
                row["mt_ms"],
                row["path_length_px"],
                row["hit"],
                row["error_distance_px"],
            ),
        )
        self.conn.commit()

    def save_demographics(self, session_number, answers):
        self.conn.execute(
            """
            INSERT OR REPLACE INTO demographics (
                participant, gender, age, handedness, computer_hours, disabilities
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(session_number),
                answers.get("gender"),
                str(answers.get("age") or "").strip(),
                answers.get("handedness"),
                str(answers.get("computer_hours") or "").strip(),
                answers.get("disabilities"),
            ),
        )
        self.conn.commit()

    def has_demographics(self, session_number):
        if self.mode != config.MODE_PARTICIPANT:
            return False
        cursor = self.conn.execute(
            "SELECT 1 FROM demographics WHERE participant = ?",
            (int(session_number),),
        )
        return cursor.fetchone() is not None

    def completed_conditions(self, session_number, trial_number):
        table = self.ensure_session(session_number)
        cursor = self.conn.execute(
            f"""
            SELECT direction, distance_px, diameter_px
            FROM {table}
            WHERE trial_number = ?
            """,
            (trial_number,),
        )
        return {
            (row["direction"], row["distance_px"], row["diameter_px"])
            for row in cursor
        }

    def _table_exists(self, table):
        cursor = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        )
        return cursor.fetchone() is not None

    def target_count(self, session_number, trial_number=None):
        table = self.table_name(session_number)
        if not self._table_exists(table):
            return 0
        if trial_number is None:
            cursor = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}")
        else:
            cursor = self.conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE trial_number = ?",
                (trial_number,),
            )
        return cursor.fetchone()["n"]

    def next_trial_number(self, session_number):
        """First trial that is not finished, or None when all 10 are done."""
        for trial_number in range(1, config.TRIAL_COUNT + 1):
            if self.target_count(session_number, trial_number) < config.TARGETS_PER_TRIAL:
                return trial_number
        return None

    def _demographics_numbers(self):
        if self.mode != config.MODE_PARTICIPANT:
            return []
        cursor = self.conn.execute("SELECT participant FROM demographics")
        return [int(row["participant"]) for row in cursor]

    def _trial_table_numbers(self):
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        numbers = []
        for row in cursor:
            match = TABLE_RE.match(row["name"])
            if match and match.group(1) == self.prefix:
                numbers.append(int(match.group(2)))
        return numbers

    def session_numbers(self):
        """Sessions that have trial rows and/or demographics. Empty tables are ignored."""
        numbers = []
        for number in self._trial_table_numbers():
            if self.target_count(number) > 0:
                numbers.append(number)
        numbers.extend(self._demographics_numbers())
        return sorted(set(numbers))

    def purge_empty_sessions(self):
        """Drop trial tables with no rows when they also have no demographics."""
        for number in self._trial_table_numbers():
            if self.target_count(number) == 0 and not self.has_demographics(number):
                self.delete_session(number)

    def next_session_number(self):
        numbers = self.session_numbers()
        return 1 if not numbers else max(numbers) + 1

    def latest_unfinished(self):
        unfinished = []
        for number in self.session_numbers():
            if self.next_trial_number(number) is not None:
                unfinished.append(number)
        return max(unfinished) if unfinished else None

    def session_active_time_ms(self, session_number):
        """Sum of movement times only. Menus and Next waits are not included."""
        table = self.table_name(session_number)
        if not self._table_exists(table):
            return 0.0
        cursor = self.conn.execute(f"SELECT COALESCE(SUM(mt_ms), 0) AS total FROM {table}")
        return float(cursor.fetchone()["total"])

    def fetch_trials(self):
        rows = []
        for number in self.session_numbers():
            table = self.table_name(number)
            if not self._table_exists(table):
                continue
            cursor = self.conn.execute(
                f"""
                SELECT trial_number, target_number, direction,
                       distance_px, diameter_px, id_bits, mt_ms,
                       path_length_px, hit, error_distance_px
                FROM {table}
                ORDER BY id
                """
            )
            for row in cursor:
                item = dict(row)
                item["participant"] = str(number)
                rows.append(item)
        return rows

    def session_totals(self):
        """Active pointing time in ms for each session that has trial data."""
        totals = {}
        for number in self.session_numbers():
            total = self.session_active_time_ms(number)
            if total > 0 or self.target_count(number) > 0:
                totals[number] = total
        return totals
