(function (root, factory) {
  "use strict";

  var api = factory(
    typeof require === "function" ? require("./one_out_execution.js") : root.WebWeaverOneOutExecution
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverMovementController = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (execution) {
  "use strict";

  var MODES = Object.freeze(["ambient", "approach", "present", "release"]);

  function createController(initialPosition) {
    var position = initialPosition || { x: 0, y: 0 };
    var mode = "ambient";
    var owner = "ambient";
    var activePlan = null;
    var writes = [];

    function setMode(nextMode, nextOwner) {
      if (MODES.indexOf(nextMode) === -1) {
        throw new Error("Unknown movement mode: " + nextMode);
      }
      mode = nextMode;
      owner = nextOwner || (nextMode === "ambient" ? "ambient" : "tamp_choreography");
      return getState();
    }

    function writePosition(nextPosition, writer) {
      if (mode !== "ambient" && writer !== owner) {
        throw new Error("Movement ownership violation: " + writer + " cannot write during " + mode);
      }
      position = { x: nextPosition.x, y: nextPosition.y };
      writes.push({ writer: writer, mode: mode, x: position.x, y: position.y });
      return position;
    }

    function beginApproach(approachResult) {
      if (!approachResult || approachResult.execution_status !== "approach") {
        throw new Error("Approach result required");
      }
      activePlan = approachResult.glide_plan;
      setMode("approach", approachResult.owner || "tamp_choreography");
      return getState();
    }

    function updateApproach(elapsedMs) {
      if (mode !== "approach" || !activePlan) {
        return { updated: false, reason: "not_approaching", position: position };
      }
      var sample = execution.sampleGlide(activePlan, elapsedMs);
      writePosition({ x: sample.x, y: sample.y }, owner);
      return {
        updated: true,
        position: position,
        sample: sample
      };
    }

    function completeApproach() {
      setMode("present", "tamp_choreography");
      activePlan = null;
      return getState();
    }

    function beginRelease() {
      setMode("release", "tamp_choreography");
      return getState();
    }

    function completeRelease() {
      activePlan = null;
      setMode("ambient", "ambient");
      return getState();
    }

    function getState() {
      return {
        movement_mode: mode,
        owner: owner,
        position: { x: position.x, y: position.y },
        active_plan: activePlan,
        writes: writes.slice()
      };
    }

    return {
      beginApproach: beginApproach,
      beginRelease: beginRelease,
      completeApproach: completeApproach,
      completeRelease: completeRelease,
      getState: getState,
      setMode: setMode,
      updateApproach: updateApproach,
      writePosition: writePosition
    };
  }

  return Object.freeze({
    MODES: MODES,
    createController: createController
  });
});
