// Strand hair from the .blend's 'Hair' curves, drawn as camera-facing ribbons.
// Dynamics follow the file's "Hair Dynamics (OT)" settings: 1100 guide springs,
// each strand blends its 3 guides (gid/gw), scalp stiff, free beyond Free Length.
import * as THREE from 'three';

const VS = /* glsl */`
uniform sampler2D uPts; uniform sampler2D uStrand; uniform sampler2D uGuide;
uniform int uK; uniform int uW; uniform int uGW;
uniform float uWidth, uScalp, uFreeLen, uPx;
out float vT; out vec3 vTan; out vec3 vView; out float vRand; out float vCov; out float vDepth;
ivec2 tc(int i, int w) { return ivec2(i % w, i / w); }
vec3 guide(float id) { return texelFetch(uGuide, tc(int(id + 0.5), uGW), 0).xyz; }
void main() {
  int vid = gl_VertexID;
  int strand = vid / (2 * uK);
  int pt = (vid / 2) % uK;
  float sideSign = (vid % 2 == 0) ? -1.0 : 1.0;
  int base = strand * uK;
  vec4 P = texelFetch(uPts, tc(base + pt, uW), 0);
  vec4 Pn = texelFetch(uPts, tc(base + min(pt + 1, uK - 1), uW), 0);
  vec4 Pp = texelFetch(uPts, tc(base + max(pt - 1, 0), uW), 0);
  vec4 s0 = texelFetch(uStrand, tc(strand * 2, uW), 0);
  vec4 s1 = texelFetch(uStrand, tc(strand * 2 + 1, uW), 0);
  vec3 D = s1.x * guide(s0.x) + s1.y * guide(s0.y) + s1.z * guide(s0.z);
  float w = uScalp + (1.0 - uScalp) * smoothstep(0.0, uFreeLen, P.w);
  vec3 pos = P.xyz + D * w;
  vec3 tan = normalize(Pn.xyz - Pp.xyz);
  float t = float(pt) / float(uK - 1);
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  vec3 tv = normalize(mat3(modelViewMatrix) * tan);
  vec3 vdir = normalize(-mv.xyz);
  vec3 sdir = normalize(cross(tv, vdir));
  float pxPerUnit = uPx * projectionMatrix[1][1] / max(1e-4, -mv.z);
  float wWorld = uWidth * mix(1.0, 0.35, t * t);
  float wPx = wWorld * pxPerUnit;
  float use = max(wPx, 1.0);
  vCov = clamp(wPx / 1.0, 0.35, 1.0);
  mv.xyz += sdir * sideSign * 0.5 * use / pxPerUnit;
  gl_Position = projectionMatrix * mv;
  vT = t; vTan = tv; vView = vdir; vRand = s0.w; vDepth = P.w;
}`;

const FS = /* glsl */`
layout(location = 0) out highp vec4 pc_fragColor;
#define gl_FragColor pc_fragColor
uniform vec3 uRoot, uTip, uSpec; uniform vec3 uL1, uL2; uniform float uL1i, uL2i, uAmb;
in float vT; in vec3 vTan; in vec3 vView; in float vRand; in float vCov; in float vDepth;
float kk(vec3 T, vec3 L, vec3 V, float e) {
  vec3 H = normalize(L + V);
  float th = dot(T, H);
  return pow(sqrt(max(0.0, 1.0 - th * th)), e);
}
void main() {
  // stochastic coverage: thin strands keep their density without sorting
  float hsh = fract(sin(dot(gl_FragCoord.xy + vec2(vRand * 173.1, vRand * 91.7), vec2(12.9898, 78.233))) * 43758.5453);
  if (hsh > vCov) discard;
  vec3 T = normalize(vTan);
  vec3 base = mix(uRoot, uTip, smoothstep(0.0, 1.0, vT)) * (0.78 + 0.44 * vRand);
  float ao = mix(0.45, 1.0, smoothstep(0.0, 0.55, vT));
  vec3 c = base * uAmb * ao;
  for (int i = 0; i < 2; i++) {
    vec3 L = i == 0 ? uL1 : uL2; float li = i == 0 ? uL1i : uL2i;
    float tl = dot(T, L);
    float diff = sqrt(max(0.0, 1.0 - tl * tl));
    c += li * ao * (base * diff * 0.75 + uSpec * (0.22 * kk(T, L, vView, 80.0) + 0.12 * base.r * 4.0 * kk(T, L, vView, 18.0)));
  }
  gl_FragColor = vec4(c, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

export class Hair {
  constructor(meta, buf, renderer) {
    this.meta = meta;
    const N = meta.strands, K = meta.K, G = meta.guides;
    let o = 0;
    const pts = new Float32Array(buf, o, N * K * 4); o += meta.bytes.points;
    const gids = new Uint16Array(buf, o, N * 3); o += meta.bytes.gids;
    const gw = new Uint8Array(buf, o, N * 4); o += meta.bytes.gw;
    const guide = new Float32Array(buf, o, G * 6);
    const W = 1024;
    const rowsP = Math.ceil(N * K / W);
    const ptsData = new Float32Array(W * rowsP * 4); ptsData.set(pts);
    this.texPts = new THREE.DataTexture(ptsData, W, rowsP, THREE.RGBAFormat, THREE.FloatType);
    const rowsS = Math.ceil(N * 2 / W);
    const sData = new Float32Array(W * rowsS * 4);
    for (let i = 0; i < N; i++) {
      sData.set([gids[i * 3], gids[i * 3 + 1], gids[i * 3 + 2], gw[i * 4 + 3] / 255], i * 8);
      sData.set([gw[i * 4] / 255, gw[i * 4 + 1] / 255, gw[i * 4 + 2] / 255, 0], i * 8 + 4);
    }
    this.texStrand = new THREE.DataTexture(sData, W, rowsS, THREE.RGBAFormat, THREE.FloatType);
    const GW = 64, rowsG = Math.ceil(G / GW);
    this.guideData = new Float32Array(GW * rowsG * 4);
    this.texGuide = new THREE.DataTexture(this.guideData, GW, rowsG, THREE.RGBAFormat, THREE.FloatType);
    for (const t of [this.texPts, this.texStrand, this.texGuide]) {
      t.minFilter = t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true;
    }
    // guide sim state (rest-frame displacement of each guide tip)
    this.G = G;
    this.gTip = new Float32Array(G * 3); this.gMid = new Float32Array(G * 3);
    for (let g = 0; g < G; g++) { this.gTip.set(guide.subarray(g * 6, g * 6 + 3), g * 3); this.gMid.set(guide.subarray(g * 6 + 3, g * 6 + 6), g * 3); }
    this.d = new Float32Array(G * 3); this.v = new Float32Array(G * 3);
    this.prevW = null; this.prevW2 = null;
    this.enabled = true;
    // index buffer: ribbons
    const idx = new Uint32Array(N * (K - 1) * 6);
    let p = 0;
    for (let s = 0; s < N; s++) {
      const b = s * K * 2;
      for (let k = 0; k < K - 1; k++) {
        const a = b + k * 2;
        idx[p++] = a; idx[p++] = a + 1; idx[p++] = a + 2;
        idx[p++] = a + 1; idx[p++] = a + 3; idx[p++] = a + 2;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    this.N = N; this.K = K;
    geo.setDrawRange(0, idx.length);
    this.geo = geo;
    this.material = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3, vertexShader: VS, fragmentShader: FS,
      side: THREE.DoubleSide,
      uniforms: {
        uPts: { value: this.texPts }, uStrand: { value: this.texStrand }, uGuide: { value: this.texGuide },
        uK: { value: K }, uW: { value: W }, uGW: { value: GW },
        uWidth: { value: 0.00016 }, uScalp: { value: meta.dyn.scalp }, uFreeLen: { value: meta.dyn.freeLength },
        uPx: { value: 400 },
        uRoot: { value: new THREE.Color(0x140c07) }, uTip: { value: new THREE.Color(0x3b2515) },
        uSpec: { value: new THREE.Color(0xc9a27a) },
        uL1: { value: new THREE.Vector3(0.4, 0.7, 0.6).normalize() }, uL2: { value: new THREE.Vector3(-0.6, 0.3, -0.7).normalize() },
        uL1i: { value: 1.25 }, uL2i: { value: 0.55 }, uAmb: { value: 0.55 },
      },
    });
    this.mesh = new THREE.Mesh(geo, this.material);
    this.mesh.frustumCulled = false;
    this.mesh.matrixAutoUpdate = false;
    this.mesh.renderOrder = 2;
    this.setQuality(1);
  }

  setQuality(q) { // 0 = light, 1 = standard, 2 = high
    const frac = [0.45, 0.75, 1.0][q];
    const n = Math.floor(this.N * frac);
    this.geo.setDrawRange(0, n * (this.K - 1) * 6);
    this.material.uniforms.uWidth.value = 0.00024 / Math.sqrt(frac);
  }

  // headWorld: current head bone matrixWorld; headRestInv: inverse of rest head matrixWorld
  update(dt, headWorld, headRestInv, camera, renderer) {
    const M = this.mesh.matrix;
    M.multiplyMatrices(headWorld, headRestInv);
    this.mesh.matrixWorld.copy(M);
    const h = renderer.domElement.height;
    this.material.uniforms.uPx.value = h * 0.5;
    // light directions in view space
    const vm = camera.matrixWorldInverse;
    this.material.uniforms.uL1.value.set(-2.55, 4.05, 2.5).normalize().transformDirection(vm);
    this.material.uniforms.uL2.value.set(2.65, 3.05, 1.6).normalize().transformDirection(vm);
    if (!this.enabled) {
      if (this._wasOn) { this.d.fill(0); this.v.fill(0); this._writeGuides(); this._wasOn = false; }
      this.prevW = null; return;
    }
    this._wasOn = true;
    dt = Math.min(Math.max(dt, 1 / 240), 1 / 15);
    const dyn = this.meta.dyn;
    const w = 2 * Math.PI * dyn.frequency, z = dyn.damping;
    const e = M.elements;
    // rotation part R (column-major), we need R^T for world->rest
    const G = this.G, tip = this.gTip, d = this.d, v = this.v;
    const cur = this._cur || (this._cur = new Float32Array(G * 3));
    for (let g = 0; g < G; g++) {
      const x = tip[g * 3], y = tip[g * 3 + 1], zz = tip[g * 3 + 2];
      cur[g * 3] = e[0] * x + e[4] * y + e[8] * zz + e[12];
      cur[g * 3 + 1] = e[1] * x + e[5] * y + e[9] * zz + e[13];
      cur[g * 3 + 2] = e[2] * x + e[6] * y + e[10] * zz + e[14];
    }
    if (!this.prevW) { this.prevW = cur.slice(); this.prevW2 = cur.slice(); this.prevDt = dt; }
    // gravity in rest frame relative to rest orientation
    const gx = -9.81 * e[1], gy = -9.81 * e[5], gz = -9.81 * e[9]; // R^T * (0,-9.81,0)
    const grx = gx * dyn.gravity, gry = (gy + 9.81) * dyn.gravity, grz = gz * dyn.gravity;
    const sub = 2, h2 = dt / sub;
    const maxTip = dyn.maxTip;
    const pdt = this.prevDt;
    for (let g = 0; g < G; g++) {
      const i = g * 3;
      // world acceleration from three samples (variable dt)
      const v1x = (cur[i] - this.prevW[i]) / dt, v1y = (cur[i + 1] - this.prevW[i + 1]) / dt, v1z = (cur[i + 2] - this.prevW[i + 2]) / dt;
      const v0x = (this.prevW[i] - this.prevW2[i]) / pdt, v0y = (this.prevW[i + 1] - this.prevW2[i + 1]) / pdt, v0z = (this.prevW[i + 2] - this.prevW2[i + 2]) / pdt;
      let ax = (v1x - v0x) / dt, ay = (v1y - v0y) / dt, az = (v1z - v0z) / dt;
      const am = Math.hypot(ax, ay, az); if (am > 60) { const s = 60 / am; ax *= s; ay *= s; az *= s; }
      // to rest frame (R^T a)
      const arx = e[0] * ax + e[1] * ay + e[2] * az;
      const ary = e[4] * ax + e[5] * ay + e[6] * az;
      const arz = e[8] * ax + e[9] * ay + e[10] * az;
      for (let s = 0; s < sub; s++) {
        v[i] += (-w * w * d[i] - 2 * z * w * v[i] - dyn.inertia * arx + grx) * h2;
        v[i + 1] += (-w * w * d[i + 1] - 2 * z * w * v[i + 1] - dyn.inertia * ary + gry) * h2;
        v[i + 2] += (-w * w * d[i + 2] - 2 * z * w * v[i + 2] - dyn.inertia * arz + grz) * h2;
        d[i] += v[i] * h2; d[i + 1] += v[i + 1] * h2; d[i + 2] += v[i + 2] * h2;
      }
      const m = Math.hypot(d[i], d[i + 1], d[i + 2]);
      if (m > maxTip) { const s = maxTip / m; d[i] *= s; d[i + 1] *= s; d[i + 2] *= s; v[i] *= 0.5; v[i + 1] *= 0.5; v[i + 2] *= 0.5; }
    }
    this.prevW2.set(this.prevW); this.prevW.set(cur); this.prevDt = dt;
    this._writeGuides();
  }

  _writeGuides() {
    const gd = this.guideData, d = this.d;
    for (let g = 0; g < this.G; g++) { gd[g * 4] = d[g * 3]; gd[g * 4 + 1] = d[g * 3 + 1]; gd[g * 4 + 2] = d[g * 3 + 2]; }
    this.texGuide.needsUpdate = true;
  }
}
