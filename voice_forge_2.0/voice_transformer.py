"""
Voice Forge 2.1 - Character Voice Transformation
Transforms your natural voice into distinct character voices
"""

import numpy as np
from pathlib import Path
from typing import Dict, Tuple, Optional
from scipy.signal import butter, lfilter
import librosa
import soundfile as sf
from dataclasses import dataclass
import json

@dataclass
class VoiceCharacteristics:
    """Measurable vocal characteristics"""
    avg_pitch: float          # Fundamental frequency (Hz)
    pitch_range: float        # Variation (Hz)
    formant_f1: float        # First formant frequency
    formant_f2: float        # Second formant frequency
    speaking_rate: float      # Syllables per second
    breathiness: float        # High-frequency noise ratio
    nasality: float           # Nasal resonance strength
    resonance: float          # Vocal tract length factor


class VoiceTransformer:
    """
    Transforms source voice samples into character-specific voices
    while preserving emotional content and natural prosody
    """

    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate

        # Character transformation profiles
        self.character_profiles = {
            "phil": {
                "pitch_shift": -3.0,
                "formant_shift": 0.85,
                "speaking_rate": 0.92,
                "resonance_boost": 2.5,
                "breathiness": 0.3,
                "nasality": 0.1,
                "spectral_tilt": -2.0,
                "vibrato": 0.0
            },
            "jim": {
                "pitch_shift": +2.0,
                "formant_shift": 1.1,
                "speaking_rate": 1.15,
                "resonance_boost": 1.2,
                "breathiness": 0.1,
                "nasality": 0.4,
                "spectral_tilt": +1.5,
                "vibrato": 0.1
            },
            "bryan": {
                "pitch_shift": -5.0,
                "formant_shift": 0.75,
                "speaking_rate": 0.88,
                "resonance_boost": 4.0,
                "breathiness": 0.0,
                "nasality": 0.05,
                "spectral_tilt": -3.5,
                "vibrato": 0.0
            },
            "cali": {
                "pitch_shift": +1.5,           # Slightly higher, clear feminine
                "formant_shift": 0.9,          # Longer vocal tract (warm authority)
                "speaking_rate": 0.95,         # Measured, never rushed
                "resonance_boost": 1.8,        # Warm but precise
                "breathiness": 0.05,           # Pure tone
                "nasality": 0.1,               # Minimal nasal
                "spectral_tilt": -1.0,         # Slightly dark, authoritative
                "vibrato": 0.0                 # Steady, reliable
            }
        }

    def analyze_voice(self, audio_path: Path) -> VoiceCharacteristics:
        """Extract vocal characteristics from source sample"""

        # Load audio
        # Load audio using librosa (avoids torchcodec/FFmpeg for WAV files)
        audio, sr = librosa.load(str(audio_path), sr=self.sample_rate, mono=True)

        # Extract pitch using librosa
        pitches, magnitudes = librosa.piptrack(
            y=audio,
            sr=self.sample_rate,
            hop_length=512,
            fmin=75,
            fmax=400
        )

        pitch_values = []
        for t in range(pitches.shape[1]):
            index = magnitudes[:, t].argmax()
            pitch = pitches[index, t]
            if pitch > 0:
                pitch_values.append(pitch)

        characteristics = VoiceCharacteristics(
            avg_pitch=np.mean(pitch_values) if pitch_values else 150.0,
            pitch_range=np.std(pitch_values) if pitch_values else 20.0,
            formant_f1=self._estimate_formant(audio, 500, 1500),
            formant_f2=self._estimate_formant(audio, 1500, 2500),
            speaking_rate=self._measure_speaking_rate(audio),
            breathiness=self._measure_breathiness(audio),
            nasality=self._measure_nasality(audio),
            resonance=self._estimate_resonance(audio)
        )

        return characteristics

    def _estimate_formant(self, audio: np.ndarray, fmin: float, fmax: float) -> float:
        """Estimate formant frequency in given range"""
        spectrum = np.fft.fft(audio)
        freqs = np.fft.fftfreq(len(audio), 1/self.sample_rate)
        mask = (freqs >= fmin) & (freqs <= fmax)
        if not np.any(mask):
            return (fmin + fmax) / 2
        region_spectrum = np.abs(spectrum[mask])
        region_freqs = freqs[mask]
        peak_idx = np.argmax(region_spectrum)
        return region_freqs[peak_idx]

    def _measure_speaking_rate(self, audio: np.ndarray) -> float:
        """Estimate syllables per second"""
        frame_length = int(0.025 * self.sample_rate)
        hop_length = int(0.010 * self.sample_rate)
        energy = librosa.feature.rms(
            y=audio,
            hop_length=hop_length,
            frame_length=frame_length
        )[0]
        peaks = librosa.effects.split(
            audio,
            hop_length=hop_length,
            frame_length=frame_length,
            top_db=20
        )
        duration = len(audio) / self.sample_rate
        syllable_count = len(peaks)
        return syllable_count / duration if duration > 0 else 5.0

    def _measure_breathiness(self, audio: np.ndarray) -> float:
        """Measure high-frequency noise component"""
        nyquist = self.sample_rate / 2
        high_freq = 4000 / nyquist
        b, a = butter(4, high_freq, btype='high')
        high_freq_audio = lfilter(b, a, audio)
        total_energy = np.sum(audio**2)
        high_freq_energy = np.sum(high_freq_audio**2)
        return high_freq_energy / total_energy if total_energy > 0 else 0.0

    def _measure_nasality(self, audio: np.ndarray) -> float:
        """Measure nasal resonance around 250-500Hz"""
        nyquist = self.sample_rate / 2
        low_freq = 250 / nyquist
        high_freq = 500 / nyquist
        b, a = butter(4, [low_freq, high_freq], btype='band')
        nasal_audio = lfilter(b, a, audio)
        total_energy = np.sum(audio**2)
        nasal_energy = np.sum(nasal_audio**2)
        return nasal_energy / total_energy if total_energy > 0 else 0.0

    def _estimate_resonance(self, audio: np.ndarray) -> float:
        """Estimate vocal tract length from spectral tilt"""
        spectrum = np.abs(np.fft.fft(audio))
        freqs = np.fft.fftfreq(len(audio), 1/self.sample_rate)
        spectral_centroid = np.sum(spectrum * freqs) / np.sum(spectrum)
        return spectral_centroid / 1000.0

    def transform_voice(
        self,
        source_audio: np.ndarray,
        target_character: str,
        preserve_prosody: bool = True
    ) -> np.ndarray:
        """
        Transform source voice into character voice
        """

        if target_character not in self.character_profiles:
            raise ValueError(f"Unknown character: {target_character}")

        profile = self.character_profiles[target_character]

        transformed = self._pitch_shift_with_formants(
            source_audio,
            profile["pitch_shift"],
            profile["formant_shift"]
        )

        if preserve_prosody:
            transformed = self._time_stretch_prosody_preserving(
                transformed,
                profile["speaking_rate"]
            )
        else:
            transformed = self._change_speaking_rate(
                transformed,
                profile["speaking_rate"]
            )

        transformed = self._apply_character_spectrum(
            transformed,
            profile
        )

        transformed = self._enhance_resonance(
            transformed,
            profile["resonance_boost"],
            profile["spectral_tilt"]
        )

        transformed = self._apply_character_finetuning(
            transformed,
            profile
        )

        transformed = np.clip(transformed, -0.95, 0.95)

        return transformed

    def _pitch_shift_with_formants(
        self,
        audio: np.ndarray,
        pitch_shift: float,
        formant_shift: float
    ) -> np.ndarray:
        import librosa
        pitch_ratio = 2 ** (pitch_shift / 12)
        shifted = librosa.effects.pitch_shift(
            audio,
            sr=self.sample_rate,
            n_steps=pitch_shift,
            bins_per_octave=12
        )
        if abs(formant_shift - 1.0) > 0.05:
            shifted = self._shift_formants(shifted, formant_shift)
        return shifted

    def _shift_formants(self, audio: np.ndarray, factor: float) -> np.ndarray:
        spectrum = np.fft.fft(audio)
        freqs = np.fft.fftfreq(len(audio), 1/self.sample_rate)
        new_spectrum = np.interp(
            freqs,
            freqs * factor,
            spectrum,
            left=0,
            right=0
        )
        return np.real(np.fft.ifft(new_spectrum))

    def _time_stretch_prosody_preserving(
        self,
        audio: np.ndarray,
        rate_factor: float
    ) -> np.ndarray:
        import librosa
        return librosa.effects.time_stretch(audio, rate=1.0/rate_factor)

    def _change_speaking_rate(
        self,
        audio: np.ndarray,
        rate_factor: float
    ) -> np.ndarray:
        new_length = int(len(audio) / rate_factor)
        indices = np.linspace(0, len(audio)-1, new_length)
        return np.interp(indices, np.arange(len(audio)), audio)

    def _apply_character_spectrum(
        self,
        audio: np.ndarray,
        profile: Dict
    ) -> np.ndarray:
        spectrum = np.fft.fft(audio)
        freqs = np.fft.fftfreq(len(audio), 1/self.sample_rate)
        filter_response = self._create_character_filter(freqs, profile)
        shaped_spectrum = spectrum * filter_response
        return np.real(np.fft.ifft(shaped_spectrum))

    def _create_character_filter(
        self,
        freqs: np.ndarray,
        profile: Dict
    ) -> np.ndarray:
        response = np.ones_like(freqs)
        tilt = profile.get("spectral_tilt", 0)
        if tilt != 0:
            tilt_response = 10 ** (tilt * freqs / 1000 / 20)
            response *= tilt_response
        breathiness = profile.get("breathiness", 0)
        if breathiness > 0:
            high_freq_mask = freqs > 3000
            response[high_freq_mask] *= (1 + breathiness)
        nasality = profile.get("nasality", 0)
        if nasality > 0:
            nasal_mask = (freqs >= 250) & (freqs <= 500)
            response[nasal_mask] *= (1 + nasality)
        return response

    def _enhance_resonance(
        self,
        audio: np.ndarray,
        boost_factor: float,
        spectral_tilt: float
    ) -> np.ndarray:
        harmonics = audio.copy()
        threshold = 0.3
        ratio = 1.5
        harmonics = np.where(
            np.abs(harmonics) > threshold,
            np.sign(harmonics) * (threshold + (np.abs(harmonics) - threshold) / ratio),
            harmonics
        )
        enhanced = audio + (harmonics * (boost_factor - 1.0))
        return np.clip(enhanced, -1.0, 1.0)

    def _apply_character_finetuning(
        self,
        audio: np.ndarray,
        profile: Dict
    ) -> np.ndarray:
        vibrato = profile.get("vibrato", 0)
        if vibrato > 0:
            audio = self._add_vibrato(audio, vibrato)
        return audio

    def _add_vibrato(self, audio: np.ndarray, amount: float) -> np.ndarray:
        duration = len(audio) / self.sample_rate
        time = np.linspace(0, duration, len(audio))
        vibrato_freq = 5.5
        vibrato_depth = amount * 0.02
        modulation = 1.0 + vibrato_depth * np.sin(2 * np.pi * vibrato_freq * time)
        return audio * modulation


class CharacterVoiceGenerator:
    """
    High-level interface for generating character voices
    """

    def __init__(self, sample_rate: int = 24000):
        self.transformer = VoiceTransformer(sample_rate)
        self.sample_rate = sample_rate

    def generate_character_sample(
        self,
        source_sample_path: Path,
        character: str,
        output_path: Path,
        preview_segments: bool = True
    ) -> bool:
        try:
            # Load source audio using librosa (mono)
            source_audio, sr = librosa.load(str(source_sample_path), sr=self.sample_rate, mono=True)
            source_chars = self.transformer.analyze_voice(source_sample_path)
            print("   Applying character transformations...")
            character_audio = self.transformer.transform_voice(
                source_audio,
                character,
                preserve_prosody=True
            )
            print(f"   Saving transformed sample: {output_path}")
            sf.write(str(output_path), character_audio, self.sample_rate)
            if preview_segments:
                self._generate_preview_segments(
                    character_audio,
                    character,
                    output_path.parent
                )
            self._print_transformation_summary(source_chars, character)
            return True
        except Exception as e:
            print(f"❌ Character generation failed: {e}")
            return False

    def _generate_preview_segments(
        self,
        audio: np.ndarray,
        character: str,
        output_dir: Path
    ):
        segment_length = self.sample_rate * 10
        for i, start in enumerate([0, segment_length, segment_length*2]):
            if start + segment_length <= len(audio):
                segment = audio[start:start + segment_length]
                preview_path = output_dir / f"{character}_preview_{i+1}.wav"
                sf.write(str(preview_path), segment, self.sample_rate)
                print(f"   Preview saved: {preview_path.name}")

    def _print_transformation_summary(
        self,
        source_chars: VoiceCharacteristics,
        character: str
    ):
        profile = self.transformer.character_profiles[character]
        print(f"\n📊 Transformation Summary for {character.title()}:")
        print(f"   Pitch shift: {profile['pitch_shift']:+} semitones")
        print(f"   Formant shift: {profile['formant_shift']:.2f}x")
        print(f"   Speaking rate: {profile['speaking_rate']:.2f}x")
        print(f"   Resonance boost: {profile['resonance_boost']:.1f}x")
        print(f"   Spectral tilt: {profile['spectral_tilt']:+} dB/octave")


def test_transformation(source_path: Path, character: str):
    generator = CharacterVoiceGenerator()
    output_name = f"{source_path.stem}_as_{character}.wav"
    output_path = source_path.parent / output_name
    success = generator.generate_character_sample(
        source_path,
        character,
        output_path,
        preview_segments=True
    )
    if success:
        print(f"\n✅ Character voice generated!")
        print(f"   Full sample: {output_path}")
        print(f"   Preview clips: {output_path.parent}")
        print(f"\nNext step: Use this transformed sample with Voice Forge 2.0")
        print(f"   python forge.py --use-transformed --character {character}")
    else:
        print(f"\n❌ Transformation failed")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python voice_transformer.py <source_sample.wav> <character>")
        print("Characters: phil, jim, bryan")
        sys.exit(1)
    source_path = Path(sys.argv[1])
    character = sys.argv[2].lower()
    test_transformation(source_path, character)
