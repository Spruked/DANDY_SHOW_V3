"use strict";

var assert = require("assert");
var tamp = require("../../TAMP/states/tamp_state_model.js");
var pingPresenter = require("../../POINTER/ping/ping_presenter.js");
var morb = require("../../POINTER/morb/morb_pointer_actuator.js");

var pointer = morb.createMorb({
  target_id: "demo-card",
  action_id: "show_card",
  launch_x: 100,
  launch_y: 200,
  ping_x: 640,
  ping_y: 270,
  geometry_version: 4,
  payload: { type: "pointer_only" }
});

assert.strictEqual(pointer.mission_type, "pointer");
assert.strictEqual(pointer.owner, "morb_pointer_actuator");
assert.strictEqual(pointer.state, "READY");
assert.strictEqual(pointer.visual.rendered_width_px, 50);
assert.strictEqual(pointer.visual.rendered_height_px, 50);
assert.strictEqual(pointer.visual.asset_path, "ASSETS/morb/webweaver-morb.png");
assert.deepStrictEqual(pointer.sound_events, ["MORB_LAUNCH", "MORB_FLIGHT", "MORB_ARRIVE", "MORB_CONFIRM", "MORB_ABORT"]);
assert.strictEqual(morb.validateMorb(pointer), true);

var launched = morb.transition(pointer, "LAUNCHED", "spawned_from_parent");
var inFlight = morb.transition(launched, "IN_FLIGHT", "flight_started");
assert.strictEqual(inFlight.state, "IN_FLIGHT");
assert.throws(function () {
  morb.transition(pointer, "COMPLETE");
}, /Illegal MORB transition/);

var plan = morb.planFlight(pointer, { speed_px_per_ms: 1, minimum_duration_ms: 300 });
assert.strictEqual(plan.destination.x, pointer.ping_x);
assert.strictEqual(plan.destination.y, pointer.ping_y);
assert.ok(plan.planned_duration_ms >= plan.minimum_duration_ms);
var sample = morb.sampleFlight(plan, plan.planned_duration_ms);
assert.strictEqual(sample.complete, true);
assert.strictEqual(sample.x, pointer.ping_x);
assert.strictEqual(sample.y, pointer.ping_y);

var geometry = {
  geometry_status: "ready",
  target_id: "demo-card",
  live_geometry: {
    geometry_version: 4,
    ping_x: 640,
    ping_y: 270
  }
};
assert.strictEqual(morb.finalCheck(pointer, geometry).valid, true);
assert.strictEqual(morb.finalCheck(pointer, {
  geometry_status: "ready",
  target_id: "demo-card",
  live_geometry: { geometry_version: 5, ping_x: 640, ping_y: 270 }
}).valid, true);
assert.strictEqual(morb.finalCheck(pointer, {
  geometry_status: "ready",
  target_id: "demo-card",
  live_geometry: { geometry_version: 5, ping_x: 641, ping_y: 270 }
}).valid, false);

var approachState = tamp.createState({
  current_state: "APPROACH",
  target_id: "demo-card",
  action_id: "show_card",
  verification: { verified_intent: true, single_target: true, legal_action: true }
});
var presentState = tamp.createState({
  current_state: "PRESENT",
  target_id: "demo-card",
  action_id: "show_card",
  verification: { verified_intent: true, single_target: true, legal_action: true }
});
var verification = { valid: true };
assert.strictEqual(pingPresenter.canAuthorizePing(approachState, verification), false);
assert.strictEqual(morb.completeAtTarget(inFlight, approachState, verification).state, "ABORTED");
var completed = morb.completeAtTarget(inFlight, presentState, verification);
assert.strictEqual(completed.state, "COMPLETE");
assert.strictEqual(completed.result.ping_shown, true);

console.log("Website MORB pointer actuator tests passed");
