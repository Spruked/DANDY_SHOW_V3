"use strict";

var assert = require("assert");
var tamp = require("../../TAMP/states/tamp_state_model.js");

function rejects(fn, pattern) {
  assert.throws(fn, pattern);
}

assert.deepStrictEqual(tamp.STATES, [
  "WAIT",
  "SEARCH",
  "AWAIT_CLARIFICATION",
  "ACQUIRE",
  "APPROACH",
  "PRESENT",
  "RECOVER",
  "RELEASE"
]);

var wait = tamp.createState();
assert.strictEqual(wait.current_state, "WAIT");
assert.strictEqual(wait.previous_state, null);
assert.strictEqual(wait.verified_intent, false);
assert.strictEqual(wait.single_target, false);
assert.strictEqual(wait.legal_action, false);
assert.strictEqual(wait.sequence, 0);

var ambiguous = tamp.classifyCandidateSet({
  verified_intent: true,
  candidates: [
    { target_id: "pricing-standard", action_id: "show-plan", legal_action: true },
    { target_id: "pricing-professional", action_id: "show-plan", legal_action: true }
  ]
});
assert.strictEqual(ambiguous.state, "AWAIT_CLARIFICATION");
assert.strictEqual(ambiguous.may_acquire, false);
assert.strictEqual(ambiguous.may_approach, false);
assert.strictEqual(ambiguous.may_present, false);
assert.strictEqual(ambiguous.may_authorize_ping, false);

var awaiting = tamp.transition(wait, "AWAIT_CLARIFICATION", {
  reason: ambiguous.reason,
  verification: {
    verified_intent: true,
    single_target: false,
    legal_action: true
  }
});
assert.strictEqual(awaiting.current_state, "AWAIT_CLARIFICATION");
assert.strictEqual(tamp.mayAuthorizePing(awaiting), false);

[
  { verified_intent: false, single_target: true, legal_action: true },
  { verified_intent: true, single_target: false, legal_action: true },
  { verified_intent: true, single_target: true, legal_action: false }
].forEach(function (verification) {
  rejects(function () {
    tamp.transition(wait, "ACQUIRE", { verification: verification });
  }, /ACQUIRE rejected/);
});

var acquired = tamp.transition(wait, "ACQUIRE", {
  reason: "single_verified_legal_choice",
  target_id: "pricing-standard",
  action_id: "show-plan",
  verification: {
    verified_intent: true,
    single_target: true,
    legal_action: true
  }
});
assert.strictEqual(acquired.current_state, "ACQUIRE");
assert.strictEqual(acquired.previous_state, "WAIT");
assert.strictEqual(acquired.target_id, "pricing-standard");
assert.strictEqual(acquired.action_id, "show-plan");
assert.strictEqual(acquired.verified_intent, true);
assert.strictEqual(acquired.single_target, true);
assert.strictEqual(acquired.legal_action, true);

rejects(function () {
  tamp.transition(wait, "PRESENT");
}, /Illegal TAMP transition: WAIT -> PRESENT/);

rejects(function () {
  tamp.transition(awaiting, "PRESENT");
}, /Illegal TAMP transition: AWAIT_CLARIFICATION -> PRESENT/);

rejects(function () {
  tamp.transition(wait, "APPROACH");
}, /Illegal TAMP transition: WAIT -> APPROACH/);

var approaching = tamp.transition(acquired, "APPROACH");
var present = tamp.transition(approaching, "PRESENT");
assert.strictEqual(tamp.mayAuthorizePing(present), true);

console.log("TAMP state model tests passed");
