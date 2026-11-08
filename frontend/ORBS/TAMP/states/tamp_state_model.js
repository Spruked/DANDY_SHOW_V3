(function (root, factory) {
  "use strict";

  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverTamp = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var STATES = Object.freeze([
    "WAIT",
    "SEARCH",
    "AWAIT_CLARIFICATION",
    "ACQUIRE",
    "APPROACH",
    "PRESENT",
    "RECOVER",
    "RELEASE"
  ]);

  var TRANSITIONS = Object.freeze({
    WAIT: Object.freeze(["AWAIT_CLARIFICATION", "ACQUIRE"]),
    SEARCH: Object.freeze(["ACQUIRE", "RECOVER", "RELEASE"]),
    AWAIT_CLARIFICATION: Object.freeze(["ACQUIRE", "WAIT", "RELEASE"]),
    ACQUIRE: Object.freeze(["SEARCH", "APPROACH", "RELEASE"]),
    APPROACH: Object.freeze(["PRESENT", "RECOVER", "RELEASE"]),
    PRESENT: Object.freeze(["RELEASE", "RECOVER"]),
    RECOVER: Object.freeze(["ACQUIRE", "APPROACH", "RELEASE"]),
    RELEASE: Object.freeze(["WAIT"])
  });

  function hasState(value) {
    return STATES.indexOf(value) !== -1;
  }

  function normalizeFlags(flags) {
    flags = flags || {};
    return {
      verified_intent: flags.verified_intent === true,
      single_target: flags.single_target === true,
      legal_action: flags.legal_action === true
    };
  }

  function acquireGate(flags) {
    var normalized = normalizeFlags(flags);
    return {
      allowed: normalized.verified_intent && normalized.single_target && normalized.legal_action,
      verification: normalized
    };
  }

  function createState(options) {
    options = options || {};
    var current = options.current_state || "WAIT";
    if (!hasState(current)) {
      throw new Error("Unknown TAMP state: " + current);
    }
    var verification = normalizeFlags(options.verification);
    return {
      current_state: current,
      previous_state: options.previous_state || null,
      reason: options.reason || "initial",
      target_id: options.target_id || null,
      action_id: options.action_id || null,
      verified_intent: verification.verified_intent,
      single_target: verification.single_target,
      legal_action: verification.legal_action,
      sequence: Number(options.sequence || 0),
      transitioned_at: options.transitioned_at || null,
      verification: verification
    };
  }

  function transition(state, nextState, options) {
    options = options || {};
    state = createState(state || {});
    if (!hasState(nextState)) {
      throw new Error("Unknown TAMP state: " + nextState);
    }
    if ((TRANSITIONS[state.current_state] || []).indexOf(nextState) === -1) {
      throw new Error("Illegal TAMP transition: " + state.current_state + " -> " + nextState);
    }

    var verification = normalizeFlags(options.verification || state.verification);
    if (nextState === "ACQUIRE") {
      var gate = acquireGate(verification);
      if (!gate.allowed) {
        throw new Error(
          "ACQUIRE rejected: verified_intent=" + gate.verification.verified_intent +
          ", single_target=" + gate.verification.single_target +
          ", legal_action=" + gate.verification.legal_action
        );
      }
      verification = gate.verification;
    }

    return createState({
      current_state: nextState,
      previous_state: state.current_state,
      reason: options.reason || "transition",
      target_id: options.target_id || state.target_id || null,
      action_id: options.action_id || state.action_id || null,
      sequence: state.sequence + 1,
      transitioned_at: options.transitioned_at || new Date().toISOString(),
      verification: verification
    });
  }

  function classifyCandidateSet(input) {
    input = input || {};
    var candidates = Array.isArray(input.candidates) ? input.candidates : [];
    var legalCandidates = candidates.filter(function (candidate) {
      return candidate && candidate.legal_action === true;
    });

    if (legalCandidates.length > 1) {
      return {
        state: "AWAIT_CLARIFICATION",
        reason: "multiple_unresolved_legal_candidates",
        may_acquire: false,
        may_approach: false,
        may_present: false,
        may_authorize_ping: false
      };
    }

    if (
      input.verified_intent === true &&
      legalCandidates.length === 1 &&
      legalCandidates[0].action_id
    ) {
      return {
        state: "ACQUIRE",
        reason: "single_verified_legal_choice",
        target_id: legalCandidates[0].target_id || null,
        action_id: legalCandidates[0].action_id || null,
        may_acquire: true,
        may_approach: false,
        may_present: false,
        may_authorize_ping: false
      };
    }

    return {
      state: "WAIT",
      reason: "no_target_directed_task",
      may_acquire: false,
      may_approach: false,
      may_present: false,
      may_authorize_ping: false
    };
  }

  function mayAuthorizePing(state) {
    return !!state && state.current_state === "PRESENT";
  }

  return Object.freeze({
    STATES: STATES,
    TRANSITIONS: TRANSITIONS,
    acquireGate: acquireGate,
    classifyCandidateSet: classifyCandidateSet,
    createState: createState,
    hasState: hasState,
    mayAuthorizePing: mayAuthorizePing,
    transition: transition
  });
});
