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

// A tiny element: a tag, its classes and children, its parent.
const node = (cls, ...children) => {
  const n = { nodeType: 1, cls, children, parentElement: null,
    classList: { contains: (c) => cls.split(" ").includes(c) } };
  children.forEach((c, i) => {
    c.parentElement = n;
    c.nextElementSibling = children[i + 1] || null;
  });
  n.firstElementChild = children[0] || null;
  return n;
};

test("the label of a `?` is found without :has(), which older browsers lack", () => {
  const term = node("term"), text = node("label-text");
  const label = node("fact__label", text, term);
  node("card", label);
  assert.equal(A.termHost(text), label);
  assert.equal(A.termHost(term), label);
  assert.equal(A.termHost(node("lonely")), null);
  assert.equal(A.termHost(null), null);
});

test("a figure that is not a number sorts as missing, last", () => {
  const row = (v) => ({ cells: [{ getAttribute: () => v, textContent: "" }] });
  assert.equal(A.sortKey(row("12.5"), 0, "number"), 12.5);
  assert.equal(A.sortKey(row("n/a"), 0, "number"), null);
  assert.equal(A.sortKey(row(""), 0, "number"), null);
});
