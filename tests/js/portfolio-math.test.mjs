// The portfolio page's arithmetic against the ledger's answers. DECISIONS V1-82.
// Run: node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const M = require("../../src/m6_views/static/portfolio-math.js");
const { cases } = JSON.parse(
  readFileSync(new URL("../fixtures/portfolio_cases.json", import.meta.url), "utf-8"));

const series = (navs) => M.parseNavFile(
  "# scheme_id=X amfi_code=1\n" + navs.map(([d, v]) => `${d},${v}`).join("\n") + "\n");
const rupees = (paise) => (paise / 100).toFixed(2);
const units = (milli) => `${milli / 1000n}.${String(milli % 1000n).padStart(3, "0")}`;

for (const c of cases) {
  test(`case: ${c.name}`, () => {
    const holding = { purchases: c.purchases || [], sips: c.sips || [] };
    const p = M.position(M.purchasesOf(holding, c.today), series(c.navs));
    const lots = p.lots.map((l) => (l.error ? null : {
      nav_date: l.navDate,
      nav: c.navs.find(([d]) => d === l.navDate)[1],
      stamp_duty: rupees(l.dutyPaise),
      units: units(l.unitsMilli),
    }));
    assert.deepEqual(lots, c.expect.lots);
    assert.equal(units(p.unitsMilli), c.expect.units);
    assert.equal(rupees(p.valuePaise), c.expect.value);
    assert.equal(p.valueDate, c.expect.value_date);
    if (c.expect.xirr === null) assert.equal(p.xirr, null);
    else assert.ok(Math.abs(p.xirr - Number(c.expect.xirr)) < 1e-6, `xirr ${p.xirr}`);
  });
}

test("a purchase whose NAV is not out yet says so", () => {
  const c = cases.find((x) => x.name.startsWith("a purchase whose NAV"));
  const p = M.position(M.purchasesOf({ purchases: c.purchases, sips: [] }, c.today), series(c.navs));
  assert.equal(p.lots[1].error, "pending");
  assert.equal(p.investedPaise, 300000);
});

test("a date before the first NAV is refused", () => {
  assert.deepEqual(M.allot(100000, "2023-12-31", series([["2024-01-01", "10"]])), { error: "before" });
});

test("amounts are read as people type them", () => {
  assert.equal(M.toPaise("10,000"), 1000000);
  assert.equal(M.toPaise("₹ 5,000.5"), 500050);
  for (const bad of ["1e4", "-500", "0", "", "12.345", "abc"]) assert.equal(M.toPaise(bad), null, bad);
});

test("the display rule: XIRR from a year of holding", () => {
  assert.equal(M.showsXirr("2025-01-01", "2025-12-31"), false);  // 364 days
  assert.equal(M.showsXirr("2025-01-01", "2026-01-01"), true);   // 365 days
});

const LOOK = {
  A: { as_of: "2026-08-31", aggregator: false,
       holdings: [["X", "Xco", "equity", "60"], ["Y", "Yco", "equity", "30"], ["__CASH__", "Cash", "cash", "10"]],
       mix: [["equity", "90"], ["cash", "10"]], sectors: [["Banks", "100"]], sizes: [["large", "100"]] },
  B: { as_of: "2026-07-31", aggregator: true,
       holdings: [["X", "Xco", "equity", "50"], ["__UNRESOLVED__", "Unresolved", "equity", "50"]],
       mix: [["equity", "100"]], sectors: [["Banks", "50"], ["IT", "50"]], sizes: [["mid", "100"]] },
};

test("look-through adds a company up across funds by issuer id", () => {
  const out = M.lookThrough([{ id: "A", valuePaise: 100000 }, { id: "B", valuePaise: 100000 }], LOOK);
  const x = out.companies.find((r) => r.id === "X");
  assert.equal(x.paise, 60000 + 50000);
  assert.equal(x.funds, 2);
  assert.ok(Math.abs(x.pct - 55) < 1e-9);
  assert.ok(!out.companies.some((r) => M.isSynthetic(r.id)));
  assert.equal(out.coverage.unresolvedPaise, 50000);
  const banks = out.sectors.find((s) => s.key === "Banks");
  assert.ok(Math.abs(banks.pct - (90000 + 50000) * 100 / 190000) < 1e-9);
});

test("a fund with no look-through file is counted, not dropped", () => {
  const out = M.lookThrough([{ id: "A", valuePaise: 100000 }, { id: "C", valuePaise: 50000 }],
                            { A: LOOK.A, C: null });
  assert.equal(out.total, 150000);
  assert.equal(out.coverage.unknownPaise, 50000);
});

test("overlap is the sum of the smaller weights, synthetics left out", () => {
  assert.equal(M.overlap(LOOK.A, LOOK.B), 50);
});

test("alternatives: one per rule, same category, priced back to the first purchase", () => {
  const funds = [
    { id: "H", category: "c", name: "Held", amfi: "1", prices_from: "2015-01-01", ter: "1.0", r3: "0.10", size: "100" },
    { id: "P", category: "c", name: "Cheap", amfi: "2", prices_from: "2015-01-01", ter: "0.2", r3: "0.12", size: "500" },
    { id: "Q", category: "c", name: "Quick", amfi: "3", prices_from: "2015-01-01", ter: "0.9", r3: "0.20", size: "50" },
    { id: "N", category: "c", name: "New", amfi: "4", prices_from: "2024-06-01", ter: "0.1", r3: "0.30", size: "900" },
    { id: "O", category: "other", name: "Other", amfi: "5", prices_from: "2015-01-01", ter: "0.0", r3: "0.9", size: "9" },
  ];
  const out = M.alternatives(funds[0], funds, "2020-01-01");
  assert.deepEqual(out.map((a) => [a.fund.id, a.reasons]), [["P", ["ter", "size"]], ["Q", ["r3"]]]);
});

test("parsePortfolio refuses a foreign file", () => {
  assert.ok(M.parsePortfolio({ hello: 1 }).error);
  assert.ok(M.parsePortfolio(null).error);
  assert.ok(M.parsePortfolio({ version: 2, funds: [] }).error);
});

test("parsePortfolio merges a fund entered twice and counts what it drops", () => {
  const got = M.parsePortfolio({ version: 1, funds: [
    { id: "INF000T01011", purchases: [{ date: "2024-01-01", amount: "100" }, { date: "2024-01-02", amount: { x: 1 } }], sips: [] },
    { id: "INF000T01011", purchases: [], sips: [{ amount: "500", day: 5, start: "2024-01", stop: null }] },
  ] });
  assert.equal(got.portfolio.funds.length, 1);
  assert.equal(got.portfolio.funds[0].purchases.length, 1);
  assert.equal(got.portfolio.funds[0].sips.length, 1);
  assert.equal(got.dropped, 1);
});

test("parsePortfolio keeps a blank or half-typed row: checking it is the page's job", () => {
  const got = M.parsePortfolio({ version: 1, funds: [
    { id: "INF000T01011", purchases: [{ date: "", amount: "" }, { date: "2024-01-01", amount: "" }],
      sips: [{ amount: "", day: 1, start: "2024-01", stop: null }] },
  ] });
  assert.equal(got.dropped, 0);
  assert.equal(got.portfolio.funds[0].purchases.length, 2);
  assert.equal(got.portfolio.funds[0].sips.length, 1);
});

test("today is the visitor's own date, not UTC's", () => {
  assert.equal(M.localDay(new Date(2026, 9, 2, 1, 30)), "2026-10-02");
});

const FUND = { prices_from: "2013-01-15" };
const SIP = (over) => Object.assign({ amount: "1000", day: 5, start: "2014-01", stop: null }, over);

test("rowError refuses a SIP day that is not a whole day of the month", () => {
  for (const day of [0, 2.5, 45, null]) {
    assert.match(M.rowError(FUND, "sip", SIP({ day }), "2026-10-01"), /day of the month/, String(day));
  }
});

test("rowError refuses a SIP whose first instalment is before prices begin", () => {
  assert.match(M.rowError(FUND, "sip", SIP({ start: "2013-01", day: 5 }), "2026-10-01"), /begin on 2013-01-15/);
  assert.equal(M.rowError(FUND, "sip", SIP({ start: "2013-01", day: 20 }), "2026-10-01"), null);
});

test("rowError refuses a SIP that starts after this month, and a purchase after today", () => {
  assert.match(M.rowError(FUND, "sip", SIP({ start: "2026-11" }), "2026-10-01"), /starts after this month/);
  assert.match(M.rowError(FUND, "purchase", { date: "2026-10-02", amount: "5" }, "2026-10-01"), /after today/);
});

test("entriesOf prices only rows without errors, and counts the rest", () => {
  const got = M.entriesOf({
    purchases: [{ date: "2020-01-01", amount: "1000" }, { date: "2030-01-01", amount: "1000" }, { date: "", amount: "" }],
    sips: [SIP({ day: 0 }), SIP({ start: "2026-08", stop: "2026-09" })],
  }, FUND, "2026-10-01");
  assert.deepEqual(got.buys.map((b) => b.date), ["2020-01-01", "2026-08-05", "2026-09-05"]);
  assert.equal(got.excluded, 2);  // the future purchase and the day-0 SIP; a blank row is not an error
});

test("altSlots keeps each slot where it is drawn", () => {
  const byId = (id) => ({ id });
  const suggested = [{ fund: { id: "A" }, reasons: ["ter"] }, { fund: { id: "B" }, reasons: ["r3"] }, { fund: { id: "C" }, reasons: ["size"] }];
  const slots = M.altSlots([null, "X", null], suggested, byId);
  assert.deepEqual(slots.map((s) => [s.slot, s.fund && s.fund.id]), [[0, "A"], [1, "X"], [2, "C"]]);
  // A suggestion the person already chose elsewhere is not shown twice.
  const again = M.altSlots([null, null, "A"], suggested, byId);
  assert.deepEqual(again.map((s) => s.fund && s.fund.id), [null, "B", "A"]);
  // Fewer suggestions than slots: the rest stay empty, at their own index.
  const one = M.altSlots([null, "X", null], suggested.slice(0, 1), byId);
  assert.deepEqual(one.map((s) => [s.slot, s.fund && s.fund.id]), [[0, "A"], [1, "X"], [2, null]]);
});

test("an alternative replays only the purchases the held fund priced", () => {
  const pos = { lots: [{ date: "2024-01-01", paise: 100000, unitsMilli: 1n }, { date: "2026-10-01", paise: 50000, error: "pending" }] };
  assert.deepEqual(M.pricedBuys(pos), [{ date: "2024-01-01", paise: 100000 }]);
});

test("a category AMFI uses for mixed kinds of fund gets no suggestions", () => {
  // "Other Scheme - Index Funds" holds equity and debt index funds alike: a
  // Nifty 50 fund must not be set beside a bond index as its like.
  const funds = [
    { id: "H", category: "index/undivided", name: "Nifty", amfi: "1", prices_from: "2015-01-01", ter: "0.2", r3: "0.1", size: "10" },
    { id: "D", category: "index/undivided", name: "Bonds", amfi: "2", prices_from: "2015-01-01", ter: "0.1", r3: "0.07", size: "90" },
  ];
  assert.deepEqual(M.alternatives(funds[0], funds, "2020-01-01"), []);
});
