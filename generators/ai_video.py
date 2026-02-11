"""
AI Video Generation — Wan2GP (Wan2.1) subprocess integration.

Runs Wan2GP as a separate process (isolated CUDA context) for text-to-video.
Designed for RTX 3070 8GB with CPU offloading enabled.

Resolution: 480x848, 81 frames (~5s at 16fps)
VRAM: ~8.2GB with CPU offloading
Timeout: 10 minutes per clip

All AI features are optional — the system works without GPU.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from utils.cache import ensure_cache_dir, is_cached

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Wan2GPVideoGenerator:
    """
    Generate video clips using Wan2GP (Wan2.1 text-to-video).

    Runs as subprocess to isolate CUDA context from main process.
    Requires Wan2GP to be installed separately.

    Usage:
        gen = Wan2GPVideoGenerator(config)
        path = gen.generate_single("A sunset over the ocean", duration=5)
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.wan2gp_path = self.config.get("wan2gp_path", "")
        self.model = self.config.get("model", "1.3B")
        self.resolution = self.config.get("resolution", [480, 848])
        self.cpu_offload = self.config.get("cpu_offload", True)
        self.timeout = self.config.get("timeout", 600)  # 10 minutes
        self.cache_dir = ensure_cache_dir("ai_video")

    def is_available(self):
        """Check if Wan2GP is installed and accessible."""
        if not self.wan2gp_path:
            return False
        wgp_script = os.path.join(self.wan2gp_path, "wgp.py")
        return os.path.exists(wgp_script)

    def generate_single(self, prompt, duration=5):
        """
        Generate a single video clip from text prompt.

        Args:
            prompt: Text description of the video
            duration: Target duration in seconds (affects frame count)

        Returns:
            Path to generated video file, or None on failure
        """
        if not self.is_available():
            print("   [AI Video] Wan2GP not configured or not found")
            return None

        # Check cache
        cache_key = hashlib.md5(
            f"{prompt}_{duration}_{self.model}".encode()
        ).hexdigest()[:12]
        output_path = os.path.join(self.cache_dir, f"wan2gp_{cache_key}.mp4")

        if is_cached(output_path):
            print(f"   [AI Video] Cache hit: {output_path}")
            return output_path

        print(f"   [AI Video] Generating: {prompt[:60]}...")
        print(f"   [AI Video] Model: {self.model}, Resolution: {self.resolution}")
        print(f"   [AI Video] CPU offload: {self.cpu_offload}")

        try:
            result = self._run_wan2gp(prompt, output_path)
            if result and os.path.exists(output_path):
                print(f"   [AI Video] Generated: {output_path}")
                return output_path
            else:
                print("   [AI Video] Generation failed — no output file")
                return None
        except subprocess.TimeoutExpired:
            print(f"   [AI Video] Timeout ({self.timeout}s) — clip took too long")
            return None
        except Exception as e:
            print(f"   [AI Video] Error: {e}")
            return None

    def _run_wan2gp(self, prompt, output_path):
        """
        Run Wan2GP as subprocess.

        Creates a queue.zip with job config, runs wgp.py, collects output.
        """
        wgp_script = os.path.join(self.wan2gp_path, "wgp.py")

        # Create temporary job directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create job config
            job_config = {
                "prompt": prompt,
                "negative_prompt": "blurry, distorted, low quality, watermark",
                "width": self.resolution[0],
                "height": self.resolution[1],
                "num_frames": 81,  # ~5 seconds at 16fps
                "guidance_scale": 5.0,
                "num_inference_steps": 20,
                "seed": -1,
            }

            # Write job JSON
            job_path = os.path.join(tmpdir, "job.json")
            with open(job_path, "w") as f:
                json.dump(job_config, f)

            # Create queue.zip
            queue_zip = os.path.join(tmpdir, "queue.zip")
            with zipfile.ZipFile(queue_zip, "w") as zf:
                zf.write(job_path, "job.json")

            # Build command
            cmd = [
                sys.executable, wgp_script,
                "--process", queue_zip,
            ]

            if self.cpu_offload:
                cmd.append("--cpu-offload")

            # Run subprocess
            print(f"   [AI Video] Running Wan2GP subprocess...")
            start_time = time.time()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.wan2gp_path,
                timeout=self.timeout,
            )

            elapsed = time.time() - start_time
            print(f"   [AI Video] Subprocess completed in {elapsed:.1f}s")

            if result.returncode != 0:
                print(f"   [AI Video] Subprocess error: {result.stderr[-200:]}")
                return False

            # Find output video in Wan2GP output directory
            output_dir = os.path.join(self.wan2gp_path, "output")
            if os.path.exists(output_dir):
                videos = sorted(
                    [f for f in os.listdir(output_dir) if f.endswith(".mp4")],
                    key=lambda f: os.path.getmtime(os.path.join(output_dir, f)),
                    reverse=True,
                )
                if videos:
                    src = os.path.join(output_dir, videos[0])
                    shutil.copy2(src, output_path)
                    return True

            return False

    def generate_batch(self, prompts):
        """
        Generate multiple video clips (serialized — one at a time due to VRAM).

        Args:
            prompts: List of (prompt, duration) tuples

        Returns:
            List of output paths (None for failed generations)
        """
        results = []
        for i, (prompt, duration) in enumerate(prompts):
            print(f"\n   [AI Video] Batch {i+1}/{len(prompts)}")
            path = self.generate_single(prompt, duration)
            results.append(path)
        return results


def is_ai_video_available(config=None):
    """Check if AI video generation is available."""
    config = config or {}
    gen_config = config.get("generators", {}).get("ai_video", {})

    if not gen_config.get("enabled", False):
        return False

    wan2gp_path = gen_config.get("wan2gp_path", "")
    if not wan2gp_path:
        return False

    return os.path.exists(os.path.join(wan2gp_path, "wgp.py"))
