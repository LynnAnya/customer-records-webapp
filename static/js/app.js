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
})();
