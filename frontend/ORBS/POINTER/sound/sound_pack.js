(function (root, factory) {
  "use strict";

  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.WebWeaverSoundPack = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function resolveUrl(path, base) {
    return new URL(path, base || (typeof window !== "undefined" ? window.location.href : "http://localhost/")).toString();
  }

  function getEvent(profile, eventName) {
    return profile && profile.events && profile.events[eventName] || null;
  }

  function createSoundPlayer(profile, packageBase, options) {
    options = options || {};
    var AudioCtor = options.Audio || (typeof Audio !== "undefined" ? Audio : null);

    function playEvent(eventName) {
      var event = getEvent(profile, eventName);
      if (!event) {
        return Promise.resolve({ played: false, event: eventName, reason: "event_not_configured" });
      }
      if (!AudioCtor) {
        return Promise.resolve({ played: false, event: eventName, reason: "audio_unavailable" });
      }

      var audio = new AudioCtor(resolveUrl(event.asset, packageBase));
      var volume = typeof event.volume === "number" ? event.volume : (profile.default_volume || 0.5);
      audio.volume = Math.max(0, Math.min(1, volume));
      audio.currentTime = Number(event.start_seconds || 0);
      var durationMs = Math.max(1, Number(event.duration_seconds || 0.3) * 1000);

      var stopTimer = null;
      var played = Promise.resolve(audio.play()).then(function () {
        stopTimer = setTimeout(function () {
          audio.pause();
          audio.currentTime = Number(event.start_seconds || 0);
        }, durationMs);
        return {
          played: true,
          event: eventName,
          asset: event.asset,
          start_seconds: Number(event.start_seconds || 0),
          duration_seconds: Number(event.duration_seconds || 0.3),
          volume: audio.volume
        };
      }).catch(function (error) {
        if (stopTimer) clearTimeout(stopTimer);
        return {
          played: false,
          event: eventName,
          reason: "play_rejected",
          message: error && error.message || String(error)
        };
      });
      return played;
    }

    return {
      getEvent: function (eventName) {
        return getEvent(profile, eventName);
      },
      playEvent: playEvent,
      profile: profile
    };
  }

  return Object.freeze({
    createSoundPlayer: createSoundPlayer,
    getEvent: getEvent
  });
});
