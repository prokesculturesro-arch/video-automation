"""
Transition effects between scenes.

Supports: crossfade, fade to black, slide (left/right), zoom (in/out)
using MoviePy 2.x vfx + custom implementations.
"""

import numpy as np
from PIL import Image
from moviepy import vfx, VideoClip

from brain.storyboard import TransitionType
from utils.animation import ease_out_cubic


class TransitionEngine:
    """Applies transitions between video clips."""

    def apply_transition(self, clip, transition_type, duration=0.5):
        """
        Apply a transition-in effect to a clip.

        Args:
            clip: MoviePy clip
            transition_type: TransitionType enum value
            duration: Transition duration in seconds

        Returns:
            Clip with transition applied
        """
        if duration <= 0:
            return clip

        try:
            if transition_type == TransitionType.CROSSFADE:
                return clip.with_effects([vfx.CrossFadeIn(duration)])

            elif transition_type == TransitionType.FADE_BLACK:
                return clip.with_effects([vfx.FadeIn(duration)])

            elif transition_type == TransitionType.CUT:
                return clip  # No transition

            elif transition_type == TransitionType.SLIDE_LEFT:
                return self._apply_slide(clip, duration, direction="right")

            elif transition_type == TransitionType.SLIDE_RIGHT:
                return self._apply_slide(clip, duration, direction="left")

            elif transition_type == TransitionType.ZOOM_IN:
                return self._apply_zoom_in(clip, duration)

            elif transition_type == TransitionType.ZOOM_OUT:
                return self._apply_zoom_out(clip, duration)

            else:
                return clip.with_effects([vfx.CrossFadeIn(duration)])
        except Exception:
            return clip

    def apply_transition_out(self, clip, transition_type, duration=0.5):
        """Apply a transition-out effect to a clip."""
        if duration <= 0:
            return clip

        try:
            if transition_type == TransitionType.CROSSFADE:
                return clip.with_effects([vfx.CrossFadeOut(duration)])
            elif transition_type == TransitionType.FADE_BLACK:
                return clip.with_effects([vfx.FadeOut(duration)])
            elif transition_type == TransitionType.CUT:
                return clip
            else:
                return clip.with_effects([vfx.CrossFadeOut(duration)])
        except Exception:
            return clip

    def _apply_slide(self, clip, duration, direction="right"):
        """
        Slide-in transition — content enters from the specified side.

        direction="right" means content slides in from the right edge (SLIDE_LEFT).
        direction="left" means content slides in from the left edge (SLIDE_RIGHT).
        """
        try:
            W, H = clip.size
            clip_duration = clip.duration
            original_start = clip.start if hasattr(clip, 'start') else 0

            def slide_filter(get_frame, t):
                frame = get_frame(t)
                if t > duration:
                    return frame

                progress = ease_out_cubic(t / duration)

                if direction == "right":
                    # Slide from right
                    offset = int(W * (1.0 - progress))
                    result = np.zeros_like(frame)
                    if offset < W:
                        result[:, :W - offset] = frame[:, offset:]
                else:
                    # Slide from left
                    offset = int(W * (1.0 - progress))
                    result = np.zeros_like(frame)
                    if offset < W:
                        result[:, offset:] = frame[:, :W - offset]

                return result

            return clip.transform(slide_filter)
        except Exception:
            return clip.with_effects([vfx.CrossFadeIn(duration)])

    def _apply_zoom_in(self, clip, duration):
        """
        Zoom-in transition — clip starts at 0.3x scale, grows to 1.0x with fade.
        """
        try:
            W, H = clip.size

            def zoom_filter(get_frame, t):
                frame = get_frame(t)
                if t > duration:
                    return frame

                progress = ease_out_cubic(t / duration)
                scale = 0.3 + 0.7 * progress  # 0.3 -> 1.0
                alpha = min(1.0, progress * 1.5)  # fade in faster than zoom

                # Scale the frame
                new_w = max(1, int(W * scale))
                new_h = max(1, int(H * scale))

                pil_img = Image.fromarray(frame)
                pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

                # Center on black canvas
                result = np.zeros_like(frame)
                x_off = (W - new_w) // 2
                y_off = (H - new_h) // 2

                # Paste centered
                result[y_off:y_off + new_h, x_off:x_off + new_w] = np.array(pil_img)

                # Apply alpha
                result = (result * alpha).astype(np.uint8)
                return result

            return clip.transform(zoom_filter)
        except Exception:
            return clip.with_effects([vfx.CrossFadeIn(duration)])

    def _apply_zoom_out(self, clip, duration):
        """
        Zoom-out transition — clip starts at 1.5x scale, shrinks to 1.0x with fade.
        """
        try:
            W, H = clip.size

            def zoom_filter(get_frame, t):
                frame = get_frame(t)
                if t > duration:
                    return frame

                progress = ease_out_cubic(t / duration)
                scale = 1.5 - 0.5 * progress  # 1.5 -> 1.0
                alpha = min(1.0, progress * 1.5)

                # Scale the frame (larger than target)
                new_w = max(1, int(W * scale))
                new_h = max(1, int(H * scale))

                pil_img = Image.fromarray(frame)
                pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

                # Crop center to target size
                x_off = (new_w - W) // 2
                y_off = (new_h - H) // 2
                pil_img = pil_img.crop((x_off, y_off, x_off + W, y_off + H))

                result = np.array(pil_img)
                result = (result * alpha).astype(np.uint8)
                return result

            return clip.transform(zoom_filter)
        except Exception:
            return clip.with_effects([vfx.CrossFadeIn(duration)])
