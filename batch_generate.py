#!/usr/bin/env python3
"""
ULTIMATE AI VIDEO CREATOR — Batch generate multiple videos.

Usage:
  python batch_generate.py --topics topics.txt
  python batch_generate.py --topics topics.txt --count 5 --lang sk
  python batch_generate.py --category education --count 3

NEW: Auto mode batch:
  python batch_generate.py --category education --mode auto --brain template
  python batch_generate.py --topics topics.txt --mode auto --lang de --visuals mixed
"""

import argparse
import os
import sys
import time
import json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from modules.script_generator import generate_script

# Default topics by category for auto-generation
DEFAULT_TOPICS = {
    "education": [
        "Benefits of reading every day",
        "How sleep affects your brain",
        "3 habits of successful people",
        "Why meditation is so powerful",
        "The science of motivation",
        "How to learn anything faster",
        "Why exercise boosts creativity",
        "The power of compound interest",
        "How your diet affects your mood",
        "Why journaling changes your life",
    ],
    "lifestyle": [
        "Morning routine for productivity",
        "5 minute stress relief techniques",
        "How to build better habits",
        "Digital detox tips that work",
        "Minimalism for beginners",
        "Self care ideas for busy people",
        "How to improve your sleep quality",
        "Healthy meal prep basics",
        "Time management secrets",
        "How to stay motivated daily",
    ],
    "wellness": [
        "Benefits of CBD for anxiety",
        "Natural ways to improve sleep",
        "Understanding adaptogens",
        "How breathing exercises reduce stress",
        "Benefits of cold exposure",
        "Gut health basics everyone should know",
        "Natural energy boosters",
        "Mindfulness for beginners",
        "Benefits of herbal supplements",
        "How to reduce inflammation naturally",
    ],
    "product": [
        "Best wellness products of 2025",
        "CBD oil buying guide",
        "Top supplements you actually need",
        "Wellness gadgets worth the money",
        "Natural skincare essentials",
    ],
}


def load_topics_from_file(filepath):
    """Load topics from a text file (one per line)."""
    topics = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                topics.append(line)
    return topics


def main():
    parser = argparse.ArgumentParser(
        description="ULTIMATE AI VIDEO CREATOR — Batch generate videos"
    )
    parser.add_argument("--topics", default=None,
                        help="Path to topics file (one topic per line)")
    parser.add_argument("--category", default=None,
                        choices=list(DEFAULT_TOPICS.keys()),
                        help="Auto-generate from category")
    parser.add_argument("--count", type=int, default=3,
                        help="Number of videos to generate (default: 3)")
    parser.add_argument("--mode", default="standard",
                        choices=["standard", "chat", "podcast", "story", "auto"],
                        help="Video mode (default: standard)")
    parser.add_argument("--lang", default="en",
                        help="Language code — any language (default: en)")
    parser.add_argument("--duration", type=int, default=30,
                        help="Target duration per video (default: 30)")
    parser.add_argument("--style", default="education",
                        choices=["humor", "bait", "education", "lifestyle", "product"],
                        help="Content style (default: education)")
    parser.add_argument("--no-music", action="store_true",
                        help="Disable background music")
    parser.add_argument("--no-subtitles", action="store_true",
                        help="Disable subtitles")

    # NEW: AI Director args
    parser.add_argument("--brain", default="template",
                        choices=["template", "claude"],
                        help="Brain mode for auto mode (default: template)")
    parser.add_argument("--visuals", default="stock",
                        choices=["stock", "ai_image", "ai_video", "mixed"],
                        help="Visual mode for auto mode (default: stock)")
    parser.add_argument("--voice-clone", action="store_true",
                        help="Enable voice cloning")

    args = parser.parse_args()

    # Collect topics
    if args.topics:
        topics = load_topics_from_file(args.topics)
    elif args.category:
        topics = DEFAULT_TOPICS.get(args.category, DEFAULT_TOPICS["education"])
    else:
        topics = DEFAULT_TOPICS["education"]

    # Limit to requested count
    topics = topics[:args.count]

    print("=" * 55)
    print("  ULTIMATE AI VIDEO CREATOR — BATCH MODE")
    print("=" * 55)
    print(f"  Topics:   {len(topics)}")
    print(f"  Mode:     {args.mode}")
    print(f"  Language: {args.lang}")
    print(f"  Duration: {args.duration}s each")
    print(f"  Style:    {args.style}")
    if args.mode == "auto":
        print(f"  Brain:    {args.brain}")
        print(f"  Visuals:  {args.visuals}")
    print("=" * 55)

    batch_start = time.time()
    results = []

    for i, topic in enumerate(topics):
        print(f"\n{'#' * 55}")
        print(f"  VIDEO {i+1}/{len(topics)}: {topic}")
        print(f"{'#' * 55}")

        # Build command args
        cmd_args = [
            sys.executable, os.path.join(PROJECT_ROOT, "generate.py"),
            "--topic", topic,
            "--mode", args.mode,
            "--lang", args.lang,
            "--duration", str(args.duration),
            "--style", args.style,
        ]
        if args.no_music:
            cmd_args.append("--no-music")
        if args.no_subtitles:
            cmd_args.append("--no-subtitles")

        # NEW: Auto mode args
        if args.mode == "auto":
            cmd_args.extend(["--brain", args.brain])
            cmd_args.extend(["--visuals", args.visuals])
            if args.voice_clone:
                cmd_args.append("--voice-clone")

        # Run as subprocess to isolate memory
        import subprocess
        video_start = time.time()

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=300,  # 5 min timeout per video
            )

            video_time = time.time() - video_start

            if result.returncode == 0:
                # Extract output path from stdout
                output_line = ""
                for line in result.stdout.split("\n"):
                    if "Output:" in line:
                        output_line = line.strip()
                        break

                results.append({
                    "topic": topic,
                    "status": "success",
                    "time": round(video_time, 1),
                    "output": output_line,
                })
                print(f"  [OK] Completed in {video_time:.1f}s")
            else:
                results.append({
                    "topic": topic,
                    "status": "error",
                    "time": round(video_time, 1),
                    "error": result.stderr[-200:] if result.stderr else "Unknown error",
                })
                print(f"  [FAIL] Error after {video_time:.1f}s")
                if result.stderr:
                    print(f"  {result.stderr[-150:]}")

        except subprocess.TimeoutExpired:
            results.append({
                "topic": topic,
                "status": "timeout",
                "time": 300,
            })
            print(f"  [TIMEOUT] Exceeded 5 minute limit")
        except Exception as e:
            results.append({
                "topic": topic,
                "status": "error",
                "error": str(e),
            })
            print(f"  [ERROR] {e}")

    # ===== SUMMARY =====
    total_time = time.time() - batch_start
    success = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - success

    print(f"\n{'=' * 55}")
    print(f"  BATCH COMPLETE")
    print(f"{'=' * 55}")
    print(f"  Total videos: {len(results)}")
    print(f"  Successful:   {success}")
    print(f"  Failed:       {failed}")
    print(f"  Total time:   {total_time:.1f}s")
    print(f"  Avg per video: {total_time/max(len(results),1):.1f}s")
    print(f"{'=' * 55}")

    for r in results:
        status = "OK" if r["status"] == "success" else "FAIL"
        print(f"  [{status}] {r['topic']}")

    # Save results to JSON
    results_path = os.path.join(PROJECT_ROOT, "output", "batch_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(results),
            "success": success,
            "failed": failed,
            "total_time": round(total_time, 1),
            "results": results,
        }, f, indent=2)
    print(f"\n  Results saved to: {results_path}")


if __name__ == "__main__":
    main()
