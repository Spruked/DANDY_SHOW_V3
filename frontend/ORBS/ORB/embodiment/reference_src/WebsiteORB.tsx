import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Orb } from "./OrbVisual";
import { WebsiteOrbApi, type AnswerResponse, type RouteContextResponse } from "./api";
import type { PlotRecord } from "./pointer/pointerPlotTypes";
import { resolveTarget } from "./pointer/pointerResolution";
import "./WebsiteORB.css";

type Props = {
  apiBase?: string;
  size?: number;
};

type Position = {
  x: number;
  y: number;
};

const EDGE = 8;
const CURSOR_SAFE_RADIUS = 180;

export const WebsiteORB: React.FC<Props> = ({ apiBase = "", size = 164 }) => {
  const api = useMemo(() => new WebsiteOrbApi(apiBase), [apiBase]);
  const orbRef = useRef<HTMLDivElement | null>(null);
  const cursorRef = useRef<Position | null>(null);
  const posRef = useRef<Position>({ x: EDGE, y: EDGE });
  const targetRef = useRef<Position>({ x: EDGE, y: EDGE });
  const routeRef = useRef(window.location.pathname || "/");
  const [position, setPosition] = useState<Position>({ x: EDGE, y: EDGE });
  const [routeContext, setRouteContext] = useState<RouteContextResponse | null>(null);
  const [message, setMessage] = useState("");
  const [answer, setAnswer] = useState("Tap or ask. I know where I am on Orb Weaver.");
  const [state, setState] = useState<"idle" | "listening" | "speaking">("idle");
  const [resolvedTarget, setResolvedTarget] = useState<Element | null>(null);

  const clamp = useCallback(
    (next: Position): Position => ({
      x: Math.max(EDGE, Math.min(next.x, window.innerWidth - size - EDGE)),
      y: Math.max(EDGE, Math.min(next.y, window.innerHeight - size - EDGE)),
    }),
    [size],
  );

  const chooseDestination = useCallback(() => {
    const current = posRef.current;
    let candidate = current;
    for (let i = 0; i < 35; i += 1) {
      const next = clamp({
        x: EDGE + Math.random() * Math.max(1, window.innerWidth - size - EDGE * 2),
        y: EDGE + Math.random() * Math.max(1, window.innerHeight - size - EDGE * 2),
      });
      const cursor = cursorRef.current;
      const cursorDistance = cursor
        ? Math.hypot(next.x + size / 2 - cursor.x, next.y + size / 2 - cursor.y)
        : Number.POSITIVE_INFINITY;
      const travel = Math.hypot(next.x - current.x, next.y - current.y);
      if (cursorDistance > CURSOR_SAFE_RADIUS && travel > Math.min(420, window.innerWidth * 0.3)) {
        candidate = next;
        break;
      }
    }
    targetRef.current = candidate;
  }, [clamp, size]);

  useEffect(() => {
    chooseDestination();
    let frame = 0;
    let lastDestinationAt = performance.now();

    const tick = (now: number) => {
      const cursor = cursorRef.current;
      let target = targetRef.current;
      if (cursor) {
        const distance = Math.hypot(posRef.current.x + size / 2 - cursor.x, posRef.current.y + size / 2 - cursor.y);
        if (distance < CURSOR_SAFE_RADIUS) {
          target = clamp({
            x: posRef.current.x + (posRef.current.x + size / 2 - cursor.x) * 0.9,
            y: posRef.current.y + (posRef.current.y + size / 2 - cursor.y) * 0.9,
          });
          targetRef.current = target;
        }
      }

      if (now - lastDestinationAt > 2200 + Math.random() * 2800) {
        chooseDestination();
        lastDestinationAt = now;
      }

      const current = posRef.current;
      const next = clamp({
        x: current.x + (target.x - current.x) * 0.022,
        y: current.y + (target.y - current.y) * 0.022,
      });
      posRef.current = next;
      setPosition(next);
      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [chooseDestination, clamp, size]);

  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      cursorRef.current = { x: event.clientX, y: event.clientY };
    };
    window.addEventListener("pointermove", onPointer, { passive: true });
    return () => window.removeEventListener("pointermove", onPointer);
  }, []);

  const refreshRoute = useCallback(async () => {
    const route = window.location.pathname || "/";
    if (route === routeRef.current && routeContext) return;
    routeRef.current = route;
    const context = await api.routeContext(route);
    setRouteContext(context);
  }, [api, routeContext]);

  useEffect(() => {
    void refreshRoute().catch(() => undefined);
    const timer = window.setInterval(() => void refreshRoute().catch(() => undefined), 1200);
    return () => window.clearInterval(timer);
  }, [refreshRoute]);

  const submit = useCallback(async () => {
    const trimmed = message.trim();
    if (!trimmed) return;
    setState("speaking");
    setResolvedTarget(null);
    try {
      const response = await api.answerText(trimmed, routeRef.current);
      setAnswer(response.answer);
      await resolveBestPointer(response);
    } catch {
      setAnswer("I am here, but the Website ORB runtime is unavailable.");
    } finally {
      setMessage("");
      window.setTimeout(() => setState("idle"), 1200);
    }
  }, [api, message]);

  const resolveBestPointer = async (response: AnswerResponse) => {
    const record = response.pointer_targets[0] as unknown as PlotRecord | undefined;
    if (!record) return;
    const result = await resolveTarget(record);
    if (result.status === "resolved" && result.target?.element && result.target.onScreen) {
      setResolvedTarget(result.target.element);
      result.target.element.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
      window.setTimeout(() => setResolvedTarget(null), 1800);
    }
  };

  useEffect(() => {
    if (!resolvedTarget) return;
    resolvedTarget.classList.add("website-orb-pointer-ping");
    return () => resolvedTarget.classList.remove("website-orb-pointer-ping");
  }, [resolvedTarget]);

  return (
    <div
      ref={orbRef}
      className="website-orb-root"
      style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
    >
      <Orb size={size} state={state} onClick={() => setState((current) => (current === "listening" ? "idle" : "listening"))} />
      <form
        className="website-orb-panel"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="website-orb-answer">{answer}</div>
        <div className="website-orb-route">{routeContext?.matched_route || routeRef.current}</div>
        <div className="website-orb-row">
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Ask Weaver"
            aria-label="Ask Weaver"
          />
          <button type="submit">Ask</button>
        </div>
      </form>
    </div>
  );
};

export default WebsiteORB;

