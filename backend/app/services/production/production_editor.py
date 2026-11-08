"""MORB policies and production QC used by the explicit Production Editor stage."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .production_manifest import checked_take_path, file_hash, load_manifest
from ..storage.episode_store import save_json


def _spoken_text(text: str) -> str:
    """Apply only established, meaning-preserving TTS substitutions."""
    normalized = " ".join(text.split())
    for pattern, replacement in (
        (r"\be\.g\.", "for example"),
        (r"\bi\.e\.", "that is"),
        (r"\bvs\.", "versus"),
    ):
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


class EditorialMorb:
    name = "Editorial MORB"

    def propose(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        proposals = []
        for index, line in enumerate(lines, start=1):
            if line.get("ad_id") or line.get("is_ad"):
                continue
            original = str(line.get("text", ""))
            normalized = _spoken_text(original)
            if normalized != original:
                proposals.append({"morb": self.name, "segment_id": f"line_{index:03d}",
                                  "action": "NORMALIZE", "field": "text", "before": original,
                                  "after": normalized,
                                  "reason": "Normalize whitespace and known spoken abbreviations for TTS"})
            if normalized and not re.search(r"[.!?…\"']$", normalized):
                proposals.append({"morb": self.name, "segment_id": f"line_{index:03d}",
                                  "action": "FLAG", "severity": "review",
                                  "reason": "Line may end mid-sentence; no automatic completion"})
        return proposals


class PerformanceMorb:
    name = "Performance MORB"

    def propose(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        proposals = []
        for index, line in enumerate(lines, start=1):
            if line.get("ad_id") or line.get("is_ad") or line.get("pause_locked"):
                continue
            current = str(line.get("text", "")).strip()
            following = lines[index] if index < len(lines) else None
            next_text = str((following or {}).get("text", "")).strip()
            next_speaker = str((following or {}).get("speaker", "")).lower()
            speaker = str(line.get("speaker", "")).lower()
            next_is_ad = bool(following and (following.get("ad_id") or following.get("is_ad")))
            section_break = bool(following and line.get("segment_index") is not None
                                 and following.get("segment_index") is not None
                                 and line.get("segment_index") != following.get("segment_index"))
            if following is None or next_is_ad or section_break:
                pause, reason = 0.75, "Section or show transition"
            elif next_speaker == speaker:
                pause, reason = 0.22, "Same speaker continues"
            elif current.endswith("?") and re.match(r"(?i)^(yes|no|because|exactly|well|right|sure|actually|but)\b", next_text):
                pause, reason = 0.2, "Immediate answer to a question"
            elif current.endswith("?"):
                pause, reason = 0.32, "Question handoff"
            elif re.match(r"(?i)^(oh|wait|but|exactly|right|yeah|yes|no|really)\b", next_text):
                pause, reason = 0.24, "Next speaker reacts to this turn"
            elif len(current.split()) >= 36:
                pause, reason = 0.52, "Long turn needs a breath"
            elif current.endswith("!"):
                pause, reason = 0.28, "Energetic handoff"
            else:
                pause, reason = 0.38, "Ordinary conversational handoff"
            prior = line.get("pause_after")
            if prior is None or abs(float(prior) - pause) >= 0.01:
                window = lines[max(0, index - 3): min(len(lines), index + 2)]
                proposals.append({"morb": self.name, "segment_id": f"line_{index:03d}",
                                  "action": "PERFORM", "field": "pause_after", "before": prior,
                                  "after": pause, "reason": reason,
                                  "context": {"topic": line.get("segment_title"),
                                              "window": [{"speaker": item.get("speaker"),
                                                          "text": str(item.get("text", ""))[:240]}
                                                         for item in window]}})
        return proposals


class DirectorMorb:
    name = "Director MORB"

    def propose(self, cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"morb": self.name, "segment_id": f"line_{int(cue.get('line_number') or 0):03d}",
                 "action": "DIRECT", "asset_id": cue.get("asset_id"),
                 "cue_id": cue.get("cue_id"), "cue_type": cue.get("cue_type", "media"),
                 "position": {"line_number": cue.get("line_number"),
                              "start_seconds": cue.get("start_seconds")},
                 "reason": "Saved episode media cue"}
                for cue in cues]


class CampaignMorb:
    name = "Campaign MORB"

    def propose(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Campaign claims remain exactly as approved in the source script.
        return []


class ArbiterMorb:
    name = "Arbiter MORB"

    @staticmethod
    def decide(proposal: dict[str, Any], assets: dict[str, dict[str, Any]], allow_embellish: bool) -> tuple[str, str]:
        action = proposal.get("action")
        if action == "FLAG":
            return "flagged", "Operator review; source text preserved"
        if action == "NORMALIZE" and proposal.get("field") == "text":
            before = str(proposal.get("before", ""))
            after = str(proposal.get("after", ""))
            if _spoken_text(before) == after:
                return "accepted", "Approved deterministic spoken-text normalization"
        if action == "PERFORM" and proposal.get("field") == "pause_after":
            pause = proposal.get("after")
            if isinstance(pause, (int, float)) and 0 <= pause <= 2:
                return "accepted", "Bounded pause"
        if action == "DIRECT":
            asset = assets.get(str(proposal.get("asset_id") or ""))
            if not asset:
                return "rejected", "Asset ID absent from current registry"
            if asset.get("asset_type") != "audio":
                return "rejected", "Audio cue refers to a non-audio asset"
            return "accepted", "Audio asset present in current registry"
        if action == "EMBELLISH" and not allow_embellish:
            return "rejected", "Episode embellishment flag is off"
        return "rejected", "Action outside current deterministic policy"


class QcMorb:
    name = "QC MORB"

    def inspect(self, episode_path: Path, audio_path: Path) -> dict[str, Any]:
        manifest = load_manifest(episode_path)
        findings = []
        take_findings = []
        if manifest is None:
            findings.append("Production manifest missing")
        else:
            for segment in manifest["segments"]:
                for chunk in segment.get("audio", {}).get("chunks", []):
                    try:
                        take_path = checked_take_path(episode_path, str(chunk.get("path") or ""))
                        if file_hash(take_path) != chunk.get("hash"):
                            raise ValueError("Saved take hash mismatch")
                    except (ValueError, KeyError) as exc:
                        take_findings.append({"segment_id": segment["segment_id"],
                                              "finding": str(exc), "take_asset_id": chunk.get("asset_id")})
            processing = manifest.get("processing", {})
            if processing.get("compliant") is False:
                findings.append("Audio post-processing did not meet its configured compliance target")
            if (manifest.get("global_cues", {}).get("intro_outro", {}).get("enabled")
                    and processing.get("intro_outro") != "wrapped"):
                findings.append("Configured intro/outro was not recorded as wrapped")
            for segment in manifest["segments"]:
                chunks = segment.get("audio", {}).get("chunks", [])
                duration = sum(int(chunk.get("duration_ms") or 0) for chunk in chunks) / 1000
                words = len(str(segment.get("production_text") or "").split())
                if duration <= 0:
                    take_findings.append({"segment_id": segment["segment_id"], "finding": "Take has no measured duration"})
                elif words >= 6 and duration < words / 5:
                    take_findings.append({"segment_id": segment["segment_id"],
                                          "finding": "Take duration is unusually short for its text; listen for clipped delivery",
                                          "duration_seconds": round(duration, 2), "words": words})
                if (segment.get("source_line_index") and
                        str(segment.get("original_text") or "").strip() and
                        not re.search(r"[.!?…\"']$", str(segment["original_text"]).strip())):
                    take_findings.append({"segment_id": segment["segment_id"],
                                          "finding": "Approved source line appears unfinished; review the spoken ending"})
        if not audio_path.is_file() or audio_path.stat().st_size == 0:
            findings.append("Final audio is missing or empty")
        report = {
            "episode_id": episode_path.name, "qc_morb": self.name,
            "status": "pass" if not findings and not take_findings else "flagged",
            "findings": findings, "take_findings": take_findings,
            "audio_hash": file_hash(audio_path) if audio_path.is_file() else None,
            "checked_at": datetime.now().isoformat(),
            "checks": ["final audio exists", "saved take files exist", "saved take hashes match",
                       "post-processing compliance", "configured theme wrapping",
                       "per-take duration plausibility", "source line completeness"],
        }
        save_json(episode_path / "qc_report.v1.json", report)
        return report


class ProductionEditor:
    """Compatibility guard: production preparation must be an explicit editor action."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def prepare(
        self, episode_id: str, script_lines: list[dict[str, Any]],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError(
            "Implicit production preparation is disabled. Create and approve a Production Editor version first."
        )


def build_assembly_graph(episode_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    theme = manifest.get("global_cues", {}).get("intro_outro", {})
    theme_path = Path(str(theme.get("music_file") or ""))
    if theme.get("enabled") and manifest.get("processing", {}).get("intro_outro") == "wrapped":
        if not theme_path.is_absolute():
            theme_path = (episode_path.parents[1] / theme_path).resolve()
        nodes.append({"node_id": "intro", "kind": "theme", "position": "start",
                      "asset_path": str(theme_path),
                      "asset_hash": file_hash(theme_path) if theme_path.is_file() else None,
                      "duration_ms": 18000})
    for segment in manifest["segments"]:
        for chunk in segment["audio"]["chunks"]:
            nodes.append({"node_id": f"node_{len(nodes)+1:04d}", "kind": "voice_take",
                          "segment_id": segment["segment_id"], "asset_id": chunk["asset_id"],
                          "audio_hash": chunk["hash"], "duration_ms": chunk["duration_ms"]})
            if chunk.get("pause_after", 0) > 0:
                nodes.append({"node_id": f"node_{len(nodes)+1:04d}", "kind": "pause",
                              "segment_id": segment["segment_id"],
                              "duration_ms": round(float(chunk["pause_after"]) * 1000)})
    if theme.get("enabled") and manifest.get("processing", {}).get("intro_outro") == "wrapped":
        nodes.append({"node_id": "outro", "kind": "theme", "position": "end",
                      "asset_path": str(theme_path),
                      "asset_hash": file_hash(theme_path) if theme_path.is_file() else None,
                      "duration_ms": 18000})
    cue_nodes = [{"node_id": str(item.get("cue_id") or f"cue_{index:03d}"),
                  "kind": "media_cue", "status": "authorized_unverified",
                  "asset_id": item["asset_id"],
                  "position": item.get("position")}
                 for index, item in enumerate(manifest.get("directives", []), start=1)]
    graph = {"episode_id": episode_path.name, "editor_run_id": manifest["editor_run_id"],
             "nodes": nodes, "cue_nodes": cue_nodes,
             "global_cues": manifest.get("global_cues", {}),
             "scope": "voice, pauses, theme and approved saved cues; configured SFX remain global treatments"}
    save_json(episode_path / "assembly_graph.v1.json", graph)
    return graph
