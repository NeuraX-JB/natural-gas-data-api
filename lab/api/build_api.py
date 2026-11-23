#!/usr/bin/env python3
"""Build versioned JSON endpoints from the lab's validated public-source CSV snapshots."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, timedelta
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
        "about": "Working gas in underground storage for the Lower 48. A positive weekly change is a net injection.",
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
    "change_bcf": {"label": "Weekly change", "unit": "Bcf", "type": "number or null", "definition": "Current working gas inventory less inventory on the prior Friday. An injection is positive. A withdrawal is negative."},
    "hdd": {"label": "Heating degree days", "unit": "°F-days", "type": "number or null", "definition": "Weekly sum of population-weighted heating degree days from NOAA CPC, 65°F base."},
    "cdd": {"label": "Cooling degree days", "unit": "°F-days", "type": "number or null", "definition": "Weekly sum of population-weighted cooling degree days from NOAA CPC, 65°F base."},
    "spot_avg_usd_mmbtu": {"label": "Mean spot", "unit": "$/MMBtu", "type": "number or null", "definition": "Arithmetic mean of the Henry Hub daily spot quotes published within the seven-day window, rounded to four decimal places."},
    "spot_days": {"label": "Spot quotes", "unit": "days", "type": "integer", "definition": "Count of reported daily spot prices inside the sampling window. Unreported dates receive no weight."},
    "date": {"label": "Quote date", "unit": "date", "type": "YYYY-MM-DD", "definition": "Calendar date of the observed Henry Hub spot quote."},
    "usd_per_mmbtu": {"label": "Henry Hub spot", "unit": "$/MMBtu", "type": "number", "definition": "Henry Hub natural gas spot price in U.S. dollars per million British thermal units."},
}

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
        missing = set(fields) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{file.name} missing fields {sorted(missing)}")
        for raw in reader:
            row = {k: date.fromisoformat(raw[k]).isoformat() if k in dates else parse_number(raw[k], optional=k in optional) for k in fields}
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
    return sorted(rows, key=lambda x: x[date_key])

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
    manifest = json.loads((source / "manifest.json").read_text())
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
        if not stamp:
            raise ValueError(f"Source {name} lacks a successful fetch timestamp")
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
    for name in DATASETS:
        meta = DATASETS[name]
        data = rows[name]
        write_json(target / (name+".json"), data)
        by_year = defaultdict(list)
        for r in data:
            by_year[r[meta["key"]][:4]].append(r)
        summary = {**meta, "path": name+".json", "first_date": data[0][meta["key"]],
                   "last_date": data[-1][meta["key"]], "rows": len(data), "years": sorted(by_year)}
        if name == "weekly":
            for year, annual in by_year.items():
                write_json(target / "years" / (year+".json"), annual)
            write_json(target / "latest.json", data[-1])
            write_json(target / "recent.json", data[-52:])
        catalog["datasets"][name] = summary
    write_json(target / "index.json", catalog)
    return catalog

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=DEFAULT_DATA)
    p.add_argument("--target", type=Path, default=HERE / "v1")
    opts = p.parse_args()
    cat = build(opts.source, opts.target)
    print("\n".join(f"{n}: {d['rows']} rows ({d['first_date']} through {d['last_date']})" for n, d in cat["datasets"].items()))
