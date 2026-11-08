(function (root, factory) {
  "use strict";

  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverRelationalStance = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEFAULT_GUIDANCE = Object.freeze({
    preferred_direction: "left",
    fallback_directions: Object.freeze(["upper-left", "lower-left", "above", "below", "right"]),
    base_n: 220,
    variation_px: 10,
    minimum_clearance: 16,
    orb_width: 164,
    orb_height: 164
  });

  var DIRECTIONS = Object.freeze({
    left: Object.freeze({ x: -1, y: 0, px: 0, py: -1 }),
    "upper-left": Object.freeze({ x: -0.7071067812, y: -0.7071067812, px: 0.7071067812, py: -0.7071067812 }),
    "lower-left": Object.freeze({ x: -0.7071067812, y: 0.7071067812, px: -0.7071067812, py: -0.7071067812 }),
    above: Object.freeze({ x: 0, y: -1, px: 1, py: 0 }),
    below: Object.freeze({ x: 0, y: 1, px: 1, py: 0 }),
    right: Object.freeze({ x: 1, y: 0, px: 0, py: 1 })
  });

  function mergeGuidance(guidance) {
    var out = {};
    Object.keys(DEFAULT_GUIDANCE).forEach(function (key) { out[key] = DEFAULT_GUIDANCE[key]; });
    Object.keys(guidance || {}).forEach(function (key) { out[key] = guidance[key]; });
    return out;
  }

  function seededUnit(seed, index) {
    var text = String(seed || "stance") + ":" + index;
    var hash = 2166136261;
    for (var i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return ((hash >>> 0) % 10000) / 10000;
  }

  function variation(seed, limit, index) {
    if (!limit) return 0;
    return (seededUnit(seed, index) * 2 - 1) * limit;
  }

  function rectsOverlap(a, b) {
    return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  }

  function distance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function orbRect(center, guidance) {
    var halfW = guidance.orb_width / 2;
    var halfH = guidance.orb_height / 2;
    return {
      left: center.x - halfW,
      top: center.y - halfH,
      right: center.x + halfW,
      bottom: center.y + halfH,
      width: guidance.orb_width,
      height: guidance.orb_height
    };
  }

  function withinViewport(rect, viewport) {
    return rect.left >= 0 && rect.top >= 0 && rect.right <= viewport.width && rect.bottom <= viewport.height;
  }

  function expanded(rect, amount) {
    return {
      left: rect.left - amount,
      top: rect.top - amount,
      right: rect.right + amount,
      bottom: rect.bottom + amount
    };
  }

  function directionOrder(guidance) {
    var order = [guidance.preferred_direction].concat(guidance.fallback_directions || []);
    var seen = {};
    return order.filter(function (item) {
      if (!DIRECTIONS[item] || seen[item]) return false;
      seen[item] = true;
      return true;
    });
  }

  function candidateForDirection(ping, directionName, guidance, seed, index) {
    var dir = DIRECTIONS[directionName];
    var n = Number(guidance.base_n);
    var offset = variation(seed, Number(guidance.variation_px), index);
    var center = {
      x: ping.x + dir.x * n + dir.px * offset,
      y: ping.y + dir.y * n + dir.py * offset
    };
    return {
      direction: directionName,
      stance_x: center.x,
      stance_y: center.y,
      variation_offset_px: offset,
      n: distance(center, ping)
    };
  }

  function validateCandidate(candidate, targetRect, viewport, guidance) {
    var rect = orbRect({ x: candidate.stance_x, y: candidate.stance_y }, guidance);
    if (!withinViewport(rect, viewport)) return { valid: false, reason: "outside_viewport", orb_rect: rect };
    if (rectsOverlap(rect, expanded(targetRect, guidance.minimum_clearance))) {
      return { valid: false, reason: "target_obstructed", orb_rect: rect };
    }
    if (candidate.n < guidance.base_n - guidance.variation_px - 0.001) {
      return { valid: false, reason: "minimum_n_violation", orb_rect: rect };
    }
    return { valid: true, reason: "valid", orb_rect: rect };
  }

  function computeRelationalStance(liveGeometry, guidance, options) {
    options = options || {};
    guidance = mergeGuidance(guidance);
    var ping = { x: liveGeometry.ping_x, y: liveGeometry.ping_y };
    var order = directionOrder(guidance);
    var rejected = [];

    for (var i = 0; i < order.length; i += 1) {
      var candidate = candidateForDirection(ping, order[i], guidance, options.seed || liveGeometry.geometry_version || 0, i);
      var validation = validateCandidate(candidate, liveGeometry.rect, liveGeometry.viewport, guidance);
      if (validation.valid) {
        return {
          stance_status: "ready",
          ping_x: liveGeometry.ping_x,
          ping_y: liveGeometry.ping_y,
          stance_x: candidate.stance_x,
          stance_y: candidate.stance_y,
          n: candidate.n,
          base_n: guidance.base_n,
          direction: candidate.direction,
          variation_offset_px: candidate.variation_offset_px,
          variation_limit_px: guidance.variation_px,
          orb_rect: validation.orb_rect,
          rejected: rejected,
          may_authorize_ping: false
        };
      }
      rejected.push({
        direction: candidate.direction,
        reason: validation.reason,
        stance_x: candidate.stance_x,
        stance_y: candidate.stance_y
      });
    }

    return {
      stance_status: "unresolved",
      reason: "no_legal_stance",
      ping_x: liveGeometry.ping_x,
      ping_y: liveGeometry.ping_y,
      rejected: rejected,
      may_authorize_ping: false
    };
  }

  return Object.freeze({
    DEFAULT_GUIDANCE: DEFAULT_GUIDANCE,
    computeRelationalStance: computeRelationalStance,
    validateCandidate: validateCandidate
  });
});
