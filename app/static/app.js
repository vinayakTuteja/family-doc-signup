/*
 * Progressive enhancements for the signup form.
 *
 * Without JavaScript the form shows every question on one page and still works.
 * With JavaScript it becomes one question per screen. Written in plain ES5 (no
 * arrow functions, let/const or modern APIs) so it runs on older phones.
 */
(function () {
  "use strict";

  var POSTAL_RE = /^[KLMNP][0-9][ABCEGHJ-NPRSTV-Z] ?[0-9][ABCEGHJ-NPRSTV-Z][0-9]$/;
  var EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  function each(list, fn) { for (var i = 0; i < list.length; i++) fn(list[i], i); }
  function closest(el, cls) {
    while (el && el.nodeType === 1) {
      if (el.classList && el.classList.contains(cls)) return el;
      el = el.parentNode;
    }
    return null;
  }
  function focusQuietly(el) {
    if (!el) return;
    try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
  }

  /* ------------------------------------------------------------ radius slider */
  function setupRadius(root) {
    var range = root.querySelector("#radius_km");
    var output = root.querySelector("#radius-value");
    if (!range || !output) return function () {};
    function update() {
      output.textContent = range.value + " km";
      var pct = ((range.value - range.min) / (range.max - range.min)) * 100;
      if (range.style.setProperty) range.style.setProperty("--fill", pct + "%");
    }
    range.addEventListener("input", update);
    range.addEventListener("change", update);
    update();
    return update;
  }

  /* ------------------------------------------------- checked-state styling */
  // Mirrors the CSS :has() rule for browsers that do not support it.
  function syncChecked(form) {
    each(form.querySelectorAll(".choice"), function (label) {
      var input = label.querySelector("input");
      if (input) label.classList.toggle("is-checked", input.checked);
    });
  }

  /* ------------------------------------------------------------ step form */
  function setupSteps(form, updateRadius) {
    var steps = form.querySelectorAll(".q-step");
    if (!steps.length) return null;

    var nav = form.querySelector(".step-nav");
    var nextBtn = form.querySelector(".step-next");
    var backBtn = form.querySelector(".step-back");
    var sectionEl = form.querySelector(".step-section");
    var countEl = form.querySelector(".step-count");
    var fillEl = form.querySelector(".step-progress-fill");
    var announce = document.getElementById("step-announce");
    var current = 0;
    var autoTimer = null;

    form.classList.add("js-steps");

    function radioValue(name) {
      var checked = form.querySelector('input[name="' + name + '"]:checked');
      return checked ? checked.value : "";
    }

    function isVisible(step) {
      var rule = step.getAttribute("data-show-if");
      if (!rule) return true;
      if (rule === "has_flags") return !!form.querySelector('input[name="need_flags"]:checked');
      var parts = rule.split("=");
      return radioValue(parts[0]) === parts[1];
    }

    // Steps that are skipped get a sensible default (e.g. a single person cannot be split).
    function applyDefaults() {
      each(steps, function (step) {
        var def = step.getAttribute("data-default-hidden");
        if (!def) return;
        var parts = def.split("=");
        var input = form.querySelector('input[name="' + parts[0] + '"][value="' + parts[1] + '"]');
        if (!input) return;
        if (!isVisible(step)) {
          input.checked = true;
          step.setAttribute("data-auto-set", "true");
        } else if (step.getAttribute("data-auto-set") === "true") {
          input.checked = false;
          step.removeAttribute("data-auto-set");
        }
      });
      if (!form.querySelector('input[name="need_flags"]:checked')) {
        var hc = form.querySelector('input[name="health_consent"]');
        if (hc) hc.checked = false;
      }
      syncChecked(form);
    }

    function visibleSteps() {
      var list = [];
      each(steps, function (step, i) { if (isVisible(step)) list.push(i); });
      return list;
    }

    function stepIsEmpty(step) {
      var empty = true;
      each(step.querySelectorAll("input, select"), function (el) {
        if (el.type === "checkbox" || el.type === "radio") { if (el.checked) empty = false; }
        else if (el.type !== "range" && el.value) empty = false;
      });
      return empty;
    }

    /* ---------------- validation (mirrors the server; the server always re-checks) */
    function clearErrors(step) {
      each(step.querySelectorAll(".error.js-error"), function (e) { e.parentNode.removeChild(e); });
      each(step.querySelectorAll(".has-error"), function (e) { e.classList.remove("has-error"); });
    }

    function addError(el, message) {
      var field = closest(el, "field");
      if (!field) return;
      field.classList.add("has-error");
      var p = document.createElement("p");
      p.className = "error js-error";
      p.setAttribute("role", "alert");
      p.textContent = message;
      var anchor = field.querySelector(".hint") || field.querySelector("legend, label, .q-title");
      if (anchor && anchor.parentNode === field) field.insertBefore(p, anchor.nextSibling);
      else field.insertBefore(p, field.firstChild);
    }

    function validate(step) {
      clearErrors(step);
      var ok = true;
      function fail(el, msg) { ok = false; addError(el, msg); }

      var email = step.querySelector("#email");
      if (email && !EMAIL_RE.test(email.value.trim())) fail(email, "Enter a valid email address.");

      var phone = step.querySelector("#phone");
      if (phone && phone.value.trim()) {
        var d = phone.value.replace(/\D/g, "");
        if (d.length === 11 && d.charAt(0) === "1") d = d.slice(1);
        if (d.length !== 10) fail(phone, "Enter a 10-digit phone number, or leave it blank.");
      }

      var postal = step.querySelector("#postal_code");
      if (postal) {
        var v = postal.value.replace(/\s+/g, "").toUpperCase();
        if (v.length === 6) v = v.slice(0, 3) + " " + v.slice(3);
        if (!POSTAL_RE.test(v)) fail(postal, "Enter an Ontario postal code, for example M5V 3L9.");
        else postal.value = v;
      }

      var household = step.querySelector("#household_size");
      if (household && household.value) {
        var n = parseInt(household.value, 10);
        if (!(n >= 1 && n <= 12)) fail(household, "Enter a number from 1 to 12, or leave it blank.");
      }

      if (step.getAttribute("data-optional") !== "true") {
        var names = {};
        each(step.querySelectorAll('input[type="radio"]'), function (r) { names[r.name] = r; });
        for (var name in names) {
          if (names.hasOwnProperty(name) && !radioValue(name)) fail(names[name], "Choose an option to continue.");
        }
      }

      var hc = step.querySelector('input[name="health_consent"]');
      if (hc && !hc.checked) fail(hc, "Tick this box to let us use those answers, or go back and untick them.");

      var sc = step.querySelector('input[name="service_consent"]');
      if (sc && !sc.checked) fail(sc, "We need your consent to use your details for this service.");

      return ok;
    }

    /* ---------------- navigation */
    function render() {
      var visible = visibleSteps();
      var pos = visible.indexOf(current);
      each(steps, function (step, i) {
        var active = i === current;
        step.classList.toggle("is-active", active);
        step.setAttribute("aria-hidden", active ? "false" : "true");
      });
      var step = steps[current];
      var isFinal = step.getAttribute("data-final") === "true";
      form.classList.toggle("is-final", isFinal);

      backBtn.style.visibility = pos > 0 ? "visible" : "hidden";
      nextBtn.style.display = isFinal ? "none" : "";
      if (step.getAttribute("data-optional") === "true" && stepIsEmpty(step)) {
        nextBtn.textContent = step.getAttribute("data-empty-label") || "Skip";
      } else {
        nextBtn.textContent = "Next";
      }

      var label = "Question " + (pos + 1) + " of " + visible.length;
      if (countEl) countEl.textContent = label;
      if (sectionEl) sectionEl.textContent = step.getAttribute("data-section") || "";
      if (fillEl) fillEl.style.width = Math.round(((pos + 1) / visible.length) * 100) + "%";
      if (announce) announce.textContent = label;
    }

    function go(index, focus) {
      current = index;
      render();
      var step = steps[current];
      // Keep the progress bar just under the sticky header so each question starts at the top.
      var header = document.querySelector(".site-header");
      var offset = (header ? header.offsetHeight : 0) + 16;
      var top = form.getBoundingClientRect().top;
      if (Math.abs(top - offset) > 8) {
        window.scrollTo(0, top + (window.pageYOffset || document.documentElement.scrollTop) - offset);
      }
      if (focus) {
        var field = step.querySelector('input[type="email"], input[type="tel"], input[type="number"], input:not([type]), input[type="text"]:not([name="website"])');
        if (field) focusQuietly(field);
        else {
          var title = step.querySelector(".q-title");
          if (title) { title.setAttribute("tabindex", "-1"); focusQuietly(title); }
        }
      }
    }

    function next() {
      clearTimeout(autoTimer);
      if (!validate(steps[current])) return;
      applyDefaults();
      var visible = visibleSteps();
      var pos = visible.indexOf(current);
      if (pos < visible.length - 1) go(visible[pos + 1], true);
    }

    function back() {
      clearTimeout(autoTimer);
      applyDefaults();
      var visible = visibleSteps();
      var pos = visible.indexOf(current);
      if (pos > 0) go(visible[pos - 1], true);
    }

    nextBtn.addEventListener("click", next);
    backBtn.addEventListener("click", back);

    form.addEventListener("change", function (e) {
      syncChecked(form);
      var step = closest(e.target, "q-step");
      if (!step) return;
      clearErrors(step);
      render();
      if (e.target.type === "radio" && step.getAttribute("data-auto") === "true" && step === steps[current]) {
        clearTimeout(autoTimer);
        autoTimer = setTimeout(next, 260);
      }
    });

    form.addEventListener("input", function (e) {
      var step = closest(e.target, "q-step");
      if (step === steps[current]) render();
    });

    form.addEventListener("keydown", function (e) {
      var key = e.key || e.keyCode;
      if ((key === "Enter" || key === 13) && e.target.tagName === "INPUT" && e.target.type !== "checkbox" && e.target.type !== "radio") {
        var step = steps[current];
        if (step.getAttribute("data-final") !== "true") { e.preventDefault(); next(); }
      }
    });

    // Last check before the form is sent; the server validates everything again.
    form.addEventListener("submit", function (e) {
      if (!validate(steps[current])) { e.preventDefault(); if (e.stopImmediatePropagation) e.stopImmediatePropagation(); }
    }, true);

    // After a server-side error, open the first question that needs fixing.
    var start = 0;
    var firstError = form.querySelector(".q-step .has-error");
    if (firstError) {
      each(steps, function (step, i) { if (step.contains(firstError) && !start) start = i; });
    }
    applyDefaults();
    go(start, false);

    return {
      reset: function () {
        each(steps, function (step) { clearErrors(step); step.removeAttribute("data-auto-set"); });
        applyDefaults();
        updateRadius();
        syncChecked(form);
        go(0, false);
      }
    };
  }

  function init() {
    var form = document.querySelector("form.signup");
    if (!form) return;
    var updateRadius = setupRadius(form);
    syncChecked(form);
    window.signupSteps = setupSteps(form, updateRadius);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
