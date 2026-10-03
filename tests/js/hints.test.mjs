// app.js: where a hover explanation opens. DECISIONS V1-91.
// Run: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const A = createRequire(import.meta.url)("../../src/m6_views/static/app.js");
const label = (left, top, width = 120, height = 20) =>
  ({ left, top, right: left + width, bottom: top + height });

test("the card opens just under its label, aligned to its left edge", () => {
  assert.deepEqual(A.hintPlace(label(100, 200), 300, 120, 1440, 900), { left: 100, top: 228 });
});

test("near the bottom of the screen it opens above the label instead", () => {
  assert.deepEqual(A.hintPlace(label(100, 820), 300, 120, 1440, 900), { left: 100, top: 692 });
});

test("it never runs off the right edge, or the left", () => {
  assert.equal(A.hintPlace(label(1300, 200), 300, 120, 1440, 900).left, 1132);
  assert.equal(A.hintPlace(label(-40, 200), 300, 120, 1440, 900).left, 8);
});

test("with no room above or below it keeps to the top of the screen", () => {
  assert.equal(A.hintPlace(label(100, 100), 300, 700, 1440, 760).top, 8);
});
