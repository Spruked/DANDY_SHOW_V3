(function () {
  "use strict";

  var DEFAULT_RUNTIME = {
    display_name: "Web Weaver",
    orb_name: "Web Weaver",
    default_prompt: "Ask Web Weaver",
    default_answer: "Tap or ask. I know where I am on this site.",
    offline_answer: "I am here, but the Web Weaver runtime is unavailable.",
    size: 164,
    asset_base_path: "./ASSETS",
    skin_path: "./ASSETS/orb/webweaver-orb.png",
    movement: {
      edge_px: 8,
      cursor_safe_radius_px: 180
    }
  };

  var DEFAULT_ENDPOINTS = {
    api_base_url: "",
    route_context_path: "/orb/route-context",
    answer_text_path: "/orb/answer-text"
  };

  var DEFAULT_SITE = {
    display_name: "Web Weaver",
    site_name: "Web Weaver Development Site",
    identity: {
      name: "Web Weaver",
      role: "embodied site host"
    }
  };

  function scriptDirectory() {
    var script = document.currentScript || document.querySelector("script[data-web-weaver-bootstrap]");
    if (!script || !script.src) return "./BROWSER/";
    return new URL(".", script.src).toString();
  }

  function packageBaseFromBrowserDir(browserDir) {
    return new URL("../", browserDir).toString();
  }

  function resolveUrl(path, base) {
    if (!path) return "";
    return new URL(path, base || window.location.href).toString();
  }

  function merge(base, override) {
    var out = {};
    Object.keys(base || {}).forEach(function (key) {
      out[key] = base[key];
    });
    Object.keys(override || {}).forEach(function (key) {
      if (
        override[key] &&
        typeof override[key] === "object" &&
        !Array.isArray(override[key]) &&
        base[key] &&
        typeof base[key] === "object" &&
        !Array.isArray(base[key])
      ) {
        out[key] = merge(base[key], override[key]);
      } else {
        out[key] = override[key];
      }
    });
    return out;
  }

  function fetchJson(path, base) {
    return fetch(resolveUrl(path, base), { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error("config fetch failed: " + response.status);
      return response.json();
    });
  }

  function loadConfig(options) {
    options = options || {};
    var browserDir = options.browserBase || scriptDirectory();
    var packageBase = options.packageBase || packageBaseFromBrowserDir(browserDir);
    var runtimePath = options.runtimeConfig || "CONFIG/runtime.json";
    var endpointsPath = options.endpointsConfig || "CONFIG/endpoints.json";
    var sitePath = options.siteConfig || "SITE/site_config.json";
    var soundPath = options.soundProfile || "SITE/sound_profile.json";

    return Promise.all([
      fetchJson(runtimePath, packageBase).catch(function () { return {}; }),
      fetchJson(endpointsPath, packageBase).catch(function () { return {}; }),
      fetchJson(sitePath, packageBase).catch(function () { return {}; }),
      fetchJson(soundPath, packageBase).catch(function () { return {}; })
    ]).then(function (parts) {
      return {
        packageBase: packageBase,
        browserBase: browserDir,
        runtime: merge(DEFAULT_RUNTIME, parts[0]),
        endpoints: merge(DEFAULT_ENDPOINTS, parts[1]),
        site: merge(DEFAULT_SITE, parts[2]),
        sound: parts[3]
      };
    });
  }

  function createApi(config) {
    var endpoints = config.endpoints;
    var apiBase = endpoints.api_base_url || "";

    function apiUrl(path) {
      if (!apiBase) return path;
      return apiBase.replace(/\/$/, "") + path;
    }

    return {
      apiBase: apiBase,
      routeContext: function (route) {
        var path = endpoints.route_context_path + "?route=" + encodeURIComponent(route);
        return fetch(apiUrl(path)).then(function (response) {
          if (!response.ok) throw new Error("route context failed: " + response.status);
          return response.json();
        });
      },
      answerText: function (message, route) {
        return fetch(apiUrl(endpoints.answer_text_path), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: message, route: route, want_pointer: true })
        }).then(function (response) {
          if (!response.ok) throw new Error("answer failed: " + response.status);
          return response.json();
        });
      }
    };
  }

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function queryElements(selector) {
    if (!selector) return [];
    try {
      return Array.prototype.slice.call(document.querySelectorAll(selector));
    } catch (_error) {
      return [];
    }
  }

  function elementMatchesRecord(element, record) {
    var expectedTag = String((record.structural_context || {}).tag || "").toLowerCase();
    if (expectedTag && element.tagName.toLowerCase() !== expectedTag) return false;
    var text = normalizeText(element.textContent || element.getAttribute("aria-label") || "");
    var meaningText = String(record.meaning || "").replace(/^[^:]+:\s*/, "");
    var aliases = record.direct_aliases || record.intent_aliases || [];
    var fragments = [meaningText].concat(aliases).map(function (item) {
      return normalizeText(item).slice(0, 120);
    }).filter(function (item) {
      return item.length >= 2;
    });
    return !fragments.length || fragments.some(function (fragment) {
      return text.indexOf(fragment) !== -1 || fragment.indexOf(text) !== -1;
    });
  }

  function resolveTarget(record) {
    var parent = String(((record || {}).structural_context || {}).parent_locator || "").trim();
    var child = String((record || {}).semantic_locator || "").trim();
    var scoped = parent ? parent + " " + child : child;
    var candidates = queryElements(scoped).concat(queryElements(child));

    for (var i = 0; i < candidates.length; i += 1) {
      if (elementMatchesRecord(candidates[i], record)) {
        var rect = candidates[i].getBoundingClientRect();
        return {
          element: candidates[i],
          onScreen: rect.top >= 0 && rect.bottom <= (window.innerHeight || document.documentElement.clientHeight)
        };
      }
    }
    return null;
  }

  function mount(container, options) {
    options = options || {};
    var host = container || document.body;
    return loadConfig(options).then(function (config) {
      var runtime = config.runtime;
      var site = config.site;
      var api = createApi(config);
      var edge = Number((runtime.movement || {}).edge_px || 8);
      var cursorSafeRadius = Number((runtime.movement || {}).cursor_safe_radius_px || 180);
      var size = Number(options.size || runtime.size || 164);
      var skinPath = resolveUrl(runtime.skin_path, config.packageBase);
      var tamp = window.WebWeaverTamp || null;
      var decisionAdapter = window.WebWeaverTampDecisionAdapter || null;
      var geometryRuntime = window.WebWeaverGeometryRuntime || null;
      var oneOutExecution = window.WebWeaverOneOutExecution || null;
      var movementControllerFactory = window.WebWeaverMovementController || null;
      var pingPresenter = window.WebWeaverPingPresenter || null;
      var morbPointerActuator = window.WebWeaverMorbPointerActuator || null;
      var soundPack = window.WebWeaverSoundPack || null;
      var soundPlayer = soundPack ? soundPack.createSoundPlayer(config.sound || {}, config.packageBase) : null;
      var tampState = tamp ? tamp.createState() : null;
      var state = "idle";
      var route = window.location.pathname || "/";
      var pos = { x: edge, y: edge };
      var target = { x: edge, y: edge };
      var cursor = null;
      var frame = 0;
      var lastDestinationAt = performance.now();
      var movementController = movementControllerFactory ? movementControllerFactory.createController(pos) : null;
      var lastExecution = null;

      var root = document.createElement("div");
      root.className = "website-orb-root";
      root.setAttribute("data-web-weaver-root", "true");
      if (tampState) root.setAttribute("data-tamp-state", tampState.current_state);

      var orb = document.createElement("button");
      orb.type = "button";
      orb.className = "ow-v2-orb-body idle has-image-skin";
      orb.style.width = size + "px";
      orb.style.height = size + "px";
      orb.setAttribute("aria-label", (site.display_name || runtime.display_name) + " intelligence orb");

      var halo = document.createElement("div");
      halo.className = "ow-v2-orb-halo";
      var img = document.createElement("img");
      img.className = "ow-v2-orb-skin-image";
      img.src = skinPath;
      img.alt = "";
      img.draggable = false;
      var eye = document.createElement("div");
      eye.className = "ow-v2-orb-eye-pulse";
      var specular = document.createElement("div");
      specular.className = "ow-v2-orb-specular";
      orb.append(halo, img, eye, specular);

      var form = document.createElement("form");
      form.className = "website-orb-panel";
      var answer = document.createElement("div");
      answer.className = "website-orb-answer";
      answer.textContent = runtime.default_answer;
      var routeLabel = document.createElement("div");
      routeLabel.className = "website-orb-route";
      routeLabel.textContent = route;
      var row = document.createElement("div");
      row.className = "website-orb-row";
      var input = document.createElement("input");
      input.placeholder = runtime.default_prompt || ("Ask " + (site.display_name || runtime.display_name));
      input.setAttribute("aria-label", input.placeholder);
      var submit = document.createElement("button");
      submit.type = "submit";
      submit.textContent = "Ask";
      row.append(input, submit);
      form.append(answer, routeLabel, row);
      root.append(orb, form);
      host.appendChild(root);

      function setState(next) {
        state = next;
        orb.className = "ow-v2-orb-body " + state + " has-image-skin";
      }

      function writeOrbPosition(next, writer) {
        pos = { x: next.x, y: next.y };
        if (movementController) {
          movementController.writePosition(pos, writer || "ambient");
        }
        root.style.transform = "translate3d(" + pos.x + "px, " + pos.y + "px, 0)";
      }

      function applyTampDecision(decision) {
        if (!decisionAdapter) {
          throw new Error("Web Weaver TAMP decision adapter is not loaded");
        }
        var result = decisionAdapter.applyDecision(tampState || (tamp && tamp.createState()), decision);
        tampState = result.state;
        if (tampState) root.setAttribute("data-tamp-state", tampState.current_state);
        return result;
      }

      function resolveTampGeometry(targetRecord, geometryOptions) {
        if (!geometryRuntime) {
          throw new Error("Web Weaver geometry runtime is not loaded");
        }
        var result = geometryRuntime.evaluateGeometry(tampState || (tamp && tamp.createState()), targetRecord, merge({
          window: window,
          document: document
        }, geometryOptions || {}));
        tampState = result.state;
        if (tampState) root.setAttribute("data-tamp-state", tampState.current_state);
        return result;
      }

      function clamp(next) {
        return {
          x: Math.max(edge, Math.min(next.x, window.innerWidth - size - edge)),
          y: Math.max(edge, Math.min(next.y, window.innerHeight - size - edge))
        };
      }

      function chooseDestination() {
        var candidate = pos;
        for (var i = 0; i < 35; i += 1) {
          var next = clamp({
            x: edge + Math.random() * Math.max(1, window.innerWidth - size - edge * 2),
            y: edge + Math.random() * Math.max(1, window.innerHeight - size - edge * 2)
          });
          var cursorDistance = cursor
            ? Math.hypot(next.x + size / 2 - cursor.x, next.y + size / 2 - cursor.y)
            : Number.POSITIVE_INFINITY;
          var travel = Math.hypot(next.x - pos.x, next.y - pos.y);
          if (cursorDistance > cursorSafeRadius && travel > Math.min(420, window.innerWidth * 0.3)) {
            candidate = next;
            break;
          }
        }
        target = candidate;
      }

      function tick(now) {
        if (movementController && movementController.getState().movement_mode !== "ambient") {
          frame = requestAnimationFrame(tick);
          return;
        }
        var activeTarget = target;
        if (cursor) {
          var distance = Math.hypot(pos.x + size / 2 - cursor.x, pos.y + size / 2 - cursor.y);
          if (distance < cursorSafeRadius) {
            activeTarget = clamp({
              x: pos.x + (pos.x + size / 2 - cursor.x) * 0.9,
              y: pos.y + (pos.y + size / 2 - cursor.y) * 0.9
            });
            target = activeTarget;
          }
        }
        if (now - lastDestinationAt > 2200 + Math.random() * 2800) {
          chooseDestination();
          lastDestinationAt = now;
        }
        writeOrbPosition(clamp({
          x: pos.x + (activeTarget.x - pos.x) * 0.022,
          y: pos.y + (activeTarget.y - pos.y) * 0.022
        }), "ambient");
        frame = requestAnimationFrame(tick);
      }

      function animateApproach(approachResult) {
        return new Promise(function (resolve) {
          var startAt = performance.now();
          function step(now) {
            var elapsed = now - startAt;
            var update = movementController.updateApproach(elapsed);
            if (update.updated) {
              pos = update.position;
              root.style.transform = "translate3d(" + pos.x + "px, " + pos.y + "px, 0)";
            }
            if (update.sample && update.sample.complete) {
              resolve(update);
              return;
            }
            requestAnimationFrame(step);
          }
          requestAnimationFrame(step);
        });
      }

      function executeOneOut(targetRecord, executionOptions) {
        executionOptions = executionOptions || {};
        if (!oneOutExecution || !movementController || !pingPresenter) {
          throw new Error("Web Weaver PASS 6 execution modules are not loaded");
        }
        var geometry = resolveTampGeometry(targetRecord, executionOptions.geometry || {});
        var approach = oneOutExecution.beginApproach(tampState, geometry, { x: pos.x, y: pos.y }, executionOptions.glide || {});
        tampState = approach.state;
        if (tampState) root.setAttribute("data-tamp-state", tampState.current_state);
        lastExecution = {
          initial_geometry: geometry,
          approach: approach,
          start_position: { x: pos.x, y: pos.y }
        };
        if (approach.execution_status !== "approach") {
          return Promise.resolve(lastExecution);
        }
        movementController.beginApproach(approach);
        return animateApproach(approach).then(function (arrival) {
          var finalGeometry = resolveTampGeometry(targetRecord, executionOptions.geometry || {});
          var completed = oneOutExecution.completeApproach(approach, finalGeometry);
          tampState = completed.state;
          if (tampState) root.setAttribute("data-tamp-state", tampState.current_state);
          lastExecution.arrival = arrival;
          lastExecution.final_geometry = finalGeometry;
          lastExecution.completed = completed;
          if (completed.execution_status !== "present") {
            movementController.beginRelease();
            return lastExecution;
          }
          movementController.completeApproach();
          var point = pingPresenter.pointRelationship(
            { x: completed.point.from_x, y: completed.point.from_y },
            { x: completed.point.to_x, y: completed.point.to_y }
          );
          var pingResult = { shown: false, reason: "not_authorized" };
          if (pingPresenter.canAuthorizePing(tampState, completed.final_verification)) {
            pingResult = pingPresenter.showPing(window, { x: point.to_x, y: point.to_y }, executionOptions.ping || {});
          }
          lastExecution.point = point;
          lastExecution.ping = pingResult;
          movementController.beginRelease();
          return new Promise(function (resolve) {
            window.setTimeout(function () {
              var released = oneOutExecution.releasePresentation(tampState);
              tampState = released.state;
              if (tampState) root.setAttribute("data-tamp-state", tampState.current_state);
              movementController.completeRelease();
              lastExecution.release = released;
              resolve(lastExecution);
            }, Number((executionOptions.glide || {}).release_delay_ms || oneOutExecution.DEFAULT_GLIDE.release_delay_ms));
          });
        });
      }

      function executeMorbPointer(targetRecord, executionOptions) {
        executionOptions = executionOptions || {};
        if (!morbPointerActuator || !oneOutExecution || !pingPresenter) {
          throw new Error("Web Weaver MORB pointer modules are not loaded");
        }
        var geometry = resolveTampGeometry(targetRecord, executionOptions.geometry || {});
        var lock = oneOutExecution.createTwoInLock(tampState, geometry);
        if (!lock.valid) {
          return Promise.resolve({
            execution_status: "rejected",
            reason: !lock.authority_lock.valid ? "authority_lock_invalid" : "physical_lock_invalid",
            two_in_lock: lock,
            may_authorize_ping: false
          });
        }
        var presentState = tamp.transition(tampState, "APPROACH", {
          reason: "morb_pointer_launch",
          target_id: lock.authority_lock.target_id,
          action_id: lock.authority_lock.action_id,
          verification: tampState.verification
        });
        tampState = presentState;
        root.setAttribute("data-tamp-state", tampState.current_state);
        var orbRect = root.getBoundingClientRect();
        var launch = {
          x: orbRect.left + orbRect.width / 2,
          y: orbRect.top + orbRect.height / 2
        };
        var activeMorb = morbPointerActuator.createMorb({
          parent_orb_id: "web-weaver-orb",
          target_id: lock.authority_lock.target_id,
          action_id: lock.authority_lock.action_id,
          launch_x: launch.x,
          launch_y: launch.y,
          ping_x: lock.physical_lock.ping_x,
          ping_y: lock.physical_lock.ping_y,
          geometry_version: lock.physical_lock.geometry_version,
          payload: executionOptions.payload || { type: "pointer_only" },
          sound_profile: executionOptions.sound_profile || "web_weaver_signature"
        });
        var marker = document.createElement("div");
        marker.className = "website-morb-pointer";
        marker.setAttribute("data-web-weaver-morb", activeMorb.morb_id);
        marker.style.position = "fixed";
        marker.style.left = activeMorb.launch_x + "px";
        marker.style.top = activeMorb.launch_y + "px";
        marker.style.width = activeMorb.visual.rendered_width_px + "px";
        marker.style.height = activeMorb.visual.rendered_height_px + "px";
        marker.style.marginLeft = -(activeMorb.visual.rendered_width_px / 2) + "px";
        marker.style.marginTop = -(activeMorb.visual.rendered_height_px / 2) + "px";
        marker.style.borderRadius = "50%";
        marker.style.backgroundImage = "url('" + resolveUrl(activeMorb.visual.asset_path, config.packageBase) + "')";
        marker.style.backgroundRepeat = "no-repeat";
        marker.style.backgroundPosition = "center";
        marker.style.backgroundSize = "contain";
        marker.style.filter = "drop-shadow(0 0 10px rgba(220, 20, 32, 0.72)) drop-shadow(0 0 14px rgba(20, 12, 12, 0.72))";
        marker.style.pointerEvents = "none";
        marker.style.zIndex = "2147483646";
        marker.setAttribute("data-sound-event-launch", "MORB_LAUNCH");
        marker.setAttribute("data-sound-event-flight", "MORB_FLIGHT");
        marker.setAttribute("data-sound-event-arrive", "MORB_ARRIVE");
        marker.setAttribute("data-sound-event-confirm", "MORB_CONFIRM");
        marker.setAttribute("data-sound-event-abort", "MORB_ABORT");
        document.body.appendChild(marker);
        activeMorb = morbPointerActuator.transition(activeMorb, "LAUNCHED", "spawned_from_parent");
        if (soundPlayer) soundPlayer.playEvent("MORB_LAUNCH");
        activeMorb = morbPointerActuator.transition(activeMorb, "IN_FLIGHT", "flight_started");
        if (soundPlayer) soundPlayer.playEvent("MORB_FLIGHT");
        var plan = morbPointerActuator.planFlight(activeMorb, executionOptions.flight || {});
        var startedAt = performance.now();
        return new Promise(function (resolve) {
          function step(now) {
            var sample = morbPointerActuator.sampleFlight(plan, now - startedAt);
            marker.style.left = sample.x + "px";
            marker.style.top = sample.y + "px";
            if (!sample.complete) {
              requestAnimationFrame(step);
              return;
            }
            var finalGeometry = resolveTampGeometry(targetRecord, executionOptions.geometry || {});
            var finalVerification = morbPointerActuator.finalCheck(activeMorb, finalGeometry);
            if (finalVerification.valid) {
              tampState = tamp.transition(tampState, "PRESENT", {
                reason: "morb_arrival_final_verified",
                target_id: lock.authority_lock.target_id,
                action_id: lock.authority_lock.action_id,
                verification: tampState.verification
              });
              root.setAttribute("data-tamp-state", tampState.current_state);
            } else {
              tampState = tamp.transition(tampState, "RECOVER", {
                reason: "morb_final_verification_failed",
                target_id: lock.authority_lock.target_id,
                action_id: lock.authority_lock.action_id,
                verification: tampState.verification
              });
              root.setAttribute("data-tamp-state", tampState.current_state);
            }
            var completed = morbPointerActuator.completeAtTarget(activeMorb, tampState, finalVerification);
            var pingResult = { shown: false, reason: "not_authorized" };
            if (completed.state === "COMPLETE" && pingPresenter.canAuthorizePing(tampState, finalVerification)) {
              if (soundPlayer) soundPlayer.playEvent("MORB_ARRIVE");
              pingResult = pingPresenter.showPing(window, { x: activeMorb.ping_x, y: activeMorb.ping_y }, executionOptions.ping || {});
              if (activeMorb.payload && activeMorb.payload.type && activeMorb.payload.type !== "pointer_only" && soundPlayer) {
                soundPlayer.playEvent("MORB_CONFIRM");
              }
            } else if (soundPlayer) {
              soundPlayer.playEvent("MORB_ABORT");
            }
            marker.remove();
            if (completed.state === "COMPLETE") {
              var released = oneOutExecution.releasePresentation(tampState);
              tampState = released.state;
              root.setAttribute("data-tamp-state", tampState.current_state);
            }
            resolve({
              execution_status: completed.state === "COMPLETE" ? "complete" : "aborted",
              morb: completed,
              launch: launch,
              flight_plan: plan,
              final_verification: finalVerification,
              final_geometry: finalGeometry,
              ping: pingResult,
              state: tampState,
              may_authorize_ping: pingResult.shown === true
            });
          }
          requestAnimationFrame(step);
        });
      }

      function refreshRoute() {
        route = window.location.pathname || "/";
        routeLabel.textContent = route;
        api.routeContext(route).then(function (context) {
          routeLabel.textContent = context.matched_route || route;
        }).catch(function () {
          routeLabel.textContent = route;
        });
      }

      function pingTarget(record) {
        var resolved = resolveTarget(record);
        if (!resolved || !resolved.element || !resolved.onScreen) return;
        resolved.element.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
        resolved.element.classList.add("website-orb-pointer-ping");
        window.setTimeout(function () {
          resolved.element.classList.remove("website-orb-pointer-ping");
        }, 1800);
      }

      window.addEventListener("pointermove", function (event) {
        cursor = { x: event.clientX, y: event.clientY };
      }, { passive: true });

      orb.addEventListener("click", function () {
        setState(state === "listening" ? "idle" : "listening");
      });

      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var message = input.value.trim();
        if (!message) return;
        setState("speaking");
        api.answerText(message, route).then(function (response) {
          answer.textContent = response.answer || runtime.default_answer;
          if (response.pointer_targets && response.pointer_targets[0]) {
            pingTarget(response.pointer_targets[0]);
          }
        }).catch(function () {
          answer.textContent = runtime.offline_answer;
        }).finally(function () {
          input.value = "";
          window.setTimeout(function () { setState("idle"); }, 1200);
        });
      });

      chooseDestination();
      refreshRoute();
      frame = requestAnimationFrame(tick);
      var routeTimer = window.setInterval(refreshRoute, 1200);

      var instance = {
        root: root,
        config: config,
        apiBaseUrl: api.apiBase,
        skinPath: skinPath,
        getInteractionState: function () {
          return state;
        },
        getTampState: function () {
          return tampState;
        },
        applyTampDecision: applyTampDecision,
        resolveTampGeometry: resolveTampGeometry,
        executeOneOut: executeOneOut,
        executeMorbPointer: executeMorbPointer,
        getMovementState: function () {
          return movementController ? movementController.getState() : null;
        },
        getLastExecution: function () {
          return lastExecution;
        },
        tamp: tamp,
        tampDecisionAdapter: decisionAdapter,
        geometryRuntime: geometryRuntime,
        oneOutExecution: oneOutExecution,
        movementController: movementController,
        pingPresenter: pingPresenter,
        morbPointerActuator: morbPointerActuator,
        soundPlayer: soundPlayer,
        destroy: function () {
          cancelAnimationFrame(frame);
          window.clearInterval(routeTimer);
          root.remove();
        }
      };
      window.__WEB_WEAVER_INSTANCE__ = instance;
      return instance;
    });
  }

  window.WebWeaver = {
    loadConfig: loadConfig,
    mount: mount
  };
})();
