#!/usr/bin/env python3
"""Convert ECharts SSR SVG figures to static PNG files for the Markdown paper."""
from pathlib import Path
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
for source in sorted((ROOT / "figures").glob("figure_*.svg")):
    target = source.with_suffix(".png")
    cairosvg.svg2png(url=str(source), write_to=str(target), scale=1.5)
    print(target.name)
