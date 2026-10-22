"""Sharpen the face of a (low-resolution) reference photo with GFPGAN v1.4 (ONNX, CPU).
python3 face_restore.py <photo> <photo_landmarks.json> <out.png> [scale]
The face is aligned to the 512x512 FFHQ template (eyes / nose / mouth corners from the MediaPipe landmarks), restored, pasted back
into an up-scaled copy of the photo with a feathered mask. Needs onnxruntime + opencv (OLIVER_MPLIBS) and OLIVER_GFPGAN (path of GFPGANv1.4.onnx).
Output: the up-scaled photo (scale x) with the restored face; the scale is returned so that landmarks can be multiplied by it."""
import sys, os, json
if os.environ.get("OLIVER_MPLIBS"):
    sys.path.insert(0, os.environ["OLIVER_MPLIBS"])
import numpy as np, cv2
import onnxruntime as ort

photo, lmp, out = sys.argv[1:4]
scale = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0
img = cv2.imread(photo, cv2.IMREAD_COLOR)
L = np.array(json.load(open(lmp)))[:, :2]
big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
L = L * scale
# 5 points (FFHQ template at 512): left eye, right eye, nose tip, mouth left, mouth right  (image left/right)
eye_r = L[[33, 133, 468]].mean(0) if len(L) > 468 else L[[33, 133]].mean(0)       # subject's right eye = image left
eye_l = L[[362, 263, 473]].mean(0) if len(L) > 473 else L[[362, 263]].mean(0)
src = np.array([eye_r, eye_l, L[1], L[61], L[291]], np.float32)
tmpl = np.array([[192.98, 239.95], [318.90, 240.19], [256.63, 314.02], [201.26, 371.41], [313.09, 371.15]], np.float32)
M, _ = cv2.estimateAffinePartial2D(src, tmpl, method=cv2.LMEDS)
crop = cv2.warpAffine(big, M, (512, 512), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
cv2.imwrite(out.replace(".png", "_crop.png"), crop)
sess = ort.InferenceSession(os.environ["OLIVER_GFPGAN"], providers=["CPUExecutionProvider"])
x = (cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0 - 0.5) / 0.5
y = sess.run(None, {"input": x.transpose(2, 0, 1)[None]})[0][0]
res = ((y.transpose(1, 2, 0) * 0.5 + 0.5).clip(0, 1) * 255).astype(np.uint8)
res = cv2.cvtColor(res, cv2.COLOR_RGB2BGR)
cv2.imwrite(out.replace(".png", "_restored_crop.png"), res)
# paste back (inverse affine) with a soft elliptical mask
Mi = cv2.invertAffineTransform(M)
H, W = big.shape[:2]
back = cv2.warpAffine(res, Mi, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
mask = np.zeros((512, 512), np.float32)
cv2.ellipse(mask, (256, 300), (170, 215), 0, 0, 360, 1.0, -1)
mask = cv2.GaussianBlur(mask, (0, 0), 14)
mb = cv2.warpAffine(mask, Mi, (W, H), flags=cv2.INTER_LINEAR)[..., None]
comp = (back.astype(np.float32) * mb + big.astype(np.float32) * (1 - mb)).astype(np.uint8)
cv2.imwrite(out, comp)
print("restored ->", out, "scale", scale, "size", comp.shape[:2][::-1])
os._exit(0)
