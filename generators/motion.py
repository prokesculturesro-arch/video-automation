"""
Motion Graphics Engine — kinetic text, animated titles, counters, lower thirds.

Returns animated CompositeVideoClip objects (frame-by-frame at 10 FPS).
Uses Pillow -> numpy array -> ImageClip pattern per frame.
"""

import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, CompositeVideoClip

from utils.fonts import get_font
from utils.colors import hex_to_rgb, lerp_color, draw_gradient
from utils.animation import (
    ease_out_cubic, ease_in_out_cubic, ease_out_quad,
    ease_out_bounce, smooth_step, interpolate,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Default dimensions
SCREEN_W = 1080
SCREEN_H = 1920
ANIM_FPS = 10


def _load_presets():
    """Load motion presets from JSON."""
    path = os.path.join(TEMPLATES_DIR, "motion_presets.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class MotionGraphicsRenderer:
    """
    Renders animated motion graphics and kinetic text.

    All effects return CompositeVideoClip objects with frame-by-frame animation.

    Effects:
      - typewriter: Text appears character by character
      - fade_words: Words fade in one by one
      - slide_in: Words slide in from edges
      - kinetic_typography: Dynamic text scaling with bounce
      - counter: Counting number animation
      - lower_third: Name/title lower-third bar sliding in
      - title_card: Full-screen title with fade/scale animation
    """

    def __init__(self, width=SCREEN_W, height=SCREEN_H):
        self.width = width
        self.height = height
        self.presets = _load_presets()

    def render_for_scene(self, scene):
        """
        Render animated motion graphic for a scene.

        Returns CompositeVideoClip (not a file path).
        """
        effect = scene.visual_params.get("effect", "title_card")
        text = scene.visual_params.get("text", scene.text_overlay or scene.text[:80])
        duration = max(2.0, scene.duration)

        render_map = {
            "typewriter": self.render_typewriter_animated,
            "fade_words": self.render_fade_words_animated,
            "slide_in": self.render_slide_in_animated,
            "kinetic_typography": self.render_kinetic_animated,
            "counter": self.render_counter_animated,
            "lower_third": self.render_lower_third_animated,
            "title_card": self.render_title_card_animated,
        }

        renderer = render_map.get(effect, self.render_title_card_animated)

        try:
            clip = renderer(text, duration, scene.visual_params)
            print(f"   [Motion] Animated {effect} ({duration:.1f}s)")
            return clip
        except Exception as e:
            print(f"   [Motion] Error rendering {effect}: {e}")
            return None

    # ─── TYPEWRITER ───────────────────────────────────────────────

    def render_typewriter_animated(self, text, duration, params=None):
        """Typewriter — characters appear one by one with blinking cursor."""
        params = params or {}
        bg_top = tuple(params.get("bg_top", (15, 15, 35)))
        bg_bot = tuple(params.get("bg_bot", (5, 5, 15)))
        text_color = tuple(params.get("text_color", (255, 255, 255)))
        cursor_color = tuple(params.get("cursor_color", (255, 215, 0)))

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        total_chars = len(text)
        type_end = 0.7  # typing takes 70% of duration

        frame_clips = []
        for f in range(total_frames):
            progress = f / max(1, total_frames - 1)

            # Calculate visible characters
            if progress < type_end:
                type_progress = ease_out_cubic(progress / type_end)
                visible = int(total_chars * type_progress)
            else:
                visible = total_chars

            visible_text = text[:visible]
            show_cursor = (f % 10) < 5  # blink every 5 frames

            img = self._draw_typewriter_frame(
                visible_text, show_cursor, bg_top, bg_bot, text_color, cursor_color
            )
            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    def _draw_typewriter_frame(self, text, show_cursor, bg_top, bg_bot, text_color, cursor_color):
        img = Image.new("RGB", (self.width, self.height))
        draw = ImageDraw.Draw(img)
        draw_gradient(draw, self.width, self.height, bg_top, bg_bot)

        font = get_font(52)
        lines = self._wrap_text(text, font, draw, int(self.width * 0.8))
        line_h = 68
        total_h = max(1, len(lines)) * line_h
        y_start = (self.height - total_h) // 2

        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (self.width - tw) // 2
            y = y_start + i * line_h
            draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=font)
            draw.text((x, y), line, fill=text_color, font=font)

        # Cursor
        if show_cursor and lines:
            last_line = lines[-1]
            bbox = draw.textbbox((0, 0), last_line, font=font)
            cursor_x = (self.width + bbox[2] - bbox[0]) // 2 + 5
            cursor_y = y_start + (len(lines) - 1) * line_h
            draw.rectangle(
                [cursor_x, cursor_y, cursor_x + 4, cursor_y + 55],
                fill=cursor_color,
            )

        return img

    # ─── FADE WORDS ───────────────────────────────────────────────

    def render_fade_words_animated(self, text, duration, params=None):
        """Words fade in one by one with glow on the currently appearing word."""
        params = params or {}
        bg_top = tuple(params.get("bg_top", (10, 10, 30)))
        bg_bot = tuple(params.get("bg_bot", (5, 5, 15)))

        words = text.split()
        if not words:
            words = ["..."]

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        word_fade_dur = 0.5  # seconds per word fade
        stagger = 0.4  # seconds between word starts

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur  # current time in seconds

            # Calculate per-word opacity
            word_opacities = []
            active_word = -1
            for wi in range(len(words)):
                word_start = wi * stagger
                word_progress = (t - word_start) / word_fade_dur if word_fade_dur > 0 else 1.0
                opacity = ease_in_out_cubic(max(0.0, min(1.0, word_progress)))
                word_opacities.append(opacity)
                if 0.0 < word_progress < 1.0:
                    active_word = wi

            img = self._draw_fade_words_frame(
                words, word_opacities, active_word, bg_top, bg_bot
            )
            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    def _draw_fade_words_frame(self, words, opacities, active_word, bg_top, bg_bot):
        img = Image.new("RGB", (self.width, self.height))
        draw = ImageDraw.Draw(img)
        draw_gradient(draw, self.width, self.height, bg_top, bg_bot)

        font = get_font(56)
        space_w = draw.textlength(" ", font=font)

        # Word wrap into lines
        lines = []
        current_line = []
        current_width = 0
        max_w = self.width * 0.8

        for i, word in enumerate(words):
            ww = draw.textlength(word, font=font)
            if current_width + ww + space_w > max_w and current_line:
                lines.append(current_line)
                current_line = [(i, word)]
                current_width = ww
            else:
                current_line.append((i, word))
                current_width += ww + space_w
        if current_line:
            lines.append(current_line)

        line_h = 72
        total_h = len(lines) * line_h
        y_start = (self.height - total_h) // 2

        for li, line_words in enumerate(lines):
            # Calculate total line width for centering
            line_text = " ".join(w for _, w in line_words)
            bbox = draw.textbbox((0, 0), line_text, font=font)
            total_w = bbox[2] - bbox[0]
            x = (self.width - total_w) // 2
            y = y_start + li * line_h

            for idx, word in line_words:
                opacity = opacities[idx] if idx < len(opacities) else 1.0
                alpha = int(255 * opacity)

                if idx == active_word:
                    # Glow effect — larger shadow
                    glow_color = (255, 215, 0)
                    gc = tuple(int(c * opacity) for c in glow_color)
                    draw.text((x - 1, y - 1), word, fill=gc, font=font)
                    draw.text((x + 3, y + 3), word, fill=gc, font=font)

                color = (alpha, alpha, alpha)
                draw.text((x + 2, y + 2), word, fill=(0, 0, min(alpha, 30)), font=font)
                draw.text((x, y), word, fill=color, font=font)
                x += draw.textlength(word + " ", font=font)

        return img

    # ─── SLIDE IN ─────────────────────────────────────────────────

    def render_slide_in_animated(self, text, duration, params=None):
        """Words slide in from alternating edges."""
        params = params or {}
        bg_top = tuple(params.get("bg_top", (20, 10, 30)))
        bg_bot = tuple(params.get("bg_bot", (5, 5, 15)))

        words = text.split()
        if not words:
            words = ["..."]

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        stagger = 0.4

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, bg_top, bg_bot)

            font = get_font(60)
            line_h = 80
            total_h = len(words) * line_h
            y_start = (self.height - total_h) // 2

            for i, word in enumerate(words):
                word_start = i * stagger
                word_progress = (t - word_start) / 0.6 if t > word_start else 0.0
                word_progress = max(0.0, min(1.0, word_progress))

                bbox = draw.textbbox((0, 0), word, font=font)
                tw = bbox[2] - bbox[0]

                if i % 2 == 0:
                    final_x = int(self.width * 0.1)
                    start_x = -tw - 50
                else:
                    final_x = int(self.width * 0.9) - tw
                    start_x = self.width + 50

                x = int(interpolate(start_x, final_x, word_progress, ease_out_cubic))
                y = y_start + i * line_h
                color = (255, 215, 0) if i % 3 == 0 else (255, 255, 255)

                alpha = int(255 * ease_out_cubic(word_progress))
                c = tuple(int(v * alpha / 255) for v in color)

                draw.text((x + 2, y + 2), word, fill=(0, 0, 0), font=font)
                draw.text((x, y), word, fill=c, font=font)

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── KINETIC TYPOGRAPHY ───────────────────────────────────────

    def render_kinetic_animated(self, text, duration, params=None):
        """Words pop in with bounce scale effect at different sizes/positions."""
        params = params or {}
        bg_top = tuple(params.get("bg_top", (15, 15, 40)))
        bg_bot = tuple(params.get("bg_bot", (5, 5, 10)))

        words = text.split()
        if not words:
            words = ["..."]

        # Pre-calculate sizes and positions for each word
        random.seed(hash(text) % 10000)  # deterministic for same text
        word_sizes = []
        for word in words:
            if len(word) > 5:
                word_sizes.append(random.randint(64, 80))
            else:
                word_sizes.append(random.randint(40, 56))

        offsets = [0.5, 0.35, 0.65, 0.45, 0.55]

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        stagger = 0.3

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, bg_top, bg_bot)

            total_h = sum(s + 20 for s in word_sizes)
            y = (self.height - total_h) // 2

            for i, word in enumerate(words):
                word_start = i * stagger
                word_progress = (t - word_start) / 0.5 if t > word_start else 0.0
                word_progress = max(0.0, min(1.0, word_progress))

                # Scale: 0 -> 1.2 -> 1.0 via bounce
                scale = ease_out_bounce(word_progress)
                font_size = max(8, int(word_sizes[i] * scale))
                font = get_font(font_size)

                bbox = draw.textbbox((0, 0), word, font=font)
                tw = bbox[2] - bbox[0]
                x = int(self.width * offsets[i % len(offsets)] - tw / 2)

                color = (255, 215, 0) if word_sizes[i] > 60 else (200, 200, 220)
                alpha = int(255 * min(1.0, word_progress * 2))
                c = tuple(int(v * alpha / 255) for v in color)

                if word_progress > 0:
                    draw.text((x + 2, y + 2), word, fill=(0, 0, 0), font=font)
                    draw.text((x, y), word, fill=c, font=font)

                y += word_sizes[i] + 20

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── COUNTER ──────────────────────────────────────────────────

    def render_counter_animated(self, text, duration, params=None):
        """Animated counter — number counts up with label fade-in."""
        params = params or {}
        target_number = params.get("number", 100)
        label = params.get("label", text)
        suffix = params.get("suffix", "%")
        bg_top = tuple(params.get("bg_top", (10, 20, 40)))
        bg_bot = tuple(params.get("bg_bot", (5, 10, 20)))

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        count_end = 0.7  # counting takes 70% of duration

        frame_clips = []
        for f in range(total_frames):
            progress = f / max(1, total_frames - 1)

            # Count progress
            if progress < count_end:
                count_progress = ease_out_cubic(progress / count_end)
            else:
                count_progress = 1.0
            current_number = int(target_number * count_progress)

            # Label opacity (fades in during last 30%)
            if progress > count_end:
                label_opacity = ease_in_out_cubic((progress - count_end) / (1.0 - count_end))
            else:
                label_opacity = 0.0

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, bg_top, bg_bot)

            # Big number
            number_font = get_font(120)
            number_text = f"{current_number}{suffix}"
            bbox = draw.textbbox((0, 0), number_text, font=number_font)
            tw = bbox[2] - bbox[0]
            x = (self.width - tw) // 2
            y = self.height // 2 - 100

            draw.text((x + 3, y + 3), number_text, fill=(0, 0, 0), font=number_font)
            draw.text((x, y), number_text, fill=(255, 215, 0), font=number_font)

            # Label
            if label_opacity > 0:
                label_font = get_font(36)
                bbox = draw.textbbox((0, 0), label, font=label_font)
                tw = bbox[2] - bbox[0]
                x = (self.width - tw) // 2
                alpha = int(220 * label_opacity)
                draw.text((x, y + 150), label, fill=(alpha, alpha, alpha), font=label_font)

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── LOWER THIRD ──────────────────────────────────────────────

    def render_lower_third_animated(self, text, duration, params=None):
        """Lower-third bar slides in from left, then text types on."""
        params = params or {}
        subtitle = params.get("subtitle", "")
        accent_color = tuple(params.get("accent_color", (255, 215, 0)))
        bg_top = tuple(params.get("bg_top", (15, 15, 35)))
        bg_bot = tuple(params.get("bg_bot", (5, 5, 15)))

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        slide_dur = 0.5  # bar slide-in time in seconds
        total_chars = len(text)

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, bg_top, bg_bot)

            bar_y = int(self.height * 0.75)
            bar_h = 120

            # Phase 1: Bar slides in
            if t < slide_dur:
                bar_progress = ease_out_cubic(t / slide_dur)
            else:
                bar_progress = 1.0

            bar_right = int(self.width * bar_progress)

            # Accent stripe
            draw.rectangle([0, bar_y, bar_right, bar_y + 5], fill=accent_color)
            # Dark bar
            draw.rectangle([0, bar_y + 5, bar_right, bar_y + bar_h], fill=(20, 20, 30))

            # Phase 2: Text types on
            if t > slide_dur:
                text_progress = (t - slide_dur) / max(0.1, duration - slide_dur)
                text_progress = min(1.0, text_progress)
                visible_chars = int(total_chars * ease_out_cubic(text_progress))
                visible_text = text[:visible_chars]

                font = get_font(42)
                draw.text((60, bar_y + 20), visible_text, fill=(255, 255, 255), font=font)

                if subtitle and text_progress > 0.5:
                    sub_progress = (text_progress - 0.5) / 0.5
                    sub_alpha = int(200 * min(1.0, sub_progress))
                    sub_font = get_font(28)
                    draw.text((60, bar_y + 70), subtitle,
                              fill=(sub_alpha, sub_alpha, int(sub_alpha * 0.9)), font=sub_font)

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── TITLE CARD ───────────────────────────────────────────────

    def render_title_card_animated(self, text, duration, params=None):
        """Title card with fade-in, scale, and expanding decorative lines."""
        params = params or {}
        accent_color = tuple(params.get("accent_color", (255, 215, 0)))
        bg_top = tuple(params.get("bg_top", (25, 15, 40)))
        bg_bot = tuple(params.get("bg_bot", (5, 5, 10)))

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        fade_end = 0.4  # fade-in takes 40% of duration

        frame_clips = []
        for f in range(total_frames):
            progress = f / max(1, total_frames - 1)

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, bg_top, bg_bot)

            # Opacity + scale
            if progress < fade_end:
                anim_t = ease_in_out_cubic(progress / fade_end)
                opacity = anim_t
                scale = 1.0 + 0.05 * (1.0 - anim_t)  # 1.05 -> 1.0
            else:
                opacity = 1.0
                scale = 1.0

            # Decorative lines expand from center
            line_progress = ease_out_cubic(min(1.0, progress / 0.6))
            cx = self.width // 2
            line_half = int((self.width // 2 - 100) * line_progress)
            line_color = tuple(int(c * opacity) for c in accent_color)

            if line_half > 5:
                draw.rectangle(
                    [cx - line_half, self.height // 2 - 150,
                     cx + line_half, self.height // 2 - 148],
                    fill=line_color
                )
                draw.rectangle(
                    [cx - line_half, self.height // 2 + 120,
                     cx + line_half, self.height // 2 + 122],
                    fill=line_color
                )

            # Title text
            font_size = max(8, int(56 * scale))
            font = get_font(font_size)
            lines = self._wrap_text(text, font, draw, int(self.width * 0.75))
            line_h = int(70 * scale)
            total_h = len(lines) * line_h
            y_start = (self.height - total_h) // 2

            alpha = int(255 * opacity)

            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                tw = bbox[2] - bbox[0]
                x = (self.width - tw) // 2
                y = y_start + i * line_h

                if alpha > 10:
                    shadow_a = max(0, alpha - 200)
                    draw.text((x + 2, y + 2), line,
                              fill=(shadow_a, shadow_a, shadow_a), font=font)
                    draw.text((x, y), line,
                              fill=(alpha, alpha, alpha), font=font)

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── HELPERS ──────────────────────────────────────────────────

    def _wrap_text(self, text, font, draw, max_width):
        """Word-wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current = ""

        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        return lines if lines else [text]
