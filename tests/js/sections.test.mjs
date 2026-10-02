// sections.js: which section of a fund page is current. DECISIONS V1-84.
// Run: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const S = createRequire(import.meta.url)("../../src/m6_views/static/sections.js");

const TOPS = [{ id: "a", top: 0 }, { id: "b", top: 1000 }, { id: "c", top: 2500 }];
test("before the first panel is reached, the first is current", () => {
  assert.equal(S.currentSection([{ id: "a", top: 300 }, { id: "b", top: 900 }], 0, 120, false), "a");
});
test("between panels, the last one passed is current", () => {
  assert.equal(S.currentSection(TOPS, 1500, 120, false), "b");
});
test("a panel whose top meets the offset is current", () => {
  assert.equal(S.currentSection(TOPS, 880, 120, false), "b");
  assert.equal(S.currentSection(TOPS, 879, 120, false), "a");
});
test("at the bottom of the page the last panel is current", () => {
  assert.equal(S.currentSection(TOPS, 1200, 120, true), "c");
});
test("no panels, no current section", () => {
  assert.equal(S.currentSection([], 0, 120, false), null);
});

// On a wide screen Returns and Consistency share a row (dense grid), so their tops
// are equal and Consistency's comes before Peers' and Falls' in page order.
const WIDE = [
  { id: "fund_header", top: 0 }, { id: "fund_performance", top: 1000 },
  { id: "fund_growth", top: 2000 }, { id: "fund_nav", top: 3000 },
  { id: "fund_returns", top: 4000 }, { id: "fund_peers", top: 5000 },
  { id: "fund_drawdown", top: 6000 }, { id: "fund_consistency", top: 4000 },
  { id: "fund_portfolio", top: 7000 },
];
test("panels sharing a row: the first in page order stands for it", () => {
  assert.equal(S.currentSection(WIDE, 4100, 0, false), "fund_returns");
});
test("a later panel is current once passed, whatever shares an earlier row", () => {
  assert.equal(S.currentSection(WIDE, 5100, 0, false), "fund_peers");
  assert.equal(S.currentSection(WIDE, 6100, 0, false), "fund_drawdown");
});
