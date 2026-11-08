export type AnswerResponse = {
  answer: string;
  route: string;
  intent: string;
  action_class: string;
  pointer_targets: Array<Record<string, unknown>>;
  requires_confirmation: boolean;
  source: string;
};

export type RouteContextResponse = {
  route: string;
  matched_route: string;
  record: Record<string, unknown>;
  source: string;
};

export class WebsiteOrbApi {
  constructor(private apiBase = "") {}

  async routeContext(route: string): Promise<RouteContextResponse> {
    const response = await fetch(`${this.apiBase}/orb/route-context?route=${encodeURIComponent(route)}`);
    if (!response.ok) throw new Error(`route context failed: ${response.status}`);
    return response.json();
  }

  async answerText(message: string, route: string): Promise<AnswerResponse> {
    const response = await fetch(`${this.apiBase}/orb/answer-text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, route, want_pointer: true }),
    });
    if (!response.ok) throw new Error(`answer failed: ${response.status}`);
    return response.json();
  }
}

