/*
 * Compare two to four funds (DECISIONS V1-85).
 *
 * The page is a shell (compare.html); this fills it in the browser from files
 * the site already publishes: funds.json (figures and their Python-formatted
 * labels), each fund's NAV file and its look-through file. The chosen funds live
 * in the address (#f=ISIN,ISIN), so a comparison is just its link; nothing is
 * stored. The pure functions below are exported for `node --test`.
 */
(function () {
  "use strict";

  var ISIN = /^[A-Z0-9]{12}$/;
  var MAX = 4;

  // The funds named in the address: trimmed, upper-cased, ISIN-shaped, each once,
  // at most four, in the order given.
  function parseHash(hash) {
    var m = /^#?f=(.*)$/.exec(hash || "");
    if (!m) return [];
    var out = [];
    m[1].split(",").forEach(function (part) {
      var id;
      try { id = decodeURIComponent(part).trim().toUpperCase(); } catch (e) { return; }
      if (ISIN.test(id) && out.indexOf(id) < 0 && out.length < MAX) out.push(id);
    });
    return out;
  }

  function writeHash(ids) { return ids.length ? "#f=" + ids.join(",") : ""; }

  // The latest first price among the funds: the first date all of them have one.
  function sharedStart(funds) {
    var dates = funds.map(function (f) { return f.prices_from; }).filter(Boolean).sort();
    return dates.length ? dates[dates.length - 1] : null;
  }

  // What Rs 10,000 put in on the first price on or after `startIso` became on each
  // later price date: 10000 x NAV / the starting NAV.
  function growthSeries(series, startIso) {
    var i = 0;
    while (i < series.dates.length && series.dates[i] < startIso) i++;
    if (i >= series.dates.length) return [];
    var base = Number(series.navs[i]);
    var out = [];
    for (var j = i; j < series.dates.length; j++) {
      out.push([series.dates[j], 10000 * Number(series.navs[j]) / base]);
    }
    return out;
  }

  // "highest" and "lowest" for the extremes of a row, ties included; nothing when
  // fewer than two values are known or all are equal. Text, never a verdict.
  function highLow(values) {
    var known = values.filter(function (v) { return v != null; });
    if (known.length < 2) return values.map(function () { return null; });
    var hi = Math.max.apply(null, known), lo = Math.min.apply(null, known);
    if (hi === lo) return values.map(function () { return null; });
    return values.map(function (v) {
      return v == null ? null : v === hi ? "highest" : v === lo ? "lowest" : null;
    });
  }

  // The number a label shows ("₹1,01,793 Cr", "+15.4% p.a.", "0.71"), so the
  // high/low tags compare what the reader sees: two funds showing 0.71 tie.
  function shownFigure(text) {
    if (text == null) return null;
    var n = parseFloat(String(text).replace(/[−–]/g, "-").replace(/[^0-9.\-]/g, ""));
    return isNaN(n) ? null : n;
  }

  // Companies (not cash, receivables or unresolved rows) held by at least two of
  // the funds, with each fund's weight, by combined weight.
  function commonHoldings(files, ids) {
    var byIssuer = new Map();
    ids.forEach(function (id, k) {
      var file = files[id];
      if (!file) return;
      file.holdings.forEach(function (h) {
        if (h[0].indexOf("__") === 0) return;
        var row = byIssuer.get(h[0]);
        if (!row) {
          row = { issuer: h[0], name: h[1], weights: ids.map(function () { return null; }), total: 0 };
          byIssuer.set(h[0], row);
        }
        row.weights[k] = (row.weights[k] || 0) + Number(h[3]);
        row.total += Number(h[3]);
      });
    });
    return Array.from(byIssuer.values())
      .filter(function (r) { return r.weights.filter(function (w) { return w != null; }).length >= 2; })
      .sort(function (a, b) { return b.total - a.total || (a.name < b.name ? -1 : 1); });
  }

  // After a fund at `index` is removed: the column now in its place, else the new
  // last one, else none (the picker).
  function nextFocus(idsAfter, index) {
    return idsAfter.length ? idsAfter[Math.min(index, idsAfter.length - 1)] : null;
  }

  var api = {
    parseHash: parseHash, writeHash: writeHash, sharedStart: sharedStart,
    growthSeries: growthSeries, highLow: highLow, commonHoldings: commonHoldings,
    shownFigure: shownFigure, nextFocus: nextFocus, MAX: MAX,
  };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  window.Compare = api;

  // --- in the browser -----------------------------------------------------------
  // Built with createElement/textContent only, never innerHTML.
  var M = window.PortfolioMath, K = window.Kit;
  var page = document.querySelector("[data-compare]");
  if (!page || !M || !K) return;
  var el = K.el, fill = K.fill, bar = K.bar, CLASS = K.CLASS, INR = K.INR;

  var BASE = page.getAttribute("data-root") || "";
  var FUNDS = new Map();
  var BY_NAME = new Map();
  var ids = [];                 // the funds on show, in the address's order
  var generation = 0;           // the newest render; older ones do not draw

  function out(name) { return page.querySelector('[data-out="' + name + '"]'); }
  function note(text) { return el("p", { "class": "cmp__note" }, text); }
  function say(text) { document.getElementById("cmp-status").textContent = text; }

  // --- the address ----------------------------------------------------------------
  function read() {
    var asked = parseHash(location.hash);
    var unknown = asked.filter(function (id) { return !FUNDS.has(id); });
    ids = asked.filter(function (id) { return FUNDS.has(id); });
    if (unknown.length) {
      say("Not among the funds this site publishes, so left out: " + unknown.join(", ") + ".");
      history.replaceState(null, "", writeHash(ids) || location.pathname);
    }
  }
  function changed() {
    history.replaceState(null, "", writeHash(ids) || location.pathname);
    render();
  }
  function add(id) {
    var fund = FUNDS.get(id);
    if (ids.indexOf(id) >= 0) { say(fund.name + " is already on this page."); return; }
    if (ids.length >= MAX) { say("Up to four funds can be compared; remove one first."); return; }
    ids.push(id);
    changed();
    say(fund.name + " added.");
    // A chip is rebuilt by the render; keep the keyboard where it was working.
    var stay = document.querySelector(".cmp__chip") || document.getElementById("cmp-pick");
    if (document.activeElement === document.body) stay.focus();
  }

  page.addEventListener("change", function (e) {
    if (e.target.id !== "cmp-pick") return;
    var fund = BY_NAME.get(e.target.value);
    if (!fund) { say("No published fund has exactly that name; choose one from the list."); return; }
    e.target.value = "";
    add(fund.id);
  });
  page.addEventListener("click", function (e) {
    var b = e.target.closest("[data-add], [data-remove]");
    if (!b) return;
    if (b.hasAttribute("data-add")) { add(b.getAttribute("data-add")); return; }
    var gone = b.getAttribute("data-remove"), at = ids.indexOf(gone);
    ids = ids.filter(function (id) { return id !== gone; });
    changed();
    say(FUNDS.get(gone).name + " removed.");
    var next = nextFocus(ids, at);
    var target = next && page.querySelector('.cmp__remove[data-remove="' + next + '"]');
    (target || document.getElementById("cmp-pick")).focus();
  });
  window.addEventListener("hashchange", function () { say(""); read(); render(); });

  // --- suggestions ------------------------------------------------------------------
  var REASON = { ter: "lowest expense ratio", r3: "highest three-year return", size: "largest fund" };

  function suggest(funds) {
    var box = out("suggest");
    var first = funds[0];
    var picks = first && first.prices_from && funds.length < MAX
      ? M.alternatives(first, Array.from(FUNDS.values()), first.prices_from)
          .filter(function (s) { return ids.indexOf(s.fund.id) < 0; })
      : [];
    if (!picks.length) { fill(box); return; }
    var list = el("ul", { "class": "cmp__suggest" });
    picks.forEach(function (s) {
      list.appendChild(el("li", null, el("button", { type: "button", "class": "chip cmp__chip", "data-add": s.fund.id },
        s.fund.name, el("span", { "class": "cmp__why" }, s.reasons.map(function (r) { return REASON[r]; }).join(", ")))));
    });
    fill(box, el("p", { "class": "cmp__note" }, "Of the same category, by the rule beside each:"), list);
  }

  // --- 1. key facts and returns ------------------------------------------------------
  // [label, the shown text, the figure the high/low tags compare (tagged rows only):
  // the one shown, so the tags never disagree with the text]
  function raw(key, abs) {
    return function (f) {
      var n = shownFigure(f.labels[key]);
      return n != null && abs ? Math.abs(n) : n;
    };
  }
  function label(key) { return function (f) { return f.labels[key]; }; }
  var ROWS = [
    ["Fund house", function (f) { return f.house; }],
    ["Category", function (f) { return f.category_name; }],
    ["Fund size", label("size"), raw("size")],
    ["Expense ratio", label("ter"), raw("ter")],
    ["Prices from", label("prices_from")],
    ["Benchmark", function (f) { return f.benchmark; }],
    ["Return a year, 1 year", label("r1"), raw("r1")],
    ["Return a year, 3 years", label("r3"), raw("r3")],
    ["Return a year, 5 years", label("r5"), raw("r5")],
    ["Volatility, 3 years", label("vol3"), raw("vol3")],
    ["Deepest fall, 3 years", label("fall3"), raw("fall3", true)],
    ["Sharpe ratio, 3 years", label("sharpe3"), raw("sharpe3")],
    ["Rank in category, 3 years", function (f) { return f.rank3; }],
  ];

  function heading(f) {
    return el("th", { scope: "col" },
      el("span", { "class": "cmp__fund" },
        el("a", { href: BASE + "/fund/" + f.id + "/" }, f.name),
        el("button", { type: "button", "class": "cmp__remove", "data-remove": f.id,
                       "aria-label": "Remove " + f.name }, "×")));
  }

  function facts(funds) {
    var box = out("facts");
    if (!funds.length) { fill(box, note("Add a fund to compare, with the box above.")); return; }
    var head = el("tr", null, el("th", { scope: "col" }, ""));
    funds.forEach(function (f) { head.appendChild(heading(f)); });
    var body = el("tbody");
    ROWS.forEach(function (row) {
      var tags = row[2] ? highLow(funds.map(row[2])) : [];
      var tr = el("tr", null, el("th", { scope: "row" }, row[0]));
      funds.forEach(function (f, i) {
        var text = row[1](f);
        tr.appendChild(el("td", { "class": row[2] ? "num" : null }, text == null ? "—" : text,
          tags[i] && el("span", { "class": "cmp-tag" }, tags[i] + " here")));
      });
      body.appendChild(tr);
    });
    fill(box, el("div", { "class": "table-wrap" }, el("table", { "class": "cmp__table" }, el("thead", null, head), body)),
      funds.length === 1 && note("Add another fund to compare."));
  }

  // --- formatting -------------------------------------------------------------------
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  // DD Mon YYYY, as every date the server prints (§9.4).
  function day(iso) { return iso.slice(8, 10) + " " + MONTHS[Number(iso.slice(5, 7)) - 1] + " " + iso.slice(0, 4); }
  function pct(x) { return x.toFixed(1) + "%"; }
  function names(list) {
    return list.length < 2 ? list.join("") : list.slice(0, -1).join(", ") + " and " + list[list.length - 1];
  }

  // A table with a row heading first and the funds' cells after it.
  function table(head, rows) {
    var tr = el("tr");
    head.forEach(function (h) { tr.appendChild(el("th", { scope: "col" }, h)); });
    var body = el("tbody");
    rows.forEach(function (cells) {
      var row = el("tr", null, el("th", { scope: "row" }, cells[0]));
      cells.slice(1).forEach(function (c) { row.appendChild(el("td", { "class": "num" }, c)); });
      body.appendChild(row);
    });
    return el("div", { "class": "table-wrap" }, el("table", { "class": "cmp__table" }, el("thead", null, tr), body));
  }
  // The first `shown` rows, and the rest behind "N more".
  function tucked(head, rows, shown) {
    var more = rows.slice(shown);
    return [table(head, rows.slice(0, shown)),
      more.length && el("details", { "class": "tuck" }, el("summary", null, more.length + " more"), table(head, more))];
  }

  // --- 2. what Rs 10,000 became ----------------------------------------------------------
  function drawGrowth(funds, live) {
    return Promise.all(funds.map(function (f) {
      return f.amfi ? K.navSeries(BASE, f).catch(function () { return null; }) : null;
    })).then(function (series) {
      if (!live()) return;
      var box = out("growth");
      var old = box.querySelector(".echart__canvas");
      var chart = old && window.echarts && window.echarts.getInstanceByDom(old);
      if (chart) chart.dispose();
      var priced = funds.filter(function (f, i) { return series[i] && series[i].dates.length; });
      var start = sharedStart(priced);
      var lines = [], ended = [], unloaded = [];
      funds.forEach(function (f, i) {
        if (priced.indexOf(f) < 0) { unloaded.push(f.name); return; }
        var pts = growthSeries(series[i], start);
        if (pts.length) lines.push({ f: f, pts: pts }); else ended.push(f.name);
      });
      function off(list, why) {
        return list.length && note(names(list) + " " + why + ", so " +
          (list.length === 1 ? "it is" : "they are") + " left off the chart.");
      }
      var notes = [off(ended, (ended.length === 1 ? "has" : "have") + " no prices here from " + day(start || "")),
                   off(unloaded, (unloaded.length === 1 ? "has" : "have") + " prices that did not load")];
      if (lines.length < 2) {
        fill.apply(null, [box, note("Fewer than two of these funds have prices from a shared date.")].concat(notes));
        return;
      }

      var ends = lines.map(function (l) { return l.pts[l.pts.length - 1]; });
      var sameEnd = ends.every(function (e) { return e[0] === ends[0][0]; });
      var headline = "₹10,000 put in on " + day(lines[0].pts[0][0]) + " became " + names(lines.map(function (l, i) {
        return INR.format(ends[i][1]) + " in " + l.f.name + (sameEnd ? "" : " by " + day(ends[i][0]));
      })) + (sameEnd ? " by " + day(ends[0][0]) : "") + ".";
      var spec = { charts: [{ kind: "line", y: "inr", title: "What ₹10,000 became", series: lines.map(function (l) {
        return { name: l.f.name, role: "fund", points: l.pts.map(function (pt) {
          return [pt[0], String(Math.round(pt[1])), INR.format(pt[1])];
        }) };
      }) }] };
      var data = el("script", { type: "application/json", "class": "echart-data" });
      data.textContent = JSON.stringify(spec);
      var container = el("div", { "class": "echarts", "data-chart": "echart" },
        el("figure", { "class": "echart echart--line" },
          el("div", { "class": "zoom", "data-zoom-slot": true, role: "group", "aria-label": "Show a period" }),
          el("div", { "class": "echart__canvas", "data-index": "0", role: "img", "aria-label": headline })),
        data);
      fill.apply(null, [box, el("p", { "class": "cmp__lead" }, headline), container,
        note("From " + day(start) + ", the first date all " + lines.length + " funds have prices.")].concat(notes));
      if (window.Charts) window.Charts.draw(box);   // draws the charts inside box
    });
  }

  // --- 3. overlap and 4. mix -------------------------------------------------------------

  function disclosures(funds, files) {
    var ul = el("ul", { "class": "cmp__note" });
    funds.forEach(function (f, i) {
      ul.appendChild(el("li", null, f.name + ": " + (files[i]
        ? "disclosed " + day(files[i].as_of) + (files[i].aggregator ? ", read from an aggregator's page" : "") + "."
        : "no holdings disclosed here.")));
    });
    return ul;
  }

  function drawOverlap(funds, files) {
    var box = out("overlap");
    var have = funds.filter(function (f, i) { return files[i]; });
    var fileOf = function (f) { return files[funds.indexOf(f)]; };
    if (have.length < 2) {
      fill(box, note("Fewer than two of these funds have holdings disclosed here."), disclosures(funds, files));
      return;
    }
    var shared = have.length === 2
      ? el("p", { "class": "cmp__lead" }, have[0].name + " and " + have[1].name + " have " +
          pct(M.overlap(fileOf(have[0]), fileOf(have[1]))) + " of their portfolios in the same companies.")
      : table([""].concat(have.map(function (f) { return f.name; })), have.map(function (a) {
          return [a.name].concat(have.map(function (b) {
            return a === b ? "—" : pct(M.overlap(fileOf(a), fileOf(b)));
          }));
        }));
    var byId = {};
    funds.forEach(function (f, i) { byId[f.id] = files[i]; });
    var common = commonHoldings(byId, funds.map(function (f) { return f.id; })).map(function (r) {
      return [r.name].concat(r.weights.map(function (w) { return w == null ? "—" : pct(w); }));
    });
    fill.apply(null, [box, shared,
      note("The share of two funds' portfolios in the same companies: 100% would be identical funds, 0% nothing in common."),
      el("h3", null, "Companies held by two or more of them")]
      .concat(common.length
        ? [note("Each figure is the company's share of that fund.")]
          .concat(tucked(["Company"].concat(funds.map(function (f) { return f.name; })), common, 15))
        : [note("No company is held by two of these funds.")])
      .concat([disclosures(funds, files)]));
  }

  function drawMix(funds, files) {
    var box = out("mix");
    if (!files.some(Boolean)) { fill(box, note("None of these funds has holdings disclosed here.")); return; }
    var head = [""].concat(funds.map(function (f) { return f.name; }));
    // One row per key any fund has, largest share in any fund first.
    function rows(pick) {
      var keys = [];
      var at = funds.map(function (f, i) {
        var m = new Map();
        (files[i] ? pick(files[i]) : []).forEach(function (kv) {
          m.set(kv[0], Number(kv[1]));
          if (keys.indexOf(kv[0]) < 0) keys.push(kv[0]);
        });
        return m;
      });
      var top = function (k) { return Math.max.apply(null, at.map(function (m) { return m.get(k) || 0; })); };
      return keys.sort(function (a, b) { return top(b) - top(a) || (a < b ? -1 : 1); }).map(function (k) {
        return [CLASS[k] || k].concat(at.map(function (m) { return m.has(k) ? bar(m.get(k)) : "—"; }));
      });
    }
    var sectors = rows(function (f) { return f.sectors; });
    fill.apply(null, [box, el("h3", null, "Asset mix"), note("Each figure is a share of the fund."),
      table(head, rows(function (f) { return f.mix; }))]
      .concat(sectors.length
        ? [el("h3", null, "Shares by sector"), note("Each figure is a share of the fund's shares.")]
          .concat(tucked(head, sectors, 8))
        : []));
  }

  // --- drawing -----------------------------------------------------------------------
  function render() {
    var funds = ids.map(function (id) { return FUNDS.get(id); });
    var mine = ++generation;
    var live = function () { return mine === generation; };
    suggest(funds);
    facts(funds);
    if (funds.length < 2) {
      ["growth", "overlap", "mix"].forEach(function (name) {
        fill(out(name), note(funds.length ? "Add another fund to compare." : "Shown once two funds are chosen."));
      });
      return;
    }
    drawGrowth(funds, live);
    Promise.all(funds.map(function (f) { return K.lookFile(BASE, f.id); })).then(function (files) {
      if (!live()) return;
      drawOverlap(funds, files);
      drawMix(funds, files);
    });
  }

  // --- start -------------------------------------------------------------------------
  // Only a failed fetch is "did not load"; a fault while drawing is not hidden.
  fetch(BASE + "/funds.json").then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (list) {
    var options = document.getElementById("cmp-funds");
    list.forEach(function (f) {
      FUNDS.set(f.id, f);
      BY_NAME.set(f.name, f);
      options.appendChild(el("option", { value: f.name }, f.category_name));
    });
    document.getElementById("cmp-pick").disabled = false;
    read();
    render();
  }, function () {
    say("The list of funds did not load; reload to try again.");
  });
})();
