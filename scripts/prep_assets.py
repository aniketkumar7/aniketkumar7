"""
One-time local prep. Run only when the photo or fonts change; outputs are committed,
so the daily workflow needs nothing but Pillow.

  1. photo  -> source-prepped.png  (background removed, toned for ASCII)
  2. fonts  -> fonts/*.woff2       (ASCII-only subsets, embedded into every card)

    pip install rembg onnxruntime opencv-python fonttools brotli
    python scripts/prep_assets.py [photo.png]
"""
import os
import sys

import cv2
import numpy as np
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image
from rembg import remove

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PHOTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "source-photo.png")
FONTS = os.path.join(ROOT, "fonts")


def prep_photo():
    cut = remove(Image.open(PHOTO).convert("RGBA"))
    rgb = np.array(cut.convert("RGB"))
    alpha = np.array(cut.split()[-1])
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # local contrast so eyes/beard/hairline survive the downsample
    gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    smooth = cv2.bilateralFilter(gray, 9, 50, 9)

    lo, hi = np.percentile(smooth[alpha > 128], [3, 97])
    tone = np.clip((smooth.astype(np.float32) - lo) / (hi - lo), 0, 1)

    # light subject on dark bg: ASCII density = brightness, so invert nothing,
    # just push edges (eyes, smile, jaw) brighter for definition
    fine = cv2.GaussianBlur(smooth, (0, 0), 1.2).astype(np.float32)
    coarse = cv2.GaussianBlur(smooth, (0, 0), 5).astype(np.float32)
    edges = np.clip(np.abs(fine - coarse) / 35.0, 0, 1)
    out = np.clip(tone * 0.85 + edges * 0.35, 0, 1)

    mask = cv2.GaussianBlur(alpha.astype(np.float32) / 255.0, (0, 0), 1.0)
    out = (out * mask * 255).astype(np.uint8)

    ys, xs = np.where(alpha > 20)
    side = max(xs.max() - xs.min(), ys.max() - ys.min()) + 20
    cx, cy = (xs.min() + xs.max()) // 2, (ys.min() + ys.max()) // 2
    canvas = np.zeros((side, side), np.uint8)
    x0, y0 = cx - side // 2, cy - side // 2
    sx0, sy0 = max(x0, 0), max(y0, 0)
    sx1, sy1 = min(x0 + side, out.shape[1]), min(y0 + side, out.shape[0])
    canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = out[sy0:sy1, sx0:sx1]
    Image.fromarray(canvas, mode="L").save(os.path.join(ROOT, "source-prepped.png"))
    print("wrote source-prepped.png", canvas.shape)


def subset_font(src, dst, wght=None):
    font = TTFont(os.path.join(FONTS, src))
    if wght and "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": wght})
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(chr(c) for c in range(32, 127)) + "·—→←✓▸●★│─")
    sub.subset(font)
    font.flavor = "woff2"
    font.save(os.path.join(FONTS, dst))
    print("wrote", dst, os.path.getsize(os.path.join(FONTS, dst)), "bytes")


if __name__ == "__main__":
    prep_photo()
    subset_font("InstrumentSerif-Italic.ttf", "serif-italic.woff2")
    subset_font("InstrumentSerif-Regular.ttf", "serif.woff2")
    subset_font("JetBrainsMono.ttf", "mono.woff2", wght=400)
    subset_font("JetBrainsMono.ttf", "mono-bold.woff2", wght=700)
