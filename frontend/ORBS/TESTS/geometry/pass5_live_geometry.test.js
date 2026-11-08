"use strict";

var assert = require("assert");
var jsdom = require("C:/Users/bryan/Downloads/qwen-code-main/qwen-code-main/node_modules/jsdom");
var JSDOM = jsdom.JSDOM;
var tamp = require("../../TAMP/states/tamp_state_model.js");
var adapter = require("../../TAMP/intent/tamp_decision_adapter.js");
var runtime = require("../../TAMP/geometry/geometry_runtime.js");
var stance = require("../../TAMP/geometry/relational_stance.js");

function makeDom(rect) {
  var dom = new JSDOM('<!doctype html><main><section id="pricing" data-orb-target="pricing-professional"><h2>Professional Pricing</h2></section></main>', {
    pretendToBeVisual: true
  });
  dom.window.innerWidth = 1000;
  dom.window.innerHeight = 720;
  var target = dom.window.document.querySelector("#pricing");
  target.getBoundingClientRect = function () {
    return {
      left: rect.left,
      top: rect.top,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      width: rect.width,
      height: rect.height
    };
  };
  return dom;
}

function acquireState(targetId) {
  var decision = adapter.applyDecision(tamp.createState(), {
    classification_source: "sf_orb",
    classification_status: "verified",
    intent_id: "show_pricing_professional",
    governor_status: "approved",
    action_id: "show_plan",
    legal_action: true,
    candidate_targets: [{ target_id: targetId }]
  });
  assert.strictEqual(decision.state.current_state, "ACQUIRE");
  return decision.state;
}

function targetRecord(overrides) {
  return Object.assign({
    target_id: "pricing-professional",
    semantic_locator: "#pricing",
    anchor_strategy: "element_center",
    meaning: "Professional Pricing",
    structural_context: { tag: "section" },
    confidence: 1
  }, overrides || {});
}

var acquired = acquireState("pricing-professional");
var dom = makeDom({ left: 620, top: 220, width: 180, height: 110 });
var result = runtime.evaluateGeometry(acquired, targetRecord(), {
  window: dom.window,
  document: dom.window.document,
  seed: "pass5-seed"
});

assert.strictEqual(result.state.current_state, "ACQUIRE");
assert.strictEqual(result.geometry_status, "ready");
assert.strictEqual(result.live_geometry.target_id, "pricing-professional");
assert.strictEqual(result.live_geometry.rect.left, 620);
assert.strictEqual(result.live_geometry.rect.top, 220);
assert.strictEqual(result.live_geometry.rect.right, 800);
assert.strictEqual(result.live_geometry.rect.bottom, 330);
assert.strictEqual(result.live_geometry.viewport.width, 1000);
assert.strictEqual(result.live_geometry.viewport.height, 720);
assert.strictEqual(result.live_geometry.ping_x, 710);
assert.strictEqual(result.live_geometry.ping_y, 275);
assert.strictEqual(result.may_authorize_ping, false);
assert.strictEqual(result.may_present, false);
assert.notStrictEqual(result.state.current_state, "PRESENT");

assert.strictEqual(result.stance.ping_x, result.live_geometry.ping_x);
assert.strictEqual(result.stance.ping_y, result.live_geometry.ping_y);
assert.notStrictEqual(result.stance.stance_x, result.stance.ping_x);
assert.notStrictEqual(result.stance.stance_y, result.stance.ping_y);
assert.ok(result.stance.n > 0);
assert.strictEqual(result.stance.direction, "left");
assert.ok(Math.abs(result.stance.variation_offset_px) <= result.stance.variation_limit_px);
assert.strictEqual(result.stance.may_authorize_ping, false);

function overlaps(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}
assert.strictEqual(overlaps(result.stance.orb_rect, result.live_geometry.rect), false);
assert.ok(result.stance.orb_rect.left >= 0);
assert.ok(result.stance.orb_rect.top >= 0);
assert.ok(result.stance.orb_rect.right <= result.live_geometry.viewport.width);
assert.ok(result.stance.orb_rect.bottom <= result.live_geometry.viewport.height);

var repeatA = runtime.evaluateGeometry(acquired, targetRecord(), {
  window: dom.window,
  document: dom.window.document,
  seed: "repeatable"
});
var repeatB = runtime.evaluateGeometry(acquired, targetRecord(), {
  window: dom.window,
  document: dom.window.document,
  seed: "repeatable"
});
assert.strictEqual(repeatA.stance.stance_x, repeatB.stance.stance_x);
assert.strictEqual(repeatA.stance.stance_y, repeatB.stance.stance_y);

var fallbackDom = makeDom({ left: 100, top: 220, width: 170, height: 90 });
var fallback = runtime.evaluateGeometry(acquired, targetRecord(), {
  window: fallbackDom.window,
  document: fallbackDom.window.document,
  seed: "fallback",
  stance_guidance: {
    preferred_direction: "left",
    fallback_directions: ["right", "below"],
    base_n: 220,
    variation_px: 0,
    minimum_clearance: 16,
    orb_width: 164,
    orb_height: 164
  }
});
assert.strictEqual(fallback.geometry_status, "ready");
assert.strictEqual(fallback.stance.direction, "right");
assert.strictEqual(fallback.stance.ping_x, fallback.live_geometry.ping_x);
assert.strictEqual(fallback.stance.ping_y, fallback.live_geometry.ping_y);
assert.ok(fallback.stance.rejected.some(function (entry) { return entry.direction === "left" && entry.reason === "outside_viewport"; }));

var movedDom = makeDom({ left: 430, top: 380, width: 180, height: 110 });
var moved = runtime.evaluateGeometry(acquired, targetRecord(), {
  window: movedDom.window,
  document: movedDom.window.document,
  seed: "pass5-seed"
});
assert.ok(moved.live_geometry.geometry_version > result.live_geometry.geometry_version);
assert.notStrictEqual(moved.live_geometry.ping_x, result.live_geometry.ping_x);
assert.notStrictEqual(moved.live_geometry.ping_y, result.live_geometry.ping_y);
assert.notStrictEqual(moved.stance.stance_x, result.stance.stance_x);
assert.notStrictEqual(moved.stance.stance_y, result.stance.stance_y);

var unresolvedDom = new JSDOM("<!doctype html><main></main>", { pretendToBeVisual: true });
unresolvedDom.window.innerWidth = 1000;
unresolvedDom.window.innerHeight = 720;
var searchResult = runtime.evaluateGeometry(acquired, targetRecord(), {
  window: unresolvedDom.window,
  document: unresolvedDom.window.document
});
assert.strictEqual(searchResult.state.current_state, "SEARCH");
assert.strictEqual(searchResult.reason, "target_geometry_unresolved");
assert.strictEqual(searchResult.target_id, "pricing-professional");

var mismatch = runtime.evaluateGeometry(acquired, targetRecord({ target_id: "other-target" }), {
  window: dom.window,
  document: dom.window.document
});
assert.strictEqual(mismatch.state.current_state, "ACQUIRE");
assert.strictEqual(mismatch.geometry_status, "target_identity_mismatch");
assert.notStrictEqual(mismatch.state.current_state, "SEARCH");

var rediscovered = runtime.evaluateGeometry(searchResult.state, targetRecord(), {
  window: dom.window,
  document: dom.window.document,
  seed: "rediscovered"
});
assert.strictEqual(rediscovered.state.current_state, "ACQUIRE");
assert.strictEqual(rediscovered.state.previous_state, "SEARCH");
assert.strictEqual(rediscovered.geometry_status, "ready");
assert.notStrictEqual(rediscovered.state.current_state, "APPROACH");
assert.notStrictEqual(rediscovered.state.current_state, "PRESENT");

var unknown = runtime.evaluateGeometry(tamp.createState({ current_state: "ACQUIRE" }), {}, {
  window: dom.window,
  document: dom.window.document
});
assert.strictEqual(unknown.state.current_state, "ACQUIRE");
assert.strictEqual(unknown.geometry_status, "no_target_identity");
assert.notStrictEqual(unknown.state.current_state, "SEARCH");

assert.throws(function () {
  tamp.transition(acquired, "PRESENT");
}, /Illegal TAMP transition: ACQUIRE -> PRESENT/);

console.log("PASS 5 live geometry tests passed");
