// node --test "tests/js/*.test.mjs" — the shared page helpers (kit.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const K = createRequire(import.meta.url)("../../src/m6_views/static/kit.js");

test("present keeps only what should be drawn: a count of nothing is not a child", () => {
  const node = { nodeType: 1 };
  assert.deepEqual(K.present([0, null, false, undefined, "", "a", node]), ["a", node]);
});
