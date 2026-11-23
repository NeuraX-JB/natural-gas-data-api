"""Run with python -m unittest discover -s api -p test_api.py from the lab directory."""
import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from build_api import DATASETS, build, join_weekly, parse_date, parse_timestamp, publish_snapshot, read_csv, write_json

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


class InputBoundaryTests(unittest.TestCase):
    def parse_storage(self, content):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "storage.csv"
            path.write_text(content, encoding="utf-8")
            return read_csv(path, DATASETS["storage"]["columns"], "week_ending")

    def test_rejects_duplicate_headers_and_ragged_rows(self):
        header = "week_ending,working_gas_bcf,change_bcf\n"
        cases = [
            "week_ending,working_gas_bcf,change_bcf,change_bcf\n2024-01-05,100,,0\n",
            header + "2024-01-05,100\n",
            header + "2024-01-05,100,,unclaimed\n",
        ]
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.parse_storage(content)

    def test_rejects_ambiguous_dates_and_invalid_utc_timestamps(self):
        for value in ["20240105", "2024-W01-5", "2024-02-30", " 2024-01-05"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_date(value)
        for value in ["yesterday", "2024-01-05T12:00:00", "2024-01-05T12:00:00+02:00", "2024-02-30T00:00:00Z"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_timestamp(value)
        self.assertEqual(parse_date("2024-02-29"), "2024-02-29")

    def test_rejects_negative_inventory_inconsistent_change_and_gap_change(self):
        header = "week_ending,working_gas_bcf,change_bcf\n"
        cases = ["2024-01-05,-100,\n", "2024-01-05,100,\n2024-01-12,90,10\n", "2024-01-05,100,\n2024-01-19,90,-10\n"]
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.parse_storage(header + content)
        rows = self.parse_storage(header + "2024-01-05,100,\n2024-01-12,100,0\n2024-01-26,90,\n")
        self.assertEqual([row["change_bcf"] for row in rows], [None, 0, None])


class PublicationTests(unittest.TestCase):
    def snapshot_outputs(self):
        return {path.relative_to(V1).as_posix(): json.loads(path.read_text(encoding="utf-8")) for path in V1.rglob("*.json")}

    def test_incomplete_staging_leaves_published_snapshot_intact(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v1"
            shutil.copytree(V1, target)
            original = {p.relative_to(target): p.read_bytes() for p in target.rglob("*.json")}
            writes = 0
            def interrupted(path, data):
                nonlocal writes
                writes += 1
                if writes == 2:
                    raise OSError("simulated disk failure")
                write_json(path, data)
            with patch("build_api.write_json", side_effect=interrupted), self.assertRaises(OSError):
                publish_snapshot(target, {"index.json": {"edition": "new"}, "years/2021.json": [2]})
            self.assertEqual({p.relative_to(target): p.read_bytes() for p in target.rglob("*.json")}, original)

    def test_promotion_failure_restores_previous_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v1"
            shutil.copytree(V1, target)
            original = (target / "index.json").read_bytes()
            outputs = self.snapshot_outputs()
            outputs["index.json"]["release_note"] = "Simulated new edition"
            replace = Path.replace
            def interrupted(path, destination):
                if "-stage-" in path.name and destination == target:
                    raise OSError("simulated promotion failure")
                return replace(path, destination)
            with patch.object(Path, "replace", interrupted), self.assertRaises(OSError):
                publish_snapshot(target, outputs)
            self.assertEqual((target / "index.json").read_bytes(), original)

    def test_rebuild_removes_stale_partitions_and_preserves_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v1"
            build(ROOT.parent / "data", target)
            obsolete = {**load("weekly.json")[0], "week_ending": "1900-01-05", "period_start": "1899-12-29", "period_end": "1900-01-04"}
            write_json(target / "years/1900.json", [obsolete])
            build(ROOT.parent / "data", target)
            self.assertFalse((target / "years/1900.json").exists())
            for path in V1.rglob("*.json"):
                if path.name != "index.json":
                    self.assertEqual(path.read_bytes(), (target / path.relative_to(V1)).read_bytes())

    def test_unrelated_target_and_unrecognized_catalog_survive_unchanged(self):
        for case in ("sibling-app", "unexpected-file", "wrong-catalog", "unexpected-year-file"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "destination"
                if case == "sibling-app":
                    target.mkdir()
                    (target / "index.html").write_text("Existing user application", encoding="utf-8")
                    write_json(target / "settings.json", {"keep": True})
                else:
                    shutil.copytree(V1, target)
                    if case == "unexpected-file":
                        (target / "notes.txt").write_text("Unrelated user work", encoding="utf-8")
                    elif case == "wrong-catalog":
                        write_json(target / "index.json", {"version": "v1", "datasets": {"other-app": {}}})
                    else:
                        write_json(target / "years/1900.json", [{"not_api_data": True}])
                original = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
                with self.assertRaisesRegex(ValueError, "unmanaged API target"):
                    build(ROOT.parent / "data", target)
                self.assertEqual({p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}, original)
                self.assertEqual(list(Path(temp).iterdir()), [target])

    def test_concurrent_builder_lock_is_respected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v1"
            (Path(temp) / ".v1.build-lock").mkdir()
            with self.assertRaises(RuntimeError):
                publish_snapshot(target, {"index.json": {}})
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
