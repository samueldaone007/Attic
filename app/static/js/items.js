/* =====================================================================
   Attic - item list, capture box, tags and item view
   Loaded only on the main page (guards on #itemList).
   ===================================================================== */
(function () {
  "use strict";

  var ui = Attic.ui;
  var api = Attic.api;

  var state = {
    type: null,
    tag: null,
    pinned: false,
    archived: false,
    trashed: false,
    sort: "newest",
    q: "",
    editingId: null,
    currentType: "note",
  };

  var refs = null;
  var previewing = false;
  var searchSeq = 0;
  var navIndex = -1;

  function $id(id) { return document.getElementById(id); }

  /* ------------------------- small helpers ------------------------ */
  var TYPE_META = {
    note: { label: "Note", icon: "note" },
    link: { label: "Link", icon: "link" },
    snippet: { label: "Snippet", icon: "snippet" },
  };
  function typeMeta(type) { return TYPE_META[type] || TYPE_META.note; }

  function defaultTitle(it) {
    if (it.type === "link") return it.url || "Untitled link";
    if (it.type === "snippet") return "Untitled snippet";
    return "Untitled note";
  }

  function domainOf(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return url; }
  }

  function parseTags(value) {
    return String(value || "")
      .split(/[,\n]/)
      .map(function (s) { return s.trim(); })
      .filter(Boolean);
  }

  function apiMessage(err) {
    if (err.status === 401) return "Your session expired. Please log in again.";
    if (err.status === 403) return "Session expired. Reload the page and try again.";
    return err.message || "Something went wrong.";
  }

  function closeDialog(dialog) {
    if (dialog && dialog.open) dialog.close();
  }

  function clearSearch() {
    state.q = "";
    if (refs && refs.search) refs.search.value = "";
  }

  /* ---------------------------- filters --------------------------- */
  function currentView() {
    if (state.trashed) return "trash";
    if (state.archived) return "archive";
    if (state.pinned) return "pinned";
    if (state.type) return state.type;
    return "all";
  }

  function setNavActive() {
    var view = currentView();
    document.querySelectorAll(".side-link[data-view]").forEach(function (link) {
      link.classList.toggle("is-active", link.getAttribute("data-view") === view);
    });
    document.querySelectorAll("#tagList .tag-chip").forEach(function (chip) {
      chip.classList.toggle("is-active", chip.getAttribute("data-tag") === state.tag);
    });
  }

  function applyView(view) {
    var base = { tag: null, pinned: false, archived: false, trashed: false };
    if (view === "all") {
      Object.assign(state, base, { type: null });
    } else if (view === "note" || view === "link" || view === "snippet") {
      Object.assign(state, base, { type: view });
    } else if (view === "pinned") {
      Object.assign(state, base, { type: null, pinned: true });
    } else if (view === "archive") {
      Object.assign(state, base, { type: null, archived: true });
    } else if (view === "trash") {
      Object.assign(state, base, { type: null, trashed: true });
    } else {
      return;
    }
    clearSearch();
    loadList();
    setNavActive();
  }

  function setTagFilter(name) {
    Object.assign(state, { tag: name, type: null, pinned: false, archived: false, trashed: false });
    clearSearch();
    loadList(true);
    setNavActive();
  }

  function toggleTagFilter(name) {
    if (state.tag === name) state.tag = null;
    else Object.assign(state, { tag: name, type: null, pinned: false, archived: false, trashed: false });
    clearSearch();
    loadList(true);
    setNavActive();
  }

  function resetFilters() {
    Object.assign(state, { type: null, tag: null, pinned: false, archived: false, trashed: false });
    clearSearch();
    loadList(true);
    setNavActive();
  }

  function newItemFor(type) {
    document.dispatchEvent(new CustomEvent("attic:new", { detail: { type: type || "note" } }));
  }

  /* ------------------------------ list ---------------------------- */
  function loadList(refreshTags) {
    searchSeq += 1;
    var mySeq = searchSeq;
    return api.listItems({
      type: state.type,
      tag: state.tag,
      pinned: state.pinned ? 1 : 0,
      archived: state.archived ? 1 : 0,
      deleted: state.trashed ? 1 : 0,
      sort: state.sort,
      q: state.q,
    }).then(function (data) {
      if (mySeq !== searchSeq) return;
      renderList(data.items);
      if (refreshTags) updateSidebarTags();
    }).catch(function (err) {
      if (mySeq !== searchSeq) return;
      ui.toast(apiMessage(err));
    });
  }

  function renderList(items) {
    refs.list.innerHTML = "";
    navIndex = -1;
    refreshHighlight();
    var hasFilters = !!(state.type || state.tag || state.pinned || state.archived || state.trashed || state.q);
    refs.toolbar.hidden = items.length === 0;
    if (refs.sortWrap) refs.sortWrap.hidden = state.trashed;
    var countText = items.length + (items.length === 1 ? " item" : " items");
    if (state.q) countText += ' for "' + state.q + '"';
    refs.count.textContent = countText;
    if (refs.searchStatus) refs.searchStatus.textContent = state.q ? countText : "";
    items.forEach(function (item) { refs.list.appendChild(card(item)); });
    refs.empty.hidden = items.length !== 0 || hasFilters;
    refs.searchEmpty.hidden = items.length !== 0 || !hasFilters;
    if (items.length === 0 && hasFilters) updateEmptyCopy();
  }

  function updateEmptyCopy() {
    var title = "Nothing in the attic matches that.";
    var text = "Try fewer letters, or clear the filters.";
    var action = "Clear filters";
    var create = "";

    if (state.q) {
      text = 'Nothing matches "' + state.q + '". Try fewer letters, or clear the filters.';
    } else if (state.type === "note") {
      title = "No notes yet.";
      text = "Add a few quick Markdown lines to get going.";
      action = "Add your first note";
      create = "note";
    } else if (state.type === "link") {
      title = "No links yet.";
      text = "Save a URL and its real page title comes along automatically.";
      action = "Save your first link";
      create = "link";
    } else if (state.type === "snippet") {
      title = "No snippets yet.";
      text = "Paste a command or a code block to keep it close.";
      action = "Add your first snippet";
      create = "snippet";
    } else if (state.tag) {
      title = 'Nothing tagged "' + state.tag + '".';
      text = "Try another tag, or clear the filter.";
    } else if (state.archived) {
      title = "The archive is empty.";
      text = "Items you archive will live here.";
    } else if (state.trashed) {
      title = "Trash is empty.";
      text = "Items you delete wait here until they're removed for good.";
    } else if (state.pinned) {
      title = "Nothing pinned yet.";
      text = "Pin an item to keep it near the top of the list.";
    }

    refs.searchEmptyTitle.textContent = title;
    refs.searchEmptyText.textContent = text;
    refs.searchEmptyActionLabel.textContent = action;
    refs.clearFilters.classList.toggle("btn-primary", !!create);
    refs.clearFilters.classList.toggle("btn-ghost", !create);
    refs.clearFilters.dataset.create = create;
  }

  /* --------------- match highlighting (live search) --------------- */
  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function queryTokens() {
    var tokens = (state.q || "").toLowerCase().match(/\w+/g) || [];
    return tokens.map(function (t) { return t.replace(/^_+|_+$/g, ""); }).filter(Boolean).slice(0, 12);
  }

  var highlightRe = null;
  function refreshHighlight() {
    var tokens = queryTokens();
    highlightRe = tokens.length
      ? new RegExp("([^\\w]|^)(" + tokens.map(escapeRegExp).join("|") + ")", "gi")
      : null;
  }

  function highlightHTML(text) {
    var escaped = ui.escapeHtml(text);
    if (!highlightRe) return escaped;
    return escaped.replace(highlightRe, "$1<mark>$2</mark>");
  }

  function card(item) {
    if (state.trashed) {
      var li = document.createElement("li");
      li.className = "item-card-li";
      li.dataset.id = item.id;
      var div = document.createElement("div");
      div.className = "item-card item-card-trash";
      div.innerHTML = trashCardHTML(item);
      div.querySelector('[data-action="restore"]').addEventListener("click", function () { restoreTrashItem(item.id); });
      div.querySelector('[data-action="delete-forever"]').addEventListener("click", function () { deleteForever(item.id); });
      li.appendChild(div);
      return li;
    }

    var li = document.createElement("li");
    li.className = "item-card-li";
    li.dataset.id = item.id;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "item-card";
    btn.dataset.id = item.id;
    btn.setAttribute("aria-label", "Open " + typeMeta(item.type).label.toLowerCase() + ": " + (item.title || "untitled"));
    btn.innerHTML = cardHTML(item);
    btn.addEventListener("click", function () { openItem(item.id); });
    li.appendChild(btn);
    return li;
  }

  function trashCardHTML(it) {
    var t = typeMeta(it.type);
    var when = it.deleted_at || it.updated_at;
    return (
      '<div class="item-card-top">' +
        '<span class="badge badge-' + it.type + '">' + ui.icon(t.icon, 13) + t.label + "</span>" +
        '<span class="badge badge-trash">' + ui.icon("trash", 13) + "Trashed</span>" +
        '<time class="item-date">' + ui.escapeHtml(ui.formatDateTime(when)) + "</time>" +
      "</div>" +
      '<h3 class="item-title">' + ui.escapeHtml(it.title || defaultTitle(it)) + "</h3>" +
      (it.preview ? '<p class="item-preview">' + highlightHTML(it.preview) + "</p>" : "") +
      '<div class="item-card-actions">' +
        '<button type="button" class="btn btn-ghost btn-sm" data-action="restore">' +
          ui.icon("restore", 14) + "Restore</button>" +
        '<button type="button" class="btn btn-ghost btn-danger-ghost btn-sm" data-action="delete-forever">' +
          ui.icon("trash", 14) + "Delete forever</button>" +
      "</div>"
    );
  }

  function cardHTML(it) {
    var t = typeMeta(it.type);
    var top =
      '<div class="item-card-top">' +
        '<span class="badge badge-' + it.type + '">' + ui.icon(t.icon, 13) + t.label + "</span>" +
        (it.pinned ? '<span class="badge badge-pinned">' + ui.icon("pin", 13) + "Pinned</span>" : "") +
        '<time class="item-date">' + ui.escapeHtml(ui.formatDateTime(it.updated_at)) + "</time>" +
      "</div>";
    var domain = it.url ? '<div class="item-domain">' + ui.escapeHtml(domainOf(it.url)) + "</div>" : "";
    var preview = it.preview ? '<p class="item-preview">' + highlightHTML(it.preview) + "</p>" : "";
    var tags = it.tags.length
      ? '<div class="item-tags">' + it.tags.map(function (n) {
          return '<span class="tag-chip">#' + ui.escapeHtml(n) + "</span>";
        }).join("") + "</div>"
      : "";
    return top + domain +
      '<h3 class="item-title">' + highlightHTML(it.title || defaultTitle(it)) + "</h3>" +
      preview + tags;
  }

  /* --------------------------- sidebar tags ----------------------- */
  function updateSidebarTags() {
    api.tags().then(function (res) {
      refs.tagList.innerHTML = "";
      if (!res.tags.length) {
        var empty = document.createElement("li");
        empty.className = "side-muted";
        empty.textContent = "No tags yet";
        refs.tagList.appendChild(empty);
        return;
      }
      res.tags.forEach(function (t) {
        var li = document.createElement("li");
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "tag-chip" + (state.tag === t.name ? " is-active" : "");
        chip.setAttribute("data-tag", t.name);
        chip.textContent = "#" + t.name;
        var count = document.createElement("span");
        count.className = "tag-count";
        count.textContent = t.count;
        chip.appendChild(count);
        chip.addEventListener("click", function () { toggleTagFilter(t.name); });
        li.appendChild(chip);
        refs.tagList.appendChild(li);
      });
    }).catch(function () { /* non-fatal */ });
  }

  /* ---------------------------- item view ------------------------- */
  function openItem(id) {
    Promise.all([api.getItem(id), api.relatedItems(id)]).then(function (results) {
      var item = results[0];
      var related = (results[1] && results[1].items) || [];
      refs.itemDetail.innerHTML = detailHTML(item, related);
      bindDetail(item);
      if (!refs.itemDialog.open) refs.itemDialog.showModal();
    }).catch(function (err) {
      ui.toast(apiMessage(err));
    });
  }

  function detailHTML(it, related) {
    var t = typeMeta(it.type);
    var urlBlock = it.url
      ? '<a class="item-detail-url" href="' + ui.escapeHtml(it.url) + '" target="_blank" rel="noopener noreferrer">' +
        ui.icon("external", 15) + ui.escapeHtml(it.url) + "</a>"
      : "";
    var tags = it.tags.length
      ? '<div class="item-detail-tags">' + it.tags.map(function (n) {
          return '<button type="button" class="tag-chip" data-action="tag" data-tag="' + ui.escapeHtml(n) + '">#' + ui.escapeHtml(n) + "</button>";
        }).join("") + "</div>"
      : "";
    var states = [];
    if (it.pinned) states.push("Pinned");
    if (it.archived) states.push("Archived");
    var meta =
      '<p class="item-detail-meta">Last edited ' + ui.escapeHtml(ui.formatDateTime(it.updated_at)) +
      (states.length ? " · " + states.join(" · ") : "") + "</p>";
    var copyAction = it.type === "snippet"
      ? '<button type="button" class="icon-btn" data-action="copy" aria-label="Copy snippet" title="Copy">' + ui.icon("copy", 20) + "</button>"
      : "";
    var pinAction =
      '<button type="button" class="icon-btn' + (it.pinned ? " is-active" : "") + '" data-action="pin" ' +
      'aria-label="' + (it.pinned ? "Unpin item" : "Pin item") + '" title="' + (it.pinned ? "Unpin" : "Pin to top") + '">' +
      ui.icon("pin", 20) + "</button>";
    var archiveAction =
      '<button type="button" class="icon-btn' + (it.archived ? " is-active" : "") + '" data-action="archive" ' +
      'aria-label="' + (it.archived ? "Unarchive item" : "Archive item") + '" title="' + (it.archived ? "Unarchive" : "Archive") + '">' +
      ui.icon("archive", 20) + "</button>";
    var relatedBlock = related.length
      ? '<div class="related"><h3 class="related-title">Related</h3><ul class="related-list">' +
        related.map(function (r) {
          var tr = typeMeta(r.type);
          return '<li><button type="button" class="related-item" data-action="related" data-id="' + r.id + '">' +
            '<span class="badge badge-' + r.type + '">' + ui.icon(tr.icon, 12) + tr.label + "</span>" +
            '<span class="related-item-title">' + ui.escapeHtml(r.title || defaultTitle(r)) + "</span>" +
            "</button></li>";
        }).join("") + "</ul></div>"
      : "";

    return (
      '<div class="item-detail-head">' +
        '<span class="badge badge-' + it.type + '">' + ui.icon(t.icon, 14) + t.label + "</span>" +
        '<div class="item-detail-actions">' +
          pinAction +
          archiveAction +
          copyAction +
          '<button type="button" class="icon-btn" data-action="edit" aria-label="Edit item" title="Edit">' + ui.icon("edit", 20) + "</button>" +
          '<button type="button" class="icon-btn" data-dialog-close aria-label="Close" title="Close (Esc)">' + ui.icon("close", 22) + "</button>" +
        "</div>" +
      "</div>" +
      urlBlock +
      '<h2 class="item-detail-title">' + ui.escapeHtml(it.title || defaultTitle(it)) + "</h2>" +
      meta +
      tags +
      (it.body_html ? '<div class="markdown-body">' + it.body_html + "</div>" : '<p class="item-preview">No body yet.</p>') +
      relatedBlock
    );
  }

  function copyText(text) {
    function legacyCopy() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); ui.toast("Copied to clipboard."); }
      catch (e) { ui.toast("Clipboard unavailable — select the code manually."); }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () {
        ui.toast("Copied to clipboard.");
      }, legacyCopy);
    } else {
      legacyCopy();
    }
  }

  function bindDetail(item) {
    var editBtn = refs.itemDetail.querySelector('[data-action="edit"]');
    if (editBtn) {
      editBtn.addEventListener("click", function () {
        closeDialog(refs.itemDialog);
        openCapture(item.type, item);
      });
    }
    var copyBtn = refs.itemDetail.querySelector('[data-action="copy"]');
    if (copyBtn) {
      copyBtn.addEventListener("click", function () { copyText(item.body || ""); });
    }

    var pinBtn = refs.itemDetail.querySelector('[data-action="pin"]');
    if (pinBtn) {
      pinBtn.addEventListener("click", function () {
        updateItemFlag(item, "pinned", item.pinned ? "Unpinned." : "Pinned to top.");
      });
    }
    var archiveBtn = refs.itemDetail.querySelector('[data-action="archive"]');
    if (archiveBtn) {
      archiveBtn.addEventListener("click", function () {
        updateItemFlag(item, "archived", item.archived ? "Unarchived." : "Archived.");
      });
    }

    refs.itemDetail.querySelectorAll('[data-action="tag"]').forEach(function (chip) {
      chip.addEventListener("click", function () {
        closeDialog(refs.itemDialog);
        setTagFilter(chip.getAttribute("data-tag"));
      });
    });
    refs.itemDetail.querySelectorAll('[data-action="related"]').forEach(function (btn) {
      btn.addEventListener("click", function () {
        closeDialog(refs.itemDialog);
        openItem(parseInt(btn.getAttribute("data-id"), 10));
      });
    });
    refs.itemDetail.querySelectorAll("[data-dialog-close]").forEach(function (btn) {
      btn.addEventListener("click", function () { closeDialog(refs.itemDialog); });
    });
  }

  function updateItemFlag(item, key, message) {
    var next = {};
    next[key] = !item[key];
    api.updateItemFlags(item.id, next).then(function () {
      ui.toast(message);
      loadList();
      openItem(item.id);
    }).catch(function (err) {
      ui.toast(apiMessage(err));
    });
  }

  /* ---------------------------- capture --------------------------- */
  function openCapture(type, item) {
    var isEdit = !!item;
    state.editingId = isEdit ? item.id : null;
    state.currentType = (item && item.type) || type || "note";
    switchType(state.currentType);
    hidePreview();

    refs.captureId.value = isEdit ? item.id : "";
    refs.captureTitle.value = item ? (item.title || "") : "";
    refs.captureUrl.value = item ? (item.url || "") : "";
    refs.captureLanguage.value = item ? (item.language || "") : "";
    refs.captureBody.value = item ? (item.body || "") : "";
    refs.captureTags.value = item ? (item.tags || []).join(", ") : "";
    refs.captureDelete.hidden = !isEdit;

    if (!refs.captureDialog.open) refs.captureDialog.showModal();
    var first = state.currentType === "link" && !refs.captureUrl.value ? refs.captureUrl : refs.captureTitle;
    first.focus();
  }

  function switchType(type) {
    state.currentType = type;
    refs.tabs.forEach(function (tab) {
      var active = tab.getAttribute("data-type") === type;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    refs.linkUrlRow.hidden = type !== "link";
    refs.snippetLangRow.hidden = type !== "snippet";
    refs.previewToggle.hidden = type === "snippet";
    if (type === "note") refs.captureBody.placeholder = "Write in Markdown… (Ctrl/Cmd + Enter to save)";
    else if (type === "link") refs.captureBody.placeholder = "Notes about this link (Markdown)…";
    else refs.captureBody.placeholder = "Paste your code or command…";
    hidePreview();
  }

  function submitCapture(e) {
    if (e) e.preventDefault();
    var type = state.currentType;
    var title = refs.captureTitle.value.trim();
    var body = refs.captureBody.value;
    var url = refs.captureUrl.value.trim() || null;
    var language = refs.captureLanguage.value.trim() || null;
    var tags = parseTags(refs.captureTags.value);

    if (type === "link" && !url) {
      ui.toast("A link needs a URL.");
      refs.captureUrl.focus();
      return;
    }

    var payload = { type: type, title: title, body: body, url: url, language: language, tags: tags };
    var saveBtn = refs.captureSave;
    saveBtn.disabled = true;

    var promise = state.editingId
      ? api.updateItem(state.editingId, payload)
      : api.createItem(payload);

    promise.then(function () {
      closeDialog(refs.captureDialog);
      ui.toast(state.editingId ? "Item updated." : "Saved to the attic.");
      loadList(true);
    }).catch(function (err) {
      if (err.status === 403) location.reload();
      else ui.toast(apiMessage(err));
    }).finally(function () {
      saveBtn.disabled = false;
    });
  }

  function deleteCapture() {
    var id = state.editingId;
    if (!id) return;
    if (!window.confirm("Move to trash? You can undo this, or delete it forever from the Trash view.")) return;
    api.deleteItem(id).then(function () {
      closeDialog(refs.captureDialog);
      closeDialog(refs.itemDialog);
      ui.toast("Moved to trash.", {
        label: "Undo",
        onClick: function () {
          api.restoreItem(id).then(function () {
            ui.toast("Restored.");
            loadList(true);
          }).catch(function () { ui.toast("Couldn't restore that item."); });
        },
      });
      loadList(true);
    }).catch(function (err) {
      ui.toast(apiMessage(err));
    });
  }

  function restoreTrashItem(id) {
    api.restoreItem(id).then(function () {
      ui.toast("Restored.");
      loadList(true);
    }).catch(function (err) {
      ui.toast(apiMessage(err));
    });
  }

  function deleteForever(id) {
    if (!window.confirm("Delete forever? This cannot be undone.")) return;
    api.deleteItemPermanent(id).then(function () {
      ui.toast("Deleted forever.");
      loadList(true);
    }).catch(function (err) {
      ui.toast(apiMessage(err));
    });
  }

  /* --------------------------- live preview ----------------------- */
  function hidePreview() {
    previewing = false;
    refs.previewToggleLabel.textContent = "Preview";
    refs.capturePreview.hidden = true;
    refs.capturePreview.innerHTML = "";
  }

  function togglePreview() {
    if (previewing) { hidePreview(); return; }
    previewing = true;
    refs.previewToggleLabel.textContent = "Edit";
    refs.capturePreview.hidden = false;
    refs.capturePreview.innerHTML = '<p class="side-muted">Rendering…</p>';
    api.renderMarkdown(refs.captureBody.value).then(function (res) {
      refs.capturePreview.innerHTML = res.html; // sanitized server-side
    }).catch(function (err) {
      refs.capturePreview.innerHTML = '<p class="alert alert-error" role="alert">' + ui.escapeHtml(err.message) + "</p>";
    });
  }

  /* -------------------------- tag suggestions ---------------------- */
  function initTagSuggest() {
    var input = refs.captureTags;
    var debounced = ui.debounce(function () {
      var parts = input.value.split(/[,\n]/);
      var token = (parts[parts.length - 1] || "").trim().toLowerCase();
      if (!token) { refs.tagSuggest.hidden = true; refs.tagSuggest.innerHTML = ""; return; }
      api.tags().then(function (res) {
        var used = input.value.toLowerCase();
        var matches = res.tags
          .filter(function (t) { return t.name.indexOf(token) === 0 && used.indexOf(t.name) === -1; })
          .slice(0, 6);
        refs.tagSuggest.innerHTML = "";
        if (!matches.length) { refs.tagSuggest.hidden = true; return; }
        matches.forEach(function (t) {
          var chip = document.createElement("button");
          chip.type = "button";
          chip.className = "suggest-chip";
          chip.textContent = t.name;
          chip.addEventListener("click", function () {
            var trailing = input.value.replace(/([,\n]*)\s*$/, "");
            input.value = trailing + (trailing ? "," : "") + " " + t.name + ", ";
            refs.tagSuggest.hidden = true;
            input.focus();
          });
          refs.tagSuggest.appendChild(chip);
        });
        refs.tagSuggest.hidden = false;
      }).catch(function () { refs.tagSuggest.hidden = true; });
    }, 150);

    input.addEventListener("input", debounced);
    input.addEventListener("blur", function () {
      setTimeout(function () { refs.tagSuggest.hidden = true; }, 200);
    });
    input.addEventListener("keydown", function (e) { if (e.key === "Escape") refs.tagSuggest.hidden = true; });
  }

  /* ------------------------- keyboard navigation ------------------ */
  function isTypingTarget(el) {
    return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" ||
      el.tagName === "SELECT" || el.isContentEditable);
  }

  function currentCards() {
    return Array.prototype.slice.call(refs.list.querySelectorAll(".item-card"));
  }

  function selectIndex(idx, cards) {
    cards.forEach(function (c, i) {
      var sel = i === idx;
      c.classList.toggle("is-selected", sel);
      if (sel) {
        c.setAttribute("aria-current", "true");
        c.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else {
        c.removeAttribute("aria-current");
      }
    });
  }

  function clearListSelection() {
    navIndex = -1;
    refs.list.querySelectorAll(".item-card.is-selected").forEach(function (c) {
      c.classList.remove("is-selected");
      c.removeAttribute("aria-current");
    });
  }

  function moveSelection(step) {
    var cards = currentCards();
    if (!cards.length) return;
    var idx = navIndex < 0 ? (step > 0 ? -1 : 0) : navIndex + step;
    idx = ((idx % cards.length) + cards.length) % cards.length;
    navIndex = idx;
    selectIndex(idx, cards);
  }

  function jumpSelection(position) {
    var cards = currentCards();
    if (!cards.length) return;
    navIndex = position === "home" ? 0 : cards.length - 1;
    selectIndex(navIndex, cards);
  }

  function openSelected() {
    if (navIndex < 0 || state.trashed) return;
    var cards = currentCards();
    if (!cards[navIndex]) return;
    openItem(parseInt(cards[navIndex].dataset.id, 10) || cards[navIndex].dataset.id);
  }

  function initListNavigation() {
    document.addEventListener("keydown", function (e) {
      if (refs.captureDialog.open || refs.itemDialog.open) {
        if (e.key === "Escape") clearListSelection();
        return;
      }
      if (isTypingTarget(document.activeElement)) return;
      if (e.key === "ArrowDown") { e.preventDefault(); moveSelection(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); moveSelection(-1); }
      else if (e.key === "Home") { e.preventDefault(); jumpSelection("home"); }
      else if (e.key === "End") { e.preventDefault(); jumpSelection("end"); }
      else if (e.key === "Enter" && navIndex >= 0) { e.preventDefault(); openSelected(); }
      else if (e.key === "Escape") clearListSelection();
    });
  }

  /* ---------------------------- boot ------------------------------- */
  function init() {
    refs = {
      list: $id("itemList"),
      toolbar: $id("listToolbar"),
      sortWrap: $id("sortWrap"),
      count: $id("resultCount"),
      sort: $id("sortSelect"),
      empty: $id("emptyState"),
      searchEmpty: $id("searchEmpty"),
      searchEmptyTitle: $id("searchEmptyTitle"),
      searchEmptyText: $id("searchEmptyText"),
      searchEmptyActionLabel: $id("searchEmptyActionLabel"),
      clearFilters: $id("clearFiltersBtn"),
      tagList: $id("tagList"),
      search: $id("searchInput"),
      searchStatus: $id("searchStatus"),

      captureDialog: $id("captureDialog"),
      captureForm: $id("captureForm"),
      captureId: $id("captureId"),
      captureTitle: $id("captureTitle"),
      captureUrl: $id("captureUrl"),
      captureBody: $id("captureBody"),
      captureTags: $id("captureTags"),
      captureLanguage: $id("captureLanguage"),
      tagSuggest: $id("tagSuggest"),
      captureDelete: $id("captureDelete"),
      captureSave: $id("captureSave"),
      linkUrlRow: $id("linkUrlRow"),
      snippetLangRow: $id("snippetLangRow"),
      tabs: $id("captureDialog").querySelectorAll(".type-tab"),
      previewToggle: $id("previewToggle"),
      previewToggleLabel: $id("previewToggleLabel"),
      capturePreview: $id("capturePreview"),

      itemDialog: $id("itemDialog"),
      itemDetail: $id("itemDetail"),
    };

    refs.sort.addEventListener("change", function () {
      state.sort = refs.sort.value;
      loadList();
    });

    var runSearch = ui.debounce(function () {
      state.q = refs.search.value.trim();
      loadList();
    }, 150);
    refs.search.addEventListener("input", runSearch);
    refs.search.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        state.q = refs.search.value.trim();
        loadList();
      }
    });

    refs.clearFilters.addEventListener("click", function () {
      var create = refs.clearFilters.dataset.create;
      if (create) { newItemFor(create); return; }
      resetFilters();
    });

    refs.tabs.forEach(function (tab) {
      tab.addEventListener("click", function () { switchType(tab.getAttribute("data-type")); });
    });

    refs.captureForm.addEventListener("submit", submitCapture);
    refs.captureBody.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submitCapture(e);
    });
    refs.previewToggle.addEventListener("click", togglePreview);
    refs.captureDelete.addEventListener("click", deleteCapture);

    initTagSuggest();

    document.querySelectorAll("[data-dialog-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        closeDialog(btn.closest("dialog"));
      });
    });
    [refs.captureDialog, refs.itemDialog].forEach(function (dialog) {
      dialog.addEventListener("click", function (e) {
        if (e.target === dialog) closeDialog(dialog);
      });
    });

    document.querySelectorAll(".side-link[data-view]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        applyView(link.getAttribute("data-view"));
      });
    });

    initListNavigation();

    document.addEventListener("attic:new", function (e) {
      var type = (e.detail && e.detail.type) || "note";
      if (refs.captureDialog.open) return; // already capturing; don't wipe text
      openCapture(type);
    });

    state.currentType = "note";
    switchType("note");
    loadList(true);
    setNavActive();
  }

  if (document.getElementById("itemList")) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})();