(function () {
  "use strict";

  var script = document.currentScript;
  var browserBase = script && script.src ? new URL(".", script.src).toString() : "./BROWSER/";
  var packageBase = script && script.src ? new URL("../", browserBase).toString() : "./";

  function loadStyle() {
    var href = new URL("web_weaver.css", browserBase).toString();
    if (document.querySelector('link[href="' + href + '"]')) return;
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function loadScript() {
    return new Promise(function (resolve, reject) {
      if (window.WebWeaver) {
        resolve();
        return;
      }
      var tag = document.createElement("script");
      tag.src = new URL("web_weaver.js", browserBase).toString();
      tag.defer = true;
      tag.onload = function () { resolve(); };
      tag.onerror = function () { reject(new Error("Web Weaver runtime failed to load")); };
      document.head.appendChild(tag);
    });
  }

  function mount() {
    return loadScript().then(function () {
      return window.WebWeaver.mount(document.body, {
        browserBase: browserBase,
        packageBase: packageBase
      });
    });
  }

  loadStyle();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }
})();
