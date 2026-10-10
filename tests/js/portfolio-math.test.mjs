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

// --- sales (external audit, 2026-10-04: purchases only overstated anyone who sold) ---
const SOLD = series([["2019-01-01", "100.000000"], ["2021-01-01", "200.000000"], ["2022-01-03", "200.000000"]]);

test("a sale removes units at that day's price, and the return counts the money back", () => {
  const p = M.position([{ date: "2019-01-01", paise: 1000000 }], SOLD,
                       [{ date: "2021-01-01", paise: 500000 }]);
  assert.equal(units(p.unitsMilli), "75.000");          // 100 bought, 25 sold at 200
  assert.equal(rupees(p.valuePaise), "15000.00");
  assert.equal(p.investedPaise, 1000000);
  assert.equal(p.redeemedPaise, 500000);
  assert.ok(p.xirr > 0.25 && p.xirr < 0.3, `xirr ${p.xirr}`);   // doubled in two years
});

test("a sale of more than was held then is left out and said so", () => {
  const p = M.position([{ date: "2019-01-01", paise: 1000000 }], SOLD,
                       [{ date: "2021-01-01", paise: 9000000 }]);
  assert.equal(p.redeemedPaise, 0);
  assert.equal(units(p.unitsMilli), "100.000");
  assert.equal(p.sales[0].error, "more");
});

test("a sale row needs a date in the record and an amount", () => {
  const fund = { prices_from: "2019-01-01" };
  assert.ok(M.rowError(fund, "sale", { date: "", amount: "5000" }, "2022-01-03"));
  assert.ok(M.rowError(fund, "sale", { date: "2021-01-01", amount: "" }, "2022-01-03"));
  assert.equal(M.rowError(fund, "sale", { date: "2021-01-01", amount: "5000" }, "2022-01-03"), null);
  const e = M.entriesOf({ purchases: [], sips: [], sales: [{ date: "2021-01-01", amount: "5000" }] },
                        fund, "2022-01-03");
  assert.deepEqual(e.sales, [{ date: "2021-01-01", paise: 500000 }]);
});

test("a saved portfolio keeps its sales", () => {
  const got = M.parsePortfolio({ version: 1, funds: [
    { id: "INF000T01011", purchases: [], sips: [], sales: [{ date: "2021-01-01", amount: "5000" }] }] });
  assert.deepEqual(got.portfolio.funds[0].sales, [{ date: "2021-01-01", amount: "5000" }]);
});

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

test("equal values sort the same way whatever order the files list them in", () => {
  // External audit, 2026-10-04 (D-312): no tie-break made the order depend on
  // the input's, so the same portfolio could draw two ways.
  const file = (rows) => ({ as_of: "2026-08-31", aggregator: false, holdings: rows,
                            mix: [["equity", "50"], ["debt", "50"]], sectors: [["Banks", "50"], ["IT", "50"]], sizes: [] });
  const one = M.lookThrough([{ id: "F", valuePaise: 1000 }],
    { F: file([["Q", "Qco", "equity", "50"], ["P", "Pco", "equity", "50"]]) });
  const two = M.lookThrough([{ id: "F", valuePaise: 1000 }],
    { F: file([["P", "Pco", "equity", "50"], ["Q", "Qco", "equity", "50"]]) });
  assert.deepEqual(one.companies.map((r) => r.id), ["P", "Q"]);
  assert.deepEqual(two.companies.map((r) => r.id), ["P", "Q"]);
  assert.deepEqual(one.mix.map((r) => r.key), two.mix.map((r) => r.key));
});

test("overlap is the sum of the smaller weights, synthetics left out", () => {
  assert.equal(M.overlap(LOOK.A, LOOK.B), 50);
});

const ALT = [
  { id: "H", category: "c", name: "Held", amfi: "1", prices_from: "2015-01-01", ter: "1.0", r3: "0.10", size: "100" },
  { id: "P", category: "c", name: "Cheap", amfi: "2", prices_from: "2015-01-01", ter: "0.2", r3: "0.12", size: "500" },
  { id: "R", category: "c", name: "Middling", amfi: "6", prices_from: "2015-01-01", ter: "0.8", r3: "0.15", size: "60" },
  { id: "Q", category: "c", name: "Quick", amfi: "3", prices_from: "2015-01-01", ter: "0.9", r3: "0.20", size: "50" },
  { id: "N", category: "c", name: "New", amfi: "4", prices_from: "2024-06-01", ter: "0.1", r3: null, size: "900" },
  { id: "Y", category: "c", name: "Younger", amfi: "7", prices_from: "2021-03-01", ter: "0.95", r3: "0.30", size: "40" },
  { id: "O", category: "other", name: "Other", amfi: "5", prices_from: "2015-01-01", ter: "0.0", r3: "0.9", size: "9" },
];

test("alternatives: one per rule, same category, priced back to the first purchase", () => {
  const out = M.alternatives(ALT[0], ALT, "2020-01-01");
  assert.deepEqual(out.map((a) => [a.fund.id, a.reasons]), [["P", ["ter", "size"]], ["R", ["r3"]]]);
});

test("the return rule picks the category's middle fund, not today's best", () => {
  // External audit, 2026-10-04: today's highest three-year return, set against
  // purchases made years ago, is chosen knowing the outcome.
  const out = M.alternatives(ALT[0], ALT, "2020-01-01");
  const middle = out.find((a) => a.reasons.includes("r3"));
  assert.equal(middle.fund.id, "R");
});

test("a Regular plan is never suggested: suggestions compare Direct plans only", () => {
  const regular = { id: "RG", category: "c", name: "Cheap (Regular)", amfi: "8", prices_from: "2015-01-01",
                    ter: "0.01", plan: "regular", direct: "P" };
  const out = M.alternatives(ALT[0], [...ALT, regular], "2020-01-01");
  assert.ok(!out.some((a) => a.fund.id === "RG"));
});

test("with no purchase date (Compare), any fund with three years of prices is a candidate", () => {
  // External audit: Compare cut candidates at the first fund's launch, so a
  // younger fund with three years of prices was silently left out.
  const out = M.alternatives(ALT[0], ALT, null);
  const ids = out.map((a) => a.fund.id);
  assert.ok(!ids.includes("N"), "no three-year return, no candidate");
  const pool = ["P", "R", "Q", "Y"];
  assert.ok(ids.every((id) => pool.includes(id)));
  assert.equal(out.find((a) => a.reasons.includes("r3")).fund.id, "R");
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
  assert.match(M.rowError(FUND, "sip", SIP({ start: "2013-01", day: 5 }), "2026-10-01"), /begin on 15 Jan 2013; the first instalment, 05 Jan 2013,/);
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
  // `mixed` comes from categories.yaml's `ranked: false` (funds.json).
  const funds = [
    { id: "H", category: "index/undivided", mixed: true, name: "Nifty", amfi: "1", prices_from: "2015-01-01", ter: "0.2", r3: "0.1", size: "10" },
    { id: "D", category: "index/undivided", mixed: true, name: "Bonds", amfi: "2", prices_from: "2015-01-01", ter: "0.1", r3: "0.07", size: "90" },
  ];
  assert.deepEqual(M.alternatives(funds[0], funds, "2020-01-01"), []);
});

test("dates read as the rest of the site writes them", () => {
  // Design review, 2026-10-04: "Worth on 2026-09-25" beside "25 Sep 2026" elsewhere.
  assert.equal(M.day("2026-09-25"), "25 Sep 2026");
  assert.equal(M.day("2021-01-05"), "05 Jan 2021");
  assert.equal(M.day(null), "—");
});

test("units are grouped like rupees, to three places", () => {
  assert.equal(M.units(3412036n), "3,412.036");
  assert.equal(M.units(488397n), "488.397");
  assert.equal(M.units(123456789012n), "12,34,56,789.012");
});

// UI/UX critique P-03: an amount in Indian grouping once typed, and in words, so a
// lakh is not read as ten.
test("an amount is grouped the Indian way, and anything else is left as typed", () => {
  assert.equal(M.grouped("100000"), "1,00,000");
  assert.equal(M.grouped("1,00,000"), "1,00,000");
  assert.equal(M.grouped("₹ 12345678.5"), "1,23,45,678.5");
  assert.equal(M.grouped("999"), "999");
  assert.equal(M.grouped("12a"), "12a");
  assert.equal(M.grouped(""), "");
});

test("an amount in words: thousands, lakhs and crores, to two places", () => {
  assert.equal(M.inWords("100000"), "₹1 lakh");
  assert.equal(M.inWords("2,50,000"), "₹2.5 lakh");
  assert.equal(M.inWords("12345678"), "₹1.23 crore");
  assert.equal(M.inWords("5000"), "₹5 thousand");
  assert.equal(M.inWords("950"), "");
  assert.equal(M.inWords("abc"), "");
});

// P-01: each holding set beside a reference -- the longest-running index fund on its
// benchmark (funds.json `tracker`), else its category's middle three-year return.
const REF = [
  { id: "INF000000001", amfi: "1", name: "Active Flexi", category: "equity/flexi", prices_from: "2015-01-01", r3: "0.15", ter: "0.01", size: "100", tracker: "INF000000009" },
  { id: "INF000000002", amfi: "2", name: "Flexi Two", category: "equity/flexi", prices_from: "2015-01-01", r3: "0.12", ter: "0.008", size: "50" },
  { id: "INF000000003", amfi: "3", name: "Flexi Three", category: "equity/flexi", prices_from: "2015-01-01", r3: "0.10", ter: "0.009", size: "40" },
  { id: "INF000000004", amfi: "4", name: "Flexi Four", category: "equity/flexi", prices_from: "2015-01-01", r3: "0.08", ter: "0.012", size: "30" },
  { id: "INF000000009", amfi: "9", name: "Nifty 500 Index Fund", category: "index/broad", prices_from: "2016-01-01", r3: "0.13", ter: "0.002", size: "10" },
  { id: "INF000000010", amfi: "10", name: "Active Flexi (Regular)", plan: "regular", direct: "INF000000001", category: "equity/flexi", prices_from: "2015-01-01", tracker: "INF000000009" },
];
const held = (id) => REF.find((f) => f.id === id);

test("a holding's reference is the index fund on its benchmark, if it was there to buy", () => {
  const ref = M.reference(held("INF000000001"), REF, "2020-01-01");
  assert.equal(ref.fund.id, "INF000000009");
  assert.equal(ref.why, "index");
  // A Regular plan takes its Direct plan's tracker.
  assert.equal(M.reference(held("INF000000010"), REF, "2020-01-01").fund.id, "INF000000009");
});

test("else the category's middle three-year return, never the holding or its own Direct plan", () => {
  // The index fund's prices begin after the first purchase: it could not take the money.
  const ref = M.reference(held("INF000000001"), REF, "2015-06-01");
  assert.equal(ref.why, "middle");
  assert.equal(ref.fund.id, "INF000000003");   // of 2, 3 and 4 by r3: the middle one
  const regular = M.reference(held("INF000000010"), REF, "2015-06-01");
  assert.notEqual(regular.fund.id, "INF000000001");
  assert.notEqual(regular.fund.id, "INF000000010");
});

test("no reference where there is no index fund and no category to draw from", () => {
  assert.equal(M.reference({ ...held("INF000000001"), tracker: null, mixed: true }, REF, "2020-01-01"), null);
});

test("a NAV file reads to exact millionths, past headers, blanks and spaces", () => {
  const s = M.parseNavFile("# scheme_id=X amfi_code=1\n2024-01-01,12\n\n 2024-01-02,12.5 \n" +
    "2024-01-03,0.123456\r\n# a note\n2024-01-04,1000.000001\n");
  assert.deepEqual(s.dates, ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]);
  assert.deepEqual(s.navs, [12000000n, 12500000n, 123456n, 1000000001n]);
});

test("a NAV file with a figure that is not a NAV is refused", () => {
  for (const bad of ["2024-01-01,12.1234567", "2024-01-01,abc", "2024-01-01,-1", "2024-01-01,.5",
    "2024-01-01,1e3", "2024-01-01"]) {
    assert.throws(() => M.parseNavFile(bad + "\n"), /not a NAV/, bad);
  }
});
