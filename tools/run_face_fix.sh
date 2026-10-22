#!/usr/bin/env bash
# Face correction of one model from a reference photo (texture only). Usage: run_face_fix.sh <tag> <photo> [photo_crop x0,y0,x1,y1 [upscale]]
# needs: OLIVER_WORK OLIVER_TEX OLIVER_PYLIBS BLENDER (setup_env.sh), OLIVER_MPLIBS (pip install --target <dir> mediapipe numpy opencv-contrib-python pillow),
#        OLIVER_FACE_MODEL (face_landmarker.task from storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/)
# result: $OLIVER_WORK/face/<tag>_tex_new.png (corrected base colour, same size / UVs as the original) + before/after render
set -e
TAG=$1; PHOTO=$2; CROP=${3:-0,0,100000,100000}; UP=${4:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
export OLIVER_ROOT=$(cd "$HERE/.." && pwd)
OUT=$OLIVER_WORK/face; mkdir -p "$OUT"
# 1. front render of the model's head + its landmarks (the model is the 'photo' the landmarks are matched to)
"$BLENDER" -b --factory-startup --python "$HERE/oliver_rig/face_render.py" -- "$TAG" "$OUT/${TAG}_orig.png" 0.38 1400
python3 "$HERE/oliver_rig/face_landmarks.py" "$OUT/${TAG}_orig.png" "$OUT/${TAG}_orig_lm.json"
# 2. landmarks of the reference photo
python3 "$HERE/oliver_rig/face_landmarks.py" "$PHOTO" "$OUT/${TAG}_photo_lm.json" "$CROP" "$UP"
# 3. warp the photo into the model's front view, swap low frequencies, bake into the UV texture
python3 "$HERE/oliver_rig/face_texture.py" "$TAG" "$PHOTO" "$OUT/${TAG}_orig_lm.json" "$OUT/${TAG}_photo_lm.json" "$OUT/${TAG}_orig.png" "$OLIVER_TEX/$TAG/texture_0.png" "$OUT/${TAG}_tex_new.png" "$OUT/dbg"
# 4. render the result for a visual check
FACE_TEX="$OUT/${TAG}_tex_new.png" "$BLENDER" -b --factory-startup --python "$HERE/oliver_rig/face_render.py" -- "$TAG" "$OUT/${TAG}_new.png" 0.38 1400
