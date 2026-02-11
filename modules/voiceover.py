"""
Text-to-Speech using Edge TTS (Microsoft) — completely FREE and unlimited.
Generates high-quality neural voices in 40+ languages including Slovak.
Provides word-level timestamps for subtitle synchronization.

Edge TTS 7.x provides SentenceBoundary only, so we interpolate
word-level timings from sentence boundaries based on character length.
"""

import asyncio
import hashlib
import json
import os
import re
import sys

import edge_tts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "tts")


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _get_cache_path(text, voice, rate, pitch):
    """Generate deterministic cache path from TTS parameters."""
    key = f"{text}|{voice}|{rate}|{pitch}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{h}.mp3")


def _get_timestamp_path(audio_path):
    """Get the timestamp JSON path for an audio file."""
    return audio_path.replace(".mp3", "_timestamps.json")


def _interpolate_word_timestamps(sentence_boundaries):
    """
    Create word-level timestamps by interpolating from sentence boundaries.

    Each sentence boundary has: offset, duration, text.
    We split each sentence into words and distribute timing proportionally
    based on character count (rough but effective for subtitles).
    """
    word_timestamps = []

    for sb in sentence_boundaries:
        sentence_text = sb["text"]
        sent_start = sb["offset"] / 10_000_000  # Convert 100-ns ticks to seconds
        sent_duration = sb["duration"] / 10_000_000

        # Split sentence into words
        words = sentence_text.split()
        if not words:
            continue

        # Calculate proportional timing based on character length
        # Add 1 char per word for space/pause effect
        char_lengths = [len(w) + 1 for w in words]
        total_chars = sum(char_lengths)

        current_time = sent_start
        for i, word in enumerate(words):
            word_fraction = char_lengths[i] / total_chars
            word_duration = sent_duration * word_fraction

            word_timestamps.append({
                "word": word,
                "start": round(current_time, 3),
                "end": round(current_time + word_duration, 3),
            })

            current_time += word_duration

    return word_timestamps


async def _generate_voiceover_async(
    text,
    output_path,
    voice="en-US-GuyNeural",
    rate="+0%",
    pitch="+0Hz",
):
    """
    Async implementation of voiceover generation.
    Returns dict with audio_path, duration, and word_timestamps.
    """
    _ensure_cache_dir()

    # Check cache
    ts_path = _get_timestamp_path(output_path)
    if os.path.exists(output_path) and os.path.exists(ts_path):
        with open(ts_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        print(f"   [TTS] Using cached: {output_path}")
        return cached

    print(f"   [TTS] Generating with voice: {voice}")

    # Generate audio + collect sentence boundaries in one pass
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)

    sentence_boundaries = []
    audio_chunks = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            sentence_boundaries.append({
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "text": chunk["text"],
            })
        elif chunk["type"] == "WordBoundary":
            # Edge TTS 6.x compatibility (if it ever returns these)
            sentence_boundaries.append({
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "text": chunk["text"],
            })

    # Write audio file
    with open(output_path, "wb") as f:
        for audio_data in audio_chunks:
            f.write(audio_data)

    # Interpolate word-level timestamps from sentence boundaries
    timestamps = _interpolate_word_timestamps(sentence_boundaries)

    # Get audio duration
    duration = _get_audio_duration(output_path)

    result = {
        "audio_path": output_path,
        "duration": duration,
        "word_timestamps": timestamps,
    }

    # Cache timestamps
    with open(ts_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"   [TTS] Generated {duration:.1f}s audio with {len(timestamps)} word timestamps")
    return result


def _get_audio_duration(path):
    """Get duration of audio file using moviepy."""
    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(path)
        dur = clip.duration
        clip.close()
        return round(dur, 2)
    except Exception:
        # Fallback: estimate from file size (128kbps MP3 ~ 16KB/sec)
        size = os.path.getsize(path)
        return round(size / 16000, 2)


def generate_voiceover(
    text,
    output_path=None,
    voice="en-US-GuyNeural",
    rate="+0%",
    pitch="+0Hz",
):
    """
    Generate voiceover audio + word-level timestamps.

    Args:
        text: Text to synthesize
        output_path: Output MP3 path (auto-generated if None)
        voice: Edge TTS voice name
        rate: Speech rate adjustment (-50% to +100%)
        pitch: Pitch adjustment

    Returns:
        dict with:
            audio_path: str — path to MP3 file
            duration: float — audio duration in seconds
            word_timestamps: list[dict] — word-level timing data
    """
    if output_path is None:
        output_path = _get_cache_path(text, voice, rate, pitch)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Run async function
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            _generate_voiceover_async(text, output_path, voice, rate, pitch)
        )
    finally:
        loop.close()

    return result


def generate_segmented_voiceover(segments, voice="en-US-GuyNeural", rate="+0%", pitch="+0Hz"):
    """
    Generate separate voiceover for each segment.

    Args:
        segments: List of dicts with "text" key
        voice: Edge TTS voice name
        rate: Speech rate
        pitch: Pitch

    Returns:
        List of voiceover result dicts (one per segment)
    """
    results = []
    for i, segment in enumerate(segments):
        text = segment["text"]
        path = _get_cache_path(f"seg_{i}_{text}", voice, rate, pitch)
        result = generate_voiceover(text, path, voice, rate, pitch)
        results.append(result)
    return results


async def _list_voices_async(language_filter=None):
    """List available Edge TTS voices."""
    voices = await edge_tts.list_voices()
    if language_filter:
        voices = [v for v in voices if v["Locale"].startswith(language_filter)]
    return voices


def list_voices(language_filter=None):
    """
    List available voices, optionally filtered by language.

    Args:
        language_filter: Language prefix like "en", "sk", "cs"

    Returns:
        List of voice dicts with name, gender, locale
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    try:
        voices = loop.run_until_complete(_list_voices_async(language_filter))
    finally:
        loop.close()

    return [
        {
            "name": v["ShortName"],
            "gender": v["Gender"],
            "locale": v["Locale"],
        }
        for v in voices
    ]


if __name__ == "__main__":
    # Quick test
    result = generate_voiceover(
        "Hello, this is a test of the video automation pipeline. Let's see how it works.",
        voice="en-US-GuyNeural",
    )
    print(f"Audio: {result['audio_path']}")
    print(f"Duration: {result['duration']}s")
    print(f"Words: {len(result['word_timestamps'])}")
    for w in result["word_timestamps"][:10]:
        print(f"  {w['start']:.2f}-{w['end']:.2f}: {w['word']}")
