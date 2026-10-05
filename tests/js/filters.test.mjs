// app.js: the Explore funds filters in the address. DECISIONS V1-88.
// Run: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const A = createRequire(import.meta.url)("../../src/m6_views/static/app.js");

test("filterHash and parseFilterHash round-trip", () => {
  const state = { category: "equity/flexi_cap", family: "equity", q: "hdfc top" };
  const hash = A.filterHash(state);
  assert.equal(hash, "#category=equity%2Fflexi_cap&family=equity&q=hdfc%20top");
  assert.deepEqual(A.parseFilterHash(hash), state);
});

test("an empty state is no hash", () => {
  assert.equal(A.filterHash({ category: "", family: "", q: "" }), "");
  assert.deepEqual(A.parseFilterHash(""), { category: "", family: "", q: "" });
});

test("only what is set is written", () => {
  assert.equal(A.filterHash({ category: "", family: "debt", q: "" }), "#family=debt");
});

test("parseFilterHash ignores what it cannot use", () => {
  // Validity against the select's options is the page's job; a broken escape,
  // an unknown key and a repeated key are this function's.
  assert.deepEqual(A.parseFilterHash("#category=nope&family=%E0&x=1&q=a&q=b"),
    { category: "nope", family: "", q: "a" });
});

test("the front page's old links still parse", () => {
  assert.deepEqual(A.parseFilterHash("#category=equity/elss"),
    { category: "equity/elss", family: "", q: "" });
});

test("only a hash that names a filter is a filter hash", () => {
  // "#content" is the skip link's target; following it must leave the filters alone.
  assert.equal(A.isFilterHash("#content"), false);
  assert.equal(A.isFilterHash(""), false);
  assert.equal(A.isFilterHash("#family=equity"), true);
  assert.equal(A.isFilterHash("#x=1&q=a"), true);
});

test("on load the hash wins and ?q= only fills a missing q", () => {
  assert.deepEqual(A.initialFilters("?q=hdfc", "#family=hybrid&q=axis"),
    { category: "", family: "hybrid", q: "axis" });
  assert.deepEqual(A.initialFilters("?q=hdfc+top", "#family=hybrid"),
    { category: "", family: "hybrid", q: "hdfc top" });
  assert.deepEqual(A.initialFilters("?q=hdfc", "#content"),
    { category: "", family: "", q: "hdfc" });
  assert.deepEqual(A.initialFilters("?q=%E0", ""), { category: "", family: "", q: "" });
});

test("later runs once, when the calls pause", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const got = [];
  const f = A.later((x) => got.push(x), 250);
  f("h"); f("hd"); f("hdfc");
  t.mock.timers.tick(249);
  assert.deepEqual(got, []);
  t.mock.timers.tick(1);
  assert.deepEqual(got, ["hdfc"]);
});

test("the filters write the address through later", async () => {
  // Safari refuses replaceState after ~100 calls in a short window: one per key is too many.
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../../src/m6_views/static/app.js", import.meta.url), "utf-8");
  assert.equal(src.match(/history\.replaceState/g).length, 1);
  assert.match(src, /later\(function \(hash\) \{\s*history\.replaceState/);
});

test("a submitted search goes in the fragment, which is never sent", () => {
  assert.equal(A.searchTarget("/funds/", " hdfc top "), "/funds/#q=hdfc%20top");
  assert.equal(A.searchTarget("/Repo/funds/", ""), "/Repo/funds/");
  assert.equal(A.searchTarget("https://x.test/funds/?q=old#family=debt", "axis"),
    "https://x.test/funds/#q=axis");
});

// Explore funds from funds/rows.json (UI/UX critique E-01 to E-03): `c` holds each
// column's [value, label, ...]; a value "" is a fund with no figure.
const ROWS = [
  { id: "A", name: "Alpha Flexi Cap Fund", family: "equity", cat: "equity/flexi_cap", cat_name: "Flexi cap",
    c: { size: ["900", "₹900 Cr"], r3: ["0.12", "+12.0%"] } },
  { id: "B", name: "Beta Flexi Cap Fund", family: "equity", cat: "equity/flexi_cap", cat_name: "Flexi cap",
    c: { size: ["", "—"], r3: ["0.18", "+18.0%"] } },
  { id: "C", name: "Gamma Liquid Fund", family: "debt", cat: "debt/liquid", cat_name: "Liquid",
    c: { size: ["5000", "₹5,000 Cr"], r3: ["", "—"] } },
  { id: "D", name: "Delta Small Cap Fund", family: "equity", cat: "equity/small_cap", cat_name: "Small cap",
    c: { size: ["300", "₹300 Cr"], r3: ["0.25", "+25.0%"] } },
];
const ids = (rows) => rows.map((r) => r.id);

test("Explore's first view is every fund, the largest first, one with no size last", () => {
  assert.deepEqual(ids(A.exploreRows(ROWS, {})), ["C", "A", "D", "B"]);
});

test("a column sorts either way on its figure, a fund without one last both times", () => {
  assert.deepEqual(ids(A.exploreRows(ROWS, { sort: "r3", dir: "desc" })), ["D", "B", "A", "C"]);
  assert.deepEqual(ids(A.exploreRows(ROWS, { sort: "r3", dir: "asc" })), ["A", "B", "D", "C"]);
  assert.deepEqual(ids(A.exploreRows(ROWS, { sort: "name", dir: "asc" })), ["A", "B", "D", "C"]);
});

test("the filters narrow together: family, category and the words of a name", () => {
  assert.deepEqual(ids(A.exploreRows(ROWS, { family: "equity" })), ["A", "D", "B"]);
  assert.deepEqual(ids(A.exploreRows(ROWS, { family: "equity", category: "equity/flexi_cap" })), ["A", "B"]);
  assert.deepEqual(ids(A.exploreRows(ROWS, { q: "flexi beta" })), ["B"]);
  assert.deepEqual(A.exploreRows(ROWS, { family: "debt", category: "equity/flexi_cap" }), []);
});

test("each family's count, and each category's within the family chosen", () => {
  const all = A.exploreCounts(ROWS, "");
  assert.deepEqual(all.families, { equity: 3, debt: 1 });
  assert.deepEqual(all.categories, { "equity/flexi_cap": 2, "debt/liquid": 1, "equity/small_cap": 1 });
  assert.deepEqual(A.exploreCounts(ROWS, "equity").categories, { "equity/flexi_cap": 2, "equity/small_cap": 1 });
});
