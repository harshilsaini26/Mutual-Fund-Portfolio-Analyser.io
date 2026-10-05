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


// Just enough of a document for `K.table`: elements with attributes and children.
function fakeDocument() {
  const node = (tag) => ({
    tagName: tag.toUpperCase(), attributes: {}, childNodes: [], nodeType: 1,
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; },
    appendChild(c) { this.childNodes.push(c); return c; },
    get textContent() { return this.childNodes.map((c) => c.textContent).join(""); },
  });
  return { createElement: node, createTextNode: (t) => ({ nodeType: 3, textContent: t }) };
}
const kids = (n, tag) => n.childNodes.filter((c) => c.tagName === tag);

test("a table is a region named by its own caption, ready for a phone's cards", () => {
  globalThis.document = fakeDocument();
  try {
    const wrap = K.table("Your funds", ["Fund", "Worth", ""], [["A fund", "₹1,000", "x"]],
                         { numeric: [0, 1, 0] });
    const [tbl] = kids(wrap, "TABLE");
    const [caption] = kids(tbl, "CAPTION");
    assert.equal(wrap.getAttribute("class"), "table-wrap");
    assert.equal(wrap.getAttribute("role"), "region");
    assert.equal(wrap.getAttribute("aria-labelledby"), caption.getAttribute("id"));
    assert.equal(caption.textContent, "Your funds");
    assert.equal(tbl.getAttribute("class"), "table--stack");
    const [row] = kids(kids(tbl, "TBODY")[0], "TR");
    const [name, worth, last] = row.childNodes;
    assert.equal(name.getAttribute("data-label"), "Fund");
    assert.equal(worth.getAttribute("data-label"), "Worth");
    assert.equal(worth.getAttribute("class"), "num");
    assert.equal(last.getAttribute("data-label"), null);   // no heading, no label
    const again = K.table("Your funds", ["Fund"], [], {});
    assert.notEqual(again.getAttribute("aria-labelledby"), wrap.getAttribute("aria-labelledby"));
  } finally { delete globalThis.document; }
});

test("a table can head each row and name its columns other than by their text", () => {
  globalThis.document = fakeDocument();
  try {
    const link = document.createElement("a");
    link.appendChild(document.createTextNode("Fund B×"));
    const tag = document.createElement("span");
    tag.appendChild(document.createTextNode("lowest here"));
    const wrap = K.table("Key facts", ["", link], [["Expense ratio", ["0.77%", tag, null]]],
                         { rowHead: true, labels: ["", "Fund B"], stack: false });
    const [tbl] = kids(wrap, "TABLE");
    assert.equal(tbl.getAttribute("class"), null);
    const [row] = kids(kids(tbl, "TBODY")[0], "TR");
    assert.equal(row.childNodes[0].tagName, "TH");
    assert.equal(row.childNodes[0].getAttribute("scope"), "row");
    assert.equal(row.childNodes[1].getAttribute("data-label"), "Fund B");
    assert.equal(row.childNodes[1].textContent, "0.77%lowest here");   // a cell of parts
    const own = K.table("Key facts", ["", "Fund B"], [], { cls: "cmp__table" });
    assert.equal(kids(own, "TABLE")[0].getAttribute("class"), "cmp__table table--stack");
  } finally { delete globalThis.document; }
});

// The picker's matching (UI/UX critique C-01), over funds.json-shaped records.
const PICK = [
  { id: "INF879O01027", name: "Parag Parikh Flexi Cap Fund", house: "PPFAS Mutual Fund", category_name: "Flexi cap" },
  { id: "INF179K01UT0", name: "HDFC Flexi Cap Fund", house: "HDFC Mutual Fund", category_name: "Flexi cap" },
  { id: "INF179K01XQ0", name: "HDFC Mid Cap Fund", house: "HDFC Mutual Fund", category_name: "Mid cap" },
  { id: "INF200K01QX4", name: "SBI Small Cap Fund", house: "SBI Mutual Fund", category_name: "Small cap" },
  { id: "INF179K01UT1", name: "HDFC Flexi Cap Fund (Regular)", house: "HDFC Mutual Fund", category_name: "Flexi cap" },
];
const names = (hits) => hits.map((f) => f.name);

test("every word typed must match, in any order: 'parag flexi' finds Parag Parikh", () => {
  assert.deepEqual(names(K.match(PICK, "parag flexi")), ["Parag Parikh Flexi Cap Fund"]);
  assert.deepEqual(names(K.match(PICK, "flexi parag")), ["Parag Parikh Flexi Cap Fund"]);
});

test("a fund house finds its funds, an abbreviation its fund: 'ppfas', 'ppfcf'", () => {
  assert.deepEqual(names(K.match(PICK, "ppfas")), ["Parag Parikh Flexi Cap Fund"]);
  assert.deepEqual(names(K.match(PICK, "ppfcf")), ["Parag Parikh Flexi Cap Fund"]);
  assert.deepEqual(names(K.match(PICK, "hdfc mid")), ["HDFC Mid Cap Fund"]);
});

test("an ISIN, or its first part, finds its fund", () => {
  assert.deepEqual(names(K.match(PICK, "INF200K01QX4")), ["SBI Small Cap Fund"]);
  assert.deepEqual(names(K.match(PICK, "inf879o")), ["Parag Parikh Flexi Cap Fund"]);
});

test("matches in the name come first, then a name starting with the first word, then shorter", () => {
  // "flexi": three names hold it; HDFC's Direct plan is shorter than its Regular one.
  assert.deepEqual(names(K.match(PICK, "flexi")),
    ["HDFC Flexi Cap Fund", "Parag Parikh Flexi Cap Fund", "HDFC Flexi Cap Fund (Regular)"]);
  // "hdfc": all three start with it; then the shorter.
  assert.deepEqual(names(K.match(PICK, "hdfc")).slice(0, 2), ["HDFC Mid Cap Fund", "HDFC Flexi Cap Fund"]);
  // "cap" matches every name; "small cap" only the one.
  assert.deepEqual(names(K.match(PICK, "small cap")), ["SBI Small Cap Fund"]);
});

test("nothing typed, nothing that matches, and a limit: what the picker shows", () => {
  assert.deepEqual(K.match(PICK, "  "), []);
  assert.deepEqual(K.match(PICK, "axis"), []);
  assert.equal(K.match(PICK, "fund", 2).length, 2);
});
