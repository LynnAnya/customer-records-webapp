// Loaded in <head> without defer, so the theme and sidebar state are applied
// before the page is painted (no flash).
//
// Theme ("light" | "dark" | "system"):
//   Logged-in pages: saved on the person's account. The server writes it into
//   <html data-theme>, so it follows the person, not the browser.
//   Public pages (login, QR form): no account, so the browser keeps a copy in
//   localStorage "theme" (the last theme used on this device).
// Sidebar: localStorage "sidebar" = "collapsed" | "open" (this device only).
(function () {
  var root = document.documentElement;
  var darkMedia = window.matchMedia("(prefers-color-scheme: dark)");
  var desktopMedia = window.matchMedia("(min-width: 1024px)");

  function validTheme(value) {
    return value === "light" || value === "dark" ? value : "system";
  }

  function storedTheme() {
    var account = root.dataset.theme;
    if (account) {
      localStorage.setItem("theme", validTheme(account)); // copy for public pages
      return validTheme(account);
    }
    return validTheme(localStorage.getItem("theme"));
  }

  // Save a new choice on the account (logged-in pages only). The CSRF token is
  // taken from the logout form, which every logged-in page has.
  function saveTheme(value) {
    var url = root.dataset.themeUrl;
    var token = document.querySelector("[name=csrfmiddlewaretoken]");
    if (!url || !token) return;
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": token.value },
      body: new URLSearchParams({ theme: value }),
    }).catch(function () {});
  }

  function applyTheme() {
    var choice = storedTheme();
    var dark = choice === "dark" || (choice === "system" && darkMedia.matches);
    root.classList.toggle("dark", dark);
  }

  function applySidebar(collapsed) {
    root.classList.toggle("rail-collapsed", collapsed);
  }

  // Tables: try even column spacing (the same extra width for every column);
  // keep it only if the table still fits, otherwise use the normal layout,
  // which wraps long text. Runs on load, resize, sidebar changes and HTMX swaps.
  function evenColumns() {
    document.querySelectorAll(".data-table").forEach(function (table) {
      var box = table.parentElement;
      table.classList.add("even-cols");
      if (!box.clientWidth || table.scrollWidth > box.clientWidth + 1) {
        table.classList.remove("even-cols");
      }
    });
  }
  var evenTimer;
  function evenColumnsSoon(delay) {
    clearTimeout(evenTimer);
    evenTimer = setTimeout(evenColumns, delay);
  }
  document.addEventListener("DOMContentLoaded", evenColumns);
  document.addEventListener("htmx:afterSwap", evenColumns);
  window.addEventListener("resize", function () { evenColumnsSoon(100); });

  applyTheme();
  applySidebar(localStorage.getItem("sidebar") === "collapsed");
  darkMedia.addEventListener("change", applyTheme);

  // State for the app frame (Alpine): <body x-data="appShell()">
  window.appShell = function () {
    return {
      drawer: false, // mobile: is the floating menu open
      collapsed: localStorage.getItem("sidebar") === "collapsed",
      settingsOpen: false,
      themeOpen: false,
      theme: storedTheme(),

      // Hamburger: collapse/expand on desktop, open/close the drawer on mobile.
      toggleMenu: function () {
        if (desktopMedia.matches) {
          this.setCollapsed(!this.collapsed);
        } else {
          this.drawer = !this.drawer;
        }
      },
      setCollapsed: function (value) {
        this.collapsed = value;
        localStorage.setItem("sidebar", value ? "collapsed" : "open");
        applySidebar(value);
        evenColumnsSoon(320); // after the sidebar has finished resizing
        if (value) {
          this.settingsOpen = false;
          this.themeOpen = false;
        }
      },
      toggleSettings: function () {
        // The sub-menu needs room, so expand a collapsed sidebar first.
        if (desktopMedia.matches && this.collapsed) {
          this.setCollapsed(false);
          this.settingsOpen = true;
          return;
        }
        this.settingsOpen = !this.settingsOpen;
        if (!this.settingsOpen) this.themeOpen = false;
      },
      // Mobile "ตั้งค่า" tab: open the drawer with the theme choices showing.
      openSettingsDrawer: function () {
        this.drawer = true;
        this.settingsOpen = true;
        this.themeOpen = true;
      },
      setTheme: function (value) {
        this.theme = value;
        root.dataset.theme = value;
        localStorage.setItem("theme", value);
        applyTheme();
        saveTheme(value);
      },
    };
  };

  // Ticked customers on the customers page (Alpine): x-data="customerSelection()"
  // The ordered list of IDs lives here, outside the part HTMX swaps, and is kept
  // for this browser tab only (sessionStorage).
  // Select every character of a text box (iPhones need setSelectionRange).
  function selectAll(box) {
    box.focus();
    box.select();
    box.setSelectionRange(0, box.value.length);
  }

  // The older copy command: works in almost every browser and on plain http://,
  // but only close to a tap. Uses the given box, or a hidden one that is removed
  // straight away so no account number stays in the page. Returns true on success.
  function legacyCopy(text, box) {
    var temporary = !box;
    if (temporary) {
      box = document.createElement("textarea");
      box.value = text;
      box.setAttribute("readonly", "");
      box.style.position = "fixed";
      box.style.top = "0";
      box.style.opacity = "0";
      document.body.appendChild(box);
    }
    var copied = false;
    try {
      selectAll(box);
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    if (temporary) box.remove();
    window.getSelection().removeAllRanges();
    return copied;
  }

  window.customerSelection = function () {
    function load(key) {
      try {
        var value = JSON.parse(sessionStorage.getItem(key) || "[]");
        return Array.isArray(value) ? value : [];
      } catch (error) {
        return [];
      }
    }
    return {
      ids: load("selected"),
      // Phone cards the user opened. Kept here, outside the swapped table,
      // so the 10-second refresh, search and paging do not close them.
      openCards: load("openCards"),
      filtersOpen: false,
      activeFilters: 0,
      // Copy / Share
      busy: false,
      notice: "",
      sheetOpen: false,
      sheetText: "",
      // Share is offered on touch devices that support the system share sheet.
      canShare: !!navigator.share && window.matchMedia("(pointer: coarse)").matches,

      // Filters (search and sort are not filters). Counted live in the browser,
      // because the filter button sits outside the part HTMX swaps.
      filterNames: ["name", "plate", "bank", "source", "referral", "from", "to", "hidden"],
      countFilters: function (form) {
        return this.filterNames.filter(function (name) {
          return form.elements[name] && form.elements[name].value;
        }).length;
      },
      resetFilters: function (form) {
        this.filterNames.forEach(function (name) {
          if (form.elements[name]) form.elements[name].value = "";
        });
        // One change event: HTMX reloads the table, Alpine recounts.
        form.dispatchEvent(new Event("change", { bubbles: true }));
      },

      init: function () {
        // After a page reload the server does not know the ticks yet.
        if (this.ids.length) this.refresh();
      },
      isOpen: function (id) {
        return this.openCards.indexOf(id) !== -1;
      },
      toggleOpen: function (id) {
        if (this.isOpen(id)) {
          this.openCards = this.openCards.filter(function (other) { return other !== id; });
        } else {
          this.openCards.push(id);
        }
        sessionStorage.setItem("openCards", JSON.stringify(this.openCards));
      },
      has: function (id) {
        return this.ids.indexOf(id) !== -1;
      },
      toggle: function (id) {
        if (this.has(id)) {
          this.ids = this.ids.filter(function (other) { return other !== id; });
        } else {
          this.ids.push(id);
        }
        this.changed();
      },
      clear: function () {
        this.ids = [];
        this.changed();
      },
      // IDs of every row now on screen (pinned rows and this page of results).
      pageIds: function () {
        var seen = [];
        document.querySelectorAll("#customer-table [data-row-id]").forEach(function (row) {
          var id = Number(row.dataset.rowId);
          if (seen.indexOf(id) === -1) seen.push(id);
        });
        return seen;
      },
      allOnPage: function () {
        var self = this;
        var page = this.pageIds();
        return page.length > 0 && page.every(function (id) { return self.has(id); });
      },
      togglePage: function (checked) {
        var self = this;
        var page = this.pageIds();
        if (checked) {
          page.forEach(function (id) { if (!self.has(id)) self.ids.push(id); });
        } else {
          this.ids = this.ids.filter(function (id) { return page.indexOf(id) === -1; });
        }
        this.changed();
      },
      // The server reports ticked IDs it would not show (hidden or deleted).
      dropInvalid: function () {
        var meta = document.getElementById("pinned-meta");
        if (!meta || !meta.dataset.dropped) return;
        var dropped = meta.dataset.dropped.split(",").map(Number);
        this.ids = this.ids.filter(function (id) { return dropped.indexOf(id) === -1; });
        this.save();
      },
      save: function () {
        sessionStorage.setItem("selected", JSON.stringify(this.ids));
      },

      // --- Copy and Share -------------------------------------------------
      // The server builds the text, re-checks every ID and writes the log row
      // before answering. `kind` is "copy" or "share". `ids`: the customers to
      // send; the ticked ones when not given (selection bar).
      fetchText: function (kind, ids) {
        var form = this.$refs.exportForm;
        var body = new URLSearchParams({ ids: (ids || this.ids).join(","), kind: kind });
        return fetch(form.dataset.textUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value },
          body: body,
        }).then(function (response) {
          if (!response.ok) throw new Error("request failed");
          return response.text().then(function (text) {
            return { text: text, count: response.headers.get("X-Customer-Count") };
          });
        });
      },
      flash: function (message) {
        var self = this;
        this.notice = message;
        clearTimeout(this._noticeTimer);
        this._noticeTimer = setTimeout(function () { self.notice = ""; }, 3500);
      },
      // Toolbar Copy. Works in any browser, in three layers (feature checks, never browser names):
      // 1. Modern clipboard. ClipboardItem lets the write start inside the tap, before the text
      //    arrives, which iPhones require; otherwise writeText after the text arrives.
      // 2. The older copy command (also works on plain http://).
      // 3. The sheet with the text, where the person copies with one more tap.
      // `ids`: one row's button passes [id]; the selection bar passes nothing.
      copy: function (ids) {
        var self = this;
        this.busy = true;
        var fetched = this.fetchText("copy", Array.isArray(ids) ? ids : null);
        var written;
        try {
          if (navigator.clipboard && window.ClipboardItem) {
            var blob = fetched.then(function (result) {
              return new Blob([result.text], { type: "text/plain" });
            });
            written = navigator.clipboard.write([new ClipboardItem({ "text/plain": blob })]);
          } else if (navigator.clipboard) {
            written = fetched.then(function (result) {
              return navigator.clipboard.writeText(result.text);
            });
          }
        } catch (error) {
          written = null;
        }
        written = written || Promise.reject(new Error("no clipboard"));
        written.catch(function () {}); // handled below, once the text is here
        fetched
          .then(function (result) {
            var done = function () { self.flash("คัดลอกแล้ว " + result.count + " ราย"); };
            return written.then(done, function () {
              if (legacyCopy(result.text)) done();
              else self.openSheet(result.text);
            });
          })
          .catch(function () { self.flash("คัดลอกไม่สำเร็จ กรุณาลองใหม่"); })
          .finally(function () { self.busy = false; });
      },
      // Toolbar Share: fetch first, then the sheet. The sheet's own Share
      // button calls navigator.share from its click, as iOS requires.
      // `ids`: one card's button passes [id]; the selection bar passes nothing.
      openShare: function (ids) {
        var self = this;
        this.busy = true;
        this.fetchText("share", Array.isArray(ids) ? ids : null)
          .then(function (result) { self.openSheet(result.text); })
          .catch(function () { self.flash("เตรียมข้อความไม่สำเร็จ กรุณาลองใหม่"); })
          .finally(function () { self.busy = false; });
      },
      openSheet: function (text) {
        this.sheetText = text;
        this.sheetOpen = true;
      },
      closeSheet: function () {
        this.sheetOpen = false;
        this.sheetText = ""; // do not keep account numbers in the page
      },
      shareNow: function () {
        navigator.share({ text: this.sheetText }).catch(function () {});
      },
      // The sheet's Copy button runs inside the tap, so every layer is allowed here.
      copyFromSheet: function () {
        var self = this;
        var box = this.$refs.sheetText;
        var fallback = function () {
          if (legacyCopy(self.sheetText, box)) {
            self.flash("คัดลอกแล้ว");
          } else {
            selectAll(box); // last resort: the phone's own Copy menu
            self.flash("เลือกข้อความแล้ว กดคัดลอกได้เลย");
          }
        };
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(this.sheetText).then(function () { self.flash("คัดลอกแล้ว"); }, fallback);
        } else {
          fallback();
        }
      },
      changed: function () {
        this.save();
        this.refresh();
      },
      refresh: function () {
        // Wait one tick so the hidden "selected" input holds the new list.
        this.$nextTick(function () {
          document.body.dispatchEvent(new CustomEvent("selection-changed"));
        });
      },
    };
  };
})();
