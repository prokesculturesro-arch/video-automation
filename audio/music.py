"""
Background music manager.
Manages music files from assets/music/ directory.
"""

import os
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")


class MusicManager:
    """Manages background music selection and loading."""

    def __init__(self, config=None):
        self.config = config or {}
        music_config = self.config.get("music", {})
        self.enabled = music_config.get("enabled", True)
        self.volume = music_config.get("volume", 0.15)
        self.fade_in = music_config.get("fade_in", 1.0)
        self.fade_out = music_config.get("fade_out", 2.0)

    def get_music_file(self, mood=None):
        """
        Get a music file path matching the mood.

        Args:
            mood: Music mood (calm, upbeat, dramatic, inspiring, funny)
                  If None, picks randomly from available files.

        Returns:
            Path to music file, or None if not available
        """
        if not self.enabled:
            return None

        os.makedirs(MUSIC_DIR, exist_ok=True)

        music_files = [
            f for f in os.listdir(MUSIC_DIR)
            if f.endswith((".mp3", ".wav", ".ogg"))
        ]

        if not music_files:
            return None

        # Try mood-based matching
        if mood:
            mood_matches = [f for f in music_files if mood.lower() in f.lower()]
            if mood_matches:
                return os.path.join(MUSIC_DIR, random.choice(mood_matches))

        return os.path.join(MUSIC_DIR, random.choice(music_files))

    def list_available(self):
        """List all available music files."""
        os.makedirs(MUSIC_DIR, exist_ok=True)
        return [
            f for f in os.listdir(MUSIC_DIR)
            if f.endswith((".mp3", ".wav", ".ogg"))
        ]
