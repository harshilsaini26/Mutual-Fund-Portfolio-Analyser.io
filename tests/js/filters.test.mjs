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
