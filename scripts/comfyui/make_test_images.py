"""Generate test.png and test_mask.png for ComfyUI inpaint workflow validation."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(r"D:\ComfyUI\input")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Source image: light background + gray circle + green bar
img = Image.new("RGB", (512, 512), (180, 200, 220))
draw = ImageDraw.Draw(img)
draw.ellipse([156, 156, 356, 356], fill=(120, 120, 130), outline=(80, 80, 90), width=3)
draw.rectangle([80, 380, 432, 460], fill=(100, 140, 100))
img.save(OUT_DIR / "test.png")

# Mask: black background + white circle (white = inpaint region)
mask = Image.new("RGB", (512, 512), (0, 0, 0))
md = ImageDraw.Draw(mask)
md.ellipse([156, 156, 356, 356], fill=(255, 255, 255))
mask.save(OUT_DIR / "test_mask.png")

print(f"Created: {OUT_DIR / 'test.png'}")
print(f"Created: {OUT_DIR / 'test_mask.png'}")
