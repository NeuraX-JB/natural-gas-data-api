# Natural Gas Data API

Fetch a weekly research dataset combining U.S. Lower 48 working gas storage, contiguous U.S. degree-day weather and Henry Hub spot prices. Public static JSON works from a notebook, browser or command line, with no authentication. Start in the [API explorer](./index.html), [data-status page](./status.html) or [sample Python notebook](./natural_gas_api.ipynb).

## One request

```python
import json
from urllib.request import urlopen

base = (
    "https://neurax-jb.github.io/"
    "natural-gas-data-api/lab/api"
)
with urlopen(f"{base}/v1/weekly.json", timeout=25) as response:
    weeks = json.load(response)

print(weeks[-1]["week_ending"], weeks[-1]["change_bcf"])
```

## Endpoints

All paths below start at `v1/`. Time-series arrays are chronological.

| Path | Response |
| --- | --- |
| `weekly.json` | All joined storage weeks |
| `recent.json` | Latest 52 reported storage weeks |
| `latest.json` | Single object with the latest joined storage week |
| `years/YYYY.json` | Joined rows whose storage Friday falls within the requested calendar year |
| `storage.json` | Weekly Lower 48 working gas stocks and net stock changes, Bcf |
| `weather.json` | Observed population-weighted CONUS weekly heating and cooling degree days, base 65°F |
| `spot.json` | Observed daily Henry Hub quotes in USD/MMBtu |
| `index.json` | Fields, units, source URLs, retrieval times, coverage and supported years |

Choose a year listed in `datasets.weekly.years` in [the catalog](v1/index.json). Annual partitions contain joined storage weeks. For earlier weather or spot history, request the corresponding full series. For a narrower date range, filter the returned array in your code. The explorer previews up to six rows newest first and exports the entire selection to CSV. JSON nulls become empty CSV cells.

## Alignment

The joined data uses Friday EIA storage dates as its calendar. Weather sums cover the preceding Friday through Thursday (inclusive). Spot uses the arithmetic mean of reported quotes in that same window, rounded to four decimal places. `spot_days` gives the number of observations behind each price. Missing quotes receive no weight. Weeks with zero price observations have a null mean. Zero degree days and unchanged inventories remain zero. Historic files can incorporate revisions, and the retrieval timestamp marks when this edition obtained its sources.

For the week ending 13 November 2026, the price observations on 6, 9, 10, 11 and 12 November were $2.60, $2.89, $3.00, $3.00 and $3.00 per MMBtu. Their sum divided by five gives $2.898 per MMBtu. The 13 November quote falls in the next sampling window. [Daily quotes](v1/spot.json) · [Joined result](v1/latest.json)

EIA is the source of working gas stocks and Henry Hub spot observations. EIA attributes its underlying spot price series to Refinitiv, an LSEG business. NOAA's Climate Prediction Center supplies population-weighted degree days. The [source documentation](../data/README.md) describes coverage, cleaning and original sources.

## Rebuild

To reproduce this frozen edition, keep the checked-in CSVs and manifest together. From the lab directory, run the following without refreshing the upstream data. The API builder and tests use Python 3.10+ and its standard library.

```sh
python api/build_api.py
python -m unittest discover -s api -p test_api.py
node --test api/test_response.cjs
```

The notebook runs in Jupyter with pandas and matplotlib. Its default base is this repository’s standalone Pages API. Set `NATGAS_API_BASE` to point to a local or hosted API mirror. Saved outputs are cleared so an unrun notebook cannot display results from another endpoint. Running all cells reads the selected mirror and prints its snapshot timestamp.


## Build and timestamp contract

The builder rejects duplicate headers, ragged rows, noncanonical dates, nonfinite values, negative inventory and unreconciled weekly changes. A missing prior Friday requires a null stock change. It stages every endpoint before replacing the managed target directory and removes obsolete year partitions. An incomplete staging write leaves the previous target intact; a failed promotion restores it. An existing target is accepted only when it has a recognizable v1 API catalog, every required endpoint, and only the managed JSON/year layout. Unrelated files, catalogs, directories or symlinks are rejected without replacing the target. Choose a new, nonexistent directory when creating a fresh export. Obsolete year partitions are removed only from a validated managed snapshot.

Build before deploying. Replacing an existing directory takes two renames and is not a transaction for concurrent HTTP readers. A sibling build lock prevents two builders from replacing the same target at once. If a process is forcibly terminated, inspect its lock and backup before manual recovery.

For compatibility, catalog key `built_at_utc` retains its name but records the **source manifest generation time**, not the time the API was rebuilt or deployed. Source `updated_at_utc` records successful retrieval. Neither timestamp proves first-release availability. The source page shows elapsed retrieval age from the reader's clock and saved pipeline status, not provider uptime.

The browser validates endpoint shape, dates, numeric types, required null conventions and price denominators before allowing CSV export. A 25-second request timeout produces a recoverable error. Direct JSON links remain available without JavaScript.
