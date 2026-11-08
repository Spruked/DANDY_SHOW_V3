/**
 * Mirrors python/pointer_plot_schema.py exactly. Keep these two files
 * in sync manually, or generate this file from the Pydantic schema
 * (e.g. via pydantic2ts) once the schema stabilizes.
 */

export type TargetType =
  | "nav"
  | "heading"
  | "section"
  | "paragraph"
  | "form_field"
  | "button"
  | "faq_answer"
  | "price_card"
  | "policy_line"
  | "download"
  | "other";

export type AllowedAction = "point" | "point_and_navigate" | "point_and_confirm_navigate";

export type AnchorStrategy =
  | "element_center"
  | "text_start"
  | "heading_center"
  | "field_center"
  | "card_title"
  | "visual_rect";

export type PlotStatus = "active" | "stale" | "unresolved" | "needs_review";

export type PlotSource = "scan" | "live_recovery_promoted";

export interface PlotRecord {
  target_id: string;
  page_route: string;
  target_type: TargetType;
  meaning: string;
  intent_aliases: string[];
  direct_aliases?: string[];
  topic_aliases?: string[];
  content_fingerprint: string;
  semantic_locator: string;
  anchor_strategy: AnchorStrategy;
  structural_context: Record<string, string | number | boolean | null>;
  confidence: number;
  allowed_actions: AllowedAction[];
  status: PlotStatus;
  last_verified_at: string; // ISO timestamp
  source: PlotSource;
}

export interface CandidateCorrection {
  target_id: string;
  new_locator: string;
  evidence: string;
  observed_count: number;
  first_observed_at: string;
  last_observed_at: string;
}
