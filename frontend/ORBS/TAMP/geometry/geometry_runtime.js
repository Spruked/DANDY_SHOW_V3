(function (root, factory) {
  "use strict";

  var api = factory(
    typeof require === "function" ? require("../states/tamp_state_model.js") : root.WebWeaverTamp,
    typeof require === "function" ? require("../../POINTER/live_geometry/live_target_geometry.js") : root.WebWeaverLiveTargetGeometry,
    typeof require === "function" ? require("./relational_stance.js") : root.WebWeaverRelationalStance
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverGeometryRuntime = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (tamp, liveGeometry, stance) {
  "use strict";

  function evaluateGeometry(currentState, targetRecord, options) {
    options = options || {};
    var state = tamp.createState(currentState || {});
    var recordTargetId = targetRecord && targetRecord.target_id || null;
    if (state.target_id && recordTargetId && state.target_id !== recordTargetId) {
      return {
        state: state,
        geometry_status: "target_identity_mismatch",
        reason: "target_identity_mismatch",
        target_id: state.target_id,
        requested_target_id: recordTargetId,
        may_authorize_ping: false
      };
    }
    var targetId = recordTargetId || state.target_id || null;
    if (!targetId) {
      return {
        state: state,
        geometry_status: "no_target_identity",
        reason: "unknown_target_identity",
        may_authorize_ping: false
      };
    }

    var record = {};
    Object.keys(targetRecord || {}).forEach(function (key) { record[key] = targetRecord[key]; });
    record.target_id = targetId;
    var live = liveGeometry.captureLiveGeometry(record, options);

    if (live.geometry_status !== "ready") {
      var nextState = state;
      if (state.current_state === "ACQUIRE") {
        nextState = tamp.transition(state, "SEARCH", {
          reason: "target_geometry_unresolved",
          target_id: targetId,
          verification: state.verification
        });
      }
      return {
        state: nextState,
        geometry_status: live.geometry_status,
        reason: live.reason || "target_geometry_unresolved",
        target_id: targetId,
        live_geometry: live,
        may_authorize_ping: false
      };
    }

    var next = state;
    if (state.current_state === "SEARCH") {
      next = tamp.transition(state, "ACQUIRE", {
        reason: "target_geometry_rediscovered",
        target_id: targetId,
        verification: state.verification
      });
    }

    var stanceResult = stance.computeRelationalStance(live, options.stance_guidance, {
      seed: options.seed
    });

    return {
      state: next,
      geometry_status: stanceResult.stance_status === "ready" ? "ready" : "stance_unresolved",
      reason: stanceResult.stance_status === "ready" ? "geometry_ready" : stanceResult.reason,
      target_id: targetId,
      live_geometry: live,
      stance: stanceResult,
      may_authorize_ping: false,
      may_present: false
    };
  }

  return Object.freeze({
    evaluateGeometry: evaluateGeometry
  });
});
