import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class FFmpegPostProcessor:
    def __init__(self, base_path: Path, logger_instance: Optional[logging.Logger] = None):
        self.base_path = Path(base_path)
        self.logger = logger_instance or logger
        self.target_loudness = {
            "I": -16,
            "TP": -1.5,
            "LRA": 11,
        }

    def process_episode(self, input_file: Path, output_file: Path, voice_profile: str = "standard") -> Dict[str, Any]:
        input_path = Path(input_file).resolve()
        output_path = Path(output_file).resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        with tempfile.TemporaryDirectory(dir=self.base_path) as temp_dir:
            temp_path = Path(temp_dir)
            pass1_output = temp_path / "pass1_cleaned.wav"
            analysis_data = self._pass1_analysis_and_cleanup(input_path, pass1_output)
            self._pass2_dynamics_and_normalize(
                input_file=pass1_output,
                output_file=output_path,
                measured_loudness=analysis_data.get("input_i", -23.0),
                measured_peak=analysis_data.get("input_tp", -1.0),
                measured_lra=analysis_data.get("input_lra", 7.0),
                measured_thresh=analysis_data.get("input_thresh", -34.0),
                target_offset=analysis_data.get("target_offset", 0.0),
                voice_profile=voice_profile,
            )
            verification = self._verify_loudness(output_path)
            return {
                "input_file": str(input_path),
                "output_file": str(output_path),
                "measured_loudness": analysis_data.get("input_i"),
                "final_loudness": verification.get("input_i"),
                "true_peak": verification.get("input_tp"),
                "loudness_range": verification.get("input_lra"),
                "compliant": self._check_compliance(verification),
                "processing_chain": "two_pass_ffmpeg",
            }

    def _pass1_analysis_and_cleanup(self, input_file: Path, output_file: Path) -> Dict[str, Any]:
        filters = [
            "highpass=f=80:poles=2",
            "lowpass=f=8000:poles=2",
            "afftdn=nr=15:nf=-25:bn=1",
            "agate=threshold=-35dB:ratio=1:attack=10:release=100",
            f"loudnorm=I={self.target_loudness['I']}:TP={self.target_loudness['TP']}:LRA={self.target_loudness['LRA']}:print_format=json:linear=true:dual_mono=true",
        ]
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_file),
            "-af",
            ",".join(filters),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(output_file),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg Pass 1 failed: {result.stderr[-500:]}")
        return self._parse_loudnorm_output(result.stderr)

    def _pass2_dynamics_and_normalize(
        self,
        input_file: Path,
        output_file: Path,
        measured_loudness: float,
        measured_peak: float,
        measured_lra: float,
        measured_thresh: float,
        target_offset: float,
        voice_profile: str,
    ) -> None:
        if "phil" in voice_profile.lower():
            compand_settings = "compand=attacks=0.1:decays=0.3:points=-70/-70|-40/-30|-20/-15|0/-10:soft-knee=3:gain=2"
        elif "jim" in voice_profile.lower():
            compand_settings = "compand=attacks=0.3:decays=0.8:points=-70/-70|-50/-45|-30/-25|0/-12:soft-knee=6:gain=0"
        else:
            compand_settings = "compand=attacks=0.2:decays=0.5:points=-70/-70|-40/-35|-20/-15|0/-12:soft-knee=3"

        loudnorm_filter = (
            f"loudnorm=I={self.target_loudness['I']}:"
            f"TP={self.target_loudness['TP']}:"
            f"LRA={self.target_loudness['LRA']}:"
            f"measured_I={measured_loudness}:"
            f"measured_TP={measured_peak}:"
            f"measured_LRA={measured_lra}:"
            f"measured_thresh={measured_thresh}:"
            f"offset={target_offset}:"
            "linear=true:"
            "dual_mono=true"
        )

        filters = [
            "dynaudnorm=f=100:g=15:p=0.95:m=10:s=20",
            compand_settings,
            loudnorm_filter,
            "treble=gain=2:f=3000:width_type=h:width=2000",
        ]
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_file),
            "-af",
            ",".join(filters),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            "-id3v2_version",
            "3",
            str(output_file),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg Pass 2 failed: {result.stderr[-500:]}")

    def _parse_loudnorm_output(self, ffmpeg_stderr: str) -> Dict[str, float]:
        try:
            match = re.search(r"\{[\s\S]*?\}", ffmpeg_stderr)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return {}

    def _verify_loudness(self, filepath: Path) -> Dict[str, Any]:
        cmd = [
            "ffmpeg",
            "-i",
            str(filepath),
            "-af",
            f"loudnorm=I={self.target_loudness['I']}:print_format=json",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return self._parse_loudnorm_output(result.stderr)

    def _check_compliance(self, metrics: Dict[str, Any]) -> bool:
        if not metrics:
            return False
        try:
            integrated = float(metrics.get("input_i", -99))
            true_peak = float(metrics.get("input_tp", 0))
        except Exception:
            return False
        return -17 <= integrated <= -15 and true_peak <= -1.0
