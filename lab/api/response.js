/* The browser and its contract tests use the same response boundary. */
(function (scope) {
  "use strict";
  const columns = {
    weekly: ["week_ending", "period_start", "period_end", "working_gas_bcf", "change_bcf", "hdd", "cdd", "spot_avg_usd_mmbtu", "spot_days"],
    storage: ["week_ending", "working_gas_bcf", "change_bcf"],
    weather: ["week_ending", "period_start", "period_end", "hdd", "cdd"],
    spot: ["date", "usd_per_mmbtu"],
  };
  const dateFields = new Set(["date", "week_ending", "period_start", "period_end"]);
  const nullable = new Set(["change_bcf", "hdd", "cdd", "spot_avg_usd_mmbtu"]);
  function isoDate(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const time = new Date(value + "T00:00:00Z");
    return Number.isFinite(+time) && time.toISOString().slice(0, 10) === value;
  }
  function timestamp(value) {
    return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value) &&
      Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value.replace("Z", ".000Z");
  }
  function fail(message) { throw new Error("Invalid API response: " + message); }
  function validateRows(name, payload, single = false) {
    if (!Object.hasOwn(columns, name)) fail("unknown dataset");
    if (single ? !payload || Array.isArray(payload) || typeof payload !== "object" : !Array.isArray(payload))
      fail(single ? "latest must be an object" : "time series must be an array");
    const rows = single ? [payload] : payload, key = name === "spot" ? "date" : "week_ending";
    let previous;
    for (const row of rows) {
      if (!row || typeof row !== "object" || Array.isArray(row)) fail("row must be an object");
      for (const field of columns[name]) {
        if (!Object.hasOwn(row, field)) fail("missing " + field);
        const value = row[field];
        if (dateFields.has(field)) {
          if (!isoDate(value)) fail("invalid date in " + field);
        } else if (!(value === null && nullable.has(field)) && (typeof value !== "number" || !Number.isFinite(value))) {
          fail("expected a finite number" + (nullable.has(field) ? " or null" : "") + " in " + field);
        }
      }
      if (previous && row[key] <= previous[key]) fail("dates must be distinct and chronological");
      if (name !== "spot" && new Date(row[key] + "T00:00:00Z").getUTCDay() !== 5) fail("week must end on Friday");
      if (row.working_gas_bcf < 0 || row.hdd < 0 || row.cdd < 0) fail("negative inventory or degree days");
      if ("period_start" in row) {
        const anchor = Date.parse(row.week_ending + "T00:00:00Z");
        if (anchor - Date.parse(row.period_start + "T00:00:00Z") !== 7 * 86400000 ||
            anchor - Date.parse(row.period_end + "T00:00:00Z") !== 86400000) fail("incorrect Friday–Thursday window");
      }
      if (name === "weekly" && (!Number.isInteger(row.spot_days) || row.spot_days < 0 || row.spot_days > 7 ||
          (row.spot_days === 0) !== (row.spot_avg_usd_mmbtu === null))) fail("price count and missing mean disagree");
      if (previous && "working_gas_bcf" in row && Date.parse(row[key]) - Date.parse(previous[key]) === 7 * 86400000 &&
          row.change_bcf !== row.working_gas_bcf - previous.working_gas_bcf) fail("stock change does not reconcile");
      previous = row;
    }
    return rows;
  }
  function validateCatalog(catalog) {
    if (!catalog || catalog.version !== "v1" || !timestamp(catalog.built_at_utc)) fail("invalid catalog version or snapshot time");
    for (const [name, fields] of Object.entries(columns)) {
      const meta = catalog.datasets?.[name];
      if (!meta || meta.key !== (name === "spot" ? "date" : "week_ending") || typeof meta.about !== "string" || JSON.stringify(meta.columns) !== JSON.stringify(fields) || !Array.isArray(meta.years) ||
          meta.years.some((year) => !/^\d{4}$/.test(year)) || !isoDate(meta.first_date) || !isoDate(meta.last_date) ||
          !Number.isInteger(meta.rows) || meta.rows < 1 || meta.first_date > meta.last_date) fail("invalid " + name + " catalog");
      for (const field of fields) {
        const def = catalog.fields?.[field];
        if (!def || [def.label, def.definition, def.unit, def.type].some((s) => typeof s !== "string")) fail("missing definition for " + field);
      }
      if (name === "weekly") continue;
      const source = catalog.sources?.[name];
      if (!source || !timestamp(source.updated_at_utc) || !isoDate(source.first_date) || !isoDate(source.last_date) ||
          !Number.isInteger(source.rows) || source.rows < 1 || !/^https:\/\//.test(source.source_url)) fail("invalid " + name + " source metadata");
    }
    return catalog;
  }
  function ageLabel(stamp, now = Date.now()) {
    const days = Math.floor((now - Date.parse(stamp)) / 86400000);
    if (days < 0) return "Timestamp is ahead of this device's clock";
    return days === 0 ? "Retrieved less than one day ago" : "Retrieved " + days + (days === 1 ? " day ago" : " days ago");
  }
  const api = { validateRows, validateCatalog, ageLabel };
  if (typeof module === "object" && module.exports) module.exports = api;
  else scope.NaturalGasContract = api;
})(globalThis);
