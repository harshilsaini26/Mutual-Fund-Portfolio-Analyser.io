/*
 * What the portfolio (V1-82) and compare (V1-85) pages share: building the DOM
 * with createElement/textContent (never innerHTML), the bar-in-cell, the asset
 * class names, and reading the NAV and look-through files this site publishes.
 * `present` is exported for `node --test`; the rest runs in the browser.
 */
(function () {
  "use strict";

  // The children worth drawing: text and nodes. `list.length && x` gives 0 for an
  // empty list, and a stray "0" on a page of figures reads as one.
  function present(children) { return children.filter(function (c) { return !!c; }); }

  function el(tag, attrs) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] != null && attrs[k] !== false) node.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    });
    present(Array.prototype.slice.call(arguments, 2)).forEach(function (c) {
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }
  function fill(box) {
    box.replaceChildren.apply(box, present(Array.prototype.slice.call(arguments, 1)));
  }

  // Every table on these pages (UI/UX critique G-17, P-08, C-04): a region named by
  // its caption, which app.js makes a tab stop when it scrolls sideways; on a phone
  // (`table--stack`, unless `stack: false`) each row a card, every figure under its
  // column's name. `head` holds text or nodes, `labels` names node columns plainly,
  // `numeric` marks right-aligned columns, `rowHead` heads each row with its first
  // cell, `cls` is the table's own class. A cell is text, a node, or a list of them.
  var tables = 0;
  function table(caption, head, rows, opts) {
    opts = opts || {};
    var id = "tbl-" + (++tables);
    var labels = opts.labels || head.map(function (h) { return typeof h === "string" ? h : h.textContent; });
    var align = function (i) { return opts.numeric && opts.numeric[i] ? "num" : null; };
    var tr = el("tr");
    head.forEach(function (h, i) { tr.appendChild(el("th", { scope: "col", "class": align(i) }, h)); });
    var body = el("tbody");
    rows.forEach(function (cells) {
      var row = el("tr");
      cells.forEach(function (c, i) {
        var attrs = i === 0 && opts.rowHead ? { scope: "row" }
          : { "class": align(i), "data-label": labels[i] || null };
        row.appendChild(el.apply(null, [attrs.scope ? "th" : "td", attrs].concat(c)));
      });
      body.appendChild(row);
    });
    return el("div", { "class": "table-wrap", role: "region", "aria-labelledby": id },
      el("table", { "class": present([opts.cls, opts.stack !== false && "table--stack"]).join(" ") || null },
        el("caption", { "class": "sr-only", id: id }, caption), el("thead", null, tr), body));
  }

  // The fund picker's matching (UI/UX critique C-01). Every word typed must match
  // the fund: the start of a word of its name, anywhere in its name, the start of its
  // fund house or category, its name's initials ("ppfcf"), or its ISIN's start --
  // so "parag flexi", "ppfas" and an ISIN all find Parag Parikh Flexi Cap. Best
  // first: words matched in the name, then a name starting with the first word,
  // then the shorter name.
  function fold(text) { return String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
  function match(funds, query, limit) {
    var typed = fold(query).split(" ").filter(Boolean);
    if (!typed.length) return [];
    var hits = [];
    funds.forEach(function (f) {
      var name = fold(f.name), words = name.split(" ");
      var initials = words.map(function (w) { return w.charAt(0); }).join("");
      var rest = fold([f.house, f.category_name].join(" ")).split(" ");
      var isin = String(f.id || "").toLowerCase();
      var starts = function (list, t) { return list.some(function (w) { return w.indexOf(t) === 0; }); };
      var score = 0;
      for (var i = 0; i < typed.length; i++) {
        var t = typed[i];
        var s = starts(words, t) ? 3 : name.indexOf(t) >= 0 ? 2
          : starts(rest, t) || (t.length > 1 && initials.indexOf(t) === 0) ||
            (t.length > 3 && isin.indexOf(t) === 0) ? 1 : 0;
        if (!s) return;
        score += s;
      }
      hits.push({ f: f, score: score, lead: name.indexOf(typed[0]) === 0 ? 1 : 0 });
    });
    hits.sort(function (a, b) {
      return b.score - a.score || b.lead - a.lead || a.f.name.length - b.f.name.length ||
        (a.f.name < b.f.name ? -1 : 1);
    });
    return hits.slice(0, limit || 8).map(function (h) { return h.f; });
  }

  // The fund picker (C-01): an ARIA 1.2 combobox on Compare and Your portfolio, in
  // place of a <datalist> of every fund. The list follows the typing, the arrows
  // move through it, Enter or a click picks, Esc closes it. `funds()` gives the
  // funds to search; `pick(fund)` takes the one chosen.
  var pickers = 0;
  function picker(input, funds, pick) {
    var id = "pick-" + (++pickers);
    var list = el("ul", { "class": "search__suggest picker", role: "listbox", id: id,
                          "aria-label": "Funds", hidden: true });
    var hits = [], at = -1;
    input.parentNode.appendChild(list);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-controls", id);
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      mark(-1);
    }
    function mark(i) {
      at = i;
      Array.prototype.forEach.call(list.children, function (li, k) {
        li.setAttribute("aria-selected", String(k === i));
      });
      if (i < 0) { input.removeAttribute("aria-activedescendant"); return; }
      input.setAttribute("aria-activedescendant", id + "-" + i);
      list.children[i].scrollIntoView({ block: "nearest" });
    }
    function show() {
      if (input.value.trim().length < 2) { close(); return; }
      hits = match(funds(), input.value, 8);
      fill.apply(null, [list].concat(hits.length ? hits.map(function (f, i) {
        return el("li", { role: "option", id: id + "-" + i, "data-i": i },
          el("span", { "class": "search__name" }, f.name),
          el("span", { "class": "search__meta" }, present([f.house, f.category_name]).join(" · ")));
      }) : [el("li", { "class": "picker__none", role: "option", "aria-disabled": "true" },
                "No fund's name, fund house or ISIN matches that")]));
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      mark(hits.length ? 0 : -1);
    }
    function choose(i) {
      var fund = hits[i];
      if (!fund) return;
      input.value = "";
      close();
      pick(fund);
    }

    input.addEventListener("input", show);
    input.addEventListener("keydown", function (e) {
      var step = { ArrowDown: 1, ArrowUp: -1 }[e.key];
      if (step) {
        e.preventDefault();
        if (list.hidden) show();
        else if (hits.length) mark((at + step + hits.length) % hits.length);
      } else if (e.key === "Enter" && !list.hidden && at >= 0) {
        e.preventDefault();
        choose(at);
      } else if (e.key === "Escape" && !list.hidden) {
        // Only the list closes: the page's own Esc (Your portfolio's "cancel
        // replacing") waits for a second press.
        e.stopImmediatePropagation();
        close();
      }
    });
    input.addEventListener("blur", close);
    // A press on an option would blur the box and close the list before the click.
    list.addEventListener("mousedown", function (e) { e.preventDefault(); });
    list.addEventListener("click", function (e) {
      var li = e.target.closest("[data-i]");
      if (li) choose(Number(li.getAttribute("data-i")));
    });
  }

  // An overlap's figure on a tint as strong as it is large (UI/UX critique C-05):
  // up to a third of the accent at 100%, so dark text stays readable on it. The
  // figure is written, so the tint is never the only way to read it. CSSOM, not a
  // style attribute: the CSP allows none.
  function heat(value, text) {
    var span = el("span", { "class": "heat" }, text);
    var share = Math.max(0, Math.min(100, value)) / 3;
    span.style.backgroundColor = "color-mix(in srgb, var(--accent) " + share.toFixed(1) + "%, transparent)";
    return span;
  }

  var INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
  var CLASS = { equity: "Shares", debt: "Bonds and other debt", cash: "Cash and equivalents",
                derivative: "Derivatives", mfunit: "Other funds", other: "REITs, InvITs and other" };

  // A share drawn as a bar behind its figure: an SVG <rect> whose width is the
  // figure itself, so no style attribute (the CSP allows none).
  var SVG = "http://www.w3.org/2000/svg";
  function bar(value) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "bar");
    svg.setAttribute("viewBox", "0 0 100 6");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    [["bar__track", 100], ["bar__fill", Math.max(0, Math.min(100, value))]].forEach(function (r) {
      var rect = document.createElementNS(SVG, "rect");
      rect.setAttribute("class", r[0]);
      rect.setAttribute("width", r[1].toFixed(2));
      rect.setAttribute("height", "6");
      rect.setAttribute("rx", "3");
      svg.appendChild(rect);
    });
    return el("span", { "class": "bar-cell" }, svg, el("span", null, value.toFixed(1) + "%"));
  }

  // Each file fetched once per page. A NAV file that fails rejects with the
  // reason; a look-through file that fails is null (no disclosure loaded).
  var navs = new Map(), looks = new Map();
  function navSeries(base, fund) {
    if (!navs.has(fund.id)) {
      var M = window.PortfolioMath;
      // A failed load leaves the cache, so a Retry fetches again (/sip/'s Retry).
      navs.set(fund.id, fetch(base + "/data/nav/" + fund.amfi + ".csv.gz").then(function (r) {
        if (!r.ok) throw new Error("its prices did not load (" + r.status + ")");
        return M.gzipText(r).then(M.parseNavFile);
      }).catch(function (e) { navs.delete(fund.id); throw e; }));
    }
    return navs.get(fund.id);
  }
  function lookFile(base, id) {
    if (!looks.has(id)) {
      looks.set(id, fetch(base + "/data/lookthrough/" + id + ".json")
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; }));
    }
    return looks.get(id);
  }

  // The `?` for a term whose explanation the server rendered (macros.html
  // term_pop, V1-87): a native popover, so it opens without further script.
  function termButton(key, where) {
    var pop = document.getElementById("t-" + key + "-" + where);
    if (!pop) return null;
    var label = "What is " + pop.getAttribute("data-title") + "?";
    if (!("popover" in HTMLElement.prototype)) {   // no popovers: the glossary entry instead
      return el("a", { "class": "term", href: pop.querySelector("a").getAttribute("href"),
                       "aria-label": label }, "?");
    }
    return el("button", { type: "button", "class": "term", popovertarget: pop.id, "data-key": key,
                          "aria-label": label }, "?");
  }

  // An action that waits `ms` for an Undo, then runs `done` once (the design
  // bucket's fuse-button, V1-93). The clock is passed in for tests.
  function fuse(ms, done, clock) {
    // Wrapped: a browser's timers refuse to be called as another object's methods.
    var c = clock || {
      now: function () { return Date.now(); },
      set: function (fn, wait) { return setTimeout(fn, wait); },
      clear: function (t) { clearTimeout(t); },
    };
    var end = c.now() + ms;
    var id = c.set(function () { id = null; done(); }, ms);
    return {
      remaining: function () { return id === null ? 0 : Math.max(0, end - c.now()); },
      cancel: function () {
        if (id === null) return false;
        c.clear(id);
        id = null;
        return true;
      },
    };
  }

  // The few icons drawn by script, stroked like icons.html's; beside a word, or
  // on a button that carries its name in aria-label.
  var ICONS = {
    close: ["M6 6l12 12M18 6L6 18"],
    plus: ["M12 5v14M5 12h14"],
    bin: ["M4 7h16", "M10 11v6M14 11v6", "M6 7l1 12.5A1.5 1.5 0 0 0 8.5 21h7a1.5 1.5 0 0 0 1.5-1.5L18 7",
          "M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"],
    undo: ["M9 14L4 9l5-5", "M4 9h10.5a5.5 5.5 0 0 1 0 11H11"],
  };
  function icon(name) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    ICONS[name].forEach(function (d) {
      var path = document.createElementNS(SVG, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  var api = { present: present, el: el, fill: fill, table: table, match: match, picker: picker,
              heat: heat,
              bar: bar, INR: INR, CLASS: CLASS,
              navSeries: navSeries, lookFile: lookFile, termButton: termButton,
              fuse: fuse, icon: icon };
  if (typeof module === "object" && module.exports) module.exports = api;
  else window.Kit = api;
})();
