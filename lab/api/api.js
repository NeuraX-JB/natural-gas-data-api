(() => {
  "use strict";
  const $ = (key) => document.getElementById(key);
  const el = (tag, text) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const number = (value) => Number(value).toLocaleString("en-US");
  const day = (value) =>
    value
      ? new Date(value.slice(0, 10) + "T12:00:00Z").toLocaleDateString("en-GB", {
          year: "numeric",
          month: "short",
          day: "2-digit",
          timeZone: "UTC",
        })
      : "Unavailable";
  const fetched = (stamp) =>
    stamp ? day(stamp) + " · " + stamp.slice(11, 16) + " UTC" : "Unavailable";
  const root = new URL(".", location.href);
  let catalog,
    currentRows = [],
    currentName = "",
    requestVersion = 0,
    format = "python";
  const defaultPartition = (name) => (name === "weekly" ? "recent" : "all");
  function displayError(message) {
    $("error").hidden = !message;
    $("error").textContent = message;
  }
  async function json(url) {
    const r = await fetch(url);
    if (!r.ok) throw Error("HTTP " + r.status);
    return r.json();
  }
  function addOptions(control, entries, selected) {
    control.replaceChildren(
      ...entries.map(([value, label]) => new Option(label, value, false, value === selected)),
    );
  }
  function partitions(name) {
    if (name !== "weekly") return [["all", "Full record"]];
    return [
      ["recent", "Latest 52 weeks"],
      ["latest", "Latest week"],
      ["all", "Full record"],
      ...catalog.datasets.weekly.years
        .slice()
        .reverse()
        .map((y) => [y, y + " calendar year"]),
    ];
  }
  function pathFor(name, period) {
    if (name !== "weekly" || period === "all") return "v1/" + name + ".json";
    if (period === "recent" || period === "latest") return "v1/" + period + ".json";
    return "v1/years/" + period + ".json";
  }
  function selectedUrl() {
    return new URL(pathFor($("dataset").value, $("partition").value), root).href;
  }
  function code() {
    const url = selectedUrl();
    if (format === "python")
      return (
        'import json\nfrom urllib.request import urlopen\n\nwith urlopen("' +
        url +
        '") as response:\n    data = json.load(response)'
      );
    if (format === "js")
      return (
        'const response = await fetch("' +
        url +
        '");\nif (!response.ok) throw new Error(`HTTP ${response.status}`);\nconst data = await response.json();'
      );
    return 'curl --fail --location "' + url + '"';
  }
  function displayCode() {
    $("snippet").textContent = code();
    for (const b of document.querySelectorAll("[data-code]"))
      b.setAttribute("aria-pressed", String(b.dataset.code === format));
  }
  function friendly(value, key) {
    if (value == null) return "—";
    if (key === "spot_avg_usd_mmbtu") return value.toFixed(4);
    if (key === "usd_per_mmbtu") return value.toFixed(2);
    if (typeof value === "number") return number(value);
    return value;
  }
  function showTable(rows, name) {
    const meta = catalog.datasets[name],
      fields = meta.columns;
    const tr = el("tr");
    for (const field of fields) {
      const def = catalog.fields[field];
      const th = el("th", def.label);
      th.scope = "col";
      th.title = field + " · " + def.definition;
      if (def.unit !== "date") th.append(el("small", def.unit));
      tr.append(th);
    }
    $("t-head").replaceChildren(tr);
    const preview = rows.slice(-6).reverse();
    const rendered = preview.map((row) => {
      const tr = el("tr");
      for (const field of fields) tr.append(el("td", friendly(row[field], field)));
      return tr;
    });
    $("t-body").replaceChildren(...rendered);
    $("summary").textContent =
      number(rows.length) +
      " " +
      (rows.length === 1 ? "record" : "records") +
      (rows.length
        ? " · " +
          (rows.length === 1
            ? day(rows[0][meta.key])
            : day(rows[0][meta.key]) + " – " + day(rows.at(-1)[meta.key]))
        : "");
    $("table-hint").textContent =
      rows.length > 1
        ? "Showing the newest " + preview.length + " first. The JSON and CSV are chronological."
        : "The latest endpoint returns a single JSON object. Other time-series endpoints return arrays.";
  }
  async function loadSelection() {
    const sequence = ++requestVersion,
      name = $("dataset").value,
      period = $("partition").value;
    currentRows = [];
    currentName = name;
    $("csv").disabled = true;
    $("summary").textContent = "Loading observations…";
    $("t-head").replaceChildren();
    $("t-body").replaceChildren();
    $("table-hint").textContent = "";
    const url = selectedUrl(),
      link = $("api-link");
    link.href = url;
    link.textContent = url;
    $("about").textContent = catalog.datasets[name].about;
    displayCode();
    displayError("");
    const state = new URL(location.href);
    state.searchParams.set("resource", name);
    state.searchParams.set("window", period);
    history.replaceState(null, "", state);
    try {
      const blob = await json(url);
      if (sequence !== requestVersion) return;
      if (!Array.isArray(blob) && (!blob || !(catalog.datasets[name].key in blob)))
        throw Error("Unexpected API response");
      currentRows = Array.isArray(blob) ? blob : [blob];
      showTable(currentRows, name);
      $("csv").disabled = !currentRows.length;
    } catch (e) {
      if (sequence === requestVersion) {
        displayError(
          "This endpoint could not be loaded (" +
            e.message +
            "). Open the endpoint link or choose another observation window.",
        );
        $("summary").textContent = "Response unavailable";
      }
    }
  }
  function configure(name, suggestedPeriod) {
    const available = partitions(name),
      chosen = available.some(([id]) => id === suggestedPeriod)
        ? suggestedPeriod
        : defaultPartition(name);
    addOptions($("partition"), available, chosen);
    return loadSelection();
  }
  function downloadCSV() {
    const fields = catalog.datasets[currentName].columns;
    const escape = (v) => {
      if (v == null) return "";
      const s = String(v);
      return /[\r\n,"]/.test(s) ? '"' + s.replaceAll('"', '""') + '"' : s;
    };
    const lines = [
      fields.join(","),
      ...currentRows.map((row) => fields.map((field) => escape(row[field])).join(",")),
    ];
    const objectURL = URL.createObjectURL(
      new Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" }),
    );
    const a = el("a");
    a.href = objectURL;
    a.download = "henry_hub_" + currentName + "_" + $("partition").value + ".csv";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(objectURL), 10000);
  }
  async function copyText(value) {
    try {
      await navigator.clipboard.writeText(value);
      $("notice").textContent = "Copied.";
    } catch (_) {
      $("notice").textContent = "Select and copy the displayed text.";
    }
  }
  function showStatus() {
    $("build-stamp").textContent = fetched(catalog.built_at_utc);
    const sourceLabels = {
      storage: "EIA · Lower 48 storage",
      weather: "NOAA CPC · U.S. degree days",
      spot: "EIA · Henry Hub spot",
    };
    const notes = {
      storage: "Lower 48 inventories from EIA's weekly storage survey.",
      weather: "NOAA CPC population-weighted observations for the contiguous United States.",
      spot: "EIA reports Henry Hub prices supplied by Refinitiv, an LSEG business. Some early periods have few reported quotes.",
    };
    for (const [key, info] of Object.entries(catalog.sources)) {
      const card = el("article");
      card.className = "source-card";
      const identity = el("div");
      identity.append(el("h3", sourceLabels[key]), el("p", notes[key]));
      const anchor = el("a", "Original source");
      anchor.href = info.source_url;
      anchor.className = "status-link";
      identity.append(anchor);
      const facts = el("div");
      facts.className = "facts";
      const cells = [
        ["Coverage", day(info.first_date) + " – " + day(info.last_date)],
        ["Rows", number(info.rows)],
        ["Units", typeof info.units === "string" ? info.units : JSON.stringify(info.units)],
        ["Latest observation", day(info.last_date)],
        ["Last successful retrieval", fetched(info.updated_at_utc)],
      ];
      for (const [name, value] of cells) {
        const box = el("div");
        box.append(el("span", name), el("b", value));
        facts.append(box);
      }
      card.append(identity, facts);
      $("source-list").append(card);
    }
  }
  async function main() {
    catalog = await json(new URL("v1/index.json", root));
    if (document.body.dataset.page === "status") {
      showStatus();
      return;
    }
    const params = new URLSearchParams(location.search),
      wanted = params.get("resource");
    const name = Object.hasOwn(catalog.datasets, wanted) ? wanted : "weekly";
    $("dataset").value = name;
    $("dataset").onchange = () => configure($("dataset").value, "");
    $("partition").onchange = loadSelection;
    $("csv").onclick = downloadCSV;
    $("copy-code").onclick = () => copyText(code());
    $("copy-url").onclick = () => copyText(selectedUrl());
    for (const b of document.querySelectorAll("[data-code]"))
      b.onclick = () => {
        format = b.dataset.code;
        displayCode();
      };
    for (const [field, def] of Object.entries(catalog.fields)) {
      $("definitions").append(
        el("dt", field),
        el("dd", def.definition + " Data type is " + def.type + "."),
      );
    }
    await configure(name, params.get("window") || defaultPartition(name));
  }
  main().catch((e) =>
    displayError(
      "The API catalog could not be loaded (" + e.message + "). Reload the page to try again.",
    ),
  );
})();
