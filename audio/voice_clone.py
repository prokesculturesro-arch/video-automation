"""
Voice Cloning — OpenVoice v2 integration.

Uses MeloTTS for base speech generation + OpenVoice for voice color transfer.
Falls back to Edge TTS if cloning is unavailable.

Requirements:
- OpenVoice v2 installed separately
- MeloTTS installed
- Reference audio file (10-30s WAV sample of target voice)

May run as subprocess if Python version mismatch (OpenVoice needs 3.9-3.10).
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

from utils.cache import ensure_cache_dir, is_cached

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VoiceCloner:
    """
    Clone a voice from reference audio and generate speech.

    Usage:
        cloner = VoiceCloner(config)
        result = cloner.clone_and_speak("Hello world", language="en")
        # result = {"audio_path": ..., "duration": ..., "word_timestamps": [...]}
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.engine = self.config.get("engine", "openvoice")
        self.reference_audio = self.config.get("reference_audio", "")
        self.openvoice_path = self.config.get("openvoice_path", "")
        self.cache_dir = ensure_cache_dir("voice_clone")
        self._available = None

    def is_available(self):
        """Check if voice cloning is available."""
        if self._available is not None:
            return self._available

        if not self.reference_audio or not os.path.exists(self.reference_audio):
            self._available = False
            return False

        # Try importing OpenVoice
        try:
            from openvoice import se_extractor
            from openvoice.api import ToneColorConverter
            self._available = True
        except ImportError:
            # Check if available via subprocess
            if self.openvoice_path and os.path.exists(self.openvoice_path):
                self._available = True
            else:
                self._available = False

        return self._available

    def clone_and_speak(self, text, language="en"):
        """
        Generate speech with cloned voice.

        Pipeline:
        1. MeloTTS generates base speech in target language
        2. OpenVoice transfers voice color from reference audio
        3. Returns audio with word timestamps

        Falls back to Edge TTS if cloning fails.

        Args:
            text: Text to speak
            language: Language code

        Returns:
            dict with audio_path, duration, word_timestamps
        """
        # Check cache
        cache_key = hashlib.md5(
            f"{text}|{self.reference_audio}|{language}".encode()
        ).hexdigest()[:16]
        cached_path = os.path.join(self.cache_dir, f"clone_{cache_key}.wav")
        meta_path = cached_path.replace(".wav", "_meta.json")

        if is_cached(cached_path) and os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                return json.load(f)

        if not self.is_available():
            print("   [VoiceClone] Not available, falling back to Edge TTS")
            return self._fallback_tts(text, language)

        try:
            # Try in-process first
            result = self._clone_inprocess(text, language, cached_path)
        except ImportError:
            try:
                # Try subprocess
                result = self._clone_subprocess(text, language, cached_path)
            except Exception as e:
                print(f"   [VoiceClone] Subprocess failed: {e}")
                return self._fallback_tts(text, language)
        except Exception as e:
            print(f"   [VoiceClone] Error: {e}")
            return self._fallback_tts(text, language)

        if result:
            # Save metadata
            with open(meta_path, "w") as f:
                json.dump(result, f, indent=2)
            return result

        return self._fallback_tts(text, language)

    def _clone_inprocess(self, text, language, output_path):
        """Run voice cloning in the current process."""
        import torch
        from openvoice import se_extractor
        from openvoice.api import ToneColorConverter
        from melo.api import TTS as MeloTTS

        device = "cuda" if torch.cuda.is_available() else "cpu"

        # Extract speaker embedding from reference
        print("   [VoiceClone] Extracting voice color from reference...")
        target_se, _ = se_extractor.get_se(
            self.reference_audio, device=device
        )

        # Generate base speech with MeloTTS
        lang_map = {
            "en": "EN_NEWEST",
            "es": "ES",
            "fr": "FR",
            "zh": "ZH",
            "ja": "JP",
            "ko": "KR",
        }
        melo_lang = lang_map.get(language, "EN_NEWEST")

        print(f"   [VoiceClone] Generating base speech ({melo_lang})...")
        melo = MeloTTS(language=melo_lang, device=device)
        speaker_ids = melo.hps.data.spk2id

        # Get first available speaker
        speaker_key = list(speaker_ids.keys())[0]
        speaker_id = speaker_ids[speaker_key]

        # Generate base audio to temp file
        base_path = output_path.replace(".wav", "_base.wav")
        melo.tts_to_file(text, speaker_id, base_path, speed=1.0)

        # Apply voice color transfer
        print("   [VoiceClone] Applying voice color transfer...")
        ckpt_path = os.path.join(
            self.openvoice_path or ".",
            "checkpoints_v2", "converter"
        )

        tone_converter = ToneColorConverter(
            os.path.join(ckpt_path, "config.json"), device=device
        )
        tone_converter.load_ckpt(os.path.join(ckpt_path, "checkpoint.pth"))

        # Extract source speaker embedding
        source_se, _ = se_extractor.get_se(base_path, device=device)

        # Convert
        tone_converter.convert(
            audio_src_path=base_path,
            src_se=source_se,
            tgt_se=target_se,
            output_path=output_path,
        )

        # Get duration and create approximate timestamps
        duration = self._get_duration(output_path)
        timestamps = self._approximate_timestamps(text, duration)

        # Clean up temp
        if os.path.exists(base_path):
            os.remove(base_path)

        print(f"   [VoiceClone] Generated {duration:.1f}s cloned audio")

        return {
            "audio_path": output_path,
            "duration": duration,
            "word_timestamps": timestamps,
        }

    def _clone_subprocess(self, text, language, output_path):
        """Run voice cloning as subprocess (for Python version isolation)."""
        if not self.openvoice_path:
            raise RuntimeError("openvoice_path not configured")

        # Write clone script
        script = f'''
import sys
sys.path.insert(0, "{self.openvoice_path}")
import torch
from openvoice import se_extractor
from openvoice.api import ToneColorConverter
from melo.api import TTS as MeloTTS
import json

device = "cuda" if torch.cuda.is_available() else "cpu"
text = """{text.replace('"', '\\"')}"""
ref_audio = "{self.reference_audio}"
output = "{output_path}"
language = "{language}"

target_se, _ = se_extractor.get_se(ref_audio, device=device)

lang_map = {{"en": "EN_NEWEST", "es": "ES", "fr": "FR", "zh": "ZH", "ja": "JP", "ko": "KR"}}
melo_lang = lang_map.get(language, "EN_NEWEST")

melo = MeloTTS(language=melo_lang, device=device)
speaker_ids = melo.hps.data.spk2id
speaker_key = list(speaker_ids.keys())[0]
speaker_id = speaker_ids[speaker_key]

base_path = output.replace(".wav", "_base.wav")
melo.tts_to_file(text, speaker_id, base_path, speed=1.0)

ckpt = "{os.path.join(self.openvoice_path, 'checkpoints_v2', 'converter')}"
tc = ToneColorConverter(ckpt + "/config.json", device=device)
tc.load_ckpt(ckpt + "/checkpoint.pth")

source_se, _ = se_extractor.get_se(base_path, device=device)
tc.convert(audio_src_path=base_path, src_se=source_se, tgt_se=target_se, output_path=output)

import os
if os.path.exists(base_path):
    os.remove(base_path)

print("SUCCESS")
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0 or "SUCCESS" not in result.stdout:
                raise RuntimeError(f"Clone subprocess failed: {result.stderr[-200:]}")

            duration = self._get_duration(output_path)
            timestamps = self._approximate_timestamps(text, duration)

            return {
                "audio_path": output_path,
                "duration": duration,
                "word_timestamps": timestamps,
            }
        finally:
            os.unlink(script_path)

    def _fallback_tts(self, text, language):
        """Fall back to Edge TTS when voice cloning is unavailable."""
        from modules.voiceover import generate_voiceover

        # Map language to voice
        voice_map = {
            "en": "en-US-GuyNeural",
            "sk": "sk-SK-LukasNeural",
            "cs": "cs-CZ-AntoninNeural",
            "cz": "cs-CZ-AntoninNeural",
            "de": "de-DE-ConradNeural",
            "fr": "fr-FR-HenriNeural",
            "es": "es-ES-AlvaroNeural",
            "ja": "ja-JP-KeitaNeural",
            "ko": "ko-KR-InJoonNeural",
            "zh": "zh-CN-YunxiNeural",
        }
        voice = voice_map.get(language, "en-US-GuyNeural")

        cache_key = hashlib.md5(f"vc_fb_{text}_{voice}".encode()).hexdigest()[:12]
        output_path = os.path.join(self.cache_dir, f"fb_{cache_key}.mp3")

        return generate_voiceover(text=text, output_path=output_path, voice=voice)

    def _get_duration(self, audio_path):
        """Get audio duration."""
        try:
            from moviepy import AudioFileClip
            clip = AudioFileClip(audio_path)
            dur = clip.duration
            clip.close()
            return round(dur, 2)
        except Exception:
            size = os.path.getsize(audio_path)
            return round(size / 32000, 2)  # Rough estimate for WAV

    def _approximate_timestamps(self, text, duration):
        """Create approximate word timestamps from text and duration."""
        words = text.split()
        if not words:
            return []

        char_lengths = [len(w) + 1 for w in words]
        total_chars = sum(char_lengths)
        current_time = 0.0
        timestamps = []

        for i, word in enumerate(words):
            fraction = char_lengths[i] / total_chars
            word_dur = duration * fraction

            timestamps.append({
                "word": word,
                "start": round(current_time, 3),
                "end": round(current_time + word_dur, 3),
            })
            current_time += word_dur

        return timestamps
