(function (root, factory) {
  "use strict";

  var api = factory(
    typeof require === "function" ? require("../states/tamp_state_model.js") : root.WebWeaverTamp
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverOneOutExecution = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (tamp) {
  "use strict";

  var DEFAULT_GLIDE = Object.freeze({
    default_speed_px_per_ms: 0.22,
    minimum_duration_ms: 900,
    preparation_estimate_ms: 250,
    release_delay_ms: 650
  });

  function merge(base, override) {
    var out = {};
    Object.keys(base || {}).forEach(function (key) { out[key] = base[key]; });
    Object.keys(override || {}).forEach(function (key) { out[key] = override[key]; });
    return out;
  }

  function distance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function authorityLockFromState(state) {
    state = tamp.createState(state || {});
    return {
      valid: state.current_state === "ACQUIRE" &&
        state.verified_intent === true &&
        state.single_target === true &&
        state.legal_action === true &&
        !!state.target_id &&
        !!state.action_id,
      verified_intent: state.verified_intent === true,
      single_target: state.single_target === true,
      legal_action: state.legal_action === true,
      target_id: state.target_id,
      action_id: state.action_id
    };
  }

  function physicalLockFromGeometry(geometryResult) {
    var live = geometryResult && geometryResult.live_geometry || {};
    var stance = geometryResult && geometryResult.stance || {};
    var valid = geometryResult &&
      geometryResult.geometry_status === "ready" &&
      live.geometry_status === "ready" &&
      stance.stance_status === "ready" &&
      typeof live.ping_x === "number" &&
      typeof live.ping_y === "number" &&
      typeof stance.stance_x === "number" &&
      typeof stance.stance_y === "number" &&
      typeof stance.n === "number";

    return {
      valid: !!valid,
      geometry_status: geometryResult && geometryResult.geometry_status || null,
      geometry_version: live.geometry_version || null,
      target_id: geometryResult && geometryResult.target_id || live.target_id || null,
      ping_x: live.ping_x,
      ping_y: live.ping_y,
      stance_x: stance.stance_x,
      stance_y: stance.stance_y,
      n: stance.n,
      direction: stance.direction || null,
      target_evidence: live.locator_evidence || null
    };
  }

  function createTwoInLock(state, geometryResult) {
    var authority = authorityLockFromState(state);
    var physical = physicalLockFromGeometry(geometryResult);
    return {
      valid: authority.valid && physical.valid && authority.target_id === physical.target_id,
      authority_lock: authority,
      physical_lock: physical
    };
  }

  function planGlide(start, destination, config) {
    config = merge(DEFAULT_GLIDE, config || {});
    var travel = distance(start, destination);
    var travelDuration = travel / Math.max(0.001, Number(config.default_speed_px_per_ms));
    var planned = Math.max(
      Number(config.minimum_duration_ms),
      travelDuration,
      Number(config.preparation_estimate_ms)
    );
    return {
      start: start,
      destination: destination,
      distance_px: travel,
      planned_duration_ms: planned,
      minimum_duration_ms: Number(config.minimum_duration_ms),
      preparation_estimate_ms: Number(config.preparation_estimate_ms)
    };
  }

  function easeOutCubic(t) {
    var clamped = Math.max(0, Math.min(1, t));
    return 1 - Math.pow(1 - clamped, 3);
  }

  function sampleGlide(plan, elapsedMs) {
    var t = Math.max(0, Math.min(1, elapsedMs / plan.planned_duration_ms));
    var eased = easeOutCubic(t);
    return {
      x: plan.start.x + (plan.destination.x - plan.start.x) * eased,
      y: plan.start.y + (plan.destination.y - plan.start.y) * eased,
      progress: t,
      eased_progress: eased,
      decelerating: t >= 0.62 && t < 1,
      complete: t >= 1
    };
  }

  function verifyFinalLock(lock, finalGeometry) {
    var finalLock = physicalLockFromGeometry(finalGeometry);
    var valid = lock.valid &&
      finalLock.valid &&
      lock.authority_lock.target_id === finalLock.target_id &&
      Math.abs(lock.physical_lock.ping_x - finalLock.ping_x) < 0.001 &&
      Math.abs(lock.physical_lock.ping_y - finalLock.ping_y) < 0.001;
    return {
      valid: valid,
      physical_lock: finalLock
    };
  }

  function canAuthorizePing(state, finalVerification) {
    state = tamp.createState(state || {});
    return state.current_state === "PRESENT" && !!finalVerification && finalVerification.valid === true;
  }

  function beginApproach(state, geometryResult, startPosition, config) {
    var lock = createTwoInLock(state, geometryResult);
    if (!lock.valid) {
      return {
        execution_status: "rejected",
        reason: !lock.authority_lock.valid ? "authority_lock_invalid" : "physical_lock_invalid",
        state: tamp.createState(state || {}),
        two_in_lock: lock,
        may_authorize_ping: false
      };
    }
    var approach = tamp.transition(state, "APPROACH", {
      reason: "two_in_lock_valid",
      target_id: lock.authority_lock.target_id,
      action_id: lock.authority_lock.action_id,
      verification: {
        verified_intent: true,
        single_target: true,
        legal_action: true
      }
    });
    var destination = {
      x: lock.physical_lock.stance_x,
      y: lock.physical_lock.stance_y
    };
    return {
      execution_status: "approach",
      state: approach,
      two_in_lock: lock,
      movement_mode: "approach",
      owner: "tamp_choreography",
      destination: destination,
      glide_plan: planGlide(startPosition, destination, config),
      may_authorize_ping: false
    };
  }

  function completeApproach(approachResult, finalGeometry) {
    var state = tamp.createState(approachResult.state || {});
    var finalVerification = verifyFinalLock(approachResult.two_in_lock, finalGeometry);
    if (!finalVerification.valid) {
      var recover = tamp.transition(state, "RECOVER", {
        reason: "final_verification_failed",
        target_id: approachResult.two_in_lock.authority_lock.target_id,
        action_id: approachResult.two_in_lock.authority_lock.action_id,
        verification: state.verification
      });
      return {
        execution_status: "recovery_required",
        state: recover,
        final_verification: finalVerification,
        may_authorize_ping: false,
        may_present: false
      };
    }
    var present = tamp.transition(state, "PRESENT", {
      reason: "arrival_final_verified",
      target_id: approachResult.two_in_lock.authority_lock.target_id,
      action_id: approachResult.two_in_lock.authority_lock.action_id,
      verification: state.verification
    });
    return {
      execution_status: "present",
      state: present,
      final_verification: finalVerification,
      point: {
        from_x: approachResult.destination.x,
        from_y: approachResult.destination.y,
        to_x: approachResult.two_in_lock.physical_lock.ping_x,
        to_y: approachResult.two_in_lock.physical_lock.ping_y
      },
      may_authorize_ping: true,
      may_present: true
    };
  }

  function releasePresentation(state) {
    var release = tamp.transition(state, "RELEASE", {
      reason: "presentation_complete",
      verification: state.verification
    });
    var wait = tamp.transition(release, "WAIT", {
      reason: "release_complete"
    });
    return {
      execution_status: "released",
      release_state: release,
      state: wait,
      movement_mode: "ambient",
      may_authorize_ping: false
    };
  }

  return Object.freeze({
    DEFAULT_GLIDE: DEFAULT_GLIDE,
    beginApproach: beginApproach,
    canAuthorizePing: canAuthorizePing,
    completeApproach: completeApproach,
    createTwoInLock: createTwoInLock,
    easeOutCubic: easeOutCubic,
    physicalLockFromGeometry: physicalLockFromGeometry,
    planGlide: planGlide,
    releasePresentation: releasePresentation,
    sampleGlide: sampleGlide,
    verifyFinalLock: verifyFinalLock
  });
});
