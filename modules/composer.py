"""
Main video composition engine using MoviePy 2.x + FFmpeg.
Takes script + voiceover + visuals → produces final video.
"""

import os
import sys
import random

import numpy as np
from moviepy import (
    VideoFileClip, AudioFileClip, ImageClip, TextClip,
    CompositeVideoClip, CompositeAudioClip, ColorClip,
    concatenate_videoclips, concatenate_audioclips,
    vfx, afx,
)

from modules.subtitles import create_subtitles

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure imageio-ffmpeg's bundled ffmpeg is available
try:
    import imageio_ffmpeg
    import moviepy.config as mpy_config
    mpy_config.FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    pass


def resize_to_fill(clip, target_w, target_h):
    """
    Resize clip to fill target dimensions, cropping excess.
    Like CSS 'object-fit: cover'.
    """
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


def create_background_from_footage(footage_paths, target_duration, target_w, target_h):
    """
    Create a background video from stock footage clips.
    Clips are resized to fill, trimmed, and concatenated.
    """
    if not footage_paths:
        return ColorClip(
            size=(target_w, target_h), color=(10, 10, 15)
        ).with_duration(target_duration)

    clips = []
    total_dur = 0

    for path in footage_paths:
        if total_dur >= target_duration:
            break

        try:
            if path.lower().endswith((".png", ".jpg", ".jpeg")):
                # Static image — Ken Burns zoom effect
                clip = ImageClip(path).with_duration(8)
                clip = resize_to_fill(clip, target_w, target_h)
            else:
                clip = VideoFileClip(path, audio=False)
                clip = resize_to_fill(clip, target_w, target_h)

            # Trim if needed
            remaining = target_duration - total_dur
            if clip.duration > remaining:
                clip = clip.subclipped(0, remaining)

            clips.append(clip)
            total_dur += clip.duration

        except Exception as e:
            print(f"   [Composer] Warning: Could not load {path}: {e}")
            continue

    if not clips:
        return ColorClip(
            size=(target_w, target_h), color=(10, 10, 15)
        ).with_duration(target_duration)

    # If not enough footage, loop
    if total_dur < target_duration:
        remaining = target_duration - total_dur
        last_clip = clips[-1]
        if last_clip.duration > 0:
            loops_needed = int(remaining / last_clip.duration) + 1
            for _ in range(loops_needed):
                if total_dur >= target_duration:
                    break
                trim = min(last_clip.duration, target_duration - total_dur)
                loop_clip = last_clip.subclipped(0, trim)
                clips.append(loop_clip)
                total_dur += trim

    bg = concatenate_videoclips(clips, method="compose")

    if bg.duration > target_duration:
        bg = bg.subclipped(0, target_duration)

    return bg


def create_text_overlay(text, duration, start_time, video_w, video_h, config=None):
    """Create a text overlay clip for a segment."""
    if not text:
        return None

    if config is None:
        config = {}

    font_path = os.path.join(BASE_DIR, "assets", "fonts", "Montserrat-Bold.ttf")
    if not os.path.exists(font_path):
        font_path = "Arial"

    font_size = config.get("font_size", 64)
    color = config.get("color", "#FFFFFF")
    stroke_color = config.get("stroke_color", "#000000")
    stroke_width = config.get("stroke_width", 3)
    max_width = int(video_w * config.get("max_width_ratio", 0.85))

    try:
        clip = (
            TextClip(
                text=text,
                font_size=font_size,
                color=color,
                font=font_path,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                method="caption",
                size=(max_width, None),
                text_align="center",
            )
            .with_duration(duration)
            .with_start(start_time)
            .with_position(("center", int(video_h * 0.25)))
            .with_effects([vfx.CrossFadeIn(0.3), vfx.CrossFadeOut(0.3)])
        )
        return clip
    except Exception as e:
        print(f"   [Composer] Warning: Could not create text overlay: {e}")
        return None


def add_logo(logo_path, duration, video_w, video_h, position="top_right",
             size=80, opacity=0.7):
    """Create a logo overlay clip."""
    if not logo_path or not os.path.exists(logo_path):
        return None

    try:
        logo = ImageClip(logo_path).with_duration(duration)

        # Resize maintaining aspect ratio
        ratio = size / logo.h
        logo = logo.resized(ratio)

        # Set opacity
        logo = logo.with_opacity(opacity)

        # Position
        margin = 30
        positions = {
            "top_right": (video_w - logo.w - margin, margin),
            "top_left": (margin, margin),
            "bottom_right": (video_w - logo.w - margin, video_h - logo.h - margin),
            "bottom_left": (margin, video_h - logo.h - margin),
        }
        pos = positions.get(position, positions["top_right"])
        logo = logo.with_position(pos)

        return logo
    except Exception as e:
        print(f"   [Composer] Warning: Could not load logo: {e}")
        return None


def create_cta_clip(text, duration, video_w, video_h, config=None):
    """Create a Call-to-Action overlay for the end of the video."""
    if not text:
        return None

    try:
        font_path = os.path.join(BASE_DIR, "assets", "fonts", "Montserrat-Bold.ttf")
        if not os.path.exists(font_path):
            font_path = "Arial"

        accent = "#FFD700"
        if config and "colors" in config:
            accent = config["colors"].get("accent", accent)

        clip = (
            TextClip(
                text=text,
                font_size=56,
                color=accent,
                font=font_path,
                stroke_color="black",
                stroke_width=2,
                method="caption",
                size=(int(video_w * 0.8), None),
                text_align="center",
            )
            .with_duration(duration)
            .with_position(("center", "center"))
            .with_effects([vfx.CrossFadeIn(0.5)])
        )
        return clip
    except Exception:
        return None


def compose_video(script, voiceover, footage_clips, output_path, config):
    """
    Compose the final video from all components.

    Args:
        script: Dict from script_generator
        voiceover: Dict from voiceover module (audio_path, duration, word_timestamps)
        footage_clips: List of file paths from visuals module
        output_path: Where to save the output MP4
        config: Full config dict from config.yaml

    Returns:
        str: Path to the output video file
    """
    video_config = config.get("video", {})
    W = video_config.get("width", 1080)
    H = video_config.get("height", 1920)
    FPS = video_config.get("fps", 30)

    total_duration = voiceover["duration"]
    print(f"   [Composer] Composing {W}x{H} video, {total_duration:.1f}s")

    # ===== STEP 1: Background footage =====
    print("   [Composer] Step 1: Building background...")
    bg_clip = create_background_from_footage(footage_clips, total_duration, W, H)

    # ===== STEP 2: Voiceover audio =====
    print("   [Composer] Step 2: Loading voiceover...")
    vo_audio = AudioFileClip(voiceover["audio_path"])

    # ===== STEP 3: Subtitles =====
    subtitle_clips = []
    sub_config = config.get("subtitles", {})
    if sub_config.get("enabled", True) and voiceover.get("word_timestamps"):
        print("   [Composer] Step 3: Creating subtitles...")
        subtitle_clips = create_subtitles(
            voiceover["word_timestamps"], W, H, sub_config
        )
        print(f"   [Composer] Created {len(subtitle_clips)} subtitle clips")
    else:
        print("   [Composer] Step 3: Subtitles disabled, skipping")

    # ===== STEP 4: Text overlays per segment =====
    print("   [Composer] Step 4: Creating text overlays...")
    text_overlays = []
    text_config = config.get("visuals", {}).get("text", {})
    elapsed = 3.0  # After hook

    for segment in script.get("segments", []):
        overlay_text = segment.get("text_overlay", "")
        seg_duration = segment.get("duration", 8)

        if overlay_text:
            clip = create_text_overlay(
                overlay_text, seg_duration, elapsed, W, H, text_config
            )
            if clip:
                text_overlays.append(clip)

        elapsed += seg_duration

    # ===== STEP 5: Background music =====
    print("   [Composer] Step 5: Mixing audio...")
    music_config = config.get("music", {})
    audio_tracks = [vo_audio]

    if music_config.get("enabled", True):
        music_dir = os.path.join(BASE_DIR, "assets", "music")
        if os.path.exists(music_dir):
            music_files = [
                os.path.join(music_dir, f) for f in os.listdir(music_dir)
                if f.endswith((".mp3", ".wav", ".ogg"))
            ]
            if music_files:
                music_path = random.choice(music_files)
                try:
                    music = AudioFileClip(music_path)
                    # Loop if shorter than video
                    if music.duration < total_duration:
                        loops = int(total_duration / music.duration) + 1
                        music = concatenate_audioclips([music] * loops)
                    music = music.subclipped(0, total_duration)
                    # Set volume
                    vol = music_config.get("volume", 0.15)
                    music = music.with_volume_scaled(vol)
                    # Fade in/out
                    fade_in = music_config.get("fade_in", 1.0)
                    fade_out = music_config.get("fade_out", 2.0)
                    music = music.with_effects([
                        afx.AudioFadeIn(fade_in),
                        afx.AudioFadeOut(fade_out),
                    ])
                    audio_tracks.append(music)
                    print(f"   [Composer] Added background music: {os.path.basename(music_path)}")
                except Exception as e:
                    print(f"   [Composer] Warning: Could not load music: {e}")

    # Mix all audio
    if len(audio_tracks) > 1:
        final_audio = CompositeAudioClip(audio_tracks)
    else:
        final_audio = audio_tracks[0]

    # ===== STEP 6: Logo =====
    print("   [Composer] Step 6: Adding overlays...")
    logo_clip = None
    brand_config = config.get("brand", {})
    if brand_config.get("logo"):
        logo_clip = add_logo(
            brand_config["logo"],
            total_duration, W, H,
            position=brand_config.get("logo_position", "top_right"),
            size=brand_config.get("logo_size", 80),
            opacity=brand_config.get("logo_opacity", 0.7),
        )

    # ===== STEP 7: CTA overlay =====
    cta_clip = None
    cta_config = brand_config.get("cta", {})
    if cta_config.get("enabled") and script.get("cta"):
        cta_dur = cta_config.get("duration", 3)
        cta_clip = create_cta_clip(
            script["cta"], cta_dur, W, H, brand_config
        )
        if cta_clip:
            cta_clip = cta_clip.with_start(total_duration - cta_dur)

    # ===== COMPOSE ALL LAYERS =====
    print("   [Composer] Composing layers...")
    layers = [bg_clip]
    layers.extend(subtitle_clips)
    layers.extend(text_overlays)
    if logo_clip:
        layers.append(logo_clip)
    if cta_clip:
        layers.append(cta_clip)

    final_video = CompositeVideoClip(layers, size=(W, H))
    final_video = final_video.with_duration(total_duration)
    final_video = final_video.with_audio(final_audio)

    # Fade in/out
    final_video = final_video.with_effects([
        vfx.FadeIn(0.5),
        vfx.FadeOut(0.5),
    ])

    # ===== EXPORT =====
    print(f"   [Composer] Exporting to {output_path}...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    codec = video_config.get("codec", "libx264")
    audio_codec = video_config.get("audio_codec", "aac")
    bitrate = video_config.get("bitrate", "4M")

    final_video.write_videofile(
        output_path,
        fps=FPS,
        codec=codec,
        audio_codec=audio_codec,
        bitrate=bitrate,
        preset="medium",
        threads=4,
        logger="bar",
    )

    # Cleanup
    try:
        bg_clip.close()
        vo_audio.close()
        final_video.close()
    except Exception:
        pass

    print(f"   [Composer] Done! Output: {output_path}")
    return output_path
