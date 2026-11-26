#!/usr/bin/env python3
"""Embed models/car_*.glb and models/thumb_*.jpg into index.html (between <!--MODELS--> markers).

Keeps the game a single self-contained file, so it runs from file:// as well as from GitHub Pages.
Usage: python3 tools/embed_models.py
"""
import base64, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARS = ['hatch', 'supermini', 'coupe', 'crossover']
html = (ROOT / 'index.html').read_text()
parts = ['<!--MODELS-->']
for k in CARS:
    glb = ROOT / 'models' / f'car_{k}.glb'
    thumb = ROOT / 'models' / f'thumb_{k}.jpg'
    parts.append(f'<script id="glb_{k}" type="application/octet-stream">{base64.b64encode(glb.read_bytes()).decode()}</script>')
    if thumb.exists():
        parts.append(f'<script id="thumb_{k}" type="text/plain">{base64.b64encode(thumb.read_bytes()).decode()}</script>')
parts.append('<!--/MODELS-->')
new, n = re.subn(r'<!--MODELS-->.*?<!--/MODELS-->', lambda m: '\n'.join(parts), html, flags=re.S)
assert n == 1, 'MODELS markers not found in index.html'
(ROOT / 'index.html').write_text(new)
print(f'embedded {len(CARS)} cars -> index.html ({len(new) / 1024:.0f} KB)')
