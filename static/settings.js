/* ═══════════════════════════════════════════════════════════════════════
   VORIS — SETTINGS DRAWER
   ───────────────────────────────────────────────────────────────────────
   Voice and image configuration, wired to the endpoints that already exist:
     GET   /api/voice/status     current settings + tts/stt capability
     GET   /api/voice/personas   available voice profiles
     PATCH /api/voice/settings   persist a change
     GET   /api/image/status     image provider truth

   Design rule, taken from MASTER_SPEC: a control is only shown as usable
   if the backend actually supports it. Each section reports its real state
   and anything unavailable explains itself in plain language rather than
   silently greying out.

   Built with createElement/textContent throughout — never innerHTML — so
   nothing returned by the API can be parsed as markup.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  if (window.__VORIS_SETTINGS__) return;
  window.__VORIS_SETTINGS__ = true;

  /* ───────────────────────────── helpers ───────────────────────────── */

  function el(tag, props, kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (v === undefined || v === null) return;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k in node && k !== "list") node[k] = v;
      else node.setAttribute(k, v);
    });
    (kids || []).forEach((c) => c && node.appendChild(c));
    return node;
  }

  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  async function getJSON(url) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      return r.ok ? await r.json() : null;
    } catch { return null; }
  }

  /* ─────────────────────────── state + saving ─────────────────────────── */

  let settings = {};
  let voiceStatus = {};
  let saveTimer = null;
  const pending = {};

  const savedNote = el("span", { class: "vs-saved", text: "No changes yet" });

  function queueSave(patch) {
    Object.assign(pending, patch);
    savedNote.className = "vs-saved";
    savedNote.textContent = "Saving…";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flush, 420);
  }

  async function flush() {
    const body = { ...pending };
    for (const k of Object.keys(pending)) delete pending[k];
    if (!Object.keys(body).length) return;
    try {
      const r = await fetch("/api/voice/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();
      if (data && data.settings) settings = data.settings;
      savedNote.className = "vs-saved is-ok";
      savedNote.textContent = "Saved";
    } catch (err) {
      savedNote.className = "vs-saved is-err";
      savedNote.textContent = "Not saved — " + err.message;
    }
  }

  /* ───────────────────────────── controls ───────────────────────────── */

  function statusChip(kind, label) {
    return el("span", { class: "vs-status vs-status--" + kind, text: label });
  }

  function sectionEl(title, chip, note) {
    const head = el("div", { class: "vs-section__head" }, [
      el("h3", { class: "vs-section__title", text: title }),
      chip,
    ]);
    const sec = el("section", { class: "vs-section" }, [head]);
    if (note) sec.appendChild(el("p", { class: "vs-section__note", text: note }));
    return sec;
  }

  /* label + live mono readout + full-width slider */
  function sliderRow(opts) {
    const value = el("span", { class: "vs-value", text: opts.format(opts.value) });
    const input = el("input", {
      class: "vs-slider",
      type: "range",
      min: String(opts.min),
      max: String(opts.max),
      step: String(opts.step),
      value: String(opts.value),
      disabled: !!opts.disabled,
      "aria-label": opts.label,
    });
    input.addEventListener("input", () => {
      const v = parseFloat(input.value);
      value.textContent = opts.format(v);
      opts.onChange(v);
    });
    const row = el("div", { class: "vs-row" + (opts.disabled ? " is-disabled" : "") }, [
      el("span", { class: "vs-row__label", text: opts.label }),
      value,
      input,
    ]);
    if (opts.hint) row.appendChild(el("p", { class: "vs-row__hint", text: opts.hint }));
    return row;
  }

  function switchRow(opts) {
    const btn = el("button", {
      class: "vs-switch",
      type: "button",
      role: "switch",
      "aria-checked": String(!!opts.value),
      "aria-label": opts.label,
      disabled: !!opts.disabled,
    });
    btn.addEventListener("click", () => {
      const next = btn.getAttribute("aria-checked") !== "true";
      btn.setAttribute("aria-checked", String(next));
      opts.onChange(next);
    });
    const row = el("div", { class: "vs-row" + (opts.disabled ? " is-disabled" : "") }, [
      el("span", { class: "vs-row__label", text: opts.label }),
      btn,
    ]);
    if (opts.hint) row.appendChild(el("p", { class: "vs-row__hint", text: opts.hint }));
    return row;
  }

  function selectRow(opts) {
    const sel = el("select", {
      class: "vs-select",
      disabled: !!opts.disabled,
      "aria-label": opts.label,
    });
    (opts.options || []).forEach((o) =>
      sel.appendChild(el("option", { value: o.value, text: o.label, selected: o.value === opts.value }))
    );
    sel.addEventListener("change", () => opts.onChange(sel.value));
    const row = el("div", { class: "vs-row" + (opts.disabled ? " is-disabled" : "") }, [
      el("span", { class: "vs-row__label", text: opts.label }),
      sel,
    ]);
    if (opts.hint) row.appendChild(el("p", { class: "vs-row__hint", text: opts.hint }));
    return row;
  }

  function wakeWordRow(words, disabled, onChange) {
    const list = Array.isArray(words) ? words.slice() : [];
    const chips = el("div", { class: "vs-chips" });

    function render() {
      while (chips.firstChild) chips.removeChild(chips.firstChild);
      list.forEach((w, i) => {
        chips.appendChild(
          el("span", { class: "vs-chip" }, [
            el("span", { text: w }),
            el("button", {
              class: "vs-chip__x",
              type: "button",
              text: "×",
              "aria-label": "Remove wake word " + w,
              disabled,
              onclick: () => { list.splice(i, 1); render(); onChange(list.slice()); },
            }),
          ])
        );
      });
      const add = el("input", {
        class: "vs-chip-input",
        type: "text",
        placeholder: "add a phrase…",
        disabled,
        "aria-label": "Add a wake word",
      });
      add.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        const v = add.value.trim().toLowerCase();
        if (!v || list.includes(v) || list.length >= 8) { add.value = ""; return; }
        list.push(v);
        render();
        onChange(list.slice());
      });
      chips.appendChild(add);
    }
    render();

    const row = el("div", { class: "vs-row" + (disabled ? " is-disabled" : "") }, [
      el("span", { class: "vs-row__label", text: "Wake phrases" }),
      el("span", { class: "vs-value", text: String(list.length) + "/8" }),
      chips,
    ]);
    row.appendChild(
      el("p", {
        class: "vs-row__hint",
        text: "Press Enter to add. Say one of these to start listening.",
      })
    );
    return row;
  }

  /* ─────────────────────────── drawer shell ─────────────────────────── */

  const scrim = el("div", { class: "vs-scrim" });
  const body = el("div", { class: "vs-body" });

  const closeBtn = el("button", {
    class: "vs-close",
    type: "button",
    text: "×",
    "aria-label": "Close settings",
  });

  const drawer = el("div", {
    class: "vs-drawer",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "VORIS settings",
    hidden: true,
  }, [
    el("div", { class: "vs-head" }, [
      el("div", {}, [
        el("p", { class: "vs-head__eyebrow", text: "Control deck" }),
        el("h2", { class: "vs-head__title", text: "Settings" }),
      ]),
      closeBtn,
    ]),
    body,
    el("div", { class: "vs-foot" }, [
      savedNote,
      el("span", {
        class: "vs-saved",
        text: "Changes apply immediately",
      }),
    ]),
  ]);

  /* ───────────────────────────── build body ───────────────────────────── */

  function speakSample() {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(
      "This is how I sound at these settings."
    );
    u.rate = clamp(Number(settings.rate) || 1, 0.5, 2);
    u.pitch = clamp(Number(settings.pitch) || 1, 0, 2);
    u.volume = clamp(Number(settings.volume) || 1, 0, 1);
    if (settings.language) u.lang = settings.language;
    synth.speak(u);
  }

  function render(personas, imageStatus) {
    while (body.firstChild) body.removeChild(body.firstChild);

    const tts = voiceStatus.tts || {};
    const browserTTS = typeof window.speechSynthesis !== "undefined";

    /* ── Speaking ── */
    const speakChip = browserTTS
      ? statusChip("live", "Live in browser")
      : statusChip("off", "Unavailable");

    const speaking = sectionEl(
      "Speaking",
      speakChip,
      browserTTS
        ? "VORIS reads replies aloud using your browser's speech engine. Changes take effect on the next reply."
        : "This browser has no speech engine, so VORIS cannot read replies aloud here."
    );

    if (personas.length) {
      speaking.appendChild(selectRow({
        label: "Voice",
        value: settings.profile_id || "jarvis",
        options: personas.map((p) => ({ value: p.id, label: p.name })),
        onChange: (v) => { settings.profile_id = v; queueSave({ profile_id: v }); },
      }));
    }

    speaking.appendChild(sliderRow({
      label: "Speed", min: 0.5, max: 2, step: 0.05,
      value: Number(settings.rate) || 0.95,
      disabled: !browserTTS,
      format: (v) => v.toFixed(2) + "×",
      onChange: (v) => { settings.rate = v; queueSave({ rate: v }); },
    }));

    speaking.appendChild(sliderRow({
      label: "Pitch", min: 0, max: 2, step: 0.05,
      value: Number(settings.pitch) || 0.85,
      disabled: !browserTTS,
      format: (v) => v.toFixed(2),
      onChange: (v) => { settings.pitch = v; queueSave({ pitch: v }); },
    }));

    speaking.appendChild(sliderRow({
      label: "Volume", min: 0, max: 1, step: 0.05,
      value: Number(settings.volume) === 0 ? 0 : Number(settings.volume) || 1,
      disabled: !browserTTS,
      format: (v) => Math.round(v * 100) + "%",
      onChange: (v) => { settings.volume = v; queueSave({ volume: v }); },
    }));

    speaking.appendChild(switchRow({
      label: "Read replies aloud",
      value: settings.auto_speak_responses !== false,
      disabled: !browserTTS,
      onChange: (v) => { settings.auto_speak_responses = v; queueSave({ auto_speak_responses: v }); },
    }));

    speaking.appendChild(
      el("div", { class: "vs-row" }, [
        el("span", { class: "vs-row__label", text: "Hear these settings" }),
        el("button", {
          class: "vs-btn",
          type: "button",
          text: "Play sample",
          disabled: !browserTTS,
          onclick: speakSample,
        }),
      ])
    );

    body.appendChild(speaking);

    /* ── Listening ── */
    const micReady = !!(voiceStatus.microphone && voiceStatus.microphone.available);
    const browserSTT =
      "webkitSpeechRecognition" in window || "SpeechRecognition" in window;

    let listenChip;
    let listenNote;
    if (micReady) {
      listenChip = statusChip("live", "Desktop mic ready");
      listenNote = "Wake phrases start a listening turn on your machine.";
    } else if (browserSTT) {
      listenChip = statusChip("partial", "Browser only");
      listenNote =
        "Your browser can listen with the mic button. Desktop wake words need local speech dependencies installed.";
    } else {
      listenChip = statusChip("off", "Unavailable");
      listenNote =
        "No speech recognition here. Install the local speech dependencies, or use a browser that supports it.";
    }

    const listening = sectionEl("Listening", listenChip, listenNote);
    const listenDisabled = !micReady && !browserSTT;

    listening.appendChild(
      wakeWordRow(settings.wake_words, listenDisabled, (words) => {
        settings.wake_words = words;
        queueSave({ wake_words: words });
      })
    );

    listening.appendChild(sliderRow({
      label: "Wake sensitivity", min: 0, max: 1, step: 0.05,
      value: Number(settings.wake_word_sensitivity) || 0.7,
      disabled: listenDisabled,
      format: (v) => Math.round(v * 100) + "%",
      hint: "Higher catches more, and mishears more.",
      onChange: (v) => {
        settings.wake_word_sensitivity = v;
        queueSave({ wake_word_sensitivity: v });
      },
    }));

    listening.appendChild(sliderRow({
      label: "Listen for", min: 2, max: 30, step: 1,
      value: Number(settings.phrase_time_limit) || 8,
      disabled: listenDisabled,
      format: (v) => v.toFixed(0) + "s",
      hint: "How long a single spoken turn can run before VORIS answers.",
      onChange: (v) => {
        settings.phrase_time_limit = v;
        queueSave({ phrase_time_limit: v });
      },
    }));

    body.appendChild(listening);

    /* ── Images ── */
    const img = (imageStatus && imageStatus.image_generation) || {};
    const provider = String(img.provider || "").toLowerCase();
    const imgAvailable = !!img.available;

    const imgChip = imgAvailable
      ? statusChip("live", provider ? provider : "Live")
      : statusChip("partial", "Pollinations only");

    const images = sectionEl(
      "Images",
      imgChip,
      imgAvailable
        ? "Image requests route to the configured provider."
        : "Image requests are served by Pollinations when your message starts with draw, generate, create or make. No other provider is configured yet."
    );

    images.appendChild(selectRow({
      label: "Size",
      value: localStorage.getItem("voris-image-size") || "1024x1024",
      options: [
        { value: "1024x1024", label: "Square · 1024" },
        { value: "1280x720", label: "Wide · 1280×720" },
        { value: "720x1280", label: "Tall · 720×1280" },
      ],
      onChange: (v) => {
        localStorage.setItem("voris-image-size", v);
        savedNote.className = "vs-saved is-ok";
        savedNote.textContent = "Saved";
      },
      hint: "Applies to new image requests from this browser.",
    }));

    images.appendChild(
      el("div", { class: "vs-row" }, [
        el("span", { class: "vs-row__label", text: "Try it" }),
        el("button", {
          class: "vs-btn",
          type: "button",
          text: "Draw something",
          onclick: () => {
            const field = document.getElementById("messageInput");
            if (!field) return;
            field.value = "draw a picture of a quiet observatory at night";
            field.dispatchEvent(new Event("input", { bubbles: true }));
            close();
            field.focus();
          },
        }),
      ])
    );

    body.appendChild(images);
  }

  /* ───────────────────────────── open / close ───────────────────────────── */

  let lastFocus = null;

  async function open() {
    lastFocus = document.activeElement;
    drawer.hidden = false;
    requestAnimationFrame(() => {
      scrim.classList.add("is-open");
      drawer.classList.add("is-open");
      closeBtn.focus();
    });

    const [vs, personasRes, imgRes] = await Promise.all([
      getJSON("/api/voice/status"),
      getJSON("/api/voice/personas"),
      getJSON("/api/image/status"),
    ]);
    voiceStatus = vs || {};
    settings = (vs && vs.settings) || {};
    /* /api/voice/status reports a narrow settings view; fill the rest from
       the profile it returns so sliders start at the real stored values. */
    const profile = (vs && vs.user_profile) || {};
    settings.profile_id = settings.profile_id || profile.voice_profile || "jarvis";
    settings.rate = settings.rate ?? profile.voice_rate;
    settings.pitch = settings.pitch ?? profile.voice_pitch;
    settings.volume = settings.volume ?? profile.voice_volume;

    render((personasRes && personasRes.personas) || [], imgRes);
  }

  function close() {
    scrim.classList.remove("is-open");
    drawer.classList.remove("is-open");
    setTimeout(() => { drawer.hidden = true; }, 320);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  closeBtn.addEventListener("click", close);
  scrim.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !drawer.hidden) close();
  });

  /* keep Tab inside the drawer while it is open */
  drawer.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const items = drawer.querySelectorAll(
      "button:not([disabled]), select:not([disabled]), input:not([disabled])"
    );
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  });

  /* ───────────────────────────── mount ───────────────────────────── */

  function mount() {
    document.body.appendChild(scrim);
    document.body.appendChild(drawer);

    const footer = document.querySelector(".sidebar__footer");
    if (footer) {
      const link = el("a", {
        class: "sidebar__link vs-open-link",
        text: "Settings",
        role: "button",
        tabindex: "0",
        onclick: (e) => { e.preventDefault(); open(); },
        onkeydown: (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
        },
      });
      footer.insertBefore(link, footer.firstChild);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }

  window.VORIS_SETTINGS = { open, close };
})();
