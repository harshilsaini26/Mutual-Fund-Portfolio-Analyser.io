// settings.js: stored choices and the device into five attributes. DECISIONS V1-83.
// Run: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const S = createRequire(import.meta.url)("../../src/m6_views/static/settings.js");

const LIGHT = { dark: false, reducedMotion: false };
const DARK_CALM = { dark: true, reducedMotion: true };
const memory = (init = {}) => { const m = new Map(Object.entries(init)); return {
  getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)),
  removeItem: (k) => m.delete(k), dump: () => Object.fromEntries(m) }; };
const throwing = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } };

test("defaults follow the device: Santorini by day, Midnight Neon by night", () => {
  assert.deepEqual(S.resolve(null, LIGHT), { theme: "santorini", font: "atkinson", size: "standard", density: "comfortable", motion: "on" });
  assert.deepEqual(S.resolve(null, DARK_CALM), { theme: "midnight", font: "atkinson", size: "standard", density: "comfortable", motion: "off" });
});
test("each stored value is honoured", () => {
  assert.deepEqual(S.resolve({ v: 1, theme: "heritage", font: "atkinson", size: "large", density: "compact", motion: "on" }, DARK_CALM),
    { theme: "heritage", font: "atkinson", size: "large", density: "compact", motion: "on" });
  for (const theme of ["santorini", "sky", "heritage", "crimson", "midnight", "matrix"]) {
    assert.equal(S.resolve({ v: 1, theme }, LIGHT).theme, theme);
  }
});
test("unknown values fall back one by one", () => {
  const r = S.resolve({ v: 1, font: "comic", size: "large" }, LIGHT);
  assert.equal(r.font, "atkinson"); assert.equal(r.size, "large");
});
test("device changes are followed only while the choice is device", () => {
  assert.equal(S.resolve({ v: 1, theme: "device" }, DARK_CALM).theme, "midnight");
  assert.equal(S.resolve({ v: 1, theme: "sky" }, DARK_CALM).theme, "sky");
  assert.equal(S.resolve({ v: 1, motion: "on" }, DARK_CALM).motion, "on");
});
test("a retired theme or accent follows the device instead", () => {
  assert.equal(S.resolve({ v: 1, theme: "light", accent: "violet" }, DARK_CALM).theme, "midnight");
  assert.equal(S.resolve({ v: 1, theme: "dark" }, LIGHT).theme, "santorini");
  assert.equal("accent" in S.resolve({ v: 1, accent: "violet" }, LIGHT), false);
});
test("a corrupted entry reads as nothing stored", () => {
  assert.deepEqual(S.read(memory({ settings: "{not json" })), { stored: null, ok: true });
  assert.deepEqual(S.read(memory({ settings: JSON.stringify({ v: 9, theme: "dark" }) })), { stored: null, ok: true });
});
test("the old theme key is migrated once", () => {
  const store = memory({ theme: "matrix" });
  assert.equal(S.read(store).stored.theme, "matrix");
  assert.equal(store.dump().theme, undefined);
  assert.equal(JSON.parse(store.dump().settings).theme, "matrix");
});
test("read and write survive a storage that throws", () => {
  assert.deepEqual(S.read(throwing), { stored: null, ok: false });
  assert.equal(S.write(throwing, { v: 1 }), false);
});
test("onStorage re-applies when another tab writes", () => {
  let n = 0; S.onStorage({ key: "settings" }, () => n++); S.onStorage({ key: "other" }, () => n++);
  assert.equal(n, 1);
});
test("each font has a preload file", () => {
  assert.equal(S.preloadFor("atkinson"), "fonts/atkinson-hyperlegible-latin-400-normal.woff2");
  assert.equal(S.preloadFor("nope"), S.preloadFor("atkinson"));
});
