// Loaded in <head> without defer, so the theme and sidebar state are applied
// before the page is painted (no flash).
//
// Stored in the browser only:
//   localStorage "theme"   = "light" | "dark" | "system"
//   localStorage "sidebar" = "collapsed" | "open"
(function () {
  var root = document.documentElement;
  var darkMedia = window.matchMedia("(prefers-color-scheme: dark)");
  var desktopMedia = window.matchMedia("(min-width: 1024px)");

  function storedTheme() {
    var value = localStorage.getItem("theme");
    return value === "light" || value === "dark" ? value : "system";
  }

  function applyTheme() {
    var choice = storedTheme();
    var dark = choice === "dark" || (choice === "system" && darkMedia.matches);
    root.classList.toggle("dark", dark);
  }

  function applySidebar(collapsed) {
    root.classList.toggle("rail-collapsed", collapsed);
  }

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
        localStorage.setItem("theme", value);
        applyTheme();
      },
    };
  };

  // Ticked customers on the customers page (Alpine): x-data="customerSelection()"
  // The ordered list of IDs lives here, outside the part HTMX swaps, and is kept
  // for this browser tab only (sessionStorage).
  window.customerSelection = function () {
    var saved = [];
    try {
      saved = JSON.parse(sessionStorage.getItem("selected") || "[]");
    } catch (error) {
      saved = [];
    }
    return {
      ids: Array.isArray(saved) ? saved : [],
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
      filterNames: ["source", "referral", "from", "to", "hidden"],
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
        form.elements.source.dispatchEvent(new Event("change", { bubbles: true }));
      },

      init: function () {
        // After a page reload the server does not know the ticks yet.
        if (this.ids.length) this.refresh();
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
      // before answering. `kind` is "copy" or "share".
      fetchText: function (kind) {
        var form = this.$refs.exportForm;
        var body = new URLSearchParams({ ids: this.ids.join(","), kind: kind });
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
      // Toolbar Copy: straight to the clipboard; if the browser refuses
      // (Safari after a network request), show the sheet instead.
      copy: function () {
        var self = this;
        this.busy = true;
        this.fetchText("copy")
          .then(function (result) {
            return navigator.clipboard.writeText(result.text).then(
              function () { self.flash("คัดลอกแล้ว " + result.count + " ราย"); },
              function () { self.openSheet(result.text); }
            );
          })
          .catch(function () { self.flash("คัดลอกไม่สำเร็จ กรุณาลองใหม่"); })
          .finally(function () { self.busy = false; });
      },
      // Toolbar Share: fetch first, then the sheet. The sheet's own Share
      // button calls navigator.share from its click, as iOS requires.
      openShare: function () {
        var self = this;
        this.busy = true;
        this.fetchText("share")
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
      copyFromSheet: function () {
        var self = this;
        var box = this.$refs.sheetText;
        navigator.clipboard.writeText(this.sheetText).then(
          function () { self.flash("คัดลอกแล้ว"); },
          function () {
            // Last resort: select the text so the user can copy it by hand.
            box.focus();
            box.select();
            self.flash("เลือกข้อความแล้ว กดคัดลอกได้เลย");
          }
        );
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
