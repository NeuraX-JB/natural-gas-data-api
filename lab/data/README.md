# Shared observations

To reproduce the published edition, use the checked-in CSVs and run `python lab/api/build_api.py` from the repository root. The manifest ties the three CSVs to their retrieval records and hashes.

To retrieve a new edition for comparison, run the following from the repository root with Python 3.10+ and network access. The refresh writes three CSVs and their manifest to the specified output directory. The upstream downloads require no API key.

```sh
python -m pip install -r scripts/requirements-ci.txt
python lab/data/refresh.py --output-dir fresh-observations
```

Run `python -m unittest discover -s lab/data -p test_refresh.py` to check date alignment, missing-data handling and output hashes. Publish all three CSVs and the matching manifest together when releasing a new edition.

## Time and units

- `storage.csv` contains EIA's Lower 48 working-gas stock for Friday at 9 a.m. Central and the difference in Bcf from the preceding Friday. Positive values indicate a net stock increase. Reclassifications can make this measure differ from EIA's implied physical flow. The first change is blank. [EIA series](https://www.eia.gov/dnav/ng/hist/nw2_epg0_swo_r48_bcfw.htm) · [Survey methodology](https://ir.eia.gov/ngs/methodology.html) · [Release calendar](https://ir.eia.gov/ngs/schedule.html)
- `weather.csv` sums NOAA CPC's daily CONUS population-weighted HDD and CDD with a 65°F base. `week_ending` is the storage reference Friday. `period_start` is the previous Friday and `period_end` the Thursday just before the reference date, both inclusive. This approximates a Friday-morning inventory reporting interval using full observed days. The build requires both variables on all seven days. Heating and cooling degree days measure population-weighted temperature exposure in °F-days. They do not measure gas demand in Bcf. [NOAA daily source archive](https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/) · [CPC degree-day program](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/)
- `spot.csv` contains EIA's Henry Hub spot series in U.S. dollars per million Btu. EIA attributes the underlying price to Refinitiv, an LSEG business. Dates with no numeric observation are absent. A weekend, holiday or other gap is never filled with yesterday's price. [EIA series](https://www.eia.gov/dnav/ng/hist/rngwhhdd.htm) · [Definitions and sources](https://www.eia.gov/dnav/ng/TblDefs/ng_pri_fut_tbldef2.asp)

## Provenance

EIA typically releases the weekly inventory on the following Thursday at 10:30 a.m. Eastern, with exceptions on its release calendar. Daily Henry Hub observations appear in EIA's weekly price release. Early spot history contains fewer observed trading days and missing observations can span several weeks. NOAA publishes daily degree days. A weekly total becomes available once both temperature series cover the full Friday–Thursday interval. [EIA storage schedule](https://ir.eia.gov/ngs/schedule.html) · [EIA price release](https://www.eia.gov/dnav/ng/ng_pri_fut_s1_d.htm) · [CPC latest observations](https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/latest/)

`manifest.json` records the refresh time in UTC, observed coverage, row counts, hashes of the generated CSVs, and a list of raw input URLs with SHA-256 digests and retrieval times. The supplied dates are measurement dates. A download timestamp records when the pipeline fetched the current vintage. Upstream agencies may revise prior observations. The archive does not reconstruct the original release vintage for every historical date.

A refresh validates series identifiers, checks date ordering and the required number of historical observations, and builds files in a temporary directory before replacing outputs. Any change to the upstream schema or incomplete network run raises an error before results are published. The current-year NOAA files may first appear several days into January.
