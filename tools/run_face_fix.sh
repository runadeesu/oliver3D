#!/usr/bin/env bash
# Face correction of one model from a reference photo. Usage: run_face_fix.sh <tag> <photo> [photo_crop x0,y0,x1,y1]
# Steps (see README "顔の修正"):
#   0. GFPGAN v1.4 restores the photo's face (3x upscale)         -> $OLIVER_WORK/face/<tag>_restored.png (+ landmarks)
#   1. landmarks of the model's front render and of the restored photo
#   2. (only if tools/configs/<tag>.json has "surgery") face_surgery.py: warp the face geometry towards the photo and rebuild glasses;
#      then step 1 is repeated on the new geometry
#   3. face_texture.py: photo -> model front view (thin-plate spline), colour / shading / features into the 8K UV texture
# needs: OLIVER_WORK OLIVER_TEX OLIVER_PYLIBS BLENDER (setup_env.sh), OLIVER_MPLIBS (pip install --target <dir> mediapipe onnxruntime),
#        OLIVER_FACE_MODEL (face_landmarker.task from storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/),
#        OLIVER_GFPGAN (GFPGANv1.4.onnx, e.g. huggingface.co/datasets/Gourieff/ReActor/resolve/main/models/facerestore_models/GFPGANv1.4.onnx)
# result: $OLIVER_WORK/face/<tag>_tex_new.png (corrected base colour, same size / UVs as the original), <tag>_new.png (render)
set -e
TAG=$1; PHOTO=$2; CROP=${3:-0,0,100000,100000}
HERE=$(cd "$(dirname "$0")" && pwd)
export OLIVER_ROOT=$(cd "$HERE/.." && pwd)
OUT=$OLIVER_WORK/face; mkdir -p "$OUT"
render() { FACE_TEX=$1 "$BLENDER" -b --factory-startup --python "$HERE/oliver_rig/face_render.py" -- "$TAG" "$2" 0.38 1400 $3; }
TEXIN=$OLIVER_TEX/$TAG/texture_0.png
# 0. restore the photo
python3 "$HERE/oliver_rig/face_landmarks.py" "$PHOTO" "$OUT/${TAG}_photo_lm0.json" "$CROP" 4
python3 "$HERE/oliver_rig/face_restore.py" "$PHOTO" "$OUT/${TAG}_photo_lm0.json" "$OUT/${TAG}_restored.png" 3
# 1. model front view + landmarks (original geometry)
render "$TEXIN" "$OUT/${TAG}_base.png"
python3 "$HERE/oliver_rig/face_landmarks.py" "$OUT/${TAG}_base.png" "$OUT/${TAG}_base_lm.json"
# landmarks of the restored photo = landmarks of the original photo x3 (the restored image is a 3x upscale)
python3 -c "import json,sys; L=json.load(open(sys.argv[1])); json.dump([[x*3,y*3,z*3] for x,y,z in L], open(sys.argv[2],'w'))" "$OUT/${TAG}_photo_lm0.json" "$OUT/${TAG}_photo_lm.json"
# 2. optional geometry surgery (face warp + glasses)
if grep -q '"surgery"' "$HERE/configs/$TAG.json"; then
  "$BLENDER" -b --factory-startup --python "$HERE/oliver_rig/face_surgery.py" -- "$TAG" "$OUT/${TAG}_base_lm.json" "$OUT/${TAG}_base.png.json" "$OUT/${TAG}_photo_lm.json"
  [ -f "$OLIVER_WORK/${TAG}_tex_prefilled.png" ] && TEXIN=$OLIVER_WORK/${TAG}_tex_prefilled.png
fi
# 3. texture transfer
render "$TEXIN" "$OUT/${TAG}_orig.png"
python3 "$HERE/oliver_rig/face_landmarks.py" "$OUT/${TAG}_orig.png" "$OUT/${TAG}_orig_lm.json"
python3 "$HERE/oliver_rig/face_texture.py" "$TAG" "$OUT/${TAG}_restored.png" "$OUT/${TAG}_orig_lm.json" "$OUT/${TAG}_photo_lm.json" "$OUT/${TAG}_orig.png" "$TEXIN" "$OUT/${TAG}_tex_new.png" "$OUT/dbg"
FACE_GLASSES=1 render "$OUT/${TAG}_tex_new.png" "$OUT/${TAG}_new.png"
echo "done: $OUT/${TAG}_tex_new.png"
