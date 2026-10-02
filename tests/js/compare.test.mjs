// compare.js: choosing and comparing funds. DECISIONS V1-85.
// Run: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const C = createRequire(import.meta.url)("../../src/m6_views/static/compare.js");

test("parseHash cleans what people paste", () => {
  assert.deepEqual(C.parseHash("#f=inf179k01ut0, x ,INF179K01UT0,INF109K016L0,INF789F01XA0,INF0R8F01182,INF174KA1EZ1"),
    ["INF179K01UT0", "INF109K016L0", "INF789F01XA0", "INF0R8F01182"]);
  assert.deepEqual(C.parseHash(""), []);
  assert.deepEqual(C.parseHash("#other"), []);
});
test("writeHash round-trips", () => {
  assert.equal(C.writeHash(["A00000000001", "B00000000002"]), "#f=A00000000001,B00000000002");
  assert.equal(C.writeHash([]), "");
});
test("the shared start is the latest first price", () => {
  assert.equal(C.sharedStart([{ prices_from: "2013-01-01" }, { prices_from: "2019-03-12" }, { prices_from: null }]), "2019-03-12");
});
const S = { dates: ["2019-03-11", "2019-03-13", "2020-03-13"], navs: [100000000n, 50000000n, 75000000n] };
test("growthSeries starts at ₹10,000 on the first price from the start", () => {
  assert.deepEqual(C.growthSeries(S, "2019-03-12"), [["2019-03-13", 10000], ["2020-03-13", 15000]]);
});
test("growthSeries is empty when the start is after the last price", () => {
  assert.deepEqual(C.growthSeries(S, "2021-01-01"), []);
});
test("highLow tags the extremes and ties, and stays quiet otherwise", () => {
  assert.deepEqual(C.highLow([3, 1, 3, null]), ["highest", "lowest", "highest", null]);
  assert.deepEqual(C.highLow([2, 2]), [null, null]);
  assert.deepEqual(C.highLow([5, null]), [null, null]);
});
const LT = (holdings) => ({ as_of: "2026-08-31", aggregator: false, holdings, mix: [], sectors: [], sizes: [] });
test("commonHoldings lists companies held by two or more, by combined weight", () => {
  const files = {
    A: LT([["X", "Xco", "equity", "6"], ["Y", "Yco", "equity", "3"], ["__CASH__", "Cash", "cash", "9"]]),
    B: LT([["X", "Xco", "equity", "4"], ["Z", "Zco", "equity", "8"], ["__CASH__", "Cash", "cash", "9"]]),
    C: LT([["Y", "Yco", "equity", "1"]]),
  };
  assert.deepEqual(C.commonHoldings(files, ["A", "B", "C"]), [
    { issuer: "X", name: "Xco", weights: [6, 4, null], total: 10 },
    { issuer: "Y", name: "Yco", weights: [3, null, 1], total: 4 },
  ]);
});
test("commonHoldings is empty when nothing is shared", () => {
  assert.deepEqual(C.commonHoldings({ A: LT([["X", "Xco", "equity", "5"]]), B: null }, ["A", "B"]), []);
});
test("parseHash survives a broken escape in the address", () => {
  assert.deepEqual(C.parseHash("#f=%E0%A4%A,INF179K01UT0"), ["INF179K01UT0"]);
});

test("shownFigure reads the number a label shows", () => {
  assert.equal(C.shownFigure("₹1,01,793 Cr"), 101793);
  assert.equal(C.shownFigure("+15.4% p.a."), 15.4);
  assert.equal(C.shownFigure("-0.3% p.a."), -0.3);
  assert.equal(C.shownFigure("−4.0% p.a."), -4);
  assert.equal(C.shownFigure("0.71"), 0.71);
  assert.equal(C.shownFigure(null), null);
  // Two funds whose Sharpe ratios both show 0.71 tie, whatever lies beyond.
  assert.deepEqual(C.highLow(["0.71", "0.28", "0.71"].map(C.shownFigure)),
    ["highest", "lowest", "highest"]);
});

test("nextFocus goes to the column that took the removed one's place, else the last", () => {
  assert.equal(C.nextFocus(["A", "C"], 1), "C");   // B removed from A,B,C
  assert.equal(C.nextFocus(["A", "B"], 2), "B");   // C removed: the new last
  assert.equal(C.nextFocus([], 0), null);          // nothing left: the picker
});
