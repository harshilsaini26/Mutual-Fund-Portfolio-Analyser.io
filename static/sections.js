/*
 * The fund page's section navigator. DECISIONS V1-84.
 *
 * The links themselves are server-rendered (fund.html) and work without this
 * file. This marks which section the reader is in, keeps that chip in view on a
 * narrow screen, opens the closed "Every figure" table when it is chosen, and
 * keeps --nav-h (the navigator's height, for scroll-padding-top) true.
 */
(function () {
  "use strict";

  // Of the sections whose top the reader has passed (top <= scrollY + offset), the
  // lowest on the page; the first before any is reached; the last once the page's
  // bottom is reached. Lowest, not last in page order: on a wide screen panels
  // share rows, so page order and position differ. Panels sharing a row (equal
  // tops) are stood for by the first of them in page order.
  function currentSection(tops, scrollY, offset, atBottom) {
    if (!tops.length) return null;
    if (atBottom) return tops[tops.length - 1].id;
    var current = tops[0];
    for (var i = 0; i < tops.length; i++) {
      if (tops[i].top <= scrollY + offset && tops[i].top > current.top) current = tops[i];
    }
    return current.id;
  }

  var api = { currentSection: currentSection };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  window.Sections = api;

  // --- in the browser -----------------------------------------------------------
  var nav = document.querySelector("nav.sections");
  if (!nav) return;
  var html = document.documentElement;
  var chips = Array.prototype.slice.call(nav.querySelectorAll(".sections__chip"));
  var detail = document.getElementById("fund_xray_header");

  function px(name) { return parseFloat(getComputedStyle(html).getPropertyValue(name)) || 0; }
  function measure() { html.style.setProperty("--nav-h", nav.offsetHeight + "px"); }

  var shown = null;
  function mark() {
    var tops = chips.map(function (chip) {
      var target = document.getElementById(chip.getAttribute("href").slice(1));
      return { id: target ? target.id : "", top: target ? target.getBoundingClientRect().top + window.scrollY : Infinity };
    }).filter(function (t) { return t.id; });
    var bottom = window.scrollY + window.innerHeight >= html.scrollHeight - 2;
    var id = currentSection(tops, window.scrollY, px("--bar-h") + px("--nav-h") + 16, bottom);
    if (id === shown) return;
    shown = id;
    chips.forEach(function (chip) {
      var on = chip.getAttribute("href") === "#" + id;
      if (on) chip.setAttribute("aria-current", "true"); else chip.removeAttribute("aria-current");
      // Only the chip row scrolls, never the page: scrollIntoView would also move
      // the window and fight a smooth scroll already under way.
      var outside = chip.offsetLeft < nav.scrollLeft ||
        chip.offsetLeft + chip.offsetWidth > nav.scrollLeft + nav.clientWidth;
      // Whenever the row overflows, not only on a phone: between 721px and about
      // 1,000px it does too, and its scrollbar is hidden.
      if (on && nav.scrollWidth > nav.clientWidth && outside) {
        nav.scrollTo({
          left: chip.offsetLeft - 12,
          behavior: html.getAttribute("data-motion") === "on" ? "smooth" : "auto",
        });
      }
    });
  }

  var queued = false;
  function soon() {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(function () { queued = false; mark(); });
  }

  // "Every figure" is a closed table: choosing it, or arriving at it, opens it.
  function openDetail() { if (detail) detail.open = true; }
  if (location.hash === "#fund_xray_header") openDetail();
  nav.addEventListener("click", function (event) {
    var chip = event.target.closest(".sections__chip");
    if (chip && chip.getAttribute("href") === "#fund_xray_header") openDetail();
  });

  measure();
  mark();
  window.addEventListener("scroll", soon, { passive: true });
  window.addEventListener("resize", function () { measure(); soon(); });
  // The navigator's height follows the reader's text size and font (V1-83).
  new MutationObserver(function () { measure(); soon(); })
    .observe(html, { attributes: true, attributeFilter: ["data-size", "data-font"] });
})();
