// Screenshots of the public site, for the README and the tour video (DECISIONS V1-90).
//
// Drives an installed Chrome through its DevTools protocol with Node's own WebSocket,
// so it needs no packages. Light theme and reduced motion: every scroll-built picture
// is captured finished. The portfolio page is shown with an example entry written to
// that page's own browser storage, as a visitor would type it.
//
//   node scripts/capture.mjs [base-url]      (default: the published site)
//
// Writes public/shots/*.png.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = (process.argv[2] ||
  "https://didmysipwork.vercel.app").replace(/\/$/, "");
const OUT = fileURLToPath(new URL("../public/shots/", import.meta.url));
const PORT = 9333;
const CHROME = [
  process.env.CHROME,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
].find((p) => p && existsSync(p));
if (!CHROME) throw new Error("No Chrome or Edge found; set CHROME to its path.");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** The fund ids to show, found by name in the site's own list. */
async function pickFunds() {
  const funds = await (await fetch(`${BASE}/funds.json`)).json();
  const find = (re) => funds.find((f) => re.test(f.name));
  const named = [/^HDFC Flexi Cap/i, /^Parag Parikh Flexi Cap/i, /^Nippon India Growth/i]
    .map(find).filter(Boolean);
  const bySize = funds.filter((f) => f.size && f.category?.startsWith("equity/"))
    .sort((a, b) => Number(b.size) - Number(a.size));
  for (const f of bySize) if (named.length < 3 && !named.includes(f)) named.push(f);
  return named.map((f) => f.id);
}

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = pages.find((p) => p.type === "page");
      if (page) return new WebSocket(page.webSocketDebuggerUrl);
    } catch { /* not up yet */ }
    await sleep(200);
  }
  throw new Error("Chrome did not open its debugging port.");
}

const profile = mkdtempSync(join(tmpdir(), "lt-shots-"));
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "about:blank",
], { stdio: "ignore" });

try {
  const ws = await connect();
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  let next = 0;
  const waiting = new Map();
  ws.addEventListener("message", (e) => {
    const msg = JSON.parse(e.data);
    if (msg.id && waiting.has(msg.id)) {
      waiting.get(msg.id)(msg);
      waiting.delete(msg.id);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++next;
    waiting.set(id, (msg) => (msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)));
    ws.send(JSON.stringify({ id, method, params }));
  });
  const run = (expression) => send("Runtime.evaluate", { expression, awaitPromise: true });

  await send("Page.enable");
  await send("Emulation.setEmulatedMedia", { features: [
    { name: "prefers-color-scheme", value: "light" },
    { name: "prefers-reduced-motion", value: "reduce" },
  ] });

  // `steps` run in order on the loaded page, each followed by a settle (a step may reload).
  async function shot(name, path, { width = 1440, height = 900, mobile = false, settle = 2500,
    steps = [] } = {}) {
    await send("Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: mobile ? 2 : 1, mobile });
    await send("Page.navigate", { url: `${BASE}${path}` });
    await sleep(settle);
    for (const step of steps) { await run(step); await sleep(settle); }
    const { data } = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(OUT, `${name}.png`), Buffer.from(data, "base64"));
    console.log(`  ${name}.png  ${path}`);
  }

  mkdirSync(OUT, { recursive: true });
  const [a, b, c] = await pickFunds();
  const example = JSON.stringify({ version: 1, funds: [
    { id: a, purchases: [], sips: [{ amount: "10000", day: 5, start: "2021-01", stop: null }],
      alts: [null, null, null] },
    { id: b, purchases: [{ date: "2022-06-15", amount: "200000" }], sips: [],
      alts: [null, null, null] },
  ] });

  await shot("home", "/");
  const scrollTo = (id) => `document.getElementById('${id}').scrollIntoView()`;
  await shot("home-lookup", "/", { steps: [scrollTo("lookup")] });
  await shot("home-privacy", "/", { steps: [scrollTo("privacy")] });
  await shot("fund", `/fund/${a}/`, { settle: 4000 });
  await shot("funds", "/funds/", { settle: 4000 });
  await shot("compare", `/compare/#f=${a},${b},${c}`, { settle: 5000,
    steps: [scrollTo("cmp-growth-h")] });
  await shot("portfolio", "/portfolio/", { settle: 4000, steps: [
    `localStorage.setItem("lookthrough.portfolio.v1", ${JSON.stringify(example)}); location.reload()`,
    scrollTo("pf-look-h"),
  ] });
  await shot("learn", "/learn/");
  await shot("home-phone", "/", { width: 390, height: 844, mobile: true });
  ws.close();
} finally {
  chrome.kill();
  await sleep(500);
  rmSync(profile, { recursive: true, force: true });
}
