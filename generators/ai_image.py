"""
AI Image Generation — SDXL Turbo local + Pollinations fallback.

Local mode: SDXL Turbo FP16 (~3.5GB VRAM), 1-step inference, 512x512
Fallback:   Pollinations.ai (free, no API key needed)

All GPU features are optional — works without GPU or API keys.
"""

import hashlib
import os

from utils.cache import ensure_cache_dir, is_cached

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LocalImageGenerator:
    """
    Generate images locally with SDXL Turbo.

    Requires: torch, diffusers, transformers, accelerate
    VRAM: ~3.5 GB (FP16)
    Speed: ~1 second per image (RTX 3070)
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.model_name = self.config.get("model", "stabilityai/sdxl-turbo")
        self.width = self.config.get("width", 512)
        self.height = self.config.get("height", 512)
        self.steps = self.config.get("steps", 1)
        self.guidance_scale = self.config.get("guidance_scale", 0.0)
        self._pipe = None
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy-load the SDXL Turbo model."""
        if self._loaded:
            return

        try:
            import torch
            from diffusers import AutoPipelineForText2Image

            print(f"   [AI Image] Loading SDXL Turbo ({self.model_name})...")
            self._pipe = AutoPipelineForText2Image.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16,
                variant="fp16",
            )
            self._pipe = self._pipe.to("cuda")
            self._loaded = True
            print("   [AI Image] SDXL Turbo loaded successfully")

        except ImportError:
            raise ImportError(
                "Local AI image generation requires: "
                "pip install torch diffusers transformers accelerate"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load SDXL Turbo: {e}")

    def generate(self, prompt, width=None, height=None):
        """
        Generate an image from text prompt.

        Args:
            prompt: Text description
            width: Image width (default from config)
            height: Image height (default from config)

        Returns:
            Path to generated image
        """
        w = width or self.width
        h = height or self.height

        cache_dir = ensure_cache_dir("ai_images")
        cache_key = hashlib.md5(f"{prompt}_{w}_{h}_local".encode()).hexdigest()[:12]
        output_path = os.path.join(cache_dir, f"sdxl_{cache_key}.png")

        if is_cached(output_path):
            return output_path

        self._ensure_loaded()

        print(f"   [AI Image] Generating: {prompt[:60]}...")
        image = self._pipe(
            prompt=prompt,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance_scale,
            width=w,
            height=h,
        ).images[0]

        image.save(output_path)
        print(f"   [AI Image] Saved: {output_path}")
        return output_path

    def generate_and_upscale(self, prompt, target_w=1080, target_h=1920):
        """
        Generate image at native resolution and upscale to target.

        Args:
            prompt: Text description
            target_w: Target width
            target_h: Target height

        Returns:
            Path to upscaled image
        """
        from PIL import Image

        cache_dir = ensure_cache_dir("ai_images")
        cache_key = hashlib.md5(
            f"{prompt}_{target_w}_{target_h}_upscaled".encode()
        ).hexdigest()[:12]
        upscaled_path = os.path.join(cache_dir, f"sdxl_up_{cache_key}.png")

        if is_cached(upscaled_path):
            return upscaled_path

        # Generate at native resolution
        raw_path = self.generate(prompt)
        if not raw_path:
            return None

        # Upscale with Pillow (Lanczos)
        img = Image.open(raw_path)
        img_upscaled = img.resize((target_w, target_h), Image.LANCZOS)
        img_upscaled.save(upscaled_path)

        print(f"   [AI Image] Upscaled to {target_w}x{target_h}")
        return upscaled_path

    def unload(self):
        """Free GPU memory by unloading the model."""
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            self._loaded = False

            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            print("   [AI Image] SDXL Turbo unloaded, VRAM freed")


class PollinationsImageGenerator:
    """
    Generate images using Pollinations.ai (free, no API key).
    Wraps existing modules/image_gen.py functionality.
    """

    def __init__(self, config=None):
        self.config = config or {}

    def generate(self, prompt, width=1080, height=1920):
        """
        Generate an image via Pollinations API.

        Args:
            prompt: Text description
            width: Image width
            height: Image height

        Returns:
            Path to generated image
        """
        from modules.image_gen import generate_image_pollinations
        return generate_image_pollinations(prompt, width, height)

    def unload(self):
        """No-op for API-based generator."""
        pass


def get_image_generator(config=None):
    """
    Factory function — returns appropriate image generator.

    Args:
        config: generators.ai_image config dict

    Returns:
        Image generator instance (Local or Pollinations)
    """
    config = config or {}
    engine = config.get("engine", "pollinations")

    if engine == "local":
        try:
            import torch
            if not torch.cuda.is_available():
                print("   [AI Image] No CUDA GPU available, falling back to Pollinations")
                return PollinationsImageGenerator(config)
            return LocalImageGenerator(config.get("local", {}))
        except ImportError:
            print("   [AI Image] PyTorch not installed, falling back to Pollinations")
            return PollinationsImageGenerator(config)
    else:
        return PollinationsImageGenerator(config)
