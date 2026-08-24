#!/usr/bin/env python3
"""Chrome headless PNG renderer + quality check for X card system."""

import subprocess
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# CSS viewport dimensions — the HTML/CSS is authored at these pixel values.
# Chrome renders at 2x device pixel ratio (--force-device-scale-factor=2),
# producing a 2400×1350 PNG — retina quality, matching reputable media sources.
CARD_W   = 1200
CARD_H   = 675
DPR      = 2
OUT_W    = CARD_W * DPR   # 2400
OUT_H    = CARD_H * DPR   # 1350


def render_html_to_png(html_path: Path, out_path: Path) -> None:
    """Render an HTML file to PNG via Chrome headless at 2x retina resolution."""
    html_path = Path(html_path).resolve()
    out_path  = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--disable-extensions",
            f"--force-device-scale-factor={DPR}",
            f"--window-size={CARD_W},{CARD_H}",
            f"--screenshot={out_path}",
            f"file://{html_path}",
        ],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Chrome headless failed (exit {result.returncode}):\n"
            + result.stderr.decode(errors="replace")
        )
    if not out_path.exists():
        raise RuntimeError(f"Chrome ran but output not found: {out_path}")


def quality_check(png_path: Path) -> bool:
    from PIL import Image

    img = Image.open(png_path).convert("RGB")
    w, h = img.size
    size_bytes = Path(png_path).stat().st_size
    cx, cy = w // 2, h // 2

    checks = {
        f"dimensions_{OUT_W}x{OUT_H}": (w, h) == (OUT_W, OUT_H),
        "file_size_ok":  50_000 < size_bytes < 8_000_000,
        "center_not_white": img.getpixel((cx, cy)) != (255, 255, 255),
        "corners_dark": all(
            sum(img.getpixel(pt)) < 300
            # y=50 skips the top gradient stripe + glow; bottom corners unchanged
            for pt in [(5, 50), (w - 5, 50), (5, h - 5), (w - 5, h - 5)]
        ),
    }

    all_pass = all(checks.values())
    for name, ok in checks.items():
        print(f"  QC {'PASS' if ok else 'FAIL'}: {name}")
    if not all_pass:
        print("  QC FAILED — inspect the output PNG before posting")
    else:
        kb = size_bytes // 1024
        print(f"  QC PASS: {w}×{h}px · {kb}KB  [2x retina]")
    return all_pass
