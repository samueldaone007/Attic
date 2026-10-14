/* =====================================================================
   Attic - shared UI helpers
   Loaded on every page before the other scripts.
   ===================================================================== */
window.Attic = window.Attic || {};

(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // SVG icon by name; paths come from the sprite in partials/sprite.html.
  function icon(name, size) {
    var s = size || 18;
    return '<svg class="icon" width="' + s + '" height="' + s +
      '" aria-hidden="true" focusable="false"><use href="#i-' + escapeHtml(name) + '"></use></svg>';
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (key === "class") node.className = attrs[key];
        else if (key === "text") node.textContent = attrs[key];
        else node.setAttribute(key, attrs[key]);
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach(function (child) {
        if (child == null) return;
        node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
      });
    }
    return node;
  }

  function toast(message, action) {
    var elNode = document.getElementById("atticToast");
    if (!elNode) {
      elNode = document.createElement("div");
      elNode.id = "atticToast";
      elNode.className = "toast";
      elNode.setAttribute("role", "status");
      elNode.setAttribute("aria-live", "polite");
      document.body.appendChild(elNode);
    }
    elNode.textContent = message;
    elNode.classList.toggle("has-action", !!action);

    var btn = elNode.querySelector(".toast-action");
    if (btn) btn.remove();
    if (action) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "toast-action";
      btn.textContent = action.label;
      btn.addEventListener("click", function () {
        hideToast(elNode);
        if (action.onClick) action.onClick();
      });
      elNode.appendChild(btn);
    }

    elNode.classList.add("is-visible");
    clearTimeout(elNode._timer);
    elNode._timer = setTimeout(hideToast, action ? 6000 : 2600, elNode);
  }

  function hideToast(elNode) {
    elNode.classList.remove("is-visible");
  }

  // SQLite stores UTC as "2026-10-11 12:00:00". Show it in the owner's zone.
  function formatDateTime(value) {
    if (!value) return "";
    var date = new Date(String(value).replace(" ", "T") + "Z");
    if (isNaN(date.getTime())) return String(value);
    var now = new Date();
    var sameYear = date.getFullYear() === now.getFullYear();
    var opts = sameYear
      ? { month: "short", day: "numeric" }
      : { year: "numeric", month: "short", day: "numeric" };
    return date.toLocaleDateString(undefined, opts) +
      " · " + date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  function debounce(fn, ms) {
    var timer = null;
    return function () {
      var args = arguments;
      var self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  function csrfMeta() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }

  Attic.ui = {
    escapeHtml: escapeHtml,
    icon: icon,
    el: el,
    toast: toast,
    formatDateTime: formatDateTime,
    debounce: debounce,
    csrfMeta: csrfMeta,
  };
})();