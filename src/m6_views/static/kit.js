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

  var api = { present: present, el: el, fill: fill, bar: bar, INR: INR, CLASS: CLASS,
              navSeries: navSeries, lookFile: lookFile };
  if (typeof module === "object" && module.exports) module.exports = api;
  else window.Kit = api;
})();
