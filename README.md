# Natural Gas Data API

John Barreto · Independent natural gas research

Compare weekly changes in U.S. Lower 48 working gas stocks with observed weather and Henry Hub spot prices. Each row uses a storage Friday as its reference date, so the temperature and price observations can be traced back to the same seven-day window.

[Explore the data](https://neurax-jb.github.io/natural-gas-data-api/lab/api/) · [Read the API reference](lab/api/README.md) · [Open the example notebook](lab/api/natural_gas_api.ipynb)

## Read one week

For **13 November 2026**, Lower 48 stocks rose from **3,862 to 3,882 Bcf**, a net increase of **20 billion cubic feet**. Reclassifications can affect that difference. In the preceding Friday–Thursday window, 6–12 November, NOAA recorded **77 heating degree days and 6 cooling degree days** on a population-weighted basis. Five Henry Hub spot quotes averaged **$2.898 per MMBtu**. These observations line up in time. Explaining the stock increase requires additional evidence on supply and demand. [Joined row](lab/api/v1/latest.json) · [Both inventory readings](lab/api/v1/years/2026.json)

Read that row from a clone with Python, from the repository root.

```python
import json
from pathlib import Path

week = json.loads(Path("lab/api/v1/latest.json").read_text(encoding="utf-8"))
print(week["week_ending"], week["change_bcf"], week["spot_days"])
# 2026-11-13 20 5
```

For an HTTP request, fetch the [same JSON object](https://neurax-jb.github.io/natural-gas-data-api/lab/api/v1/latest.json). For multiple weeks, use the [most recent 52](lab/api/v1/recent.json) or [all joined weeks](lab/api/v1/weekly.json). Both return arrays ordered oldest first.

## Coverage in the 23 November 2026 edition

| Series | First observation | Last observation | Rows |
| --- | --- | --- | ---: |
| Joined storage weeks | 1 Jan 2010 | 13 Nov 2026 | 881 |
| EIA Lower 48 working gas stocks (Bcf) | 1 Jan 2010 | 13 Nov 2026 | 881 |
| NOAA contiguous U.S. heating and cooling degree days (65°F base) | 9 Jan 1981 | 20 Nov 2026 | 2,394 |
| EIA Henry Hub daily spot quotes (USD/MMBtu) | 7 Jan 1997 | 17 Nov 2026 | 5,732 |

This is a frozen edition. The last joined date follows the storage series. Individual weather and spot series extend further. In the first joined week, `change_bcf` is `null` because the previous inventory is outside the snapshot. That same row has `cdd = 0`, an observed zero. [Field definitions and coverage](lab/api/v1/index.json) · [First year of joined observations](lab/api/v1/years/2010.json)

## Reproduce and cite

To rebuild the JSON from the checked-in CSVs, run `python lab/api/build_api.py` from the repository root. To browse the explorer locally, run `python -m http.server 8000` there and open [the local explorer](http://localhost:8000/lab/api/). The [validation guide](VALIDATION.md) lists the checks for data integrity and the Python and JavaScript regression tests.

For a reproducible citation, record the repository commit, the endpoint path, the observation period and the source edition. The 23 November retrieval includes any historical revisions then present. A historical pre-release study needs separate evidence of when each input first became available. [Source records and hashes](lab/data/manifest.json) · [Attribution and reuse](DATA_SOURCES.md) · [Original research lab revision](https://github.com/NeuraX-JB/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/tree/80c2e5321dadc95aadd4c7f65792fb15f0e2f156)
