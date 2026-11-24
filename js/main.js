import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { OTRig } from './rig.js';
import { Hair } from './hair.js';
import { Driver } from './drive.js';
import { MicLipSync } from './lipsync.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// ---------- persisted settings
const DEF = { jacket: 'ot', bg: 'street', frame: 'bust', mirror: true, hair: true, q: 1, glasses: 'on', pip: true, hands: true, arms: true };
let S = { ...DEF };
try { S = { ...DEF, ...JSON.parse(localStorage.getItem('jc-settings') || '{}') }; } catch {}
const save = () => { try { localStorage.setItem('jc-settings', JSON.stringify(S)); } catch {} };
const isMobile = matchMedia('(pointer:coarse)').matches;

// ---------- renderer / scene
const canvas = $('#stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, isMobile ? 1.5 : 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.toneMappingExposure = 0.82;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(26, 1, 0.05, 50);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.4;
// same layout as the .blend's softboxes (Softbox L = key, Softbox R = fill, Rim / Back fill behind)
const key = new THREE.DirectionalLight(0xfff5eb, 1.7); key.position.set(-2.55, 4.05, 2.5);
const fill = new THREE.DirectionalLight(0xdbe9ff, 0.8); fill.position.set(2.65, 3.05, 1.6);
const rim = new THREE.DirectionalLight(0xebf2ff, 0.9); rim.position.set(1.3, 3.0, -1.4);
const back = new THREE.DirectionalLight(0xf7f2ff, 0.6); back.position.set(-1.0, 2.0, -2.3);
scene.add(key, fill, rim, back, new THREE.HemisphereLight(0xfff4ea, 0x2a2030, 0.25));

// ---------- backgrounds
const BGS = [
  { id: 'street', name: 'ストリート', src: './assets/bg/street.jpg', thumb: './assets/bg/street_thumb.jpg' },
  { id: 'plaza', name: 'プラザ', src: './assets/bg/plaza.jpg', thumb: './assets/bg/plaza_thumb.jpg' },
  { id: 'studio', name: 'スタジオ', grad: ['#3b1a66', '#c8143c'] },
  { id: 'sunny', name: 'ひまわり', grad: ['#f6c21a', '#f08a3c'] },
  { id: 'green', name: 'グリーンバック', color: '#00b140' },
  { id: 'blue', name: 'ブルーバック', color: '#0047bb' },
];
const texLoader = new THREE.TextureLoader();
let bgTex = null;
function gradTex(a, b) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 1024;
  const g = c.getContext('2d');
  const lg = g.createLinearGradient(0, 0, 0, 1024); lg.addColorStop(0, a); lg.addColorStop(1, b);
  g.fillStyle = lg; g.fillRect(0, 0, 1024, 1024);
  const rg = g.createRadialGradient(512, 360, 40, 512, 420, 620);
  rg.addColorStop(0, 'rgba(255,255,255,.28)'); rg.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = rg; g.fillRect(0, 0, 1024, 1024);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function setBgTexture(t) {
  if (bgTex && bgTex !== t && bgTex.userData.dispose) bgTex.dispose();
  bgTex = t; scene.background = t; fitBg();
}
function fitBg() {
  const t = scene.background;
  if (!t || !t.isTexture || !t.image) return;
  const iw = t.image.width || t.image.videoWidth, ih = t.image.height || t.image.videoHeight;
  const ia = iw / ih, ca = canvas.clientWidth / canvas.clientHeight;
  if (ca > ia) { t.repeat.set(1, ia / ca); t.offset.set(0, (1 - ia / ca) / 2); }
  else { t.repeat.set(ca / ia, 1); t.offset.set((1 - ca / ia) / 2, 0); }
}
function applyBg(id) {
  S.bg = id; save();
  $$('.bg').forEach(b => b.classList.toggle('on', b.dataset.bg === id));
  if (id === 'custom') {
    const url = (() => { try { return localStorage.getItem('jc-bg'); } catch { return null; } })();
    if (url) return texLoader.load(url, t => { t.colorSpace = THREE.SRGBColorSpace; t.userData.dispose = true; setBgTexture(t); });
    id = 'street';
  }
  const b = BGS.find(x => x.id === id) || BGS[0];
  if (b.color) { bgTex = null; scene.background = new THREE.Color(b.color); }
  else if (b.grad) setBgTexture(gradTex(...b.grad));
  else texLoader.load(b.src, t => { t.colorSpace = THREE.SRGBColorSpace; setBgTexture(t); });
}
function buildBgGrid() {
  const grid = $('#bgGrid');
  let custom = null; try { custom = localStorage.getItem('jc-bg'); } catch {}
  const items = (custom ? [{ id: 'custom', name: 'あなたの写真', thumb: custom }] : []).concat(BGS);
  for (const b of items) {
    const el = document.createElement('button');
    el.className = 'bg'; el.dataset.bg = b.id; el.textContent = b.name;
    if (b.thumb) el.style.backgroundImage = `url("${b.thumb}")`;
    else if (b.grad) el.style.background = `linear-gradient(${b.grad[0]},${b.grad[1]})`;
    else el.style.background = b.color;
    el.onclick = () => applyBg(b.id);
    grid.appendChild(el);
  }
}
$('#bgFile').addEventListener('change', async e => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const bmp = await createImageBitmap(f, { imageOrientation: 'from-image' });
    const s = Math.min(1, 2048 / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas'); c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    let url = c.toDataURL('image/jpeg', 0.86);
    try { localStorage.setItem('jc-bg', url); } catch {
      // too big for storage: keep a smaller copy so it survives reloads
      const c2 = document.createElement('canvas'); const s2 = 1280 / Math.max(c.width, c.height);
      c2.width = Math.round(c.width * s2); c2.height = Math.round(c.height * s2);
      c2.getContext('2d').drawImage(c, 0, 0, c2.width, c2.height);
      try { localStorage.setItem('jc-bg', c2.toDataURL('image/jpeg', 0.8)); } catch {}
    }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.userData.dispose = true;
    setBgTexture(t); S.bg = 'custom'; save();
    $('#bgGrid').querySelectorAll('.bg:not(.up)').forEach(n => n.remove());
    buildBgGrid();
    $$('.bg').forEach(b => b.classList.toggle('on', b.dataset.bg === 'custom'));
    toast('背景を変更しました');
  } catch (err) { console.error(err); toast('この画像は読み込めませんでした'); }
  e.target.value = '';
});
$('#bgUpload').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') $('#bgFile').click(); });

// ---------- UI helpers
let toastT;
function toast(m) { const t = $('#toast'); t.textContent = m; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2200); }
const dock = $('#dock');
$$('.tab').forEach(t => t.onclick = () => {
  const same = t.classList.contains('on') && dock.classList.contains('open');
  $$('.tab').forEach(x => x.classList.toggle('on', x === t));
  $$('.pane').forEach(p => p.classList.toggle('on', p.dataset.pane === t.dataset.tab));
  dock.classList.toggle('open', !same);
});
const setOn = (el, on) => { el.classList.toggle('on', !!on); el.setAttribute('aria-pressed', on ? 'true' : 'false'); };

// ---------- avatar
let rig, hair, driver, avatar, headRestInv, coverU;
const parts = { ot: [], mb: [], glasses: [] };

function setupMaterials(root) {
  coverU = { value: new THREE.Vector3(1, 0, 1) };
  root.traverse(o => {
    if (!o.isMesh) return;
    o.frustumCulled = false;
    const m = o.material; const n = m.name || '';
    if (o.geometry.attributes._cover) {
      m.onBeforeCompile = sh => {
        sh.uniforms.uCover = coverU;
        sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute vec3 _cover;\nvarying vec3 vCover;')
          .replace('#include <begin_vertex>', '#include <begin_vertex>\nvCover = _cover;');
        sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform vec3 uCover;\nvarying vec3 vCover;')
          .replace('void main() {', 'void main() {\nif (dot(vCover, uCover) > 0.5) discard;');
      };
      m.customProgramCacheKey = () => 'cover';
    }
    if (n.startsWith('Std_Skin') || n === 'Std_Nails') { m.roughness = n === 'Std_Skin_Head' ? 0.52 : 0.6; m.envMapIntensity = 0.7; }
    if (n === 'Std_Eyelash') { m.alphaTest = 0.45; m.transparent = false; m.side = THREE.DoubleSide; }
    if (n.startsWith('Std_Eye_')) { m.roughness = 0.25; }
    if (n === 'cornea') { m.transparent = true; m.opacity = 0.1; m.roughness = 0.02; m.depthWrite = false; m.envMapIntensity = 2; o.renderOrder = 3; }
    if (n === 'lenses') { m.transparent = true; m.opacity = 0.86; m.roughness = 0.04; m.metalness = 0.5; m.color.set(0x0d0f12); m.depthWrite = false; o.renderOrder = 3; }
    if (n === 'shades') { m.roughness = 0.32; }
    const isWB = o.name.startsWith('Windbreaker') || (o.parent && o.parent.name.startsWith('Windbreaker'));
    const isMB = o.name.startsWith('JACKET') || (o.parent && o.parent.name.startsWith('JACKET'));
    if (isWB || isMB || n === 'pant') m.side = THREE.DoubleSide;
    if (isWB && /Shell|Collar|Facing|Cuffs/.test(n)) m.roughness = Math.max(m.roughness, 0.55);
    if (isWB) parts.ot.push(o); else if (isMB) parts.mb.push(o);
    if (o.name.startsWith('OT_Sunglasses') || (o.parent && o.parent.name.startsWith('OT_Sunglasses'))) parts.glasses.push(o);
  });
}

function applyJacket(j) {
  S.jacket = j; save();
  parts.ot.forEach(o => o.visible = j === 'ot');
  parts.mb.forEach(o => o.visible = j === 'mb');
  coverU && coverU.value.set(j === 'ot' ? 1 : 0, j === 'mb' ? 1 : 0, 1);
  if (rig) rig.props.turbo_jacket = j === 'ot' ? 1 : 0;
  $$('[data-jacket]').forEach(b => setOn(b, b.dataset.jacket === j));
}
function applyGlasses(g) {
  S.glasses = g; save();
  parts.glasses.forEach(o => o.visible = g !== 'off');
  if (rig) { rig.props.sunglasses = g === 'off' ? 0 : 1; rig.props.sunglasses_low = g === 'low' ? 1 : 0; }
  $$('[data-glasses]').forEach(b => setOn(b, b.dataset.glasses === g));
}

// ---------- camera framing
const FR = { face: { h: 0.36, y: 0.02, bone: 'CC_Base_Head' }, bust: { h: 0.95, y: -0.2, bone: 'CC_Base_Head' }, full: { h: 2.05, y: 0, bone: null } };
const camTarget = new THREE.Vector3(0, 1.4, 0); let camInit = false, camDist = 3;
function frameCamera(dt) {
  const f = FR[S.frame];
  const W = canvas.clientWidth, H = canvas.clientHeight, aspect = W / H;
  const tgt = new THREE.Vector3();
  if (S.frame === 'face' && rig) { rig.bones[f.bone].getWorldPosition(tgt); tgt.y += f.y + 0.06; tgt.x *= 0.6; tgt.z = 0; }
  else if (f.bone) tgt.set(0, (rig ? rig.restHeadY : 1.58) + f.y + 0.06, 0);
  else tgt.set(0, 0.93, 0);
  const vfov = THREE.MathUtils.degToRad(camera.fov), th = Math.tan(vfov / 2);
  // keep the avatar in the part of the screen the dock doesn't cover
  const dockRect = dock.getBoundingClientRect().height;
  document.documentElement.style.setProperty('--dockH', dockRect + 'px');
  const dockH = Math.min(dockRect + 12, H * 0.6);
  const freeH = Math.max(H - dockH, H * 0.4);
  const needW = S.frame === 'full' ? 0.9 : S.frame === 'bust' ? 0.56 : 0.3;
  // visible height at the target plane so that f.h fits into freeH and needW fits the width
  const visH = Math.max(f.h * H / freeH, needW / aspect);
  const dist = visH / 2 / th;
  // shift so the subject is centred in the free area (above the dock)
  tgt.y -= (dockH / 2) / H * visH;
  const k = camInit ? 1 - Math.exp(-6 * dt) : 1; camInit = true;
  camTarget.lerp(tgt, k);
  camDist += (dist - camDist) * k;
  camera.position.set(camTarget.x, camTarget.y + (S.frame === 'full' ? 0.05 : 0.02), camDist);
  camera.lookAt(camTarget);
}

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h; camera.updateProjectionMatrix();
  fitBg();
}
addEventListener('resize', resize);

// ---------- loading
async function loadAll() {
  const prog = $('#prog'), msg = $('#msg');
  const progress = { glb: 0, hair: 0 };
  const upd = () => { prog.style.width = `${Math.round((progress.glb * 0.8 + progress.hair * 0.2) * 100)}%`; };
  const loader = new GLTFLoader(); loader.setMeshoptDecoder(MeshoptDecoder);
  const [def, hairMeta, hairBuf, gltf] = await Promise.all([
    fetch('./assets/rig.json').then(r => r.json()),
    fetch('./assets/hair.json').then(r => r.json()),
    fetch('./assets/hair.bin').then(r => { progress.hair = 1; upd(); return r.arrayBuffer(); }),
    loader.loadAsync('./assets/avatar.glb', e => { if (e.total) { progress.glb = e.loaded / e.total; upd(); } }),
  ]);
  progress.glb = 1; upd();
  avatar = gltf.scene;
  scene.add(avatar);
  avatar.updateMatrixWorld(true);
  setupMaterials(avatar);
  rig = new OTRig(avatar, def);
  rig.restHeadY = new THREE.Vector3().setFromMatrixPosition(rig.bones.CC_Base_Head.matrixWorld).y;
  headRestInv = rig.bones.CC_Base_Head.matrixWorld.clone().invert();
  hair = new Hair(hairMeta, hairBuf, renderer);
  scene.add(hair.mesh);
  driver = new Driver(rig);
  window.__app = { rig, hair, driver, S, scene, camera, renderer, THREE };
  msg.textContent = '準備できました';
}

// ---------- tracking
let tracker = null, trackOn = false;
async function startCamera() {
  const msg = $('#msg');
  $('#goCam').disabled = true; $('#goNoCam').disabled = true;
  try {
    const { Tracker } = await import('./tracking.js');
    tracker = new Tracker();
    window.__tracker = tracker;
    tracker.useHands = S.hands; tracker.usePose = S.arms;
    await tracker.start(t => { msg.textContent = t; });
    trackOn = true;
    $('#pip').appendChild(tracker.video);
    applyPip();
    $('#start').remove();
    $('#trackDot').classList.add('on'); $('#trackTxt').textContent = 'トラッキング中';
    toast('正面を向いて「設定 › 今の顔を正面にする」を押すと精度が上がります');
  } catch (e) {
    console.error(e);
    msg.textContent = e && e.name === 'NotAllowedError'
      ? 'カメラの使用が許可されませんでした。ブラウザの設定でカメラを許可してください。'
      : 'カメラを起動できませんでした（' + (e && e.message || e) + '）';
    $('#goCam').disabled = false; $('#goNoCam').disabled = false;
  }
}
function applyPip() { const p = $('#pip'); p.style.display = trackOn && S.pip ? 'block' : 'none'; p.classList.toggle('mirror', S.mirror); }

// ---------- expressions, vowels, hand poses, sliders
const EX = [['ex_smile', '笑顔'], ['ex_laugh', '大笑い'], ['ex_angry', '怒り'], ['ex_sad', '悲しみ'], ['ex_surprise', '驚き'], ['ex_disgust', 'うえっ'], ['ex_fear', '怖がる'], ['ex_smirk', 'ニヤリ'], ['ex_pout', '口とがらせ'], ['ex_puff', 'ほっぺぷく'], ['ex_wink_L', 'ウインク左'], ['ex_wink_R', 'ウインク右'], ['ex_tongue', '舌ベー']];
const exTarget = {};
function buildFaceUI() {
  const row = $('#exRow');
  for (const [k, label] of EX) {
    const b = document.createElement('button'); b.className = 'btn'; b.textContent = label; b.dataset.ex = k;
    b.onclick = () => { exTarget[k] = exTarget[k] ? 0 : 1; setOn(b, exTarget[k]); };
    row.appendChild(b);
  }
  const vr = $('#vowelRow');
  for (const [k, label] of [['ls_a', 'あ'], ['ls_i', 'い'], ['ls_u', 'う'], ['ls_e', 'え'], ['ls_o', 'お'], ['ls_m', 'ん']]) {
    const b = document.createElement('button'); b.className = 'btn'; b.textContent = label; b.setAttribute('aria-label', `口の形 ${label}（押している間）`);
    const on = e => { e.preventDefault(); manualVowel[k] = 1; b.classList.add('on'); };
    const off = () => { manualVowel[k] = 0; b.classList.remove('on'); };
    b.addEventListener('pointerdown', on); b.addEventListener('pointerup', off); b.addEventListener('pointerleave', off); b.addEventListener('pointercancel', off);
    vr.appendChild(b);
  }
}
const manualVowel = {};
const POSES = {
  open: { thumb: 0, index: 0, middle: 0, ring: 0, pinky: 0, spread: 0.6, fist: 0, relax: 0 },
  relax: { thumb: 0, index: 0, middle: 0, ring: 0, pinky: 0, spread: 0, fist: 0, relax: 1 },
  fist: { thumb: 0.2, index: 0, middle: 0, ring: 0, pinky: 0, spread: 0, fist: 1, relax: 0 },
  peace: { thumb: 0.9, index: 0, middle: 0, ring: 1, pinky: 1, spread: 0.7, fist: 0, relax: 0 },
  point: { thumb: 0.8, index: 0, middle: 1, ring: 1, pinky: 1, spread: 0, fist: 0, relax: 0 },
  good: { thumb: 0, index: 1, middle: 1, ring: 1, pinky: 1, spread: 0, fist: 0, relax: 0 },
};
const handManual = { L: { ...POSES.relax }, R: { ...POSES.relax } };
function buildHandUI() {
  const row = $('#poseRow');
  for (const [k, label] of [['relax', '自然'], ['open', 'パー'], ['fist', 'グー'], ['peace', 'ピース'], ['point', '指さし'], ['good', 'いいね']]) {
    const b = document.createElement('button'); b.className = 'btn'; b.textContent = label;
    b.onclick = () => { handManual.L = { ...POSES[k] }; handManual.R = { ...POSES[k] }; syncFingerSliders(); };
    row.appendChild(b);
  }
  const cols = $('#fingerCols');
  for (const s of ['L', 'R']) {
    const col = document.createElement('div');
    col.innerHTML = `<h3>${s === 'L' ? '左手' : '右手'}</h3>`;
    for (const [f, label] of [['thumb', '親指'], ['index', '人差し指'], ['middle', '中指'], ['ring', '薬指'], ['pinky', '小指'], ['spread', '指を広げる'], ['fist', 'グー']]) {
      const id = `fs_${s}_${f}`;
      const min = f === 'spread' ? -1 : 0;
      col.insertAdjacentHTML('beforeend', `<label class="sl" for="${id}"><span>${label}</span><input type="range" id="${id}" min="${min}" max="1" step="0.01"><output></output></label>`);
    }
    cols.appendChild(col);
  }
  for (const inp of cols.querySelectorAll('input')) {
    const [, s, f] = inp.id.split('_');
    inp.oninput = () => { handManual[s][f] = +inp.value; handManual[s].relax = 0; inp.nextElementSibling.textContent = (+inp.value).toFixed(2); };
  }
  syncFingerSliders();
}
function syncFingerSliders() {
  for (const s of ['L', 'R']) for (const f of ['thumb', 'index', 'middle', 'ring', 'pinky', 'spread', 'fist']) {
    const inp = document.getElementById(`fs_${s}_${f}`); if (!inp) continue;
    inp.value = handManual[s][f]; inp.nextElementSibling.textContent = (+handManual[s][f]).toFixed(2);
  }
}
function buildRigSliders(def) {
  const box = $('#rigSliders');
  for (const k of ['neck_correctives', 'eyelid_follow', 'shoulder_relax', 'auto_twist', 'eye_pupil']) {
    const p = def.props[k];
    box.insertAdjacentHTML('beforeend', `<label class="sl" for="rs_${k}"><span>${p.label.replace(/（.*?）/g, '')}</span><input type="range" id="rs_${k}" min="${p.min}" max="${p.max}" step="0.01" value="${p.default}"><output>${p.default.toFixed(2)}</output></label>`);
    const inp = document.getElementById('rs_' + k);
    inp.oninput = () => { rig.props[k] = +inp.value; inp.nextElementSibling.textContent = (+inp.value).toFixed(2); };
  }
}

// ---------- mic
const mic = new MicLipSync();
$('#micBtn').onclick = async () => {
  const b = $('#micBtn');
  if (mic.on) { mic.stop(); setOn(b, false); return; }
  try { await mic.start(); setOn(b, true); toast('マイクの声で口が動きます'); }
  catch (e) { console.error(e); toast('マイクを使えませんでした'); }
};

// ---------- recording & screenshot
let rec = null, recStart = 0;
function download(blob, name) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
}
$('#shotBtn').onclick = () => {
  renderFrame(0);
  canvas.toBlob(b => { if (b) { download(b, `jacketcam-${Date.now()}.png`); toast('写真を保存しました'); } }, 'image/png');
};
$('#recBtn').onclick = () => {
  if (rec) { rec.stop(); return; }
  if (!window.MediaRecorder || !canvas.captureStream) { toast('このブラウザは録画に対応していません'); return; }
  const stream = canvas.captureStream(30);
  if (mic.on && mic.stream) mic.stream.getAudioTracks().forEach(t => stream.addTrack(t));
  const types = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'];
  const mimeType = types.find(t => MediaRecorder.isTypeSupported(t)) || '';
  const chunks = [];
  rec = new MediaRecorder(stream, mimeType ? { mimeType, videoBitsPerSecond: 6e6 } : undefined);
  rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  rec.onstop = () => {
    const type = rec.mimeType || mimeType || 'video/webm';
    download(new Blob(chunks, { type }), `jacketcam-${Date.now()}.${type.includes('mp4') ? 'mp4' : 'webm'}`);
    rec = null; $('#recBtn').classList.remove('live'); $('#recChip').hidden = true; toast('動画を保存しました');
  };
  rec.start(1000); recStart = performance.now();
  $('#recBtn').classList.add('live'); $('#recChip').hidden = false;
};

// ---------- settings wiring
function wireSettings() {
  $$('[data-jacket]').forEach(b => b.onclick = () => applyJacket(b.dataset.jacket));
  $$('[data-glasses]').forEach(b => b.onclick = () => applyGlasses(b.dataset.glasses));
  $$('[data-frame]').forEach(b => b.onclick = () => { S.frame = b.dataset.frame; save(); $$('[data-frame]').forEach(x => setOn(x, x === b)); });
  $$('[data-frame]').forEach(x => setOn(x, x.dataset.frame === S.frame));
  $$('[data-q]').forEach(b => b.onclick = () => { S.q = +b.dataset.q; save(); hair.setQuality(S.q); $$('[data-q]').forEach(x => setOn(x, x === b)); });
  $$('[data-q]').forEach(x => setOn(x, +x.dataset.q === S.q));
  hair.setQuality(S.q);
  const tog = (id, key, fn) => { const b = $(id); setOn(b, S[key]); b.onclick = () => { S[key] = !S[key]; save(); setOn(b, S[key]); fn && fn(); }; };
  tog('#mirrorBtn', 'mirror', () => { driver.mirror = S.mirror; applyPip(); });
  tog('#hairBtn', 'hair', () => { hair.enabled = S.hair; });
  tog('#pipBtn', 'pip', applyPip);
  tog('#handsBtn', 'hands', async () => { if (tracker) { tracker.useHands = S.hands; await tracker.ensureBody(); } });
  tog('#armsBtn', 'arms', async () => { if (tracker) { tracker.usePose = S.arms; await tracker.ensureBody(); } });
  $('#calBtn').onclick = () => { if (!trackOn) return toast('カメラをオンにすると使えます'); driver.calibrate(); toast('今の顔の向きを正面にしました'); };
  driver.mirror = S.mirror; hair.enabled = S.hair;
}

// ---------- main loop
const clock = new THREE.Clock();
let fpsAcc = 0, fpsN = 0;
function renderFrame(dt) {
  const now = performance.now();
  let res = null;
  if (trackOn && tracker) { tracker.step(now); res = tracker.last; if (now - res.t > 800) res = null; }
  driver.update(res, dt, now);
  const P = rig.props;
  // expression presets fade in/out
  for (const [k] of EX) P[k] = P[k] + ((exTarget[k] || 0) - P[k]) * (1 - Math.exp(-10 * dt));
  // lip sync: mic + hold buttons
  const m = mic.update(dt);
  for (const v of ['a', 'i', 'u', 'e', 'o']) {
    const target = Math.max(m[v] * 1.6, manualVowel['ls_' + v] || 0);
    P['ls_' + v] = P['ls_' + v] + (clamp(target, 0, 1) - P['ls_' + v]) * (1 - Math.exp(-20 * dt));
  }
  P.ls_m = P.ls_m + ((manualVowel.ls_m || 0) - P.ls_m) * (1 - Math.exp(-20 * dt));
  $('#micMeter').style.width = `${Math.round(m.level * 100)}%`;
  // manual hands when the camera doesn't see them
  for (const s of ['L', 'R']) {
    const w = 1 - (driver.handW[s] || 0);
    if (w > 0.02) for (const f of ['thumb', 'index', 'middle', 'ring', 'pinky', 'spread', 'fist', 'relax']) {
      const key = `hand_${s}_${f}`; const cur = P[key];
      P[key] = cur + (handManual[s][f] - cur) * w * (1 - Math.exp(-12 * dt));
    }
  }
  rig.update();
  avatar.updateMatrixWorld(true);
  hair.update(dt, rig.bones.CC_Base_Head.matrixWorld, headRestInv, camera, renderer);
  frameCamera(dt);
  renderer.render(scene, camera);
  if (rec) { const s = Math.floor((now - recStart) / 1000); $('#recTime').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; }
}
function loop() {
  const dt = Math.min(clock.getDelta(), 0.1);
  renderFrame(dt);
  fpsAcc += dt; fpsN++;
  if (fpsAcc > 1) { window.__fps = fpsN / fpsAcc; fpsAcc = 0; fpsN = 0; }
  requestAnimationFrame(loop);
}

// ---------- boot
(async () => {
  resize();
  buildBgGrid();
  applyBg(S.bg);
  try {
    await loadAll();
  } catch (e) {
    console.error(e); $('#msg').textContent = 'アバターを読み込めませんでした。ページを再読み込みしてください。'; return;
  }
  buildFaceUI(); buildHandUI(); buildRigSliders(rig.def);
  applyJacket(S.jacket); applyGlasses(S.glasses); wireSettings();
  resize();
  loop();
  $('#goCam').disabled = false; $('#goNoCam').disabled = false;
  $('#goCam').onclick = startCamera;
  $('#goNoCam').onclick = () => { $('#start').remove(); dock.classList.add('open'); };
  if (!navigator.mediaDevices?.getUserMedia) { $('#goCam').disabled = true; $('#msg').textContent = 'このブラウザではカメラを使えません（https で開いてください）'; }
})();
