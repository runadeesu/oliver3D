// Microphone lip sync for the rig's Japanese visemes (ls_a, ls_i, ls_u, ls_e, ls_o).
// Rough formant estimate (F1/F2 peaks of a smoothed spectrum) -> soft vowel weights.
const VOWELS = { a: [800, 1250], i: [300, 2300], u: [350, 1350], e: [500, 1900], o: [500, 850] };

export class MicLipSync {
  constructor() { this.on = false; this.out = { a: 0, i: 0, u: 0, e: 0, o: 0, level: 0 }; this.floor = 0.008; }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false });
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new Ctx();
    await this.ctx.resume();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.an = this.ctx.createAnalyser(); this.an.fftSize = 2048; this.an.smoothingTimeConstant = 0.35;
    src.connect(this.an);
    this.freq = new Float32Array(this.an.frequencyBinCount);
    this.time = new Float32Array(this.an.fftSize);
    this.on = true;
  }

  stop() {
    this.on = false;
    this.stream?.getTracks().forEach(t => t.stop());
    this.ctx?.close();
    for (const k in this.out) this.out[k] = 0;
  }

  update(dt) {
    if (!this.on) return this.out;
    this.an.getFloatTimeDomainData(this.time);
    let rms = 0; for (const v of this.time) rms += v * v; rms = Math.sqrt(rms / this.time.length);
    // adaptive noise floor
    this.floor = Math.min(Math.max(this.floor * 0.995 + rms * 0.005, 0.004), 0.05);
    const level = Math.min(1, Math.max(0, (rms - this.floor * 1.6) / 0.08));
    this.an.getFloatFrequencyData(this.freq);
    const sr = this.ctx.sampleRate, bw = sr / this.an.fftSize;
    const mag = i => Math.pow(10, this.freq[i] / 20);
    const smooth = new Float32Array(160);  // 25 Hz bins up to 4 kHz
    for (let k = 0; k < smooth.length; k++) {
      const f = k * 25; let s = 0, n = 0;
      for (let j = Math.floor((f - 75) / bw); j <= Math.ceil((f + 75) / bw); j++) if (j > 0 && j < this.freq.length) { s += mag(j); n++; }
      smooth[k] = n ? s / n : 0;
    }
    const peak = (lo, hi) => { let bi = lo / 25, bv = -1; for (let k = lo / 25; k <= hi / 25; k++) if (smooth[k] > bv) { bv = smooth[k]; bi = k; } return bi * 25; };
    const F1 = peak(250, 950);
    const F2 = peak(Math.max(800, F1 + 300), 2800);
    const w = {}; let sum = 0;
    for (const [v, [f1, f2]] of Object.entries(VOWELS)) {
      const d = ((F1 - f1) / 220) ** 2 + ((F2 - f2) / 420) ** 2;
      w[v] = Math.exp(-d); sum += w[v];
    }
    const a = 1 - Math.exp(-18 * dt);
    for (const v of Object.keys(VOWELS)) {
      const target = sum > 0 ? (w[v] / sum) * level : 0;
      this.out[v] += (target - this.out[v]) * a;
    }
    this.out.level += (level - this.out.level) * a;
    return this.out;
  }
}
