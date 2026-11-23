const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {validateRows, validateCatalog, ageLabel} = require('./response.js');
const read = name => JSON.parse(fs.readFileSync(path.join(__dirname, 'v1', name), 'utf8'));

test('every published endpoint satisfies the browser boundary', () => {
  const catalog = validateCatalog(read('index.json'));
  for (const name of Object.keys(catalog.datasets)) validateRows(name, read(name + '.json'));
  validateRows('weekly', read('latest.json'), true);
  validateRows('weekly', read('recent.json'));
  for (const year of catalog.datasets.weekly.years) validateRows('weekly', read('years/' + year + '.json'));
});
test('response shape does not depend on row count', () => {
  const row = read('latest.json');
  assert.equal(validateRows('weekly', [row]).length, 1);
  assert.deepEqual(validateRows('weekly', []), []);
  assert.throws(() => validateRows('weekly', row), /array/);
  assert.throws(() => validateRows('weekly', [row], true), /object/);
});
test('malformed values cannot enter preview or CSV state', () => {
  const row = read('latest.json');
  const cases = [null, {...row, hdd: '0'}, {...row, hdd: -1}, {...row, working_gas_bcf: null},
    {...row, spot_days: 0}, {...row, spot_days: 1.5}, {...row, spot_avg_usd_mmbtu: Infinity},
    {...row, week_ending: '2026-02-30'}, {...row, period_start: row.period_end}];
  for (const bad of cases) assert.throws(() => validateRows('weekly', [bad]));
  const missing = {...row}; delete missing.change_bcf;
  assert.throws(() => validateRows('weekly', [missing]), /missing/);
  assert.throws(() => validateRows('weekly', [row, row]), /distinct/);
  const noQuote = {...row, spot_days: 0, spot_avg_usd_mmbtu: null, hdd: 0, cdd: null};
  assert.equal(validateRows('weekly', [noQuote])[0].hdd, 0);
});
test('bad catalog clocks fail and elapsed age distinguishes future clocks', () => {
  const catalog = read('index.json');
  assert.throws(() => validateCatalog({...catalog, built_at_utc: 'today'}));
  assert.equal(ageLabel('2026-11-20T00:00:00Z', Date.parse('2026-11-23T00:00:00Z')), 'Retrieved 3 days ago');
  assert.match(ageLabel('2026-11-24T00:00:00Z', Date.parse('2026-11-23T00:00:00Z')), /ahead/);
});
