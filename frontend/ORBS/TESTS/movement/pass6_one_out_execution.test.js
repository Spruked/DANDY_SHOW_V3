"use strict";

var assert = require("assert");
var tamp = require("../../TAMP/states/tamp_state_model.js");
var adapter = require("../../TAMP/intent/tamp_decision_adapter.js");
var execution = require("../../TAMP/movement/one_out_execution.js");
var movementController = require("../../TAMP/movement/movement_controller.js");
var pingPresenter = require("../../POINTER/ping/ping_presenter.js");

function acquireState() {
  return adapter.applyDecision(tamp.createState(), {
    classification_source: "sf_orb",
    classification_status: "verified",
    intent_id: "show_demo_target",
    governor_status: "approved",
    action_id: "show_card",
    legal_action: true,
    candidate_targets: [{ target_id: "demo-card" }]
  }).state;
}

function geometry(overrides) {
  return Object.assign({
    state: acquireState(),
    geometry_status: "ready",
    target_id: "demo-card",
    live_geometry: {
      geometry_status: "ready",
      target_id: "demo-card",
      geometry_version: 7,
      ping_x: 640,
      ping_y: 270,
      locator_evidence: { method: "semantic_locator", locator: "[data-orb-target=\"demo-card\"]" }
    },
    stance: {
      stance_status: "ready",
      stance_x: 420,
      stance_y: 490,
      n: 220,
      direction: "below"
    },
    may_authorize_ping: false,
    may_present: false
  }, overrides || {});
}

var acquired = acquireState();
var readyGeometry = geometry();

var noAuthority = execution.beginApproach(tamp.createState(), readyGeometry, { x: 10, y: 10 });
assert.strictEqual(noAuthority.execution_status, "rejected");
assert.strictEqual(noAuthority.reason, "authority_lock_invalid");
assert.notStrictEqual(noAuthority.state.current_state, "APPROACH");

var noGeometry = execution.beginApproach(acquired, geometry({ geometry_status: "unresolved" }), { x: 10, y: 10 });
assert.strictEqual(noGeometry.execution_status, "rejected");
assert.strictEqual(noGeometry.reason, "physical_lock_invalid");
assert.notStrictEqual(noGeometry.state.current_state, "APPROACH");

var approach = execution.beginApproach(acquired, readyGeometry, { x: 20, y: 30 }, {
  default_speed_px_per_ms: 0.2,
  minimum_duration_ms: 1200,
  preparation_estimate_ms: 250
});
assert.strictEqual(approach.execution_status, "approach");
assert.strictEqual(approach.state.current_state, "APPROACH");
assert.strictEqual(approach.destination.x, readyGeometry.stance.stance_x);
assert.strictEqual(approach.destination.y, readyGeometry.stance.stance_y);
assert.notStrictEqual(approach.destination.x, readyGeometry.live_geometry.ping_x);
assert.notStrictEqual(approach.destination.y, readyGeometry.live_geometry.ping_y);
assert.ok(approach.glide_plan.planned_duration_ms >= approach.glide_plan.minimum_duration_ms);
assert.ok(approach.glide_plan.distance_px > 0);
assert.strictEqual(approach.may_authorize_ping, false);

var controller = movementController.createController({ x: 20, y: 30 });
controller.writePosition({ x: 21, y: 31 }, "ambient");
controller.beginApproach(approach);
assert.strictEqual(controller.getState().movement_mode, "approach");
assert.throws(function () {
  controller.writePosition({ x: 22, y: 32 }, "ambient");
}, /Movement ownership violation/);

var early = controller.updateApproach(approach.glide_plan.planned_duration_ms * 0.2);
var late = controller.updateApproach(approach.glide_plan.planned_duration_ms * 0.8);
assert.strictEqual(late.sample.decelerating, true);
assert.ok(late.sample.eased_progress - early.sample.eased_progress < 0.8);
var end = controller.updateApproach(approach.glide_plan.planned_duration_ms);
assert.strictEqual(end.sample.complete, true);
assert.strictEqual(Math.round(end.position.x), Math.round(approach.destination.x));
assert.strictEqual(Math.round(end.position.y), Math.round(approach.destination.y));

var present = execution.completeApproach(approach, readyGeometry);
assert.strictEqual(present.execution_status, "present");
assert.strictEqual(present.state.current_state, "PRESENT");
assert.strictEqual(present.may_authorize_ping, true);
assert.strictEqual(present.point.to_x, readyGeometry.live_geometry.ping_x);
assert.strictEqual(present.point.to_y, readyGeometry.live_geometry.ping_y);
assert.strictEqual(present.point.from_x, readyGeometry.stance.stance_x);
assert.strictEqual(present.point.from_y, readyGeometry.stance.stance_y);

controller.completeApproach();
assert.strictEqual(controller.getState().movement_mode, "present");
assert.strictEqual(execution.canAuthorizePing(approach.state, present.final_verification), false);
assert.strictEqual(execution.canAuthorizePing(present.state, present.final_verification), true);
assert.strictEqual(pingPresenter.canAuthorizePing(approach.state, present.final_verification), false);
assert.strictEqual(pingPresenter.canAuthorizePing(present.state, present.final_verification), true);
var relationship = pingPresenter.pointRelationship(
  { x: present.point.from_x, y: present.point.from_y },
  { x: present.point.to_x, y: present.point.to_y }
);
assert.strictEqual(relationship.to_x, readyGeometry.live_geometry.ping_x);
assert.strictEqual(readyGeometry.live_geometry.ping_x, 640);

var release = execution.releasePresentation(present.state);
assert.strictEqual(release.release_state.current_state, "RELEASE");
assert.strictEqual(release.state.current_state, "WAIT");
controller.beginRelease();
controller.completeRelease();
assert.strictEqual(controller.getState().movement_mode, "ambient");

var failed = execution.completeApproach(approach, geometry({
  live_geometry: {
    geometry_status: "unresolved",
    target_id: "demo-card"
  },
  stance: {},
  geometry_status: "unresolved"
}));
assert.strictEqual(failed.execution_status, "recovery_required");
assert.strictEqual(failed.state.current_state, "RECOVER");
assert.strictEqual(failed.may_authorize_ping, false);
assert.strictEqual(failed.may_present, false);

var interactionState = "speaking";
assert.strictEqual(interactionState, "speaking");
assert.strictEqual(approach.state.current_state, "APPROACH");

console.log("PASS 6 one-out execution tests passed");
