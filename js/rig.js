// Port of the OT_Rig control network from the .blend:
// custom properties -> (drivers) -> MCH bones / shape keys -> (constraints) -> deform bones.
import * as THREE from 'three';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _e = new THREE.Euler();
const ID = new THREE.Quaternion();

// Blender 'XYZ' euler == three.js order 'ZYX'
function blEuler(x, y, z, out = new THREE.Quaternion()) {
  _e.set(x, y, z, 'ZYX');
  return out.setFromEuler(_e);
}

// twist angle of quaternion q around local axis (unit vector)
function twistAngle(q, axis) {
  const d = q.x * axis.x + q.y * axis.y + q.z * axis.z;
  const tw = new THREE.Quaternion(axis.x * d, axis.y * d, axis.z * d, q.w).normalize();
  let a = 2 * Math.atan2(Math.hypot(tw.x, tw.y, tw.z), tw.w);
  if (d < 0) a = -a;
  if (a > Math.PI) a -= 2 * Math.PI; if (a < -Math.PI) a += 2 * Math.PI;
  return a;
}

export class OTRig {
  constructor(root, def) {
    this.root = root;
    this.def = def;
    this.props = {};
    for (const [k, v] of Object.entries(def.props)) this.props[k] = v.default;
    this.bones = {};
    root.traverse(o => { if (o.isBone) this.bones[o.name] = o; });
    this.rest = {};
    for (const [n, b] of Object.entries(this.bones)) this.rest[n] = { q: b.quaternion.clone(), p: b.position.clone() };
    root.updateMatrixWorld(true);
    this.restWorldQ = {};
    for (const [n, b] of Object.entries(this.bones)) this.restWorldQ[n] = b.getWorldQuaternion(new THREE.Quaternion());
    // morph targets: name -> [[mesh, index], ...]
    this.morph = {};
    root.traverse(o => {
      if (o.morphTargetDictionary) {
        for (const [k, i] of Object.entries(o.morphTargetDictionary)) (this.morph[k] ||= []).push([o, i]);
        o.morphTargetInfluences.fill(0);
      }
    });
    this.shapeDrivers = def.shapeDrivers.filter(d => d.linear && (d.objects.includes('CC_Base_Body') || d.objects.includes('CC_Base_Eye')));
    this.boneDrivers = def.boneDrivers.filter(d => d.linear);
    this.fingerCons = def.constraints.filter(c => c.name === 'Finger controls');
    this.defaultPose = {};
    for (const [n, p] of Object.entries(def.defaultPose)) this.defaultPose[n] = new THREE.Quaternion(p.q[1], p.q[2], p.q[3], p.q[0]);
    // external inputs (set by tracking / UI)
    this.headQ = new THREE.Quaternion();     // world-space head rotation (character axes: X=left, Y=up, Z=front)
    this.gaze = { yaw: 0, pitch: 0 };         // radians, + = character's left / up
    this.armOverride = {};                    // boneName -> local quaternion (absolute, replaces rest*default)
    this.extraMorph = {};                     // direct shape key overrides added on top
    this.mch = {};
  }

  set(name, v) { if (name in this.props) this.props[name] = v; }

  evalLinear(d) {
    let v = d.c;
    for (const [p, w] of d.terms) v += w * (this.props[p] || 0);
    return clamp(v, d.lo, d.hi);
  }

  morphSet(name, v) {
    const list = this.morph[name];
    if (list) for (const [m, i] of list) m.morphTargetInfluences[i] = v;
  }

  aim(boneName, childName, dir, w) {
    const b = this.bones[boneName], c = this.bones[childName];
    if (!b || !c) return;
    b.updateWorldMatrix(true, true);
    const p0 = new THREE.Vector3().setFromMatrixPosition(b.matrixWorld);
    const d0 = new THREE.Vector3().setFromMatrixPosition(c.matrixWorld).sub(p0).normalize();
    const q = new THREE.Quaternion().setFromUnitVectors(d0, dir);
    const bw = b.getWorldQuaternion(new THREE.Quaternion());
    const target = q.multiply(bw);
    const pw = b.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
    b.quaternion.slerp(pw.multiply(target), w);
    b.updateWorldMatrix(false, true);
  }

  orientHand(s, f, sd, w) {
    const h = this.bones[`CC_Base_${s}_Hand`], mid = this.bones[`CC_Base_${s}_Mid1`];
    const idx = this.bones[`CC_Base_${s}_Index1`], pk = this.bones[`CC_Base_${s}_Pinky1`];
    if (!h || !mid || !idx || !pk) return;
    h.updateWorldMatrix(true, true);
    const pos = o => new THREE.Vector3().setFromMatrixPosition(o.matrixWorld);
    const fa = pos(mid).sub(pos(h)).normalize(), sa = pos(idx).sub(pos(pk)).normalize();
    const basis = (a, b) => { const e1 = a.clone().normalize(); const e3 = a.clone().cross(b).normalize(); const e2 = e3.clone().cross(e1); return new THREE.Matrix4().makeBasis(e1, e2, e3); };
    const Ba = basis(fa, sa), Bt = basis(f, sd);
    const Rm = Bt.multiply(Ba.transpose());
    const q = new THREE.Quaternion().setFromRotationMatrix(Rm);
    const hw = h.getWorldQuaternion(new THREE.Quaternion());
    const target = q.multiply(hw);
    const pw = h.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
    h.quaternion.slerp(pw.multiply(target), w);
  }

  update() {
    const P = this.props, B = this.bones, R = this.rest;
    // 1) MCH bone channels from drivers
    const mch = this.mch;
    for (const k in mch) { mch[k].rot[0] = mch[k].rot[1] = mch[k].rot[2] = 0; mch[k].loc[0] = mch[k].loc[1] = mch[k].loc[2] = 0; }
    for (const d of this.boneDrivers) {
      const m = (mch[d.bone] ||= { rot: [0, 0, 0], loc: [0, 0, 0] });
      (d.channel === 'location' ? m.loc : m.rot)[d.index] = this.evalLinear(d);
    }
    // 2) reset deform bones to rest (+ the file's default pose)
    for (const [n, b] of Object.entries(B)) {
      b.quaternion.copy(R[n].q);
      b.position.copy(R[n].p);
      if (this.defaultPose[n]) b.quaternion.multiply(this.defaultPose[n]);
      if (this.armOverride[n]) b.quaternion.copy(this.armOverride[n]);
    }
    // 4) jaw
    const jm = mch['MCH_Jaw'] || { rot: [0, 0, 0], loc: [0, 0, 0] };
    const jaw = B['CC_Base_JawRoot'];
    if (jaw) {
      jaw.quaternion.multiply(blEuler(jm.rot[0], jm.rot[1], jm.rot[2], _q));
      jaw.position.add(new THREE.Vector3(...jm.loc).applyQuaternion(R['CC_Base_JawRoot'].q));
    }
    // 5) head & neck: distribute world rotation 30/30/40 like the file's constraints
    const parts = [['CC_Base_NeckTwist01', 0.3], ['CC_Base_NeckTwist02', 0.3], ['CC_Base_Head', 0.4]];
    for (const [n, f] of parts) {
      const b = B[n]; if (!b) continue;
      _q.identity().slerp(this.headQ, f);
      const W = this.restWorldQ[n];
      _q2.copy(W).invert().multiply(_q).multiply(W);
      b.quaternion.multiply(_q2);
    }
    // 6) eyes (damped-track equivalent): rotate around head-relative axes
    for (const n of ['CC_Base_L_Eye', 'CC_Base_R_Eye']) {
      const b = B[n]; if (!b) continue;
      _e.set(-this.gaze.pitch, this.gaze.yaw, 0, 'YXZ');
      _q.setFromEuler(_e);
      const W = this.restWorldQ[n];
      _q2.copy(W).invert().multiply(_q).multiply(W);
      b.quaternion.multiply(_q2);
    }
    // 6b) spine lean + breathing (character-space deltas)
    if (this.bodyLean) {
      const L = this.bodyLean;
      for (const [n, f] of [['CC_Base_Spine01', 0.5], ['CC_Base_Spine02', 0.5]]) {
        const b = B[n]; if (!b) continue;
        _e.set(L.breath * 0.012, 0, L.roll * f, 'YXZ');
        _q.setFromEuler(_e);
        const W = this.restWorldQ[n];
        _q2.copy(W).invert().multiply(_q).multiply(W);
        b.quaternion.multiply(_q2);
      }
    }
    // 6c) arms from tracking (aim upper arm / forearm, orient palm)
    if (this.armTargets) {
      this.root.updateMatrixWorld(true);
      for (const s of ['L', 'R']) {
        const T = this.armTargets[s]; if (!T) continue;
        const w = this.armW?.[s] || 0, wh = this.handW?.[s] || 0;
        if (w > 0.001 && T.up) {
          this.aim(`CC_Base_${s}_Upperarm`, `CC_Base_${s}_Forearm`, T.up, w);
          this.aim(`CC_Base_${s}_Forearm`, `CC_Base_${s}_Hand`, T.fo, w);
        }
        if (wh > 0.001 && T.hand && w > 0.3) this.orientHand(s, T.hand.f, T.hand.s, wh * Math.min(1, w * 1.5));
      }
    }
    // 6d) fingers: local ADD of MCH euler
    for (const c of this.fingerCons) {
      const m = mch[c.from]; const b = B[c.bone];
      if (!m || !b) continue;
      b.quaternion.multiply(blEuler(m.rot[0], m.rot[1], m.rot[2], _q));
    }
    // 7) auto twist (forearm follows hand, upper-arm twist counter-rotates)
    const yAxis = new THREE.Vector3(0, 1, 0);
    if (P.auto_twist > 0) {
      for (const s of ['L', 'R']) {
        const ua = B[`CC_Base_${s}_Upperarm`], uat = B[`CC_Base_${s}_UpperarmTwist01`];
        const hd = B[`CC_Base_${s}_Hand`], fat = B[`CC_Base_${s}_ForearmTwist01`];
        if (ua && uat) {
          _q.copy(R[ua.name].q).invert().multiply(ua.quaternion);
          const a = twistAngle(_q, yAxis);
          uat.quaternion.multiply(_q2.setFromAxisAngle(yAxis, -a * 0.5 * P.auto_twist));
        }
        if (hd && fat) {
          _q.copy(R[hd.name].q).invert().multiply(hd.quaternion);
          const a = twistAngle(_q, yAxis);
          fat.quaternion.multiply(_q2.setFromAxisAngle(yAxis, a * 0.5 * P.auto_twist));
        }
      }
    }
    // 8) shape keys from linear drivers
    for (const d of this.shapeDrivers) this.morphSet(d.key, this.evalLinear(d));
    // nonlinear drivers from the file
    const jawOpen = clamp(jm.rot[2] * 1.79049, 0, 1);
    this.morphSet('Jaw_Open', jawOpen);
    const ef = P.eyelid_follow;
    const gy = this.gaze.yaw, gp = this.gaze.pitch;
    for (const s of ['L', 'R']) {
      this.morphSet(`Eye_${s}_Look_L`, clamp(gy * 2.0463, 0, 1) * ef);
      this.morphSet(`Eye_${s}_Look_R`, clamp(-gy * 2.0463, 0, 1) * ef);
      this.morphSet(`Eye_${s}_Look_Up`, clamp(gp * 2.6044, 0, 1) * ef);
      this.morphSet(`Eye_${s}_Look_Down`, clamp(-gp * 2.6044, 0, 1) * ef);
    }
    const nc = P.neck_correctives;
    _e.setFromQuaternion(this.headQ, 'YXZ');
    const pitch = _e.x, yaw = _e.y, roll = _e.z;
    this.morphSet('Head_Turn_Down', clamp(pitch * 1.637, 0, 1) * nc);
    this.morphSet('Head_Turn_Up', clamp(-pitch * 1.637, 0, 1) * nc);
    this.morphSet('Head_Turn_L', clamp(yaw * 1.1459, 0, 1) * nc);
    this.morphSet('Head_Turn_R', clamp(-yaw * 1.1459, 0, 1) * nc);
    this.morphSet('Head_Tilt_R', clamp(roll * 1.9099, 0, 1) * nc);
    this.morphSet('Head_Tilt_L', clamp(-roll * 1.9099, 0, 1) * nc);
    this.morphSet('鼻ずらし', clamp(P.sunglasses_low, 0, 1));
    // jacket shoulder drape follows how far the upper arm is lowered
    for (const [s, div, key] of [['L', -0.3945, '肩の自然なドレープ（左）'], ['R', 0.39448, '肩の自然なドレープ（右）']]) {
      const ua = B[`CC_Base_${s}_Upperarm`];
      _q.copy(R[ua.name].q).invert().multiply(ua.quaternion);
      this.morphSet(key, P.shoulder_relax * clamp(_q.z / div, 0, 1));
    }
    for (const [k, v] of Object.entries(this.extraMorph)) {
      const list = this.morph[k]; if (!list) continue;
      for (const [m, i] of list) m.morphTargetInfluences[i] = clamp(m.morphTargetInfluences[i] + v, 0, 1);
    }
  }
}

export { blEuler, clamp };
