"""Approved audio rendering with ad takes and media cues."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydub import AudioSegment
from .worker import HardenedPodcastWorker
from ..storage.episode_store import load_media_cues
logger = logging.getLogger(__name__)


class SegmentAwarePodcastWorker(HardenedPodcastWorker):
    """Retain the production worker name for existing callers."""

    def generate_script(
        self,
        episode_config: Dict[str, Any],
        line_callback: Optional[Callable] = None,
        max_retries: int = 2,
    ) -> List[Dict[str, Any]]:
        raise RuntimeError("Episode writing is archived. Build a document context package and import an externally written script.")




    def _synthesize_segments(self, script_lines, output_dir, episode_id, progress_callback=None):
        from ..storage.episode_store import list_ads
        import json
        from .ads import ad_audio_fingerprint
        ads = {ad["ad_id"]: ad for ad in list_ads(episode_id)}
        segments, offset, block = [], 0, 0
        while offset < len(script_lines):
            self._check_cancelled()
            line = script_lines[offset]
            ad_id = line.get("ad_id")
            end = offset + 1
            if ad_id:
                while (end < len(script_lines) and script_lines[end].get("ad_id") == ad_id
                       and script_lines[end].get('ad_slot_id') == line.get('ad_slot_id')):
                    end += 1
                ad = ads.get(ad_id)
                if not ad or not ad.get("audio_file") or not Path(ad["audio_file"]).is_file():
                    raise RuntimeError(f"Ad {ad_id} must have produced audio before episode assembly")
                signature = ad_audio_fingerprint(script_lines[offset:end])
                if signature != ad.get("audio_script_fingerprint"):
                    raise RuntimeError(f"Ad {ad_id} audio does not match the inserted script; produce/reinsert the matching ad before assembly")
                selected_engine = self.qwen_tts_config.get("production", {}).get("required_engine") or self.project_config.get("tts", {}).get("primary_engine", "kokoro")
                provenance = ad.get("voice_resolution") or []
                if not provenance or any(item.get("engine") != selected_engine or
                                         item.get("resolved_voice_id") != self._resolve_voice_name(item.get("resolved_voice"), selected_engine)
                                         for item in provenance):
                    raise RuntimeError(f"Ad {ad_id} audio voice settings have changed or are unverified; produce the ad again")
                audio_file = Path(ad["audio_file"])
                if ad.get("composition", {}).get("sfx_tracks"):
                    from .ads import mix_ad_tracks
                    asset_meta = self.base_path / "episodes" / episode_id / "ads" / f"{ad_id}_assets.json"
                    assets = json.loads(asset_meta.read_text(encoding="utf-8")) if asset_meta.is_file() else []
                    mixed = mix_ad_tracks(ad, ad["composition"]["sfx_tracks"], assets)
                    audio_file = output_dir / f"{ad_id}_mixed.mp3"
                    mixed.export(audio_file, format="mp3", bitrate="192k").close()
                segments.append({"index": len(segments) + 1, "line_index": end, "speaker": ad.get("resolved_voice", ad.get("announcer_key")),
                                 "audio_file": str(audio_file), "duration_seconds": self._probe_duration_seconds(audio_file),
                                 "pause_after": 0, "engine": "saved_ad_audio", "ad_id": ad_id, "text": " ".join(item['text'] for item in script_lines[offset:end]),
                                 "voice_resolution": ad.get("voice_resolution"), "generated_by": "ad_engine"})
            else:
                while end < len(script_lines) and not script_lines[end].get("ad_id"):
                    end += 1
                block += 1
                def report(update):
                    if progress_callback:
                        adjusted = dict(update)
                        adjusted["line_number"] = offset + update.get("line_number", 0)
                        adjusted["total_lines"] = len(script_lines)
                        adjusted["progress"] = 0.85 * (offset + (end - offset) * update.get("progress", 0) / 0.85) / len(script_lines)
                        progress_callback(adjusted)
                produced = super()._synthesize_segments(script_lines[offset:end], output_dir, f"{episode_id}_block{block}", report)
                for item in produced:
                    item["line_index"] += offset
                    item["index"] = len(segments) + 1
                    segments.append(item)
            offset = end
        return segments

    def _concatenate_segments(
        self, segments: List[Dict[str, Any]], output_path: Path,
        media_cues_override: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Build dialogue audio, then apply episode media cues before wrapping."""
        super()._concatenate_segments(segments, output_path, media_cues_override=[])
        if not output_path.exists():
            return

        episode_id = output_path.stem
        if episode_id.endswith("_raw_mix"):
            episode_id = episode_id[: -len("_raw_mix")]
        if media_cues_override is None:
            cue_payload = load_media_cues(episode_id)
            cues = list(cue_payload.get("cues", []) or [])
        else:
            cues = list(media_cues_override)
        seen_line_cues = set()
        for segment in segments:
            for cue in segment.get("production_cues", []) or []:
                identity = (segment.get("production_line_id"), json.dumps(cue, sort_keys=True, ensure_ascii=False))
                if identity in seen_line_cues:
                    continue
                seen_line_cues.add(identity)
                try:
                    line_index = int(segment.get("line_index", 1)) - 1
                except (TypeError, ValueError):
                    line_index = 0
                cues.append({**cue, "line_number": line_index})
        if not cues:
            return

        elapsed_ms = 0
        line_end_ms: Dict[int, int] = {}
        for segment in segments:
            elapsed_ms += int(float(segment.get("duration_seconds", 0.0) or 0.0) * 1000)
            elapsed_ms += int(float(segment.get("pause_after", 0.0) or 0.0) * 1000)
            try:
                line_number = int(segment.get("line_index", 0) or 0)
            except (TypeError, ValueError):
                line_number = 0
            if line_number > 0:
                line_end_ms[line_number] = elapsed_ms

        audio = AudioSegment.from_file(str(output_path))
        resolved_cues: List[tuple[int, Dict[str, Any], Dict[str, Any]]] = []
        for cue in cues:
            asset_id = str(cue.get("asset_id") or "")
            if not asset_id:
                continue
            from ...api.assets import _resolve_any_asset
            asset = _resolve_any_asset(episode_id, asset_id)
            if not asset:
                logger.warning("Media cue asset missing: %s", asset_id)
                continue
            try:
                raw_index = cue.get("line_number")
                if raw_index is None:
                    base_ms = len(audio)
                else:
                    anchor_line = max(1, int(raw_index) + 1)
                    base_ms = line_end_ms.get(anchor_line, len(audio))
            except (TypeError, ValueError):
                base_ms = len(audio)
            resolved_cues.append((base_ms, cue, asset))

        resolved_cues.sort(key=lambda item: item[0])
        inserted_shift_ms = 0
        for base_ms, cue, asset in resolved_cues:
            asset_path = Path(str(asset.get("stored_path") or ""))
            if not asset_path.exists():
                continue
            try:
                clip = AudioSegment.from_file(str(asset_path))
            except Exception as exc:
                logger.warning("Media cue could not load %s: %s", asset_path, exc)
                continue

            role = str(asset.get("role") or cue.get("display_label") or "media").lower()
            note = str(cue.get("notes") or "").lower()
            overlay = "overlay" in note or role == "sfx"
            position_ms = max(0, min(len(audio), base_ms + inserted_shift_ms))

            if overlay:
                gain_db = -8.0
                clip = clip.apply_gain(gain_db)
                audio = audio.overlay(clip, position=position_ms)
                logger.info("Media cue overlay %s at %dms", asset_path.name, position_ms)
            else:
                audio = audio[:position_ms] + clip + audio[position_ms:]
                inserted_shift_ms += len(clip)
                logger.info("Media cue insert %s at %dms", asset_path.name, position_ms)

        audio.export(str(output_path), format="mp3", bitrate="192k")
