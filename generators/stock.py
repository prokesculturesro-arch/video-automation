"""
Stock footage generator — wraps modules/visuals.py with Scene-based interface.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.visuals import search_and_download, create_fallback_clip


class StockFootageGenerator:
    """Generates stock footage visuals for scenes."""

    def __init__(self, config=None):
        self.config = config or {}
        visuals_config = self.config.get("visuals", {})
        self.pexels_config = visuals_config.get("pexels", {})

    def generate_for_scene(self, scene):
        """
        Get stock footage for a scene.

        Args:
            scene: Scene object with visual_prompt as search query

        Returns:
            List of local file paths to footage clips
        """
        query = scene.visual_prompt or scene.text[:30]
        count = scene.visual_params.get("clip_count", 2)

        clips = search_and_download(
            query=query,
            count=count,
            orientation=self.pexels_config.get("orientation", "portrait"),
            min_duration=self.pexels_config.get("min_duration", 5),
        )

        if not clips:
            fallback = create_fallback_clip(
                query, duration=int(scene.duration)
            )
            return [fallback] if fallback else []

        return clips

    def generate_batch(self, scenes):
        """Generate stock footage for multiple scenes."""
        results = {}
        for scene in scenes:
            results[scene.scene_index] = self.generate_for_scene(scene)
        return results
