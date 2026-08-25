/**
 * VORIS HUD — ULTRON-style sphere interface.
 *
 * Implements layers L0-L4 of the build spec (steps 1-7): void + starfield,
 * particle shell with limb brightening, great-circle rings, bloom, and the
 * centre readout. HUD chrome (side panels, rails), audio reactivity and the
 * VORIS state feed are NOT wired yet — state is driven by fake events so the
 * visual can be verified on its own. See setState() and window.HUD.
 */
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const stage = document.getElementById('stage');
const titleEl = document.getElementById('hudTitle');
const subEl = document.getElementById('hudSub');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------------------------------------------------------------- L0: void

const CAMERA_Z = 5.2;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 100);
camera.position.z = CAMERA_Z;

// No `antialias`: the scene is rendered into the composer's own render target,
// so MSAA on the default framebuffer would only ever apply to OutputPass's
// fullscreen triangle — it costs an MSAA drawing buffer and antialiases
// nothing. Bloom softens the ring edges instead.
const renderer = new THREE.WebGLRenderer({ powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
// EffectComposer renders into a linear half-float target and OutputPass does the
// final sRGB encode, so the clear colour has to be handed over already in linear
// space. Passing the sRGB hex straight through comes back several stops light
// (#03060f arrives on screen as roughly #1e2645) and washes out the whole HUD.
renderer.setClearColor(new THREE.Color(0x03060f).convertSRGBToLinear(), 1);
stage.appendChild(renderer.domElement);

const starGeo = new THREE.BufferGeometry();
const starPos = new Float32Array(160 * 3);
for (let i = 0; i < 160; i++) {
  starPos[i * 3] = (Math.random() - 0.5) * 30;
  starPos[i * 3 + 1] = (Math.random() - 0.5) * 18;
  starPos[i * 3 + 2] = -8 - Math.random() * 12;
}
starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({
  color: 0x5c8fb8, size: 0.035, sizeAttenuation: true,
  transparent: true, opacity: 0.55
})));

// ------------------------------------------------------- L1: particle shell

const COUNT = 4000;

/**
 * Extra radial offset applied to each particle when the shell is built, on top
 * of the Fibonacci position and the uniform jitter.
 *
 * The reference sphere is not pure noise — some particles form arc-like wave
 * patterns. Returning 0 gives an evenly dusted shell; returning a function of
 * latitude and/or angle carves visible structure into it.
 *
 * @param {number} y      latitude, +1 at the north pole down to -1 at the south
 * @param {number} theta  accumulated golden-angle rotation for this particle
 * @param {number} index  particle index, 0..COUNT-1
 * @returns {number} radial offset in sphere radii; keep within about +/-0.05
 */
function waveDisplacement(y, theta, index) {
  // TODO: shape the shell here.
  return 0;
}

function buildShellGeometry(count) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const rnd = new Float32Array(count);
  const golden = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const t = golden * i;
    // slight radial jitter so it reads as a cloud, not a shrink-wrap
    const rad = 1 + (Math.random() - 0.5) * 0.06 + waveDisplacement(y, t, i);
    pos[i * 3] = Math.cos(t) * r * rad;
    pos[i * 3 + 1] = y * rad;
    pos[i * 3 + 2] = Math.sin(t) * r * rad;
    rnd[i] = Math.random();
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('aRnd', new THREE.BufferAttribute(rnd, 1));
  return geo;
}

const SHELL_VERT = `
attribute float aRnd;
uniform float uTime, uLevel, uSize, uPixelRatio, uRefDist;
varying float vEdge;

void main() {
  vec3 p = position;

  // breathing + per-particle shimmer
  p *= 1.0 + uLevel * 0.10 + sin(uTime * 2.0 + aRnd * 40.0) * 0.012;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);

  // limb brightening: normal perpendicular to view = silhouette edge
  vec3 n = normalize(mat3(modelViewMatrix) * normalize(position));
  vEdge = 1.0 - abs(dot(n, vec3(0.0, 0.0, 1.0)));

  // uSize is CSS pixels at the camera's rest distance, so the dust stays the
  // same apparent size on any display instead of scaling with canvas height.
  gl_PointSize = uSize * uPixelRatio * (1.0 + vEdge * 1.6) * (1.0 + uLevel * 0.5) * (uRefDist / -mv.z);
  gl_Position = projectionMatrix * mv;
}
`;

const SHELL_FRAG = `
uniform vec3 uCore, uDeep;
uniform float uLevel;
varying float vEdge;

void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  float soft = smoothstep(0.5, 0.05, d);

  vec3 col = mix(uDeep, uCore, vEdge);
  float a = (0.10 + vEdge * 0.72) * soft * (0.5 + uLevel * 0.5);
  gl_FragColor = vec4(col, a);
}
`;

const shellMat = new THREE.ShaderMaterial({
  vertexShader: SHELL_VERT,
  fragmentShader: SHELL_FRAG,
  transparent: true,
  depthWrite: false,
  blending: THREE.AdditiveBlending,
  uniforms: {
    uTime: { value: 0 },
    uLevel: { value: 0 },
    uSize: { value: 2.4 },
    uPixelRatio: { value: renderer.getPixelRatio() },
    uRefDist: { value: CAMERA_Z },
    uCore: { value: new THREE.Color(0x7fdfff) },
    uDeep: { value: new THREE.Color(0x0a5c8f) }
  }
});

const shell = new THREE.Points(buildShellGeometry(COUNT), shellMat);
scene.add(shell);

// --------------------------------------------------------------- L2: rings

function makeRing(radius, tubeRadius, color) {
  const geo = new THREE.TorusGeometry(radius, tubeRadius, 12, 220);
  const mat = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.95,
    blending: THREE.AdditiveBlending, depthWrite: false
  });
  return new THREE.Mesh(geo, mat);
}

const ringGroup = new THREE.Group();
const ringA = makeRing(1.06, 0.006, 0x00c8ff);
const ringB = makeRing(1.06, 0.005, 0x00c8ff);
const ringC = makeRing(1.10, 0.003, 0x0090cc);
const rings = [ringA, ringB, ringC];

ringB.rotation.y = Math.PI / 2;
ringC.rotation.x = Math.PI / 2;
ringGroup.add(ringA, ringB, ringC);
ringGroup.rotation.z = 0.34;  // the ~20 degree tilt off-axis
scene.add(ringGroup);

// Non-harmonic ratios: 0.62 and 0.41 keep the intersection drifting instead of
// visibly looping every few seconds the way 0.5 / 0.25 would.
function animateRings(dt, spin) {
  ringA.rotation.y += dt * spin * 1.00;
  ringB.rotation.x += dt * spin * 0.62;
  ringC.rotation.z += dt * spin * 0.41;
}

// ---------------------------------------------------------------- L3: bloom

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));

const bloom = new UnrealBloomPass(
  new THREE.Vector2(innerWidth / 2, innerHeight / 2),  // half-res, per the perf budget
  1.15,   // strength
  0.45,   // radius
  0.18    // threshold — must sit under the ring brightness or the rings stay flat
);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// -------------------------------------------------------- states + readout

const STATES = {
  locked:    { title: 'SYSTEM LOCKED', sub: 'awaiting activation',
               core: 0x7fdfff, deep: 0x0a5c8f, ring: 0x00c8ff, spin: 0.12, bloom: 1.00 },
  listening: { title: 'LISTENING', sub: 'go ahead',
               core: 0xa5f3fc, deep: 0x0e7490, ring: 0x22d3ee, spin: 0.30, bloom: 1.15 },
  thinking:  { title: 'PROCESSING', sub: 'routing through tools',
               core: 0xffd27f, deep: 0xb45309, ring: 0xff8c1a, spin: 0.75, bloom: 1.30 },
  speaking:  { title: 'RESPONDING', sub: 'speaking',
               core: 0xffe9b8, deep: 0xc2620a, ring: 0xffa033, spin: 0.38, bloom: 1.45 }
};

let cur = STATES.locked;
const live = {
  core: new THREE.Color(cur.core),
  deep: new THREE.Color(cur.deep),
  ring: new THREE.Color(cur.ring),
  spin: cur.spin,
  bloom: cur.bloom
};
// Scratch colours, reused each frame so easeState() allocates nothing.
const target = { core: new THREE.Color(), deep: new THREE.Color(), ring: new THREE.Color() };

function setState(name) {
  if (!(name in STATES)) return;
  cur = STATES[name];
  document.body.dataset.state = name;
  titleEl.textContent = cur.title;
  subEl.textContent = cur.sub;
}

function easeState(dt) {
  const k = Math.min(dt * 1.6, 1);  // ~1s crossfade; instant swaps look like a bug
  live.core.lerp(target.core.setHex(cur.core), k);
  live.deep.lerp(target.deep.setHex(cur.deep), k);
  live.ring.lerp(target.ring.setHex(cur.ring), k);
  live.spin += (cur.spin - live.spin) * k;
  live.bloom += (cur.bloom - live.bloom) * k;

  shellMat.uniforms.uCore.value.copy(live.core);
  shellMat.uniforms.uDeep.value.copy(live.deep);
  for (const r of rings) r.material.color.copy(live.ring);
  bloom.strength = live.bloom + level * 0.5;
}

// ------------------------------------------------------------------- level

// Placeholder for step 10. Real audio reactivity replaces this with an
// AnalyserNode reading the mic (listening) or the TTS element (speaking);
// until then a slow breath keeps the shell from looking dead.
let level = 0;
function idleBreath(t) {
  level = 0.18 + Math.sin(t * 0.9) * 0.10 + Math.sin(t * 2.3) * 0.04;
}

// -------------------------------------------------------------------- loop

const clock = new THREE.Clock();

function frame() {
  const dt = Math.min(clock.getDelta(), 0.1);
  const t = clock.elapsedTime;

  idleBreath(t);
  easeState(dt);

  shellMat.uniforms.uTime.value = t;
  shellMat.uniforms.uLevel.value = level;

  animateRings(dt, reducedMotion ? live.spin * 0.25 : live.spin);
  shell.rotation.y += dt * 0.04;

  composer.render();
  requestAnimationFrame(frame);
}

// Size from the stage element rather than the window. A ResizeObserver fires on
// the element's first layout, so a HUD that loads inside a container with no
// dimensions yet (hidden tab, kiosk mid-transition) still recovers — a plain
// window 'resize' listener never fires in that case and leaves a blank canvas.
function resize() {
  const w = stage.clientWidth || innerWidth;
  const h = stage.clientHeight || innerHeight;
  if (!w || !h) return;

  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  composer.setSize(w, h);
  bloom.resolution.set(w / 2, h / 2);  // half-res, per the perf budget
  shellMat.uniforms.uPixelRatio.value = renderer.getPixelRatio();
}

new ResizeObserver(resize).observe(stage);
addEventListener('resize', resize);

// ------------------------------------------------------------ fake events

// Build the HUD against fake events first, wire the real state feed second.
// Keys 1-4 cycle states; window.HUD is the seam that app.js setAssistantState()
// will drive later.
const FAKE_KEYS = { '1': 'locked', '2': 'listening', '3': 'thinking', '4': 'speaking' };
addEventListener('keydown', (e) => {
  const next = FAKE_KEYS[e.key];
  if (next) setState(next);
});

// `debug` exposes the live objects so bloom and shell brightness can be tuned
// from the console against the running scene, which is far quicker than
// editing constants and reloading.
window.HUD = {
  setState,
  states: Object.keys(STATES),
  debug: { renderer, scene, camera, bloom, shellMat, rings, ringGroup, shell }
};

setState('locked');
resize();
frame();
