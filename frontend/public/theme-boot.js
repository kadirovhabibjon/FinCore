/* Applies the theme chosen on this device before the first paint, so a
 * page forced light or dark never flashes the other one. A separate file
 * because the CSP allows no inline script. Nothing chosen: the page
 * follows the system (styles.css). */
(function () {
  try {
    var theme = localStorage.getItem("fincore:theme");
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
    }
  } catch (error) {
    // No storage (private mode): the system preference applies.
  }
})();
