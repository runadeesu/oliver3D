"""Detect the 478 MediaPipe face-mesh landmarks of a face in an image (photo or a render of the model).
python3 face_landmarks.py <image> <out.json> [x0,y0,x1,y1 [upscale]]
Needs mediapipe + the face_landmarker.task model (env OLIVER_MPLIBS = pip --target dir, OLIVER_FACE_MODEL = .task file).
Writes [[x, y, z], ...] in pixels of the (uncropped) input image."""
import sys, os, json
sys.path.insert(0, os.environ["OLIVER_MPLIBS"])
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision
from PIL import Image

path, out = sys.argv[1], sys.argv[2]
im = Image.open(path).convert("RGB")
crop = tuple(int(v) for v in sys.argv[3].split(",")) if len(sys.argv) > 3 else (0, 0, im.width, im.height)
up = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
c = im.crop(crop)
big = c.resize((int(c.width * up), int(c.height * up)), Image.LANCZOS) if up != 1.0 else c
opts = vision.FaceLandmarkerOptions(base_options=mpp.BaseOptions(model_asset_path=os.environ["OLIVER_FACE_MODEL"]), num_faces=1,
                                    min_face_detection_confidence=0.05, min_face_presence_confidence=0.05)
det = vision.FaceLandmarker.create_from_options(opts)
res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(big)))
if not res.face_landmarks:
    print("NO FACE in", path)
    os._exit(1)
pts = np.array([[p.x * big.width / up + crop[0], p.y * big.height / up + crop[1], p.z * big.width / up] for p in res.face_landmarks[0]])
json.dump(pts.tolist(), open(out, "w"))
print("landmarks", len(pts), "->", out)
os._exit(0)     # the mediapipe C++ teardown crashes at interpreter exit on some builds
