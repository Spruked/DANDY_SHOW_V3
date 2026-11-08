"use strict";

var assert = require("assert");
var tamp = require("../../TAMP/states/tamp_state_model.js");
var adapter = require("../../TAMP/intent/tamp_decision_adapter.js");

function approvedDecision(overrides) {
  return Object.assign({
    classification_source: "sf_orb",
    classification_status: "verified",
    intent_id: "show_pricing",
    governor_status: "approved",
    action_id: "show_plan",
    legal_action: true,
    requires_physical_target: true,
    candidate_targets: [
      {
        target_id: "pricing-standard"
      }
    ]
  }, overrides || {});
}

function assertNoPhysicalAuthority(result) {
  assert.strictEqual(result.may_acquire, false);
  assert.strictEqual(result.may_approach, false);
  assert.strictEqual(result.may_present, false);
  assert.strictEqual(result.may_point, false);
  assert.strictEqual(result.may_authorize_ping, false);
}

var wait = tamp.createState();

var raw = adapter.applyDecision(wait, "take me to pricing");
assert.strictEqual(raw.state.current_state, "WAIT");
assert.strictEqual(raw.reason, "unverified_classification");
assertNoPhysicalAuthority(raw);

var wrongSource = adapter.applyDecision(wait, approvedDecision({
  classification_source: "browser_text"
}));
assert.strictEqual(wrongSource.state.current_state, "WAIT");
assert.strictEqual(wrongSource.reason, "unverified_classification");
assertNoPhysicalAuthority(wrongSource);

var governorReject = adapter.applyDecision(wait, approvedDecision({
  governor_status: "rejected",
  legal_action: true
}));
assert.strictEqual(governorReject.state.current_state, "WAIT");
assert.strictEqual(governorReject.reason, "governor_rejected_action");
assertNoPhysicalAuthority(governorReject);

var informational = adapter.applyDecision(wait, approvedDecision({
  intent_id: "explain_founding_beta",
  action_id: "answer_verbally",
  requires_physical_target: false,
  candidate_targets: []
}));
assert.strictEqual(informational.state.current_state, "WAIT");
assert.strictEqual(informational.reason, "informational_no_physical_target");
assertNoPhysicalAuthority(informational);

var ambiguous = adapter.applyDecision(wait, approvedDecision({
  candidate_targets: [
    { target_id: "pricing-standard" },
    { target_id: "pricing-professional" }
  ]
}));
assert.strictEqual(ambiguous.state.current_state, "AWAIT_CLARIFICATION");
assert.strictEqual(ambiguous.state.previous_state, "WAIT");
assert.strictEqual(ambiguous.reason, "multiple_legal_targets");
assert.strictEqual(ambiguous.candidate_count, 2);
assertNoPhysicalAuthority(ambiguous);
assert.strictEqual(tamp.mayAuthorizePing(ambiguous.state), false);

var clarified = adapter.applyDecision(ambiguous.state, approvedDecision({
  candidate_targets: [
    { target_id: "pricing-professional" }
  ]
}));
assert.strictEqual(clarified.state.current_state, "ACQUIRE");
assert.strictEqual(clarified.state.previous_state, "AWAIT_CLARIFICATION");
assert.strictEqual(clarified.state.target_id, "pricing-professional");

var single = adapter.applyDecision(wait, approvedDecision());
assert.strictEqual(single.state.current_state, "ACQUIRE");
assert.strictEqual(single.state.previous_state, "WAIT");
assert.strictEqual(single.state.target_id, "pricing-standard");
assert.strictEqual(single.state.action_id, "show_plan");
assert.strictEqual(single.state.verified_intent, true);
assert.strictEqual(single.state.single_target, true);
assert.strictEqual(single.state.legal_action, true);
assert.strictEqual(single.may_acquire, true);
assert.strictEqual(single.may_approach, false);
assert.strictEqual(single.may_present, false);
assert.strictEqual(single.may_authorize_ping, false);

var zero = adapter.applyDecision(wait, approvedDecision({
  candidate_targets: []
}));
assert.strictEqual(zero.state.current_state, "WAIT");
assert.strictEqual(zero.reason, "no_legal_target");
assert.notStrictEqual(zero.state.current_state, "SEARCH");
assert.notStrictEqual(zero.state.current_state, "ACQUIRE");
assertNoPhysicalAuthority(zero);

var missingActionId = adapter.applyDecision(wait, approvedDecision({
  action_id: null
}));
assert.strictEqual(missingActionId.state.current_state, "WAIT");
assert.strictEqual(missingActionId.reason, "governor_rejected_action");
assertNoPhysicalAuthority(missingActionId);

assert.throws(function () {
  tamp.transition(wait, "PRESENT");
}, /Illegal TAMP transition: WAIT -> PRESENT/);

assert.throws(function () {
  tamp.transition(wait, "APPROACH");
}, /Illegal TAMP transition: WAIT -> APPROACH/);

var listeningInteraction = "listening";
assert.strictEqual(listeningInteraction, "listening");
assert.strictEqual(wait.current_state, "WAIT");

console.log("TAMP decision adapter tests passed");
