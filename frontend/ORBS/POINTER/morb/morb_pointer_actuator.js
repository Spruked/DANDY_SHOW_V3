(function (root, factory) {
  "use strict";

  var api = factory(
    typeof require === "function" ? require("../../POINTER/ping/ping_presenter.js") : root.WebWeaverPingPresenter
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverMorbPointerActuator = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (pingPresenter) {
  "use strict";

  var STATES = Object.freeze(["READY", "LAUNCHED", "IN_FLIGHT", "ARRIVED", "ACTING", "COMPLETE", "ABORTED"]);
  var VISUAL_SPEC = Object.freeze({
    asset_path: "ASSETS/morb/webweaver-morb.png",
    ico_asset_path: "ASSETS/morb/webweaver-morb.ico",
    rendered_width_px: 50,
    rendered_height_px: 50,
    glow: "black_red"
  });
  var SOUND_EVENTS = Object.freeze(["MORB_LAUNCH", "MORB_FLIGHT", "MORB_ARRIVE", "MORB_CONFIRM", "MORB_ABORT"]);

  function hasState(value) {
    return STATES.indexOf(value) !== -1;
  }

  function makeId(prefix, seed) {
    var text = String(seed || Date.now());
    var hash = 2166136261;
    for (var i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return prefix + "-" + (hash >>> 0).toString(16);
  }

  function createMorb(input) {
    input = input || {};
    return {
      morb_id: input.morb_id || makeId("web-morb", input.target_id + ":" + input.action_id + ":" + input.geometry_version),
      parent_orb_id: input.parent_orb_id || "web-weaver-orb",
      mission_type: "pointer",
      target_id: input.target_id || null,
      action_id: input.action_id || null,
      launch_x: input.launch_x,
      launch_y: input.launch_y,
      ping_x: input.ping_x,
      ping_y: input.ping_y,
      geometry_version: input.geometry_version || null,
      payload: input.payload || { type: "pointer_only" },
      sound_profile: input.sound_profile || "web_weaver_signature",
      sound_events: SOUND_EVENTS,
      visual: input.visual || VISUAL_SPEC,
      state: input.state || "READY",
      owner: "morb_pointer_actuator",
      created_at: input.created_at || null,
      completed_at: null,
      result: null
    };
  }

  function validateMorb(morb) {
    return !!morb &&
      morb.mission_type === "pointer" &&
      !!morb.target_id &&
      !!morb.action_id &&
      typeof morb.launch_x === "number" &&
      typeof morb.launch_y === "number" &&
      typeof morb.ping_x === "number" &&
      typeof morb.ping_y === "number" &&
      !!morb.geometry_version &&
      hasState(morb.state);
  }

  function transition(morb, nextState, reason) {
    if (!hasState(nextState)) {
      throw new Error("Unknown MORB state: " + nextState);
    }
    var allowed = {
      READY: ["LAUNCHED", "ABORTED"],
      LAUNCHED: ["IN_FLIGHT", "ABORTED"],
      IN_FLIGHT: ["ARRIVED", "ABORTED"],
      ARRIVED: ["ACTING", "COMPLETE", "ABORTED"],
      ACTING: ["COMPLETE", "ABORTED"],
      COMPLETE: [],
      ABORTED: []
    };
    if ((allowed[morb.state] || []).indexOf(nextState) === -1) {
      throw new Error("Illegal MORB transition: " + morb.state + " -> " + nextState);
    }
    var next = createMorb(morb);
    next.state = nextState;
    next.reason = reason || "transition";
    return next;
  }

  function planFlight(morb, config) {
    config = config || {};
    var dx = morb.ping_x - morb.launch_x;
    var dy = morb.ping_y - morb.launch_y;
    var distance = Math.hypot(dx, dy);
    var speed = Number(config.speed_px_per_ms || 0.85);
    var minimum = Number(config.minimum_duration_ms || 420);
    return {
      start: { x: morb.launch_x, y: morb.launch_y },
      destination: { x: morb.ping_x, y: morb.ping_y },
      distance_px: distance,
      planned_duration_ms: Math.max(minimum, distance / Math.max(0.001, speed)),
      minimum_duration_ms: minimum
    };
  }

  function easeOutQuad(t) {
    var clamped = Math.max(0, Math.min(1, t));
    return 1 - (1 - clamped) * (1 - clamped);
  }

  function sampleFlight(plan, elapsedMs) {
    var t = Math.max(0, Math.min(1, elapsedMs / plan.planned_duration_ms));
    var eased = easeOutQuad(t);
    return {
      x: plan.start.x + (plan.destination.x - plan.start.x) * eased,
      y: plan.start.y + (plan.destination.y - plan.start.y) * eased,
      progress: t,
      eased_progress: eased,
      complete: t >= 1
    };
  }

  function finalCheck(morb, geometryResult) {
    var live = geometryResult && geometryResult.live_geometry || {};
    return {
      valid: geometryResult && geometryResult.geometry_status === "ready" &&
        geometryResult.target_id === morb.target_id &&
        live.geometry_version >= morb.geometry_version &&
        Math.abs(live.ping_x - morb.ping_x) < 0.001 &&
        Math.abs(live.ping_y - morb.ping_y) < 0.001,
      target_id: morb.target_id,
      expected_geometry_version: morb.geometry_version,
      observed_geometry_version: live.geometry_version || null
    };
  }

  function completeAtTarget(morb, tampState, verification) {
    var arrived = transition(morb, "ARRIVED", "target_reached");
    if (!pingPresenter.canAuthorizePing(tampState, verification)) {
      var aborted = transition(arrived, "ABORTED", "ping_not_authorized");
      aborted.completed_at = new Date().toISOString();
      aborted.result = { ping_shown: false };
      return aborted;
    }
    var complete = transition(arrived, "COMPLETE", "ping_complete");
    complete.completed_at = new Date().toISOString();
    complete.result = {
      ping_shown: true,
      ping_x: morb.ping_x,
      ping_y: morb.ping_y
    };
    return complete;
  }

  return Object.freeze({
    STATES: STATES,
    SOUND_EVENTS: SOUND_EVENTS,
    VISUAL_SPEC: VISUAL_SPEC,
    completeAtTarget: completeAtTarget,
    createMorb: createMorb,
    finalCheck: finalCheck,
    planFlight: planFlight,
    sampleFlight: sampleFlight,
    transition: transition,
    validateMorb: validateMorb
  });
});
