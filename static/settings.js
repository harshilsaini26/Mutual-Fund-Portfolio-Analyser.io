/*
 * The reader's settings, applied before the page is drawn. DECISIONS V1-83.
 *
 * Loaded in <head> without `defer`, so nobody sees one theme flash before
 * another. Six attributes on <html> carry everything the CSS and the other
 * scripts read: data-theme, -font, -size, -density, -motion and -accent.
 * "Device" theme and motion follow the phone or computer, live. Storage can be
 * missing or refused (a private window); the settings then last for the visit.
 * The panel that changes them is in app.js.
 */
(function () {
  "use strict";

  var KEY = "settings";
  var DEFAULTS = {
    theme: "device", font: "terminess", size: "standard",
    density: "comfortable", motion: "device", accent: "navy",
  };
  var CHOICES = {
    theme: ["device", "light", "dark", "matrix"],
    font: ["terminess", "rubik", "atkinson"],
    size: ["small", "standard", "large"],
    density: ["comfortable", "compact"],
    motion: ["device", "on", "off"],
    accent: ["navy", "violet", "raspberry", "graphite"],
  };
  var FONTS = {
    terminess: "fonts/terminess-Regular.woff2",
    rubik: "fonts/rubik-latin-wght-normal.woff2",
    atkinson: "fonts/atkinson-hyperlegible-latin-400-normal.woff2",
  };

  function pick(stored, key) {
    var v = stored && stored[key];
    return CHOICES[key].indexOf(v) >= 0 ? v : DEFAULTS[key];
  }

  // Stored choices and the device's preferences -> the six attribute values.
  function resolve(stored, device) {
    var theme = pick(stored, "theme");
    var motion = pick(stored, "motion");
    return {
      theme: theme === "device" ? (device.dark ? "dark" : "light") : theme,
      font: pick(stored, "font"),
      size: pick(stored, "size"),
      density: pick(stored, "density"),
      motion: motion === "device" ? (device.reducedMotion ? "off" : "on") : motion,
      accent: pick(stored, "accent"),
    };
  }

  // The stored entry, or null; the old single `theme` key is carried over once.
  function read(storage) {
    var raw, legacy;
    try {
      raw = storage.getItem(KEY);
      legacy = raw == null ? storage.getItem("theme") : null;
    } catch (e) { return { stored: null, ok: false }; }
    if (raw == null && (legacy === "light" || legacy === "dark" || legacy === "matrix")) {
      var migrated = { v: 1, theme: legacy };
      if (write(storage, migrated)) {
        try { storage.removeItem("theme"); } catch (e) { /* kept; harmless */ }
      }
      return { stored: migrated, ok: true };
    }
    if (raw == null) return { stored: null, ok: true };
    var parsed = null;
    try { parsed = JSON.parse(raw); } catch (e) { parsed = null; }
    var valid = parsed && typeof parsed === "object" && parsed.v === 1;
    return { stored: valid ? parsed : null, ok: true };
  }

  function write(storage, stored) {
    try { storage.setItem(KEY, JSON.stringify(stored)); return true; }
    catch (e) { return false; }
  }

  function apply(root, attrs) {
    Object.keys(attrs).forEach(function (k) { root.setAttribute("data-" + k, attrs[k]); });
  }

  function preloadFor(font) { return FONTS[font] || FONTS.terminess; }

  function onStorage(event, applyNow) { if (event && event.key === KEY) applyNow(); }

  var api = {
    KEY: KEY, DEFAULTS: DEFAULTS, CHOICES: CHOICES, resolve: resolve, read: read,
    write: write, apply: apply, preloadFor: preloadFor, onStorage: onStorage,
  };

  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  window.Settings = api;
  if (typeof document === "undefined") return;

  // --- in the browser -----------------------------------------------------------
  var root = document.documentElement;
  var dark = window.matchMedia("(prefers-color-scheme: dark)");
  var calm = window.matchMedia("(prefers-reduced-motion: reduce)");
  var script = document.currentScript;
  var base = script ? script.src.replace(/\/static\/settings\.js(\?.*)?$/, "") : "";
  var storage = null;
  try { storage = window.localStorage; } catch (e) { storage = null; }
  var state = storage ? read(storage) : { stored: null, ok: false };
  // When storage refuses, choices made this visit are held here instead.
  var session = state.stored;

  function now() {
    return resolve(session, { dark: dark.matches, reducedMotion: calm.matches });
  }
  function refresh() { apply(root, now()); }

  refresh();
  var link = document.createElement("link");
  link.rel = "preload"; link.as = "font"; link.type = "font/woff2"; link.crossOrigin = "anonymous";
  link.href = base + "/static/" + preloadFor(now().font);
  document.head.appendChild(link);

  [dark, calm].forEach(function (query) {
    if (query.addEventListener) query.addEventListener("change", refresh);
  });
  window.addEventListener("storage", function (event) {
    onStorage(event, function () {
      state = read(storage);
      session = state.stored;
      refresh();
    });
  });

  api.current = function () { return { stored: session, ok: state.ok }; };
  api.set = function (key, value) {
    var next = Object.assign({ v: 1 }, session || {});
    next[key] = value;
    session = next;
    state.ok = storage ? write(storage, next) : false;
    refresh();
  };
  api.reset = function () {
    session = null;
    if (storage) {
      try { storage.removeItem(KEY); state.ok = true; } catch (e) { state.ok = false; }
    }
    refresh();
  };
})();
