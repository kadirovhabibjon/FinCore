/* Runs before the app, in deliberately old JavaScript, so it works on any
 * browser the app itself might not. If the app hasn't drawn anything a
 * few seconds after load — a browser too old for the bundle, a script
 * blocked or failed to load, an exception at startup — it replaces the
 * blank page with what went wrong and the browser's identity, instead of
 * leaving a white screen. Served from 'self', so the CSP allows it. */
(function () {
  var errors = [];
  function record(message) {
    errors.push(String(message));
  }
  window.addEventListener("error", function (event) {
    var target = event.target;
    if (target && target !== window && (target.src || target.href)) {
      record("Failed to load " + (target.src || target.href));
    } else {
      record(event.message || event.error);
    }
  }, true);
  window.addEventListener("unhandledrejection", function (event) {
    var reason = event.reason;
    record("Unhandled: " + (reason && reason.message ? reason.message : reason));
  });
  window.addEventListener("load", function () {
    setTimeout(function () {
      var root = document.getElementById("root");
      if (!root || root.childNodes.length > 0) return;
      var box = document.createElement("div");
      box.setAttribute("role", "alert");
      box.style.cssText =
        "font:15px/1.5 system-ui,sans-serif;padding:24px;max-width:640px;margin:auto;color:#1a2233";
      var title = document.createElement("h1");
      title.style.cssText = "font-size:20px";
      title.appendChild(document.createTextNode("FinCore couldn't start in this browser"));
      var details = document.createElement("pre");
      details.style.cssText = "white-space:pre-wrap;word-break:break-word;background:#f1f3f7;padding:12px;border-radius:8px";
      details.appendChild(document.createTextNode(
        (errors.length ? errors.join("\n") : "No error was reported (the app script may not have run).") +
        "\n\nBrowser: " + navigator.userAgent + "\nPage: " + location.href
      ));
      box.appendChild(title);
      box.appendChild(details);
      document.body.appendChild(box);
    }, 4000);
  });
})();
