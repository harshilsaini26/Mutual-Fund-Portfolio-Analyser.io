/*
 * What would a SIP have become? (SPEC_SIP_WHAT_IF, Part A)
 *
 * The page is a shell (sip.html); this fills it in the browser from funds.json and
 * each fund's NAV file, as Your portfolio and Compare do (V1-82, V1-85). Every
 * figure comes from portfolio-math.js (windowOf, poolOf, outcome, spread, pathOf,
 * indexFor), which is pinned to the ledger by tests/fixtures/sip_cases.json; this
 * file only wires inputs and writes sentences. The inputs live in the address and
 * nowhere else. It shows what real prices did, never what money will do.
 * Built with createElement/textContent only, never innerHTML.
 */
(function () {
  "use strict";

  var PERIODS = [1, 3, 5, 10];
  var ISIN = /^[A-Z0-9]{12}$/;
  var DEFAULT = { a: "5000", m: "sip", y: 5, from: null, d: 5, c: null, f: [] };

  // §4.7. The address: what can be read is kept, what cannot falls back to the
  // default; an unreadable amount is reported ("amount") so the page can say so.
  function parseHash(hash) {
    var state = Object.assign({}, DEFAULT, { f: [] }), notes = [], seen = {};
    String(hash || "").replace(/^#/, "").split("&").forEach(function (pair) {
      var at = pair.indexOf("="), key, value;
      if (at < 0) return;
      key = pair.slice(0, at);
      try { value = decodeURIComponent(pair.slice(at + 1)); } catch (e) { return; }
      if (seen[key]) return;
      seen[key] = true;
      if (key === "a") { if (/^\d{1,9}$/.test(value) && Number(value) > 0) state.a = value; else notes.push("amount"); }
      else if (key === "m") { if (value === "sip" || value === "once") state.m = value; }
      else if (key === "y") { if (PERIODS.indexOf(Number(value)) >= 0) state.y = Number(value); }
      else if (key === "from") state.from = value;
      else if (key === "d") { if (/^\d{1,2}$/.test(value) && Number(value) >= 1 && Number(value) <= 31) state.d = Number(value); }
      else if (key === "c") { if (/^[a-z_]+\/[a-z0-9_]+$/.test(value)) state.c = value; }
      else if (key === "f") {
        value.split(",").forEach(function (id) {
          id = id.trim().toUpperCase();
          if (ISIN.test(id) && state.f.indexOf(id) < 0 && state.f.length < 3) state.f.push(id);
        });
      }
    });
    // A start in the shape its mode takes replaces the years; any other is dropped.
    var shape = state.m === "sip" ? /^\d{4}-\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/;
    if (state.from && shape.test(state.from)) state.y = null; else state.from = null;
    return { state: state, notes: notes };
  }

  function writeHash(s) {
    var parts = ["a=" + s.a, "m=" + s.m, s.from ? "from=" + s.from : "y=" + s.y, "d=" + s.d];
    if (s.c) parts.push("c=" + s.c);
    if (s.f.length) parts.push("f=" + s.f.join(","));
    return "#" + parts.join("&");
  }

  // §5.1.3. A figure from kinds.json (rupees as text, for the build's unit amount)
  // at `paise` instead, to the nearest ₹100, in paise: "about", never exact, since
  // units round per instalment. Integers throughout, so a half rounds up every time.
  function scaled(worth, unit, paise) {
    var w = BigInt(Math.round(Number(worth) * 100)), u = BigInt(Math.round(Number(unit) * 100));
    var d = u * 10000n;
    return Number((2n * w * BigInt(paise) + d) / (2n * d)) * 10000;
  }

  var api = { parseHash: parseHash, writeHash: writeHash, scaled: scaled };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }

  // --- in the browser ------------------------------------------------------------
  var M = window.PortfolioMath, K = window.Kit;
  var page = document.querySelector("[data-sip]");
  if (!page || !M || !K) return;
  var el = K.el, fill = K.fill, INR = K.INR;
  var BASE = page.getAttribute("data-root") || "";
  var FUNDS = new Map();
  var state = DEFAULT;
  var generation = 0;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  var form = page.querySelector("[data-sip-form]");
  var amount = document.getElementById("sip-amount");
  var words = page.querySelector("[data-sip-words]");
  var kind = document.getElementById("sip-kind");
  var about = page.querySelector("[data-sip-about]");
  var dayBox = document.getElementById("sip-day");
  var fromBox = document.getElementById("sip-from");
  var fromField = page.querySelector(".sip__from");
  var status = document.getElementById("sip-status");

  function out(name) { return page.querySelector('[data-out="' + name + '"]'); }
  function say(text) { status.textContent = text; }
  function rupees(paise) { return INR.format(Math.round(paise / 100)); }
  function pct(fraction) { return Math.abs(fraction * 100).toFixed(1) + "%"; }
  function signed(fraction) {
    var v = fraction * 100;
    return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%";
  }
  function month(iso) { var p = iso.split("-"); return MONTHS[Number(p[1]) - 1] + " " + p[0]; }
  function years(n) { return n + (n === 1 ? " year" : " years"); }
  // "Large cap" -> "large cap"; "ELSS (tax saver)" keeps its capitals.
  function lower(name) { return /^[A-Z][a-z]/.test(name) ? name.charAt(0).toLowerCase() + name.slice(1) : name; }
  function fundPage(f) { return BASE + "/fund/" + (f.direct || f.id) + "/"; }
  function kindName() { return kind.options[kind.selectedIndex].textContent.replace(/ \(\d+\)$/, ""); }

  // The return a year (XIRR) from a year on; under a year, the change in total.
  function returnText(o, first, valuedOn) {
    if (M.showsXirr(first, valuedOn)) return o.xirr == null ? "—" : signed(o.xirr) + " a year";
    return signed((o.valuePaise - o.investedPaise) / o.investedPaise) + " in total (under a year)";
  }
  function lowText(o) { return o.low < 0 ? pct(o.low) + " below, on " + M.day(o.lowOn) : "Never below"; }

  // --- inputs ------------------------------------------------------------------------
  function readForm() {
    var period = form.elements.period.value;
    var mode = form.elements.mode.value;
    return { a: (M.toPaise(amount.value) ? String(Math.round(M.toPaise(amount.value) / 100)) : state.a),
             m: mode, y: period === "from" ? null : Number(period),
             from: period === "from" ? (fromBox.value || null) : null,
             d: Number(dayBox.value), c: kind.value, f: state.f.slice() };
  }
  function showState() {
    amount.value = M.grouped(state.a);
    words.textContent = M.inWords(state.a);
    form.elements.mode.value = state.m;
    form.elements.period.value = state.from ? "from" : String(state.y);
    dayBox.value = String(state.d);
    if (state.c) kind.value = state.c;
    fromBox.type = state.m === "sip" ? "month" : "date";
    page.querySelector("[data-sip-from-label]").textContent = state.m === "sip" ? "First instalment" : "Put in on";
    fromBox.value = state.from || "";
    fromField.hidden = !state.from && form.elements.period.value !== "from";
    about.textContent = kind.options[kind.selectedIndex].getAttribute("data-about") || "";
    added();
  }
  function fieldError(name, text, input) {
    page.querySelector('[data-sip-error="' + name + '"]').textContent = text || "";
    if (text) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
  }

  // The amount waits for typing to pause; the others act at once (§4.2).
  var typing = null;
  amount.addEventListener("input", function () {
    words.textContent = M.inWords(amount.value);
    if (typing) typing.cancel();
    typing = K.fuse(300, changed);
  });
  amount.addEventListener("change", function () { if (M.toPaise(amount.value)) amount.value = M.grouped(amount.value.replace(/[₹,\s]/g, "")); });
  form.addEventListener("change", function (e) {
    if (e.target === amount) return;
    if (e.target.name === "mode") fromBox.value = "";
    changed();
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); });

  function changed() {
    var next = readForm();
    var paise = M.toPaise(amount.value);
    if (!paise) fieldError("amount", "Enter an amount in rupees, above zero.", amount);
    else if (paise > M.SIP_MAX_PAISE) fieldError("amount", "Enter an amount up to ₹10,00,00,000.", amount);
    else fieldError("amount", "", amount);
    state = next;
    showState();
    run();
  }

  // Funds added by name (§4.2): up to three, any plan, as chips with a remove.
  function added() {
    var box = out("added");
    fill(box, state.f.length && el.apply(null, ["ul", { "class": "cmp__chosen" }].concat(state.f.map(function (id, i) {
      var f = FUNDS.get(id);
      return el("li", { "class": "cmp__picked" },
        el("span", { "class": "cmp__swatch cmp__swatch--" + (i + 3), "aria-hidden": "true" }),
        el("a", { href: fundPage(f) }, f.name),
        el("button", { type: "button", "class": "cmp__remove", "data-remove": id, "aria-label": "Remove " + f.name }, "×"));
    }))));
  }
  page.addEventListener("click", function (e) {
    var b = e.target.closest("[data-remove], [data-retry], [data-kind], [data-family]");
    if (!b) return;
    if (b.hasAttribute("data-family")) {
      // The rest of a family's kinds, kept open while the figures change; focus
      // goes to the first one just shown.
      var name = b.getAttribute("data-family");
      var shown = b.parentNode.querySelectorAll(".sip__krow").length;
      opened[name] = true;
      kindsFile.then(function (j) {
        drawKinds(j);
        var f = Array.prototype.find.call(page.querySelectorAll("[data-family-of]"),
          function (x) { return x.getAttribute("data-family-of") === name; });
        var next = f && f.querySelectorAll(".sip__krow-name")[shown];
        if (next) next.focus();
      });
      return;
    }
    if (b.hasAttribute("data-remove")) {
      state.f = state.f.filter(function (id) { return id !== b.getAttribute("data-remove"); });
      showState();
      document.getElementById("sip-pick").focus();
    } else if (b.hasAttribute("data-kind")) {
      kind.value = b.getAttribute("data-kind");
      state.c = kind.value;
      showState();
      // From the overview: to the answer, which now works out this kind exactly.
      if (b.closest("[data-sip-kinds]")) out("answer-box").scrollIntoView({ block: "start" });
    }
    run();
  });
  K.picker(document.getElementById("sip-pick"), function () { return Array.from(FUNDS.values()); },
    function (f) {
      if (state.f.indexOf(f.id) >= 0) { say(f.name + " is already here."); return; }
      if (state.f.length >= 3) { say("Up to three funds can be added."); return; }
      state.f.push(f.id);
      say(f.name + " added.");
      showState();
      run();
    });

  // --- loading -------------------------------------------------------------------------
  // Each fund's NAV file, at most eight at a time, counting as they come (§4.10).
  function loadAll(funds, live) {
    var results = new Map(), queue = funds.slice(), active = 0, done = 0;
    return new Promise(function (resolve) {
      function next() {
        if (!queue.length && !active) { resolve(results); return; }
        while (active < 8 && queue.length) {
          (function (f) {
            active += 1;
            var got = f.amfi ? K.navSeries(BASE, f) : Promise.reject(new Error("no file"));
            got.then(function (s) { results.set(f.id, s); }, function () { results.set(f.id, null); })
              .then(function () {
                active -= 1; done += 1;
                if (live() && funds.length > 1) say("Loaded " + done + " of " + funds.length + " funds");
                next();
              });
          })(queue.shift());
        }
      }
      next();
    });
  }

  // --- the answer ------------------------------------------------------------------------
  function run() {
    history.replaceState(null, "", location.pathname + writeHash(state));
    var mine = ++generation;
    var live = function () { return mine === generation; };
    var all = Array.from(FUNDS.values());
    var ofKind = all.filter(function (f) { return f.category === state.c && f.plan !== "regular"; });
    var index = M.indexFor(all.filter(function (f) { return f.plan !== "regular"; }), state.c);
    var extra = state.f.map(function (id) { return FUNDS.get(id); });
    var wanted = ofKind.concat(index ? [index.fund] : [], extra).filter(function (f, i, list) {
      return list.indexOf(f) === i;
    });
    out("answer").setAttribute("aria-busy", "true");
    out("answer-box").classList.add("sip__answer--busy");
    return loadAll(wanted, live).then(function (series) {
      if (!live()) return;
      out("answer").removeAttribute("aria-busy");
      out("answer-box").classList.remove("sip__answer--busy");
      say("");
      draw(ofKind, index, extra, series);
      overview();
    });
  }

  function draw(ofKind, index, extra, series) {
    var kindSeries = new Map(ofKind.map(function (f) { return [f.id, series.get(f.id)]; }));
    var v = M.valuationDate(kindSeries);
    var name = lower(kindName());
    if (!v) {
      fill(out("answer"), el("p", { "class": "sip__lead" }, "The prices of these funds did not load."));
      sections(false);
      notIn(ofKind.map(function (f) { return { fund: f, reason: "load" }; }), null, kindSeries);
      return;
    }
    chips(ofKind, kindSeries, v.valuedOn);
    var paise = M.toPaise(state.a) && M.toPaise(state.a) <= M.SIP_MAX_PAISE ? M.toPaise(state.a) : null;
    var w = M.windowOf({ mode: state.m, amountPaise: paise, years: state.y, from: state.from, day: state.d }, v.valuedOn);
    if (w.error === "after") {
      fieldError("from", "Choose a date before " + M.day(v.valuedOn) + ", the latest date with prices.", fromBox);
      return;
    }
    fieldError("from", "", fromBox);
    if (w.error) return;
    var pool = M.poolOf(ofKind, kindSeries, w, v.valuedOn);
    var outcomes = pool.inRange.map(function (f) {
      return Object.assign({ fund: f }, M.outcome(w.buys, kindSeries.get(f.id), v.valuedOn));
    });
    var r = M.spread(outcomes);
    // The index fund and added funds: valued on the same date, where they could take
    // every instalment.
    function eligible(f) {
      var both = new Map(kindSeries);
      both.set(f.id, series.get(f.id));
      var p = M.poolOf([f], both, w, v.valuedOn);
      return p.inRange.length ? null : p.out[0].reason;
    }
    var idx = index && !eligible(index.fund) && index.fund.plan !== "regular"
      ? Object.assign({ fund: index.fund, sharedBy: index.sharedBy }, M.outcome(w.buys, series.get(index.fund.id), v.valuedOn))
      : null;
    var adds = extra.map(function (f) {
      var why = eligible(f);
      return why ? { fund: f, why: why, series: series.get(f.id) }
        : Object.assign({ fund: f }, M.outcome(w.buys, series.get(f.id), v.valuedOn));
    });
    answer(w, v, r, name, idx, adds, pool, kindSeries);
    notIndex(index, idx, name, w);
    if (r.n >= 3) {
      sections(true);
      // The answer is painted first; the charts follow, once charts.js is there
      // (it loads after this file, §4.10).
      var mine = generation;
      var charts = function () {
        if (mine !== generation) return;
        path(w, v, outcomes, r, idx, adds.filter(function (a) { return !a.why; }), series);
        ends(w, v, r, idx, adds.filter(function (a) { return !a.why; }), pool, kindSeries);
      };
      setTimeout(function () { withCharts(charts); }, 0);
    } else {
      sections(r.n > 0);
      fill(out("path"));
      fill(out("ends"), r.n ? endsTable(w, v, r, idx, []) : null, outList(pool.out, w, kindSeries));
    }
  }

  function sections(on) { page.querySelectorAll("[data-sip-section]").forEach(function (s) { s.hidden = !on; }); }

  // A period no fund of this kind reaches is not offered (§4.2).
  function chips(ofKind, kindSeries, valuedOn) {
    var firsts = ofKind.map(function (f) { var s = kindSeries.get(f.id); return s && s.dates.length ? s.dates[0] : null; })
      .filter(Boolean).sort();
    form.querySelectorAll('input[name="period"]').forEach(function (input) {
      if (input.value === "from") return;
      var w = M.windowOf({ mode: state.m, amountPaise: 100, years: Number(input.value), day: state.d }, valuedOn);
      var none = !w.first || !firsts.length || firsts[0] > w.first;
      input.disabled = none;
      input.closest("label").title = none ? "No fund of this kind has prices back " + years(Number(input.value)) + "." : "";
    });
    if (firsts.length) fromBox.min = state.m === "sip" ? firsts[0].slice(0, 7) : firsts[0];
  }

  function answer(w, v, r, name, idx, adds, pool, kindSeries) {
    var box = out("answer");
    var today = M.localDay(new Date());
    var behind = (Date.parse(today) - Date.parse(v.valuedOn)) / 86400000 > 7
      ? "Prices on this site run to " + M.day(v.valuedOn) + ". " : "";
    var each = rupees(w.buys[0].paise);
    var put = w.buys.reduce(function (s, b) { return s + b.paise; }, 0);
    var what = state.m === "sip"
      ? each + " a month " + (state.y ? "for " + years(state.y) : "from " + month(w.first))
      : each + " once, " + (state.y ? years(state.y) + " ago" : "on " + M.day(w.first));
    var how = state.m === "sip"
      ? " — " + w.count + " instalment" + (w.count === 1 ? "" : "s") + " from " + M.day(w.first) + " to " +
        M.day(w.last) + ", " + rupees(put) + " put in — "
      : (state.y ? " (on " + M.day(w.first) + ") " : " ");
    if (r.n === 0) {
      var firsts = pool.out.map(function (o) { var s = kindSeries.get(o.fund.id); return s && s.dates.length ? s.dates[0] : null; })
        .filter(Boolean).sort();
      fill(box, el("p", { "class": "sip__lead" }, behind + (firsts.length
        ? kindName() + " funds have prices from " + M.day(firsts[0]) + " at the earliest. A shorter period includes more of them."
        : "No " + name + " fund has prices to show.")));
      return;
    }
    if (r.n < 3) {
      fill(box,
        el("p", { "class": "sip__lead" }, behind + "Only " + r.n + " " + name + " fund" + (r.n === 1 ? " has" : "s have") +
          " prices back to " + M.day(w.first) + "; a range needs at least three."),
        el.apply(null, ["ul", { "class": "sip__lines" }].concat(r.sorted.map(function (o) {
          return el("li", null, el("a", { href: fundPage(o.fund) }, o.fund.name), ": " + rupees(o.valuePaise) + ", " +
            returnText(o, w.first, v.valuedOn));
        }))),
        addedLines(adds, w, v));
      return;
    }
    var lead = el("p", { "class": "sip__lead" }, behind,
      el("strong", null, what), how, "would be worth ",
      el("strong", null, "between " + rupees(r.min.valuePaise) + " and " + rupees(r.max.valuePaise)),
      " on " + M.day(v.valuedOn) + " in the " + r.n + " " + name + " funds with prices back that far. ",
      el("strong", null, "The middle of them: " + rupees(r.middle.valuePaise) + ", " + returnText(r.middle, w.first, v.valuedOn) + "."));
    function tile(label, o) {
      return el("div", { "class": "pf__tile" }, el("dt", null, label),
        el("dd", null, rupees(o.valuePaise), el("span", { "class": "pf__per" }, returnText(o, w.first, v.valuedOn))));
    }
    var along = r.belowEver === 0
      ? "None of the " + r.n + " was ever worth less than had been put in by then."
      : (state.m === "sip"
        ? r.belowEver + " of the " + r.n + " were at some point worth less than had been put in by then. "
        : r.belowEver + " of the " + r.n + " at some point fell below the " + rupees(put) + " put in. ") +
        (r.middle.low < 0 ? "The middle fund at its lowest: " + pct(r.middle.low) + " below, on " + M.day(r.middle.lowOn) + "."
          : "The middle fund was never below it.");
    fill(box, lead,
      idx && el("p", { "class": "sip__index" }, "In " + idx.fund.name + ", the index fund on the benchmark of " +
        idx.sharedBy + " of these funds: " + rupees(idx.valuePaise) + ", " + returnText(idx, w.first, v.valuedOn) + "."),
      el("dl", { "class": "pf__tiles sip__tiles" }, tile("Lowest", r.min), tile("Middle", r.middle), tile("Highest", r.max)),
      addedLines(adds, w, v),
      el("p", { "class": "sip__along" }, el("strong", null, "Along the way: "), along));
  }

  function addedLines(adds, w, v) {
    if (!adds.length) return null;
    return el.apply(null, ["ul", { "class": "sip__lines" }].concat(adds.map(function (a) {
      var why = a.why === "later" ? "its prices begin on " + M.day(a.series.dates[0]) + ", after the first instalment"
        : a.why === "stale" ? "it has no price since " + M.day(a.series.dates[a.series.dates.length - 1])
        : a.why === "load" ? "its prices did not load" : null;
      return el("li", null, el("a", { href: fundPage(a.fund) }, a.fund.name),
        why ? ": " + why + ", so it could not take the same money." :
        ": " + rupees(a.valuePaise) + ", " + returnText(a, w.first, v.valuedOn));
    })));
  }

  function notIndex(index, idx, name, w) {
    var li = out("no-index");
    li.hidden = !!idx;
    li.textContent = idx ? "" : index
      ? index.fund.name + ", the index fund on the benchmark of " + index.sharedBy + " of these funds, has no prices back to " +
        M.day(w.first) + ", so it is not shown."
      : "No index fund follows the benchmark of " + name + " funds here.";
  }

  // ECharts and charts.js, fetched only once an answer is on the page (§4.10): the
  // answer needs neither, and on a slow phone the 1.1 MB held it back two seconds.
  var chartsReady = null;
  function script(src) {
    return new Promise(function (resolve, reject) {
      var s = el("script", { src: src });
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  function withCharts(draw) {
    if (!chartsReady) {
      chartsReady = script(BASE + "/static/vendor/echarts.v6.1.0.min.js")
        .then(function () { return script(BASE + "/static/charts.js"); });
    }
    chartsReady.then(draw, function () { chartsReady = null; say("The charts did not load; the tables below hold the same figures."); });
  }

  // --- chart 1: what it was worth, month by month (§4.6.3) ----------------------------
  function path(w, v, outcomes, r, idx, adds, series) {
    var step = (Date.parse(v.valuedOn) - Date.parse(w.first)) / 86400000 < 3 * 365 ? "week" : "month";
    var paths = outcomes.map(function (o) { return M.pathOf(w.buys, series.get(o.fund.id), v.valuedOn, step); });
    var grid = paths[0].points.map(function (p) { return p[0]; });
    var putIn = paths[0].putIn;
    var put = grid.map(function (g) {
      var last = 0;
      putIn.forEach(function (x) { if (x[0] <= g) last = x[1]; });
      return last;
    });
    var band = grid.map(function (g, i) {
      var vals = paths.map(function (p) { return p.points[i][1]; }).sort(function (a, b) { return a - b; });
      return [g, vals[0], vals[Math.floor((vals.length - 1) / 2)], vals[vals.length - 1]];
    });
    var others = (idx ? [{ o: idx, role: "index", hue: 1 }] : []).concat(adds.map(function (a, i) {
      return { o: a, role: "added", hue: i + 2 };
    })).map(function (x) {
      return { x: x, pts: M.pathOf(w.buys, series.get(x.o.fund.id), v.valuedOn, step).points };
    });
    var r2 = function (p) { return String(Math.round(p / 100)); };
    var spec = { charts: [{ kind: "band", title: "What it was worth", legend: true,
      putIn: { name: "Put in", points: putIn.map(function (p) { return [p[0], r2(p[1]), rupees(p[1])]; }) },
      band: { name: "Range of the " + r.n + " funds", points: band.map(function (b) {
        return [b[0], r2(b[1]), r2(b[3]), rupees(b[1]) + " to " + rupees(b[3])];
      }) },
      lines: [{ name: "Middle on each date (not one fund)", role: "middle", hue: 0,
                points: band.map(function (b) { return [b[0], r2(b[2]), rupees(b[2])]; }) }]
        .concat(others.map(function (s) {
          return { name: s.x.o.fund.name, role: s.x.role, hue: s.x.hue,
                   points: s.pts.map(function (p) { return [p[0], r2(p[1]), rupees(p[1])]; }) };
        })) }] };
    var data = el("script", { type: "application/json", "class": "echart-data" });
    data.textContent = JSON.stringify(spec);
    var label = out("answer").textContent.replace(/\s+/g, " ").trim();
    var head = [step === "week" ? "Week to" : "Month to", "Put in", "Lowest", "Middle", "Highest"]
      .concat(others.map(function (s) { return s.x.o.fund.name; }));
    var rows = band.map(function (b, i) {
      return [M.day(b[0]), rupees(put[i]), rupees(b[1]), rupees(b[2]), rupees(b[3])]
        .concat(others.map(function (s) { return rupees(s.pts[i] ? s.pts[i][1] : 0); }));
    }).reverse();
    var box = out("path");
    fill(box,
      el("div", { "class": "echarts", "data-chart": "echart" },
        el("figure", { "class": "echart echart--band" },
          el("div", { "class": "echart__canvas", "data-index": "0", role: "img", "aria-label": label })), data),
      el("details", { "class": "chart-table" }, el("summary", null, "As a table"),
        K.table("What it was worth, " + (step === "week" ? "week" : "month") + " by " + (step === "week" ? "week" : "month"),
          head, rows, { numeric: head.map(function (h, i) { return i > 0; }) })));
    if (window.Charts) window.Charts.draw(box);
  }

  // --- chart 2: where each fund ended (§4.6.4) -----------------------------------------
  function ends(w, v, r, idx, adds, pool, kindSeries) {
    var mark = function (o) {
      return o === r.middle ? "middle" : idx && o.fund.id === idx.fund.id ? "index" : null;
    };
    var caption = function (o) {
      return rupees(o.valuePaise) + " · " + returnText(o, w.first, v.valuedOn) + " · lowest: " + lowText(o).toLowerCase() +
        (o.fund.labels && o.fund.labels.ter ? " · expense ratio " + o.fund.labels.ter : "");
    };
    var points = r.sorted.slice().sort(function (a, b) { return a.fund.id < b.fund.id ? -1 : 1; }).map(function (o) {
      return { name: o.fund.name, x: Math.round(o.valuePaise / 100), caption: caption(o), mark: mark(o),
               href: fundPage(o.fund) };
    });
    if (idx && !r.sorted.some(function (o) { return o.fund.id === idx.fund.id; })) {
      points.push({ name: idx.fund.name, x: Math.round(idx.valuePaise / 100), caption: caption(idx), mark: "index", href: fundPage(idx.fund) });
    }
    adds.forEach(function (a, i) {
      points.push({ name: a.fund.name, x: Math.round(a.valuePaise / 100), caption: caption(a), mark: "added", hue: i + 2,
                    href: fundPage(a.fund) });
    });
    var put = w.buys.reduce(function (s, b) { return s + b.paise; }, 0);
    var spec = { charts: [{ kind: "dots", title: "Where each fund ended", putIn: Math.round(put / 100),
                            putInLabel: "Put in " + rupees(put), points: points }] };
    var data = el("script", { type: "application/json", "class": "echart-data" });
    data.textContent = JSON.stringify(spec);
    var box = out("ends");
    fill(box,
      el("p", { "class": "sip__note" }, "One dot a fund. The ring is the middle fund" + (idx ? ", the diamond the index fund" : "") +
        (adds.length ? ", and the named ones are the funds you added" : "") + ". Each opens its page."),
      el("div", { "class": "echarts", "data-chart": "echart" },
        el("figure", { "class": "echart echart--dots" },
          el("div", { "class": "echart__canvas", "data-index": "0", role: "img",
                      "aria-label": "Where each of the " + r.n + " funds ended: from " + rupees(r.min.valuePaise) +
                        " to " + rupees(r.max.valuePaise) + ", the middle " + rupees(r.middle.valuePaise) +
                        ", against " + rupees(put) + " put in." })), data),
      el("details", { "class": "chart-table" }, el("summary", null, "All " + r.n + " funds as a table"),
        endsTable(w, v, r, idx, adds)),
      outList(pool.out, w, kindSeries));
    if (window.Charts) window.Charts.draw(box);
  }

  // Every fund in the range, none hidden: worth first, the middle and the index fund
  // marked in words (§4.6.4).
  function endsTable(w, v, r, idx) {
    var rows = r.sorted.slice().reverse().map(function (o) {
      var tag = o === r.middle ? " · middle" : idx && o.fund.id === idx.fund.id ? " · index fund" : "";
      return [[el("a", { href: fundPage(o.fund) }, o.fund.name), tag], rupees(o.valuePaise),
              returnText(o, w.first, v.valuedOn), lowText(o),
              (o.fund.labels && o.fund.labels.ter) || "—", (o.fund.labels && o.fund.labels.size) || "—"];
    });
    return K.table("The " + r.n + " funds, by what the money would be worth",
      ["Fund", "Worth", "Return", "Lowest point", "Expense ratio", "Fund size"], rows,
      { numeric: [0, 1, 1, 0, 1, 1] });
  }

  // §4.4. Every fund of the kind not in the range, grouped by why; a Retry for those
  // whose prices did not load.
  function outList(left, w, kindSeries) {
    if (!left.length) return null;
    var groups = { later: [], stale: [], load: [] };
    left.forEach(function (o) { groups[o.reason].push(o.fund); });
    var items = [];
    if (groups.later.length) {
      items.push(el("li", null, el("strong", null, "Started after " + M.day(w.first) + ": "),
        groups.later.map(function (f) { return f.name + " (from " + M.day(kindSeries.get(f.id).dates[0]) + ")"; }).join(", ")));
    }
    groups.stale.forEach(function (f) {
      var s = kindSeries.get(f.id);
      items.push(el("li", null, el("strong", null, "No price since " + M.day(s.dates[s.dates.length - 1]) + ": "), f.name));
    });
    if (groups.load.length) {
      items.push(el("li", null, el("strong", null, "Its prices did not load: "),
        groups.load.map(function (f) { return f.name; }).join(", "), " ",
        el("button", { type: "button", "class": "button button--quiet", "data-retry": true }, "Retry")));
    }
    return el("details", { "class": "chart-table" },
      el("summary", null, left.length + " fund" + (left.length === 1 ? "" : "s") + " not in the range, and why"),
      el.apply(null, ["ul", { "class": "sip__out" }].concat(items)));
  }

  // --- the same money in other kinds of fund (§5.1) -----------------------------------
  // data/sip/kinds.json, written by the build (src/m2_fund/sip.py) for ₹1,000 a month
  // and ₹1,00,000 once on the 5th, scaled here. Fetched once an answer is up: the
  // answer does not wait for it. No fund is named: these are ranges of kinds.
  var kindsFile = null, opened = {};
  function overview() {
    var box = page.querySelector("[data-sip-kinds]");
    if (!kindsFile) {
      kindsFile = fetch(BASE + "/data/sip/kinds.json").then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).then(function (j) {
        if (j.version !== 1) throw new Error("version " + j.version);
        return j;
      });
    }
    var mine = generation;
    kindsFile.then(function (j) {
      if (mine === generation) { box.hidden = false; drawKinds(j); }
    }, function () {
      kindsFile = null;
      box.hidden = false;
      fill(out("kinds"), el("p", { "class": "sip__note" }, "The comparison of kinds did not load."));
    });
  }

  function drawKinds(j) {
    var paise = M.toPaise(state.a);
    if (state.from || state.d !== j.day || !paise || paise > M.SIP_MAX_PAISE) {
      fill(out("kinds"), el("p", { "class": "sip__note" },
        "For SIPs on the 5th, over standard periods. Choose one to compare kinds."));
      return;
    }
    var unit = j.unit[state.m], period = String(state.y);
    var scale = function (worth) { return scaled(worth, unit, paise); };
    var rows = [];
    j.kinds.forEach(function (k) {
      var option = kind.querySelector('option[value="' + k.category + '"]');
      if (option) rows.push({ k: k, w: k[state.m][period], family: option.parentNode.label });
    });
    var ranged = rows.filter(function (r) { return r.w; });
    if (!ranged.length) { fill(out("kinds"), el("p", { "class": "sip__note" }, "No kind has three funds with prices back that far.")); return; }
    var putIn = ranged[0].w.count * paise;
    // One ₹ axis for every kind, from the lowest of them (or what was put in) to the highest.
    var lo = Math.min.apply(null, ranged.map(function (r) { return scale(r.w.min); }).concat(putIn));
    var hi = Math.max.apply(null, ranged.map(function (r) { return scale(r.w.max); }));
    var at = function (p) { return ((p - lo) / (hi - lo || 1) * 100).toFixed(2) + "%"; };
    function mark(cls, p) { var m = el("span", { "class": "sip__bar-" + cls }); m.style.left = at(p); return m; }
    function row(r) {
      var w = r.w, k = r.k, current = k.category === state.c;
      var head = el("div", { "class": "sip__krow-head" },
        el("button", { type: "button", "class": "sip__krow-name", "data-kind": k.category,
                       "aria-current": current ? "true" : null }, k.name),
        el("span", { "class": "sip__krow-count" },
          (w ? w.eligible + " of " : "") + k.funds + " fund" + (k.funds === 1 ? "" : "s")));
      var body = [el("p", { "class": "sip__krow-about" }, k.about)];
      if (!w) {
        body.push(el("p", { "class": "sip__krow-figs" }, "No range: fewer than 3 funds of this kind have prices for the whole period."));
      } else {
        var range = el("span", { "class": "sip__bar-range" });
        range.style.left = at(scale(w.min));
        range.style.width = ((scale(w.max) - scale(w.min)) / (hi - lo || 1) * 100).toFixed(2) + "%";
        var low = Number(w.middle_low);
        body.push(
          el("div", { "class": "sip__bar", "aria-hidden": "true" }, range, mark("putin", putIn),
            mark("mid", scale(w.middle)), w.index ? mark("index", scale(w.index.worth)) : null),
          el("p", { "class": "sip__krow-figs" },
            el("strong", null, "about " + rupees(scale(w.middle))), " in the middle · ",
            low < 0 ? "middle at its lowest: " + pct(low) + " below" : "the middle never below what was put in",
            el("span", { "class": "sr-only" }, ". From about " + rupees(scale(w.min)) + " to about " +
              rupees(scale(w.max)) + (w.index ? "; its index fund about " + rupees(scale(w.index.worth)) : "") + ".")));
      }
      return el.apply(null, ["li", { "class": "sip__krow" + (current ? " sip__krow--current" : "") }, head].concat(body));
    }
    // Each family's three kinds holding the most money first, the rest a tap away.
    var families = [];
    rows.forEach(function (r) {
      var f = families.length && families[families.length - 1].name === r.family ? families[families.length - 1] : null;
      if (!f) families.push(f = { name: r.family, rows: [] });
      f.rows.push(r);
    });
    var blocks = families.map(function (f) {
      f.rows.sort(function (a, b) {
        return (Number(b.k.assets) || 0) - (Number(a.k.assets) || 0) || (a.k.name < b.k.name ? -1 : 1);
      });
      var shown = opened[f.name] ? f.rows : f.rows.slice(0, 3);
      var list = el.apply(null, ["ul", { "class": "sip__kinds" }].concat(shown.map(row)));
      var more = f.rows.length > shown.length
        ? el("button", { type: "button", "class": "button button--quiet", "data-family": f.name },
            "Show all " + f.rows.length + " kinds")
        : null;
      return el("div", { "class": "sip__family", "data-family-of": f.name }, el("h3", null, f.name), list, more);
    });
    // Each kind is valued on its own latest prices, as choosing it would be.
    var dates = ranged.map(function (r) { return r.k.valued_on; }).sort();
    var on = dates[0] === dates[dates.length - 1] ? M.day(dates[0])
      : M.day(dates[0]) + " to " + M.day(dates[dates.length - 1]);
    var how = state.m === "sip"
      ? rupees(paise) + " a month for " + years(state.y) + ", " + rupees(putIn) + " put in"
      : rupees(paise) + " once, " + years(state.y) + " ago";
    fill.apply(null, [out("kinds"),
      el("p", { "class": "sip__note" }, how + ", in every kind of fund, valued on " + on +
        ". Worked out for ₹1,000 a month (₹1,00,000 once) and scaled, so each figure is about, to the nearest ₹100. Choose a kind for its exact range."),
      el("p", { "class": "sip__note sip__key", "aria-hidden": "true" },
        el("span", { "class": "sip__key-range" }), " lowest to highest  ",
        el("span", { "class": "sip__key-mid" }), " the middle fund  ",
        el("span", { "class": "sip__key-index" }), " the index fund  ",
        el("span", { "class": "sip__key-putin" }), " put in"),
      el("div", { "class": "sip__axis", "aria-hidden": "true" },
        el("span", null, "about " + rupees(lo)), el("span", null, "about " + rupees(hi)))].concat(blocks));
  }

  // --- start -------------------------------------------------------------------------
  var asked = parseHash(location.hash);
  state = asked.state;
  fetch(BASE + "/funds.json").then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (list) {
    list.forEach(function (f) { FUNDS.set(f.id, f); });
    var notes = [];
    if (asked.notes.indexOf("amount") >= 0) notes.push("The link's amount could not be read, so ₹5,000 is shown.");
    state.f = state.f.filter(function (id) {
      if (FUNDS.has(id)) return true;
      notes.push(id + " is not published here, so it was left out.");
      return false;
    });
    var known = function (c) { return c && !!kind.querySelector('option[value="' + c + '"]'); };
    if (!known(state.c)) {
      var first = state.f.length && FUNDS.get(state.f[0]).category;
      // Else the kind the server chose and preloaded (publish_site.sip_opening).
      state.c = known(first) ? first : kind.value;
    }
    form.querySelectorAll("input, select").forEach(function (x) { x.disabled = false; });
    showState();
    say(notes.join(" "));
    run();
  }, function () {
    say("The list of funds did not load. Reload the page to try again.");
  });
})();
