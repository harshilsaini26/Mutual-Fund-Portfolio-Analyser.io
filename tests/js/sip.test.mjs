// "What would a SIP have become?" (SPEC_SIP_WHAT_IF §4.5): the pure functions in
// portfolio-math.js that /sip/ uses. Run: node --test tests/js/
// tests/fixtures/sip_cases.json pins the arithmetic; tests/unit/test_sip_kinds.py
// holds M2's Decimal twin (src/m2_fund/sip.py, the build's overview) to the same file.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const M = createRequire(import.meta.url)("../../src/m6_views/static/portfolio-math.js");
const { cases } = JSON.parse(
  readFileSync(new URL("../fixtures/sip_cases.json", import.meta.url), "utf-8"));

const series = (rows) => ({ dates: rows.map((r) => r[0]), navs: rows.map((r) => M.toMicro(r[1])) });
const seriesOf = (funds) => new Map(funds.map((f) => [f.id, f.navs ? series(f.navs) : null]));

// --- windowOf (§4.3) ----------------------------------------------------------------
const sip = (over) => Object.assign({ mode: "sip", amountPaise: 500000, years: 5, from: null, day: 5 }, over);

test("five years on the 5th, valued on a 5th: 60 instalments ending that month", () => {
  const w = M.windowOf(sip({}), "2026-10-05");
  assert.equal(w.count, 60);
  assert.equal(w.first, "2021-11-05");
  assert.equal(w.last, "2026-10-05");
  assert.ok(w.buys.every((b) => b.paise === 500000));
});

test("a day after the valuation date's ends the month before", () => {
  const w = M.windowOf(sip({ day: 10 }), "2026-10-05");
  assert.equal(w.count, 60);
  assert.equal(w.first, "2021-10-10");
  assert.equal(w.last, "2026-09-10");
});

test("the 31st falls on each month's last day, February included", () => {
  const w = M.windowOf(sip({ years: 1, day: 31 }), "2026-03-31");
  assert.equal(w.count, 12);
  assert.ok(w.buys.some((b) => b.date === "2026-02-28"));
  assert.equal(w.last, "2026-03-31");
});

test("once, N years before: 29 February becomes the 28th", () => {
  const w = M.windowOf({ mode: "once", amountPaise: 10000000, years: 1, day: 5 }, "2024-02-29");
  assert.deepEqual(w.buys, [{ date: "2023-02-28", paise: 10000000 }]);
  assert.equal(w.count, 1);
});

test("a chosen start on or after the valuation date, or no amount, is an error", () => {
  assert.equal(M.windowOf(sip({ years: null, from: "2026-11" }), "2026-10-05").error, "after");
  assert.equal(M.windowOf({ mode: "once", amountPaise: 100, from: "2026-10-05" }, "2026-10-05").error,
    "after");
  assert.equal(M.windowOf(sip({ amountPaise: null }), "2026-10-05").error, "amount");
});

// §10 said toPaise's 13-digit cap kept 120 instalments under 2^53 paise; it does not
// (about 1.2e17). /sip/ caps an amount at ₹10 crore (1e10 paise): 120 of them, grown
// a hundredfold, are 1.2e14 paise, exact as a Number.
test("an amount up to ₹10 crore stays exact over 120 instalments; above it is refused", () => {
  const top = M.toPaise("100000000");
  const w = M.windowOf(sip({ amountPaise: top, years: 10 }), "2026-10-05");
  assert.equal(w.count, 120);
  assert.ok(Number.isSafeInteger(w.buys.reduce((s, b) => s + b.paise, 0) * 100));
  assert.equal(M.windowOf(sip({ amountPaise: top + 1 }), "2026-10-05").error, "amount");
  assert.equal(M.SIP_MAX_PAISE, top);
});

// --- valuationDate (§4.3) -------------------------------------------------------------
test("a fund three days behind sets the date; one eight days behind is stale", () => {
  const v = M.valuationDate(new Map([
    ["A", series([["2026-10-01", "10"], ["2026-10-05", "11"]])],
    ["B", series([["2026-10-02", "10"]])],
    ["C", series([["2026-09-27", "10"]])],
    ["D", null],
  ]));
  assert.deepEqual(v, { valuedOn: "2026-10-02", latest: "2026-10-05", stale: ["C"] });
});

// --- poolOf (§4.4) --------------------------------------------------------------------
test("every fund is in the range or out of it once, load before stale before later", () => {
  const funds = [{ id: "A" }, { id: "B" }, { id: "C" }, { id: "D" }, { id: "R", plan: "regular" }];
  const s = new Map([
    ["A", series([["2024-01-01", "10"], ["2024-03-05", "11"]])],
    ["B", series([["2024-02-01", "10"], ["2024-03-05", "11"]])],     // later
    ["C", series([["2024-02-01", "10"], ["2024-02-10", "11"]])],     // later and stale
    ["D", null],                                                    // did not load
    ["R", series([["2024-01-01", "10"], ["2024-03-05", "11"]])],
  ]);
  const pool = M.poolOf(funds, s, { first: "2024-01-05" }, "2024-03-05");
  assert.deepEqual(pool.inRange.map((f) => f.id), ["A"]);
  assert.deepEqual(pool.out.map((o) => [o.fund.id, o.reason]), [["B", "later"], ["C", "stale"], ["D", "load"]]);
  // Regular plans are the same funds at a higher cost: ranges are Direct plans.
  assert.ok(!pool.inRange.concat(pool.out.map((o) => o.fund)).some((f) => f.id === "R"));
});

// --- outcome (§4.5) -------------------------------------------------------------------
test("the lowest point, against what was put in by then", () => {
  const s = series([["2024-01-05", "10"], ["2024-02-05", "8"], ["2024-03-05", "12"]]);
  const buys = ["2024-01-05", "2024-02-05", "2024-03-05"].map((d) => ({ date: d, paise: 100000 }));
  const o = M.outcome(buys, s, "2024-03-05");
  // 2 Feb: (99.995 + 124.994) units x 8 = 1,799.912 -> 179,991 paise against 200,000.
  assert.equal(o.lowOn, "2024-02-05");
  assert.equal(o.low, (179991 - 200000) / 200000);
  assert.equal(o.valuePaise, 369982);
});

test("never below: no low; and prices after the valuation date are not used", () => {
  const s = series([["2024-01-05", "10"], ["2024-02-05", "11"], ["2024-02-08", "12"], ["2024-02-20", "1"]]);
  const o = M.outcome([{ date: "2024-01-05", paise: 100000 }], s, "2024-02-10");
  assert.equal(o.low, 0);
  assert.equal(o.lowOn, null);
  assert.equal(o.valueDate, "2024-02-08");
  assert.equal(o.valuePaise, 119994);   // 99.995 units x 12
});

test("the day of the first purchase is not a fall: only stamp duty is off it", () => {
  const s = series([["2024-01-05", "10"], ["2024-02-05", "10.1"]]);
  const o = M.outcome([{ date: "2024-01-05", paise: 100000 }], s, "2024-02-05");
  assert.equal(o.low, 0);
});

// --- spread (§4.5) --------------------------------------------------------------------
const out = (id, v, low = 0) => ({ fund: { id }, valuePaise: v, low });
test("the range: lowest, the lower middle and highest, ties on id", () => {
  assert.equal(M.spread([]).n, 0);
  const one = M.spread([out("A", 5)]);
  assert.deepEqual([one.min.fund.id, one.middle.fund.id, one.max.fund.id], ["A", "A", "A"]);
  const two = M.spread([out("B", 9), out("A", 5)]);
  assert.equal(two.middle.fund.id, "A");
  const three = M.spread([out("C", 7), out("A", 5), out("B", 9, -0.1)]);
  assert.deepEqual([three.min.fund.id, three.middle.fund.id, three.max.fund.id, three.belowEver],
    ["A", "C", "B", 1]);
  const four = M.spread([out("D", 4), out("C", 7), out("A", 5), out("B", 9)]);
  assert.equal(four.middle.fund.id, "A");
  const tie = M.spread([out("B", 5), out("A", 5), out("C", 6)]);
  assert.equal(tie.min.fund.id, "A");
});

// --- indexFor (§4.5) ------------------------------------------------------------------
test("the index fund most of a kind name, the longer record on a tie, else none", () => {
  const f = (id, category, tracker, prices_from = "2015-01-01") => ({ id, category, tracker, prices_from });
  const funds = [
    f("A", "equity/large_cap", "I1"), f("B", "equity/large_cap", "I2"), f("C", "equity/large_cap", "I2"),
    f("D", "equity/large_cap", null), f("E", "equity/mid_cap", "I1"), f("F", "equity/mid_cap", "I3"),
    f("I1", "index/broad", null, "2010-01-01"), f("I2", "index/broad", null, "2012-01-01"),
    f("I3", "index/broad", null, "2016-01-01"),
  ];
  const large = M.indexFor(funds, "equity/large_cap");
  assert.deepEqual([large.fund.id, large.sharedBy], ["I2", 2]);
  assert.equal(M.indexFor(funds, "equity/mid_cap").fund.id, "I1");   // one each: I1 is older
  assert.equal(M.indexFor(funds, "debt/liquid"), null);
});

// --- pathOf (§4.5) --------------------------------------------------------------------
test("the path: worth at each month's end, the last point on the valuation date", () => {
  const s = series([["2024-01-05", "10"], ["2024-01-31", "11"], ["2024-02-05", "10"],
                    ["2024-02-29", "12"], ["2024-03-04", "13"]]);
  const buys = [{ date: "2024-01-05", paise: 100000 }, { date: "2024-02-05", paise: 100000 }];
  const p = M.pathsOf(buys, [s], "2024-03-05", "month").paths[0];
  assert.deepEqual(p.points.map((x) => x[0]), ["2024-01-31", "2024-02-29", "2024-03-05"]);
  assert.equal(p.points[0][1], 109995);   // 99.995 units x 11 = 1,099.945 -> half up
  assert.deepEqual(p.putIn, [["2024-01-05", 100000], ["2024-02-05", 200000], ["2024-03-05", 200000]]);
});

test("every fund's path is on the same dates, from the last first price among them", () => {
  // The review's case: A priced the purchase on Friday 3 Oct, B (no NAV that day) on
  // Monday the 6th. Weekly points must still be one set of dates, with B holding units
  // at each, or chart 1's band mixes dates and its table reads ₹0.
  const a = series([["2025-10-03", "10"], ["2025-10-06", "10"], ["2025-10-20", "11"], ["2025-10-27", "12"]]);
  const b = series([["2025-10-01", "10"], ["2025-10-06", "10"], ["2025-10-20", "11"], ["2025-10-27", "12"]]);
  const got = M.pathsOf([{ date: "2025-10-03", paise: 100000 }], [a, b], "2025-10-27", "week");
  const want = ["2025-10-12", "2025-10-19", "2025-10-26", "2025-10-27"];
  assert.deepEqual(got.grid, want);
  assert.deepEqual(got.paths.map((p) => p.points.map((x) => x[0])), [want, want]);
  assert.ok(got.paths.every((p) => p.points.every((x) => x[1] > 0)));
});

test("a fund with nothing priced does not move the grid's start", () => {
  const a = series([["2025-10-03", "10"], ["2025-10-27", "12"]]);
  const later = series([["2025-10-20", "10"], ["2025-10-27", "12"]]);
  const got = M.pathsOf([{ date: "2025-10-03", paise: 100000 }], [a, later], "2025-10-27", "week");
  assert.equal(got.grid[0], "2025-10-05");
});

test("a weekly grid from a Sunday starts on that Sunday", () => {
  assert.deepEqual(M.gridOf("2025-10-05", "2025-10-17", "week"), ["2025-10-05", "2025-10-12", "2025-10-17"]);
});

// --- the shared fixture ---------------------------------------------------------------
for (const c of cases) {
  test(`fixture: ${c.name}`, () => {
    const s = seriesOf(c.funds);
    const v = M.valuationDate(s);
    assert.equal(v.valuedOn, c.expect.valued_on);
    assert.deepEqual(v.stale, c.expect.stale);
    const w = M.windowOf({ mode: c.mode, amountPaise: M.toPaise(c.amount), years: c.years || null,
                           from: c.from || null, day: c.day }, v.valuedOn);
    assert.deepEqual({ first: w.first, last: w.last, count: w.count }, c.expect.window);
    const pool = M.poolOf(c.funds, s, w, v.valuedOn);
    assert.deepEqual(pool.inRange.map((f) => f.id), c.expect.in_range);
    assert.deepEqual(pool.out.map((o) => [o.fund.id, o.reason]), c.expect.out);
    // Every fund once: in the range, or out of it with its reason (§4.4).
    assert.equal(pool.inRange.length + pool.out.length,
      c.funds.filter((f) => f.plan !== "regular").length);
    const outcomes = pool.inRange.map((f) => Object.assign({ fund: f }, M.outcome(w.buys, s.get(f.id), v.valuedOn)));
    for (const o of outcomes) {
      const want = c.expect.outcomes[o.fund.id];
      assert.equal(o.valuePaise, Math.round(Number(want.value) * 100), o.fund.id);
      assert.equal(o.investedPaise, Math.round(Number(c.expect.put_in) * 100), o.fund.id);
      assert.equal(o.xirr.toFixed(8), want.xirr, o.fund.id);
      assert.equal(o.low.toFixed(8), want.low, o.fund.id);
      assert.equal(o.lowOn, want.low_on, o.fund.id);
    }
    const r = M.spread(outcomes);
    assert.deepEqual({ n: r.n, min: r.min.fund.id, middle: r.middle.fund.id, max: r.max.fund.id,
                       below_ever: r.belowEver }, c.expect.spread);
  });
}

// --- the address (§4.7) ---------------------------------------------------------------
const S = createRequire(import.meta.url)("../../src/m6_views/static/sip.js");
const DEFAULT = { a: "5000", m: "sip", y: 5, from: null, d: 5, c: null, f: [] };

test("no hash is the default view", () => {
  assert.deepEqual(S.parseHash(""), { state: DEFAULT, notes: [] });
});

test("a full hash reads back what wrote it", () => {
  const state = { a: "100000", m: "once", y: null, from: "2019-04-01", d: 5,
                  c: "debt/corporate_bond", f: ["INF879O01027", "INF179K01XQ0"] };
  assert.deepEqual(S.parseHash(S.writeHash(state)), { state, notes: [] });
  assert.equal(S.writeHash(Object.assign({}, DEFAULT, { c: "equity/large_cap" })),
    "#a=5000&m=sip&y=5&d=5&c=equity/large_cap");
});

test("what cannot be read falls back, and an unreadable amount says so", () => {
  const got = S.parseHash("#a=5k&m=weekly&y=7&d=40&f=nope,INF879O01027,INF879O01027,A,B");
  assert.deepEqual(got.state, Object.assign({}, DEFAULT, { f: ["INF879O01027"] }));
  assert.deepEqual(got.notes, ["amount"]);
  // A start of the wrong shape for its mode is the 5 years.
  assert.equal(S.parseHash("#m=sip&from=2019-04-01").state.y, 5);
  assert.equal(S.parseHash("#m=once&from=2019-04").state.y, 5);
  assert.equal(S.parseHash("#m=sip&from=2019-04").state.from, "2019-04");
  assert.equal(S.parseHash("#f=" + ["INF879O01027", "INF179K01XQ0", "INF179K01UT0", "INF200K01QX4"].join(",")).state.f.length, 3);
});

test("the path starts when the first purchase is priced, not on a holiday before it", () => {
  // 5 Oct 2025 is a Sunday: the first instalment is priced on Monday the 6th.
  const s = series([["2025-10-03", "9"], ["2025-10-06", "10"], ["2025-10-10", "11"], ["2025-10-17", "12"]]);
  const p = M.pathsOf([{ date: "2025-10-05", paise: 100000 }], [s], "2025-10-17", "week").paths[0];
  assert.ok(p.points.every((x) => x[1] > 0), JSON.stringify(p.points));
  assert.equal(p.points[0][0], "2025-10-12");
});

// §5.1.3: the overview's figures are the build's, for ₹1,000 a month (₹1,00,000
// once), scaled to the amount and rounded to the nearest ₹100.
test("an overview figure is scaled to the amount and rounded to ₹100", () => {
  assert.equal(S.scaled("73465.61", "1000.00", 500000), 36730000);       // ₹5,000: ₹3,67,328.05
  assert.equal(S.scaled("73465.61", "1000.00", 100000), 7350000);        // ₹1,000 itself
  assert.equal(S.scaled("100049.99", "100000.00", 100000000), 100050000); // ₹10 lakh once
  assert.equal(S.scaled("1000.50", "1000.00", 10000000), 10010000);      // ₹1 lakh: ₹1,00,050 rounds up
});

// --- Part C (§6.2): a holding against every other fund of its kind --------------------
test("ordinals are worked out, not templated", () => {
  assert.deepEqual([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111, 112].map(M.ordinal),
    ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th", "112th"]);
});

// ₹1,000 on 5 Jan 2024 at NAV 10 (₹0.05 stamp duty: 99.995 units), ₹600 sold on 5 Mar.
// By hand, valued on 5 Apr: A 59.995 × 15 = ₹899.93; B 45.450 × 11 = ₹499.95;
// C 33.328 × 9 = ₹299.95; yours (H) 49.995 × 12 = ₹599.94, so 2nd of 4. F's NAV halved,
// so ₹600 needed 120 units it never had; D began after the purchase; E did not load.
const D = ["2024-01-05", "2024-02-05", "2024-03-05", "2024-04-05"];
const kindOf = [
  { id: "H", navs: ["10", "10", "12", "12"] }, { id: "A", navs: ["10", "10", "15", "15"] },
  { id: "B", navs: ["10", "10", "11", "11"] }, { id: "C", navs: ["10", "10", "9", "9"] },
  { id: "F", navs: ["10", "10", "5", "5"] }, { id: "D", navs: null, from: 1 }, { id: "E", navs: null },
];
const kindSeries = new Map(kindOf.map((f) => [f.id, f.navs ? series(f.navs.map((v, i) => [D[i], v]))
  : f.from ? series([["2024-02-05", "10"], ["2024-03-05", "12"], ["2024-04-05", "12"]]) : null]));
const buys = [{ date: D[0], paise: 100000 }];
const sold = [{ date: D[2], paise: 60000 }];

test("a holding's own purchases and sales, in every other fund of its kind", () => {
  const a = M.against(buys, sold, { id: "H" }, kindOf, kindSeries);
  assert.equal(a.valuedOn, D[3]);
  assert.deepEqual(a.r.sorted.map((o) => [o.fund.id, o.valuePaise]), [["C", 29995], ["B", 49995], ["A", 89993]]);
  assert.equal(a.r.middle.fund.id, "B");
  assert.deepEqual(a.out.map((o) => [o.fund.id, o.reason]), [["F", "sales"], ["D", "later"], ["E", "load"]]);
  assert.equal(a.yours.valuePaise, 59994);
  assert.equal(a.rank, 2);
  assert.equal(a.r.n + 1, 4);
  // Every other fund of the kind is in the range or out of it, once (§4.4).
  assert.deepEqual([...a.r.sorted.map((o) => o.fund.id), ...a.out.map((o) => o.fund.id)].sort(),
    ["A", "B", "C", "D", "E", "F"]);
});

test("a Regular holding is set against Direct funds, never its own Direct plan", () => {
  const regular = { id: "HR", plan: "regular", direct: "H" };
  const withOwn = new Map(kindSeries).set("HR", kindSeries.get("H"));
  const a = M.against(buys, sold, regular, kindOf, withOwn);
  assert.ok(!a.r.sorted.some((o) => o.fund.id === "H") && !a.out.some((o) => o.fund.id === "H"));
  assert.equal(a.yours.valuePaise, 59994);
});

test("with no sales the lowest point is worked out; with sales it is not stated", () => {
  const bought = M.against(buys, [], { id: "H" }, kindOf, kindSeries);
  // On 5 Feb the NAV is still 10: ₹999.95 against ₹1,000, the stamp duty below.
  assert.equal(bought.yours.low, -0.00005);
  assert.equal(bought.yours.lowOn, D[1]);
  assert.equal(bought.out.length, 2);    // F can hold its units now: only D and E are out
  assert.equal(M.against(buys, sold, { id: "H" }, kindOf, kindSeries).yours.low, null);
});

// Flows after V (review, Important 2). H, O1 and O2 are priced to 3 Oct 2025, O3 to the
// 2nd, so the kind is valued on 2 Oct. A purchase and a sale on 3 Oct are priced by no
// fund on that date: they are left out of every fund alike, and said so.
const priced = (dates, nav) => series(dates.map((d) => [d, nav]));
const lateDays = ["2024-12-31", "2025-01-02", "2025-06-02", "2025-10-01", "2025-10-02", "2025-10-03"];
const lateKind = [{ id: "H" }, { id: "O1" }, { id: "O2" }, { id: "O3" }];
const lateSeries = new Map([["H", priced(lateDays, "10")], ["O1", priced(lateDays, "11")],
  ["O2", priced(lateDays, "12")], ["O3", priced(lateDays.slice(0, -1), "13")]]);
const lateBuys = [{ date: "2025-01-02", paise: 1000000 }, { date: "2025-10-03", paise: 1000000 }];

test("a sale after V puts no fund out of the range; it is counted as left out", () => {
  const a = M.against(lateBuys, [{ date: "2025-10-03", paise: 50000 }], { id: "H" }, lateKind, lateSeries);
  assert.equal(a.valuedOn, "2025-10-02");
  assert.equal(a.r.n, 3);
  assert.ok(!a.out.some((o) => o.reason === "sales"), JSON.stringify(a.out));
  assert.deepEqual(a.after, { buys: 1, sales: 1 });
});

test("what was put in is what was priced by V", () => {
  const a = M.against(lateBuys, [], { id: "H" }, lateKind, lateSeries);
  assert.equal(a.putPaise, 1000000);
  assert.ok(a.r.sorted.every((o) => o.investedPaise === 1000000));
});

test("the stale floor counts the holding's own prices", () => {
  // H runs to 20 Oct; O1 and O2 stop on the 10th and 12th: more than 7 days behind.
  const days = (last) => ["2025-01-01", "2025-06-02", last];
  const s = new Map([["H", priced(days("2025-10-20"), "10")], ["O1", priced(days("2025-10-10"), "11")],
    ["O2", priced(days("2025-10-12"), "12")]]);
  const a = M.against([{ date: "2025-06-02", paise: 100000 }], [], { id: "H" }, [{ id: "H" }, { id: "O1" }, { id: "O2" }], s);
  assert.equal(a.valuedOn, "2025-10-20");
  assert.deepEqual(a.out.map((o) => [o.fund.id, o.reason]), [["O1", "stale"], ["O2", "stale"]]);
});

test("a holding whose prices stopped is valued on its own last date", () => {
  const days = (last) => ["2025-01-01", "2025-06-02", last];
  const s = new Map([["H", priced(days("2025-10-01"), "10")], ["O1", priced(days("2025-10-20"), "11")],
    ["O2", priced(days("2025-10-20"), "12")]]);
  const a = M.against([{ date: "2025-06-02", paise: 100000 }], [], { id: "H" }, [{ id: "H" }, { id: "O1" }, { id: "O2" }], s);
  assert.equal(a.valuedOn, "2025-10-20");
  assert.equal(a.yours.valuedOn, "2025-10-01");
});

test("a holding bought only after V is not a failed load: nothing is priced yet", () => {
  const a = M.against([{ date: "2025-10-03", paise: 100000 }], [], { id: "H" }, lateKind, lateSeries);
  assert.equal(a.valuedOn, "2025-10-02");
  assert.deepEqual(a.after, { buys: 1, sales: 0 });
  assert.equal(a.yours, null);
  assert.equal(a.r.n, 0);
});

// The amount field (review, Important 3 and Minor 18): what is typed is read, never
// rounded; what cannot be read keeps the last amount and says why.
test("an amount is read as whole rupees, or kept with a reason", () => {
  assert.deepEqual(S.readAmount("12,345", "5000"), { a: "12345", error: null });
  assert.deepEqual(S.readAmount("₹ 5,000", "100"), { a: "5000", error: null });
  assert.deepEqual(S.readAmount("", "5000"), { a: "5000", error: "empty" });
  assert.deepEqual(S.readAmount("0", "5000"), { a: "5000", error: "empty" });
  assert.deepEqual(S.readAmount("abc", "5000"), { a: "5000", error: "empty" });
  assert.deepEqual(S.readAmount("5000.50", "5000"), { a: "5000", error: "paise" });
  assert.deepEqual(S.readAmount("10,00,00,000", "5000"), { a: "100000000", error: null });
  assert.deepEqual(S.readAmount("10,00,00,001", "5000"), { a: "5000", error: "cap" });
  assert.equal(S.SIP_MAX_RUPEES * 100, M.SIP_MAX_PAISE);
});

test("a link's amount over ₹10 crore is not read, and the page says so", () => {
  const over = S.parseHash("#a=200000000");
  assert.equal(over.state.a, "5000");
  assert.deepEqual(over.notes, ["amount"]);
  assert.equal(S.parseHash("#a=100000000").state.a, "100000000");
});

// Chart 2's dots (review, Minor 6): one a fund. A fund added by name that is already
// in the range (a fund page's link adds the fund itself) marks its own dot.
test("an added fund in the range is one dot, named", () => {
  const outs = ["A", "B", "C"].map((id, i) => ({ fund: { id, name: "Fund " + id }, valuePaise: (i + 1) * 1000 }));
  const r = M.spread(outs);
  const added = S.pointsOf({ r, idx: null, marked: [{ o: outs[0], label: "Fund A", hue: 2 }] });
  assert.equal(added.length, 3);
  assert.deepEqual(added.filter((p) => p.mark === "added").map((p) => [p.o.fund.id, p.name, p.hue]), [["A", "Fund A", 2]]);
  // Yours (Part C) is never one of the others: one more dot.
  const yours = { fund: { id: "H", name: "Mine" }, valuePaise: 1500 };
  assert.equal(S.pointsOf({ r, idx: null, marked: [{ o: yours, label: "Yours", hue: 2 }] }).length, 4);
});

// A fall too small for one decimal (review, Minor 11) is not "0.0% below".
test("a fall reads to one decimal, or as less than 0.1%", () => {
  assert.equal(S.fallText(-0.0123), "1.2%");
  assert.equal(S.fallText(-0.0005), "0.1%");
  assert.equal(S.fallText(-0.00049), "less than 0.1%");
  assert.equal(S.fallText(-0.00004), "less than 0.1%");
});

// An index or added fund beside the range (review, Minor 15): valued on V or not at
// all, never on an earlier date under V's name.
test("a fund beside the range needs a price from the first purchase to V", () => {
  const s = series([["2024-01-02", "10"], ["2024-06-03", "11"], ["2024-09-20", "12"]]);
  assert.equal(M.eligibleOn(s, "2024-01-05", "2024-09-20"), null);
  assert.equal(M.eligibleOn(s, "2024-01-05", "2024-09-24"), "stale");
  assert.equal(M.eligibleOn(s, "2023-12-05", "2024-09-20"), "later");
  assert.equal(M.eligibleOn(null, "2024-01-05", "2024-09-20"), "load");
});
