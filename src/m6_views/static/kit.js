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
      navs.set(fund.id, fetch(base + "/data/nav/" + fund.amfi + ".csv.gz").then(function (r) {
        if (!r.ok) throw new Error("its prices did not load (" + r.status + ")");
        return M.gzipText(r).then(M.parseNavFile);
      }));
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

  var api = { present: present, el: el, fill: fill, bar: bar, INR: INR, CLASS: CLASS,
              navSeries: navSeries, lookFile: lookFile, termButton: termButton,
              fuse: fuse, icon: icon };
  if (typeof module === "object" && module.exports) module.exports = api;
  else window.Kit = api;
})();
