// node --test "tests/js/*.test.mjs" — the shared page helpers (kit.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const K = createRequire(import.meta.url)("../../src/m6_views/static/kit.js");

test("present keeps only what should be drawn: a count of nothing is not a child", () => {
  const node = { nodeType: 1 };
  assert.deepEqual(K.present([0, null, false, undefined, "", "a", node]), ["a", node]);
});

// A clock that moves only when told: timers run once `advance` passes their time.
function fakeClock() {
  let now = 0, next = 1;
  const timers = new Map();
  return {
    now: () => now,
    set: (fn, ms) => { const id = next++; timers.set(id, [now + ms, fn]); return id; },
    clear: (id) => { timers.delete(id); },
    advance(ms) {
      now += ms;
      for (const [id, [at, fn]] of [...timers]) if (at <= now) { timers.delete(id); fn(); }
    },
  };
}

test("a fuse runs its action once, when it burns out", () => {
  const clock = fakeClock();
  let runs = 0;
  const fuse = K.fuse(4000, () => runs++, clock);
  clock.advance(3999);
  assert.equal(runs, 0);
  assert.equal(fuse.remaining(), 1);
  clock.advance(1);
  assert.equal(runs, 1);
  clock.advance(10000);
  assert.equal(runs, 1);
  assert.equal(fuse.remaining(), 0);
});

test("undo before the end means the action never runs", () => {
  const clock = fakeClock();
  let runs = 0;
  const fuse = K.fuse(4000, () => runs++, clock);
  clock.advance(1500);
  assert.equal(fuse.remaining(), 2500);
  assert.equal(fuse.cancel(), true);
  clock.advance(10000);
  assert.equal(runs, 0);
  assert.equal(fuse.cancel(), false);   // nothing left to undo
});

test("with no clock given, a fuse calls the page's timers as browsers require", async () => {
  // A browser's setTimeout refuses to be called as another object's method.
  const real = globalThis.setTimeout;
  globalThis.setTimeout = function (fn, ms) {
    if (this !== undefined && this !== globalThis) throw new TypeError("Illegal invocation");
    return real(fn, ms);
  };
  try {
    let runs = 0;
    K.fuse(5, () => runs++);
    await new Promise((resolve) => real(resolve, 40));
    assert.equal(runs, 1);
  } finally {
    globalThis.setTimeout = real;
  }
});

