"""Targeted checks for dates, gaps and snapshot integrity. Run from this directory."""
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import unittest

from refresh import storage_rows, weather_rows


class DataContractTests(unittest.TestCase):
    def test_stock_change_never_crosses_a_gap(self):
        observations = {date(2026, 1, 2): 3000.0, date(2026, 1, 9): 2950.0, date(2026, 1, 23): 2900.0}
        self.assertEqual([row[2] for row in storage_rows(observations)], [None, -50, None])

    def test_weather_uses_previous_friday_through_thursday(self):
        first = date(2026, 1, 2)
        heating = {first + timedelta(days=i): i for i in range(15)}
        cooling = dict.fromkeys(heating, 1)
        rows, missing = weather_rows(heating, cooling, date(2026, 1, 20))
        self.assertEqual(rows[0], ["2026-01-09", 21, 7, "2026-01-02", "2026-01-08"])
        self.assertEqual(rows[1], ["2026-01-16", 70, 7, "2026-01-09", "2026-01-15"])
        self.assertEqual(missing, [])
        del cooling[date(2026, 1, 8)]
        rows, missing = weather_rows(heating, cooling, date(2026, 1, 20))
        self.assertEqual(missing, ["2026-01-09"])
        self.assertEqual(len(rows), 1)

    def test_packaged_csv_files_match_manifest(self):
        root = Path(__file__).resolve().parent
        manifest = json.loads((root / "manifest.json").read_text())
        for name, source in manifest["sources"].items():
            path = root / source["file"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source["sha256"])
            with path.open(newline="") as f:
                rows = list(csv.reader(f))[1:]
            labels = [r[0] for r in rows]
            self.assertEqual(len(rows), source["row_count"], name)
            self.assertEqual(labels, sorted(set(labels)), name)
            self.assertEqual(labels[0], source["min_date"])
            self.assertEqual(labels[-1], source["max_date"])


if __name__ == "__main__":
    unittest.main()
