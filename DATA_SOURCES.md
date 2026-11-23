# Data sources and attribution

This project contains three observation series and a weekly join of them. It does not bundle GFS forecast fields, Census geometry, SEC futures curves or their licenses.

| Source | Material in this repository | Evidence |
| :--- | :--- | :--- |
| U.S. Energy Information Administration | Lower 48 working gas stocks and Henry Hub daily spot observations | [Source definitions](lab/data/README.md), [retrieval records and SHA-256 hashes](lab/data/manifest.json), [EIA natural gas data](https://www.eia.gov/naturalgas/) |
| NOAA Climate Prediction Center | Observed population-weighted CONUS heating and cooling degree days, base 65°F | [Aggregation method](lab/data/README.md), [raw source records](lab/data/manifest.json), [NOAA archive](https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/) |

The [API catalog](lab/api/v1/index.json) documents units, null conventions, coverage and retrieval times. Observation dates identify the period measured, not when a user could first have obtained the figure. These are frozen current-vintage observations; historical revisions may be present.

EIA attributes the underlying Henry Hub spot data to Refinitiv, an LSEG business. Public access does not establish unrestricted redistribution or commercial reuse. Check the applicable provider terms before redistributing those observations.

No repository-wide license is declared. This document grants no new rights to the code, research text or third-party data. Original project context is preserved in the [canonical source revision](https://github.com/NeuraX-JB/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/tree/80c2e5321dadc95aadd4c7f65792fb15f0e2f156).
