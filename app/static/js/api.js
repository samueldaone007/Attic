/* =====================================================================
   Attic - JSON API client
   All requests go to /api/*. State-changing calls carry the CSRF token
   from the page meta tag in the X-CSRF-Token header.
   ===================================================================== */
(function () {
  "use strict";

  var csrf = Attic.ui.csrfMeta;

  async function request(method, url, body) {
    var opts = {
      method: method,
      headers: { "Accept": "application/json" },
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    if (method !== "GET" && method !== "HEAD") {
      opts.headers["X-CSRF-Token"] = csrf();
    }

    var res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      var netErr = new Error("Could not reach the server. Check your connection.");
      netErr.status = 0;
      throw netErr;
    }

    if (!res.ok) {
      var detail = "";
      try { detail = (await res.json()).detail || ""; } catch (e) { /* no json */ }
      var err = new Error(detail || "Request failed (" + res.status + ")");
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    return res.json();
  }

  function query(params) {
    var s = new URLSearchParams();
    Object.keys(params || {}).forEach(function (key) {
      var v = params[key];
      if (v === undefined || v === null || v === "") return;
      s.set(key, v);
    });
    return s.toString();
  }

  Attic.api = {
    listItems: function (params) { return request("GET", "/api/items?" + query(params)); },
    getItem: function (id) { return request("GET", "/api/items/" + encodeURIComponent(id)); },
    relatedItems: function (id) { return request("GET", "/api/items/" + encodeURIComponent(id) + "/related"); },
    createItem: function (data) { return request("POST", "/api/items", data); },
    updateItem: function (id, data) { return request("PUT", "/api/items/" + encodeURIComponent(id), data); },
    updateItemFlags: function (id, data) { return request("PATCH", "/api/items/" + encodeURIComponent(id), data); },
    deleteItem: function (id) { return request("DELETE", "/api/items/" + encodeURIComponent(id)); },
    deleteItemPermanent: function (id) { return request("DELETE", "/api/items/" + encodeURIComponent(id) + "/permanent"); },
    restoreItem: function (id) { return request("POST", "/api/items/" + encodeURIComponent(id) + "/restore"); },
    tags: function () { return request("GET", "/api/tags"); },
    renderMarkdown: function (text) { return request("POST", "/api/markdown", { text: text }); },
  };
})();