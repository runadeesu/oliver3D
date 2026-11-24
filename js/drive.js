// Tracking results -> the rig's own controls (fc_*, jaw_*, hand_*), head/eyes/arms.
import * as THREE from 'three';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;

// calibrated against renders of the avatar itself (see tests)
export const CAL = { yaw: 1, pitch: 1, roll: 1, faceLR: 1 };

const FACE_MAP = [
  // [rig prop, blendshape(s) on the subject's side, gain]
  ['fc_blink_L', ['eyeBlinkLeft'], 1.15], ['fc_blink_R', ['eyeBlinkRight'], 1.15],
  ['fc_smile_L', ['mouthSmileLeft'], 1.6], ['fc_smile_R', ['mouthSmileRight'], 1.6],
  ['fc_frown_L', ['mouthFrownLeft'], 1.2], ['fc_frown_R', ['mouthFrownRight'], 1.2],
  ['fc_brow_up_L', ['browOuterUpLeft'], 1.0], ['fc_brow_up_R', ['browOuterUpRight'], 1.0],
  ['fc_brow_down_L', ['browDownLeft'], 1.0], ['fc_brow_down_R', ['browDownRight'], 1.0],
  ['fc_mouth_left', ['mouthLeft'], 1.3], ['fc_mouth_right', ['mouthRight'], 1.3],
];
const FACE_SYM = [
  ['fc_brow_worry', ['browInnerUp'], 1.0],
  ['fc_eye_wide', ['eyeWideLeft', 'eyeWideRight'], 1.2],
  ['fc_eye_squint', ['eyeSquintLeft', 'eyeSquintRight'], 0.9],
  ['fc_mouth_wide', ['mouthStretchLeft', 'mouthStretchRight'], 1.4],
  ['fc_pucker', ['mouthPucker'], 1.1],
  ['fc_funnel', ['mouthFunnel'], 1.3],
  ['fc_press', ['mouthPressLeft', 'mouthPressRight'], 1.0],
  ['fc_upper_lip_up', ['mouthUpperUpLeft', 'mouthUpperUpRight'], 1.0],
  ['fc_lower_lip_down', ['mouthLowerDownLeft', 'mouthLowerDownRight'], 1.0],
  ['fc_cheek_puff', ['cheekPuff'], 1.4],
  ['fc_cheek_raise', ['cheekSquintLeft', 'cheekSquintRight'], 1.0],
  ['fc_sneer', ['noseSneerLeft', 'noseSneerRight'], 1.0],
];
const SWAP = s => s.replace(/_L$/, '_X').replace(/_R$/, '_L').replace(/_X$/, '_R')
  .replace('mouth_left', 'mouth_TMP').replace('mouth_right', 'mouth_left').replace('mouth_TMP', 'mouth_right');

// smoothed scalar store
class Smooth {
  constructor() { this.v = {}; }
  get(k, target, rate, dt) {
    const a = 1 - Math.exp(-rate * dt);
    const cur = this.v[k] ?? target;
    const nv = cur + (target - cur) * a;
    this.v[k] = nv; return nv;
  }
}

// MediaPipe (image x right, y down, z away) -> character space (X = avatar left, Y up, Z toward viewer)
function toChar(l, mirror, out = new THREE.Vector3()) {
  return out.set(mirror ? -l.x : l.x, -l.y, -l.z);
}

export class Driver {
  constructor(rig) {
    this.rig = rig;
    this.mirror = true;
    this.sm = new Smooth();
    this.neutral = null;        // head calibration (quaternion)
    this.bsNeutral = {};        // blendshape resting offsets
    this.headQ = new THREE.Quaternion();
    this.faceSeen = 0; this.handSeen = [0, 0]; this.armW = { L: 0, R: 0 }; this.handW = { L: 0, R: 0 };
    this.blinkT = 2; this.blinkPhase = -1;
    this.manualFingers = true;
    this.lastBs = null; this.lastHeadRaw = null;
    this.armTargets = { L: null, R: null };
    this.debug = {};
  }

  calibrate() {
    if (this.lastHeadRaw) this.neutral = this.lastHeadRaw.clone().invert();
    if (this.lastBs) {
      this.bsNeutral = {};
      for (const [k, v] of Object.entries(this.lastBs)) this.bsNeutral[k] = Math.min(v, 0.35);
    }
  }

  bs(name) { const b = this.lastBs; if (!b) return 0; return Math.max(0, (b[name] || 0) - (this.bsNeutral[name] || 0) * 0.85); }

  update(res, dt, now) {
    const R = this.rig, P = R.props;
    const face = res?.face;
    const hasFace = face && face.faceBlendshapes && face.faceBlendshapes.length > 0;
    if (hasFace) {
      this.faceSeen = now;
      const cats = face.faceBlendshapes[0].categories;
      const bs = {}; for (const c of cats) bs[c.categoryName] = c.score;
      this.lastBs = bs;
      // L/R: MediaPipe names follow the subject; in mirror mode the avatar mirrors the user
      const swap = this.mirror !== (CAL.faceLR < 0);
      for (const [prop, names, gain] of FACE_MAP) {
        const raw = names.reduce((a, n) => a + this.bs(n), 0) / names.length;
        const v = prop.startsWith('fc_blink') ? clamp((raw - 0.14) / 0.36, 0, 1) : clamp(raw * gain, 0, 1);
        const target = swap ? SWAP(prop) : prop;
        const rate = prop.startsWith('fc_blink') ? 40 : 18;
        P[target] = this.sm.get(target, v, rate, dt);
      }
      for (const [prop, names, gain] of FACE_SYM) {
        const v = clamp(names.reduce((a, n) => a + this.bs(n), 0) / names.length * gain, 0, 1);
        P[prop] = this.sm.get(prop, v, 18, dt);
      }
      P.fc_blink = 0;
      P.jaw_open = this.sm.get('jaw', clamp((this.bs('jawOpen') - 0.03) * 1.7, 0, 1), 25, dt);
      const jlr = (this.bs('jawLeft') - this.bs('jawRight')) * 1.5 * (swap ? -1 : 1);
      P.jaw_lr = this.sm.get('jlr', clamp(jlr, -1, 1), 15, dt);
      P.jaw_fwd = this.sm.get('jfw', clamp(this.bs('jawForward') * 1.5, 0, 1), 15, dt);
      // gaze (subject-left positive), then mirrored
      const yawL = ((this.bs('eyeLookOutLeft') + this.bs('eyeLookInRight')) - (this.bs('eyeLookInLeft') + this.bs('eyeLookOutRight'))) * 0.5;
      const pitch = (this.bs('eyeLookUpLeft') + this.bs('eyeLookUpRight') - this.bs('eyeLookDownLeft') - this.bs('eyeLookDownRight')) * 0.5;
      R.gaze.yaw = this.sm.get('gy', clamp(yawL * 0.55 * (swap ? -1 : 1) * CAL.faceLR, -0.5, 0.5), 20, dt);
      R.gaze.pitch = this.sm.get('gp', clamp(pitch * 0.45 + 0.04, -0.4, 0.4), 20, dt);
      // head rotation
      const mats = face.facialTransformationMatrixes;
      if (mats && mats.length) {
        const m = new THREE.Matrix4().fromArray(mats[0].data);
        const q = new THREE.Quaternion().setFromRotationMatrix(m);
        this.lastHeadRaw = q.clone();
        if (this.neutral) q.premultiply(this.neutral);
        const e = new THREE.Euler().setFromQuaternion(q, 'YXZ');
        let yaw = e.y * CAL.yaw * 1.1, pitch2 = e.x * CAL.pitch * 1.1, roll = e.z * CAL.roll;
        if (this.mirror) { yaw = -yaw; roll = -roll; }
        this.debug.head = [e.x, e.y, e.z];
        const target = new THREE.Quaternion().setFromEuler(new THREE.Euler(clamp(pitch2, -0.7, 0.7), clamp(yaw, -0.9, 0.9), clamp(roll, -0.6, 0.6), 'YXZ'));
        this.headQ.slerp(target, 1 - Math.exp(-14 * dt));
        // head translation -> subtle body lean
        const tx = m.elements[12], ty = m.elements[13];
        this.lean = this.lean || { x: 0, y: 0 };
        this.lean.x = lerp(this.lean.x, clamp((this.mirror ? -tx : tx) * 0.012, -0.18, 0.18), 1 - Math.exp(-4 * dt));
      }
    } else {
      // idle: relax towards neutral, auto blink, soft breathing
      const away = now - this.faceSeen > 600;
      if (away) {
        for (const [prop] of FACE_MAP) { P[prop] = this.sm.get(prop, 0, 6, dt); P[SWAP(prop)] = this.sm.get(SWAP(prop), 0, 6, dt); }
        for (const [prop] of FACE_SYM) P[prop] = this.sm.get(prop, 0, 6, dt);
        P.jaw_open = this.sm.get('jaw', 0, 8, dt);
        this.headQ.slerp(new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.sin(now / 2300) * 0.03, Math.sin(now / 3100) * 0.06, Math.sin(now / 2700) * 0.02, 'YXZ')), 1 - Math.exp(-2 * dt));
        R.gaze.yaw = this.sm.get('gy', Math.sin(now / 1900) * 0.08, 3, dt); R.gaze.pitch = this.sm.get('gp', 0.03, 3, dt);
        this.autoBlink(dt);
      }
    }
    R.headQ.copy(this.headQ);
    // spine lean from head offset + breathing
    const br = Math.sin(now / 1000 * 2 * Math.PI / 4.2);
    R.bodyLean = { roll: (this.lean?.x || 0) * 0.6, breath: br };

    this.updateBody(res, dt, now);
  }

  autoBlink(dt) {
    const P = this.rig.props;
    this.blinkT -= dt;
    if (this.blinkT <= 0 && this.blinkPhase < 0) { this.blinkPhase = 0; this.blinkT = 2 + Math.random() * 3.5; }
    if (this.blinkPhase >= 0) {
      this.blinkPhase += dt / 0.16;
      P.fc_blink = Math.sin(Math.min(1, this.blinkPhase) * Math.PI);
      if (this.blinkPhase >= 1) { this.blinkPhase = -1; P.fc_blink = 0; }
    }
  }

  // arms from pose world landmarks, hands from hand landmarks
  updateBody(res, dt, now) {
    const R = this.rig, P = R.props;
    const pose = res?.pose, hands = res?.hands;
    const pl = pose?.worldLandmarks?.[0], pn = pose?.landmarks?.[0];
    const a = 1 - Math.exp(-10 * dt);
    for (const side of ['L', 'R']) {
      // which subject arm drives this avatar arm
      const subjLeft = this.mirror ? side === 'R' : side === 'L';
      const [iS, iE, iW] = subjLeft ? [11, 13, 15] : [12, 14, 16];
      let ok = false;
      if (pl && pn) {
        const vis = Math.min(pn[iS].visibility ?? 1, pn[iE].visibility ?? 1, pn[iW].visibility ?? 1);
        const inFrame = pn[iW].y < 1.02 && pn[iE].y < 1.05;
        ok = vis > 0.55 && inFrame;
        if (ok) {
          const s = toChar(pl[iS], this.mirror), e = toChar(pl[iE], this.mirror), w = toChar(pl[iW], this.mirror);
          const up = e.clone().sub(s).normalize(), fo = w.clone().sub(e).normalize();
          const T = (this.armTargets[side] ||= { up: null, fo: null, hand: null });
          if (!T.up) { T.up = up.clone(); T.fo = fo.clone(); }
          else { T.up.lerp(up, a).normalize(); T.fo.lerp(fo, a).normalize(); }
        }
      }
      this.armW[side] = lerp(this.armW[side], ok ? 1 : 0, 1 - Math.exp(-(ok ? 8 : 3) * dt));
    }
    // hands: match each detected hand to a pose wrist (robust to handedness labels)
    const seen = { L: false, R: false };
    if (hands && hands.landmarks && hands.landmarks.length) {
      hands.landmarks.forEach((lm, hi) => {
        let subjLeft;
        if (pn) {
          const w = lm[0];
          const dl = Math.hypot(w.x - pn[15].x, w.y - pn[15].y), dr = Math.hypot(w.x - pn[16].x, w.y - pn[16].y);
          subjLeft = dl < dr;
        } else {
          const lab = hands.handedness?.[hi]?.[0]?.categoryName;
          subjLeft = lab === 'Left'; // on un-mirrored camera frames the label matches the subject's hand (checked)
        }
        const side = (this.mirror ? !subjLeft : subjLeft) ? 'L' : 'R';
        if (seen[side]) return;
        seen[side] = true;
        const wl = hands.worldLandmarks?.[hi] || lm;
        this.applyHand(side, wl, dt);
      });
    }
    for (const side of ['L', 'R']) {
      this.handW[side] = lerp(this.handW[side], seen[side] ? 1 : 0, 1 - Math.exp(-(seen[side] ? 10 : 2.5) * dt));
      if (!seen[side]) {
        // fade fingers back to the file's relaxed hand
        P[`hand_${side}_relax`] = lerp(P[`hand_${side}_relax`], 1, 1 - Math.exp(-3 * dt));
        if (!this.manualFingers) for (const f of ['thumb', 'index', 'middle', 'ring', 'pinky', 'spread'])
          P[`hand_${side}_${f}`] = lerp(P[`hand_${side}_${f}`], 0, 1 - Math.exp(-3 * dt));
      }
    }
    R.armTargets = this.armTargets; R.armW = this.armW; R.handW = this.handW;
  }

  applyHand(side, lm, dt) {
    const P = this.rig.props;
    const V = i => toChar(lm[i], this.mirror);
    const ang = (a, b, c) => { const u = V(b).sub(V(a)).normalize(), v = V(c).sub(V(b)).normalize(); return Math.acos(clamp(u.dot(v), -1, 1)); };
    const curl = ([w, m, p, d, t]) => ang(w, m, p) + ang(m, p, d) + ang(p, d, t);
    const fingers = { index: [0, 5, 6, 7, 8], middle: [0, 9, 10, 11, 12], ring: [0, 13, 14, 15, 16], pinky: [0, 17, 18, 19, 20] };
    const k = 1 - Math.exp(-16 * dt);
    this.manualFingers = false;
    P[`hand_${side}_relax`] = lerp(P[`hand_${side}_relax`], 0, k);
    P[`hand_${side}_fist`] = lerp(P[`hand_${side}_fist`], 0, k);
    for (const [f, ids] of Object.entries(fingers)) {
      const c = clamp((curl(ids) - 0.35) / 3.0, 0, 1);
      P[`hand_${side}_${f}`] = lerp(P[`hand_${side}_${f}`], c, k);
    }
    const th = ang(1, 2, 3) + ang(2, 3, 4);
    P[`hand_${side}_thumb`] = lerp(P[`hand_${side}_thumb`], clamp((th - 0.45) / 1.3, 0, 1), k);
    const di = V(6).sub(V(5)).normalize(), dp = V(18).sub(V(17)).normalize();
    const spread = Math.acos(clamp(di.dot(dp), -1, 1));
    P[`hand_${side}_spread`] = lerp(P[`hand_${side}_spread`], clamp((spread - 0.32) / 0.3, -1, 1), k);
    // palm frame for the hand bone
    const f = V(9).sub(V(0)).normalize();
    const sdir = V(5).sub(V(17)).normalize();
    const T = (this.armTargets[side] ||= { up: null, fo: null, hand: null });
    T.hand = T.hand || { f: f.clone(), s: sdir.clone() };
    T.hand.f.lerp(f, k).normalize(); T.hand.s.lerp(sdir, k).normalize();
  }
}
