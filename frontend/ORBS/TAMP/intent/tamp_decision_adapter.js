(function (root, factory) {
  "use strict";

  var api = factory(
    typeof require === "function" ? require("../states/tamp_state_model.js") : root.WebWeaverTamp
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverTampDecisionAdapter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (tamp) {
  "use strict";

  var APPROVED_CLASSIFICATION_SOURCE = "sf_orb";
  var VERIFIED_CLASSIFICATION_STATUSES = Object.freeze(["classified", "verified"]);
  var APPROVED_GOVERNOR_STATUSES = Object.freeze(["approved"]);

  function isObject(value) {
    return !!value && typeof value === "object" && !Array.isArray(value);
  }

  function normalizeDecision(decision) {
    if (!isObject(decision)) {
      return {
        classification_source: null,
        classification_status: null,
        intent_id: null,
        governor_status: null,
        action_id: null,
        legal_action: null,
        requires_physical_target: true,
        candidate_targets: []
      };
    }
    return {
      classification_source: decision.classification_source || null,
      classification_status: decision.classification_status || null,
      intent_id: decision.intent_id || null,
      governor_status: decision.governor_status || null,
      action_id: decision.action_id || null,
      legal_action: decision.legal_action === true,
      requires_physical_target: decision.requires_physical_target !== false,
      candidate_targets: Array.isArray(decision.candidate_targets) ? decision.candidate_targets : []
    };
  }

  function isVerifiedClassification(decision) {
    return decision.classification_source === APPROVED_CLASSIFICATION_SOURCE &&
      VERIFIED_CLASSIFICATION_STATUSES.indexOf(decision.classification_status) !== -1 &&
      !!decision.intent_id;
  }

  function isLegalActionApproved(decision) {
    return decision.legal_action === true &&
      APPROVED_GOVERNOR_STATUSES.indexOf(decision.governor_status) !== -1 &&
      !!decision.action_id;
  }

  function legitimateTargets(candidateTargets) {
    return candidateTargets.filter(function (target) {
      return isObject(target) && target.legal_target !== false && !!(target.target_id || target.id);
    });
  }

  function targetId(target) {
    return target.target_id || target.id || null;
  }

  function waitResult(state, reason, decision) {
    return {
      state: tamp.createState({
        current_state: "WAIT",
        previous_state: state && state.current_state ? state.current_state : null,
        reason: reason,
        sequence: state && typeof state.sequence === "number" ? state.sequence : 0
      }),
      reason: reason,
      decision: decision,
      may_acquire: false,
      may_approach: false,
      may_present: false,
      may_point: false,
      may_authorize_ping: false
    };
  }

  function applyDecision(currentState, rawDecision) {
    if (!tamp) {
      throw new Error("PASS 3 TAMP state model is required");
    }
    var state = tamp.createState(currentState || {});
    var decision = normalizeDecision(rawDecision);

    if (!isVerifiedClassification(decision)) {
      return waitResult(state, "unverified_classification", decision);
    }

    if (!isLegalActionApproved(decision)) {
      return waitResult(state, "governor_rejected_action", decision);
    }

    if (!decision.requires_physical_target) {
      return waitResult(state, "informational_no_physical_target", decision);
    }

    var candidates = legitimateTargets(decision.candidate_targets);

    if (candidates.length === 0) {
      return waitResult(state, "no_legal_target", decision);
    }

    if (candidates.length > 1) {
      var awaiting = tamp.transition(state, "AWAIT_CLARIFICATION", {
        reason: "multiple_legal_targets",
        action_id: decision.action_id,
        verification: {
          verified_intent: true,
          single_target: false,
          legal_action: true
        }
      });
      return {
        state: awaiting,
        reason: "multiple_legal_targets",
        decision: decision,
        candidate_count: candidates.length,
        may_acquire: false,
        may_approach: false,
        may_present: false,
        may_point: false,
        may_authorize_ping: false
      };
    }

    var target = candidates[0];
    var acquired = tamp.transition(state, "ACQUIRE", {
      reason: "single_verified_legal_target",
      target_id: targetId(target),
      action_id: decision.action_id,
      verification: {
        verified_intent: true,
        single_target: true,
        legal_action: true
      }
    });

    return {
      state: acquired,
      reason: "single_verified_legal_target",
      decision: decision,
      candidate_count: 1,
      may_acquire: true,
      may_approach: false,
      may_present: false,
      may_point: false,
      may_authorize_ping: false
    };
  }

  return Object.freeze({
    APPROVED_CLASSIFICATION_SOURCE: APPROVED_CLASSIFICATION_SOURCE,
    APPROVED_GOVERNOR_STATUSES: APPROVED_GOVERNOR_STATUSES,
    VERIFIED_CLASSIFICATION_STATUSES: VERIFIED_CLASSIFICATION_STATUSES,
    applyDecision: applyDecision,
    isLegalActionApproved: isLegalActionApproved,
    isVerifiedClassification: isVerifiedClassification,
    legitimateTargets: legitimateTargets
  });
});
