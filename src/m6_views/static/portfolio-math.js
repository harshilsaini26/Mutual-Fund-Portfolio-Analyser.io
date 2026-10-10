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

  // One BigInt per line, not two: /sip/ reads some 30 of these files on opening,
  // and on a slow phone this loop was half a second of it (§4.10).
  var NAV = /^\d+(?:\.\d{1,6})?$/;
  function parseNavFile(text) {
    var dates = [], navs = [], lines = text.split("\n");
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line || line.charAt(0) === "#") continue;
      var comma = line.indexOf(",");
      var nav = comma < 0 ? "" : line.slice(comma + 1).trim();
      if (!NAV.test(nav)) throw new Error("not a NAV: " + nav);
      var dot = nav.indexOf(".");
      dates.push(line.slice(0, comma));
      navs.push(BigInt(dot < 0 ? nav + "000000"
        : nav.slice(0, dot) + nav.slice(dot + 1).padEnd(6, "0")));
    }
    return { dates: dates, navs: oneScale(navs) };
  }

  // A fund that re-denominates its units moves its NAV by 100, 10, 1/10 or 1/100 in
  // a day (within 10%: it also moved that day); read raw, that is a 900% gain. The
  // file keeps the raw prices, and every earlier one is restated here onto the later
  // scale, rounded half up to the millionth: the warehouse's nav_adj
  // (`rescale_splits`), so these pages and the fund pages agree.
  var SPLITS = [[100n, 1n], [10n, 1n], [1n, 10n], [1n, 100n]];
  function splitAt(prev, cur) {
    for (var k = 0; k < SPLITS.length; k++) {
      var a = 10n * SPLITS[k][1] * cur, b = SPLITS[k][0] * prev;
      if (a >= 9n * b && a <= 11n * b) return SPLITS[k];
    }
    return null;
  }
  function oneScale(navs) {
    var num = 1n, den = 1n, out = navs;
    for (var i = navs.length - 1; i > 0; i--) {
      var s = splitAt(navs[i - 1], navs[i]);
      if (s) { num *= s[0]; den *= s[1]; if (out === navs) out = navs.slice(); }
      if (out !== navs) out[i - 1] = roundDiv(navs[i - 1] * num, den);
    }
    return out;
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

  // "25 Sep 2026", as format.py's `format_date` writes every date on the site.
  // The months are spelled here: en-GB formatting gives "Sept" in some browsers.
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function day(iso) {
    if (!iso) return "—";
    var p = String(iso).split("-");
    return p[2] + " " + MONTHS[Number(p[1]) - 1] + " " + p[0];
  }

  // Units held, from thousandths, grouped as rupees are: 12,34,567.890.
  var GROUPED = new Intl.NumberFormat("en-IN");
  function units(milli) {
    return GROUPED.format(milli / 1000n) + "." + String(milli % 1000n).padStart(3, "0");
  }


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
    return kind === "sip" ? !row.amount : !row.date && !row.amount;
  }

  // What is wrong with one entry, in words, or null. The page shows this beside
  // the row, and `entriesOf` prices only rows for which it is null, so what the
  // page says and what it counts are the same thing.
  function rowError(fund, kind, row, todayIso) {
    var from = fund && fund.prices_from;
    if (kind === "purchase" || kind === "sale") {
      if (!ISO.test(row.date || "")) return "Enter the date of the " + kind + ".";
      if (row.date > todayIso) return "The date is after today.";
      if (from && row.date < from) return "Prices on record begin on " + day(from) + "; enter a date from then on.";
      if (!toPaise(row.amount)) {
        return kind === "sale" ? "Enter the amount you received, in rupees, above zero."
          : "Enter an amount in rupees, above zero.";
      }
      return null;
    }
    if (!toPaise(row.amount)) return "Enter a monthly amount in rupees, above zero.";
    if (!Number.isInteger(row.day) || row.day < 1 || row.day > 31) return "Enter a day of the month from 1 to 31.";
    if (!MONTH.test(row.start || "")) return "Enter the month the SIP started.";
    if (row.start > todayIso.slice(0, 7)) return "The SIP starts after this month.";
    if (row.stop && row.stop < row.start) return "The SIP stops before it starts.";
    var first = sipDates({ day: row.day, start: row.start, stop: row.start }, "9999-12-31")[0];
    if (from && first < from) return "Prices on record begin on " + day(from) + "; the first instalment, " + day(first) + ", is before that.";
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
    buys.sort(byDate);
    var sales = [];
    (holding.sales || []).forEach(function (p) {
      if (rowError(fund, "sale", p, todayIso)) { if (!blank("sale", p)) excluded += 1; return; }
      sales.push({ date: p.date, paise: toPaise(p.amount) });
    });
    sales.sort(byDate);
    return { buys: buys, sales: sales, excluded: excluded };
  }

  function byDate(x, y) {
    var a = x.date || x[0], b = y.date || y[0];
    return a < b ? -1 : a > b ? 1 : 0;
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

  // A sale: the units the amount buys back at that day's NAV, without stamp
  // duty (it is charged on purchases), or why it cannot be priced.
  function redeem(amountPaise, iso, series) {
    if (!series.dates.length || iso < series.dates[0]) return { error: "before" };
    var i = onOrAfter(series.dates, iso);
    if (i < 0) return { error: "pending" };
    return { navDate: series.dates[i], navMicro: series.navs[i],
             unitsMilli: roundDiv(BigInt(amountPaise) * 10000000n, series.navs[i]) };
  }

  // `sales` are the money received from selling units (external audit,
  // 2026-10-04: purchases alone overstated anyone who had sold). Each removes
  // its units on its date; one larger than what was held then is left out
  // ("more"), and the return counts the money back as it came.
  function position(buys, series, sales) {
    var lots = buys.map(function (b) {
      return Object.assign({ date: b.date, paise: b.paise }, allot(b.paise, b.date, series));
    });
    var priced = lots.filter(function (l) { return !l.error; });
    var bought = function (iso) {
      return priced.reduce(function (s, l) { return l.date <= iso ? s + l.unitsMilli : s; }, 0n);
    };
    var soldUnits = 0n;
    var out = (sales || []).slice().sort(byDate).map(function (s) {
      var sale = Object.assign({ date: s.date, paise: s.paise }, redeem(s.paise, s.date, series));
      if (sale.error) return sale;
      if (sale.unitsMilli > bought(s.date) - soldUnits) return Object.assign(sale, { error: "more" });
      soldUnits += sale.unitsMilli;
      return sale;
    });
    var taken = out.filter(function (s) { return !s.error; });
    var units = bought("9999-12-31") - soldUnits;
    var last = series.dates.length - 1;
    var valuePaise = Number(roundDiv(units * series.navs[last], 10000000n));
    var flows = priced.map(function (l) { return [l.date, -l.paise / 100]; })
      .concat(taken.map(function (s) { return [s.date, s.paise / 100]; }))
      .sort(byDate)
      .concat([[series.dates[last], valuePaise / 100]]);
    return {
      lots: lots,
      sales: out,
      unitsMilli: units,
      investedPaise: priced.reduce(function (s, l) { return s + l.paise; }, 0),
      redeemedPaise: taken.reduce(function (s, x) { return s + x.paise; }, 0),
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
    }).sort(function (x, y) { return y.paise - x.paise || (x.key < y.key ? -1 : x.key > y.key ? 1 : 0); });
  }

  function rows(map, total) {
    return Array.from(map.values(), function (r) {
      return { id: r.id, name: r.name, klass: r.klass, paise: r.paise,
               funds: r.funds.size, pct: total ? r.paise * 100 / total : 0 };
    }).sort(function (x, y) { return y.paise - x.paise || (x.id < y.id ? -1 : x.id > y.id ? 1 : 0); });   // a tie-break: one order (D-312)
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

  // [field, order, which]: the first after sorting, or the middle one. Not
  // today's highest three-year return: set against purchases made years ago,
  // that fund is chosen knowing the outcome (external audit, 2026-10-04).
  var RULES = [
    ["ter", function (x, y) { return x - y; }, "first"],     // lowest expense ratio
    ["r3", function (x, y) { return x - y; }, "middle"],     // the category's middle return
    ["size", function (x, y) { return y - x; }, "first"],    // largest fund today
  ];

  // A heading that holds unlike funds -- AMFI's older "Index Funds", catch-alls,
  // funds of funds -- has nothing like-for-like to suggest (`mixed` in
  // funds.json: categories.yaml's `ranked: false`). The person can still choose.
  //
  // `firstIso` is the first purchase: a candidate needs prices back to it. With
  // none (Compare), it needs three years of prices, as its return rule does.
  function alternatives(held, funds, firstIso) {
    if (held.mixed) return [];
    var pool = funds.filter(function (f) {
      return f.category === held.category && f.id !== held.id && f.amfi && f.prices_from &&
        f.plan !== "regular" &&   // Direct plans only (MODULE_2 §11.2)
        (firstIso ? f.prices_from <= firstIso : f.r3 != null);
    });
    var out = [];
    RULES.forEach(function (rule) {
      var key = rule[0];
      var ranked = pool.filter(function (f) { return f[key] != null; }).sort(function (x, y) {
        return rule[1](Number(x[key]), Number(y[key])) || (x.name < y.name ? -1 : 1);
      });
      var pick = ranked[rule[2] === "middle" ? Math.floor((ranked.length - 1) / 2) : 0];
      if (!pick) return;
      var seen = out.filter(function (o) { return o.fund.id === pick.id; })[0];
      if (seen) seen.reasons.push(key); else out.push({ fund: pick, reasons: [key] });
    });
    return out;
  }

  // What a holding is set beside in "Did it work?" (UI/UX critique P-01): the same
  // purchases and sales in the longest-running index fund on its benchmark (the
  // build's `tracker`, the one standing in for the benchmark on its page), else in
  // its category's middle three-year return. Either must have been there to buy on
  // the first purchase; never the holding itself or its own Direct plan.
  function reference(held, funds, firstIso) {
    var tracker = held.tracker && funds.filter(function (f) { return f.id === held.tracker; })[0];
    if (tracker && tracker.plan !== "regular" && tracker.prices_from && tracker.prices_from <= firstIso) {
      return { fund: tracker, why: "index" };
    }
    var others = funds.filter(function (f) { return f.id !== held.direct; });
    var middle = alternatives(held, others, firstIso).filter(function (s) {
      return s.reasons.indexOf("r3") >= 0;
    })[0];
    return middle ? { fund: middle.fund, why: "middle" } : null;
  }

  // An amount as typed, in Indian grouping (P-03): "100000" reads "1,00,000", so a
  // lakh is not taken for ten. Text that is not an amount is left as it was.
  function grouped(text) {
    var s = String(text == null ? "" : text).replace(/[₹,\s]/g, "");
    var m = /^(\d+)(\.\d*)?$/.exec(s);
    if (!m) return String(text == null ? "" : text);
    var whole = m[1].replace(/^0+(?=\d)/, "");
    var head = whole.slice(0, -3), tail = whole.slice(-3);
    return (head ? head.replace(/\B(?=(\d{2})+$)/g, ",") + "," : "") + tail + (m[2] || "");
  }

  // The same in words, beside the field: "₹2.5 lakh". Under a thousand, nothing.
  function inWords(text) {
    var paise = toPaise(text);
    if (!paise || paise < 100000) return "";
    var rupees = paise / 100;
    var unit = rupees >= 1e7 ? [1e7, "crore"] : rupees >= 1e5 ? [1e5, "lakh"] : [1e3, "thousand"];
    return "₹" + String(Math.round(rupees / unit[0] * 100) / 100) + " " + unit[1];
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

  function pricedSales(pos) {
    return (pos.sales || []).filter(function (s) { return !s.error; })
      .map(function (s) { return { date: s.date, paise: s.paise }; });
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
      var into = byId.get(f.id) || { id: f.id, purchases: [], sips: [], sales: [], alts: [null, null, null] };
      // Rows are kept whenever their fields have the right shape, filled in or
      // not: whether an entry is complete is `rowError`'s question, asked on the
      // page. Only rows that are not shaped like entries are dropped, counted.
      (f.purchases || []).forEach(function (p) {
        var d = p && text(p.date, 10), a = p && text(p.amount, 20);
        if (d != null && a != null) into.purchases.push({ date: d, amount: a });
        else dropped += 1;
      });
      (f.sales || []).forEach(function (p) {
        var d = p && text(p.date, 10), a = p && text(p.amount, 20);
        if (d != null && a != null) into.sales.push({ date: d, amount: a });
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

  // A NAV file's text, whether the server sent it packed (.csv.gz) or unpacked.
  // Browser only (DecompressionStream). Used by portfolio.js and compare.js.
  function gzipText(response) {
    return response.arrayBuffer().then(function (buf) {
      var bytes = new Uint8Array(buf);
      if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
        var stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
        return new Response(stream).text();
      }
      return new TextDecoder().decode(bytes);   // a server that already unpacked it
    });
  }

  // --- What would a SIP have become? (/sip/, SPEC_SIP_WHAT_IF §4) -------------------
  // The same money in every fund of a kind, at real past prices, all valued on one
  // date. Built on allot/position/sipDates/xirr above; nothing re-derived.

  var STALE_DAYS = 7;
  // ₹10 crore an instalment: 120 of them grown a hundredfold stay exact in paise as a
  // Number (toPaise's 13 digits would not).
  var SIP_MAX_PAISE = 10000000000;
  function shiftDays(iso, n) { return new Date(Date.parse(iso) + n * DAY_MS).toISOString().slice(0, 10); }
  function lastDay(y, m) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); }
  function monthsBack(y, m, n) { var t = y * 12 + (m - 1) - n; return [Math.floor(t / 12), t % 12 + 1]; }
  // A series cut at `iso`: no price after the valuation date is ever used.
  function cutAt(series, iso) {
    var i = onOrAfter(series.dates, iso);
    var n = i < 0 ? series.dates.length : series.dates[i] === iso ? i + 1 : i;
    return { dates: series.dates.slice(0, n), navs: series.navs.slice(0, n) };
  }
  function lastOf(series) { return series && series.dates.length ? series.dates[series.dates.length - 1] : null; }

  // §4.3. The newest date on which every fund priced in the week to the latest NAV
  // has a price; funds whose last price is older are "stale".
  function valuationDate(seriesById) {
    var lasts = [];
    seriesById.forEach(function (s, id) { var l = lastOf(s); if (l) lasts.push([id, l]); });
    if (!lasts.length) return null;
    var latest = lasts.reduce(function (m, x) { return x[1] > m ? x[1] : m; }, "");
    var floor = shiftDays(latest, -STALE_DAYS);
    var kept = lasts.filter(function (x) { return x[1] >= floor; });
    return {
      valuedOn: kept.reduce(function (m, x) { return x[1] < m ? x[1] : m; }, latest),
      latest: latest,
      stale: lasts.filter(function (x) { return x[1] < floor; }).map(function (x) { return x[0]; }),
    };
  }

  // §4.3. The purchases: `years` (1, 3, 5, 10) or `from` ("YYYY-MM" for a SIP,
  // "YYYY-MM-DD" once). A SIP's last instalment is in the valuation date's month if
  // its day (clamped to the month) has come, else the month before.
  function windowOf(w, valuedOn) {
    if (!w.amountPaise || w.amountPaise > SIP_MAX_PAISE) return { error: "amount" };
    var v = valuedOn.split("-").map(Number), dates;
    if (w.mode === "once") {
      var on = w.from || (v[0] - w.years) + "-" + pad(v[1]) + "-" +
        pad(Math.min(v[2], lastDay(v[0] - w.years, v[1])));
      if (on >= valuedOn) return { error: "after" };
      dates = [on];
    } else {
      var day = w.day || 5;
      var end = Math.min(day, lastDay(v[0], v[1])) <= v[2] ? [v[0], v[1]] : monthsBack(v[0], v[1], 1);
      var start = w.from ? w.from : (function (s) { return s[0] + "-" + pad(s[1]); })(monthsBack(end[0], end[1], 12 * w.years - 1));
      var stop = end[0] + "-" + pad(end[1]);
      if (start > stop) return { error: "after" };
      dates = sipDates({ day: day, start: start, stop: stop }, valuedOn);
    }
    return { buys: dates.map(function (d) { return { date: d, paise: w.amountPaise }; }),
             first: dates[0], last: dates[dates.length - 1], count: dates.length };
  }

  // §4.4. Which funds take the same money: Direct plans (a Regular plan is the same
  // fund at a higher cost) that loaded, were priced by the first purchase and have a
  // recent price. Every other one is listed with its reason, never dropped.
  function poolOf(funds, seriesById, window, valuedOn) {
    var latest = "";
    seriesById.forEach(function (s) { var l = lastOf(s); if (l && l > latest) latest = l; });
    var floor = shiftDays(latest || valuedOn, -STALE_DAYS);
    var inRange = [], out = [];
    funds.forEach(function (f) {
      if (f.plan === "regular") return;
      var s = seriesById.get(f.id);
      var reason = !lastOf(s) ? "load" : lastOf(s) < floor ? "stale"
        : s.dates[0] > window.first ? "later" : null;
      if (reason) out.push({ fund: f, reason: reason }); else inRange.push(f);
    });
    return { inRange: inRange, out: out };
  }

  // Worth, in paise, of `units` thousandths at a NAV in millionths.
  function worth(units, nav) { return Number(roundDiv(units * nav, 10000000n)); }

  // §4.5. One fund on one window, valued on `valuedOn`, and its lowest point against
  // what had been put in by then. The scan starts the day after the first purchase is
  // priced: on that day only its stamp duty is off it, which no fund could avoid.
  function outcome(buys, series, valuedOn) {
    var cut = cutAt(series, valuedOn);
    var pos = position(buys, cut);
    var lots = pos.lots.filter(function (l) { return !l.error; })
      .sort(function (a, b) { return a.navDate < b.navDate ? -1 : a.navDate > b.navDate ? 1 : 0; });
    var low = 0, lowOn = null, k = 0, units = 0n, paid = 0;
    for (var i = 0; i < cut.dates.length; i++) {
      var d = cut.dates[i];
      while (k < lots.length && lots[k].navDate <= d) { units += lots[k].unitsMilli; paid += lots[k].paise; k++; }
      if (!lots.length || d <= lots[0].navDate || !paid) continue;
      var fall = (worth(units, cut.navs[i]) - paid) / paid;
      if (fall < low) { low = fall; lowOn = d; }
    }
    return Object.assign(pos, { low: low, lowOn: lowOn });
  }

  // §4.5. The range: lowest, the lower middle (index floor((n-1)/2), as
  // `alternatives` takes "middle") and highest worth, ties on fund id.
  function spread(outcomes) {
    var s = outcomes.slice().sort(function (a, b) {
      return a.valuePaise - b.valuePaise || (a.fund.id < b.fund.id ? -1 : a.fund.id > b.fund.id ? 1 : 0);
    });
    var n = s.length;
    if (!n) return { n: 0 };
    return { n: n, min: s[0], middle: s[Math.floor((n - 1) / 2)], max: s[n - 1], sorted: s,
             belowEver: s.filter(function (o) { return o.low < 0; }).length };
  }

  // §4.5. Chart 1: worth at each month's (or, under three years, each week's) end
  // from the first purchase, the last point on `valuedOn`; and what had been put in,
  // stepping on each purchase. Every fund on one grid, so the band lines up.
  function pathOf(buys, series, valuedOn, step) {
    var cut = cutAt(series, valuedOn);
    var lots = position(buys, cut).lots.filter(function (l) { return !l.error; });
    // From the first purchase's price: a holiday before it would draw nothing held.
    var grid = [], d = lots.reduce(function (m, l) { return l.navDate < m ? l.navDate : m; }, valuedOn);
    while (d < valuedOn) {
      var p = d.split("-").map(Number), end;
      if (step === "week") {
        end = shiftDays(d, (7 - new Date(Date.parse(d)).getUTCDay()) % 7);   // that week's Sunday
        if (end === d && grid.length && grid[grid.length - 1] === d) end = shiftDays(d, 7);
      } else end = p[0] + "-" + pad(p[1]) + "-" + pad(lastDay(p[0], p[1]));
      if (end >= valuedOn) break;
      grid.push(end);
      d = shiftDays(end, 1);
    }
    grid.push(valuedOn);
    var points = grid.map(function (g) {
      var i = onOrAfter(cut.dates, g);
      var at = i < 0 ? cut.dates.length - 1 : cut.dates[i] === g ? i : i - 1;
      var units = lots.reduce(function (s, l) { return l.navDate <= g ? s + l.unitsMilli : s; }, 0n);
      return [g, at < 0 ? 0 : worth(units, cut.navs[at])];
    });
    var total = 0;
    var putIn = buys.map(function (b) { total += b.paise; return [b.date, total]; });
    putIn.push([valuedOn, total]);
    return { points: points, putIn: putIn };
  }

  // §4.5. The index fund a kind is measured against: the `tracker` most of its funds
  // name (each fund's benchmark, as its page draws it); on a tie the one with the
  // longer record, then the lower id. None when none names one.
  function indexFor(funds, categoryKey) {
    var byId = new Map(funds.map(function (f) { return [f.id, f]; }));
    var count = new Map();
    funds.forEach(function (f) {
      if (f.category === categoryKey && f.tracker && byId.has(f.tracker)) {
        count.set(f.tracker, (count.get(f.tracker) || 0) + 1);
      }
    });
    var best = null;
    count.forEach(function (n, id) {
      var f = byId.get(id);
      if (!best || n > best.sharedBy ||
          (n === best.sharedBy && ((f.prices_from || "9") < (best.fund.prices_from || "9") ||
            (f.prices_from === best.fund.prices_from && id < best.fund.id)))) {
        best = { fund: f, sharedBy: n };
      }
    });
    return best;
  }

  var api = {
    valuationDate: valuationDate, windowOf: windowOf, poolOf: poolOf, outcome: outcome,
    spread: spread, pathOf: pathOf, indexFor: indexFor, cutAt: cutAt, SIP_MAX_PAISE: SIP_MAX_PAISE,
    toPaise: toPaise, toMicro: toMicro, parseNavFile: parseNavFile, allot: allot,
    sipDates: sipDates, purchasesOf: purchasesOf, position: position, xirr: xirr,
    showsXirr: showsXirr, isSynthetic: isSynthetic, lookThrough: lookThrough,
    overlap: overlap, alternatives: alternatives, parsePortfolio: parsePortfolio,
    localDay: localDay, rowError: rowError, entriesOf: entriesOf, altSlots: altSlots,
    pricedBuys: pricedBuys, pricedSales: pricedSales, gzipText: gzipText, day: day, units: units,
    reference: reference, grouped: grouped, inWords: inWords,
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  else globalThis.PortfolioMath = api;
})();
