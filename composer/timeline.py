"""
Timeline — converts a Storyboard into a MoviePy layer stack.

Takes a completed Storyboard (with visual_path and audio filled in)
and builds the final composited video.
"""

import os
import random
import sys

import numpy as np
from PIL import Image
from moviepy import (
    VideoFileClip, AudioFileClip, ImageClip, TextClip,
    CompositeVideoClip, CompositeAudioClip, ColorClip, VideoClip,
    concatenate_videoclips, concatenate_audioclips,
    vfx, afx,
)
from utils.animation import ease_in_out_cubic, smooth_step

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Ensure FFmpeg is available
try:
    import imageio_ffmpeg
    import moviepy.config as mpy_config
    mpy_config.FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    pass

from brain.storyboard import Storyboard, VisualType, TransitionType
from composer.effects import TransitionEngine
from composer.export import export_video


def _resize_to_fill(clip, target_w, target_h):
    """Resize clip to fill target dimensions (CSS object-fit: cover)."""
    if clip.w == 0 or clip.h == 0:
        return clip.resized((target_w, target_h))

    clip_ratio = clip.w / clip.h
    target_ratio = target_w / target_h

    if clip_ratio > target_ratio:
        new_h = target_h
        new_w = int(clip_ratio * target_h)
    else:
        new_w = target_w
        new_h = int(target_w / clip_ratio)

    resized = clip.resized((new_w, new_h))
    return resized.cropped(
        x_center=new_w / 2,
        y_center=new_h / 2,
        width=target_w,
        height=target_h,
    )


def _apply_ken_burns(clip, duration, W, H):
    """
    Apply Ken Burns (pan/zoom) effect to a static image clip.

    Randomly chooses one of 5 effects: zoom_in, zoom_out, pan_left, pan_right, diagonal.
    The image is upscaled 20% to provide room for movement.
    """
    try:
        # Get the static frame
        frame = clip.get_frame(0)
        pil_img = Image.fromarray(frame)

        # Upscale by 20% for movement room
        up_w = int(W * 1.2)
        up_h = int(H * 1.2)
        pil_img = pil_img.resize((up_w, up_h), Image.LANCZOS)

        effects = ["zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal"]
        effect = random.choice(effects)

        def make_frame(t):
            progress = smooth_step(t / max(0.01, duration))

            if effect == "zoom_in":
                # 1.0x -> 1.15x zoom into center
                scale = 1.0 + 0.15 * progress
                cw = int(up_w / scale)
                ch = int(up_h / scale)
                x1 = (up_w - cw) // 2
                y1 = (up_h - ch) // 2

            elif effect == "zoom_out":
                # 1.15x -> 1.0x zoom out from center
                scale = 1.15 - 0.15 * progress
                cw = int(up_w / scale)
                ch = int(up_h / scale)
                x1 = (up_w - cw) // 2
                y1 = (up_h - ch) // 2

            elif effect == "pan_left":
                # Slow pan left with mild zoom
                scale = 1.05
                cw = int(up_w / scale)
                ch = int(up_h / scale)
                max_shift = up_w - cw
                x1 = int(max_shift * (1.0 - progress))
                y1 = (up_h - ch) // 2

            elif effect == "pan_right":
                # Slow pan right with mild zoom
                scale = 1.05
                cw = int(up_w / scale)
                ch = int(up_h / scale)
                max_shift = up_w - cw
                x1 = int(max_shift * progress)
                y1 = (up_h - ch) // 2

            else:  # diagonal
                # Zoom + diagonal pan
                scale = 1.0 + 0.1 * progress
                cw = int(up_w / scale)
                ch = int(up_h / scale)
                max_shift_x = up_w - cw
                max_shift_y = up_h - ch
                x1 = int(max_shift_x * progress * 0.6)
                y1 = int(max_shift_y * progress * 0.6)

            # Crop and resize back to target
            cropped = pil_img.crop((x1, y1, x1 + cw, y1 + ch))
            resized = cropped.resize((W, H), Image.LANCZOS)
            return np.array(resized)

        kb_clip = VideoClip(make_frame, duration=duration).with_fps(10)
        return kb_clip

    except Exception as e:
        print(f"   [Timeline] Ken Burns failed: {e}, using static image")
        return clip


def build_video_from_storyboard(storyboard, output_path, config):
    """
    Build final video from a completed Storyboard.

    This is the main entry point for the new composer pipeline.
    It handles mixed visual types (video, image, infographic, motion) in one timeline.

    Args:
        storyboard: Storyboard object with visual_path and audio filled
        output_path: Output MP4 path
        config: Full config dict

    Returns:
        Path to output video
    """
    video_config = config.get("video", {})
    W = video_config.get("width", 1080)
    H = video_config.get("height", 1920)
    FPS = video_config.get("fps", 30)

    # Get the full audio
    audio_path = None
    total_duration = storyboard.total_audio_duration

    for scene in storyboard.scenes:
        if scene.audio_path:
            audio_path = scene.audio_path
            if scene.audio_duration:
                total_duration = scene.audio_duration
            break

    if total_duration <= 0:
        total_duration = storyboard.target_duration

    print(f"   [Timeline] Building {W}x{H} video, {total_duration:.1f}s")

    # Build background layer from scene visuals
    scene_clips = _build_scene_clips(storyboard, total_duration, W, H)

    # Build audio
    vo_audio = None
    if audio_path:
        vo_audio = AudioFileClip(audio_path)

    # Build subtitle clips
    subtitle_clips = _build_subtitles(storyboard, W, H, config)

    # Build text overlays
    text_overlays = _build_text_overlays(storyboard, W, H, config)

    # Background music
    music_clips = _build_music(total_duration, config)

    # Mix audio
    audio_tracks = []
    if vo_audio:
        audio_tracks.append(vo_audio)
    audio_tracks.extend(music_clips)

    if len(audio_tracks) > 1:
        final_audio = CompositeAudioClip(audio_tracks)
    elif audio_tracks:
        final_audio = audio_tracks[0]
    else:
        final_audio = None

    # Logo and CTA
    logo_clip = _build_logo(total_duration, W, H, config)
    cta_clip = _build_cta(storyboard, total_duration, W, H, config)

    # Compose all layers
    print("   [Timeline] Composing layers...")
    layers = scene_clips
    layers.extend(subtitle_clips)
    layers.extend(text_overlays)
    if logo_clip:
        layers.append(logo_clip)
    if cta_clip:
        layers.append(cta_clip)

    final_video = CompositeVideoClip(layers, size=(W, H))
    final_video = final_video.with_duration(total_duration)

    if final_audio:
        final_video = final_video.with_audio(final_audio)

    # Global fade
    final_video = final_video.with_effects([
        vfx.FadeIn(0.5),
        vfx.FadeOut(0.5),
    ])

    # Export
    result = export_video(final_video, output_path, config)

    # Cleanup
    try:
        if vo_audio:
            vo_audio.close()
        final_video.close()
        # Close visual_clip objects
        for scene in storyboard.scenes:
            if scene.visual_clip is not None:
                try:
                    scene.visual_clip.close()
                except Exception:
                    pass
    except Exception:
        pass

    return result


def _build_scene_clips(storyboard, total_duration, W, H):
    """Build visual clips from storyboard scenes."""
    clips = []
    elapsed = 0.0

    # Calculate per-scene duration from audio
    num_scenes = len(storyboard.scenes)
    if num_scenes == 0:
        return [ColorClip(size=(W, H), color=(10, 10, 15)).with_duration(total_duration)]

    # Distribute duration across scenes proportionally
    scene_durations = []
    hook_time = 3.0  # Reserve for hook
    cta_time = 3.0 if storyboard.cta else 0.0
    content_time = total_duration - hook_time - cta_time
    per_scene = max(3.0, content_time / num_scenes)

    for scene in storyboard.scenes:
        scene_durations.append(per_scene)

    # Build clip for each scene
    elapsed = hook_time  # Start after hook

    for i, scene in enumerate(storyboard.scenes):
        dur = scene_durations[i]

        if scene.visual_clip is not None:
            # Animated clip from motion graphics or infographics
            clip = scene.visual_clip
            if clip.duration and clip.duration != dur:
                if clip.duration > dur:
                    clip = clip.subclipped(0, dur)
                else:
                    # Extend by holding last frame
                    clip = clip.with_duration(dur)
        elif scene.visual_path:
            try:
                if scene.visual_path.lower().endswith((".png", ".jpg", ".jpeg")):
                    clip = ImageClip(scene.visual_path).with_duration(dur)
                    clip = _resize_to_fill(clip, W, H)
                    clip = _apply_ken_burns(clip, dur, W, H)
                elif scene.visual_path.lower().endswith((".mp4", ".avi", ".mov", ".webm")):
                    clip = VideoFileClip(scene.visual_path, audio=False)
                    clip = _resize_to_fill(clip, W, H)
                    if clip.duration > dur:
                        clip = clip.subclipped(0, dur)
                    elif clip.duration < dur:
                        # Loop short clips
                        loops = int(dur / clip.duration) + 1
                        clip = concatenate_videoclips([clip] * loops).subclipped(0, dur)
                else:
                    clip = ColorClip(size=(W, H), color=(10, 10, 15)).with_duration(dur)
            except Exception as e:
                print(f"   [Timeline] Warning: Could not load {scene.visual_path}: {e}")
                clip = ColorClip(size=(W, H), color=(10, 10, 15)).with_duration(dur)
        else:
            # No visual, use dark background
            clip = ColorClip(size=(W, H), color=(10, 10, 15)).with_duration(dur)

        clip = clip.with_start(elapsed)

        # Apply transition
        transition = TransitionEngine()
        clip = transition.apply_transition(clip, scene.transition_in, scene.transition_duration)

        clips.append(clip)
        elapsed += dur

    # If no clips at all, create a solid background
    if not clips:
        clips = [ColorClip(size=(W, H), color=(10, 10, 15)).with_duration(total_duration)]

    # Add a base background that covers the whole duration
    bg = ColorClip(size=(W, H), color=(10, 10, 15)).with_duration(total_duration)
    clips.insert(0, bg)

    return clips


def _build_subtitles(storyboard, W, H, config):
    """Build subtitle clips from scene word timestamps."""
    sub_config = config.get("subtitles", {})
    if not sub_config.get("enabled", True):
        return []

    # Collect all word timestamps
    all_timestamps = []
    for scene in storyboard.scenes:
        all_timestamps.extend(scene.word_timestamps)

    if not all_timestamps:
        return []

    from modules.subtitles import create_subtitles
    return create_subtitles(all_timestamps, W, H, sub_config)


def _build_text_overlays(storyboard, W, H, config):
    """Build text overlay clips for each scene."""
    text_config = config.get("visuals", {}).get("text", {})
    overlays = []
    elapsed = 3.0  # After hook

    num_scenes = len(storyboard.scenes)
    if num_scenes == 0:
        return []

    total = storyboard.total_audio_duration or storyboard.target_duration
    hook_time = 3.0
    cta_time = 3.0 if storyboard.cta else 0.0
    content_time = total - hook_time - cta_time
    per_scene = max(3.0, content_time / num_scenes)

    for scene in storyboard.scenes:
        if scene.text_overlay:
            from modules.composer import create_text_overlay
            clip = create_text_overlay(
                scene.text_overlay, per_scene, elapsed, W, H, text_config
            )
            if clip:
                overlays.append(clip)
        elapsed += per_scene

    return overlays


def _build_music(total_duration, config):
    """Build background music track."""
    import random

    music_config = config.get("music", {})
    if not music_config.get("enabled", True):
        return []

    music_dir = os.path.join(BASE_DIR, "assets", "music")
    if not os.path.exists(music_dir):
        return []

    music_files = [
        os.path.join(music_dir, f) for f in os.listdir(music_dir)
        if f.endswith((".mp3", ".wav", ".ogg"))
    ]

    if not music_files:
        return []

    try:
        music_path = random.choice(music_files)
        music = AudioFileClip(music_path)
        if music.duration < total_duration:
            loops = int(total_duration / music.duration) + 1
            music = concatenate_audioclips([music] * loops)
        music = music.subclipped(0, total_duration)

        vol = music_config.get("volume", 0.15)
        music = music.with_volume_scaled(vol)

        fade_in = music_config.get("fade_in", 1.0)
        fade_out = music_config.get("fade_out", 2.0)
        music = music.with_effects([
            afx.AudioFadeIn(fade_in),
            afx.AudioFadeOut(fade_out),
        ])

        return [music]
    except Exception as e:
        print(f"   [Timeline] Warning: Could not load music: {e}")
        return []


def _build_logo(total_duration, W, H, config):
    """Build logo overlay."""
    from modules.composer import add_logo
    brand_config = config.get("brand", {})
    if brand_config.get("logo"):
        return add_logo(
            brand_config["logo"],
            total_duration, W, H,
            position=brand_config.get("logo_position", "top_right"),
            size=brand_config.get("logo_size", 80),
            opacity=brand_config.get("logo_opacity", 0.7),
        )
    return None


def _build_cta(storyboard, total_duration, W, H, config):
    """Build CTA overlay at end of video."""
    brand_config = config.get("brand", {})
    cta_config = brand_config.get("cta", {})

    if not cta_config.get("enabled") or not storyboard.cta:
        return None

    from modules.composer import create_cta_clip
    cta_dur = cta_config.get("duration", 3)
    clip = create_cta_clip(storyboard.cta, cta_dur, W, H, brand_config)
    if clip:
        clip = clip.with_start(total_duration - cta_dur)
    return clip
