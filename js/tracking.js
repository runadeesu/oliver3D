// Camera + MediaPipe (face / hands / pose). Everything runs on the device.
import { FilesetResolver, FaceLandmarker, HandLandmarker, PoseLandmarker } from '../vendor/mediapipe/vision_bundle.mjs';

const WASM = new URL('../vendor/mediapipe/wasm', import.meta.url).href;
const MODELS = new URL('../models/', import.meta.url).href;

async function create(Klass, fileset, opts) {
  for (const delegate of ['GPU', 'CPU']) {
    try {
      return await Klass.createFromOptions(fileset, { ...opts, baseOptions: { ...opts.baseOptions, delegate } });
    } catch (e) {
      console.warn(Klass.name, delegate, 'failed', e);
    }
  }
  throw new Error('MediaPipe init failed');
}

export class Tracker {
  constructor() {
    this.video = document.createElement('video');
    this.video.playsInline = true; this.video.muted = true; this.video.autoplay = true;
    this.face = null; this.hands = null; this.pose = null;
    this.useHands = true; this.usePose = true;
    this.last = { face: null, hands: null, pose: null, t: 0 };
    this.frame = 0; this.lastVideoTime = -1;
    this.busy = false;
  }

  async start(onStatus) {
    onStatus?.('カメラを起動中…');
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } }, audio: false,
    });
    this.stream = stream;
    this.video.srcObject = stream;
    await this.video.play().catch(() => {});
    onStatus?.('顔トラッキングを準備中…');
    this.fileset = await FilesetResolver.forVisionTasks(WASM);
    this.face = await create(FaceLandmarker, this.fileset, {
      baseOptions: { modelAssetPath: MODELS + 'face_landmarker.task' }, runningMode: 'VIDEO', numFaces: 1,
      outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
    });
    onStatus?.('手と体のトラッキングを準備中…');
    await this.ensureBody();
    onStatus?.('');
  }

  async ensureBody() {
    if (this.useHands && !this.hands) {
      this.hands = await create(HandLandmarker, this.fileset, {
        baseOptions: { modelAssetPath: MODELS + 'hand_landmarker.task' }, runningMode: 'VIDEO', numHands: 2,
        minHandDetectionConfidence: 0.5, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5,
      });
    }
    if (this.usePose && !this.pose) {
      this.pose = await create(PoseLandmarker, this.fileset, {
        baseOptions: { modelAssetPath: MODELS + 'pose_landmarker_lite.task' }, runningMode: 'VIDEO', numPoses: 1,
      });
    }
  }

  stop() {
    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = null;
  }

  // call every animation frame; returns true when new results arrived
  step(now) {
    const v = this.video;
    if (!this.face || v.readyState < 2 || v.currentTime === this.lastVideoTime) return false;
    this.lastVideoTime = v.currentTime;
    const ts = Math.round(now);
    if (ts <= (this._ts || 0)) return false;
    this._ts = ts;
    this.frame++;
    try {
      this.last.face = this.face.detectForVideo(v, ts);
      // hands and pose alternate frames to keep phones smooth
      const odd = this.frame % 2 === 1;
      if (this.useHands && this.hands && (odd || !this.usePose)) this.last.hands = this.hands.detectForVideo(v, ts);
      if (this.usePose && this.pose && (!odd || !this.useHands)) this.last.pose = this.pose.detectForVideo(v, ts);
      if (!this.useHands) this.last.hands = null;
      if (!this.usePose) this.last.pose = null;
      this.last.t = now;
    } catch (e) {
      console.warn('detect error', e);
    }
    return true;
  }
}
