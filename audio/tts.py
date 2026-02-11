"""
Multi-language TTS Engine — dynamic voice discovery for ANY language.

Uses Edge TTS (Microsoft) — completely FREE and unlimited.
Automatically discovers available voices for any language code.
"""

import asyncio
import hashlib
import json
import os
import sys

import edge_tts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "tts")

# Language code normalization map
LANG_NORMALIZE = {
    "cz": "cs",       # Czech
    "jp": "ja",       # Japanese
    "kr": "ko",       # Korean
    "cn": "zh",       # Chinese
    "ua": "uk",       # Ukrainian
    "br": "pt-BR",    # Brazilian Portuguese
    "mx": "es-MX",    # Mexican Spanish
    "gb": "en-GB",    # British English
    "us": "en-US",    # American English
}

# Preferred voice cache (populated on first discovery)
_voice_cache = {}


class TTSEngine:
    """
    Multi-language TTS engine with dynamic voice discovery.

    Features:
    - Auto-discovers available voices for ANY language
    - Selects best Neural voice based on language and gender
    - Normalizes language codes (cz->cs, jp->ja, etc.)
    - Full backward compatibility with existing voiceover module
    """

    def __init__(self, config=None):
        self.config = config or {}
        vo_config = self.config.get("voiceover", {})
        self.rate = vo_config.get("rate", "+0%")
        self.pitch = vo_config.get("pitch", "+0Hz")
        self.auto_discover = self.config.get("audio", {}).get(
            "voiceover", {}
        ).get("auto_discover", True)

        # Pre-defined voices from config
        self.configured_voices = vo_config.get("voices", {})

    def normalize_language(self, lang_code):
        """
        Normalize language code to Edge TTS format.

        Args:
            lang_code: Any language code (e.g., "cz", "jp", "en", "de")

        Returns:
            Normalized code (e.g., "cs", "ja", "en", "de")
        """
        lang_code = lang_code.lower().strip()
        return LANG_NORMALIZE.get(lang_code, lang_code)

    def discover_voices(self, language_code):
        """
        Dynamically discover available voices for a language.

        Args:
            language_code: Language code (e.g., "en", "de", "ja", "cs")

        Returns:
            List of voice dicts: [{name, gender, locale}, ...]
        """
        normalized = self.normalize_language(language_code)

        if normalized in _voice_cache:
            return _voice_cache[normalized]

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        try:
            voices = loop.run_until_complete(self._discover_async(normalized))
        finally:
            loop.close()

        _voice_cache[normalized] = voices
        return voices

    async def _discover_async(self, lang_prefix):
        """Async voice discovery."""
        all_voices = await edge_tts.list_voices()

        matched = []
        for v in all_voices:
            locale = v.get("Locale", "")
            # Match by prefix (e.g., "de" matches "de-DE", "de-AT", etc.)
            if locale.lower().startswith(lang_prefix.lower()):
                matched.append({
                    "name": v["ShortName"],
                    "gender": v["Gender"],
                    "locale": locale,
                    "friendly_name": v.get("FriendlyName", v["ShortName"]),
                })

        return matched

    def get_best_voice(self, language, gender="male"):
        """
        Auto-select the best voice for a language and gender.

        Priority:
        1. Config-defined voice for this language
        2. Neural voice matching language + gender
        3. Any available voice for this language
        4. Fallback to en-US

        Args:
            language: Language code
            gender: "male" or "female"

        Returns:
            Voice name string (e.g., "de-DE-ConradNeural")
        """
        normalized = self.normalize_language(language)

        # Check config first
        config_key = f"{normalized}_{gender}"
        alt_keys = [f"{language}_{gender}", f"{language}_male", f"{normalized}_male"]
        for key in [config_key] + alt_keys:
            if key in self.configured_voices:
                return self.configured_voices[key]

        # Discover voices
        voices = self.discover_voices(language)

        if not voices:
            print(f"   [TTS] No voices found for '{language}', using English fallback")
            return "en-US-GuyNeural"

        # Prefer matching gender
        gender_map = {"male": "Male", "female": "Female"}
        target_gender = gender_map.get(gender, "Male")

        matching = [v for v in voices if v["gender"] == target_gender]
        if matching:
            # Prefer Neural voices
            neural = [v for v in matching if "Neural" in v["name"]]
            if neural:
                return neural[0]["name"]
            return matching[0]["name"]

        # Any voice
        neural = [v for v in voices if "Neural" in v["name"]]
        if neural:
            return neural[0]["name"]

        return voices[0]["name"]

    def get_voice_for_character(self, language, char_index):
        """
        Get a voice for a conversation character by index.
        Alternates male/female voices for different characters.

        Args:
            language: Language code
            char_index: Character index (0, 1, 2, ...)

        Returns:
            Voice name string
        """
        gender = "male" if char_index % 2 == 0 else "female"
        voices = self.discover_voices(language)

        if not voices:
            return "en-US-GuyNeural"

        # Split by gender
        gender_map = {"male": "Male", "female": "Female"}
        target_gender = gender_map.get(gender, "Male")
        matching = [v for v in voices if v["gender"] == target_gender]

        if not matching:
            matching = voices

        # Cycle through available voices
        idx = (char_index // 2) % len(matching)
        return matching[idx]["name"]

    def generate(self, text, voice=None, output_path=None, rate=None, pitch=None):
        """
        Generate TTS audio with word timestamps.

        Args:
            text: Text to synthesize
            voice: Voice name (auto-selected if None)
            output_path: Output path (auto-generated if None)
            rate: Speech rate override
            pitch: Pitch override

        Returns:
            dict with audio_path, duration, word_timestamps
        """
        if voice is None:
            voice = "en-US-GuyNeural"
        if rate is None:
            rate = self.rate
        if pitch is None:
            pitch = self.pitch

        # Use existing voiceover module for actual generation
        from modules.voiceover import generate_voiceover

        if output_path is None:
            os.makedirs(CACHE_DIR, exist_ok=True)
            key = f"{text}|{voice}|{rate}|{pitch}"
            h = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]
            output_path = os.path.join(CACHE_DIR, f"{h}.mp3")

        return generate_voiceover(
            text=text,
            output_path=output_path,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )

    def list_voices_formatted(self, language):
        """
        Get formatted voice list for display.

        Args:
            language: Language code

        Returns:
            Formatted string listing all voices
        """
        voices = self.discover_voices(language)
        normalized = self.normalize_language(language)

        if not voices:
            return f"No voices found for language: {language} (normalized: {normalized})"

        lines = [f"Available voices for '{language}' ({normalized}):"]
        lines.append("-" * 50)

        for v in voices:
            lines.append(f"  {v['name']:<35} {v['gender']:<8} {v['locale']}")

        lines.append(f"\nTotal: {len(voices)} voices")
        return "\n".join(lines)
