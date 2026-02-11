#!/usr/bin/env python3
"""
ULTIMATE AI VIDEO CREATOR — Generate a single short-form video.

STANDARD MODE (unchanged):
  python generate.py --topic "Benefits of CBD for sleep"
  python generate.py --topic "3 things about hemp" --lang sk --duration 30
  python generate.py --topic "wellness tips" --voice en_dramatic --style humor

CONVERSATION MODE (unchanged):
  python generate.py --topic "sleep tips" --mode chat
  python generate.py --topic "wellness" --mode podcast
  python generate.py --topic "motivation" --mode story
  python generate.py --topic "custom" --mode chat --script conversation.txt

AUTO MODE (NEW — AI Director):
  python generate.py --topic "AI future" --mode auto --brain template
  python generate.py --topic "Gesundheit" --mode auto --lang de
  python generate.py --topic "CBD" --mode auto --brain claude --visuals mixed

MULTI-LANGUAGE (NEW — any language):
  python generate.py --topic "Gesundheit" --lang de --mode standard
  python generate.py --topic "Santé" --lang fr --mode auto

VOICE DISCOVERY (NEW):
  python generate.py --list-voices de
  python generate.py --list-voices ja
"""

import argparse
import hashlib
import os
import sys
import time

import yaml

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from modules.script_generator import generate_script
from modules.voiceover import generate_voiceover
from modules.visuals import search_and_download, create_fallback_clip
from modules.composer import compose_video
from modules.subtitles import create_subtitles


def ensure_first_run_setup():
    """Download fonts and create directories on first run."""
    fonts_dir = os.path.join(PROJECT_ROOT, "assets", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)

    fonts = {
        "Montserrat-Bold.ttf": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf",
        "Montserrat-Black.ttf": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Black.ttf",
    }

    import requests

    for filename, url in fonts.items():
        filepath = os.path.join(fonts_dir, filename)
        if not os.path.exists(filepath):
            print(f"   Downloading font: {filename}...")
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                print(f"   Downloaded: {filename}")
            except Exception as e:
                print(f"   Warning: Could not download {filename}: {e}")

    for d in [
        "output/drafts", "output/ready",
        "cache/tts", "cache/footage", "cache/images",
        "cache/ai_images", "cache/ai_video", "cache/motion",
        "cache/infographic", "cache/voice_clone",
        "assets/music", "assets/logos", "assets/overlays",
    ]:
        os.makedirs(os.path.join(PROJECT_ROOT, d), exist_ok=True)


def load_config():
    """Load configuration from config.yaml."""
    config_path = os.path.join(PROJECT_ROOT, "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_voice_for_language(lang, config):
    """Get the best TTS voice for a language, with dynamic discovery for new languages."""
    # Check configured voices first
    voices = config.get("voiceover", {}).get("voices", {})
    lang_voice_map = {"en": "en_male", "sk": "sk_male", "cz": "cz_male"}
    voice_key = lang_voice_map.get(lang)

    if voice_key and voice_key in voices:
        return voices[voice_key]

    # For unconfigured languages, use dynamic voice discovery
    try:
        from audio.tts import TTSEngine
        engine = TTSEngine(config)
        return engine.get_best_voice(lang)
    except Exception:
        # Ultimate fallback
        return "en-US-GuyNeural"


def run_standard_mode(args, config):
    """Standard video generation (voiceover + visuals + subtitles). UNCHANGED."""
    # Step 1: Generate Script
    print(f"\n[1/5] Generating script...")
    script = generate_script(
        topic=args.topic,
        duration=args.duration,
        language=args.lang,
        style=args.style,
    )
    print(f"   Hook: {script['hook'][:60]}...")
    print(f"   Segments: {len(script['segments'])}")

    # Step 2: Generate Voiceover
    print(f"\n[2/5] Generating voiceover (Edge TTS)...")
    full_text = script["hook"]
    for seg in script["segments"]:
        full_text += " " + seg["text"]
    if script.get("cta"):
        full_text += " " + script["cta"]

    if args.voice:
        voice_name = config["voiceover"]["voices"].get(args.voice, args.voice)
    else:
        voice_name = _get_voice_for_language(args.lang, config)

    rate = config["voiceover"].get("rate", "+0%")
    pitch = config["voiceover"].get("pitch", "+0Hz")

    text_hash = hashlib.md5(full_text.encode()).hexdigest()[:12]
    tts_path = os.path.join(PROJECT_ROOT, "cache", "tts", f"{text_hash}.mp3")

    vo_result = generate_voiceover(
        text=full_text, output_path=tts_path,
        voice=voice_name, rate=rate, pitch=pitch,
    )
    print(f"   Audio: {vo_result['duration']:.1f}s, {len(vo_result['word_timestamps'])} words")

    # Step 3: Get Visuals
    print(f"\n[3/5] Getting stock footage...")
    all_footage = []
    for segment in script["segments"]:
        query = segment.get("visual_query", args.topic)
        clips = search_and_download(query=query, count=2)
        all_footage.extend(clips)
        print(f"   '{query}': {len(clips)} clip(s)")

    if not all_footage:
        fallback = create_fallback_clip(args.topic, duration=8)
        if fallback:
            all_footage = [fallback]

    # Step 4: Compose
    print(f"\n[4/5] Composing video...")
    output_path = _get_output_path(args)
    compose_video(
        script=script, voiceover=vo_result,
        footage_clips=all_footage, output_path=output_path, config=config,
    )

    return output_path, vo_result["duration"], script.get("hashtags", [])


def run_conversation_mode(args, config):
    """Conversation video generation (chat/podcast/story). UNCHANGED."""
    from modules.conversation import (
        build_conversation_video, generate_conversation_script,
    )

    render_style = args.mode  # chat, podcast, or story

    # Get conversation script
    if args.script:
        print(f"\n[1/3] Loading script from {args.script}...")
        with open(args.script, "r", encoding="utf-8") as f:
            script_text = f.read()
    else:
        print(f"\n[1/3] Generating {render_style} conversation about '{args.topic}'...")
        script_text = generate_conversation_script(
            topic=args.topic,
            style=render_style,
            language=args.lang,
        )

    print(f"   Script preview:")
    for line in script_text.strip().split("\n")[:4]:
        print(f"   | {line}")
    if script_text.count("\n") > 3:
        print(f"   | ... ({script_text.count(chr(10)) + 1} lines total)")

    # Build video
    print(f"\n[2/3] Building {render_style} video...")
    output_path = _get_output_path(args, suffix=f"_{render_style}")

    result = build_conversation_video(
        script_text=script_text,
        render_style=render_style,
        output_path=output_path,
        language=args.lang,
        config=config,
    )

    return result, 0, []


def run_auto_mode(args, config):
    """
    NEW: Auto mode — AI Director creates storyboard, generates visuals, composes.

    Uses brain/director.py to orchestrate the entire pipeline.
    """
    from brain.director import Director

    brain_mode = getattr(args, "brain", "template")
    visual_mode = getattr(args, "visuals", "stock")
    voice_clone = getattr(args, "voice_clone", False)

    # Update config with CLI overrides
    if brain_mode:
        config.setdefault("brain", {})["mode"] = brain_mode
    if voice_clone:
        config.setdefault("audio", {}).setdefault("voice_clone", {})["enabled"] = True

    director = Director(config)

    # Step 1: Create storyboard
    print(f"\n[1/3] Creating storyboard ({brain_mode} mode)...")
    storyboard = director.create_storyboard(
        topic=args.topic,
        duration=args.duration,
        language=args.lang,
        style=args.style,
        visual_mode=visual_mode,
    )
    print(f"   Hook: {storyboard.hook[:60]}...")
    print(f"   Scenes: {len(storyboard.scenes)}")
    print(f"   Visual types: {[s.visual_type.value for s in storyboard.scenes]}")
    if storyboard.needs_gpu():
        print(f"   GPU required: Yes")

    # Step 2+3: Execute storyboard (generates all assets + composes)
    print(f"\n[2/3] Executing storyboard...")
    output_path = _get_output_path(args, suffix="_auto")

    result = director.execute_storyboard(storyboard, output_path, args)

    return result, storyboard.total_audio_duration, storyboard.hashtags


def run_list_voices(lang_code):
    """List available TTS voices for a language."""
    from audio.tts import TTSEngine
    engine = TTSEngine()
    print(engine.list_voices_formatted(lang_code))


def _get_output_path(args, suffix=""):
    """Generate output path from args."""
    if args.output:
        return args.output
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in args.topic)
    safe_name = safe_name.strip().replace(" ", "_")[:30]
    return os.path.join(PROJECT_ROOT, "output", "drafts", f"{safe_name}{suffix}.mp4")


def main():
    parser = argparse.ArgumentParser(
        description="ULTIMATE AI VIDEO CREATOR — Generate short-form videos"
    )
    parser.add_argument("--topic", default=None,
                        help="Video topic")
    parser.add_argument("--mode", default="standard",
                        choices=["standard", "chat", "podcast", "story", "auto"],
                        help="Video mode (default: standard)")
    parser.add_argument("--lang", default="en",
                        help="Language code — any language (default: en). "
                             "Examples: en, sk, cz, de, fr, ja, ko, zh, es, pt, it, ru")
    parser.add_argument("--duration", type=int, default=30,
                        help="Target duration in seconds (default: 30)")
    parser.add_argument("--voice", default=None,
                        help="Voice key (e.g., en_male, sk_female) or full voice name")
    parser.add_argument("--style", default="education",
                        choices=["humor", "bait", "education", "lifestyle", "product"],
                        help="Content style (default: education)")
    parser.add_argument("--script", default=None,
                        help="Path to conversation script file (conversation modes)")
    parser.add_argument("--no-music", action="store_true",
                        help="Disable background music")
    parser.add_argument("--no-subtitles", action="store_true",
                        help="Disable subtitles")
    parser.add_argument("--output", default=None,
                        help="Custom output path")

    # NEW: AI Director args
    parser.add_argument("--brain", default="template",
                        choices=["template", "claude"],
                        help="Brain mode: template (free) or claude (API key needed)")
    parser.add_argument("--visuals", default="stock",
                        choices=["stock", "ai_image", "ai_video", "mixed"],
                        help="Visual mode for auto mode (default: stock)")
    parser.add_argument("--voice-clone", action="store_true",
                        help="Enable voice cloning (requires reference audio)")

    # NEW: Voice discovery
    parser.add_argument("--list-voices", metavar="LANG",
                        help="List available TTS voices for a language code (e.g., de, fr, ja)")

    args = parser.parse_args()

    # Handle list-voices command (no video generation)
    if args.list_voices:
        ensure_first_run_setup()
        run_list_voices(args.list_voices)
        return

    # Topic is required for video generation
    if not args.topic:
        parser.error("--topic is required for video generation")

    start_time = time.time()

    is_conversation = args.mode in ("chat", "podcast", "story")
    is_auto = args.mode == "auto"

    print("=" * 55)
    print("  ULTIMATE AI VIDEO CREATOR")
    print("=" * 55)
    print(f"  Topic:    {args.topic}")
    print(f"  Mode:     {args.mode}")
    print(f"  Language: {args.lang}")
    if is_auto:
        print(f"  Brain:    {args.brain}")
        print(f"  Visuals:  {args.visuals}")
    if not is_conversation:
        print(f"  Duration: {args.duration}s")
        print(f"  Style:    {args.style}")
    print("=" * 55)

    # First run setup
    print("\n[Setup] Checking fonts and directories...")
    ensure_first_run_setup()

    # Load config
    config = load_config()
    if args.no_music:
        config["music"]["enabled"] = False
    if args.no_subtitles:
        config["subtitles"]["enabled"] = False

    # Run appropriate mode
    if is_auto:
        output_path, duration, hashtags = run_auto_mode(args, config)
    elif is_conversation:
        output_path, duration, hashtags = run_conversation_mode(args, config)
    else:
        output_path, duration, hashtags = run_standard_mode(args, config)

    # Summary
    elapsed = time.time() - start_time
    file_size = os.path.getsize(output_path) / (1024 * 1024)

    print(f"\n{'=' * 55}")
    print(f"  VIDEO READY!")
    print(f"{'=' * 55}")
    print(f"  Output:   {output_path}")
    print(f"  Size:     {file_size:.1f} MB")
    print(f"  Format:   1080x1920 (9:16 portrait)")
    print(f"  Mode:     {args.mode}")
    print(f"  Time:     {elapsed:.1f}s")
    if hashtags:
        print(f"  Hashtags: {' '.join(hashtags)}")
    print(f"{'=' * 55}")

    return output_path


if __name__ == "__main__":
    main()
