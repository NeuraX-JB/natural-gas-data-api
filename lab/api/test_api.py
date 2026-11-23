"""Run with python -m unittest discover -s api -p test_api.py from the lab directory."""
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from build_api import join_weekly

ROOT = Path(__file__).resolve().parent
V1 = ROOT / "v1"


def load(filename):
    return json.loads((V1 / filename).read_text(encoding="utf-8"))


class JoinTests(unittest.TestCase):
    def test_inclusive_period_and_missing_values(self):
        anchor = "2024-01-05"
        storage = [{"week_ending": anchor, "working_gas_bcf": 100, "change_bcf": None},
                   {"week_ending": "2024-01-19", "working_gas_bcf": 100, "change_bcf": 0}]
        weather = [{"week_ending": anchor, "hdd": 4, "cdd": 0}]
        spot = [{"date": "2023-12-29", "usd_per_mmbtu": 7},  # Friday of prior week
                {"date": "2024-01-04", "usd_per_mmbtu": 3},  # Thursday
                {"date": anchor, "usd_per_mmbtu": 11}]       # reference Friday is outside window
        first, missing = join_weekly(storage, weather, spot)
        self.assertEqual((first["period_start"], first["period_end"]), ("2023-12-29", "2024-01-04"))
        self.assertEqual((first["spot_days"], first["spot_avg_usd_mmbtu"]), (2, 5.0))
        self.assertEqual(first["cdd"], 0)
        self.assertIsNone(first["change_bcf"])
        self.assertEqual(missing["change_bcf"], 0)
        self.assertEqual((missing["spot_days"], missing["spot_avg_usd_mmbtu"]), (0, None))
        self.assertIsNone(missing["hdd"])

    def test_partitions_and_latest(self):
        data = load("weekly.json")
        catalog = load("index.json")["datasets"]["weekly"]
        years = [row for year in catalog["years"] for row in load(f"years/{year}.json")]
        self.assertEqual(years, data)
        self.assertEqual(load("latest.json"), data[-1])
        self.assertEqual(load("recent.json"), data[-52:])

    def test_catalog_and_source_manifest(self):
        cat = load("index.json")
        manifest = json.loads((ROOT.parent / "data" / "manifest.json").read_text())
        for key, meta in cat["datasets"].items():
            series = load(meta["path"])
            days = [row[meta["key"]] for row in series]
            self.assertEqual(days, sorted(set(days)))
            self.assertEqual((meta["rows"], meta["first_date"], meta["last_date"]), (len(days), days[0], days[-1]))
            self.assertEqual(set(meta["columns"]), set(series[0]))
            if key == "weekly":
                continue
            source = manifest["sources"][key]
            self.assertEqual((len(days), days[0], days[-1]), (source["row_count"], source["min_date"], source["max_date"]))
            self.assertEqual(cat["sources"][key]["updated_at_utc"], source["downloaded_at_utc"])
            self.assertEqual(cat["sources"][key]["source_url"], source["source_url"])
            self.assertEqual(cat["sources"][key]["units"], source["units"])

    def test_weekly_values_reconcile_to_underlying_endpoints(self):
        joined = load("weekly.json")
        storage = load("storage.json")
        self.assertEqual(len(joined), len(storage))
        weather = {row["week_ending"]: row for row in load("weather.json")}
        spot = {date.fromisoformat(row["date"]): row["usd_per_mmbtu"] for row in load("spot.json")}
        for row, inventory in zip(joined, storage):
            for field, value in inventory.items():
                self.assertEqual(row[field], value)
            anchor = date.fromisoformat(row["week_ending"])
            self.assertEqual(row["period_start"], (anchor - timedelta(days=7)).isoformat())
            self.assertEqual(row["period_end"], (anchor - timedelta(days=1)).isoformat())
            matches = weather.get(row["week_ending"], {})
            for field in ("hdd", "cdd"):
                self.assertEqual(row[field], matches.get(field))
            quotes = [spot[d] for d in (anchor - timedelta(days=n) for n in range(1, 8)) if d in spot]
            self.assertEqual(row["spot_days"], len(quotes))
            if quotes:
                self.assertAlmostEqual(row["spot_avg_usd_mmbtu"], sum(quotes) / len(quotes), delta=0.000051)
            else:
                self.assertIsNone(row["spot_avg_usd_mmbtu"])


if __name__ == "__main__":
    unittest.main()
