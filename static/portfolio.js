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
  var replacing = null;         // {id: held fund's ISIN, slot: 0..2} while "Replace" is picking
  var generation = 0;           // the newest results() run; older runs do not draw
  var state = { version: 1, funds: [] };
  var FUSE_MS = 4000;           // how long Undo is on offer after "Remove"
  var leaving = new Map();      // fund id -> its fuse (Kit.fuse) while Undo is on offer
  var ticking = null;           // the countdown's interval while any fund is leaving
  var dirty = false;            // changed since the last Save or Load to a file (P-10)
  var editFold = page.querySelector(".pf__edit");

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
  function field(label, attrs, prefix, words) {
    var id = "pf-" + Math.random().toString(36).slice(2, 9);
    var input = el("input", Object.assign({ id: id }, attrs));
    // The words share the label's line, so every row's boxes stay level.
    return el("label", { "class": "pf__field", "for": id },
      words == null ? label : el("span", null, label,
        el("span", { "class": "pf__words", "data-words": true, "aria-hidden": "true" }, words)),
      prefix ? el("span", { "class": "pf__affix" }, el("span", { "class": "pf__prefix" }, prefix), input) : input);
  }

  // An amount (UI/UX critique P-03): in Indian grouping once typed, and in words
  // beneath as it is typed, so ₹1,00,000 is not read as ₹10,000.
  function amountField(label, value) {
    return field(label, { type: "text", inputmode: "decimal", value: M.grouped(value), "data-field": "amount" },
                 "₹", M.inWords(value));
  }

  // Each kind of entry under its own name (P-05), when there is one.
  function group(legend, rows) {
    return rows.length ? el.apply(null, ["fieldset", { "class": "pf__group" }, el("legend", null, legend)].concat(rows)) : null;
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
    function row(kind, item, r, fields) {
      var node = el.apply(null, ["div", { "class": "pf__row", "data-kind": kind, "data-row": r, inert: !!gone }]
        .concat(fields, [errorSlot()]));
      showRowError(node, rowError(fund, kind, item));
      return node;
    }
    K.present([group("Lump sums", h.purchases.map(function (p, r) {
      return row("purchase", p, r, [
        field("Date", { type: "date", value: p.date, max: TODAY, min: fund ? fund.prices_from : null, "data-field": "date" }),
        amountField("Amount", p.amount),
        iconButton("remove-row", "Remove this lump sum", "close")]);
    })),
    // A running SIP has no end month to fill in: "Still running" stands for it, and
    // clearing the box brings the month (P-04; the empty one read "---------, ----").
    group("SIPs", h.sips.map(function (s, r) {
      return row("sip", s, r, [
        amountField("SIP a month", s.amount),
        field("Day", { type: "number", min: 1, max: 31, value: s.day, "data-field": "day" }),
        field("From", { type: "month", value: s.start, "data-field": "start" }),
        s.stop === null ? null : field("Until", { type: "month", value: s.stop, "data-field": "stop" }),
        el("label", { "class": "pf__check" },
          el("input", { type: "checkbox", "data-field": "running", checked: s.stop === null }), "Still running"),
        iconButton("remove-row", "Remove this SIP", "close")]);
    })),
    group("Sales", (h.sales || []).map(function (p, r) {
      return row("sale", p, r, [
        field("Sold on", { type: "date", value: p.date, max: TODAY, min: fund ? fund.prices_from : null, "data-field": "date" }),
        amountField("Received", p.amount),
        iconButton("remove-row", "Remove this sale", "close")]);
    }))]).forEach(function (g) { card.appendChild(g); });
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

  function changed() { save(); entry(); results(); unsaved(true); folded(); }

  // Save is the main button while there are changes no file holds (P-10).
  function unsaved(yes) {
    dirty = yes;
    page.querySelector('[data-action="save"]').classList.toggle("button--quiet", !dirty);
  }
  // The form's fold says how many funds it holds, and is open while there are none.
  function folded() {
    var n = state.funds.length;
    page.querySelector("[data-edit-label]").textContent = "Your funds and what you put in" +
      (n ? " (" + n + (n === 1 ? " fund)" : " funds)") : "");
    if (!n) editFold.open = true;
  }

  function listOf(h, kind) {
    return kind === "sip" ? h.sips : kind === "sale" ? (h.sales = h.sales || []) : h.purchases;
  }

  function stopReplacing() {
    replacing = null;
    document.getElementById("pf-pick-label").textContent = "Add a fund";
  }

  // The picker first: its Esc closes its list before this one cancels a replacing.
  K.picker(document.getElementById("pf-pick"),
           function () { return Array.from(FUNDS.values()); }, pick);
  document.getElementById("pf-pick").addEventListener("keydown", function (e) {
    if (e.key === "Escape" && replacing) { stopReplacing(); say(""); }
  });

  function pick(fund) {
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
    if (t.id === "pf-file") { loadFile(t.files[0]); t.value = ""; return; }
    var row = t.closest("[data-row]"), card = t.closest("[data-fund]");
    if (!row || !card || !t.dataset.field) return;
    var h = state.funds[Number(card.dataset.fund)];
    var item = listOf(h, row.dataset.kind)[Number(row.dataset.row)];
    if (t.dataset.field === "running") {
      // "" until a month is chosen: running still, with the month's field drawn.
      item.stop = t.checked ? null : "";
      changed();
      var at = '[data-fund="' + card.dataset.fund + '"] [data-kind="sip"][data-row="' + row.dataset.row + '"] ';
      var next = out("holdings").querySelector(at + (t.checked ? '[data-field="running"]' : '[data-field="stop"]'));
      if (next) next.focus();
      return;
    }
    if (t.dataset.field === "amount") {
      item.amount = t.value.replace(/[₹,\s]/g, "");
      t.value = M.grouped(item.amount);
    } else {
      item[t.dataset.field] = t.dataset.field === "day" ? (t.value === "" ? null : Number(t.value))
        : t.dataset.field === "stop" ? (t.value || null) : t.value;
    }
    showRowError(row, rowError(FUNDS.get(h.id), row.dataset.kind, item));
    save();
    unsaved(true);
    results();
  });

  // The amount in words, as it is typed.
  page.addEventListener("input", function (e) {
    var t = e.target;
    if (!t.dataset || t.dataset.field !== "amount") return;
    var words = t.closest(".pf__field").querySelector("[data-words]");
    if (words) words.textContent = M.inWords(t.value);
  });

  page.addEventListener("click", function (e) {
    // A kind whose prices did not load: the cache let go of them, so try again.
    if (e.target.closest("[data-retry]")) { results(); return; }
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
        editFold.open = true;
        document.getElementById("pf-pick-label").textContent = "Pick a fund to compare in this place (Esc to cancel)";
        document.getElementById("pf-pick").focus();
        return;
      case "save": saveFile(); return;
      case "load": document.getElementById("pf-file").click(); return;
      case "clear":   // the second step: More said what this removes (P-10)
        state = { version: 1, funds: [] };
        stopReplacing();
        defuse();
        b.closest("details").open = false;
        say("Every fund and entry was removed from this page and this browser.");
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
    unsaved(false);
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
      unsaved(false);
    });
  }

  // --- results ------------------------------------------------------------------
  // Kit.table: a named region, and on a phone a card per row (G-17, P-08).
  function table(caption, head, rows, numeric, opts) {
    var o = opts || {};
    o.numeric = numeric;
    return K.table(caption, head, rows, o);
  }

  // Positions summed: put in, taken out, worth, and the return a year on all their
  // dated money (XIRR) to the latest date any of them is valued on.
  function whole(positions) {
    var invested = 0, value = 0, redeemed = 0, flows = [];
    positions.forEach(function (p) {
      invested += p.investedPaise; value += p.valuePaise; redeemed += p.redeemedPaise;
      p.lots.forEach(function (l) { if (!l.error) flows.push([l.date, -l.paise / 100]); });
      p.sales.forEach(function (v) { if (!v.error) flows.push([v.date, v.paise / 100]); });
    });
    flows.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; });
    var asOf = positions.map(function (p) { return p.valueDate; }).sort().pop();
    flows.push([asOf, value / 100]);
    return { firstDate: flows[0][0], valueDate: asOf, xirr: M.xirr(flows),
             investedPaise: invested, valuePaise: value, redeemedPaise: redeemed };
  }

  // The return with its period on a smaller line (P-09): "+15.2%", "a year".
  function returnParts(pos) {
    var text = returnText(pos), cut = text.indexOf(" ");
    return cut < 0 ? [text] : [text.slice(0, cut), el("span", { "class": "pf__per" }, text.slice(cut + 1))];
  }

  // Why a fund cannot take exactly the money a holding priced, or null if it can.
  function gapReason(pos) {
    var gap = pos.lots.filter(function (l) { return l.error; })[0] ||
              pos.sales.filter(function (x) { return x.error; })[0];
    return !gap ? null : gap.error === "before" ? "its prices begin after " + gap.date
      : gap.error === "more" ? "it would not have held enough to sell the same on " + gap.date
      : "its NAV for " + gap.date + " is not out yet";
  }

  // "Did it work?" in a sentence (UI/UX critique P-01): what the money became, then
  // the same purchases and sales in each holding's reference (M.reference: the
  // index fund on its benchmark, else its category's middle three-year return),
  // each named. Two sums side by side and no verdict on them (ADR-0002).
  function verdict(list, live) {
    var box = out("verdict");
    var ok = list.filter(function (x) { return x.pos && x.pos.firstDate; });
    if (!ok.length) { fill(box); return Promise.resolve(); }
    var all = Array.from(FUNDS.values());
    return Promise.all(ok.map(function (x) {
      var ref = M.reference(x.fund, all, x.pos.firstDate);
      if (!ref) return { x: x, ref: null, pos: null };
      return K.navSeries(BASE, ref.fund).then(function (series) {
        var pos = M.position(M.pricedBuys(x.pos), series, M.pricedSales(x.pos));
        var gap = gapReason(pos);
        return { x: x, ref: ref, pos: gap ? null : pos, why: gap };
      }, function () { return { x: x, ref: ref, pos: null, why: "its prices did not load" }; });
    })).then(function (got) {
      if (!live()) return;
      var refs = el.apply(null, ["ul", { "class": "pf__refs" }].concat(got.map(function (g) {
        var name = g.x.fund.name;
        if (!g.ref) return el("li", null, name + ": no index fund on its benchmark and no category to draw a fund from, so it is left out.");
        return el("li", null, name + " beside ", el("a", { href: fundPage(g.ref.fund) }, g.ref.fund.name),
          g.ref.why === "index" ? ", the longest-running index fund on its benchmark" : ", the middle three-year return of its category",
          g.pos ? "." : "; " + g.why + ", so it is left out.");
      })));
      var priced = got.filter(function (g) { return g.pos; });
      if (!priced.length) {
        fill(box, el("p", { "class": "pf__verdict" }, "None of your funds has a reference that could take the same money:"), refs);
        return;
      }
      var mine = whole(priced.map(function (g) { return g.x.pos; }));
      var theirs = whole(priced.map(function (g) { return g.pos; }));
      var sold = mine.redeemedPaise ? ", with " + rupees(mine.redeemedPaise) + " taken out," : ",";
      var regular = priced.some(function (g) { return g.x.fund.plan === "regular"; });
      fill(box,
        el("p", { "class": "pf__verdict" },
          (priced.length < ok.length ? "For the " + priced.length + " of your " + ok.length + " funds with a reference, what" : "What") +
          " you put in, " + rupees(mine.investedPaise) + sold + " is worth " + rupees(mine.valuePaise) + ": " +
          returnText(mine) + ". The same money on the same dates in each fund's reference would be worth " +
          rupees(theirs.valuePaise) + ": " + returnText(theirs) + "."),
        refs,
        regular && el("p", { "class": "pf__note" }, "The references are Direct plans: part of any gap is a Regular plan's higher cost."));
    });
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
        : "Add a fund and a purchase to see what it is worth."),
        // Someone holding nothing yet can still look back (SPEC_SIP_WHAT_IF §4.8).
        !list.length && el("p", { "class": "pf__note" },
          el("a", { href: BASE + "/sip/" }, "Holding no funds yet? See what a SIP would have become →")));
      return;
    }
    var all = whole(ok.map(function (x) { return x.pos; }));
    var invested = all.investedPaise, value = all.valuePaise, redeemed = all.redeemedPaise, asOf = all.valueDate;
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
        el("div", { "class": "pf__tile" }, el("dt", null, "Return", K.termButton("xirr", "pf")),
          el.apply(null, ["dd", null].concat(returnParts(all))))),
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
      ? table("Your funds", ["Fund", "Put in", "Units", "Worth", "Gain", "Return", "Share"], rows,
              [0, 1, 1, 1, 1, 1, 1], { cls: "pf__funds" })
      : el("p", { "class": "pf__note" }, "No funds yet."));
  }

  var SIZE = { large: "Large companies", mid: "Mid-sized companies", small: "Small companies",
               unranked: "Not ranked by AMFI" };

  function bars(title, rowsIn, names) {
    return el("div", null, el("h3", null, title),
      table(title, ["", "Share"], rowsIn.map(function (r) { return [names[r.key] || r.key, bar(r.pct)]; }),
            [0, 1], { stack: false }));
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
      // Each share drawn as a bar (P-06); what is not a company -- cash, and holdings
      // not matched to one -- in a grey bar, as on a fund's page.
      var companyRows = top.map(function (r) {
        return [r.name, rupees(r.paise), bar(r.pct), r.funds + " of " + held.length];
      });
      if (rest.length) companyRows.push([rest.length + " other companies", rupees(restPaise), bar(lt.total ? restPaise * 100 / lt.total : 0), ""]);
      lt.synthetic.forEach(function (r) { companyRows.push([r.name, rupees(r.paise), greyBar(r.pct), r.funds + " of " + held.length]); });

      var withFiles = held.filter(function (x) { return byId[x.fund.id]; });
      var grid = null;
      if (withFiles.length > 1) {
        grid = table("How much of each pair of funds is the same",
          [""].concat(withFiles.map(function (x) { return x.fund.name; })),
          withFiles.map(function (a) {
            return [a.fund.name].concat(withFiles.map(function (b) {
              if (a === b) return el("span", { "class": "heat heat--self" }, "—");
              var v = M.overlap(byId[a.fund.id], byId[b.fund.id]);
              return K.heat(v, pct(v));
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
          ? table("Companies", ["Company", "Your money in it", "Share of portfolio", "Held by"], companyRows, [0, 1, 1, 1])
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

  function greyBar(value) {
    var b = bar(value);
    b.firstChild.setAttribute("class", "bar bar--neutral");
    return b;
  }

  function noteList(notes) {
    var ul = el("ul", { "class": "pf__note" });
    notes.forEach(function (n) { ul.appendChild(el("li", null, n)); });
    return ul;
  }

  function figure(v, kind) {
    if (v == null) return "—";
    var n = Number(v);
    if (kind === "ter") return n.toFixed(2) + "%";
    if (kind === "size") return rupees(n * 100);
    if (kind === "fall") return pct(Math.abs(n) * 100);
    return signedPct(n);
  }
  // "Flexi cap" -> "flexi cap"; "ELSS (tax saver)" keeps its capitals.
  function lower(name) { return /^[A-Z][a-z]/.test(name) ? name.charAt(0).toLowerCase() + name.slice(1) : name; }

  // In hindsight (SPEC_SIP_WHAT_IF §6.2). Each holding is set against every other
  // Direct fund of its kind on its own priced purchases and sales: the range, the
  // middle, and where the holding sits, drawn by /sip/'s strip (sip.js). No fund is
  // suggested: the slots below start empty and fill only with the visitor's choice
  // (a saved file's `alts` still fill them). The first card is worked out at once,
  // the rest as each comes within 200px of the screen, so one kind's NAV files load
  // before the visitor scrolls.
  var watching = null, grown = new Set();
  function alts(list, live) {
    var box = out("alts");
    if (watching) { watching.disconnect(); watching = null; }
    var cards = list.filter(function (x) { return x.pos && x.pos.firstDate; });
    if (!cards.length) { box.replaceChildren(el("p", { "class": "pf__note" }, "Shown once a fund is valued.")); return Promise.resolve(); }
    return Promise.all(cards.map(function (x) {
      var slots = M.altSlots(x.h.alts, [], function (id) { return FUNDS.get(id); });
      // Only the funds chosen are rows; one button offers the next free place.
      var pick = M.chosenSlots(slots);
      var buys = M.pricedBuys(x.pos), sold = M.pricedSales(x.pos);
      return Promise.all(pick.chosen.map(function (s) {
        if (!s.fund) return Promise.resolve({ s: s, pos: null, error: null });
        return K.navSeries(BASE, s.fund).then(function (series) {
          return { s: s, pos: M.position(buys, series, sold), error: null };
        }, function (e) { return { s: s, pos: null, error: e.message }; });
      })).then(function (valued) {
        var rows = [[el("strong", null, x.fund.name + " (yours)"), rupees(x.pos.valuePaise), returnText(x.pos),
                     figure(x.fund.r3), figure(x.fund.vol3, "fall"), figure(x.fund.fall3, "fall"), figure(x.fund.ter, "ter"), ""]];
        valued.forEach(function (v) {
          var f = v.s.fund;
          var button = el("button", { type: "button", "class": "button button--quiet", "data-action": "replace",
                                      "data-held": x.h.id, "data-slot": v.s.slot,
                                      "aria-label": "Replace " + f.name + " with another fund" }, "Replace");
          // Valued only on exactly the money the held fund priced: a lot this
          // fund cannot price yet would make it a different sum.
          var reason = v.error || (v.pos && gapReason(v.pos));
          rows.push([el("a", { href: BASE + "/fund/" + f.id + "/" }, f.name),
            reason ? "—" : rupees(v.pos.valuePaise),
            reason || returnText(v.pos),
            figure(f.r3), figure(f.vol3, "fall"), figure(f.fall3, "fall"), figure(f.ter, "ter"), button]);
        });
        // Until it is worked out (as it reaches the screen), a quiet placeholder.
        var strip = x.fund.mixed ? null : el("div", { "class": "pf__against" },
          el("div", { "class": "pf__waiting", "aria-hidden": "true" }),
          el("p", { "class": "sr-only" }, "Worked out as this card reaches the screen."));
        var another = pick.next == null ? null
          : el("button", { type: "button", "class": "button button--quiet pf__another", "data-action": "replace",
                           "data-held": x.h.id, "data-slot": pick.next }, "Compare another fund");
        var article = el("article", { "class": "pf__alt card" },
          el("h3", null, x.fund.name + " — " + (x.fund.category_name || "")),
          strip || el("p", { "class": "pf__note" },
            "AMFI files this fund under a heading that mixes funds doing different jobs, so none is suggested; choose any fund to compare."),
          el("h4", null, "Compare a different fund"),
          el("p", { "class": "pf__note" }, "What the same amounts on the same dates" + (sold.length ? ", and the same sales," : "") +
            " would be worth today in a fund you choose."),
          // "Return a year, 3 years", as Compare says it: "3 years a year" read garbled (P-08).
          table("Compare a different fund with " + x.fund.name,
                ["Fund", "Worth today", "Return", "Return a year, 3 years", "Volatility",
                 "Deepest fall", "Expense ratio", ""],
                rows, [0, 1, 1, 1, 1, 1, 1, 0]),
          another);
        return { x: x, buys: buys, sold: sold, box: strip, article: article };
      });
    })).then(function (made) {
      if (!live()) return;
      if (window.Charts && window.Charts.clear) window.Charts.clear(box);   // the strips' charts go with them
      fill.apply(null, [box].concat(made.map(function (m) { return m.article; }),
        [el("p", { "class": "pf__estimate" }, ESTIMATE)]));
      var todo = made.filter(function (m) { return m.box; });
      if (!todo.length) return;
      var start = function (m) { if (!m.started) { m.started = true; against(m, live); } };
      start(todo[0]);
      if (!("IntersectionObserver" in window)) { todo.forEach(start); return; }
      watching = new IntersectionObserver(function (seen) {
        seen.forEach(function (e) {
          if (!e.isIntersecting) return;
          watching.unobserve(e.target);
          start(todo.filter(function (m) { return m.box === e.target; })[0]);
        });
      }, { rootMargin: "200px 0px" });
      todo.slice(1).forEach(function (m) { watching.observe(m.box); });
    });
  }

  // One card's strip: every other Direct fund of the holding's kind, loaded and
  // counted, then M.against (portfolio-math.js) and the strip (sip.js).
  function against(m, live) {
    var x = m.x, S = window.SipStrip;
    var kindFunds = Array.from(FUNDS.values()).filter(function (f) {
      return f.category === x.fund.category && f.plan !== "regular";
    });
    var wanted = kindFunds.filter(function (f) { return f.id !== x.fund.id && f.id !== x.fund.direct; }).concat([x.fund]);
    var note = el("p", { "class": "pf__note" }, "Loading the other funds of its kind");
    fill(m.box, note);
    return S.load(wanted, function (done, n) { if (live()) note.textContent = "Loaded " + done + " of " + n + " funds"; })
      .then(function (series) {
        if (!live()) return;
        var a = M.against(m.buys, m.sold, x.fund, kindFunds, series);
        if (a && !a.yours && a.after.buys) {
          fill(m.box, el("p", { "class": "pf__note" }, "Its purchases are all after " + M.day(a.valuedOn) +
            ", the latest date every fund of its kind has a price; it is set against them once they are priced."));
          return;
        }
        if (!a || !a.yours) {
          fill(m.box, el("p", { "class": "pf__note" }, "The prices of this kind of fund did not load. ",
            el("button", { type: "button", "class": "button button--quiet", "data-retry": true }, "Retry")));
          return;
        }
        var r = a.r, n = r.n, name = x.fund.category_name || "";
        // "23 other flexi cap funds"; a category named as funds already is named whole:
        // "5 other funds of its category (Index funds, equity)".
        var others = function (k) {
          return /fund/i.test(name) ? k + " other fund" + (k === 1 ? "" : "s") + " of its category (" + name + ")"
            : k + " other " + lower(name) + " fund" + (k === 1 ? "" : "s");
        };
        var same = "The same money on the same dates" + (m.sold.length ? ", and the same sales," : "") + " in the " +
          others(n) + " with prices back to " + M.day(a.first);
        var text = !n ? "No " + others(1).replace(/^1 /, "") + " has prices back to " + M.day(a.first) + " to set this holding against."
          : same + " would be worth " + (n === 1 ? rupees(r.min.valuePaise)
            : "between " + rupees(r.min.valuePaise) + " and " + rupees(r.max.valuePaise)) + " on " + M.day(a.valuedOn) +
            (n >= 3 ? "; the middle, " + rupees(r.middle.valuePaise) : "") + ". Yours" +
            // A holding whose prices stopped is valued on its own last price.
            (a.yours.valuedOn !== a.valuedOn ? ", at its last price on " + M.day(a.yours.valuedOn) : "") + ": " +
            rupees(a.yours.valuePaise) + ", " + M.ordinal(a.rank) + " highest of " + (n + 1) + ".";
        if (a.after.buys + a.after.sales) {
          text += " Purchases and sales after " + M.day(a.valuedOn) + ", which not every fund has priced yet, are left out.";
        }
        if (x.fund.plan === "regular") text += " These are Direct plans; part of any gap is the Regular plan's higher cost.";
        var drawn = el("div");
        // The range strip, as on /sip/, with yours on it; it grows the first time this
        // holding's card is worked out on this visit, not on every edit after.
        var bar = n ? el("div", { "class": "sip__strip" },
          S.bar({ min: r.min.valuePaise, max: r.max.valuePaise, middle: n >= 3 ? r.middle.valuePaise : null,
                  putIn: a.putPaise, yours: a.yours.valuePaise },
                Math.min(r.min.valuePaise, a.yours.valuePaise, a.putPaise),
                Math.max(r.max.valuePaise, a.yours.valuePaise), !grown.has(x.fund.id)),
          S.key(n >= 3 ? ["range", "mid", "yours", "putin"] : ["range", "yours", "putin"])) : null;
        grown.add(x.fund.id);
        fill(m.box, el("p", { "class": "pf__against-lead" }, text), bar, drawn);
        S.strip(drawn, {
          first: a.first, valuedOn: a.valuedOn, r: r, idx: null, out: a.out, kindSeries: a.kindSeries,
          putPaise: a.putPaise,
          marked: [{ o: a.yours, label: "Yours", hue: 2, tag: " · yours" }],
          note: ", and the named one is yours",
          failed: function () { say("The charts did not load; the tables hold the same figures."); },
        });
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
      return Promise.all([verdict(list, live), look(list, live), alts(list, live)]);
    });
  }

  // --- start -------------------------------------------------------------------
  restore();
  editFold.open = !state.funds.length;   // the answer first (P-02)
  folded();
  fetch(BASE + "/funds.json").then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (list) {
    list.forEach(function (f) { FUNDS.set(f.id, f); });
    document.getElementById("pf-pick").disabled = false;
    entry();
    results();
  }).catch(function () {
    say("The list of funds did not load, so funds cannot be added. Reload the page to try again.");
  });
})();
