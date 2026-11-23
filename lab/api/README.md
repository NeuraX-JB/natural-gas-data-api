# Natural Gas Data API

Fetch a weekly research dataset combining U.S. Lower 48 working gas storage, contiguous U.S. degree-day weather and Henry Hub spot prices. Public static JSON works from a notebook, browser or command line, with no authentication. Start in the [API explorer](./index.html), [data-status page](./status.html) or [sample Python notebook](./natural_gas_api.ipynb).

## One request

```python
import json
from urllib.request import urlopen

base = (
    "https://neurax-jb.github.io/"
    "Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/lab/api"
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

Choose a published year from `index.json`. To select individual dates within a year, filter its returned array. API JSON paths are static. The web explorer shares selections using URL parameters and exports the selected endpoint to CSV.

## Alignment

The joined data uses Friday EIA storage dates as its calendar. Weather sums cover the preceding Friday through Thursday (inclusive). Spot uses the arithmetic mean of reported quotes in that same window, rounded to four decimal places. `spot_days` gives the number of observations behind each price. Missing quotes receive no weight. Weeks with zero price observations have a null mean. Zero degree days and unchanged inventories remain zero. Historic files can incorporate revisions, and the retrieval timestamp marks when this edition obtained its sources.

EIA is the source of working gas stocks and Henry Hub spot observations. EIA attributes its underlying spot price series to Refinitiv, an LSEG business. NOAA's Climate Prediction Center supplies population-weighted degree days. The [source documentation](../data/README.md) describes coverage, cleaning and original sources.

## Rebuild

From the lab directory, run the following after refreshing the shared CSVs and manifest. The API builder and tests use Python 3.10+ and its standard library.

```sh
python api/build_api.py
python -m unittest discover -s api -p test_api.py
```

The notebook runs in Jupyter with pandas and matplotlib. Its default base is the live GitHub Pages path. Set `NATGAS_API_BASE` to point to a local or hosted API mirror. Previously saved cell output belongs to the edition when the example was built. Running all cells fetches the currently published data.
