/* ═══════════════════════════════════════════════════════════════════════
   VORIS — ITACHI, FACE TO FACE
   ───────────────────────────────────────────────────────────────────────
   Click the orb and Itachi comes forward. You talk to him directly: his
   face fills the frame, his reply appears beneath him, and his eyes turn
   red while he is actually working.

   This is a VIEW over the existing chat, never a second implementation:
     · the input writes to the real #messageInput and submits the real
       #composerForm, so auth / history / streaming / routing are reused
     · the caption mirrors the newest assistant message observed in
       #conversationThread
     · the eyes read data-assistant-state, which app.js already writes
   Nothing here edits app.js. Remove itachi.js + itachi.css to revert.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  if (window.__VORIS_ITACHI__) return;
  window.__VORIS_ITACHI__ = true;

  /* ─────────────────────────── configuration ─────────────────────────── */

  const FRAME_DIR = "/static-v2/frames/main";
  const FRAME_COUNT = 71;

  /* Shot map, measured from the footage:
       1–13  closed        14–24 opening        24 open, calm
       25–48 sharingan (extreme close-up)       49–71 pull back + crows   */
  const SHOT = {
    CLOSED: 1,
    OPEN: 24,
    SHARINGAN_IN: 30,
    SHARINGAN_HOT: 46,
    CROWS_IN: 56,
    CROWS_OUT: 70,
  };

  const STATE_FRAMES = {
    asleep:     { hold: SHOT.CLOSED },
    idle:       { loop: [1, 12], speed: 0.10 },
    listening:  { hold: SHOT.OPEN },
    analyzing:  { hold: SHOT.SHARINGAN_IN },
    thinking:   { loop: [SHOT.SHARINGAN_IN, SHOT.SHARINGAN_HOT], speed: 0.5 },
    responding: { hold: SHOT.OPEN },
    error:      { hold: 52 },
  };

  const HOT_STATES = new Set(["analyzing", "thinking"]);
  const CROWS_AFTER_MS = 9000;

  /* Wake sequence: closed -> open, played once when he comes forward. */
  const WAKE_MS = 1500;

  /* Framing. These are the regions that must STAY VISIBLE, not crop boxes.
     Measured from the footage: on the wide shots his head occupies
     x 0.26–0.74 with the face centred at (0.50, 0.59); the sharingan frames
     already fill the frame. A small margin is added so his hair never
     touches the edge. drawRegion() expands these to the canvas aspect
     rather than cropping to it, so the head is never clipped at any size. */
  const HEAD_WIDE = { x0: 0.235, x1: 0.765, y0: 0.00, y1: 1.00 };
  const HEAD_FULL = { x0: 0.000, x1: 1.000, y0: 0.00, y1: 1.00 };
  const isCloseUp = (n) => n >= 25 && n <= 48;

  const prefersReducedMotion =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const pad3 = (n) => String(n).padStart(3, "0");

  /* ───────────────────────────── overlay DOM ─────────────────────────────
     Built with createElement/textContent only — never innerHTML — so no
     model or user text can ever be parsed as markup.                      */

  const root = document.createElement("div");
  root.className = "itachi-face";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-label", "Face to face with VORIS");
  root.hidden = true;

  const veil = document.createElement("div");
  veil.className = "itachi-face__veil";

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "itachi-face__close";
  closeBtn.setAttribute("aria-label", "Leave face to face");
  closeBtn.textContent = "×";

  const portrait = document.createElement("div");
  portrait.className = "itachi-face__portrait";

  const canvas = document.createElement("canvas");
  canvas.className = "itachi-face__canvas";

  const glow = document.createElement("div");
  glow.className = "itachi-face__glow";
  portrait.appendChild(canvas);
  portrait.appendChild(glow);

  const speech = document.createElement("div");
  speech.className = "itachi-face__speech";

  const speechName = document.createElement("span");
  speechName.className = "itachi-face__name";
  speechName.textContent = "VORIS";

  const speechText = document.createElement("p");
  speechText.className = "itachi-face__line";
  speechText.textContent = "";

  speech.appendChild(speechName);
  speech.appendChild(speechText);

  const bar = document.createElement("form");
  bar.className = "itachi-face__bar";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "itachi-face__input";
  input.placeholder = "Speak to him…";
  /* id + name: without them Chrome raises "A form field element should have
     an id or name attribute", and autofill/AT have nothing to key off. */
  input.id = "itachiFaceInput";
  input.name = "itachiFaceMessage";
  input.setAttribute("aria-label", "Message VORIS");
  input.autocomplete = "off";

  const sendBtn = document.createElement("button");
  sendBtn.type = "submit";
  sendBtn.className = "itachi-face__send";
  sendBtn.textContent = "Send";

  bar.appendChild(input);
  bar.appendChild(sendBtn);

  const stage = document.createElement("div");
  stage.className = "itachi-face__stage";
  stage.appendChild(portrait);
  stage.appendChild(speech);
  stage.appendChild(bar);

  root.appendChild(veil);
  root.appendChild(closeBtn);
  root.appendChild(stage);

  function mount() {
    document.body.appendChild(root);
    bindTriggers();
    watchThread();
  }
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });

  const ctx = canvas.getContext("2d", { alpha: false });

  /* ───────────────────────────── frames ───────────────────────────── */

  const frames = new Array(FRAME_COUNT).fill(null);
  let loadedCount = 0;
  let preloadStarted = false;

  function loadFrame(n) {
    return new Promise((resolve) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => { frames[n - 1] = img; loadedCount++; resolve(); };
      img.onerror = () => { loadedCount++; resolve(); };
      img.src = `${FRAME_DIR}/${pad3(n)}.jpg`;
    });
  }

  /* Nothing loads until he is actually summoned — the normal chat never
     pays for 6.6MB of frames it is not showing. */
  async function preload() {
    if (preloadStarted) return;
    preloadStarted = true;

    const order = [];
    for (let n = 1; n <= SHOT.OPEN; n++) order.push(n);
    for (let n = SHOT.OPEN + 1; n <= 52; n++) order.push(n);
    for (let n = 53; n <= FRAME_COUNT; n++) order.push(n);

    await loadFrame(1);
    lastDrawn = -1;
    draw(1);

    let cursor = 0;
    const worker = async () => {
      while (cursor < order.length) {
        const n = order[cursor++];
        if (!frames[n - 1]) await loadFrame(n);
      }
    };
    await Promise.all(Array.from({ length: 6 }, worker));
    root.classList.add("is-loaded");
  }

  function nearestLoaded(idx) {
    const i = clamp(Math.round(idx), 1, FRAME_COUNT);
    if (frames[i - 1]) return i;
    for (let d = 1; d < FRAME_COUNT; d++) {
      if (frames[i - d - 1]) return i - d;
      if (frames[i + d - 1]) return i + d;
    }
    return 1;
  }

  /* ───────────────────────────── drawing ─────────────────────────────
     Grow `region` until it matches the canvas aspect, then draw it 1:1.

     Cover-fitting a fixed crop would clip whichever axis is proportionally
     larger — with a 3/4 portrait that shaved ~3% off each side of his hair.
     Expanding instead means the head bbox is always fully inside the frame
     at any window size, and the extra space is filled with real footage
     (the black surround) rather than letterboxing.                        */

  function expandToAspect(region, iw, ih, canvasAspect) {
    let { x0, x1, y0, y1 } = region;
    let w = (x1 - x0) * iw;
    let h = (y1 - y0) * ih;
    const cx = ((x0 + x1) / 2) * iw;
    const cy = ((y0 + y1) / 2) * ih;

    if (w / h < canvasAspect) w = h * canvasAspect;   // too narrow: widen
    else h = w / canvasAspect;                        // too short: heighten

    /* clamp inside the image, keeping the head centred where possible */
    w = Math.min(w, iw);
    h = Math.min(h, ih);
    let sx = clamp(cx - w / 2, 0, iw - w);
    let sy = clamp(cy - h / 2, 0, ih - h);
    return { sx, sy, sw: w, sh: h };
  }

  function fit() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.round(canvas.offsetWidth * dpr);
    const h = Math.round(canvas.offsetHeight * dpr);
    if (w > 0 && h > 0 && (canvas.width !== w || canvas.height !== h)) {
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
    if (!cw || !ch) return;

    const head = isCloseUp(n) ? HEAD_FULL : HEAD_WIDE;
    const { sx, sy, sw, sh } = expandToAspect(
      head, img.naturalWidth, img.naturalHeight, cw / ch
    );

    ctx.fillStyle = "#050506";
    ctx.fillRect(0, 0, cw, ch);
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, cw, ch);

    lastDrawn = n;
  }

  /* ───────────────────────── state machine ───────────────────────── */

  let state = "idle";
  let open = false;
  let stateEnteredAt = performance.now();
  let openedAt = 0;
  let playhead = 1;
  let loopPhase = 0;

  function computeTarget(now) {
    /* the wake: closed -> open, once, on entry */
    const sinceOpen = now - openedAt;
    if (open && sinceOpen < WAKE_MS) {
      const t = clamp(sinceOpen / WAKE_MS, 0, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      return lerp(SHOT.CLOSED, SHOT.OPEN, eased);
    }

    const plan = STATE_FRAMES[state] || STATE_FRAMES.idle;

    if (state === "thinking" && now - stateEnteredAt > CROWS_AFTER_MS) {
      const t = (now / 1400) % 2;
      const k = t < 1 ? t : 2 - t;
      return lerp(SHOT.CROWS_IN, SHOT.CROWS_OUT, k);
    }

    if (plan.hold !== undefined) return plan.hold;

    const [a, b] = plan.loop;
    loopPhase += (plan.speed || 0.3) * 0.016;
    return lerp(a, b, (Math.sin(loopPhase) + 1) / 2);
  }

  function setState(next) {
    const name = next in STATE_FRAMES ? next : "idle";
    if (name === state) return;
    state = name;
    stateEnteredAt = performance.now();
    root.dataset.state = name;
    document.body.dataset.itachiState = name;
    document.body.classList.toggle("itachi-hot", HOT_STATES.has(name));
  }

  /* ────────────────── read the real state, wherever it lives ──────────────────
     web_v2/app.js writes data-assistant-state on <body>; static/app.js writes
     it on #vorisApp. Observe the document and read whichever carries it.   */

  function stateHost() {
    return document.querySelector("[data-assistant-state]") || document.body;
  }
  function readState() {
    const host = stateHost();
    return (host && host.dataset.assistantState) || "idle";
  }

  new MutationObserver(() => setState(readState())).observe(
    document.documentElement,
    { attributes: true, subtree: true, attributeFilter: ["data-assistant-state"] }
  );

  /* ─────────────── mirror his newest reply into the caption ───────────────
     Reads textContent only. Never re-parses model output as HTML.        */

  function newestAssistantText() {
    const thread =
      document.getElementById("conversationThread") ||
      document.querySelector(".conversation, .conversation-thread");
    if (!thread) return "";

    const rows = thread.children;
    for (let i = rows.length - 1; i >= 0; i--) {
      const row = rows[i];
      const cls = row.className || "";
      if (/\byou\b|--user|__user|is-user/i.test(cls)) continue;
      const body =
        row.querySelector(".message__body, .message-card__content, .message__card") ||
        row;
      /* innerText respects rendered line breaks between block elements;
         textContent would run them together ("…first?Chat, documents…"). */
      const raw = body.innerText || body.textContent || "";
      const text = raw.replace(/\s+/g, " ").trim();
      if (text) return text;
    }
    return "";
  }

  let lastLine = "";
  function syncSpeech() {
    const text = newestAssistantText();
    if (!text || text === lastLine) return;
    lastLine = text;
    speechText.textContent = text.length > 460 ? text.slice(0, 460) + "…" : text;
    speech.classList.remove("is-fresh");
    void speech.offsetWidth;            // restart the entrance
    speech.classList.add("is-fresh");
  }

  function watchThread() {
    const thread =
      document.getElementById("conversationThread") ||
      document.querySelector(".conversation, .conversation-thread");
    if (!thread) return;
    new MutationObserver(() => { if (open) syncSpeech(); })
      .observe(thread, { childList: true, subtree: true, characterData: true });
  }

  /* ─────────────────── send through the real composer ─────────────────── */

  function realComposer() {
    return {
      form: document.getElementById("composerForm"),
      field: document.getElementById("messageInput"),
    };
  }

  bar.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    const { form, field } = realComposer();
    if (!form || !field) return;

    field.value = text;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    input.value = "";

    /* submit the real form so every existing handler runs */
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });

  /* ───────────────────────── open / close ───────────────────────── */

  let lastFocus = null;

  function openFace() {
    if (open) return;
    open = true;
    lastFocus = document.activeElement;
    root.hidden = false;
    document.body.classList.add("itachi-face-open");
    openedAt = performance.now();
    playhead = SHOT.CLOSED;
    lastDrawn = -1;
    preload();
    requestAnimationFrame(() => {
      root.classList.add("is-open");
      fit();
      syncSpeech();
      input.focus();
    });
    loop();
  }

  function closeFace() {
    if (!open) return;
    open = false;
    root.classList.remove("is-open");
    document.body.classList.remove("itachi-face-open");
    setTimeout(() => { if (!open) root.hidden = true; }, 420);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  closeBtn.addEventListener("click", closeFace);
  veil.addEventListener("click", closeFace);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && open) closeFace();
  });

  /* keep tab focus inside the dialog while it is open */
  root.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const items = [input, sendBtn, closeBtn];
    const i = items.indexOf(document.activeElement);
    if (i === -1) return;
    e.preventDefault();
    const next = e.shiftKey ? (i - 1 + items.length) % items.length
                            : (i + 1) % items.length;
    items[next].focus();
  });

  /* ───────────────── the orb is the door ─────────────────
     Selector list covers both front ends; whichever exists gets wired. */

  function bindTriggers() {
    const sel = "#vorisOrb, #orbStage, .orb-wrapper, #assistantOrb, .voris-orb";
    const all = Array.from(document.querySelectorAll(sel));

    /* These selectors nest — .voris-orb lives inside .orb-wrapper — and
       promoting both to role=button produces a button inside a button:
       invalid ARIA, confusing to screen readers, and a double-fired click.
       Keep only the outermost match of each cluster. */
    const outermost = all.filter(
      (el) => !all.some((other) => other !== el && other.contains(el))
    );

    outermost.forEach((el) => {
      if (el.dataset.itachiDoor) return;
      el.dataset.itachiDoor = "1";
      el.classList.add("itachi-door");
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-label", "Speak with VORIS face to face");
      el.addEventListener("click", openFace);
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openFace(); }
      });
    });
  }

  /* ───────────────────────── render loop ─────────────────────────
     Runs only while he is present. Closed = zero cost.               */

  function loop() {
    if (!open) return;
    const now = performance.now();
    if (fit()) lastDrawn = -1;

    const target = computeTarget(now);
    playhead = prefersReducedMotion ? target : lerp(playhead, target, 0.12);
    draw(playhead);

    requestAnimationFrame(loop);
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && open) { lastDrawn = -1; requestAnimationFrame(loop); }
  });

  setState(readState());

  window.VORIS_ITACHI = {
    open: openFace,
    close: closeFace,
    demo(name) { stateHost().dataset.assistantState = name; },
    get state() { return state; },
    get loaded() { return `${loadedCount}/${FRAME_COUNT}`; },
  };
})();
