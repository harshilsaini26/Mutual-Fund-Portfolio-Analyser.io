/* The portfolio page's arithmetic. DECISIONS V1-82.
 *
 * Pure functions, no DOM: `portfolio.js` and `node --test tests/js/` load this
 * same file. Money is whole paise (Number); units are thousandths and NAVs
 * millionths of a rupee (BigInt) wherever they meet, so it rounds exactly where
 * the ledger rounds. The answers are pinned to M1's by
 * tests/fixtures/portfolio_cases.json.
 */
(function () {
  "use strict";

  var DUTY_FROM = "2020-07-01";      // stamp duty on purchases from this date
  var DAY_MS = 86400000;
  var ISIN = /^[A-Z0-9]{12}$/;
  var ISO = /^\d{4}-\d{2}-\d{2}$/;
  var MONTH = /^\d{4}-\d{2}$/;

  // Half-up division of non-negative BigInts.
  function roundDiv(n, d) { return (2n * n + d) / (2n * d); }

  function toPaise(text) {
    var s = String(text == null ? "" : text).replace(/[₹,\s]/g, "");
    var m = /^(\d{1,13})(?:\.(\d{1,2}))?$/.exec(s);
    if (!m) return null;
    var paise = Number(m[1]) * 100 + Number((m[2] || "").padEnd(2, "0"));
    return paise > 0 ? paise : null;
  }

  function toMicro(text) {
    var m = /^(\d+)(?:\.(\d{1,6}))?$/.exec(String(text).trim());
    if (!m) throw new Error("not a NAV: " + text);
    return BigInt(m[1]) * 1000000n + BigInt((m[2] || "").padEnd(6, "0"));
  }

  function parseNavFile(text) {
    var dates = [], navs = [];
    text.split("\n").forEach(function (line) {
      line = line.trim();
      if (!line || line.charAt(0) === "#") return;
      var parts = line.split(",");
      dates.push(parts[0]);
      navs.push(toMicro(parts[1]));
    });
    return { dates: dates, navs: navs };
  }

  // Index of the first NAV dated on or after `iso`, or -1.
  function onOrAfter(dates, iso) {
    var lo = 0, hi = dates.length;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (dates[mid] < iso) lo = mid + 1; else hi = mid;
    }
    return lo < dates.length ? lo : -1;
  }

  function allot(amountPaise, iso, series) {
    if (!series.dates.length || iso < series.dates[0]) return { error: "before" };
    var i = onOrAfter(series.dates, iso);
    if (i < 0) return { error: "pending" };
    var gross = BigInt(amountPaise);
    var duty = iso >= DUTY_FROM ? roundDiv(gross * 5n, 100000n) : 0n;
    return {
      navDate: series.dates[i],
      navMicro: series.navs[i],
      dutyPaise: Number(duty),
      unitsMilli: roundDiv((gross - duty) * 10000000n, series.navs[i]),
    };
  }

  function pad(n) { return String(n).padStart(2, "0"); }

  function sipDates(sip, todayIso) {
    var a = sip.start.split("-").map(Number);
    var b = (sip.stop || todayIso.slice(0, 7)).split("-").map(Number);
    var out = [];
    for (var y = a[0], m = a[1]; y < b[0] || (y === b[0] && m <= b[1]); ) {
      var last = new Date(Date.UTC(y, m, 0)).getUTCDate();
      var iso = y + "-" + pad(m) + "-" + pad(Math.min(sip.day, last));
      if (iso <= todayIso) out.push(iso);
      if (m === 12) { y += 1; m = 1; } else { m += 1; }
    }
    return out;
  }

  function purchasesOf(holding, todayIso) {
    var out = (holding.purchases || []).map(function (p) {
      return { date: p.date, paise: toPaise(p.amount) };
    });
    (holding.sips || []).forEach(function (s) {
      var paise = toPaise(s.amount);
      sipDates(s, todayIso).forEach(function (d) { out.push({ date: d, paise: paise }); });
    });
    return out.filter(function (p) { return p.paise; })
      .sort(function (x, y) { return x.date < y.date ? -1 : x.date > y.date ? 1 : 0; });
  }

  // The visitor's own calendar date: toISOString() is UTC's, which in India is
  // still yesterday until 05:30.
  function localDay(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function blank(kind, row) {
    return kind === "purchase" ? !row.date && !row.amount : !row.amount;
  }

  // What is wrong with one entry, in words, or null. The page shows this beside
  // the row, and `entriesOf` prices only rows for which it is null, so what the
  // page says and what it counts are the same thing.
  function rowError(fund, kind, row, todayIso) {
    var from = fund && fund.prices_from;
    if (kind === "purchase") {
      if (!ISO.test(row.date || "")) return "Enter the date of the purchase.";
      if (row.date > todayIso) return "The date is after today.";
      if (from && row.date < from) return "Prices on record begin on " + from + "; enter a date from then on.";
      if (!toPaise(row.amount)) return "Enter an amount in rupees, above zero.";
      return null;
    }
    if (!toPaise(row.amount)) return "Enter a monthly amount in rupees, above zero.";
    if (!Number.isInteger(row.day) || row.day < 1 || row.day > 31) return "Enter a day of the month from 1 to 31.";
    if (!MONTH.test(row.start || "")) return "Enter the month the SIP started.";
    if (row.start > todayIso.slice(0, 7)) return "The SIP starts after this month.";
    if (row.stop && row.stop < row.start) return "The SIP stops before it starts.";
    var first = sipDates({ day: row.day, start: row.start, stop: row.start }, "9999-12-31")[0];
    if (from && first < from) return "Prices on record begin on " + from + "; the first instalment, " + first + ", is before that.";
    return null;
  }

  // The purchases a holding's error-free rows make, and how many rows with an
  // error were left out (a row not yet filled in is not counted).
  function entriesOf(holding, fund, todayIso) {
    var buys = [], excluded = 0;
    (holding.purchases || []).forEach(function (p) {
      if (rowError(fund, "purchase", p, todayIso)) { if (!blank("purchase", p)) excluded += 1; return; }
      buys.push({ date: p.date, paise: toPaise(p.amount) });
    });
    (holding.sips || []).forEach(function (s) {
      if (rowError(fund, "sip", s, todayIso)) { if (!blank("sip", s)) excluded += 1; return; }
      var paise = toPaise(s.amount);
      sipDates(s, todayIso).forEach(function (d) { buys.push({ date: d, paise: paise }); });
    });
    buys.sort(function (x, y) { return x.date < y.date ? -1 : x.date > y.date ? 1 : 0; });
    return { buys: buys, excluded: excluded };
  }

  // M1's `returns.xirr`, step for step.
  function xirr(flows) {
    if (flows.length < 2) return null;
    var signs = {};
    flows.forEach(function (f) { if (f[1] !== 0) signs[f[1] > 0 ? 1 : -1] = true; });
    if (Object.keys(signs).length < 2) return null;
    var t0 = Date.parse(flows[0][0]);
    var years = flows.map(function (f) { return (Date.parse(f[0]) - t0) / DAY_MS / 365; });
    var amounts = flows.map(function (f) { return f[1]; });
    function npv(r) {
      var s = 0;
      for (var i = 0; i < amounts.length; i++) s += amounts[i] / Math.pow(1 + r, years[i]);
      return s;
    }
    function dnpv(r) {
      var s = 0;
      for (var i = 0; i < amounts.length; i++) s -= years[i] * amounts[i] / Math.pow(1 + r, years[i] + 1);
      return s;
    }
    var FLOOR = -0.9999, rate = 0.15;
    for (var k = 0; k < 50; k++) {
      var v = npv(rate);
      if (!isFinite(v)) break;
      if (Math.abs(v) < 1e-7) return rate;
      var slope = dnpv(rate);
      if (!isFinite(slope) || Math.abs(slope) < 1e-12) break;
      var next = rate - v / slope;
      if (next <= FLOOR) next = (rate + FLOOR) / 2;
      if (Math.abs(next - rate) < 1e-9) return next;
      rate = next;
    }
    var lo = FLOOR, hi = 10;
    if (!(npv(lo) * npv(hi) <= 0)) return null;
    for (var j = 0; j < 200; j++) {
      var mid = (lo + hi) / 2;
      if (npv(lo) * npv(mid) <= 0) hi = mid; else lo = mid;
      if (hi - lo < 1e-10) break;
    }
    return (lo + hi) / 2;
  }

  function position(buys, series) {
    var lots = buys.map(function (b) {
      return Object.assign({ date: b.date, paise: b.paise }, allot(b.paise, b.date, series));
    });
    var priced = lots.filter(function (l) { return !l.error; });
    var units = priced.reduce(function (s, l) { return s + l.unitsMilli; }, 0n);
    var last = series.dates.length - 1;
    var valuePaise = Number(roundDiv(units * series.navs[last], 10000000n));
    var flows = priced.map(function (l) { return [l.date, -l.paise / 100]; })
      .concat([[series.dates[last], valuePaise / 100]]);
    return {
      lots: lots,
      unitsMilli: units,
      investedPaise: priced.reduce(function (s, l) { return s + l.paise; }, 0),
      valuePaise: valuePaise,
      valueDate: series.dates[last],
      firstDate: priced.length ? priced[0].date : null,
      xirr: priced.length ? xirr(flows) : null,
    };
  }

  function showsXirr(firstIso, valueIso) {
    return (Date.parse(valueIso) - Date.parse(firstIso)) / DAY_MS >= 365;
  }

  function isSynthetic(id) { return id.indexOf("__") === 0; }

  function add(map, key, v) { map.set(key, (map.get(key) || 0) + v); }

  function shares(map, of) {
    return Array.from(map, function (kv) {
      return { key: kv[0], paise: kv[1], pct: of ? kv[1] * 100 / of : 0 };
    }).sort(function (x, y) { return y.paise - x.paise; });
  }

  function rows(map, total) {
    return Array.from(map.values(), function (r) {
      return { id: r.id, name: r.name, klass: r.klass, paise: r.paise,
               funds: r.funds.size, pct: total ? r.paise * 100 / total : 0 };
    }).sort(function (x, y) { return y.paise - x.paise; });
  }

  function lookThrough(positions, files) {
    var total = positions.reduce(function (s, p) { return s + p.valuePaise; }, 0);
    var companies = new Map(), synthetic = new Map();
    var mix = new Map(), sectors = new Map(), sizes = new Map();
    var equity = 0, unknown = 0, funds = [];
    positions.forEach(function (p) {
      var f = files[p.id];
      if (!f) { unknown += p.valuePaise; return; }
      funds.push({ id: p.id, asOf: f.as_of, aggregator: f.aggregator });
      f.holdings.forEach(function (h) {
        var into = isSynthetic(h[0]) ? synthetic : companies;
        var row = into.get(h[0]) || { id: h[0], name: h[1], klass: h[2], paise: 0, funds: new Set() };
        row.paise += p.valuePaise * Number(h[3]) / 100;
        row.funds.add(p.id);
        into.set(h[0], row);
      });
      var eq = 0;
      f.mix.forEach(function (m) {
        var paise = p.valuePaise * Number(m[1]) / 100;
        add(mix, m[0], paise);
        if (m[0] === "equity") eq = paise;
      });
      equity += eq;
      f.sectors.forEach(function (s) { add(sectors, s[0], eq * Number(s[1]) / 100); });
      f.sizes.forEach(function (s) { add(sizes, s[0], eq * Number(s[1]) / 100); });
    });
    var unresolved = synthetic.get("__UNRESOLVED__");
    return {
      total: total,
      companies: rows(companies, total),
      synthetic: rows(synthetic, total),
      mix: shares(mix, total),
      sectors: shares(sectors, equity),
      sizes: shares(sizes, equity),
      coverage: { unknownPaise: unknown, unresolvedPaise: unresolved ? unresolved.paise : 0, funds: funds },
    };
  }

  // M3's measure (`m3_lookthrough.overlap`): sum of the smaller weight over
  // shared issuers, synthetics dropped. 100 identical, 0 disjoint.
  function overlap(a, b) {
    var wb = new Map();
    b.holdings.forEach(function (h) { if (!isSynthetic(h[0])) wb.set(h[0], Number(h[3])); });
    var s = 0;
    a.holdings.forEach(function (h) {
      if (!isSynthetic(h[0]) && wb.has(h[0])) s += Math.min(Number(h[3]), wb.get(h[0]));
    });
    return s;
  }

  var RULES = [
    ["ter", function (x, y) { return x - y; }],     // lowest expense ratio
    ["r3", function (x, y) { return y - x; }],      // highest three-year return
    ["size", function (x, y) { return y - x; }],    // largest fund
  ];

  // AMFI's older "Index Funds" and "ETFs" headings hold equity, debt and gold
  // funds alike (config/categories.yaml, `*/undivided`): nothing in them is
  // like-for-like, so none is suggested. The person can still choose one.
  function mixed(category) { return /\/undivided$/.test(category || ""); }

  function alternatives(held, funds, firstIso) {
    if (mixed(held.category)) return [];
    var pool = funds.filter(function (f) {
      return f.category === held.category && f.id !== held.id && f.amfi &&
        f.prices_from && f.prices_from <= firstIso;
    });
    var out = [];
    RULES.forEach(function (rule) {
      var key = rule[0];
      var pick = pool.filter(function (f) { return f[key] != null; }).sort(function (x, y) {
        return rule[1](Number(x[key]), Number(y[key])) || (x.name < y.name ? -1 : 1);
      })[0];
      if (!pick) return;
      var seen = out.filter(function (o) { return o.fund.id === pick.id; })[0];
      if (seen) seen.reasons.push(key); else out.push({ fund: pick, reasons: [key] });
    });
    return out;
  }

  // Each of the three comparison slots, at its own index: the person's choice
  // there, else the suggestion of the same rank unless it was chosen elsewhere,
  // else empty. "Replace" writes the slot it is drawn in.
  function altSlots(alts, suggested, byId) {
    var chosen = [0, 1, 2].map(function (k) {
      var f = alts[k] ? byId(alts[k]) : null;
      return f || null;
    });
    var taken = chosen.filter(Boolean).map(function (f) { return f.id; });
    return [0, 1, 2].map(function (k) {
      if (chosen[k]) return { slot: k, fund: chosen[k], reasons: ["chosen"] };
      var s = suggested[k];
      if (s && taken.indexOf(s.fund.id) < 0) return { slot: k, fund: s.fund, reasons: s.reasons };
      return { slot: k, fund: null, reasons: [] };
    });
  }

  // The money an alternative is valued on: exactly what the held fund priced.
  function pricedBuys(pos) {
    return pos.lots.filter(function (l) { return !l.error; })
      .map(function (l) { return { date: l.date, paise: l.paise }; });
  }

  function text(v, max) {
    return (typeof v === "string" || typeof v === "number") && String(v).length <= max ? String(v) : null;
  }

  function parsePortfolio(value) {
    if (!value || value.version !== 1 || !Array.isArray(value.funds)) {
      return { error: "This is not a portfolio file from this site." };
    }
    var byId = new Map(), dropped = 0;
    for (var i = 0; i < value.funds.length; i++) {
      var f = value.funds[i];
      if (!f || typeof f.id !== "string" || !ISIN.test(f.id)) {
        return { error: "A fund in the file has no valid ISIN." };
      }
      var into = byId.get(f.id) || { id: f.id, purchases: [], sips: [], alts: [null, null, null] };
      // Rows are kept whenever their fields have the right shape, filled in or
      // not: whether an entry is complete is `rowError`'s question, asked on the
      // page. Only rows that are not shaped like entries are dropped, counted.
      (f.purchases || []).forEach(function (p) {
        var d = p && text(p.date, 10), a = p && text(p.amount, 20);
        if (d != null && a != null) into.purchases.push({ date: d, amount: a });
        else dropped += 1;
      });
      (f.sips || []).forEach(function (s) {
        var a = s && text(s.amount, 20), st = s && text(s.start, 7);
        var stop = s && (s.stop == null || s.stop === "" ? "" : text(s.stop, 7));
        var day = s && (typeof s.day === "number" || s.day == null);
        if (a != null && st != null && stop != null && day) {
          into.sips.push({ amount: a, day: s.day == null ? null : s.day, start: st, stop: stop || null });
        } else { dropped += 1; }
      });
      if (Array.isArray(f.alts)) {
        into.alts = [0, 1, 2].map(function (k) {
          var a = f.alts[k];
          return typeof a === "string" && ISIN.test(a) ? a : into.alts[k];
        });
      }
      byId.set(f.id, into);
    }
    return { portfolio: { version: 1, funds: Array.from(byId.values()) }, dropped: dropped };
  }

  var api = {
    toPaise: toPaise, toMicro: toMicro, parseNavFile: parseNavFile, allot: allot,
    sipDates: sipDates, purchasesOf: purchasesOf, position: position, xirr: xirr,
    showsXirr: showsXirr, isSynthetic: isSynthetic, lookThrough: lookThrough,
    overlap: overlap, alternatives: alternatives, parsePortfolio: parsePortfolio,
    localDay: localDay, rowError: rowError, entriesOf: entriesOf, altSlots: altSlots,
    pricedBuys: pricedBuys,
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  else globalThis.PortfolioMath = api;
})();
