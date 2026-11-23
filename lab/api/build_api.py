#!/usr/bin/env python3
"""Build versioned JSON endpoints from the lab's validated public-source CSV snapshots."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent / "data"

DATASETS = {
    "weekly": {
        "label": "Joined weekly",
        "key": "week_ending",
        "frequency": "Weekly",
        "columns": ["week_ending", "period_start", "period_end", "working_gas_bcf", "change_bcf",
                    "hdd", "cdd", "spot_avg_usd_mmbtu", "spot_days"],
        "about": "One row per EIA storage Friday. Weather and spot refer to the preceding Friday through Thursday.",
    },
    "storage": {
        "label": "Working gas storage",
        "key": "week_ending",
        "frequency": "Weekly",
        "columns": ["week_ending", "working_gas_bcf", "change_bcf"],
        "about": "Working gas in underground storage for the Lower 48. A positive weekly change is a net stock increase, which can differ from physical flow.",
    },
    "weather": {
        "label": "Heating and cooling",
        "key": "week_ending",
        "frequency": "Weekly",
        "columns": ["week_ending", "period_start", "period_end", "hdd", "cdd"],
        "about": "Contiguous U.S. population-weighted degree days, aggregated from NOAA observations for a seven-day period.",
    },
    "spot": {
        "label": "Henry Hub spot",
        "key": "date",
        "frequency": "Daily observations",
        "columns": ["date", "usd_per_mmbtu"],
        "about": "Reported Henry Hub spot price in U.S. dollars per million British thermal units. Dates with no quote are absent.",
    },
}
FIELD_NOTES = {
    "week_ending": {"label": "Week ending", "unit": "date", "type": "YYYY-MM-DD", "definition": "Friday reference date of the EIA storage series."},
    "period_start": {"label": "Period start", "unit": "date", "type": "YYYY-MM-DD", "definition": "First calendar day in the weather and spot sampling window (the preceding Friday)."},
    "period_end": {"label": "Period end", "unit": "date", "type": "YYYY-MM-DD", "definition": "Last calendar day in the sampling window (Thursday before the storage Friday)."},
    "working_gas_bcf": {"label": "Working gas", "unit": "Bcf", "type": "number", "definition": "Lower 48 working gas inventory, billion cubic feet."},
    "change_bcf": {"label": "Weekly stock change", "unit": "Bcf", "type": "number or null", "definition": "Current working gas inventory less inventory on the prior Friday. Positive is a net stock increase; negative is a decrease. Reclassifications can make this differ from physical injections or withdrawals."},
    "hdd": {"label": "Heating degree days", "unit": "°F-days", "type": "number or null", "definition": "Weekly sum of population-weighted heating degree days from NOAA CPC, 65°F base."},
    "cdd": {"label": "Cooling degree days", "unit": "°F-days", "type": "number or null", "definition": "Weekly sum of population-weighted cooling degree days from NOAA CPC, 65°F base."},
    "spot_avg_usd_mmbtu": {"label": "Mean spot", "unit": "$/MMBtu", "type": "number or null", "definition": "Arithmetic mean of Henry Hub daily spot quotes whose observation dates fall within the seven-day window, rounded to four decimal places. Observation dates are not publication dates."},
    "spot_days": {"label": "Spot quotes", "unit": "days", "type": "integer", "definition": "Count of reported daily spot prices inside the sampling window. Unreported dates receive no weight."},
    "date": {"label": "Quote date", "unit": "date", "type": "YYYY-MM-DD", "definition": "Calendar date of the observed Henry Hub spot quote."},
    "usd_per_mmbtu": {"label": "Henry Hub spot", "unit": "$/MMBtu", "type": "number", "definition": "Henry Hub natural gas spot price in U.S. dollars per million British thermal units."},
}

def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"Expected YYYY-MM-DD date, got {value!r}")
    return date.fromisoformat(value).isoformat()


def parse_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError(f"Expected UTC timestamp YYYY-MM-DDTHH:MM:SSZ, got {value!r}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def parse_number(value, *, optional=False):
    if value is None or not str(value).strip():
        if optional:
            return None
        raise ValueError("Missing required numeric value")
    num = float(value)
    if not math.isfinite(num):
        raise ValueError("Non-finite value in input")
    return int(num) if num.is_integer() else num

def read_csv(file, fields, date_key):
    dates = {"date", "week_ending", "period_start", "period_end"}
    optional = {"change_bcf", "hdd", "cdd"}
    rows = []
    seen = set()
    with file.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or set(headers) != set(fields):
            raise ValueError(f"{file.name}: expected unique headers {fields}, got {headers}")
        for raw in reader:
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"{file.name}: wrong number of CSV cells on line {reader.line_num}")
            row = {k: parse_date(raw[k]) if k in dates else parse_number(raw[k], optional=k in optional) for k in fields}
            key = row[date_key]
            if key in seen:
                raise ValueError(f"{file.name}: duplicate {key}")
            seen.add(key)
            if date_key == "week_ending" and date.fromisoformat(key).weekday() != 4:
                raise ValueError(f"Non-Friday week label: {key}")
            if file.stem == "weather":
                start, end = period_for(key)
                if (row["period_start"], row["period_end"]) != (start, end):
                    raise ValueError(f"Unexpected weather period at {key}")
                if any(row[k] is not None and row[k] < 0 for k in ("hdd", "cdd")):
                    raise ValueError(f"Negative degree days at {key}")
            rows.append(row)
    if not rows:
        raise ValueError(f"{file.name} is empty")
    rows.sort(key=lambda x: x[date_key])
    if file.stem == "storage":
        previous = None
        for row in rows:
            if row["working_gas_bcf"] < 0:
                raise ValueError(f"Negative working gas inventory at {row[date_key]}")
            contiguous = previous is not None and date.fromisoformat(row[date_key]) - date.fromisoformat(previous[date_key]) == timedelta(days=7)
            expected = row["working_gas_bcf"] - previous["working_gas_bcf"] if contiguous else None
            if row["change_bcf"] != expected:
                raise ValueError(f"Storage change does not reconcile to the prior Friday at {row[date_key]}")
            previous = row
    return rows

def period_for(week_ending):
    anchor = date.fromisoformat(week_ending)
    return (anchor - timedelta(days=7)).isoformat(), (anchor - timedelta(days=1)).isoformat()

def join_weekly(storage, weather, spot):
    by_weather = {r["week_ending"]: r for r in weather}
    by_spot = {r["date"]: r["usd_per_mmbtu"] for r in spot}
    joined = []
    for inventory in storage:
        anchor = inventory["week_ending"]
        start, end = period_for(anchor)
        obs = by_weather.get(anchor, {})
        rates = []
        for offset in range(1, 8):
            d = (date.fromisoformat(anchor) - timedelta(days=offset)).isoformat()
            if d in by_spot:
                rates.append(by_spot[d])
        joined.append({
            "week_ending": anchor, "period_start": start, "period_end": end,
            "working_gas_bcf": inventory["working_gas_bcf"], "change_bcf": inventory["change_bcf"],
            "hdd": obs.get("hdd"), "cdd": obs.get("cdd"),
            "spot_avg_usd_mmbtu": round(sum(rates) / len(rates), 4) if rates else None,
            "spot_days": len(rates),
        })
    return joined

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, allow_nan=False, separators=(",", ":"), ensure_ascii=False)+"\n", encoding="utf-8")
    temp.replace(path)

def build(source, target):
    source, target = Path(source), Path(target)
    if target.is_symlink() or source.resolve().is_relative_to(target.resolve()):
        raise ValueError("Target must be a separate generated-output directory")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    snapshot_time = parse_timestamp(manifest["generated_at_utc"])
    rows = {}
    for name in ("storage", "weather", "spot"):
        file = source / (name + ".csv")
        provenance = manifest["sources"][name]
        if hashlib.sha256(file.read_bytes()).hexdigest() != provenance["sha256"]:
            raise ValueError(f"{file.name} differs from the source manifest")
        meta = DATASETS[name]
        observations = read_csv(file, meta["columns"], meta["key"])
        key = meta["key"]
        actual = (len(observations), observations[0][key], observations[-1][key])
        expected = (provenance["row_count"], provenance["min_date"], provenance["max_date"])
        if actual != expected:
            raise ValueError(f"{file.name} coverage differs from the source manifest")
        rows[name] = observations
    rows["weekly"] = join_weekly(rows["storage"], rows["weather"], rows["spot"])
    sources = {}
    for name in ("storage", "weather", "spot"):
        meta = manifest["sources"][name]
        stamp = meta["downloaded_at_utc"]
        if parse_timestamp(stamp) > snapshot_time:
            raise ValueError(f"Source {name} was retrieved after the manifest snapshot time")
        keys = [r[DATASETS[name]["key"]] for r in rows[name]]
        sources[name] = {
            "label": DATASETS[name]["label"], "source_url": meta["source_url"],
            "updated_at_utc": stamp, "first_date": keys[0], "last_date": keys[-1], "rows": len(keys),
            "status": meta.get("status", "retrieved"), "units": meta["units"],
        }
    catalog = {
        "version": "v1", "built_at_utc": manifest["generated_at_utc"], "fields": FIELD_NOTES,
        "sources": sources, "datasets": {}, "release_note": "Snapshot dates are observation dates. Historical records reflect the current source files and may include revisions.",
    }
    outputs = {}
    for name in DATASETS:
        meta = DATASETS[name]
        data = rows[name]
        outputs[name+".json"] = data
        by_year = defaultdict(list)
        for r in data:
            by_year[r[meta["key"]][:4]].append(r)
        summary = {**meta, "path": name+".json", "first_date": data[0][meta["key"]],
                   "last_date": data[-1][meta["key"]], "rows": len(data), "years": sorted(by_year)}
        if name == "weekly":
            for year, annual in by_year.items():
                outputs["years/"+year+".json"] = annual
            outputs["latest.json"] = data[-1]
            outputs["recent.json"] = data[-52:]
        catalog["datasets"][name] = summary
    outputs["index.json"] = catalog
    publish_snapshot(target, outputs)
    return catalog


def require_managed_target(target):
    """Refuse to replace directories that are not recognizable v1 API output.

    Obsolete YYYY.json partitions are allowed, but unrelated files, directories,
    symlinks, catalogs and endpoint shapes are not. This check never writes.
    """
    def refuse(detail):
        raise ValueError(f"Refusing to replace unmanaged API target {target}: {detail}")

    if target.is_symlink():
        refuse("target is a symlink")
    if not target.exists():
        return
    if not target.is_dir():
        refuse("target is not a directory")
    required = {"index.json", "latest.json", "recent.json", *(name + ".json" for name in DATASETS)}
    files = set()
    for entry in target.rglob("*"):
        relative = entry.relative_to(target).as_posix()
        if entry.is_symlink():
            refuse(f"symlink {relative}")
        if entry.is_dir():
            if relative != "years":
                refuse(f"unrecognized directory {relative}")
        elif entry.is_file() and (relative in required or re.fullmatch(r"years/\d{4}\.json", relative)):
            files.add(relative)
        else:
            refuse(f"unrecognized file {relative}")
    if not required <= files:
        refuse("missing required API endpoints")

    def load(relative):
        try:
            return json.loads((target / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            refuse(f"unreadable JSON in {relative}: {exc}")

    catalog = load("index.json")
    try:
        if not isinstance(catalog, dict) or catalog.get("version") != "v1":
            refuse("unrecognized catalog version")
        parse_timestamp(catalog["built_at_utc"])
        if set(catalog["datasets"]) != set(DATASETS) or set(catalog["sources"]) != {"storage", "weather", "spot"}:
            refuse("unrecognized catalog datasets or sources")
        for field in FIELD_NOTES:
            definition = catalog["fields"][field]
            if not isinstance(definition, dict) or any(not isinstance(definition.get(key), str) for key in ("label", "unit", "type", "definition")):
                refuse(f"unrecognized field definition {field}")
        for name, expected in DATASETS.items():
            meta = catalog["datasets"][name]
            if meta["path"] != name + ".json" or meta["key"] != expected["key"] or meta["columns"] != expected["columns"]:
                refuse(f"unrecognized dataset contract {name}")
            first, last = parse_date(meta["first_date"]), parse_date(meta["last_date"])
            if type(meta["rows"]) is not int or meta["rows"] < 1 or first > last:
                refuse(f"invalid coverage in {name}")
            years = meta["years"]
            if not isinstance(years, list) or not years or any(not isinstance(year, str) or not re.fullmatch(r"\d{4}", year) for year in years) or years != sorted(set(years)):
                refuse(f"invalid year catalog in {name}")
        if not {f"years/{year}.json" for year in catalog["datasets"]["weekly"]["years"]} <= files:
            refuse("cataloged year endpoint is missing")
    except (KeyError, TypeError, ValueError) as exc:
        refuse(f"invalid v1 catalog: {exc}")

    for relative in files - {"index.json"}:
        value = load(relative)
        rows = [value] if relative == "latest.json" else value
        name = Path(relative).stem if relative in required and relative not in {"latest.json", "recent.json"} else "weekly"
        expected = DATASETS[name]
        if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) or set(row) != set(expected["columns"]) for row in rows):
            refuse(f"unrecognized API rows in {relative}")
        try:
            dates = [parse_date(row[expected["key"]]) for row in rows]
        except (TypeError, ValueError) as exc:
            refuse(f"invalid observation dates in {relative}: {exc}")
        if dates != sorted(set(dates)):
            refuse(f"unordered or duplicate dates in {relative}")
        if relative.startswith("years/") and any(day[:4] != Path(relative).stem for day in dates):
            refuse(f"year file contains dates from another year: {relative}")


def publish_snapshot(target, outputs):
    """Stage a complete managed directory; roll back if promotion fails.

    Build before deployment, not in a live document root: replacing an existing
    directory requires two renames. The lock prevents concurrent builder runs.
    """
    target = Path(target)
    require_managed_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name("." + target.name + ".build-lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise RuntimeError(f"Another build holds {lock}; inspect it before retrying") from exc
    stage = backup = None
    try:
        stage = Path(tempfile.mkdtemp(prefix="." + target.name + "-stage-", dir=target.parent))
        for relative, value in outputs.items():
            write_json(stage / relative, value)
        require_managed_target(stage)
        # Recheck after staging in case another process created or changed target.
        require_managed_target(target)
        if target.exists():
            backup = Path(tempfile.mkdtemp(prefix="." + target.name + "-backup-", dir=target.parent))
            backup.rmdir()
            target.replace(backup)
        try:
            stage.replace(target)
        except BaseException:
            if backup is not None:
                backup.replace(target)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        lock.rmdir()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=DEFAULT_DATA)
    p.add_argument("--target", type=Path, default=HERE / "v1")
    opts = p.parse_args()
    cat = build(opts.source, opts.target)
    print("\n".join(f"{n}: {d['rows']} rows ({d['first_date']} through {d['last_date']})" for n, d in cat["datasets"].items()))
