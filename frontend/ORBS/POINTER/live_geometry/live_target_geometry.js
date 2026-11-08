(function (root, factory) {
  "use strict";

  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverLiveTargetGeometry = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var geometrySequence = 0;

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function normalizeTarget(input) {
    input = input || {};
    return {
      target_id: input.target_id || null,
      semantic_locator: input.semantic_locator || input.selector || null,
      anchor_strategy: input.anchor_strategy || "element_center",
      meaning: input.meaning || "",
      direct_aliases: input.direct_aliases || [],
      intent_aliases: input.intent_aliases || [],
      structural_context: input.structural_context || {},
      confidence: typeof input.confidence === "number" ? input.confidence : 1
    };
  }

  function queryElements(doc, selector) {
    if (!selector) return [];
    try {
      return Array.prototype.slice.call(doc.querySelectorAll(selector));
    } catch (_error) {
      return [];
    }
  }

  function elementText(element) {
    return normalizeText([
      element.textContent || "",
      element.getAttribute && element.getAttribute("aria-label") || "",
      element.getAttribute && element.getAttribute("placeholder") || "",
      element.getAttribute && element.getAttribute("name") || ""
    ].join(" "));
  }

  function matchesRecordIdentity(element, record) {
    var expectedTag = String(record.structural_context.tag || "").toLowerCase();
    if (expectedTag && element.tagName.toLowerCase() !== expectedTag) return false;

    var text = elementText(element);
    var meaningText = String(record.meaning || "").replace(/^[^:]+:\s*/, "");
    var fragments = [meaningText].concat(record.direct_aliases || [], record.intent_aliases || [])
      .map(function (item) { return normalizeText(item).slice(0, 120); })
      .filter(function (item) { return item.length >= 2; });
    return !fragments.length || fragments.some(function (fragment) {
      return text.indexOf(fragment) !== -1 || fragment.indexOf(text) !== -1;
    });
  }

  function resolveElement(record, doc) {
    var parent = String(record.structural_context.parent_locator || "").trim();
    var child = String(record.semantic_locator || "").trim();
    var scoped = parent && child ? parent + " " + child : child;
    var bySemantic = queryElements(doc, scoped).concat(queryElements(doc, child));
    for (var i = 0; i < bySemantic.length; i += 1) {
      if (matchesRecordIdentity(bySemantic[i], record)) {
        return { element: bySemantic[i], method: "semantic_locator", locator: scoped || child };
      }
    }

    var escapedId = String(record.target_id || "").replace(/"/g, '\\"');
    var identitySelector = '[data-orb-target="' + escapedId + '"], [data-target-id="' + escapedId + '"]';
    var byIdentity = queryElements(doc, identitySelector);
    if (byIdentity[0]) {
      return { element: byIdentity[0], method: "target_id_attribute", locator: identitySelector };
    }

    return null;
  }

  function rectFromElement(element) {
    var rect = element.getBoundingClientRect();
    return {
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height
    };
  }

  function viewportFrom(win) {
    var docEl = win.document && win.document.documentElement || {};
    return {
      width: win.innerWidth || docEl.clientWidth || 0,
      height: win.innerHeight || docEl.clientHeight || 0
    };
  }

  function visibilityFromRect(rect, viewport) {
    return {
      has_box: rect.width > 0 && rect.height > 0,
      intersects_viewport: rect.right > 0 && rect.bottom > 0 && rect.left < viewport.width && rect.top < viewport.height,
      fully_in_viewport: rect.left >= 0 && rect.top >= 0 && rect.right <= viewport.width && rect.bottom <= viewport.height
    };
  }

  function computePing(rect, anchorStrategy) {
    if (anchorStrategy === "text_start") {
      return { ping_x: rect.left, ping_y: rect.top + rect.height / 2, anchor_strategy: anchorStrategy };
    }
    if (anchorStrategy === "heading_center" || anchorStrategy === "card_title") {
      return { ping_x: rect.left + rect.width / 2, ping_y: rect.top + Math.min(rect.height / 2, 28), anchor_strategy: anchorStrategy };
    }
    return { ping_x: rect.left + rect.width / 2, ping_y: rect.top + rect.height / 2, anchor_strategy: anchorStrategy || "element_center" };
  }

  function captureLiveGeometry(input, options) {
    options = options || {};
    var win = options.window || (typeof window !== "undefined" ? window : null);
    var doc = options.document || (win && win.document);
    var record = normalizeTarget(input);

    if (!record.target_id) {
      return {
        geometry_status: "no_target_identity",
        reason: "unknown_target_identity",
        may_authorize_ping: false
      };
    }
    if (!win || !doc) {
      return {
        geometry_status: "unresolved",
        reason: "no_browser_document",
        target_id: record.target_id,
        may_authorize_ping: false
      };
    }

    var resolved = resolveElement(record, doc);
    if (!resolved) {
      return {
        geometry_status: "unresolved",
        reason: "target_geometry_unresolved",
        target_id: record.target_id,
        may_authorize_ping: false
      };
    }

    var rect = rectFromElement(resolved.element);
    var viewport = viewportFrom(win);
    var visibility = visibilityFromRect(rect, viewport);
    var ping = computePing(rect, record.anchor_strategy);
    geometrySequence += 1;

    return {
      geometry_status: "ready",
      target_id: record.target_id,
      element: resolved.element,
      locator_evidence: {
        method: resolved.method,
        locator: resolved.locator
      },
      rect: rect,
      viewport: viewport,
      visibility: visibility,
      geometry_version: geometrySequence,
      resolution_confidence: record.confidence,
      ping_x: ping.ping_x,
      ping_y: ping.ping_y,
      anchor_strategy: ping.anchor_strategy,
      may_authorize_ping: false
    };
  }

  return Object.freeze({
    captureLiveGeometry: captureLiveGeometry,
    computePing: computePing,
    normalizeTarget: normalizeTarget
  });
});
