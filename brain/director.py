"""
AI Director — orchestrates the entire video creation pipeline.

Two modes:
  - "template": Uses brain/templates.py (free, no API needed)
  - "claude": Sends topic to Anthropic API for structured storyboard generation

The Director:
  1. Creates a Storyboard (template or Claude)
  2. Generates visuals for each scene (stock, AI image, AI video, infographic, motion)
  3. Generates audio (TTS or voice clone)
  4. Composes the final video via composer/timeline
"""

import json
import os
import sys
import hashlib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from brain.storyboard import Storyboard, Scene, VisualType


class Director:
    """
    Main orchestrator for the ULTIMATE AI VIDEO CREATOR.

    Usage:
        director = Director(config)
        storyboard = director.create_storyboard("AI future", 30, "en", "education")
        output_path = director.execute_storyboard(storyboard, output_path)
    """

    def __init__(self, config):
        self.config = config
        brain_config = config.get("brain", {})
        self.mode = brain_config.get("mode", "template")
        self.claude_api_key = brain_config.get("claude_api_key", "")
        self.claude_model = brain_config.get("claude_model", "claude-sonnet-4-20250514")
        self.max_scenes = brain_config.get("max_scenes", 6)

    def create_storyboard(self, topic, duration=30, language="en", style="education",
                          visual_mode="stock"):
        """
        Create a Storyboard for the given topic.

        Args:
            topic: Video topic
            duration: Target duration in seconds
            language: Language code
            style: Content style
            visual_mode: "stock", "ai_image", "ai_video", or "mixed"

        Returns:
            Storyboard object
        """
        if self.mode == "claude" and self.claude_api_key:
            return self._create_storyboard_claude(topic, duration, language, style, visual_mode)
        else:
            return self._create_storyboard_template(topic, duration, language, style, visual_mode)

    def _create_storyboard_template(self, topic, duration, language, style, visual_mode):
        """Create storyboard using template system (free)."""
        from brain.templates import generate_storyboard
        return generate_storyboard(
            topic=topic,
            duration=duration,
            language=language,
            style=style,
            visual_mode=visual_mode,
            max_scenes=self.max_scenes,
        )

    def _create_storyboard_claude(self, topic, duration, language, style, visual_mode):
        """Create storyboard using Claude API."""
        try:
            import anthropic
        except ImportError:
            print("   [Director] anthropic package not installed, falling back to template mode")
            return self._create_storyboard_template(topic, duration, language, style, visual_mode)

        client = anthropic.Anthropic(api_key=self.claude_api_key)

        visual_types_available = ["stock_footage", "text_animation", "motion_graphic"]
        gen_config = self.config.get("generators", {})
        if gen_config.get("ai_image", {}).get("enabled"):
            visual_types_available.append("ai_generated_image")
        if gen_config.get("ai_video", {}).get("enabled"):
            visual_types_available.append("ai_generated_video")

        prompt = f"""Create a short-form video storyboard for the topic: "{topic}"

Requirements:
- Language: {language}
- Target duration: {duration} seconds
- Style: {style}
- Maximum scenes: {self.max_scenes}
- Available visual types: {', '.join(visual_types_available)}

Return a JSON object with this exact structure:
{{
  "hook": "opening hook text (1-2 sentences, attention-grabbing)",
  "scenes": [
    {{
      "text": "narration text for this scene",
      "duration": 8,
      "visual_type": "stock_footage",
      "visual_prompt": "search query or generation prompt for the visual",
      "text_overlay": "short text to show on screen (max 50 chars)",
      "transition_in": "crossfade"
    }}
  ],
  "cta": "call to action text",
  "hashtags": ["#tag1", "#tag2"],
  "music_mood": "inspiring"
}}

Visual types explained:
- stock_footage: search query for Pexels stock video
- ai_generated_image: prompt for AI image generation (cinematic, detailed)
- ai_generated_video: prompt for AI video generation (simple, clear motion)
- text_animation: text to animate with kinetic typography
- motion_graphic: text/stats for motion graphic overlay

Transition types: crossfade, cut, fade_black, slide_left, zoom_in

Write the narration in {language}. Make it engaging, factual, and optimized for short-form video."""

        try:
            print("   [Director] Generating storyboard with Claude API...")
            message = client.messages.create(
                model=self.claude_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text

            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                storyboard_data = json.loads(response_text[json_start:json_end])
                storyboard_data["topic"] = topic
                storyboard_data["language"] = language
                storyboard_data["style"] = style
                storyboard_data["target_duration"] = duration
                return Storyboard.from_dict(storyboard_data)
            else:
                print("   [Director] Could not parse Claude response, falling back to template")
                return self._create_storyboard_template(topic, duration, language, style, visual_mode)

        except Exception as e:
            print(f"   [Director] Claude API error: {e}, falling back to template")
            return self._create_storyboard_template(topic, duration, language, style, visual_mode)

    def execute_storyboard(self, storyboard, output_path, args=None):
        """
        Execute a storyboard — generate all assets and compose the final video.

        Pipeline:
        1. Generate audio (TTS) for all scenes
        2. Generate AI images (if any) -> unload GPU
        3. Generate AI videos (if any) -> done with GPU
        4. Generate other visuals (stock, infographic, motion, text_animation)
        5. Compose final video

        Args:
            storyboard: Storyboard object
            output_path: Output MP4 path
            args: CLI args (optional, for flags like --no-music)

        Returns:
            Path to output video
        """
        print(f"\n   [Director] Executing storyboard: {storyboard.topic}")
        print(f"   [Director] Scenes: {len(storyboard.scenes)}")
        print(f"   [Director] Visual types: {[s.visual_type.value for s in storyboard.scenes]}")

        # Step 1: Generate audio
        print("\n   [Director] Step 1: Generating audio...")
        self._generate_audio(storyboard)

        # Step 2: Generate AI images (GPU intensive)
        ai_image_scenes = [s for s in storyboard.scenes
                          if s.visual_type == VisualType.AI_GENERATED_IMAGE]
        if ai_image_scenes:
            print(f"\n   [Director] Step 2: Generating {len(ai_image_scenes)} AI images...")
            self._generate_ai_images(ai_image_scenes)
        else:
            print("\n   [Director] Step 2: No AI images needed, skipping")

        # Step 3: Generate AI videos (GPU intensive)
        ai_video_scenes = [s for s in storyboard.scenes
                          if s.visual_type == VisualType.AI_GENERATED_VIDEO]
        if ai_video_scenes:
            print(f"\n   [Director] Step 3: Generating {len(ai_video_scenes)} AI videos...")
            self._generate_ai_videos(ai_video_scenes)
        else:
            print("\n   [Director] Step 3: No AI videos needed, skipping")

        # Step 4: Generate other visuals
        print("\n   [Director] Step 4: Generating remaining visuals...")
        self._generate_other_visuals(storyboard)

        # Step 5: Compose
        print("\n   [Director] Step 5: Composing final video...")
        from composer.timeline import build_video_from_storyboard
        result = build_video_from_storyboard(storyboard, output_path, self.config)

        return result

    def _generate_audio(self, storyboard):
        """Generate TTS audio for all scenes."""
        audio_config = self.config.get("audio", {})
        voice_clone_config = audio_config.get("voice_clone", {})

        # Check if voice cloning is enabled
        use_voice_clone = (
            voice_clone_config.get("enabled", False)
            and voice_clone_config.get("reference_audio")
        )

        if use_voice_clone:
            try:
                from audio.voice_clone import VoiceCloner
                cloner = VoiceCloner(voice_clone_config)
                self._generate_audio_cloned(storyboard, cloner)
                return
            except Exception as e:
                print(f"   [Director] Voice cloning failed: {e}, falling back to Edge TTS")

        self._generate_audio_tts(storyboard)

    def _generate_audio_tts(self, storyboard):
        """Generate TTS audio using Edge TTS."""
        try:
            from audio.tts import TTSEngine
            engine = TTSEngine(self.config)
        except ImportError:
            from modules.voiceover import generate_voiceover
            engine = None

        full_text = storyboard.get_full_narration()

        if engine:
            voice = engine.get_best_voice(storyboard.language)
            result = engine.generate(full_text, voice=voice)
        else:
            # Fallback to legacy module
            from modules.voiceover import generate_voiceover
            from utils.cache import get_cache_path
            voice = self._get_voice_for_language(storyboard.language)
            cache_path = get_cache_path(full_text, "tts", ".mp3")
            result = generate_voiceover(text=full_text, output_path=cache_path, voice=voice)

        # Store audio info on storyboard
        storyboard.total_audio_duration = result["duration"]

        # Distribute word timestamps across scenes
        self._distribute_timestamps(storyboard, result["word_timestamps"])

        # Store full audio path on first scene (composer will use it)
        if storyboard.scenes:
            storyboard.scenes[0].audio_path = result["audio_path"]
            storyboard.scenes[0].audio_duration = result["duration"]

        print(f"   [Director] Audio: {result['duration']:.1f}s, {len(result['word_timestamps'])} words")

    def _generate_audio_cloned(self, storyboard, cloner):
        """Generate audio using voice cloning."""
        full_text = storyboard.get_full_narration()
        result = cloner.clone_and_speak(full_text, storyboard.language)

        storyboard.total_audio_duration = result["duration"]
        self._distribute_timestamps(storyboard, result["word_timestamps"])

        if storyboard.scenes:
            storyboard.scenes[0].audio_path = result["audio_path"]
            storyboard.scenes[0].audio_duration = result["duration"]

    def _distribute_timestamps(self, storyboard, word_timestamps):
        """Distribute word timestamps across scenes proportionally."""
        if not word_timestamps or not storyboard.scenes:
            return

        # Simple approach: split by scene text word count
        scene_word_counts = []
        for scene in storyboard.scenes:
            scene_word_counts.append(len(scene.text.split()))

        # Include hook and cta
        hook_words = len(storyboard.hook.split()) if storyboard.hook else 0
        cta_words = len(storyboard.cta.split()) if storyboard.cta else 0

        word_idx = hook_words  # Skip hook words
        for i, scene in enumerate(storyboard.scenes):
            count = scene_word_counts[i]
            end_idx = min(word_idx + count, len(word_timestamps))
            scene.word_timestamps = word_timestamps[word_idx:end_idx]
            word_idx = end_idx

    def _get_voice_for_language(self, language):
        """Get default voice for a language from config."""
        voices = self.config.get("voiceover", {}).get("voices", {})
        lang_map = {"en": "en_male", "sk": "sk_male", "cz": "cz_male", "cs": "cz_male"}
        key = lang_map.get(language, "en_male")
        return voices.get(key, "en-US-GuyNeural")

    def _generate_ai_images(self, scenes):
        """Generate AI images for scenes that need them."""
        try:
            from generators.ai_image import get_image_generator
            gen_config = self.config.get("generators", {}).get("ai_image", {})
            generator = get_image_generator(gen_config)

            for scene in scenes:
                print(f"   [Director] Generating AI image: {scene.visual_prompt[:50]}...")
                path = generator.generate(scene.visual_prompt)
                if path:
                    scene.visual_path = path
                else:
                    # Fallback to stock footage
                    scene.visual_type = VisualType.STOCK_FOOTAGE

            # Unload GPU to free VRAM for potential AI video generation
            if hasattr(generator, 'unload'):
                generator.unload()

        except Exception as e:
            print(f"   [Director] AI image generation failed: {e}")
            for scene in scenes:
                scene.visual_type = VisualType.STOCK_FOOTAGE

    def _generate_ai_videos(self, scenes):
        """Generate AI videos for scenes that need them."""
        try:
            from generators.ai_video import Wan2GPVideoGenerator
            gen_config = self.config.get("generators", {}).get("ai_video", {})
            generator = Wan2GPVideoGenerator(gen_config)

            for scene in scenes:
                print(f"   [Director] Generating AI video: {scene.visual_prompt[:50]}...")
                path = generator.generate_single(scene.visual_prompt, scene.duration)
                if path:
                    scene.visual_path = path
                else:
                    scene.visual_type = VisualType.STOCK_FOOTAGE

        except Exception as e:
            print(f"   [Director] AI video generation failed: {e}")
            for scene in scenes:
                scene.visual_type = VisualType.STOCK_FOOTAGE

    def _generate_other_visuals(self, storyboard):
        """Generate stock footage, infographics, motion graphics, text animations."""
        for scene in storyboard.scenes:
            if scene.visual_path:
                continue  # Already generated (AI)

            if scene.visual_type == VisualType.STOCK_FOOTAGE:
                self._generate_stock(scene)
            elif scene.visual_type == VisualType.INFOGRAPHIC:
                self._generate_infographic(scene)
            elif scene.visual_type == VisualType.MOTION_GRAPHIC:
                self._generate_motion(scene)
            elif scene.visual_type == VisualType.TEXT_ANIMATION:
                self._generate_text_animation(scene)
            elif scene.visual_type == VisualType.COLOR_BACKGROUND:
                pass  # Handled by composer

    def _generate_stock(self, scene):
        """Generate stock footage for a scene."""
        try:
            from generators.stock import StockFootageGenerator
            generator = StockFootageGenerator(self.config)
            paths = generator.generate_for_scene(scene)
            if paths:
                scene.visual_path = paths[0]
        except ImportError:
            from modules.visuals import search_and_download, create_fallback_clip
            clips = search_and_download(query=scene.visual_prompt, count=1)
            if clips:
                scene.visual_path = clips[0]
            else:
                fallback = create_fallback_clip(scene.visual_prompt, duration=int(scene.duration))
                if fallback:
                    scene.visual_path = fallback

    def _generate_infographic(self, scene):
        """Generate animated infographic for a scene."""
        try:
            from generators.infographic import InfographicRenderer
            renderer = InfographicRenderer()
            clip = renderer.render_for_scene(scene)
            if clip is not None:
                scene.visual_clip = clip
            else:
                self._generate_stock(scene)
        except Exception as e:
            print(f"   [Director] Infographic failed: {e}, using fallback")
            self._generate_stock(scene)

    def _generate_motion(self, scene):
        """Generate animated motion graphic for a scene."""
        try:
            from generators.motion import MotionGraphicsRenderer
            renderer = MotionGraphicsRenderer()
            clip = renderer.render_for_scene(scene)
            if clip is not None:
                scene.visual_clip = clip
            else:
                self._generate_stock(scene)
        except Exception as e:
            print(f"   [Director] Motion graphic failed: {e}, using fallback")
            self._generate_stock(scene)

    def _generate_text_animation(self, scene):
        """Generate animated text animation for a scene."""
        try:
            from generators.motion import MotionGraphicsRenderer
            renderer = MotionGraphicsRenderer()
            clip = renderer.render_for_scene(scene)
            if clip is not None:
                scene.visual_clip = clip
            else:
                self._generate_stock(scene)
        except Exception as e:
            print(f"   [Director] Text animation failed: {e}, using fallback")
            self._generate_stock(scene)
