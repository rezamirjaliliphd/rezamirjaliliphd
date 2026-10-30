"""
Turn a photo into the ASCII portrait for the profile card (like Andrew6rant's).

    pip install pillow numpy
    python make_ascii.py me.png                        # writes ascii.txt (used on both cards)
    python make_ascii.py me.png --crop 205,50,595,560 --width 64 --gamma 1.1

Characters are dense where the photo is dark. Add --per-theme to also write
ascii_dark.txt with the opposite mapping for the dark card (try --gamma-dark 1.8).

Transparent pixels (a PNG cut-out) become blank space, which keeps the background clean.
With the card's 10px portrait font, ~64 wide x ~40 rows fills the space next to the info column.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

RAMPS = {
    "simple": " .:-=+*#%@",
    "detailed": " .'`^\",:;Il!i~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
}


def to_ascii(path, width, gamma, aspect, ramp, crop=None, bright_is_dense=False, equalize=False):
    img = Image.open(path).convert("RGBA")
    if crop:
        img = img.crop(crop)
    h = max(1, round(img.height / img.width * width * aspect))
    img = img.resize((width, h), Image.BOX)
    a = np.asarray(img).astype(float)
    lum = a[..., :3] @ [0.299, 0.587, 0.114]
    alpha = a[..., 3]
    fg = alpha >= 128

    # stretch contrast over the subject only (ignore the transparent background)
    vals = lum[fg] if fg.any() else lum.ravel()
    if equalize:      # histogram-equalize the subject: brings out face detail next to a dark suit
        ranks = np.sort(vals)
        v = np.searchsorted(ranks, lum, side="right") / len(ranks)
    else:
        lo, hi = np.percentile(vals, 2), np.percentile(vals, 98)
        v = np.clip((lum - lo) / max(hi - lo, 1), 0, 1)
    v = v ** gamma

    chars = RAMPS[ramp]
    dens = v if bright_is_dense else 1 - v
    idx = np.rint(dens * (len(chars) - 1)).astype(int)
    rows = ["".join(chars[i] if f else " " for i, f in zip(r, fr)).rstrip()
            for r, fr in zip(idx, fg)]
    while rows and not rows[-1].strip():
        rows.pop()
    while rows and not rows[0].strip():
        rows.pop(0)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--gamma-dark", type=float, help="separate gamma for the dark-mode portrait")
    ap.add_argument("--ramp", choices=list(RAMPS), default="simple")
    ap.add_argument("--aspect", type=float, default=0.5, help="char height/width correction")
    ap.add_argument("--crop", help="left,top,right,bottom in pixels")
    ap.add_argument("--equalize", action="store_true", help="boost detail on the subject")
    ap.add_argument("--per-theme", action="store_true", help="also write ascii_dark.txt (inverted)")
    a = ap.parse_args()
    crop = tuple(int(x) for x in a.crop.split(",")) if a.crop else None
    here = Path(__file__).resolve().parent
    jobs = [("ascii.txt", False)] + ([("ascii_dark.txt", True)] if a.per_theme else [])
    if not a.per_theme:
        (here / "ascii_dark.txt").unlink(missing_ok=True)
    for name, bright in jobs:
        gamma = a.gamma_dark if (bright and a.gamma_dark) else a.gamma
        lines = to_ascii(a.image, a.width, gamma, a.aspect, a.ramp, crop, bright, a.equalize)
        (here / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"── {name} ({len(lines)} rows)\n" + "\n".join(lines) + "\n")
