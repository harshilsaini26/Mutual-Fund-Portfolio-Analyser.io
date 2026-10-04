/* Your portfolio (DECISIONS V1-82): entry, checks, storage and drawing.
 * The arithmetic is portfolio-math.js. Nothing entered leaves this browser:
 * it is kept in localStorage and, when asked, in a file the visitor saves.
 * Everything is built with createElement/textContent, never innerHTML.
 */
(function () {
  "use strict";
  var M = window.PortfolioMath;
  var page = document.querySelector("[data-portfolio]");
  if (!page || !M || !window.Kit) return;

  var BASE = page.getAttribute("data-root") || "";
  var KEY = "lookthrough.portfolio.v1";
  var TODAY = M.localDay(new Date());
  var ESTIMATE = "Worked out in your browser from published NAVs: an estimate of your holding, " +
    "not a statement. Fund houses round units differently, by up to 0.001 of a unit.";
  var FUNDS = new Map();
  var BY_NAME = new Map();
  var replacing = null;         // {id: held fund's ISIN, slot: 0..2} while "Replace" is picking
  var generation = 0;           // the newest results() run; older runs do not draw
  var state = { version: 1, funds: [] };
  var FUSE_MS = 4000;           // how long Undo is on offer after "Remove"
  var leaving = new Map();      // fund id -> its fuse (Kit.fuse) while Undo is on offer
  var ticking = null;           // the countdown's interval while any fund is leaving

  var K = window.Kit;
  var el = K.el, fill = K.fill, bar = K.bar, CLASS = K.CLASS, INR = K.INR;
  function rupees(paise) { return INR.format(Math.round(paise / 100)); }
  function pct(x, dp) { return x.toFixed(dp == null ? 1 : dp) + "%"; }
  function signedPct(fraction) {
    var v = fraction * 100;
    return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%";
  }

  function out(name) { return page.querySelector('[data-out="' + name + '"]'); }
  // A Regular plan shares its Direct plan's portfolio and page (funds.json `direct`).
  function fundPage(fund) { return BASE + "/fund/" + (fund.direct || fund.id) + "/"; }
  function say(text) { document.getElementById("pf-status").textContent = text; }
  function entries(n) { return n + (n === 1 ? " entry" : " entries"); }

  // --- storage ---------------------------------------------------------------
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); return true; }
    catch (e) { say("This browser is not keeping data for this site, so the portfolio lasts only while the page is open. Save to file to keep it."); return false; }
  }
  function restore() {
    var raw = null;
    try { raw = localStorage.getItem(KEY); } catch (e) { return; }
    if (!raw) return;
    var got;
    try { got = M.parsePortfolio(JSON.parse(raw)); } catch (e) { got = { error: "unreadable" }; }
    if (got.error) { say("The portfolio saved in this browser could not be read, so the page starts empty."); return; }
    state = got.portfolio;
    if (got.dropped) say(entries(got.dropped) + " saved in this browser could not be read and were left out.");
  }

  // --- data ------------------------------------------------------------------

  // --- entry -----------------------------------------------------------------
  function rowError(fund, kind, row) { return M.rowError(fund, kind, row, TODAY); }

  // Shows or clears one row's message in place, so editing a field never
  // rebuilds the form under the cursor.
  // The message is tied to the row's fields and read out when it appears (V1-88):
  // aria-invalid on each field, aria-describedby pointing at the message. Every row
  // is drawn with an empty polite live region, since one inserted already filled is
  // often not read out; an error only changes its text.
  var errors = 0;
  function errorSlot() {
    return el("p", { "class": "pf__error", id: "row-err-" + (++errors), "aria-live": "polite" });
  }
  function showRowError(rowNode, message) {
    var p = rowNode.querySelector(".pf__error");
    p.textContent = message || "";
    rowNode.querySelectorAll("input").forEach(function (f) {
      if (message) {
        f.setAttribute("aria-invalid", "true");
        f.setAttribute("aria-describedby", p.id);
      } else {
        f.removeAttribute("aria-invalid");
        f.removeAttribute("aria-describedby");
      }
    });
  }

  // A labelled field (V1-93); `prefix` sits inside it, before the figure (₹).
  function field(label, attrs, prefix) {
    var id = "pf-" + Math.random().toString(36).slice(2, 9);
    var input = el("input", Object.assign({ id: id }, attrs));
    return el("label", { "class": "pf__field", "for": id }, label,
      prefix ? el("span", { "class": "pf__affix" }, el("span", { "class": "pf__prefix" }, prefix), input) : input);
  }

  // A button that shows only an icon: its name is read out, and shown on hover.
  function iconButton(action, name, glyph) {
    return el("button", { type: "button", "class": "button button--icon", "data-action": action,
                          "aria-label": name, title: name }, K.icon(glyph));
  }

  function holdingCard(h, i) {
    var fund = FUNDS.get(h.id);
    var gone = leaving.get(h.id);
    var title = fund
      ? el("a", { href: fundPage(fund) }, fund.name)
      : el("span", null, h.id + " (no longer published here, so it is not valued)");
    var card = el("article", { "class": "pf__holding" + (gone ? " pf__holding--leaving" : ""), "data-fund": i },
      el("header", { "class": "pf__holding-head" },
        el("h3", null, title),
        gone ? undoButton(gone) : iconButton("remove-fund", "Remove " + nameOf(h.id), "bin")),
      gone && el("p", { "class": "pf__leaving", "data-leaving": h.id }, leftText(gone)));
    h.purchases.forEach(function (p, r) {
      var row = card.appendChild(el("div", { "class": "pf__row", "data-kind": "purchase", "data-row": r, inert: !!gone },
        field("Date", { type: "date", value: p.date, max: TODAY, min: fund ? fund.prices_from : null, "data-field": "date" }),
        field("Amount", { type: "text", inputmode: "decimal", value: p.amount, "data-field": "amount" }, "₹"),
        iconButton("remove-row", "Remove this lump sum", "close"),
        errorSlot()));
      showRowError(row, rowError(fund, "purchase", p));
    });
    h.sips.forEach(function (s, r) {
      var row = card.appendChild(el("div", { "class": "pf__row", "data-kind": "sip", "data-row": r, inert: !!gone },
        field("SIP a month", { type: "text", inputmode: "decimal", value: s.amount, "data-field": "amount" }, "₹"),
        field("Day", { type: "number", min: 1, max: 31, value: s.day, "data-field": "day" }),
        field("From", { type: "month", value: s.start, "data-field": "start" }),
        field("Until (blank if running)", { type: "month", value: s.stop || "", "data-field": "stop" }),
        iconButton("remove-row", "Remove this SIP", "close"),
        errorSlot()));
      showRowError(row, rowError(fund, "sip", s));
    });
    (h.sales || []).forEach(function (p, r) {
      var row = card.appendChild(el("div", { "class": "pf__row", "data-kind": "sale", "data-row": r, inert: !!gone },
        field("Sold on", { type: "date", value: p.date, max: TODAY, min: fund ? fund.prices_from : null, "data-field": "date" }),
        field("Received", { type: "text", inputmode: "decimal", value: p.amount, "data-field": "amount" }, "₹"),
        iconButton("remove-row", "Remove this sale", "close"),
        errorSlot()));
      showRowError(row, rowError(fund, "sale", p));
    });
    card.appendChild(el("p", { "class": "pf__add", inert: !!gone },
      el("button", { type: "button", "class": "button button--tinted", "data-action": "add-lump" },
        K.icon("plus"), "Add a lump sum"),
      el("button", { type: "button", "class": "button button--tinted", "data-action": "add-sip" },
        K.icon("plus"), "Add a SIP"),
      el("button", { type: "button", "class": "button button--tinted", "data-action": "add-sale" },
        K.icon("plus"), "Add a sale")));
    return card;
  }

  // --- removing a fund, with Undo (the design bucket's fuse-button, V1-93) ------
  // The fund stays, dimmed, while a line burns down its Undo button; only when
  // the fuse ends is it taken out. Undo or Esc keeps it.

  function nameOf(id) { var f = FUNDS.get(id); return f ? f.name : id; }
  function leftText(f) {
    var s = Math.ceil(f.remaining() / 1000);
    return "Removing in " + s + (s === 1 ? " second" : " seconds") + ". Undo or Esc keeps it.";
  }
  function undoButton(f) {
    var line = el("span", { "class": "fuse__line", "aria-hidden": "true" });
    line.style.animationDelay = (f.remaining() - FUSE_MS) + "ms";   // a redrawn card burns on from where it was
    return el("button", { type: "button", "class": "button button--quiet fuse", "data-action": "undo-remove" },
      K.icon("undo"), "Undo", line);
  }
  function focusIn(id, action) {
    var at = state.funds.findIndex(function (h) { return h.id === id; });
    var b = out("holdings").querySelector('[data-fund="' + at + '"] [data-action="' + action + '"]');
    if (b) b.focus();
  }
  function tick() {
    out("holdings").querySelectorAll("[data-leaving]").forEach(function (p) {
      var f = leaving.get(p.getAttribute("data-leaving"));
      if (f) p.textContent = leftText(f);
    });
    if (leaving.size && !ticking) ticking = setInterval(tick, 250);
    if (!leaving.size && ticking) { clearInterval(ticking); ticking = null; }
  }
  function arm(id) {
    leaving.set(id, K.fuse(FUSE_MS, function () {
      leaving.delete(id);
      var at = state.funds.findIndex(function (h) { return h.id === id; });
      if (at >= 0) {
        state.funds.splice(at, 1);
        stopReplacing();
        changed();
        say(nameOf(id) + " removed.");
      }
      tick();
    }));
    entry();
    focusIn(id, "undo-remove");
    say(nameOf(id) + " will be removed in " + FUSE_MS / 1000 + " seconds. Undo keeps it.");
    tick();
  }
  function undo(id) {
    var f = leaving.get(id);
    if (!f) return;
    f.cancel();
    leaving.delete(id);
    entry();
    focusIn(id, "remove-fund");
    say(nameOf(id) + " kept.");
    tick();
  }
  // A new portfolio (cleared or loaded) has nothing on its way out.
  function defuse() {
    leaving.forEach(function (f) { f.cancel(); });
    leaving.clear();
    tick();
  }
  page.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !leaving.size || e.target.id === "pf-pick") return;
    undo(Array.from(leaving.keys()).pop());
  });

  function entry() {
    var box = out("holdings");
    box.replaceChildren.apply(box, state.funds.map(holdingCard));
  }

  function changed() { save(); entry(); results(); }

  function listOf(h, kind) {
    return kind === "sip" ? h.sips : kind === "sale" ? (h.sales = h.sales || []) : h.purchases;
  }

  function stopReplacing() {
    replacing = null;
    document.getElementById("pf-pick-label").textContent = "Add a fund";
  }

  document.getElementById("pf-pick").addEventListener("keydown", function (e) {
    if (e.key === "Escape" && replacing) { stopReplacing(); say(""); }
  });

  function pick(name) {
    var fund = BY_NAME.get(name);
    var input = document.getElementById("pf-pick");
    if (!fund) { say("No published fund has exactly that name; choose one from the list."); return; }
    input.value = "";
    if (replacing) {
      var held = state.funds.filter(function (h) { return h.id === replacing.id; })[0];
      var slot = replacing.slot;
      stopReplacing();
      if (held) { held.alts[slot] = fund.id; changed(); }
      else { say("That fund is no longer in your portfolio, so nothing was changed."); }
      return;
    }
    if (state.funds.some(function (h) { return h.id === fund.id; })) { say(fund.name + " is already in your portfolio."); return; }
    state.funds.push({ id: fund.id, purchases: [{ date: "", amount: "" }], sips: [], sales: [], alts: [null, null, null] });
    say("");
    changed();
  }

  page.addEventListener("change", function (e) {
    var t = e.target;
    if (t.id === "pf-pick") { pick(t.value); return; }
    if (t.id === "pf-file") { loadFile(t.files[0]); t.value = ""; return; }
    var row = t.closest("[data-row]"), card = t.closest("[data-fund]");
    if (!row || !card || !t.dataset.field) return;
    var h = state.funds[Number(card.dataset.fund)];
    var item = listOf(h, row.dataset.kind)[Number(row.dataset.row)];
    item[t.dataset.field] = t.dataset.field === "day" ? (t.value === "" ? null : Number(t.value))
      : t.dataset.field === "stop" ? (t.value || null) : t.value;
    showRowError(row, rowError(FUNDS.get(h.id), row.dataset.kind, item));
    save();
    results();
  });

  page.addEventListener("click", function (e) {
    var b = e.target.closest("[data-action]");
    if (!b) return;
    var card = b.closest("[data-fund]");
    var h = card ? state.funds[Number(card.dataset.fund)] : null;
    var row = b.closest("[data-row]");
    switch (b.dataset.action) {
      case "add-lump": h.purchases.push({ date: "", amount: "" }); break;
      case "add-sip": h.sips.push({ amount: "", day: 1, start: TODAY.slice(0, 7), stop: null }); break;
      case "add-sale": (h.sales = h.sales || []).push({ date: "", amount: "" }); break;
      case "remove-row": listOf(h, row.dataset.kind).splice(Number(row.dataset.row), 1); break;
      case "remove-fund": arm(h.id); return;
      case "undo-remove": undo(h.id); return;
      case "replace":
        replacing = { id: b.dataset.held, slot: Number(b.dataset.slot) };
        document.getElementById("pf-pick-label").textContent = "Pick a fund to compare in this place (Esc to cancel)";
        document.getElementById("pf-pick").focus();
        return;
      case "save": saveFile(); return;
      case "load": document.getElementById("pf-file").click(); return;
      case "clear":
        if (window.confirm("Remove every fund and purchase from this page and this browser?")) {
          state = { version: 1, funds: [] };
          stopReplacing();
          defuse();
        } else { return; }
        break;
      default: return;
    }
    changed();
  });

  function saveFile() {
    var blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
    var a = el("a", { href: URL.createObjectURL(blob), download: "portfolio-" + TODAY + ".json" });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 0);
    say("Saved to a file in your downloads.");
  }

  function loadFile(file) {
    if (!file) return;
    file.text().then(function (text) {
      var got;
      try { got = M.parsePortfolio(JSON.parse(text)); } catch (e) { got = { error: "This is not a portfolio file from this site." }; }
      if (got.error) { say(got.error + " Your portfolio is unchanged."); return; }
      state = got.portfolio;
      stopReplacing();
      defuse();
      say("Loaded " + file.name + (got.dropped ? "; " + entries(got.dropped) + " could not be read and were left out." : "."));
      changed();
    });
  }

  // --- results ------------------------------------------------------------------
  function table(head, rows, numeric) {
    var thead = el("tr");
    head.forEach(function (h, i) { thead.appendChild(el("th", { scope: "col", "class": numeric[i] ? "num" : null }, h)); });
    var body = el("tbody");
    rows.forEach(function (cells) {
      var tr = el("tr");
      cells.forEach(function (c, i) { tr.appendChild(el("td", { "class": numeric[i] ? "num" : null }, c)); });
      body.appendChild(tr);
    });
    return el("div", { "class": "table-wrap" }, el("table", null, el("thead", null, thead), body));
  }

  function returnText(pos) {
    if (!pos.firstDate) return "—";
    if (M.showsXirr(pos.firstDate, pos.valueDate)) return pos.xirr == null ? "—" : signedPct(pos.xirr) + " a year";
    var gain = pos.investedPaise ? (pos.valuePaise + pos.redeemedPaise - pos.investedPaise) / pos.investedPaise : 0;
    return signedPct(gain) + " in total (under a year)";
  }

  function priced() {
    return Promise.all(state.funds.map(function (h) {
      var fund = FUNDS.get(h.id);
      if (!fund) return { h: h, fund: null, pos: null, error: "not published here" };
      if (!fund.amfi) return { h: h, fund: fund, pos: null, error: "its prices are not published" };
      var e = M.entriesOf(h, fund, TODAY);
      return K.navSeries(BASE, fund).then(function (s) {
        return { h: h, fund: fund, pos: M.position(e.buys, s, e.sales), excluded: e.excluded, error: null };
      }, function (err) { return { h: h, fund: fund, pos: null, excluded: e.excluded, error: err.message }; });
    }));
  }

  function summary(list) {
    var ok = list.filter(function (x) { return x.pos && x.pos.firstDate; });
    var box = out("summary");
    if (!ok.length) {
      box.replaceChildren(el("p", { "class": "pf__note" }, list.length
        ? "Nothing is valued yet; the funds table says why for each fund."
        : "Add a fund and a purchase to see what it is worth."));
      return;
    }
    var invested = ok.reduce(function (s, x) { return s + x.pos.investedPaise; }, 0);
    var value = ok.reduce(function (s, x) { return s + x.pos.valuePaise; }, 0);
    var redeemed = ok.reduce(function (s, x) { return s + x.pos.redeemedPaise; }, 0);
    var flows = [];
    ok.forEach(function (x) {
      x.pos.lots.forEach(function (l) { if (!l.error) flows.push([l.date, -l.paise / 100]); });
      x.pos.sales.forEach(function (v) { if (!v.error) flows.push([v.date, v.paise / 100]); });
    });
    flows.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; });
    var asOf = ok.map(function (x) { return x.pos.valueDate; }).sort().pop();
    flows.push([asOf, value / 100]);
    var whole = { firstDate: flows[0][0], valueDate: asOf, xirr: M.xirr(flows), investedPaise: invested, valuePaise: value };
    var pending = list.reduce(function (s, x) {
      return s + (x.pos ? x.pos.lots.filter(function (l) { return l.error === "pending"; }).length : 0);
    }, 0);
    var oversold = list.reduce(function (s, x) {
      return s + (x.pos ? x.pos.sales.filter(function (v) { return v.error === "more"; }).length : 0);
    }, 0);
    var unvalued = list.filter(function (x) { return !x.pos; }).length;
    var excluded = list.reduce(function (s, x) { return s + (x.excluded || 0); }, 0);
    fill(box,
      el("dl", { "class": "pf__tiles" },
        el("div", { "class": "pf__tile" }, el("dt", null, "Put in"), el("dd", null, rupees(invested))),
        redeemed ? el("div", { "class": "pf__tile" }, el("dt", null, "Taken out"), el("dd", null, rupees(redeemed))) : null,
        el("div", { "class": "pf__tile" }, el("dt", null, "Worth on " + M.day(asOf)), el("dd", null, rupees(value))),
        el("div", { "class": "pf__tile" }, el("dt", null, "Gain"), el("dd", null, rupees(value + redeemed - invested))),
        el("div", { "class": "pf__tile" }, el("dt", null, "Return", K.termButton("xirr", "pf")), el("dd", null, returnText(whole)))),
      pending ? el("p", { "class": "pf__note" }, pending + " purchase" + (pending === 1 ? " is" : "s are") + " awaiting a published NAV and left out until it appears.") : null,
      oversold ? el("p", { "class": "pf__note" }, oversold + " sale" + (oversold === 1 ? " is" : "s are") + " larger than the units held on " + (oversold === 1 ? "its date" : "their dates") + " and left out; check the amount and the purchases before it.") : null,
      unvalued ? el("p", { "class": "pf__note" }, unvalued + " fund" + (unvalued === 1 ? " is" : "s are") + " not valued and left out of these totals; the funds table says why.") : null,
      excluded ? el("p", { "class": "pf__note" }, entries(excluded) + " with an error " + (excluded === 1 ? "is" : "are") + " left out until corrected; each says what is wrong.") : null,
      el("p", { "class": "pf__estimate" }, ESTIMATE));
  }

  function fundsTable(list) {
    var total = list.reduce(function (s, x) { return s + (x.pos ? x.pos.valuePaise : 0); }, 0);
    var rows = list.map(function (x) {
      var name = x.fund ? el("a", { href: fundPage(x.fund) }, x.fund.name) : x.h.id;
      if (!x.pos) return [name, "—", "—", "—", "—", "—", "Not valued: " + x.error];
      var p = x.pos;
      if (!p.firstDate) {
        var waiting = p.lots.some(function (l) { return l.error === "pending"; });
        return [name, "—", "—", "—", "—", "—", waiting ? "Awaiting a published NAV" : "No purchases entered yet"];
      }
      return [name, rupees(p.investedPaise), M.units(p.unitsMilli), rupees(p.valuePaise),
              rupees(p.valuePaise + p.redeemedPaise - p.investedPaise), returnText(p),
              total ? pct(p.valuePaise * 100 / total) : "—"];
    });
    out("funds").replaceChildren(rows.length
      ? table(["Fund", "Put in", "Units", "Worth", "Gain", "Return", "Share"], rows, [0, 1, 1, 1, 1, 1, 1])
      : el("p", { "class": "pf__note" }, "No funds yet."));
  }

  var SIZE = { large: "Large companies", mid: "Mid-sized companies", small: "Small companies",
               unranked: "Not ranked by AMFI" };

  function bars(title, rowsIn, names) {
    return el("div", null, el("h3", null, title),
      table(["", "Share"], rowsIn.map(function (r) { return [names[r.key] || r.key, bar(r.pct)]; }), [0, 1]));
  }

  function look(list, live) {
    var held = list.filter(function (x) { return x.pos && x.pos.valuePaise > 0; });
    var box = out("look");
    if (!held.length) { box.replaceChildren(el("p", { "class": "pf__note" }, "Shown once a fund is valued.")); return Promise.resolve(); }
    return Promise.all(held.map(function (x) { return K.lookFile(BASE, x.fund.direct || x.fund.id); })).then(function (files) {
      if (!live()) return;
      var byId = {};
      held.forEach(function (x, i) { byId[x.fund.id] = files[i]; });
      var lt = M.lookThrough(held.map(function (x) { return { id: x.fund.id, valuePaise: x.pos.valuePaise }; }), byId);
      var top = lt.companies.slice(0, 20);
      var rest = lt.companies.slice(20);
      var restPaise = rest.reduce(function (s, r) { return s + r.paise; }, 0);
      var companyRows = top.map(function (r) {
        return [r.name, rupees(r.paise), pct(r.pct), r.funds + " of " + held.length];
      });
      if (rest.length) companyRows.push([rest.length + " other companies", rupees(restPaise), pct(lt.total ? restPaise * 100 / lt.total : 0), ""]);
      lt.synthetic.forEach(function (r) { companyRows.push([r.name, rupees(r.paise), pct(r.pct), r.funds + " of " + held.length]); });

      var withFiles = held.filter(function (x) { return byId[x.fund.id]; });
      var grid = null;
      if (withFiles.length > 1) {
        grid = table([""].concat(withFiles.map(function (x) { return x.fund.name; })),
          withFiles.map(function (a) {
            return [a.fund.name].concat(withFiles.map(function (b) {
              return a === b ? "—" : pct(M.overlap(byId[a.fund.id], byId[b.fund.id]));
            }));
          }), [0].concat(withFiles.map(function () { return 1; })));
      }

      var notes = [];
      if (lt.coverage.unknownPaise) notes.push(pct(lt.coverage.unknownPaise * 100 / lt.total) + " of the portfolio is in funds with no disclosure loaded here, so it is not looked through.");
      if (lt.coverage.unresolvedPaise) notes.push(pct(lt.coverage.unresolvedPaise * 100 / lt.total) + " is in holdings the disclosures name in ways this site could not match to a company.");
      lt.coverage.funds.forEach(function (f) {
        var fund = FUNDS.get(f.id);
        notes.push((fund ? fund.name : f.id) + ": disclosed " + f.asOf + (f.aggregator ? ", read from an aggregator's page" : "") + ".");
      });

      fill(box,
        el("h3", null, "Companies"),
        // No disclosure loaded for any fund: one sentence, not a table of headers.
        companyRows.length
          ? table(["Company", "Your money in it", "Share of portfolio", "Held by"], companyRows, [0, 1, 1, 1])
          : el("p", { "class": "pf__note" }, "No company is named yet: none of these funds has a disclosure loaded here."),
        grid && el("h3", null, "How much of each pair of funds is the same", K.termButton("overlap", "pf")),
        grid && el("p", { "class": "pf__note" }, "The share of two funds' portfolios in the same companies: 100% would be identical funds, 0% nothing in common."),
        grid,
        el("div", { "class": "pf__grid" },
          lt.mix.length ? bars("Asset mix", lt.mix, CLASS) : null,
          lt.sectors.length ? bars("Shares by sector", lt.sectors, {}) : null,
          lt.sizes.length ? bars("Shares by company size", lt.sizes, SIZE) : null),
        noteList(notes));
    });
  }

  function noteList(notes) {
    var ul = el("ul", { "class": "pf__note" });
    notes.forEach(function (n) { ul.appendChild(el("li", null, n)); });
    return ul;
  }

  var REASON = {
    ter: "lowest expense ratio",
    r3: "middle three-year return in its category",
    size: "largest fund today",
  };

  function figure(v, kind) {
    if (v == null) return "—";
    var n = Number(v);
    if (kind === "ter") return n.toFixed(2) + "%";
    if (kind === "size") return rupees(n * 100);
    if (kind === "fall") return pct(Math.abs(n) * 100);
    return signedPct(n);
  }

  function alts(list, live) {
    var box = out("alts");
    var cards = list.filter(function (x) { return x.pos && x.pos.firstDate; });
    if (!cards.length) { box.replaceChildren(el("p", { "class": "pf__note" }, "Shown once a fund is valued.")); return Promise.resolve(); }
    var all = Array.from(FUNDS.values());
    return Promise.all(cards.map(function (x) {
      var suggested = M.alternatives(x.fund, all, x.pos.firstDate);
      var slots = M.altSlots(x.h.alts, suggested, function (id) { return FUNDS.get(id); });
      var buys = M.pricedBuys(x.pos), sold = M.pricedSales(x.pos);
      return Promise.all(slots.map(function (s) {
        if (!s.fund) return Promise.resolve({ s: s, pos: null, error: null });
        return K.navSeries(BASE, s.fund).then(function (series) {
          return { s: s, pos: M.position(buys, series, sold), error: null };
        }, function (e) { return { s: s, pos: null, error: e.message }; });
      })).then(function (valued) {
        var label = "the same " + rupees(x.pos.investedPaise) + (sold.length ? ", and the same sales," : "") + " on the same dates";
        var rows = [[el("strong", null, x.fund.name), "yours", rupees(x.pos.valuePaise), returnText(x.pos),
                     figure(x.fund.r3), figure(x.fund.vol3, "fall"), figure(x.fund.fall3, "fall"), figure(x.fund.ter, "ter"), ""]];
        valued.forEach(function (v) {
          var f = v.s.fund;
          var button = el("button", { type: "button", "class": "button button--quiet", "data-action": "replace",
                                      "data-held": x.h.id, "data-slot": v.s.slot },
                                    f ? "Compare a different fund" : "Choose a fund");
          if (!f) { rows.push(["—", "", "", "", "", "", "", "", button]); return; }
          var why = v.s.reasons.map(function (r) { return r === "chosen" ? "your choice" : REASON[r]; }).join(", ");
          // Valued only on exactly the money the held fund priced: a lot this
          // fund cannot price yet would make it a different sum.
          var gap = v.pos && (v.pos.lots.filter(function (l) { return l.error; })[0] ||
                              v.pos.sales.filter(function (x) { return x.error; })[0]);
          var reason = v.error || (gap && (gap.error === "before"
            ? "its prices begin after " + gap.date
            : gap.error === "more" ? "it would not have held enough to sell the same on " + gap.date
            : "its NAV for " + gap.date + " is not out yet"));
          rows.push([el("a", { href: BASE + "/fund/" + f.id + "/" }, f.name), why,
            reason ? "—" : rupees(v.pos.valuePaise),
            reason || returnText(v.pos),
            figure(f.r3), figure(f.vol3, "fall"), figure(f.fall3, "fall"), figure(f.ter, "ter"), button]);
        });
        var count = suggested.length;
        return el("article", { "class": "pf__alt card" },
          el("h3", null, x.fund.name + " — " + (x.fund.category_name || "")),
          el("p", { "class": "pf__note" }, "What " + label + " would be worth today in each fund. " +
            (x.fund.mixed
              ? "AMFI files this fund under a heading that mixes funds doing different jobs, so none is suggested; choose any fund to compare."
              : "Funds of the same category whose prices go back to " + M.day(x.pos.firstDate) + ", picked by the rule named beside each." +
                " The largest is today's largest, which leans towards funds that have done well." +
                (x.fund.plan === "regular" ? " These are Direct plans; part of any gap is the Regular plan's higher cost." : "") +
                (count === 0 ? " No other fund of this category has prices back that far; choose any fund to compare."
                  : count < 3 ? " Only " + count + " of this category " + (count === 1 ? "qualifies" : "qualify") + ", so the rest are empty; choose any fund to compare." : ""))),
          table(["Fund", "Why it is here", "Worth today", "Return", "3 years a year", "Volatility", "Deepest fall", "Expense ratio", ""],
                rows, [0, 0, 1, 1, 1, 1, 1, 1, 0]));
      });
    })).then(function (articles) {
      if (!live()) return;
      fill.apply(null, [box].concat(articles, [el("p", { "class": "pf__estimate" }, ESTIMATE)]));
    });
  }

  // Edits can start a run while an earlier one is still fetching; only the
  // newest run may draw, or a removed fund's figures could come back.
  function results() {
    var mine = ++generation;
    var live = function () { return mine === generation; };
    return priced().then(function (list) {
      if (!live()) return;
      summary(list);
      fundsTable(list);
      return Promise.all([look(list, live), alts(list, live)]);
    });
  }

  // --- start -------------------------------------------------------------------
  restore();
  fetch(BASE + "/funds.json").then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (list) {
    var options = document.getElementById("pf-funds");
    list.forEach(function (f) {
      FUNDS.set(f.id, f);
      BY_NAME.set(f.name, f);
      options.appendChild(el("option", { value: f.name }, f.category_name));
    });
    document.getElementById("pf-pick").disabled = false;
    entry();
    results();
  }).catch(function () {
    say("The list of funds did not load, so funds cannot be added. Reload the page to try again.");
  });
})();
