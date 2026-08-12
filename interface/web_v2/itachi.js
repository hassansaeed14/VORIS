/* ═══════════════════════════════════════════════════════════════════════
   VORIS — ITACHI PRESENCE LAYER
   ───────────────────────────────────────────────────────────────────────
   The face is the status indicator.

   This module renders a frame sequence whose position is driven by the
   assistant's real state, read from document.body[data-assistant-state].
   It registers no callbacks into app.js and imports nothing from it — the
   coupling is one DOM attribute, so app.js stays untouched and this whole
   feature reverts by removing two files and three tags from voris.html.

   Truth rule (MASTER_SPEC): the face may never claim a state the backend
   is not actually in. Every frame target below is derived from the state
   attribute, never from a timer pretending to be work.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  if (window.__VORIS_ITACHI__) return;   // idempotent: safe if loaded twice
  window.__VORIS_ITACHI__ = true;

  /* ─────────────────────── configuration ─────────────────────── */

  const FRAME_DIR = "/static-v2/frames/main";
  const FRAME_COUNT = 71;

  /* Shot map, measured from the footage:
       1–13  eyes closed            24     eyes fully open, calm
       14–24 opening                25–48  sharingan (extreme close-up, red)
       49–52 pulling back           53–71  crows                              */
  const SHOT = {
    CLOSED: 1,
    OPEN: 24,
    SHARINGAN_IN: 30,
    SHARINGAN_HOT: 46,
    CROWS_IN: 56,
    CROWS_OUT: 70,
  };

  /* Where each assistant state parks the playhead.
     `loop` ranges drift back and forth so a long task never looks frozen. */
  const STATE_FRAMES = {
    asleep:    { hold: SHOT.CLOSED },
    idle:      { loop: [1, 12], speed: 0.10 },          // slow breathing
    listening: { hold: SHOT.OPEN },                     // eyes open, watching
    analyzing: { hold: SHOT.SHARINGAN_IN },             // red ignites
    thinking:  { loop: [SHOT.SHARINGAN_IN, SHOT.SHARINGAN_HOT], speed: 0.5 },
    responding:{ hold: SHOT.OPEN },                     // settled, no red
    error:     { hold: 52 },                            // red dimming out
  };

  /* States where the eyes are red. Used only for CSS accenting. */
  const HOT_STATES = new Set(["analyzing", "thinking"]);

  /* If `thinking` runs longer than this, drift into the crows.
     Not a fake state — still thinking, just visually deepening. */
  const CROWS_AFTER_MS = 9000;

  /* Idle sleep: he closes his eyes after this long with no interaction,
     and reopens them the moment you come back. */
  const SLEEP_AFTER_MS = 90000;

  /* Per-frame mean luminance of the bottom 55% of each frame, precomputed
     at build time. Drives the scrim so chat text keeps its contrast when the
     footage cuts to the bright sharingan close-up. Index 0 === frame 001. */
  const LUMA = [
    0.129, 0.130, 0.131, 0.132, 0.133, 0.134, 0.134, 0.135, 0.135, 0.136,
    0.136, 0.136, 0.137, 0.139, 0.140, 0.142, 0.143, 0.144, 0.145, 0.147,
    0.149, 0.151, 0.156, 0.162, 0.177, 0.195, 0.228, 0.255, 0.287, 0.328,
    0.358, 0.400, 0.425, 0.452, 0.469, 0.478, 0.473, 0.450, 0.428, 0.411,
    0.390, 0.385, 0.389, 0.404, 0.419, 0.432, 0.439, 0.447, 0.439, 0.374,
    0.259, 0.221, 0.208, 0.206, 0.200, 0.197, 0.194, 0.201, 0.200, 0.200,
    0.198, 0.195, 0.195, 0.193, 0.193, 0.195, 0.196, 0.198, 0.192, 0.192,
    0.194,
  ];

  const prefersReducedMotion =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ─────────────────────────── helpers ─────────────────────────── */

  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const pad3 = (n) => String(n).padStart(3, "0");

  /* ───────────────────────── DOM scaffold ───────────────────────── */

  const stage = document.createElement("div");
  stage.className = "itachi-stage";
  stage.setAttribute("aria-hidden", "true");

  const canvas = document.createElement("canvas");
  canvas.className = "itachi-stage__canvas";

  const scrim = document.createElement("div");
  scrim.className = "itachi-stage__scrim";

  const bloom = document.createElement("div");
  bloom.className = "itachi-stage__bloom";

  stage.appendChild(canvas);
  stage.appendChild(bloom);
  stage.appendChild(scrim);

  function mount() {
    document.body.insertBefore(stage, document.body.firstChild);
    document.body.classList.add("itachi-active");
  }
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });

  const ctx = canvas.getContext("2d", { alpha: false });

  /* ───────────────────────── frame loading ─────────────────────────
     Priority order matters: the closed/opening frames are what the user
     sees first, so they load before the sharingan and crows. The render
     loop draws the nearest *loaded* frame, so playback degrades to a
     coarser sequence while loading rather than stalling.               */

  const frames = new Array(FRAME_COUNT).fill(null);
  let loadedCount = 0;

  function loadFrame(n) {
    return new Promise((resolve) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => { frames[n - 1] = img; loadedCount++; resolve(); };
      img.onerror = () => { loadedCount++; resolve(); };   // gap, not a crash
      img.src = `${FRAME_DIR}/${pad3(n)}.jpg`;
    });
  }

  async function preload() {
    const order = [];
    for (let n = 1; n <= SHOT.OPEN; n++) order.push(n);                  // wake
    for (let n = SHOT.OPEN + 1; n <= 52; n++) order.push(n);             // red
    for (let n = 53; n <= FRAME_COUNT; n++) order.push(n);               // crows

    await loadFrame(1);                       // paint something immediately
    draw(1);

    const CONCURRENCY = 6;
    let cursor = 0;
    async function worker() {
      while (cursor < order.length) {
        const n = order[cursor++];
        if (!frames[n - 1]) await loadFrame(n);
      }
    }
    await Promise.all(
      Array.from({ length: CONCURRENCY }, worker)
    );
    stage.classList.add("is-loaded");
  }

  /* nearest loaded frame to `idx` (1-based), so gaps never stall playback */
  function nearestLoaded(idx) {
    const i = clamp(Math.round(idx), 1, FRAME_COUNT);
    if (frames[i - 1]) return i;
    for (let d = 1; d < FRAME_COUNT; d++) {
      if (frames[i - d - 1]) return i - d;
      if (frames[i + d - 1]) return i + d;
    }
    return 1;
  }

  /* ───────────────────────── canvas drawing ─────────────────────────
     Cover-fit, but capped so a tall/narrow window crops toward the face
     instead of zooming into a nostril.                                  */

  function fit() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.round(window.innerWidth * dpr);
    const h = Math.round(window.innerHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      return true;
    }
    return false;
  }

  let lastDrawn = -1;

  function draw(idx) {
    const n = nearestLoaded(idx);
    if (n === lastDrawn) return;
    const img = frames[n - 1];
    if (!img || !img.naturalWidth) return;

    const cw = canvas.width;
    const ch = canvas.height;
    ctx.fillStyle = "#050506";
    ctx.fillRect(0, 0, cw, ch);

    const ir = img.naturalWidth / img.naturalHeight;
    let w = cw;
    let h = cw / ir;
    if (h < ch) {
      const s = Math.min(ch / h, 2.0);
      w *= s;
      h *= s;
    }
    /* bias upward: the face sits in the top two-thirds, so anchoring the
       crop at the vertical centre would push his eyes off a short window */
    ctx.drawImage(img, (cw - w) / 2, (ch - h) * 0.34, w, h);
    lastDrawn = n;

    /* scrim strength tracks the footage brightness at this frame */
    const luma = LUMA[n - 1] ?? 0.2;
    const opacity = clamp(0.30 + (luma - 0.13) * 1.35, 0.30, 0.88);
    scrim.style.setProperty("--scrim", opacity.toFixed(3));
  }

  /* ───────────────────────── state machine ───────────────────────── */

  let state = "idle";
  let asleep = false;
  let stateEnteredAt = performance.now();
  let lastInteraction = performance.now();

  let playhead = 1;      // eased, fractional
  let target = 1;
  let loopPhase = 0;

  function currentPlan() {
    if (asleep) return STATE_FRAMES.asleep;
    return STATE_FRAMES[state] || STATE_FRAMES.idle;
  }

  function computeTarget(now) {
    const plan = currentPlan();

    /* long thinking drifts into the crows — still thinking, shown deeper */
    if (
      state === "thinking" &&
      !asleep &&
      now - stateEnteredAt > CROWS_AFTER_MS
    ) {
      const t = (now / 1400) % 2;
      const k = t < 1 ? t : 2 - t;
      return lerp(SHOT.CROWS_IN, SHOT.CROWS_OUT, k);
    }

    if (plan.hold !== undefined) return plan.hold;

    const [a, b] = plan.loop;
    loopPhase += (plan.speed || 0.3) * 0.016;
    const k = (Math.sin(loopPhase) + 1) / 2;
    return lerp(a, b, k);
  }

  function setState(next) {
    const name = next in STATE_FRAMES ? next : "idle";
    if (name === state) return;
    state = name;
    stateEnteredAt = performance.now();
    stage.dataset.state = name;
    document.body.classList.toggle("itachi-hot", HOT_STATES.has(name));

    /* any real state change means the system is working for you — wake up */
    if (name !== "idle") wake();
  }

  function wake() {
    lastInteraction = performance.now();
    if (!asleep) return;
    asleep = false;
    stage.classList.remove("is-asleep");
  }

  function sleep() {
    if (asleep) return;
    asleep = true;
    stage.classList.add("is-asleep");
  }

  /* ───────────────────── observe the real state ─────────────────────
     app.js writes document.body.dataset.assistantState. That attribute is
     the only contract between the two files.                            */

  function readState() {
    return document.body.dataset.assistantState || "idle";
  }

  const observer = new MutationObserver(() => setState(readState()));

  function startObserving() {
    setState(readState());
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["data-assistant-state"],
    });
  }
  if (document.body) startObserving();
  else document.addEventListener("DOMContentLoaded", startObserving, { once: true });

  /* interaction resets the sleep timer */
  ["pointerdown", "keydown", "pointermove", "focusin"].forEach((evt) => {
    window.addEventListener(evt, wake, { passive: true });
  });

  /* ─────────────────────────── render loop ─────────────────────────── */

  let running = true;
  document.addEventListener("visibilitychange", () => {
    running = !document.hidden;
    if (running) {
      lastDrawn = -1;      // force a repaint on return
      requestAnimationFrame(tick);
    }
  });

  function tick() {
    if (!running) return;

    const now = performance.now();

    if (!asleep && now - lastInteraction > SLEEP_AFTER_MS && state === "idle") {
      sleep();
    }

    if (fit()) lastDrawn = -1;

    target = computeTarget(now);

    if (prefersReducedMotion) {
      /* no interpolation: snap to the state's frame and hold it */
      playhead = target;
    } else {
      playhead = lerp(playhead, target, 0.09);
    }

    draw(playhead);
    requestAnimationFrame(tick);
  }

  /* ─────────────────────────────── boot ─────────────────────────────── */

  fit();
  preload();
  requestAnimationFrame(tick);

  /* Small, deliberate public surface — lets you demo states from the
     console without a backend: VORIS_ITACHI.demo('thinking') */
  window.VORIS_ITACHI = {
    demo(name) { document.body.dataset.assistantState = name; },
    sleep, wake,
    get state() { return state; },
    get loaded() { return `${loadedCount}/${FRAME_COUNT}`; },
  };
})();
