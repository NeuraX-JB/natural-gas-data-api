# Natural Gas Data API

**John Barreto · Independent natural gas research**

Versioned static JSON endpoints for EIA storage, NOAA degree days and Henry Hub spot prices.

**[Open the live project](https://neurax-jb.github.io/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/lab/api/) · [Research portfolio](https://neurax-jb.github.io/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/lab/)**

**Methods and tools:** Python, data engineering, JSON, CSV, Jupyter.

## Research question
How can storage, observed weather and spot price observations be aligned into a consistent research dataset?

The API provides public static JSON endpoints, source metadata, weekly joins and missing-value conventions. In the 23 November 2026 source snapshot it contained 881 weekly storage rows, 2,394 weekly weather rows and 5,732 spot observations. Current coverage is available on the canonical [data status page](https://neurax-jb.github.io/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/lab/api/status.html).

## Methods and evidence
- [Endpoint and field documentation](lab/api/README.md)
- [Example Jupyter notebook](lab/api/natural_gas_api.ipynb)
- [API builder](lab/api/build_api.py)
- [Source provenance](lab/data/README.md)

## Run locally
Serve the root with `python -m http.server 8000` and visit `http://localhost:8000/lab/api/`. Rebuild the JSON from the checked-in source snapshots with `python lab/api/build_api.py`; validate with `python -m unittest discover -s lab/api`. Live data refreshes are maintained in the canonical research repository.

## Source and publication

This repository is a project-specific snapshot of the [canonical research lab](https://github.com/NeuraX-JB/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter). The live site and automated updates remain there, so the existing website and forecast ledger are preserved. Check the [source and attribution notes](DATA_SOURCES.md) before reusing third-party data. No new license is granted. Research and educational use; not investment advice.
