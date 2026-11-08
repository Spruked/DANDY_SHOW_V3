(function (root, factory) {
  "use strict";

  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverPingPresenter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function canAuthorizePing(tampState, finalVerification) {
    return !!tampState && tampState.current_state === "PRESENT" && !!finalVerification && finalVerification.valid === true;
  }

  function pointRelationship(stance, ping) {
    var dx = ping.x - stance.x;
    var dy = ping.y - stance.y;
    return {
      from_x: stance.x,
      from_y: stance.y,
      to_x: ping.x,
      to_y: ping.y,
      angle_rad: Math.atan2(dy, dx),
      distance_px: Math.hypot(dx, dy)
    };
  }

  function showPing(win, ping, options) {
    options = options || {};
    if (!win || !win.document) {
      return { shown: false, reason: "no_document" };
    }
    var doc = win.document;
    var marker = doc.createElement("div");
    marker.className = options.className || "website-orb-authorized-ping";
    marker.setAttribute("data-web-weaver-authorized-ping", "true");
    marker.style.position = "fixed";
    marker.style.left = ping.x + "px";
    marker.style.top = ping.y + "px";
    marker.style.width = "18px";
    marker.style.height = "18px";
    marker.style.marginLeft = "-9px";
    marker.style.marginTop = "-9px";
    marker.style.borderRadius = "50%";
    marker.style.background = "rgba(79, 232, 142, 0.95)";
    marker.style.boxShadow = "0 0 0 10px rgba(79, 232, 142, 0.2), 0 0 24px rgba(79, 232, 142, 0.75)";
    marker.style.pointerEvents = "none";
    marker.style.zIndex = "2147483647";
    doc.body.appendChild(marker);
    win.setTimeout(function () {
      marker.remove();
    }, options.duration_ms || 900);
    return {
      shown: true,
      ping_x: ping.x,
      ping_y: ping.y
    };
  }

  return Object.freeze({
    canAuthorizePing: canAuthorizePing,
    pointRelationship: pointRelationship,
    showPing: showPing
  });
});
