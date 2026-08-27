/**
 * VORIS HUD — fullscreen sphere overlay for the Control Deck workspace.
 *
 * Layer order follows the HUD build spec: void + starfield (L0), particle
 * shell with limb brightening (L1), great-circle rings (L2), bloom (L3),
 * centre readout (L4), chrome (L5). The rings are deliberately the brightest
 * layer -- if the dust matches them you get a fuzzy ball instead of a machine.
 *
 * Three.js is imported dynamically on first open(), so the workspace does not
 * pay a ~700KB parse or hold a WebGL context it may never use.
 *
 * Public surface, on window.VorisHUD:
 *   open() / close() / toggle() / isOpen()
 *   setState('locked'|'listening'|'thinking'|'speaking')
 *   setLevel(0..1)          drives breathing + bloom
 *   say(text)               shows what the assistant just said, under the title
 *   setTelemetry({ providers, runtime })   real values only; see renderPanel()
 */

const STATES = {
  locked: {
    title: "System Locked", sub: "awaiting activation",
    core: 0x7fdfff, deep: 0x0a5c8f, ring: 0x00c8ff, spin: 0.12, bloom: 1.0,
  },
  listening: {
    title: "Listening", sub: "go ahead",
    core: 0xa5f3fc, deep: 0x0e7490, ring: 0x22d3ee, spin: 0.3, bloom: 1.15,
  },
  thinking: {
    title: "Processing", sub: "routing through tools",
    core: 0xffd27f, deep: 0xb45309, ring: 0xff8c1a, spin: 0.75, bloom: 1.3,
  },
  speaking: {
    title: "Responding", sub: "",
    core: 0xffe9b8, deep: 0xc2620a, ring: 0xffa033, spin: 0.38, bloom: 1.45,
  },
};

const CAMERA_Z = 5.2;
const PARTICLE_COUNT = 4000;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const dom = {};
let gl = null;              // three.js objects, null until first open()
let loading = null;         // in-flight import promise, so double-clicks share one
let isOpen = false;
let stateName = "locked";
let level = 0;
let levelDriven = false;    // true once setLevel() is called by something real
let raf = 0;
let lastFocus = null;
let telemetry = { providers: [], runtime: "" };

/* ------------------------------------------------------------------ chrome */

function buildDom() {
  if (dom.root) return;

  const root = document.createElement("div");
  root.className = "voris-hud";
  root.id = "vorisHud";
  root.hidden = true;
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-label", "VORIS presence display");

  const stage = document.createElement("div");
  stage.className = "voris-hud__stage";

  const chrome = document.createElement("div");
  chrome.className = "voris-hud__chrome";
  chrome.innerHTML = `
    <div class="voris-hud__sweep" aria-hidden="true"></div>
    <div class="voris-hud__readout" role="status" aria-live="polite">
      <p class="voris-hud__title" id="vorisHudTitle">System Locked</p>
      <p class="voris-hud__sub" id="vorisHudSub">awaiting activation</p>
      <p class="voris-hud__speech" id="vorisHudSpeech"></p>
    </div>
    <aside class="voris-hud__panel" id="vorisHudPanel" hidden></aside>
    <p class="voris-hud__hint">Esc or click to return to the workspace</p>
  `;

  root.append(stage, chrome);
  document.body.appendChild(root);

  dom.root = root;
  dom.stage = stage;
  dom.title = chrome.querySelector("#vorisHudTitle");
  dom.sub = chrome.querySelector("#vorisHudSub");
  dom.speech = chrome.querySelector("#vorisHudSpeech");
  dom.panel = chrome.querySelector("#vorisHudPanel");

  // Clicking the backdrop returns to the workspace; the readout itself is
  // selectable text, so clicks that land on it should not dismiss.
  root.addEventListener("click", (event) => {
    if (event.target.closest(".voris-hud__readout, .voris-hud__panel")) return;
    close();
  });
}

/**
 * Providers panel. Rendered only when real provider data has been handed in --
 * an empty or absent list hides the panel rather than showing invented rows.
 */
function renderPanel() {
  if (!dom.panel) return;
  const items = Array.isArray(telemetry.providers) ? telemetry.providers : [];
  if (!items.length) {
    dom.panel.hidden = true;
    dom.panel.replaceChildren();
    return;
  }

  const frag = document.createDocumentFragment();
  const head = document.createElement("h3");
  head.textContent = telemetry.runtime ? `Providers — runtime ${telemetry.runtime}` : "Providers";
  frag.appendChild(head);

  items.slice(0, 6).forEach((item) => {
    const row = document.createElement("div");
    row.className = "voris-hud__row";
    const key = document.createElement("span");
    key.className = "voris-hud__k";
    key.textContent = item.name || item.provider || "provider";
    const value = document.createElement("span");
    value.className = "voris-hud__v";
    const status = String(item.status || item.health || "unknown");
    value.textContent = status.replace(/_/g, " ");
    value.dataset.status = status.toLowerCase();
    row.append(key, value);
    frag.appendChild(row);
  });

  dom.panel.replaceChildren(frag);
  dom.panel.hidden = false;
}

/* ------------------------------------------------------------------- scene */

const SHELL_VERT = `
attribute float aRnd;
uniform float uTime, uLevel, uSize, uPixelRatio, uRefDist;
varying float vEdge;

void main() {
  vec3 p = position;
  p *= 1.0 + uLevel * 0.10 + sin(uTime * 2.0 + aRnd * 40.0) * 0.012;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);

  // limb brightening: a normal perpendicular to the view is the silhouette
  vec3 n = normalize(mat3(modelViewMatrix) * normalize(position));
  vEdge = 1.0 - abs(dot(n, vec3(0.0, 0.0, 1.0)));

  // uSize is CSS pixels at the camera's rest distance. The spec's
  // (300.0 / -mv.z) is three's PointsMaterial projection scale, not a pixel
  // count -- at z=5.2 it yields ~115px sprites that additively blend into a
  // solid white disc instead of a hollow shell.
  gl_PointSize = uSize * uPixelRatio * (1.0 + vEdge * 1.6)
               * (1.0 + uLevel * 0.5) * (uRefDist / -mv.z);
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

async function ensureScene() {
  if (gl) return gl;
  if (loading) return loading;

  loading = (async () => {
    const THREE = await import("three");
    const { EffectComposer } = await import("three/addons/postprocessing/EffectComposer.js");
    const { RenderPass } = await import("three/addons/postprocessing/RenderPass.js");
    const { UnrealBloomPass } = await import("three/addons/postprocessing/UnrealBloomPass.js");
    const { OutputPass } = await import("three/addons/postprocessing/OutputPass.js");

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.z = CAMERA_Z;

    // No antialias: the scene renders into the composer's own target, so MSAA
    // on the default framebuffer would only apply to a fullscreen triangle.
    const renderer = new THREE.WebGLRenderer({ powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    // The composer works in linear space, so an sRGB hex handed straight to
    // setClearColor arrives on screen several stops light (#03060f -> ~#1e2645).
    renderer.setClearColor(new THREE.Color(0x03060f).convertSRGBToLinear(), 1);
    dom.stage.appendChild(renderer.domElement);

    // L0 -- starfield well behind the sphere
    const starPos = new Float32Array(160 * 3);
    for (let i = 0; i < 160; i++) {
      starPos[i * 3] = (Math.random() - 0.5) * 30;
      starPos[i * 3 + 1] = (Math.random() - 0.5) * 18;
      starPos[i * 3 + 2] = -8 - Math.random() * 12;
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({
      color: 0x5c8fb8, size: 0.035, sizeAttenuation: true,
      transparent: true, opacity: 0.55,
    })));

    // L1 -- Fibonacci shell, even coverage with no polar clustering
    const pos = new Float32Array(PARTICLE_COUNT * 3);
    const rnd = new Float32Array(PARTICLE_COUNT);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const y = 1 - (i / (PARTICLE_COUNT - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const t = golden * i;
      const rad = 1 + (Math.random() - 0.5) * 0.06;
      pos[i * 3] = Math.cos(t) * r * rad;
      pos[i * 3 + 1] = y * rad;
      pos[i * 3 + 2] = Math.sin(t) * r * rad;
      rnd[i] = Math.random();
    }
    const shellGeo = new THREE.BufferGeometry();
    shellGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    shellGeo.setAttribute("aRnd", new THREE.BufferAttribute(rnd, 1));

    const shellMat = new THREE.ShaderMaterial({
      vertexShader: SHELL_VERT,
      fragmentShader: SHELL_FRAG,
      transparent: true,
      depthWrite: false,             // with additive blending, keeps the volume
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uLevel: { value: 0 },
        uSize: { value: 2.4 },
        uPixelRatio: { value: renderer.getPixelRatio() },
        uRefDist: { value: CAMERA_Z },
        uCore: { value: new THREE.Color(STATES.locked.core) },
        uDeep: { value: new THREE.Color(STATES.locked.deep) },
      },
    });
    const shell = new THREE.Points(shellGeo, shellMat);
    scene.add(shell);

    // L2 -- great circles. TorusGeometry, never THREE.Line: WebGL caps line
    // width at 1px on virtually every platform.
    const makeRing = (radius, tube, color) => new THREE.Mesh(
      new THREE.TorusGeometry(radius, tube, 12, 220),
      new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.95,
        blending: THREE.AdditiveBlending, depthWrite: false,
      }),
    );
    const ringA = makeRing(1.06, 0.006, 0x00c8ff);
    const ringB = makeRing(1.06, 0.005, 0x00c8ff);
    const ringC = makeRing(1.1, 0.003, 0x0090cc);
    ringB.rotation.y = Math.PI / 2;
    ringC.rotation.x = Math.PI / 2;
    const ringGroup = new THREE.Group();
    ringGroup.add(ringA, ringB, ringC);
    ringGroup.rotation.z = 0.34;               // ~20 degrees off-axis
    scene.add(ringGroup);

    // L3 -- bloom. Threshold must stay under the ring brightness or the rings
    // never bloom and the whole effect fails.
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 1.15, 0.45, 0.18);
    composer.addPass(bloom);
    // Without a final sRGB encode the composer's linear output reaches the
    // screen unconverted: the rings render as thin flat lines instead of
    // neon tubes, and the dust ends up competing with them.
    composer.addPass(new OutputPass());

    const live = {
      core: new THREE.Color(STATES.locked.core),
      deep: new THREE.Color(STATES.locked.deep),
      ring: new THREE.Color(STATES.locked.ring),
      spin: STATES.locked.spin,
      bloom: STATES.locked.bloom,
    };
    const scratch = { core: new THREE.Color(), deep: new THREE.Color(), ring: new THREE.Color() };

    gl = {
      THREE, renderer, scene, camera, composer, bloom,
      shell, shellMat, rings: [ringA, ringB, ringC],
      live, scratch, clock: new THREE.Clock(),
    };

    // Size from the stage box, not the window: a ResizeObserver fires on first
    // layout, so opening from a hidden container still gets a real canvas.
    gl.observer = new ResizeObserver(resize);
    gl.observer.observe(dom.stage);
    resize();
    return gl;
  })();

  return loading;
}

function resize() {
  if (!gl) return;
  const w = dom.stage.clientWidth || window.innerWidth;
  const h = dom.stage.clientHeight || window.innerHeight;
  if (!w || !h) return;
  gl.camera.aspect = w / h;
  gl.camera.updateProjectionMatrix();
  gl.renderer.setSize(w, h);
  gl.composer.setSize(w, h);
  gl.bloom.resolution.set(w / 2, h / 2);       // half-res; bloom is blurry anyway
  gl.shellMat.uniforms.uPixelRatio.value = gl.renderer.getPixelRatio();
}

/* -------------------------------------------------------------------- loop */

function frame() {
  if (!gl || !isOpen) return;
  const dt = Math.min(gl.clock.getDelta(), 0.1);
  const t = gl.clock.elapsedTime;
  const target = STATES[stateName] || STATES.locked;

  // Purely visual idle breath until something real drives the level.
  const lvl = levelDriven ? level : 0.18 + Math.sin(t * 0.9) * 0.1 + Math.sin(t * 2.3) * 0.04;

  const k = Math.min(dt * 1.6, 1);             // ~1s crossfade; never snap
  gl.live.core.lerp(gl.scratch.core.setHex(target.core), k);
  gl.live.deep.lerp(gl.scratch.deep.setHex(target.deep), k);
  gl.live.ring.lerp(gl.scratch.ring.setHex(target.ring), k);
  gl.live.spin += (target.spin - gl.live.spin) * k;
  gl.live.bloom += (target.bloom - gl.live.bloom) * k;

  gl.shellMat.uniforms.uCore.value.copy(gl.live.core);
  gl.shellMat.uniforms.uDeep.value.copy(gl.live.deep);
  gl.shellMat.uniforms.uTime.value = t;
  gl.shellMat.uniforms.uLevel.value = lvl;
  for (const ring of gl.rings) ring.material.color.copy(gl.live.ring);
  // Ceiling matters: speaking sits at 1.45 and the level adds up to 0.5 more,
  // which pushes past the ~1.6 point where the whole sphere blows out white
  // and the rings stop being distinguishable from the dust.
  gl.bloom.strength = Math.min(gl.live.bloom + lvl * 0.5, 1.5);

  // Non-harmonic ratios: 0.5/0.25 would visibly loop every few seconds.
  const spin = reducedMotion ? gl.live.spin * 0.25 : gl.live.spin;
  gl.rings[0].rotation.y += dt * spin * 1.0;
  gl.rings[1].rotation.x += dt * spin * 0.62;
  gl.rings[2].rotation.z += dt * spin * 0.41;
  gl.shell.rotation.y += dt * 0.04;

  gl.composer.render();
  raf = requestAnimationFrame(frame);
}

/* ------------------------------------------------------------------ public */

function applyState() {
  const target = STATES[stateName] || STATES.locked;
  if (dom.root) dom.root.dataset.state = stateName;
  if (dom.title) dom.title.textContent = target.title;
  if (dom.sub) dom.sub.textContent = target.sub;
}

function setState(next) {
  const name = String(next || "").toLowerCase();
  if (!(name in STATES)) return;
  stateName = name;
  applyState();
}

function setLevel(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return;
  level = Math.min(Math.max(n, 0), 1);
  levelDriven = true;
}

function say(text) {
  const line = String(text || "").trim();
  if (!dom.speech) return;
  dom.speech.textContent = line.length > 160 ? `${line.slice(0, 157)}...` : line;
}

function setTelemetry(next) {
  if (!next || typeof next !== "object") return;
  if (Array.isArray(next.providers)) telemetry.providers = next.providers;
  if (typeof next.runtime === "string") telemetry.runtime = next.runtime;
  renderPanel();
}

function onKeydown(event) {
  if (event.key === "Escape") {
    event.preventDefault();
    close();
  }
}

async function open() {
  if (isOpen) return;
  buildDom();
  applyState();
  renderPanel();

  lastFocus = document.activeElement;
  isOpen = true;
  dom.root.hidden = false;
  document.body.classList.add("voris-hud-active");
  document.addEventListener("keydown", onKeydown);

  try {
    await ensureScene();
  } catch (error) {
    isOpen = false;
    dom.root.hidden = true;
    document.body.classList.remove("voris-hud-active");
    document.removeEventListener("keydown", onKeydown);
    console.error("[hud] WebGL unavailable", error);
    return;
  }
  if (!isOpen) return;              // closed again while three was loading

  resize();
  gl.clock.getDelta();              // drop the load time so dt starts sane
  dom.root.focus?.();
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(frame);
}

function close() {
  if (!isOpen) return;
  isOpen = false;
  cancelAnimationFrame(raf);
  raf = 0;
  if (dom.root) dom.root.hidden = true;
  document.body.classList.remove("voris-hud-active");
  document.removeEventListener("keydown", onKeydown);
  if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
}

function toggle() {
  if (isOpen) close();
  else void open();
}

window.VorisHUD = {
  open, close, toggle, setState, setLevel, say, setTelemetry,
  isOpen: () => isOpen,
  states: Object.keys(STATES),
};
