// Theme: "light" | "dark" | "system", stored in localStorage under "theme".
// Loaded in <head> without defer so the right theme is applied before first paint.
(function () {
  var media = window.matchMedia("(prefers-color-scheme: dark)");

  function stored() {
    var value = localStorage.getItem("theme");
    return value === "light" || value === "dark" ? value : "system";
  }

  function apply() {
    var choice = stored();
    var dark = choice === "dark" || (choice === "system" && media.matches);
    document.documentElement.classList.toggle("dark", dark);
  }

  apply();
  media.addEventListener("change", apply);

  // Used by the theme switch (Alpine): x-data="themeSwitch()"
  window.themeSwitch = function () {
    return {
      choice: stored(),
      set: function (value) {
        this.choice = value;
        localStorage.setItem("theme", value);
        apply();
      },
    };
  };
})();
