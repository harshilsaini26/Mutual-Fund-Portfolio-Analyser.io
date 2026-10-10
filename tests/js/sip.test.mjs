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
  const p = M.pathOf(buys, s, "2024-03-05", "month");
  assert.deepEqual(p.points.map((x) => x[0]), ["2024-01-31", "2024-02-29", "2024-03-05"]);
  assert.equal(p.points[0][1], 109995);   // 99.995 units x 11 = 1,099.945 -> half up
  assert.deepEqual(p.putIn, [["2024-01-05", 100000], ["2024-02-05", 200000], ["2024-03-05", 200000]]);
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
  const p = M.pathOf([{ date: "2025-10-05", paise: 100000 }], s, "2025-10-17", "week");
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
