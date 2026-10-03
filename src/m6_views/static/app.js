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
  if (typeof module === "object" && module.exports) {
    module.exports = { filterHash: filterHash, parseFilterHash: parseFilterHash,
                       isFilterHash: isFilterHash, initialFilters: initialFilters,
                       later: later, searchTarget: searchTarget };
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
        var ready = index ? Promise.resolve() : fetch(bundled)
          .then(function (r) { return r.ok ? r.json() : []; })
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
    return mode === "number" ? parseFloat(raw) : raw;
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

  // --- filtering the public copy's fund table -------------------------------------

  var table = document.querySelector("table[data-filterable]");
  if (table) {
    var family = document.querySelector("select[data-filter-family]");
    var category = document.querySelector("select[data-filter-category]");
    var text = document.querySelector("input[data-filter-text]");
    var count = document.querySelector("[data-filter-count]");
    var all = table.tBodies[0].rows;

    // The view is the address: replaced, not pushed, so Back still leaves; written
    // once typing pauses, since Safari refuses a burst of replaceState calls. The
    // hash carries q, so a "?q=" the page was opened with is dropped.
    var writeAddress = later(function (hash) {
      history.replaceState(null, "", location.pathname + hash);
    }, 250);
    var apply = function () {
      var wanted = family ? family.value : "";
      var kind = category ? category.value : "";
      var typed = text ? words(text.value) : [];
      var shown = 0;
      Array.prototype.forEach.call(all, function (row) {
        var name = words(row.cells[0].textContent || "").join(" ");
        var match = (!wanted || row.getAttribute("data-family") === wanted) &&
          (!kind || row.getAttribute("data-category") === kind) &&
          typed.every(function (w) { return name.indexOf(w) !== -1; });
        row.hidden = !match;
        if (match) shown += 1;
      });
      if (count) {
        count.textContent = shown === all.length
          ? all.length + " funds"
          : shown + " of " + all.length + " funds";
      }
      writeAddress(filterHash({ category: category ? category.value : "",
                                family: family ? family.value : "",
                                q: text ? text.value.trim() : "" }));
    };
    if (family) family.addEventListener("change", apply);
    if (category) category.addEventListener("change", apply);
    if (text) text.addEventListener("input", apply);

    // "#category=…&family=…&q=…": the front page's category cards, a shared or
    // bookmarked view, or Back and Forward; "?q=hdfc": the search box's plain form.
    // A value the page has no option for is ignored.
    var choose = function (select, value) {
      if (!select) return;
      var known = Array.prototype.some.call(select.options, function (o) { return o.value === value; });
      select.value = known ? value : "";
    };
    var follow = function (asked) {
      choose(family, asked.family);
      choose(category, asked.category);
      if (text) text.value = asked.q;
      apply();
    };
    if (isFilterHash(location.hash) || /[?&]q=/.test(location.search)) {
      follow(initialFilters(location.search, location.hash));
    }
    // An emptied hash resets the view; "#content" and other anchors leave it be.
    window.addEventListener("hashchange", function () {
      if (!location.hash || isFilterHash(location.hash)) follow(parseFilterHash(location.hash));
    });

    // A category tile narrows the table rather than jumping to the plain lists
    // below it, which are the way through with scripts off.
    document.querySelectorAll("a[data-family]").forEach(function (tile) {
      tile.addEventListener("click", function (e) {
        if (!family) return;
        e.preventDefault();
        family.value = tile.getAttribute("data-family");
        apply();
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
