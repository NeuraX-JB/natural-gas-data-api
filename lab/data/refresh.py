#!/usr/bin/env python3
"""Refresh public EIA and NOAA CPC sources, validate, then write the shared CSV snapshot."""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import xlrd

EIA = "https://www.eia.gov/dnav/ng/hist_xls/"
CPC = "https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/"
CPC_FIRST_YEAR = 1981
STORAGE = EIA + "NW2_EPG0_SWO_R48_BCFw.xls"
SPOT = EIA + "RNGWHHDd.xls"
METHODOLOGY = "https://ir.eia.gov/ngs/methodology.html"
CPC_INFO = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/"
EIA_ATTRIBUTION = "https://www.eia.gov/dnav/ng/TblDefs/ng_pri_fut_tbldef2.asp"
ONE_DAY = timedelta(days=1)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def download(url):
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "Henry-Hub-Research/1.0 (public data snapshot)"})
            with urlopen(req, timeout=35) as response:
                blob = response.read()
                metadata = {"url": url, "retrieved_at_utc": utc_now(), "last_modified": response.headers.get("Last-Modified"),
                            "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
                return blob, metadata
        except (OSError, TimeoutError) as error:
            if (isinstance(error, HTTPError) and 400 <= error.code < 500 and error.code != 429) or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def read_eia(blob, source_key, as_of):
    book = xlrd.open_workbook(file_contents=blob)
    sheet = book.sheet_by_name("Data 1")
    if sheet.cell_value(1, 1) != source_key:
        raise ValueError(f"Unexpected EIA source key: {sheet.cell_value(1, 1)}")
    out = {}
    omitted = Counter()
    for i in range(3, sheet.nrows):
        excel_date, value, *_ = sheet.row_values(i)
        if not isinstance(excel_date, (float, int)):
            raise ValueError(f"Invalid EIA date at row {i + 1}")
        label = xlrd.xldate_as_datetime(excel_date, book.datemode).date()
        if label > as_of:
            raise ValueError(f"EIA observation in the future: {label}")
        if label in out:
            raise ValueError(f"Duplicate EIA observation: {label}")
        if not isinstance(value, (float, int)):
            if str(value).strip().upper() in {"", "NA", "N/A", "--", "-", "W"}:
                omitted["missing_numeric_value"] += 1
                continue
            raise ValueError(f"Invalid EIA value on {label}: {value!r}")
        if not math.isfinite(value):
            raise ValueError(f"Nonfinite EIA value at {label}")
        out[label] = value
    return out, dict(omitted)


def storage_rows(observations):
    out = []
    previous = None
    for label, value in sorted(observations.items()):
        if label.weekday() != 4 or value < 0 or not value.is_integer():
            raise ValueError(f"Invalid Friday storage stock at {label}")
        delta = int(value) - previous[1] if previous and (label - previous[0]).days == 7 else None
        out.append([label.isoformat(), int(value), delta])
        previous = (label, int(value))
    return out


def load_noaa(spec):
    year, kind = spec
    blob, meta = download(f"{CPC}{year}/Population.{kind}.txt")
    lines = blob.decode("utf-8-sig").splitlines()
    if f"Product: Daily {kind} Degree Days" not in lines or "Weights: Population" not in lines:
        raise ValueError(f"Unexpected NOAA source identity: {meta['url']}")
    dates, = [line.split("|")[1:] for line in lines if line.startswith("Region|")]
    values, = [line.split("|")[1:] for line in lines if line.startswith("CONUS|")]
    if len(dates) != len(values):
        raise ValueError(f"NOAA CONUS row length mismatch: {meta['url']}")
    out = {}
    for text_date, value in zip(dates, values):
        if not re.fullmatch(r"\d{8}", text_date):
            raise ValueError(f"Bad NOAA date {text_date!r} in {year}")
        label = date(int(text_date[:4]), int(text_date[4:6]), int(text_date[6:]))
        if label.year != year or label in out:
            raise ValueError(f"Unexpected or duplicate NOAA date {label}")
        if value.strip() in {"", "NA", "N/A", "M", "NaN", "-9999", "-999", "-99", "9999"}:
            out[label] = None
        else:
            degrees = int(value)
            if not 0 <= degrees < 150:
                raise ValueError(f"Invalid CONUS {kind} at {label}: {degrees}")
            out[label] = degrees
    return kind, out, meta


def weather_rows(heating, cooling, as_of):
    """Friday is the storage reference date. Weather days cover the preceding Fri–Thu."""
    start = min(min(heating), min(cooling))
    final = min(max(heating), max(cooling), as_of - ONE_DAY)
    friday = start + timedelta(days=7)
    friday += timedelta(days=(4 - friday.weekday()) % 7)
    rows, omitted = [], []
    while friday <= min(final + ONE_DAY, as_of):
        days = [friday - timedelta(days=d) for d in range(7, 0, -1)]
        if all(heating.get(d) is not None and cooling.get(d) is not None for d in days):
            rows.append([friday.isoformat(), sum(heating[d] for d in days), sum(cooling[d] for d in days),
                         days[0].isoformat(), days[-1].isoformat()])
        else:
            omitted.append(friday.isoformat())
        friday += timedelta(days=7)
    return rows, omitted


def write_source(folder, name, header, rows, units, description, url, inputs, extra):
    target = folder / f"{name}.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return {
        "status": "ok", "file": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "row_count": len(rows), "min_date": rows[0][0], "max_date": rows[-1][0],
        "downloaded_at_utc": max(item["retrieved_at_utc"] for item in inputs),
        "source_url": url, "units": units, "description": description,
        "raw_inputs": sorted(inputs, key=lambda i: i["url"]), **extra,
    }


def refresh(output_dir):
    as_of = datetime.now(timezone.utc).date()
    output_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        storage_request = pool.submit(download, STORAGE)
        spot_request = pool.submit(download, SPOT)
        specs = [(year, kind) for year in range(CPC_FIRST_YEAR, as_of.year + 1) for kind in ("Heating", "Cooling")]
        weather_requests = {spec: pool.submit(load_noaa, spec) for spec in specs}
        inventories, storage_meta = storage_request.result()
        prices, spot_meta = spot_request.result()
        hdd, cdd, raw_weather = {}, {}, []
        for spec, request in weather_requests.items():
            try:
                kind, readings, metadata = request.result()
            except HTTPError as error:
                # At the year's turn a product may not yet exist. Complete prior years are required.
                if error.code == 404 and spec[0] == as_of.year and as_of.month == 1 and as_of.day <= 7:
                    continue
                raise
            bucket = hdd if kind == "Heating" else cdd
            bucket.update(readings)
            raw_weather.append(metadata)
    inventory, skipped_storage = read_eia(inventories, "NW2_EPG0_SWO_R48_BCF", as_of)
    spot, skipped_spot = read_eia(prices, "RNGWHHD", as_of)
    storage = storage_rows(inventory)
    daily_spot = [[d.isoformat(), f"{v:.2f}"] for d, v in sorted(spot.items())]
    weather, incomplete = weather_rows(hdd, cdd, as_of)
    last_complete_raw_day = max(
        day for day, value in hdd.items()
        if day <= as_of and value is not None and cdd.get(day) is not None
    )
    if len(storage) < 500 or len(daily_spot) < 4000 or len(weather) < 1500:
        raise ValueError("Source histories are much shorter than expected. No files updated.")
    if (as_of - max(inventory)).days > 35 or (as_of - max(spot)).days > 35 or (as_of - date.fromisoformat(weather[-1][0])).days > 35:
        raise ValueError("A recent source is more than 35 days behind the refresh date. No files updated.")
    with tempfile.TemporaryDirectory(dir=output_dir) as temp:
        temp = Path(temp)
        sources = {}
        sources["storage"] = write_source(temp, "storage", ["week_ending", "working_gas_bcf", "change_bcf"], storage,
            "Bcf", "Lower 48 states working gas in underground storage on Friday. Change is this week's reported stock minus the immediately preceding Friday's stock.",
            STORAGE, [storage_meta], {"geography": "Lower 48 states", "method_url": METHODOLOGY,
            "release_rule": "Normally published the following Thursday at 10:30 a.m. Eastern; holidays may change the date or time.",
            "release_schedule_url": "https://ir.eia.gov/ngs/schedule.html",
            "basis": "Net stock change. EIA's implied flow can differ when inventory is reclassified.",
            "omitted_source_cells": skipped_storage})
        sources["spot"] = write_source(temp, "spot", ["date", "usd_per_mmbtu"], daily_spot, "USD/MMBtu",
            "Henry Hub natural gas daily cash price as published by EIA. Only numeric observations are included. Holidays and other missing observations are never filled.",
            SPOT, [spot_meta], {"geography": "Henry Hub, Louisiana", "upstream_provider": "Refinitiv, an LSEG business, via the U.S. Energy Information Administration",
            "release_rule": "Daily market observations appear in EIA's weekly spot and futures price release. The EIA table shows the next release date.",
            "release_schedule_url": "https://www.eia.gov/dnav/ng/ng_pri_fut_s1_d.htm",
            "method_url": EIA_ATTRIBUTION, "omitted_source_cells": skipped_spot})
        sources["weather"] = write_source(temp, "weather", ["week_ending", "hdd", "cdd", "period_start", "period_end"], weather,
            "°F-days (65°F base)", "CONUS population-weighted heating and cooling degree days. Sum of seven reported daily values from the previous Friday through Thursday. The Friday label aligns the observation to EIA storage.",
            CPC, raw_weather, {"geography": "Contiguous United States (CONUS)", "weight": "NOAA CPC Population weighting",
            "method_url": CPC_INFO, "aggregation": "Observed daily CONUS rows from Population.Heating.txt and Population.Cooling.txt. Both must be present for all seven dates.",
            "release_rule": "CPC posts daily observations. Each seven-day total becomes available when both heating and cooling observations cover the preceding Friday through Thursday.",
            "excluded_incomplete_weeks": incomplete, "last_complete_raw_day": last_complete_raw_day.isoformat()})
        manifest = {"schema_version": 1, "generated_at_utc": utc_now(), "sources": sources}
        (temp / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for name in ["storage.csv", "weather.csv", "spot.csv", "manifest.json"]:
            os.replace(temp / name, output_dir / name)
    for name, info in sources.items():
        print(f"{name}: {info['row_count']:,} observations {info['min_date']} .. {info['max_date']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    refresh(parser.parse_args().output_dir)
