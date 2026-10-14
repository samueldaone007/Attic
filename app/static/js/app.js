/* =====================================================================
   Attic - shell behaviour
   Theme, mobile drawer, search focus, global shortcuts, launch flags.
   Item logic lives in items.js; this file just tells it to open.
   ===================================================================== */
(function () {
  "use strict";

  var root = document.documentElement;
  var STORAGE_KEY = "attic-theme";

  /* ---------------------------- Theme ---------------------------- */
  function systemPrefersLight() {
    return window.matchMedia("(prefers-color-scheme: light)").matches;
  }
  function resolveTheme(pref) {
    return pref === "system" ? (systemPrefersLight() ? "light" : "dark") : pref;
  }
  function applyTheme(pref) {
    root.setAttribute("data-theme", resolveTheme(pref));
    var select = document.getElementById("themeSelect");
    if (select) select.value = pref;
  }
  function storedTheme() {
    try { return localStorage.getItem(STORAGE_KEY) || "system"; } catch (e) { return "system"; }
  }
  function saveTheme(pref) {
    try { localStorage.setItem(STORAGE_KEY, pref); } catch (e) { /* ignore */ }
    applyTheme(pref);
  }

  function initTheme() {
    var pref = storedTheme();
    applyTheme(pref);

    var toggle = document.getElementById("themeToggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        saveTheme(resolveTheme(storedTheme()) === "dark" ? "light" : "dark");
      });
    }

    var select = document.getElementById("themeSelect");
    if (select) {
      select.value = pref;
      select.addEventListener("change", function () { saveTheme(select.value); });
    }

    window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", function () {
      if (storedTheme() === "system") applyTheme("system");
    });
  }

  /* ---------------------- Mobile nav drawer ---------------------- */
  function initDrawer() {
    var menuBtn = document.getElementById("menuBtn");
    var backdrop = document.getElementById("navBackdrop");
    if (!menuBtn) return;

    function setOpen(open) {
      document.body.classList.toggle("nav-open", open);
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
      if (backdrop) backdrop.hidden = !open;
    }

    menuBtn.addEventListener("click", function () {
      setOpen(!document.body.classList.contains("nav-open"));
    });
    if (backdrop) backdrop.addEventListener("click", function () { setOpen(false); });
    // Closing the drawer on Escape is handled by the shared shortcut below.
  }

  /* ------------------------- Search focus ------------------------ */
  function focusSearch() {
    var input = document.getElementById("searchInput");
    if (input) { input.focus(); input.select(); }
  }

  function initSearch() {
    var form = document.getElementById("searchForm");
    if (form) {
      // Live search arrives in Step 3; for now stop the full page reload.
      form.addEventListener("submit", function (e) { e.preventDefault(); });
    }
    document.querySelectorAll('[data-action="focus-search"]').forEach(function (el) {
      el.addEventListener("click", focusSearch);
    });
  }

  /* --------------------------- New item --------------------------- */
  function defaultItemType() {
    var flags = document.getElementById("launchFlags");
    if (flags && flags.getAttribute("data-default-type")) {
      return flags.getAttribute("data-default-type");
    }
    return "note";
  }

  function newItem(type) {
    document.dispatchEvent(new CustomEvent("attic:new", {
      detail: { type: type || defaultItemType() || "note" },
    }));
  }

  function initCaptureTriggers() {
    // Desktop topbar "New", the mobile FAB, and the empty-state button.
    document.querySelectorAll('[data-action="new-item"]').forEach(function (btn) {
      btn.addEventListener("click", function () { newItem(); });
    });
    var emptyBtn = document.getElementById("emptyCreateBtn");
    if (emptyBtn) emptyBtn.addEventListener("click", function () { newItem(); });
  }

  /* -------------------------- Shortcuts -------------------------- */
  function initShortcuts() {
    document.addEventListener("keydown", function (e) {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      var tag = (e.target.tagName || "").toLowerCase();
      var typing = tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable;

      // Never trigger global shortcuts while the user is typing in a field.
      if (typing) return;

      if (e.key === "/") {
        e.preventDefault();
        focusSearch();
      } else if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        newItem();
      } else if (e.key === "?") {
        e.preventDefault();
        var openDialog = document.querySelector("dialog[open]");
        if (!openDialog) openShortcuts();
        else if (openDialog.id === "shortcutsDialog") toggleShortcuts();
      } else if (e.key === "Escape") {
        document.body.classList.remove("nav-open");
        var menuBtn = document.getElementById("menuBtn");
        if (menuBtn) menuBtn.setAttribute("aria-expanded", "false");
        var backdrop = document.getElementById("navBackdrop");
        if (backdrop) backdrop.hidden = true;
      }
    });
  }

  /* ------------------ Keyboard shortcuts guide ------------------- */
  function shortcutsDialog() {
    return document.getElementById("shortcutsDialog");
  }

  function openShortcuts() {
    var d = shortcutsDialog();
    if (d && !d.open) d.showModal();
  }

  function toggleShortcuts() {
    var d = shortcutsDialog();
    if (!d) return;
    if (d.open) d.close(); else d.showModal();
  }

  function initShortcutsGuide() {
    document.querySelectorAll('[data-action="shortcuts"]').forEach(function (el) {
      el.addEventListener("click", openShortcuts);
    });
    document.querySelectorAll("[data-shortcuts-close]").forEach(function (el) {
      el.addEventListener("click", function () {
        var d = shortcutsDialog();
        if (d) d.close();
      });
    });
    var d = shortcutsDialog();
    if (d) {
      // Clicking the backdrop closes the guide, same as other dialogs.
      d.addEventListener("click", function (e) {
        if (e.target === d) d.close();
      });
    }
  }

  /* ------------------------ Launch flags ------------------------- */
  // /?new=note etc. only open UI; they never change data by themselves.
  function initLaunchFlags() {
    var flags = document.getElementById("launchFlags");
    if (!flags) return;
    var launchNew = flags.getAttribute("data-launch-new") || "";
    var launchSearch = flags.getAttribute("data-launch-search") || "";

    if (launchNew) {
      newItem(launchNew);
    } else if (launchSearch) {
      focusSearch();
    } else if (document.getElementById("searchInput")) {
      focusSearch();
    }
  }

  /* --------------------- Quick capture handler ------------------- */
  // "web+attic://new" opens Attic straight into the New-note popup even when
  // it is just running in the background: link to web+attic://new from any
  // app, pin a shortcut with a hotkey, or use the PWA's taskbar shortcut.
  function initQuickCapture() {
    if (!navigator.registerProtocolHandler) return;
    try {
      navigator.registerProtocolHandler(
        "web+attic",
        location.origin + "/?new=note&cmd=%s",
        "Attic quick capture"
      );
    } catch (e) {
      /* registration is a bonus; the manifest entry covers installed apps */
    }
  }

  /* --------------------- Focus existing window ------------------- */
  // When a launch URL (a PWA shortcut, a bookmarked link) opens a second
  // window of Attic, bring the other window with the same view to the front
  // instead of leaving both sitting in the background. Best effort: peers
  // that receive the ping focus themselves.
  function initFocusExisting() {
    if (!("BroadcastChannel" in window)) return;
    var flags = document.getElementById("launchFlags");
    if (!flags) return;
    var isLaunch = flags.getAttribute("data-launch-new") || flags.getAttribute("data-launch-search");
    var key = location.pathname + location.search;
    var channel;
    try {
      channel = new BroadcastChannel("attic-launch");
    } catch (e) {
      return;
    }
    channel.onmessage = function (ev) {
      var data = ev.data || {};
      if (data.type === "launch" && data.url === key) {
        try { window.focus(); } catch (e) { /* ignore */ }
      }
    };
    if (isLaunch) {
      channel.postMessage({ type: "launch", url: key });
    }
    window.addEventListener("pagehide", function () { channel.close(); });
  }

  /* ---------------------------- Boot ----------------------------- */
  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initDrawer();
    initSearch();
    initCaptureTriggers();
    initShortcuts();
    initShortcutsGuide();
    initLaunchFlags();
    initFocusExisting();
    initQuickCapture();
  });
})();