/*
 * The page's behaviour, loaded on every page. Everything here enhances markup
 * that already works: without this file search is an ordinary form, tables are
 * ordinary tables, the theme is light, and the page scrolls natively.
 *
 * MODULE_6.md §16.4 holds throughout: the browser positions, sorts, filters and
 * toggles; it never formats or derives a figure. A table sorts on the
 * `data-value` the server wrote beside each figure, never on the text.
 *
 * Every name is set with textContent, never as HTML -- fund names come from
 * AMFI's and fund houses' files, which this project reads but does not control.
 */
(function () {
  "use strict";

  // Explore funds' filters in the address (V1-88): "#category=…&family=…&q=…", each
  // left out when empty, so a filtered list can be shared, bookmarked and reloaded.
  var FILTER_KEYS = ["category", "family", "q"];
  function filterHash(state) {
    var parts = FILTER_KEYS.filter(function (k) { return state[k]; })
      .map(function (k) { return k + "=" + encodeURIComponent(state[k]); });
    return parts.length ? "#" + parts.join("&") : "";
  }
  // Unknown keys, broken escapes and repeats (the first wins) are ignored; whether
  // a value is one of the page's options is the page's to check.
  function parseFilterHash(hash) {
    var out = { category: "", family: "", q: "" }, seen = {};
    String(hash || "").replace(/^#/, "").split("&").forEach(function (pair) {
      var at = pair.indexOf("=");
      if (at < 0) return;
      var key = pair.slice(0, at), value;
      if (FILTER_KEYS.indexOf(key) < 0 || seen[key]) return;
      seen[key] = true;
      try { value = decodeURIComponent(pair.slice(at + 1)); } catch (e) { return; }
      out[key] = value;
    });
    return out;
  }
  // Any other hash ("#content", the skip link's target) is not ours to follow.
  function isFilterHash(hash) {
    return /(^#|&)(category|family|q)=/.test(String(hash || ""));
  }
  // On load the hash wins; "?q=" (the search box's plain form) only fills a missing q.
  function initialFilters(search, hash) {
    var state = isFilterHash(hash) ? parseFilterHash(hash) : { category: "", family: "", q: "" };
    var query = /(^#|&)q=/.test(String(hash || "")) ? null : /[?&]q=([^&]*)/.exec(search || "");
    if (query) {
      try { state.q = decodeURIComponent(query[1].replace(/\+/g, " ")); } catch (e) { /* none */ }
    }
    return state;
  }
  // Where a submitted public search goes: /funds/ with the words in the fragment,
  // which a browser never sends, so what is typed stays on this device (V1-89).
  function searchTarget(action, value) {
    return String(action).split("#")[0].split("?")[0] +
      filterHash({ category: "", family: "", q: String(value).trim() });
  }
  // fn once the calls have paused for ms, with the last call's arguments.
  function later(fn, ms) {
    var timer;
    return function () {
      var args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(null, args); }, ms);
    };
  }
  // Where a hover explanation opens (V1-91): just under its label and aligned to
  // its left edge; above it when the screen has no room below; never past an edge.
  function hintPlace(rect, width, height, viewWidth, viewHeight) {
    var gap = 8, edge = 8;
    var top = rect.bottom + gap;
    if (top + height > viewHeight - edge) top = rect.top - gap - height;
    return {
      left: Math.max(edge, Math.min(rect.left, viewWidth - width - edge)),
      top: Math.max(edge, top),
    };
  }
  // The label a `?` explains: the nearest element, from `node` up, with a `.term`
  // among its own children. Walked by hand: `:has()` throws in older browsers.
  function termHost(node) {
    for (var n = node; n && n.nodeType === 1; n = n.parentElement) {
      for (var c = n.firstElementChild; c; c = c.nextElementSibling) {
        if (c.classList.contains("term")) return n;
      }
    }
    return null;
  }
  // Explore funds (UI/UX critique E-01 to E-03): the funds a view shows, from every
  // fund's row in funds/rows.json, filtered by family, category and the words of a
  // name, then sorted on a column -- by default the largest fund first. A fund with
  // no figure sorts last either way: an absent return is not the lowest return.
  function exploreRows(rows, state) {
    var typed = words(state.q || "");
    var key = state.sort || "size", down = state.dir !== "asc";
    var value = function (r) {
      if (key === "name") return r.name.toLowerCase();
      if (key === "cat") return r.cat_name.toLowerCase();
      var cell = r.c[key];
      return cell && cell[0] !== "" ? Number(cell[0]) : null;
    };
    return rows.filter(function (r) {
      var name = words(r.name).join(" ");
      return (!state.family || r.family === state.family) &&
        (!state.category || r.cat === state.category) &&
        typed.every(function (w) { return name.indexOf(w) !== -1; });
    }).map(function (r, i) { return [r, value(r), i]; }).sort(function (a, b) {
      if (a[1] === null || b[1] === null) return (a[1] === null) - (b[1] === null) || a[2] - b[2];
      var d = a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0;
      return (down ? -d : d) || a[2] - b[2];
    }).map(function (x) { return x[0]; });
  }
  // How many funds each family holds, and each category within the family chosen:
  // the filters' options say so, and offer only categories of that family (E-03).
  function exploreCounts(rows, family) {
    var families = {}, categories = {};
    rows.forEach(function (r) {
      families[r.family] = (families[r.family] || 0) + 1;
      if (!family || r.family === family) categories[r.cat] = (categories[r.cat] || 0) + 1;
    });
    return { families: families, categories: categories };
  }

  if (typeof module === "object" && module.exports) {
    module.exports = { filterHash: filterHash, parseFilterHash: parseFilterHash,
                       isFilterHash: isFilterHash, initialFilters: initialFilters,
                       later: later, searchTarget: searchTarget, hintPlace: hintPlace,
                       termHost: termHost, sortKey: sortKey,
                       exploreRows: exploreRows, exploreCounts: exploreCounts };
    return;
  }

  var ROOT = document.body.getAttribute("data-root") || "";

  // The top bar's menu (V1-88) is a native popover: Esc and a tap outside close it
  // already. Choosing a link on this same page (Categories, About) and widening
  // past 1180px, where the links sit inline, close it too.
  var topnav = document.getElementById("topnav");
  if (topnav && topnav.hidePopover) {
    var shut = function () { if (topnav.matches(":popover-open")) topnav.hidePopover(); };
    topnav.addEventListener("click", function (e) { if (e.target.closest("a")) shut(); });
    window.matchMedia("(min-width: 1180px)").addEventListener("change", function (e) {
      if (e.matches) shut();
    });
  }

  // A browser without popovers (V1-87): each `?` becomes a link to its entry in
  // the glossary, so the explanation is still one tap away.
  if (!("popover" in HTMLElement.prototype)) {
    document.querySelectorAll("button.term").forEach(function (button) {
      var link = document.createElement("a");
      link.className = "term";
      link.href = ROOT + "/learn/glossary/#" + button.getAttribute("data-key");
      link.setAttribute("aria-label", button.getAttribute("aria-label"));
      link.textContent = "?";
      button.replaceWith(link);
    });
  }

  // Hover explanations (V1-91). The label of every figure with a glossary entry
  // carries a `?` and its explanation (V1-87); pausing on the label, or tabbing to
  // the `?`, opens that same card beside it as a light hint. A click or a tap on
  // the `?` still opens it as before, and Esc closes either. One set of listeners
  // for the page, not one per label.
  if ("popover" in HTMLElement.prototype) {
    var HINT_OPEN_MS = 300, HINT_CLOSE_MS = 200;
    var hinted = null, hintHost = null, openTimer = null, closeTimer = null;
    var popOf = function (button) {
      return document.getElementById(button.getAttribute("popovertarget"));
    };
    var hostOf = termHost;
    var closeHint = function () {
      if (hinted && hinted.matches(":popover-open") &&
          hinted.classList.contains("term-pop--hint")) hinted.hidePopover();
      hinted = hintHost = null;
    };
    var openHint = function (host) {
      var button = host.querySelector(":scope > .term"), pop = button && popOf(button);
      if (!pop || pop.matches(":popover-open")) return;   // already open, as it was
      closeHint();
      pop.classList.add("term-pop--hint");
      pop.showPopover();
      var place = hintPlace(host.getBoundingClientRect(), pop.offsetWidth, pop.offsetHeight,
                            window.innerWidth, window.innerHeight);
      pop.style.left = place.left + "px";
      pop.style.top = place.top + "px";
      hinted = pop;
      hintHost = host;
    };
    // A click on the `?` of an open hint keeps it open (it would otherwise
    // toggle shut); on a closed one it opens the card as before, unplaced.
    document.addEventListener("click", function (e) {
      var button = e.target.closest && e.target.closest("button.term");
      if (!button) return;
      var pop = popOf(button);
      if (!pop) return;
      if (pop === hinted && pop.matches(":popover-open")) {
        e.preventDefault();
        hinted = hintHost = null;   // pinned: leaving the label no longer closes it
      } else {
        pop.classList.remove("term-pop--hint");
        pop.style.left = pop.style.top = "";
      }
    });
    document.addEventListener("focusin", function (e) {
      if (e.target.matches && e.target.matches("button.term:focus-visible")) {
        openHint(e.target.parentElement);
      }
    });
    document.addEventListener("focusout", function (e) {
      if (hinted && !(e.relatedTarget && hinted.contains(e.relatedTarget))) closeHint();
    });
    if (window.matchMedia("(hover: hover)").matches) {
      document.addEventListener("mouseover", function (e) {
        if (hinted && hinted.contains(e.target)) { clearTimeout(closeTimer); return; }
        var host = hostOf(e.target);
        if (!host) return;
        clearTimeout(closeTimer);
        clearTimeout(openTimer);
        openTimer = setTimeout(function () { openHint(host); }, HINT_OPEN_MS);
      });
      document.addEventListener("mouseout", function (e) {
        var to = e.relatedTarget;
        if (to && ((hinted && hinted.contains(to)) || (hintHost && hintHost.contains(to)))) return;
        if (hostOf(to) === hostOf(e.target) && hostOf(to)) return;
        clearTimeout(openTimer);
        closeTimer = setTimeout(closeHint, HINT_CLOSE_MS);
      });
    }
  }

  function store(key, value) {
    try {
      if (value === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, value);
    } catch (e) { /* storage refused: a convenience lost, nothing else */ }
    return null;
  }

  // --- search ---------------------------------------------------------------
  //
  // Suggestions as you type, from /api/search on the server, or on the public
  // copy (no server, DECISIONS V1-72) from search.json matched here by the
  // server's rules: every word typed must appear, the words in the order typed
  // rank first, then names starting with the first word, then shorter names.

  var index = null;

  function words(text) {
    return text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(" ")
      .filter(Boolean).slice(0, 6);
  }

  function local(query) {
    var typed = words(query);
    var phrase = typed.join(" ");
    return index
      .map(function (hit) { return { hit: hit, name: words(hit.name).join(" ") }; })
      .filter(function (c) {
        return typed.every(function (w) { return c.name.indexOf(w) !== -1; });
      })
      .sort(function (a, b) {
        var keyA = [a.name.indexOf(phrase) === -1, a.name.indexOf(typed[0]) !== 0, a.name.length];
        var keyB = [b.name.indexOf(phrase) === -1, b.name.indexOf(typed[0]) !== 0, b.name.length];
        for (var i = 0; i < 3; i++) {
          if (keyA[i] !== keyB[i]) return keyA[i] < keyB[i] ? -1 : 1;
        }
        return a.name < b.name ? -1 : 1;
      })
      .slice(0, 10)
      .map(function (c) { return c.hit; });
  }

  function suggestions(input) {
    var list = input.parentNode.querySelector(".search__suggest");
    if (!list) return;
    var timer = null;
    var asked = "";

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
    }

    function show(hits) {
      list.textContent = "";
      hits.forEach(function (hit) {
        var item = document.createElement("li");
        var link = document.createElement("a");
        link.href = hit.url;
        var name = document.createElement("span");
        name.className = "search__name";
        name.textContent = hit.name;
        var meta = document.createElement("span");
        meta.className = "search__meta";
        meta.textContent = hit.detail;
        link.appendChild(name);
        link.appendChild(meta);
        item.appendChild(link);
        list.appendChild(item);
      });
      list.hidden = hits.length === 0;
      input.setAttribute("aria-expanded", String(hits.length > 0));
    }

    function suggest() {
      var query = input.value.trim();
      if (query.length < 2) { close(); return; }
      if (query === asked) return;
      asked = query;
      var bundled = input.getAttribute("data-index");
      if (bundled) {
        // Kept only once it has arrived: a failed fetch is tried again next time.
        var ready = index ? Promise.resolve() : fetch(bundled)
          .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
          .then(function (all) { index = all; });
        ready.then(function () { if (query === asked) show(local(query)); }).catch(close);
        return;
      }
      fetch(input.getAttribute("data-suggest") + "?q=" + encodeURIComponent(query), {
        headers: { Accept: "application/json" },
      })
        .then(function (r) { return r.ok ? r.json() : []; })
        .then(function (hits) { if (query === asked) show(hits); })
        .catch(close);
    }

    // The public search box has no name, so its form sends nothing; on submit the
    // words go to /funds/ in the fragment instead (V1-89).
    if (input.getAttribute("data-index") && input.form) {
      input.form.addEventListener("submit", function (e) {
        e.preventDefault();
        window.location.assign(searchTarget(input.form.action, input.value));
      });
    }
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(suggest, 150);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" && !list.hidden) {
        var first = list.querySelector("a");
        if (first) { first.focus(); e.preventDefault(); }
      } else if (e.key === "Escape") {
        close();
      }
    });
    list.addEventListener("keydown", function (e) {
      var links = Array.prototype.slice.call(list.querySelectorAll("a"));
      var at = links.indexOf(document.activeElement);
      if (e.key === "ArrowDown" && at < links.length - 1) {
        links[at + 1].focus(); e.preventDefault();
      } else if (e.key === "ArrowUp") {
        (at > 0 ? links[at - 1] : input).focus(); e.preventDefault();
      } else if (e.key === "Escape") {
        close(); input.focus();
      }
    });
    document.addEventListener("click", function (e) {
      if (!input.parentNode.contains(e.target)) close();
    });
  }

  document.querySelectorAll("input[data-suggest], input[data-index]").forEach(suggestions);

  // --- settings (DECISIONS V1-83) ----------------------------------------------
  //
  // settings.js applied the reader's choices before the page was drawn and owns
  // storage; this is the panel that changes them. Each radio applies at once.
  // charts.js watches the attributes and follows.

  var panel = document.getElementById("settings");
  if (panel && window.Settings && panel.showModal) {
    var S = window.Settings;
    var html = document.documentElement;

    var check = function () {
      var chosen = Object.assign({}, S.DEFAULTS, S.current().stored || {});
      Object.keys(S.DEFAULTS).forEach(function (key) {
        panel.querySelectorAll('input[name="setting-' + key + '"]').forEach(function (input) {
          input.checked = input.value === chosen[key];
        });
      });
      panel.querySelector("[data-settings-note]").hidden = S.current().ok;
    };

    // Matrix is one colour by design: the accent waits, kept, until it is left.
    var matrix = function () {
      var on = html.getAttribute("data-theme") === "matrix";
      panel.querySelectorAll('input[name="setting-accent"]').forEach(function (input) {
        input.disabled = on;
      });
      panel.querySelector("[data-matrix-note]").hidden = !on;
    };

    document.querySelectorAll("[data-settings-open]").forEach(function (button) {
      button.hidden = false;
      button.addEventListener("click", function () { check(); matrix(); panel.showModal(); });
    });
    panel.querySelector("[data-settings-close]").addEventListener("click", function () { panel.close(); });
    // A click on the backdrop lands on the dialog itself, and so does one on the
    // panel's own blank space: only a click outside its box closes it.
    panel.addEventListener("click", function (event) {
      if (event.target !== panel) return;
      var box = panel.getBoundingClientRect();
      var inside = event.clientX >= box.left && event.clientX <= box.right &&
        event.clientY >= box.top && event.clientY <= box.bottom;
      if (!inside) panel.close();
    });
    panel.addEventListener("change", function (event) {
      var input = event.target;
      if (!input.name || input.name.indexOf("setting-") !== 0) return;
      S.set(input.name.slice("setting-".length), input.value);
      panel.querySelector("[data-settings-note]").hidden = S.current().ok;
    });
    panel.querySelector("[data-settings-reset]").addEventListener("click", function () {
      S.reset();
      check();
    });
    // The recently viewed funds, which the privacy text names (UI/UX critique G-21).
    var forget = panel.querySelector("[data-recent-clear]");
    if (forget) forget.addEventListener("click", function () {
      try { window.localStorage.removeItem(RECENT); } catch (e) { /* nothing kept */ }
      forget.textContent = "Recently viewed cleared";
    });
    new MutationObserver(matrix).observe(html, { attributes: true, attributeFilter: ["data-theme"] });
  }

  // --- phones: tucked detail and a top bar that steps aside (V1-84) ----------
  //
  // `details.tuck` blocks are open in the HTML, so a wide screen and a page
  // without scripts show everything; on a narrow screen they start closed, one
  // tap from open. They are not reopened on resize: a reader may have opened one.
  var narrowScreen = window.matchMedia("(max-width: 720px)");
  if (narrowScreen.matches) {
    document.querySelectorAll("details.tuck").forEach(function (d) { d.open = false; });
  }

  // --bar-h: the top bar's height, for scroll-padding-top and the navigator's
  // pinned position. It follows the reader's text size and font.
  var topbar = document.querySelector(".topbar");
  var root = document.documentElement;
  if (topbar) {
    var barHeight = function () { root.style.setProperty("--bar-h", topbar.offsetHeight + "px"); };
    barHeight();
    window.addEventListener("resize", barHeight);
    new MutationObserver(barHeight).observe(root, {
      attributes: true, attributeFilter: ["data-size", "data-font"],
    });

    // On a phone, with motion on, the bar slides away while the reader scrolls
    // down and comes back on any scroll up. It stays while anything in it has
    // focus (typing a search), and it never moves with motion off.
    // The 8px is measured over the whole downward run, not per scroll event: a
    // reader's slow drag moves a few pixels a frame and must hide it too.
    var lastY = window.scrollY;
    var runStart = lastY;
    var setAway = function (away) {
      topbar.classList.toggle("topbar--away", away);
      document.body.classList.toggle("bar-away", away);
    };
    window.addEventListener("scroll", function () {
      var y = window.scrollY;
      var still = !narrowScreen.matches || root.getAttribute("data-motion") !== "on" ||
        topbar.contains(document.activeElement);
      if (y < lastY) runStart = y;
      if (still || y < lastY) setAway(false);
      else if (y - runStart > 8 && y > topbar.offsetHeight) setAway(true);
      lastY = y;
    }, { passive: true });
    // Keyboard focus arriving in the bar (Shift+Tab, a dialog handing focus back)
    // brings it back at once: a focused control must never sit out of view.
    topbar.addEventListener("focusin", function () { setAway(false); });
  }

  // --- the menu on a narrow screen --------------------------------------------

  var menu = document.querySelector("[data-sidebar-toggle]");
  if (menu) {
    menu.addEventListener("click", function () {
      var open = document.body.classList.toggle("sidebar-open");
      menu.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && document.body.classList.contains("sidebar-open")) {
        document.body.classList.remove("sidebar-open");
        menu.setAttribute("aria-expanded", "false");
        menu.focus();
      }
    });
  }

  // --- tables wider than their box (UI/UX critique G-17) -------------------------
  //
  // A table region that scrolls sideways is a tab stop, so a keyboard can scroll
  // it; one that fits is not, so a page of tables is not a page of extra stops.
  // While more of it lies to the right, its right edge fades (the scroll hint).
  // Both the region and its table are watched: either may change size (the window,
  // the text size, a `<details>` opening), and the page scripts draw new ones.
  function moreRight(wrap) {
    wrap.classList.toggle("table-wrap--more", wrap.scrollWidth - wrap.clientWidth - wrap.scrollLeft > 1);
  }
  var scrollers = new ResizeObserver(function (entries) {
    entries.forEach(function (e) {
      var wrap = e.target.closest(".table-wrap");
      if (wrap.scrollWidth > wrap.clientWidth + 1) wrap.setAttribute("tabindex", "0");
      else wrap.removeAttribute("tabindex");
      moreRight(wrap);
    });
  });
  document.addEventListener("scroll", function (e) {
    if (e.target.classList && e.target.classList.contains("table-wrap")) moreRight(e.target);
  }, { capture: true, passive: true });
  function eachTable(node, act) {
    if (node.nodeType !== 1) return;
    (node.matches(".table-wrap") ? [node] : node.querySelectorAll(".table-wrap")).forEach(function (wrap) {
      act.call(scrollers, wrap);
      if (wrap.firstElementChild) act.call(scrollers, wrap.firstElementChild);
    });
  }
  eachTable(document.body, scrollers.observe);
  new MutationObserver(function (records) {
    records.forEach(function (r) {
      r.removedNodes.forEach(function (n) { eachTable(n, scrollers.unobserve); });
      r.addedNodes.forEach(function (n) { eachTable(n, scrollers.observe); });
    });
  }).observe(document.body, { childList: true, subtree: true });

  // --- sortable tables ----------------------------------------------------------
  //
  // A header button sorts on the server's `data-value` (a number) or on the
  // cell's text. A cell with no figure sorts last in either direction: an
  // absent return is not the lowest return.

  // "number" sorts on the figure, "value" on the server's value as text (an
  // ISO date sorts correctly that way), "text" on what the cell says.
  function sortKey(row, column, mode) {
    var cell = row.cells[column];
    if (mode === "text") return (cell.textContent || "").trim().toLowerCase();
    var raw = cell.getAttribute("data-value");
    if (raw === null || raw === "") return null;
    if (mode !== "number") return raw;
    var n = parseFloat(raw);
    return isNaN(n) ? null : n;   // not a number: missing, so it sorts last
  }

  document.querySelectorAll("table[data-sortable]").forEach(function (table) {
    var body = table.tBodies[0];
    if (!body) return;
    table.querySelectorAll("th button[data-sort]").forEach(function (button) {
      var th = button.closest("th");
      var column = Array.prototype.indexOf.call(th.parentNode.children, th);
      var mode = button.getAttribute("data-sort");
      var numeric = mode !== "text";
      button.addEventListener("click", function () {
        // First click: figures largest first, names A to Z. Then it alternates.
        var current = th.getAttribute("aria-sort");
        var ascending = current === null ? !numeric : current !== "ascending";
        table.querySelectorAll("th[aria-sort]").forEach(function (other) {
          other.removeAttribute("aria-sort");
        });
        th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = sortKey(a, column, mode);
          var y = sortKey(b, column, mode);
          if (x === null && y === null) return 0;
          if (x === null) return 1;
          if (y === null) return -1;
          if (x === y) return 0;
          return (x < y ? -1 : 1) * (ascending ? 1 : -1);
        });
        rows.forEach(function (row) { body.appendChild(row); });
      });
    });
  });

  // --- Explore funds (UI/UX critique E-01 to E-07) -----------------------------------
  //
  // The page draws the 50 largest funds; every fund's row, its cells formatted by
  // the build, is in funds/rows.json. Here the filters, the sort and "Show 50 more"
  // draw rows from that data, in the page's own markup (explorer.html's `cell`).
  // Until it has loaded, the 50 stay as drawn.

  var table = document.querySelector("table[data-rows]");
  if (table) {
    var family = document.querySelector("select[data-filter-family]");
    var category = document.querySelector("select[data-filter-category]");
    var text = document.querySelector("input[data-filter-text]");
    var count = document.querySelector("[data-filter-count]");
    var sortBy = document.querySelector("select[data-sort-select]");
    var empty = document.querySelector("[data-empty]");
    var more = document.querySelector("[data-more]");
    var chooser = document.querySelector("[data-columns]");
    var body = table.tBodies[0];
    var heads = Array.prototype.slice.call(table.tHead.rows[0].cells);
    var STEP = 50, COLUMNS = "lookthrough.columns.v1";
    var PHONE_HIDE = "ter r1 r5 rank vol3 fall3 sharpe3";   // a phone's row: category, size, 3 years
    var data = null, shown = STEP, sort = { key: "size", dir: "desc" };

    // The page's markup for one cell (explorer.html's `cell` macro).
    var cell = function (r, th) {
      var key = th.getAttribute("data-col"), td = document.createElement("td");
      td.setAttribute("data-col", key);
      if (key === "name") {
        var link = document.createElement("a");
        link.className = "fund-name";
        link.href = ROOT + "/fund/" + r.id + "/";
        link.textContent = r.name;
        var house = document.createElement("span");
        house.className = "cell-sub";
        house.textContent = r.house;
        td.append(link, " ", house);
        return td;
      }
      if (key === "cat") { td.textContent = r.cat_name; return td; }
      var c = r.c[key], tone = /^r\d$/.test(key) ? c[2] : "";
      td.className = "num" + (tone ? " ret--" + tone : "");
      td.setAttribute("data-label", th.getAttribute("data-short"));
      if (c[0] !== "") td.setAttribute("data-value", c[0]);
      if (tone && c[3]) {
        var symbol = document.createElement("span");
        symbol.className = "ret__symbol";
        symbol.setAttribute("aria-hidden", "true");
        symbol.textContent = c[3];
        td.appendChild(symbol);
      }
      td.appendChild(document.createTextNode(c[1]));
      if (key === "rank" && c[2]) {
        var quarter = document.createElement("span");
        quarter.className = "cell-sub";
        quarter.textContent = c[2];
        td.appendChild(quarter);
      }
      return td;
    };

    // Each family and category option says how many funds it holds; the categories
    // are only the chosen family's (E-03).
    var options = function () {
      var counts = exploreCounts(data, family.value);
      Array.prototype.forEach.call(family.options, function (o) {
        if (!o.hasAttribute("data-name")) o.setAttribute("data-name", o.textContent);
        var n = o.value ? counts.families[o.value] || 0 : data.length;
        o.textContent = o.getAttribute("data-name") + " (" + n.toLocaleString("en-IN") + ")";
      });
      var names = {};
      data.forEach(function (r) { names[r.cat] = r.cat_name; });
      var keys = Object.keys(counts.categories).sort(function (a, b) {
        return names[a].toLowerCase() < names[b].toLowerCase() ? -1 : 1;
      });
      var kept = category.value, total = 0;
      keys.forEach(function (k) { total += counts.categories[k]; });
      category.replaceChildren(new Option("All categories (" + total.toLocaleString("en-IN") + ")", ""));
      keys.forEach(function (k) {
        category.appendChild(new Option(names[k] + " (" + counts.categories[k].toLocaleString("en-IN") + ")", k));
      });
      category.value = keys.indexOf(kept) >= 0 ? kept : "";
    };

    // The view is the address: replaced, not pushed, so Back still leaves; written
    // once typing pauses, since Safari refuses a burst of replaceState calls. The
    // hash carries q, so a "?q=" the page was opened with is dropped.
    var writeAddress = later(function (hash) {
      history.replaceState(null, "", location.pathname + hash);
    }, 250);
    var draw = function () {
      var hits = exploreRows(data, { family: family.value, category: category.value,
                                     q: text.value, sort: sort.key, dir: sort.dir });
      var rows = document.createDocumentFragment();
      hits.slice(0, shown).forEach(function (r) {
        var tr = document.createElement("tr");
        tr.setAttribute("data-family", r.family);
        tr.setAttribute("data-category", r.cat);
        heads.forEach(function (th) { tr.appendChild(cell(r, th)); });
        rows.appendChild(tr);
      });
      body.replaceChildren(rows);
      count.textContent = hits.length === data.length
        ? data.length.toLocaleString("en-IN") + " funds"
        : hits.length.toLocaleString("en-IN") + " of " + data.length.toLocaleString("en-IN") + " funds";
      empty.hidden = hits.length > 0;
      more.parentNode.hidden = hits.length <= shown;
      more.textContent = "Show " + Math.min(STEP, hits.length - shown) + " more";
      heads.forEach(function (th) {
        if (th.getAttribute("data-col") === sort.key) {
          th.setAttribute("aria-sort", sort.dir === "asc" ? "ascending" : "descending");
        } else th.removeAttribute("aria-sort");
      });
      var asked = sort.key + ":" + sort.dir;
      sortBy.value = Array.prototype.some.call(sortBy.options, function (o) { return o.value === asked; })
        ? asked : "";
      writeAddress(filterHash({ category: category.value, family: family.value, q: text.value.trim() }));
    };
    var refilter = function () { shown = STEP; if (data) draw(); };

    family.addEventListener("change", function () { if (data) options(); refilter(); });
    category.addEventListener("change", refilter);
    text.addEventListener("input", refilter);
    more.addEventListener("click", function () { shown += STEP; draw(); });
    document.querySelector("[data-filter-clear]").addEventListener("click", function () {
      family.value = "";
      category.value = "";
      text.value = "";
      options();
      refilter();
      family.focus();
    });
    // A heading sorts by its column: figures largest first, names A to Z, then
    // the other way. A phone has the list of sorts instead (E-07).
    heads.forEach(function (th) {
      var button = th.querySelector("button[data-sort]");
      var key = th.getAttribute("data-col");
      button.addEventListener("click", function () {
        if (!data) return;
        var named = key === "name" || key === "cat";
        sort = { key: key, dir: sort.key === key ? (sort.dir === "asc" ? "desc" : "asc") : (named ? "asc" : "desc") };
        refilter();
      });
    });
    sortBy.addEventListener("change", function () {
      if (!data || !sortBy.value) return;
      var parts = sortBy.value.split(":");
      sort = { key: parts[0], dir: parts[1] };
      refilter();
    });

    // The columns shown (E-05): the reader's choice, kept in this browser; else
    // the page's, or on a phone the three a two-line row holds.
    var hide = function (list) {
      table.setAttribute("data-hide", list);
      chooser.querySelectorAll("input[type=checkbox]").forEach(function (box) {
        box.checked = list.split(" ").indexOf(box.value) < 0;
      });
    };
    var kept = store(COLUMNS);   // "" is a choice too: every column shown
    hide(kept !== null ? kept
      : window.matchMedia("(max-width: 720px)").matches ? PHONE_HIDE : table.getAttribute("data-hide"));
    chooser.hidden = false;
    chooser.addEventListener("change", function () {
      var off = Array.prototype.filter.call(chooser.querySelectorAll("input[type=checkbox]"), function (box) {
        return !box.checked;
      }).map(function (box) { return box.value; }).join(" ");
      hide(off);
      store(COLUMNS, off);
    });

    // "#category=…&family=…&q=…": the front page's category cards, a shared or
    // bookmarked view, or Back and Forward; "?q=hdfc": the search box's plain form.
    // A value the page has no option for is ignored.
    var choose = function (select, value) {
      var known = Array.prototype.some.call(select.options, function (o) { return o.value === value; });
      select.value = known ? value : "";
    };
    var follow = function (asked) {
      choose(family, asked.family);
      options();
      choose(category, asked.category);
      text.value = asked.q;
      refilter();
    };

    fetch(table.getAttribute("data-rows")).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    }).then(function (rows) {
      data = rows;
      options();
      if (isFilterHash(location.hash) || /[?&]q=/.test(location.search)) {
        follow(initialFilters(location.search, location.hash));
      } else draw();
    }).catch(function () {
      count.textContent = "The full list did not load; reload the page to try again.";
    });
    // An emptied hash resets the view; "#content" and other anchors leave it be.
    window.addEventListener("hashchange", function () {
      if (data && (!location.hash || isFilterHash(location.hash))) follow(parseFilterHash(location.hash));
    });

    // A category tile narrows the table rather than jumping to the plain lists
    // below it, which are the way through with scripts off.
    document.querySelectorAll("a[data-family]").forEach(function (tile) {
      tile.addEventListener("click", function (e) {
        if (!data) return;
        e.preventDefault();
        family.value = tile.getAttribute("data-family");
        options();
        refilter();
        table.closest("section").scrollIntoView({ block: "start" });
      });
    });
  }

  // --- recently viewed funds --------------------------------------------------------
  //
  // Kept in this browser only, for this reader: a fund page records itself, and
  // the home page lists the last few. Stored ids are checked before they become
  // links, so nothing in storage can become anything but a link to a fund page.

  var RECENT = "recent-funds";
  var FUND_ID = /^[A-Za-z0-9_-]{1,40}$/;

  function recent() {
    try {
      var parsed = JSON.parse(store(RECENT) || "[]");
      return Array.isArray(parsed) ? parsed.filter(function (f) {
        return f && FUND_ID.test(String(f.id)) && typeof f.name === "string";
      }) : [];
    } catch (e) { return []; }
  }

  var here = document.body.getAttribute("data-fund-id");
  if (here && FUND_ID.test(here)) {
    var name = document.body.getAttribute("data-fund-name") || here;
    var seen = recent().filter(function (f) { return f.id !== here; });
    seen.unshift({ id: here, name: name });
    store(RECENT, JSON.stringify(seen.slice(0, 6)));
  }

  // --- smooth scrolling (Lenis, DECISIONS V1-80) ---------------------------------
  //
  // Only where motion is welcome; anchors still jump to their target, and a box
  // that scrolls on its own -- the /funds/ table, the app's sidebar, a panel's
  // table -- keeps the wheel (`allowNestedScroll`; Lenis's default hands every
  // wheel to the page, which left the fund table unscrollable).

  // Started and stopped by the reader's Motion setting (`data-motion`, V1-83),
  // live: turning motion off hands scrolling straight back to the browser.
  var lenis = null;
  function motion() {
    var on = document.documentElement.getAttribute("data-motion") === "on";
    if (on && !lenis && window.Lenis) {
      lenis = new window.Lenis({ autoRaf: true, anchors: true, allowNestedScroll: true });
    } else if (!on && lenis) {
      lenis.destroy();
      lenis = null;
    }
  }
  motion();
  new MutationObserver(motion).observe(document.documentElement, {
    attributes: true, attributeFilter: ["data-motion"],
  });

  document.querySelectorAll("[data-recent]").forEach(function (box) {
    var funds = recent();
    var list = box.querySelector("ul");
    if (!funds.length || !list) return;
    var slash = box.getAttribute("data-recent-slash") === "true" ? "/" : "";
    funds.forEach(function (fund) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = ROOT + "/fund/" + encodeURIComponent(fund.id) + slash;
      link.textContent = fund.name;
      item.appendChild(link);
      list.appendChild(item);
    });
    box.hidden = false;
  });
})();
