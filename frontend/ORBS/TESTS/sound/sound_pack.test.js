"use strict";

var assert = require("assert");
var sound = require("../../POINTER/sound/sound_pack.js");
var profile = require("../../SITE/sound_profile.json");

assert.strictEqual(profile.default_volume, 0.5);
assert.strictEqual(profile.voice_relative_volume, 0.5);
["MORB_LAUNCH", "MORB_FLIGHT", "MORB_ARRIVE", "MORB_CONFIRM", "MORB_ABORT"].forEach(function (eventName) {
  var event = sound.getEvent(profile, eventName);
  assert.ok(event, eventName + " is configured");
  assert.strictEqual(event.asset, "ASSETS/sounds/morb/morb-deployment-source.mp3");
  assert.ok(event.volume <= 0.5);
  assert.ok(event.duration_seconds > 0);
});

var fakeCalls = [];
function FakeAudio(src) {
  this.src = src;
  this.volume = 1;
  this.currentTime = 0;
  this.play = function () {
    fakeCalls.push({ src: this.src, volume: this.volume, currentTime: this.currentTime });
    return Promise.resolve();
  };
  this.pause = function () {};
}

var player = sound.createSoundPlayer(profile, "http://example.test/", { Audio: FakeAudio });
player.playEvent("MORB_LAUNCH").then(function (result) {
  assert.strictEqual(result.played, true);
  assert.strictEqual(result.volume, 0.5);
  assert.ok(fakeCalls[0].src.indexOf("/ASSETS/sounds/morb/morb-deployment-source.mp3") !== -1);
  console.log("Sound pack tests passed");
}).catch(function (error) {
  console.error(error);
  process.exit(1);
});
