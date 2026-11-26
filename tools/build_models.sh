#!/usr/bin/env bash
# Rebuild every car from the Blender script, compress, render thumbnails, embed into index.html.
# Needs: Python with the `bpy` module (pip install bpy) or Blender's bundled Python, Node.js (for npx).
set -euo pipefail
cd "$(dirname "$0")/.."
CARS="hatch supermini coupe crossover"

echo "1/4 Modelling cars in Blender"
python3 blender/build_cars.py

echo "2/4 Draco-compressing GLBs into models/"
for k in $CARS; do
  npx --yes @gltf-transform/cli@4 draco "blender/car_$k.glb" "models/car_$k.glb" \
    --method edgebreaker --quantize-position 14 --quantize-normal 10
done

echo "3/4 Rendering thumbnails"
python3 blender/render_cars.py s="${SAMPLES:-24}"

echo "4/4 Embedding into index.html"
python3 tools/embed_models.py
