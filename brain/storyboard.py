"""
Storyboard data model — central data structure for the video pipeline.

A Storyboard contains a sequence of Scenes, each describing:
- What text/narration to speak
- What visual to show (stock footage, AI image, AI video, infographic, motion graphic, etc.)
- How to transition between scenes
- Visual parameters for the generator
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class VisualType(Enum):
    """Types of visual content a scene can contain."""
    STOCK_FOOTAGE = "stock_footage"
    AI_GENERATED_VIDEO = "ai_generated_video"
    AI_GENERATED_IMAGE = "ai_generated_image"
    INFOGRAPHIC = "infographic"
    TEXT_ANIMATION = "text_animation"
    MOTION_GRAPHIC = "motion_graphic"
    CONVERSATION = "conversation"
    COLOR_BACKGROUND = "color_background"


class TransitionType(Enum):
    """Transition effects between scenes."""
    CUT = "cut"
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"


@dataclass
class Scene:
    """
    A single scene in the storyboard.

    Attributes:
        text: Narration/voiceover text for this scene
        duration: Target duration in seconds (may be adjusted by TTS)
        visual_type: What kind of visual to generate
        visual_prompt: Prompt/query for the visual generator
            - For stock: Pexels search query
            - For AI image: SDXL/Pollinations prompt
            - For AI video: Wan2GP text prompt
            - For infographic: data description
            - For motion: effect name
        visual_params: Additional parameters for the visual generator
        transition_in: Transition from previous scene
        transition_duration: Duration of transition in seconds
        text_overlay: Optional text to display on screen
        scene_index: Position in storyboard (set automatically)
    """
    text: str
    duration: float = 8.0
    visual_type: VisualType = VisualType.STOCK_FOOTAGE
    visual_prompt: str = ""
    visual_params: dict = field(default_factory=dict)
    transition_in: TransitionType = TransitionType.CROSSFADE
    transition_duration: float = 0.5
    text_overlay: str = ""
    scene_index: int = 0

    # Filled during pipeline execution
    visual_path: Optional[str] = None
    visual_clip: Optional[Any] = None  # VideoClip object (for animated motion/infographic)
    audio_path: Optional[str] = None
    audio_duration: Optional[float] = None
    word_timestamps: list = field(default_factory=list)


@dataclass
class Storyboard:
    """
    Complete video storyboard — the central data structure.

    Created by Director (from templates or Claude API),
    consumed by generators and composer.
    """
    topic: str
    language: str = "en"
    style: str = "education"
    target_duration: float = 30.0

    # Content
    hook: str = ""
    scenes: list[Scene] = field(default_factory=list)
    cta: str = ""

    # Metadata
    hashtags: list[str] = field(default_factory=list)
    music_mood: str = "inspiring"
    title: str = ""

    # Filled during pipeline execution
    total_audio_duration: float = 0.0

    def add_scene(self, scene: Scene) -> None:
        """Add a scene and update its index."""
        scene.scene_index = len(self.scenes)
        self.scenes.append(scene)

    def get_full_narration(self) -> str:
        """Get all narration text concatenated."""
        parts = []
        if self.hook:
            parts.append(self.hook)
        for scene in self.scenes:
            if scene.text:
                parts.append(scene.text)
        if self.cta:
            parts.append(self.cta)
        return " ".join(parts)

    def get_visual_types_used(self) -> set[VisualType]:
        """Get set of all visual types used in this storyboard."""
        return {scene.visual_type for scene in self.scenes}

    def needs_gpu(self) -> bool:
        """Check if this storyboard requires GPU for visual generation."""
        gpu_types = {VisualType.AI_GENERATED_VIDEO, VisualType.AI_GENERATED_IMAGE}
        return bool(self.get_visual_types_used() & gpu_types)

    def to_dict(self) -> dict:
        """Serialize storyboard to dict (for JSON/logging)."""
        return {
            "topic": self.topic,
            "language": self.language,
            "style": self.style,
            "target_duration": self.target_duration,
            "hook": self.hook,
            "scenes": [
                {
                    "text": s.text,
                    "duration": s.duration,
                    "visual_type": s.visual_type.value,
                    "visual_prompt": s.visual_prompt,
                    "visual_params": s.visual_params,
                    "transition_in": s.transition_in.value,
                    "text_overlay": s.text_overlay,
                }
                for s in self.scenes
            ],
            "cta": self.cta,
            "hashtags": self.hashtags,
            "music_mood": self.music_mood,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Storyboard":
        """Deserialize storyboard from dict."""
        sb = cls(
            topic=data.get("topic", ""),
            language=data.get("language", "en"),
            style=data.get("style", "education"),
            target_duration=data.get("target_duration", 30.0),
            hook=data.get("hook", ""),
            cta=data.get("cta", ""),
            hashtags=data.get("hashtags", []),
            music_mood=data.get("music_mood", "inspiring"),
        )
        for scene_data in data.get("scenes", []):
            scene = Scene(
                text=scene_data.get("text", ""),
                duration=scene_data.get("duration", 8.0),
                visual_type=VisualType(scene_data.get("visual_type", "stock_footage")),
                visual_prompt=scene_data.get("visual_prompt", ""),
                visual_params=scene_data.get("visual_params", {}),
                transition_in=TransitionType(scene_data.get("transition_in", "crossfade")),
                text_overlay=scene_data.get("text_overlay", ""),
            )
            sb.add_scene(scene)
        return sb

    def to_legacy_script(self) -> dict:
        """Convert storyboard to legacy script dict format for backward compat."""
        segments = []
        for scene in self.scenes:
            segments.append({
                "text": scene.text,
                "duration": scene.duration,
                "visual_query": scene.visual_prompt,
                "text_overlay": scene.text_overlay,
            })
        return {
            "hook": self.hook,
            "segments": segments,
            "cta": self.cta,
            "total_duration": self.target_duration,
            "hashtags": self.hashtags,
            "music_mood": self.music_mood,
            "style": self.style,
            "language": self.language,
            "topic": self.topic,
        }
