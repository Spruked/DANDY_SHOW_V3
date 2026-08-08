"""
quality_guard.py — Script Quality Validation & Gatekeeping
===========================================================
Replaces the documented-but-missing quality guard from the Dandy system.

Usage:
    from quality_guard import ScriptQualityGuard, QualityDecision

    guard = ScriptQualityGuard()
    result = guard.evaluate(script_lines, target_duration_minutes=40)

    if result.decision == QualityDecision.ACCEPT:
        save_script(script_lines)
    elif result.decision == QualityDecision.REJECT_RETRY:
        regenerate_with_tweaked_params()
    else:
        use_seed_fallback()
"""

import re
import logging
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class QualityDecision(Enum):
    ACCEPT = "accept"
    REJECT_RETRY = "reject_retry"  # Try generation again with different params
    FALLBACK_SEED = "fallback_seed"  # Give up on SKG, use enhanced seed
    FALLBACK_MINIMAL = "fallback_minimal"  # Last resort bare-bones script


@dataclass
class QualityReport:
    """Complete quality assessment of a generated script."""

    decision: QualityDecision
    score: float  # 0-100 overall quality score
    word_count: int
    line_count: int
    target_words: int
    unknown_count: int
    unknown_pct: float
    raw_template_count: int  # Unresolved {variables}
    duplicate_line_count: int = 0
    repeated_line_count: int = 0
    unique_line_ratio: float = 1.0
    speaker_diversity: Dict[str, int] = field(default_factory=dict)
    avg_words_per_line: float = 0.0
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _count_words(text: str) -> int:
    return len(text.split())


def _detect_unknowns(text: str) -> int:
    """Count literal '[unknown]' substrings in text."""
    return text.lower().count("[unknown]")


def _detect_raw_templates(text: str) -> int:
    """Count unresolved template variables like {topic}, {tech_gadget}."""
    return len(re.findall(r"\{[a-z_]+\}", text))


def _detect_nonsense_injections(text: str) -> List[str]:
    """Detect hardcoded nonsense from _inject_confidently_wrong."""
    known_nonsense = [
        "vinyl is faster than fiber",
        "cloud is just a bunch of floppy disks",
        "EVs don't use electricity when going downhill",
        "Podcasts are printed first, then streamed",
    ]
    found = []
    text_lower = text.lower()
    for nonsense in known_nonsense:
        if nonsense.lower() in text_lower:
            found.append(nonsense)
    return found


def _normalize_line(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    normalized = re.sub(r"[^a-z0-9 '\-]", "", normalized)
    return normalized


class ScriptQualityGuard:
    """
    Multi-stage quality validation for generated podcast scripts.

    The guard checks for all known failure modes:
      1. [unknown] token contamination
      2. Raw template variable leakage
      3. Insufficient line/word count
      4. Poor speaker diversity
      5. Nonsense statement injection
      6. Unrealistic words-per-line ratios
    """

    # Thresholds (tune these based on your content)
    UNKNOWN_PCT_REJECT = 15.0  # % of lines with [unknown] → reject
    UNKNOWN_PCT_WARN = 5.0  # % of lines with [unknown] → warning
    MIN_WORDS_PER_LINE = 8  # Below this, lines are too short
    MAX_WORDS_PER_LINE = 80  # Above this, lines are too long for TTS
    MIN_SPEAKER_TYPES = 2  # Need at least Phil + Jim
    NONSENSE_TOLERANCE = 0  # Any nonsense = flag

    def __init__(self, words_per_minute: int = 155):
        self.words_per_minute = words_per_minute

    def evaluate(
        self,
        script_lines: List[Dict[str, Any]],
        target_duration_minutes: int = 40,
        episode_topic: str = "",
    ) -> QualityReport:
        """
        Evaluate a script against quality criteria.

        Args:
            script_lines: List of dicts with keys: speaker, text, emotion, ...
            target_duration_minutes: Target podcast length (30-45 typical)
            episode_topic: Topic string for contextual checks

        Returns:
            QualityReport with decision and detailed metrics
        """
        issues: List[str] = []
        warnings: List[str] = []

        # ── Basic counts ──
        line_count = len(script_lines)
        word_count = sum(
            _count_words(str(line.get("text", line.get("line", ""))))
            for line in script_lines
        )
        target_words = target_duration_minutes * self.words_per_minute
        all_text = " ".join(
            str(line.get("text", line.get("line", ""))) for line in script_lines
        )
        normalized_lines = [
            _normalize_line(str(line.get("text", line.get("line", ""))))
            for line in script_lines
            if str(line.get("text", line.get("line", ""))).strip()
        ]
        line_counts = Counter(normalized_lines)
        duplicate_line_count = sum(count - 1 for count in line_counts.values() if count > 1)
        repeated_line_count = sum(1 for count in line_counts.values() if count > 1)
        unique_line_ratio = len(line_counts) / max(len(normalized_lines), 1)

        # ── [unknown] detection (FAILURE MODE 1) ──
        unknown_count = _detect_unknowns(all_text)
        unknown_pct = (unknown_count / max(line_count, 1)) * 100

        if unknown_pct >= self.UNKNOWN_PCT_REJECT:
            issues.append(
                f"CRITICAL: {unknown_pct:.1f}% lines contain [unknown] "
                f"(threshold: {self.UNKNOWN_PCT_REJECT}%)"
            )
        elif unknown_pct >= self.UNKNOWN_PCT_WARN:
            warnings.append(
                f"WARNING: {unknown_pct:.1f}% lines contain [unknown] "
                f"(threshold: {self.UNKNOWN_PCT_WARN}%)"
            )

        # ── Raw template variable detection (FAILURE MODE 7) ──
        raw_template_count = _detect_raw_templates(all_text)
        if raw_template_count > 0:
            issues.append(
                f"CRITICAL: {raw_template_count} unresolved template variables found: "
                f"{re.findall(r'{[a-z_]+}', all_text)[:5]}"
            )

        # ── Repetition detection ──
        if duplicate_line_count >= max(4, line_count * 0.08):
            issues.append(
                f"CRITICAL: Repeated script lines detected "
                f"({duplicate_line_count} duplicates across {repeated_line_count} repeated lines)"
            )
        elif duplicate_line_count > 0:
            warnings.append(f"{duplicate_line_count} duplicate line(s) detected")

        if line_count >= 20 and unique_line_ratio < 0.65:
            issues.append(
                f"CRITICAL: Low line diversity ({unique_line_ratio:.0%} unique lines)"
            )

        # ── Word count validation (FAILURE MODE 2) ──
        word_ratio = word_count / max(target_words, 1)
        if word_ratio < 0.5:
            issues.append(
                f"CRITICAL: Script is {word_ratio*100:.0f}% of target length "
                f"({word_count}/{target_words} words)"
            )
        elif word_ratio < 0.8:
            warnings.append(
                f"WARNING: Script is {word_ratio*100:.0f}% of target length "
                f"({word_count}/{target_words} words)"
            )

        # ── Line-level analysis ──
        speaker_counts: Dict[str, int] = {}
        short_lines = 0
        long_lines = 0
        for line in script_lines:
            speaker = str(line.get("speaker", "unknown")).lower().strip()
            text = str(line.get("text", line.get("line", "")))
            speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1

            wpl = _count_words(text)
            if wpl < self.MIN_WORDS_PER_LINE:
                short_lines += 1
            if wpl > self.MAX_WORDS_PER_LINE:
                long_lines += 1

        # ── Speaker diversity (FAILURE MODE 5) ──
        speaker_types = len(speaker_counts)
        if speaker_types < self.MIN_SPEAKER_TYPES:
            issues.append(
                f"CRITICAL: Only {speaker_types} speaker type(s) found "
                f"(need at least {self.MIN_SPEAKER_TYPES})"
            )

        # ── Words per line sanity ──
        avg_wpl = word_count / max(line_count, 1)
        if short_lines > line_count * 0.3:
            warnings.append(f"{short_lines} lines are unusually short (<{self.MIN_WORDS_PER_LINE} words)")
        if long_lines > 0:
            warnings.append(f"{long_lines} lines are unusually long (>{self.MAX_WORDS_PER_LINE} words)")

        # ── Nonsense injection detection (FAILURE MODE 6) ──
        nonsense_found = _detect_nonsense_injections(all_text)
        if nonsense_found:
            issues.append(
                f"CRITICAL: Hardcoded nonsense detected: {nonsense_found}"
            )

        # ── Empty/whitespace-only lines ──
        empty_lines = sum(
            1
            for line in script_lines
            if not str(line.get("text", line.get("line", ""))).strip()
        )
        if empty_lines > 0:
            warnings.append(f"{empty_lines} empty lines in script")

        # ── Score calculation ──
        score = self._calculate_score(
            word_ratio=word_ratio,
            unknown_pct=unknown_pct,
            raw_template_count=raw_template_count,
            speaker_types=speaker_types,
            nonsense_count=len(nonsense_found),
            empty_lines=empty_lines,
            duplicate_line_count=duplicate_line_count,
            unique_line_ratio=unique_line_ratio,
        )

        # ── Decision ──
        decision = self._make_decision(issues, warnings, score, word_ratio)

        report = QualityReport(
            decision=decision,
            score=score,
            word_count=word_count,
            line_count=line_count,
            target_words=target_words,
            unknown_count=unknown_count,
            unknown_pct=unknown_pct,
            raw_template_count=raw_template_count,
            duplicate_line_count=duplicate_line_count,
            repeated_line_count=repeated_line_count,
            unique_line_ratio=unique_line_ratio,
            speaker_diversity=speaker_counts,
            avg_words_per_line=avg_wpl,
            issues=issues,
            warnings=warnings,
        )

        # ── Logging ──
        self._log_report(report)
        return report

    def _calculate_score(
        self,
        word_ratio: float,
        unknown_pct: float,
        raw_template_count: int,
        speaker_types: int,
        nonsense_count: int,
        empty_lines: int,
        duplicate_line_count: int,
        unique_line_ratio: float,
    ) -> float:
        """Calculate 0-100 quality score."""
        score = 100.0

        # Length penalty (up to -40)
        if word_ratio < 1.0:
            score -= min(40, (1.0 - word_ratio) * 50)

        # [unknown] penalty (up to -30)
        score -= min(30, unknown_pct * 2)

        # Raw template penalty (up to -20)
        score -= min(20, raw_template_count * 5)

        # Speaker diversity penalty (up to -10)
        if speaker_types < 2:
            score -= 10

        # Nonsense penalty (up to -15)
        score -= min(15, nonsense_count * 15)

        # Empty lines penalty
        score -= min(10, empty_lines * 2)

        # Repetition penalty
        score -= min(35, duplicate_line_count * 4)
        if unique_line_ratio < 0.75:
            score -= min(25, (0.75 - unique_line_ratio) * 80)

        return max(0.0, min(100.0, score))

    def _make_decision(
        self,
        issues: List[str],
        warnings: List[str],
        score: float,
        word_ratio: float,
    ) -> QualityDecision:
        """Determine pipeline action based on evaluation."""
        critical_count = sum(1 for i in issues if i.startswith("CRITICAL"))

        # If multiple critical issues → go straight to seed fallback
        if critical_count >= 2 or score < 20:
            logger.error("Script quality critically low (%s/100, %d issues) → FALLBACK_SEED", score, critical_count)
            return QualityDecision.FALLBACK_SEED

        # If one critical issue → retry generation with tweaked params
        if critical_count == 1:
            logger.warning("Script has 1 critical issue (%s/100) → REJECT_RETRY", score)
            return QualityDecision.REJECT_RETRY

        # If mostly just too short → retry (expander can fix this)
        if word_ratio < 0.5 and score >= 40:
            logger.warning("Script too short but otherwise ok → REJECT_RETRY")
            return QualityDecision.REJECT_RETRY

        # Warnings only → accept with note
        if score >= 60:
            logger.info("Script accepted (score: %s/100, warnings: %d)", score, len(warnings))
            return QualityDecision.ACCEPT

        # Borderline → retry once
        logger.warning("Script borderline (score: %s/100) → REJECT_RETRY", score)
        return QualityDecision.REJECT_RETRY

    def _log_report(self, report: QualityReport) -> None:
        """Structured logging of quality report."""
        log_lines = [
            "═══ SCRIPT QUALITY REPORT ═══",
            f"  Decision: {report.decision.value}",
            f"  Score: {report.score:.1f}/100",
            f"  Lines: {report.line_count} | Words: {report.word_count}/{report.target_words}",
            f"  [unknown]: {report.unknown_count} ({report.unknown_pct:.1f}%)",
            f"  Raw templates: {report.raw_template_count}",
            f"  Duplicates: {report.duplicate_line_count} | Unique ratio: {report.unique_line_ratio:.0%}",
            f"  Speakers: {report.speaker_diversity}",
            f"  Avg words/line: {report.avg_words_per_line:.1f}",
        ]
        if report.issues:
            log_lines.append(f"  Issues ({len(report.issues)}):")
            for issue in report.issues:
                log_lines.append(f"    ! {issue}")
        if report.warnings:
            log_lines.append(f"  Warnings ({len(report.warnings)}):")
            for warning in report.warnings:
                log_lines.append(f"    • {warning}")
        log_lines.append("═══════════════════════════════")
        logger.info("\n".join(log_lines))


def quick_check(
    script_lines: List[Dict[str, Any]], target_minutes: int = 40
) -> bool:
    """One-liner pass/fail check for convenience."""
    guard = ScriptQualityGuard()
    report = guard.evaluate(script_lines, target_minutes)
    return report.decision == QualityDecision.ACCEPT
