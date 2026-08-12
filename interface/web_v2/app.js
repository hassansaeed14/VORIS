(function () {
  const LEGACY_STORAGE_KEYS = {
    sessionId: "aura-v2-session-id",
    sessionTitles: "aura-v2-session-titles",
    speechEnabled: "aura-v2-speech-enabled",
  };
  const STORAGE_KEYS = {
    sessionId: "voris-v2-session-id",
    sessionTitles: "voris-v2-session-titles",
    speechEnabled: "voris-v2-speech-enabled",
  };

  const WAKE_FALLBACK = "Hey VORIS";
  for (const [key, storageKey] of Object.entries(STORAGE_KEYS)) {
    const legacyKey = LEGACY_STORAGE_KEYS[key];
    if (legacyKey && localStorage.getItem(storageKey) === null && localStorage.getItem(legacyKey) !== null) {
      localStorage.setItem(storageKey, localStorage.getItem(legacyKey));
    }
  }
  const DEBUG_LOGS = localStorage.getItem("voris.debug") === "true" || localStorage.getItem("aura.debug") === "true";
  const ICONS = {
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"></path></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"></path></svg>',
    speaker: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10v4h4l5 4V6L8 10H4z"></path><path d="M16 9a4 4 0 0 1 0 6"></path><path d="M18.5 6.5a8 8 0 0 1 0 11"></path></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="1.5"></rect></svg>',
  };
  const STATE_COPY = {
    idle: {
      label: "Idle",
      sidebar: "Calm and ready",
      orb: "Calm presence",
    },
    listening: {
      label: "Listening",
      sidebar: "Listening closely",
      orb: "Wake focus",
    },
    analyzing: {
      label: "Analyzing",
      sidebar: "Sorting the route",
      orb: "Focused routing",
    },
    thinking: {
      label: "Thinking",
      sidebar: "Working with you",
      orb: "Workspace active",
    },
    responding: {
      label: "Responding",
      sidebar: "Delivering the result",
      orb: "Warm response",
    },
    error: {
      label: "Error",
      sidebar: "Needs a clean retry",
      orb: "Attention required",
    },
  };

  const EXTERNAL_TARGETS = [
    { pattern: /\b(?:open|launch|go to|visit)\s+youtube\b/i, label: "YouTube", type: "web", url: "https://www.youtube.com/" },
    { pattern: /\b(?:open|launch|go to|visit)\s+google\b/i, label: "Google", type: "web", url: "https://www.google.com/" },
    { pattern: /\b(?:open|launch|go to|visit)\s+github\b/i, label: "GitHub", type: "web", url: "https://github.com/" },
    { pattern: /\b(?:open|launch|go to|visit)\s+gmail\b/i, label: "Gmail", type: "web", url: "https://mail.google.com/" },
    { pattern: /\b(?:open|launch|go to|visit)\s+facebook\b/i, label: "Facebook", type: "web", url: "https://www.facebook.com/" },
    { pattern: /\b(?:open|launch|go to|visit)\s+whatsapp\b/i, label: "WhatsApp", type: "web", url: "https://web.whatsapp.com/" },
    { pattern: /\b(?:open|launch|go to|visit)\s+spotify\b/i, label: "Spotify", type: "web", url: "https://open.spotify.com/" },
    { pattern: /\b(?:open|launch)\s+(?:the\s+)?browser\b/i, label: "Browser", type: "web", url: "https://www.google.com/" },
    { pattern: /\b(?:open|launch|start)\s+(?:google chrome|chrome)\b/i, label: "Chrome", type: "desktop" },
    { pattern: /\b(?:open|launch|start)\s+(?:vs\s*code|visual studio code|vscode)\b/i, label: "VS Code", type: "desktop" },
    { pattern: /\b(?:open|launch|start)\s+notepad\b/i, label: "Notepad", type: "desktop" },
    { pattern: /\b(?:open|launch|start)\s+(?:calculator|calc)\b/i, label: "Calculator", type: "desktop" },
  ];

  const CONTROLLED_BROWSER_ACTION_RE = /\b(?:open\s+(?:a\s+)?new\s+(?:browser\s+)?tab|navigate\s+to|go\s+to\s+(?:https?:\/\/|[a-z0-9.-]+\.[a-z]{2,})|visit\s+(?:https?:\/\/|[a-z0-9.-]+\.[a-z]{2,})|re[-\s]?run\s+(?:the\s+)?search|open\s+(?:the\s+)?(?:first|top|next)\s+(?:search\s+)?(?:result|link)|open\s+chrome\s+and\s+(?:search|go\s+to|navigate\s+to|open\s+new\s+tab)|open\s+(?:notepad|vs\s*code|vscode|visual studio code|calculator|calc|chrome)\s+and\s+(?:type|write|enter|press|scroll|focus)|(?:type|write|enter)\s+.+\s+(?:in|into)\s+(?:notepad|vs\s*code|vscode|visual studio code|calculator|calc|chrome)|(?:press|hit|scroll|focus|switch\s+to)\s+(?:.+\s+)?(?:notepad|vs\s*code|vscode|visual studio code|calculator|calc|chrome))\b/i;
  const CRITICAL_DIRECT_CONTROL_RE = /\b(?:type|enter|write)\s+(?:my\s+)?(?:password|otp|pin|credit\s*card|debit\s*card|bank|banking|payment|credentials?)\b/i;
  const SAFE_WEB_ACTION_PLAN_RE = /\bopen\s+(?:youtube|google|chatgpt|facebook|github|chrome)\b.+\band\s+(?:search|ask|tell|go\s+to|navigate|open)\b/i;

  const INTERNAL_HINTS = [
    { pattern: /\b(notes?|assignment|assignments?|essay|report|slides?|presentation|pdf|docx|txt|pptx)\b/i, label: "Document task", kind: "document" },
    { pattern: /\b(code|coding|program|python|javascript|typescript|debug|function|api|build)\b/i, label: "Coding task", kind: "coding" },
    { pattern: /\b(research|compare|comparison|explain|how|why|latest|status|summary|summarize)\b/i, label: "Research task", kind: "research" },
    { pattern: /\b(write|draft|rewrite|improve|email|letter|blog|article)\b/i, label: "Writing task", kind: "writing" },
  ];

  const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;

  const el = {};
  const state = {
    sessionId: "",
    sessionTitles: readSessionTitles(),
    auth: null,
    voiceStatus: null,
    assistantRuntime: null,
    desktopVoiceStatus: null,
    assistantState: "idle",
    assistantStateEvent: "boot:uninitialized",
    orbLayout: "topbar",
    taskScope: "none",
    sessions: [],
    messages: [],
    messageDomById: new Map(),
    recentOutputs: [],
    desktopApps: [],
    sidebarSearch: "",
    panelVisible: false,
    panelMode: "",
    currentTask: null,
    currentExternal: null,
    lastActionTrace: null,
    requestInFlight: false,
    activeChatAbortController: null,
    screenShareActive: false,
    screenShareLabel: "Off",
    screenStream: null,
    voiceSupported: false,
    recognition: null,
    recognitionMode: "",
    recognitionActive: false,
    recognitionStopReason: "",
    speechCommandInFlight: false,
    speechEnabled: readSpeechEnabled(),
    speechSynthesisSupported: Boolean(window.speechSynthesis && window.SpeechSynthesisUtterance),
    speakingMessageId: "",
    speechCancelUntil: 0,
    copiedMessageId: "",
    desktopVoicePollId: 0,
    wakeModeEnabled: false,
    presenceHideTimer: 0,
  };

  function logVoiceDebug(message, details) {
    if (!DEBUG_LOGS) {
      return;
    }
    if (typeof details === "undefined") {
      console.info(`[VORIS voice] ${message}`);
      return;
    }
    console.info(`[VORIS voice] ${message}`, details);
  }

  function logVoiceError(message, details) {
    if (typeof details === "undefined") {
      console.error(`[VORIS voice] ${message}`);
      return;
    }
    console.error(`[VORIS voice] ${message}`, details);
  }

  function logOrbState(stateName, eventName) {
    console.info(`[ORB STATE] ${stateName} triggered by ${eventName}`);
  }

  function pulseOrbClass(className, durationMs = 520) {
    if (!el.assistantOrb) {
      return;
    }
    el.assistantOrb.classList.remove(className);
    void el.assistantOrb.offsetWidth;
    el.assistantOrb.classList.add(className);
    window.setTimeout(() => {
      el.assistantOrb?.classList.remove(className);
    }, durationMs);
  }

  function triggerOrbRipple() {
    pulseOrbClass("assistant-orb--rippling", 560);
  }

  function triggerOrbWake() {
    pulseOrbClass("assistant-orb--wake-active", 1200);
  }

  function triggerOrbStateShift() {
    pulseOrbClass("assistant-orb--state-shift", 420);
  }

  function triggerOrbResponsePulse() {
    pulseOrbClass("assistant-orb--response-pulse", 900);
  }

  document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    bindEvents();
    state.sessionId = ensureSessionId();
    setTaskScope("none");
    setAssistantState("idle", "boot:dom_ready");
    setOrbLayout("topbar");
    hidePresence(true);
    autoResizeTextarea();
    void pingVorisCore();
    void initialize();
  });

  function setCorePingStatus(status) {
    if (!el.corePingStatus || !el.corePingStatusLabel) return;
    const normalized = status === "online" ? "online" : status === "offline" ? "offline" : "checking";
    el.corePingStatus.classList.remove("core-ping-status--checking", "core-ping-status--online", "core-ping-status--offline");
    el.corePingStatus.classList.add(`core-ping-status--${normalized}`);
    el.corePingStatusLabel.textContent = normalized === "online"
      ? "VORIS Core: Online"
      : normalized === "offline"
        ? "Core: Offline"
        : "Core: Checking";
  }

  async function pingVorisCore() {
    setCorePingStatus("checking");
    const candidates = [
      "/ping",
      "http://localhost:8000/ping",
      "http://127.0.0.1:8000/ping",
      "http://localhost:5000/ping",
      "http://127.0.0.1:5000/ping",
    ];

    for (const url of candidates) {
      try {
        const response = await fetch(url, {
          method: "GET",
          cache: "no-store",
          headers: { "Accept": "application/json" },
        });
        if (!response.ok) continue;
        const payload = await response.json().catch(() => ({}));
        if (String(payload.status || "").toLowerCase() === "online") {
          setCorePingStatus("online");
          return;
        }
      } catch (_error) {
        // Try the next known local development port.
      }
    }
    setCorePingStatus("offline");
  }

  async function initialize() {
    await Promise.allSettled([
      refreshAuthSession(),
      loadAssistantRuntime(),
      loadVoiceStatus(),
      refreshDesktopApps(),
    ]);
    if (state.auth?.authenticated) {
      await loadSessions();
    } else {
      state.sessions = [];
    }
    syncVoiceControls();
    syncAssistantModeChrome();
    logVoiceDebug("Voice support check", {
      speechRecognition: Boolean(window.SpeechRecognition),
      webkitSpeechRecognition: Boolean(window.webkitSpeechRecognition),
      recognitionCtor: Boolean(RecognitionCtor),
      secureContext: window.isSecureContext,
      talkButtonPresent: Boolean(el.talkButton),
      wakeButtonPresent: Boolean(el.wakeButton),
      voiceSupported: state.voiceSupported,
    });
    await loadConversation(state.sessionId);
    renderSidebarSessions();
    renderConversation();
    renderRightPanel();
    updateWorkspaceChrome();
  }

  async function refreshDesktopApps() {
    try {
      const payload = await apiJson("/api/desktop/apps", { method: "GET" });
      state.desktopApps = Array.isArray(payload.apps) ? payload.apps : [];
    } catch (_error) {
      state.desktopApps = [];
    }
  }

  function cacheElements() {
    Object.assign(el, {
      body: document.body,
      assistantOrb: document.getElementById("assistantOrb"),
      orbStateLabel: document.getElementById("orbStateLabel"),
      orbModeLabel: document.getElementById("orbModeLabel"),
      presenceStage: document.getElementById("presenceStage"),
      presenceEyebrow: document.getElementById("presenceEyebrow"),
      presenceTitle: document.getElementById("presenceTitle"),
      presenceText: document.getElementById("presenceText"),
      sidebarState: document.getElementById("sidebarState"),
      newChatButton: document.getElementById("newChatButton"),
      chatSearch: document.getElementById("chatSearch"),
      chatList: document.getElementById("chatList"),
      chatListEmpty: document.getElementById("chatListEmpty"),
      historyMeta: document.getElementById("historyMeta"),
      profileButton: document.getElementById("profileButton"),
      profileEntryName: document.getElementById("profileEntryName"),
      profileEntryStatus: document.getElementById("profileEntryStatus"),
      accessChip: document.getElementById("accessChip"),
      corePingStatus: document.getElementById("corePingStatus"),
      corePingStatusLabel: document.getElementById("corePingStatusLabel"),
      stateChipLabel: document.getElementById("stateChipLabel"),
      assistantModeLabel: document.getElementById("assistantModeLabel"),
      voiceRuntimeLabel: document.getElementById("voiceRuntimeLabel"),
      workspaceSummary: document.getElementById("workspaceSummary"),
      screenChipLabel: document.getElementById("screenChipLabel"),
      conversationThread: document.getElementById("conversationThread"),
      chatScroll: document.getElementById("chatScroll"),
      composerForm: document.getElementById("composerForm"),
      messageInput: document.getElementById("messageInput"),
      composerStatus: document.getElementById("composerStatus"),
      voiceTranscript: document.getElementById("voiceTranscript"),
      composerMicButtons: [],
      screenShareButton: document.getElementById("screenShareButton"),
      talkButton: document.getElementById("talkButton"),
      speechToggleButton: document.getElementById("speechToggleButton"),
      desktopVoiceButton: document.getElementById("desktopVoiceButton"),
      wakeButton: document.getElementById("wakeButton"),
      interruptButton: document.getElementById("interruptButton"),
      uploadButton: document.getElementById("uploadButton"),
      fileUploadInput: document.getElementById("file-upload-input"),
      sendButton: document.getElementById("sendButton"),
      rightPanel: document.getElementById("rightPanel"),
      rightPanelTitle: document.getElementById("rightPanelTitle"),
      rightPanelBody: document.getElementById("rightPanelBody"),
      panelCloseButton: document.getElementById("panelCloseButton"),
    });
    ensureComposerMicButtons();
  }

  function ensureComposerMicButtons() {
    const rows = Array.from(document.querySelectorAll(".composer__main-input-row"));
    const micSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path><path d="M19 10v1a7 7 0 0 1-14 0v-1"></path><path d="M12 19v3"></path></svg>';
    const buttons = [];

    rows.forEach((row, index) => {
      const sendButton = row.querySelector(".send-button, #sendButton");
      let button = row.querySelector(".composer-mic-button");
      if (!button) {
        button = row.querySelector(".mic-visual-btn[aria-label*='Voice'], .mic-visual-btn[aria-label*='voice']");
      }
      if (!button) {
        button = document.createElement("button");
        button.innerHTML = micSvg;
      }

      button.type = "button";
      button.removeAttribute("onclick");
      button.classList.add("composer-mic-button", "mic-visual-btn");
      button.setAttribute("aria-label", "Start voice input");
      button.setAttribute("title", "Start voice input");
      if (index === 0) {
        button.id = "composerMicButton";
      } else {
        button.removeAttribute("id");
      }
      if (!button.querySelector("svg")) {
        button.innerHTML = micSvg;
      }
      if (sendButton && button.nextElementSibling !== sendButton) {
        row.insertBefore(button, sendButton);
      } else if (!sendButton && button.parentElement !== row) {
        row.appendChild(button);
      }
      buttons.push(button);
    });

    el.composerMicButtons = buttons;
  }

  function bindEvents() {
    el.newChatButton?.addEventListener("click", startNewChat);
    el.chatSearch?.addEventListener("input", () => {
      state.sidebarSearch = String(el.chatSearch.value || "").trim().toLowerCase();
      renderSidebarSessions();
    });
    el.profileButton?.addEventListener("click", async () => {
      state.panelVisible = true;
      state.panelMode = "profile";
      renderRightPanel();
      await refreshDesktopApps();
      if (state.panelMode === "profile") {
        renderRightPanel();
      }
    });
    el.panelCloseButton?.addEventListener("click", () => {
      state.panelVisible = false;
      state.panelMode = "";
      renderRightPanel();
    });
    el.composerForm?.addEventListener("submit", handleComposerSubmit);
    el.messageInput?.addEventListener("input", autoResizeTextarea);
    el.messageInput?.addEventListener("keydown", handleComposerKeydown);
    el.uploadButton?.addEventListener("click", () => {
      el.fileUploadInput?.click();
    });
    el.assistantOrb?.addEventListener("click", handleOrbActivation);
    el.assistantOrb?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handleOrbActivation();
      }
    });
    el.speechToggleButton?.addEventListener("click", toggleSpeechEnabled);
    el.desktopVoiceButton?.addEventListener("click", () => {
      void toggleDesktopVoice();
    });
    if (el.talkButton) {
      logVoiceDebug("Talk button bound", {
        id: el.talkButton.id,
        hidden: el.talkButton.hidden,
      });
    } else {
      logVoiceError("Talk button missing");
    }
    el.talkButton?.addEventListener("click", () => {
      handleVoiceInputButtonClick();
    });
    (el.composerMicButtons || []).forEach((button) => {
      button.addEventListener("click", handleVoiceInputButtonClick);
    });

    if (el.interruptButton) {
      logVoiceDebug("Interrupt button bound", { id: el.interruptButton.id });
    } else {
      logVoiceError("Interrupt button missing from DOM");
    }
    el.interruptButton?.addEventListener("click", () => {
      handleInterrupt();
    });
  }

  function handleVoiceInputButtonClick() {
    logVoiceDebug("Voice input button click", {
      voiceSupported: state.voiceSupported,
      recognitionCtor: Boolean(RecognitionCtor),
      recognitionActive: state.recognitionActive,
      recognitionMode: state.recognitionMode,
    });
    if (state.recognitionActive && state.recognitionMode === "talk") {
      stopRecognition("Listening stopped.");
      return;
    }
    void startSpeechCapture("talk");
  }

  async function handleInterrupt() {
    if (state.activeChatAbortController) {
      state.activeChatAbortController.abort();
      state.activeChatAbortController = null;
    }
    if (state.recognitionActive) {
      stopRecognition("Listening stopped.");
    }
    if (state.speakingMessageId || window.speechSynthesis?.speaking) {
      stopSpeaking("user:interrupt");
    }
    if (state.desktopVoiceStatus?.active) {
      await interruptDesktopVoice();
    }
    if (el.interruptButton) {
      el.interruptButton.hidden = true;
    }
    if (!state.requestInFlight) {
      setAssistantState("idle", "user:interrupt_completed");
      setComposerStatus("Stopped. Ready when you are.");
      settleToIdleLayout();
    } else {
      setComposerStatus("Stopping the current response.");
    }
  }

  function clearPresenceTimer() {
    if (state.presenceHideTimer) {
      window.clearTimeout(state.presenceHideTimer);
      state.presenceHideTimer = 0;
    }
  }

  function setTaskScope(scope) {
    const nextScope = scope || "none";
    state.taskScope = nextScope;
    if (el.body) {
      el.body.dataset.taskScope = nextScope;
    }
  }

  function normalizeActionTrace(payload) {
    const trace = payload && typeof payload.action_trace === "object" ? payload.action_trace : null;
    if (!trace) {
      return null;
    }
    return {
      requestId: String(trace.request_id || "").trim(),
      intent: String(trace.intent || "general").trim(),
      responseMode: String(trace.response_mode || "assistant").trim(),
      finalStatus: String(trace.final_status || "ok").trim(),
      permissionState: trace.permission_state || {},
      automationState: trace.automation_state || {},
    };
  }

  function syncRuntimeStateFromPayload(payload, fallbackEvent = "runtime:trace_sync") {
    const trace = normalizeActionTrace(payload);
    if (trace) {
      state.lastActionTrace = trace;
    }
    const runtimeState = payload && typeof payload.runtime_state === "object" ? payload.runtime_state : null;
    if (!runtimeState || state.recognitionActive) {
      return trace;
    }

    const nextScope = String(runtimeState.task_scope || "").trim();
    const nextLayout = String(runtimeState.orb_layout || "").trim();
    const nextState = String(runtimeState.assistant_state || "").trim();
    if (nextScope) {
      setTaskScope(nextScope);
    }
    if (nextLayout) {
      setOrbLayout(nextLayout);
    }
    if (nextState && nextState !== state.assistantState) {
      setAssistantState(nextState, fallbackEvent);
    }
    return trace;
  }

  function resetToCalmIdle(delayMs = 1100) {
    window.setTimeout(() => {
      if (!state.requestInFlight && !state.recognitionActive && !state.speechCommandInFlight) {
        setAssistantState("idle", "lifecycle:calm_idle_timeout");
        settleToIdleLayout();
      }
    }, delayMs);
  }

  function clearVoiceTranscript() {
    if (!el.voiceTranscript) {
      return;
    }
    el.voiceTranscript.hidden = true;
    el.voiceTranscript.dataset.final = "false";
    el.voiceTranscript.textContent = "";
  }

  function updateVoiceTranscript(text, options = {}) {
    if (!el.voiceTranscript) {
      return;
    }
    const cleanText = String(text || "").trim();
    if (!cleanText) {
      clearVoiceTranscript();
      return;
    }
    el.voiceTranscript.hidden = false;
    el.voiceTranscript.dataset.final = options.final ? "true" : "false";
    el.voiceTranscript.textContent = `${options.final ? "Heard" : "Listening"}: ${cleanText}`;
  }

  function hidePresence(immediate) {
    if (!el.presenceStage) {
      return;
    }

    clearPresenceTimer();
    const resetClasses = () => {
      el.presenceStage.classList.remove(
        "is-visible",
        "presence-stage--center",
        "presence-stage--docked",
        "presence-stage--floating",
      );
    };

    if (immediate) {
      resetClasses();
      el.presenceStage.hidden = true;
      return;
    }

    el.presenceStage.classList.remove("is-visible");
    window.setTimeout(() => {
      if (!el.presenceStage.classList.contains("is-visible")) {
        resetClasses();
        el.presenceStage.hidden = true;
      }
    }, 280);
  }

  function showPresence(options = {}) {
    if (!el.presenceStage || !el.presenceEyebrow || !el.presenceTitle || !el.presenceText) {
      return;
    }

    clearPresenceTimer();
    const mode = options.mode || "center";
    el.presenceEyebrow.textContent = options.eyebrow || "VORIS presence";
    el.presenceTitle.textContent = options.title || "VORIS is here.";
    el.presenceText.textContent = options.text || "Calm, present, and ready when you are.";
    el.presenceStage.hidden = false;
    el.presenceStage.classList.remove(
      "is-visible",
      "presence-stage--center",
      "presence-stage--docked",
      "presence-stage--floating",
    );
    el.presenceStage.classList.add(`presence-stage--${mode}`);
    window.requestAnimationFrame(() => {
      el.presenceStage.classList.add("is-visible");
    });

    if (options.duration) {
      state.presenceHideTimer = window.setTimeout(() => {
        hidePresence();
      }, options.duration);
    }
  }

  async function refreshAuthSession() {
    try {
      state.auth = await apiJson("/api/auth/session", { method: "GET" });
    } catch (_error) {
      state.auth = {
        authenticated: false,
        access_mode: "public",
        status: "error",
      };
    }
  }

  async function loadVoiceStatus() {
    try {
      state.voiceStatus = await apiJson("/api/voice/status", { method: "GET" });
    } catch (_error) {
      state.voiceStatus = null;
    }
  }

  async function loadAssistantRuntime() {
    try {
      state.assistantRuntime = await apiJson("/api/assistant/runtime", { method: "GET" });
      state.desktopVoiceStatus = state.assistantRuntime?.voice_runtime
        || state.assistantRuntime?.modes?.desktop_voice
        || null;
    } catch (_error) {
      state.assistantRuntime = null;
      state.desktopVoiceStatus = null;
    }
    syncDesktopVoicePolling();
  }

  async function getMicrophonePermissionState() {
    if (!navigator.permissions || !navigator.permissions.query) {
      return "prompt";
    }
    try {
      const result = await navigator.permissions.query({ name: "microphone" });
      return String(result?.state || "prompt");
    } catch (_error) {
      return "prompt";
    }
  }

  function syncVoiceControls() {
    state.voiceSupported = Boolean(
      RecognitionCtor
      && (window.isSecureContext || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"),
    );

    if (!el.talkButton) {
      return;
    }
    const desktopActive = Boolean(state.desktopVoiceStatus?.active);
    const chatStreaming = Boolean(state.requestInFlight && state.activeChatAbortController);
    const composerMicButtons = Array.isArray(el.composerMicButtons) ? el.composerMicButtons : [];

    if (state.voiceSupported) {
      el.talkButton.hidden = false;
      el.talkButton.classList.toggle("is-active", state.recognitionActive && state.recognitionMode === "talk");
      composerMicButtons.forEach((button) => {
        button.hidden = false;
        button.disabled = Boolean(state.requestInFlight);
        button.classList.toggle("is-active", state.recognitionActive && state.recognitionMode === "talk");
        button.setAttribute("aria-pressed", state.recognitionActive && state.recognitionMode === "talk" ? "true" : "false");
        button.setAttribute(
          "aria-label",
          state.recognitionActive && state.recognitionMode === "talk" ? "Stop voice input" : "Start voice input",
        );
        button.title = state.recognitionActive && state.recognitionMode === "talk"
          ? "Stop voice input"
          : "Start voice input";
      });
      if (el.wakeButton) {
        el.wakeButton.hidden = true;
        el.wakeButton.classList.remove("is-active");
      }
      if (el.interruptButton) {
        el.interruptButton.hidden = !state.recognitionActive && !state.speakingMessageId && !desktopActive && !chatStreaming;
        el.interruptButton.classList.toggle("is-active", state.recognitionActive || Boolean(state.speakingMessageId) || desktopActive || chatStreaming);
      }
      syncAssistantModeChrome();
      return;
    }

    el.talkButton.hidden = true;
    composerMicButtons.forEach((button) => {
      button.hidden = false;
      button.disabled = true;
      button.classList.remove("is-active");
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", "Voice input unavailable");
      button.title = "Voice input is not available in this browser or context";
    });
    if (el.wakeButton) {
      el.wakeButton.hidden = true;
      el.wakeButton.classList.remove("is-active");
    }
    el.talkButton.classList.remove("is-active");
    if (el.interruptButton) {
      el.interruptButton.hidden = !state.speakingMessageId && !desktopActive && !chatStreaming;
    }
    syncAssistantModeChrome();
  }

  function syncAssistantModeChrome() {
    const desktopVoice = state.desktopVoiceStatus
      || state.assistantRuntime?.voice_runtime
      || state.assistantRuntime?.modes?.desktop_voice
      || {};
    const desktopStateLabel = desktopVoice.active
      ? desktopVoice.processing
        ? "Desktop voice processing"
        : desktopVoice.speaking
          ? "Desktop voice speaking"
          : desktopVoice.awake
            ? "Desktop voice awake"
            : desktopVoice.listening
              ? 'Listening for "Hey VORIS"'
              : "Desktop voice active"
      : desktopVoice.available === false
        ? "Desktop voice unavailable"
        : "Desktop voice inactive";
    const currentMode = state.recognitionActive
      ? "Push-to-talk"
      : desktopVoice.active
        ? "Desktop voice"
      : state.speakingMessageId
        ? "Speaking"
        : "Text mode";
    if (el.assistantModeLabel) {
      el.assistantModeLabel.textContent = currentMode;
    }
    if (el.voiceRuntimeLabel) {
      const message = String(desktopVoice.message || "Desktop voice runtime is not active.").trim();
      el.voiceRuntimeLabel.textContent = desktopVoice.active ? desktopStateLabel : message;
    }
    if (el.speechToggleButton) {
      el.speechToggleButton.hidden = !state.speechSynthesisSupported;
      el.speechToggleButton.classList.toggle("is-active", state.speechEnabled);
      el.speechToggleButton.setAttribute("aria-pressed", state.speechEnabled ? "true" : "false");
      const label = el.speechToggleButton.querySelector(".tool-button__label") || el.speechToggleButton;
      label.textContent = state.speechEnabled ? "Speech on" : "Speech off";
    }
    if (el.desktopVoiceButton) {
      const unavailable = desktopVoice.available === false;
      el.desktopVoiceButton.disabled = Boolean(unavailable);
      el.desktopVoiceButton.classList.toggle("is-active", Boolean(desktopVoice.active));
      el.desktopVoiceButton.setAttribute("aria-pressed", desktopVoice.active ? "true" : "false");
      const desktopLabel = el.desktopVoiceButton.querySelector(".tool-button__label") || el.desktopVoiceButton;
      desktopLabel.textContent = unavailable
        ? "Desktop voice unavailable"
        : desktopVoice.active
          ? "Stop desktop voice"
          : "Enable desktop voice";
      el.desktopVoiceButton.title = String(desktopVoice.message || desktopStateLabel);
    }
  }

  async function loadSessions() {
    if (!state.auth?.authenticated) {
      state.sessions = [];
      return;
    }
    try {
      const payload = await apiJson("/api/sessions", { method: "GET" });
      state.sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
    } catch (_error) {
      state.sessions = [];
    }
  }

  async function loadConversation(sessionId) {
    if (!state.auth?.authenticated) {
      state.messages = [];
      return;
    }
    try {
      const payload = await apiJson(`/api/history?session_id=${encodeURIComponent(sessionId)}&limit=80`, { method: "GET" });
      state.messages = (Array.isArray(payload.messages) ? payload.messages : []).map(normalizeHistoryMessage);
      const title = deriveSessionTitle(state.messages);
      if (title) {
        state.sessionTitles[sessionId] = title;
        persistSessionTitles();
      }
    } catch (_error) {
      state.messages = [];
    }
  }

 async function handleComposerSubmit(event) {
    event.preventDefault();
    if (state.requestInFlight) return;

    const rawText = String(el.messageInput?.value || "").trim();
    const hasFile = window.vorisAttachedFile !== null && window.vorisAttachedFile !== undefined;

    if (!rawText && !hasFile) return;

    state.requestInFlight = true;
    el.messageInput.value = "";
    autoResizeTextarea();

    let fileName = null;
    let filePayload = null;
    let attachmentUIHtml = "";

    try {
        if (hasFile) {
          const file = window.vorisAttachedFile;
          fileName = file.name;

          // BULLETPROOF IMAGE CHECK: Looks at file type AND extension
          const isImage = (file.type && file.type.startsWith("image/")) || (fileName && fileName.match(/\.(jpg|jpeg|png|webp|gif)$/i));

          if (isImage) {
              // PROCESS AS IMAGE (Base64 URL)
              const base64Data = await new Promise((resolve, reject) => {
                  const reader = new FileReader();
                  reader.onload = () => resolve(reader.result);
                  reader.onerror = error => reject(error);
                  reader.readAsDataURL(file); // Critical: Reads as URL, not text!
              });
              filePayload = { type: "image", name: fileName, data: base64Data };
          } else {
              // PROCESS AS TEXT (CSV/TXT)
              let fileTextContext = await new Promise((resolve, reject) => {
                  const reader = new FileReader();
                  reader.onload = () => resolve(reader.result);
                  reader.onerror = error => reject(error);
                  reader.readAsText(file);
              });

              const maxChars = 2000;
              if (fileTextContext.length > maxChars) {
                  fileTextContext = fileTextContext.substring(0, maxChars) + "\n\n... [WARNING: FILE TRUNCATED TO SAVE MEMORY. SHOWING FIRST FEW ROWS ONLY.]";
              }
              filePayload = { type: "text", name: fileName, data: fileTextContext };
          }

          // Clear UI
          window.vorisAttachedFile = null;
          const fileInputHtml = document.getElementById("file-upload-input");
          if (fileInputHtml) fileInputHtml.value = "";
          const previewChip = document.getElementById("voris-file-preview");
          if (previewChip) previewChip.remove();

          attachmentUIHtml = `\n\n📎 [Attached: ${fileName}]`;
        }

        const userMessage = appendMessage({
          role: "user",
          text: rawText + attachmentUIHtml,
          badge: "You",
          timestamp: new Date().toISOString(),
        });
        void userMessage;
        
        rememberSessionTitle(rawText || "Sent an attachment");

        let commandText = rawText;
        const wakeMatch = detectWakePhrase(commandText);
        if (wakeMatch.detected && commandText) {
          await runWakeSequence();
          if (!wakeMatch.remainingText) {
            await delay(1600);
            settleToIdleLayout();
            state.requestInFlight = false;
            return;
          }
          commandText = wakeMatch.remainingText;
        }

        const classification = classifyCommand(commandText);

        // STITCH THE PAYLOAD TOGETHER BASED ON FILE TYPE
       // STITCH THE PAYLOAD TOGETHER BASED ON FILE TYPE
        let finalPayloadText = commandText;
        if (hasFile) {
            if (filePayload.type === "text") {
                finalPayloadText = `${commandText}\n\n--- ATTACHED FILE CONTEXT: ${fileName} ---\n${filePayload.data}\n--- END OF FILE ---`;
            } else if (filePayload.type === "image") {
                // Indestructible text tags instead of fragile JSON
                finalPayloadText = `[VISION_PROMPT]${commandText || "Describe this image."}[/VISION_PROMPT][VISION_URL]${filePayload.data}[/VISION_URL]`;
            }
        }

        setAssistantState("analyzing", "chat:input_received");
        setComposerStatus(hasFile ? "Reading your attachment..." : "I hear you. Let me route that.");
        updateWorkspaceSummary("Routing request.");
        await delay(120);

        if (classification.kind === "external" && !hasFile) {
          await handleExternalCommand(finalPayloadText, classification);
        } else {
          await handleInternalCommand(finalPayloadText, classification);
        }
        
    } catch (error) {
        console.error("Error in submit:", error);
        state.requestInFlight = false;
    }
  }

  async function runWakeSequence() {
    triggerOrbWake();
    setOrbLayout("center");
    setAssistantState("listening", "wake:sequence_started");
    showPresence({
      mode: "center",
      eyebrow: "Wake phrase detected",
      title: buildWakeGreeting(),
      text: "I'm with you now. Tell me what you want handled next.",
    });
    setComposerStatus(buildWakeGreeting());
    updateWorkspaceSummary("VORIS is awake, present, and listening for the next step.");
    await delay(220);
    setAssistantState("responding", "wake:greeting_ready");
    await revealAssistantMessage({
      role: "assistant",
      text: buildWakeGreeting(),
      badge: "Wake",
      timestamp: new Date().toISOString(),
    }, {
      delayMs: 220,
      stateName: "responding",
      event: "wake:greeting_revealed",
    });
    showPresence({
      mode: "center",
      eyebrow: "VORIS awake",
      title: buildWakeGreeting(),
      text: "Tell me what you want handled next.",
      duration: 1800,
    });
    renderRightPanel();
  }

  async function handleInternalCommand(commandText, classification) {
    state.requestInFlight = true;
    state.currentExternal = null;
    setTaskScope("internal");
    state.currentTask = {
      scope: "internal",
      label: classification.label,
      kind: classification.taskKind,
      text: commandText,
    };
    state.panelVisible = false;
    state.panelMode = "";
    setOrbLayout("left");
    setAssistantState("thinking", "api:request_started");
    setComposerStatus("Working on that now.");
    updateWorkspaceSummary("I can handle that inside VORIS, so the workspace is staying focused.");
    showPresence({
      mode: "docked",
      eyebrow: "Workspace mode",
      title: "Working on that now.",
      text: "I can handle that inside VORIS and keep the work close at hand.",
      duration: 1700,
    });
    renderRightPanel();

    try {
      const { payload, message: streamedMessage } = await requestChatPayload(commandText, classification);

      const delivery = normalizeDocumentDeliveryPayload(payload);
      const actionPlan = normalizeActionPlanPayload(payload);
      const actionSuggestions = normalizeActionSuggestions(payload);
      const actionTrace = syncRuntimeStateFromPayload(payload, "api:trace_received");
      const imageUrl = String(payload.image_url || "").trim();
      const isImageBypass = payload.execution_mode === "image_bypass" || Boolean(imageUrl);
      const replyText = isImageBypass
        ? ""
        : cleanAssistantReply(payload.reply || payload.content) || "Done.";
      if (actionPlan) {
        state.currentTask = {
          scope: "external",
          label: "Controlled browser action",
          kind: "action_plan",
          text: commandText,
          actionPlan,
          actionSuggestions,
          launchStatus: payload.action_status || actionPlan.status,
          launchMessage: replyText,
        };
        state.currentExternal = { type: "browser", label: "Browser action" };
        setTaskScope("external");
        setOrbLayout("floating");
        state.panelVisible = true;
        state.panelMode = "context";
      }
      const finalMessage = {
        role: "assistant",
        text: replyText,
        imageUrl: imageUrl || undefined,
        executionMode: payload.execution_mode || undefined,
        badge: humanizeBadge(payload.execution_mode || (actionPlan ? "action_plan" : classification.taskKind) || "Assistant"),
        timestamp: new Date().toISOString(),
        delivery,
        actionPlan,
        actionSuggestions,
        actionTrace,
      };
      if (streamedMessage) {
        Object.assign(streamedMessage, finalMessage, {
          id: streamedMessage.id,
          streaming: false,
          effect: "response",
        });
        setAssistantState("responding", "api:response_ready");
        refreshMessageRow(streamedMessage);
        applyMessageEffect(streamedMessage);
        scrollConversationToBottom();
        triggerOrbResponsePulse();
        maybeSpeakAssistantMessage(streamedMessage);
      } else {
        await revealAssistantMessage(finalMessage, {
          stateName: "responding",
          event: "api:response_ready",
        });
      }

      if (delivery) {
        state.recentOutputs = [delivery, ...state.recentOutputs.filter((item) => item.downloadUrl !== delivery.downloadUrl)].slice(0, 6);
        state.panelVisible = true;
        state.panelMode = "outputs";
      }

      setComposerStatus(delivery
        ? "Done. I've prepared it."
        : payload.degraded
          ? "Limited response, but I still got you the best available result."
          : "Done. I've handled that inside VORIS.");
      updateWorkspaceSummary(delivery
        ? `${capitalize(delivery.documentType)} ready with a preview and direct downloads.`
        : actionPlan
          ? "VORIS ran the controlled browser action plan and exposed each step clearly."
          : payload.degraded
          ? "VORIS stayed inside the workspace and used the safest limited path."
          : "VORIS handled the work inside the workspace.");
      showPresence({
        mode: actionPlan ? "floating" : "docked",
        eyebrow: actionPlan ? "Controlled browser action" : delivery ? "Work completed" : payload.degraded ? "Limited response" : "Work completed",
        title: delivery
          ? "Done. I've prepared it."
          : actionPlan
            ? "Action plan complete."
          : payload.degraded
            ? "Limited response."
            : "Done. I've handled that inside VORIS.",
        text: delivery
          ? `Your ${delivery.documentType} is ready below with direct downloads and a preview.`
          : actionPlan
            ? "The browser action plan is shown below with exact step statuses."
            : payload.degraded
            ? "I used the safest available path and kept the work inside VORIS."
            : "The result is ready here in the workspace.",
        duration: 2200,
      });
      await loadSessions();
      renderSidebarSessions();
      renderRightPanel();
    } catch (error) {
      if (error?.name === "AbortError") {
        setAssistantState("idle", "api:stream_aborted");
        setComposerStatus("Stopped. Ready when you are.");
        updateWorkspaceSummary("VORIS stopped the response cleanly.");
        return;
      }
      setAssistantState("error", "api:request_failed");
      setComposerStatus("I couldn't complete that yet.");
      updateWorkspaceSummary("That task did not finish cleanly inside VORIS.");
      showPresence({
        mode: "docked",
        eyebrow: "Need a retry",
        title: "I couldn't complete that yet.",
        text: "Please try again in a moment.",
        duration: 2200,
      });
      await revealAssistantMessage({
        role: "assistant",
        text: error.message || "Something went wrong while processing that request.",
        badge: "Error",
        timestamp: new Date().toISOString(),
      }, {
        delayMs: 220,
        stateName: "error",
        event: "api:error_revealed",
      });
    } finally {
      state.requestInFlight = false;
      state.activeChatAbortController = null;
      syncVoiceControls();
      renderRightPanel();
      resetToCalmIdle();
    }
  }

  async function handleExternalCommand(commandText, classification) {
    const externalModeLabel = classification.type === "browser-action"
      ? "Controlled action"
      : classification.type === "os-automation"
        ? "Controlled OS automation"
        : "Desktop control";
    setTaskScope("external");
    state.currentTask = {
      scope: "external",
      label: classification.label,
      kind: classification.taskKind,
      text: commandText,
    };
    state.currentExternal = classification;
    const shouldShowExternalPanel = classification.type !== "web";
    state.panelVisible = shouldShowExternalPanel;
    state.panelMode = shouldShowExternalPanel ? "context" : "";
    setOrbLayout("floating");
    setAssistantState("analyzing", "external:routing_started");
    setComposerStatus("Let me route that outside VORIS.");
    updateWorkspaceSummary("VORIS is routing this outside the workspace while staying present.");

    let replyText = "";
    let actionTrace = null;
    if (classification.type === "web" && classification.url) {
      const popup = window.open(classification.url, "_blank");
      if (popup) {
        try {
          popup.opener = null;
        } catch (_error) {
          // Ignore cross-window restrictions after launch.
        }
      }
      if (popup) {
        replyText = `Opening ${classification.label} for you. VORIS will stay here as your assistant presence.`;
        setAssistantState("responding", "external:launch_succeeded");
        setComposerStatus("Opening that for you.");
        updateWorkspaceSummary(`${classification.label} is opening outside VORIS while the assistant stays nearby.`);
        showPresence({
          mode: "floating",
          eyebrow: "External action",
          title: "Opening that for you.",
          text: `${classification.label} is moving outside VORIS while I stay present here.`,
          duration: 2200,
        });
      } else {
        replyText = `I couldn't open ${classification.label} because the browser blocked the new tab. Allow popups for this site and try again.`;
        setAssistantState("error", "external:popup_blocked");
        setComposerStatus("The browser blocked that new tab.");
        updateWorkspaceSummary(`${classification.label} could not open because the browser blocked it.`);
        showPresence({
          mode: "floating",
          eyebrow: "Browser blocked",
          title: "I couldn't complete that yet.",
          text: `Allow popups for this site, then try ${classification.label} again.`,
          duration: 2400,
        });
      }
    } else {
      state.requestInFlight = true;
      setComposerStatus("Opening that for you.");
      updateWorkspaceSummary("VORIS is asking the desktop controller to launch this outside the workspace.");
      showPresence({
        mode: "floating",
        eyebrow: externalModeLabel,
        title: "Opening that for you.",
        text: `${classification.label} is being launched through the VORIS backend.`,
        duration: 2200,
      });
      renderRightPanel();

      try {
        const payload = await apiJson("/api/chat", {
          method: "POST",
          body: JSON.stringify({ message: commandText, mode: "real" }),
        });
        const actionPlan = normalizeActionPlanPayload(payload);
        const actionSuggestions = normalizeActionSuggestions(payload);
        actionTrace = syncRuntimeStateFromPayload(payload, "external:trace_received");
        replyText = cleanAssistantReply(payload.reply || payload.content) || "I can't open that yet.";
        const rawLaunchStatus = payload.action_status || payload.desktop_launch_status || (payload.execution_mode === "external_desktop" ? "opened" : "unknown");
        state.currentTask.launchStatus = actionPlan?.status === "blocked" ? "blocked" : rawLaunchStatus;
        state.currentTask.launchMessage = replyText;
        state.currentTask.actionPlan = actionPlan;
        state.currentTask.actionSuggestions = actionSuggestions;
        const launched = Boolean(payload.desktop_launch_success) || (
          payload.execution_mode === "external_desktop" && /^opening\b/i.test(replyText)
        ) || Boolean(payload.action_success);
        const unavailable = payload.desktop_launch_status === "unavailable";
        const needsConfirmation = Boolean(payload.automation_confirmation_required)
          || Boolean(actionPlan?.confirmationRequired)
          || state.currentTask.launchStatus === "needs_confirmation";
        const blockedForSafety = actionPlan?.status === "blocked"
          || ["blocked", "critical_blocked"].includes(String(rawLaunchStatus || "").trim().toLowerCase());

        if (launched) {
          setAssistantState("responding", "external:desktop_launch_succeeded");
          setComposerStatus("Opening that for you.");
          updateWorkspaceSummary(`${classification.label} is opening outside VORIS while the assistant stays nearby.`);
          showPresence({
            mode: "floating",
            eyebrow: externalModeLabel,
            title: "Opening that for you.",
            text: `${classification.label} is launching outside VORIS while I stay present here.`,
            duration: 2200,
          });
        } else if (needsConfirmation) {
          setAssistantState("responding", "automation:confirmation_required");
          setComposerStatus("Control approval is needed before VORIS types, presses keys, or scrolls.");
          updateWorkspaceSummary("VORIS is waiting for your one-time approval before keyboard or mouse control.");
          showPresence({
            mode: "floating",
            eyebrow: externalModeLabel,
            title: "Approval needed before control.",
            text: "VORIS will not type, press keys, or scroll until you approve this action.",
            duration: 2600,
          });
        } else if (blockedForSafety) {
          setAssistantState("responding", "external:safety_blocked");
          setComposerStatus(replyText);
          updateWorkspaceSummary("VORIS blocked this action for safety.");
          showPresence({
            mode: "floating",
            eyebrow: externalModeLabel,
            title: "Blocked for safety.",
            text: replyText,
            duration: 2600,
          });
        } else {
          setAssistantState("error", "external:desktop_launch_unavailable");
          setComposerStatus(replyText);
          updateWorkspaceSummary(
            unavailable
              ? `${classification.label} is not available on this system.`
              : `${classification.label} could not be launched from the VORIS backend.`
          );
          showPresence({
            mode: "floating",
            eyebrow: externalModeLabel,
            title: "I couldn't complete that yet.",
            text: replyText,
            duration: 2400,
          });
        }

        await loadSessions();
        renderSidebarSessions();
      } catch (error) {
        replyText = error.message || "I couldn't complete that yet.";
        state.currentTask.launchStatus = "failed";
        state.currentTask.launchMessage = replyText;
        setAssistantState("error", "external:desktop_launch_failed");
        setComposerStatus(replyText);
        updateWorkspaceSummary(`${classification.label} could not be launched from the VORIS backend.`);
        showPresence({
          mode: "floating",
          eyebrow: externalModeLabel,
          title: "I couldn't complete that yet.",
          text: replyText,
          duration: 2400,
        });
      } finally {
        state.requestInFlight = false;
        renderRightPanel();
      }
    }

    await revealAssistantMessage({
      role: "assistant",
      text: replyText,
      badge: "External action",
      timestamp: new Date().toISOString(),
      actionPlan: state.currentTask?.actionPlan || null,
      actionSuggestions: state.currentTask?.actionSuggestions || [],
      actionTrace,
    }, {
      delayMs: 240,
      stateName: state.assistantState === "error" ? "error" : "responding",
      event: state.assistantState === "error" ? "external:reply_error_revealed" : "external:reply_revealed",
    });
    renderRightPanel();
    resetToCalmIdle();
  }

  function classifyCommand(text) {
    const normalized = String(text || "").trim();
    if (CRITICAL_DIRECT_CONTROL_RE.test(normalized) || CONTROLLED_BROWSER_ACTION_RE.test(normalized) || SAFE_WEB_ACTION_PLAN_RE.test(normalized)) {
      const isOsAutomation = /\b(?:notepad|vs\s*code|vscode|visual studio code|calculator|calc|chrome)\b.*\b(?:type|write|enter|press|scroll|focus)\b/i.test(normalized)
        || /\b(?:type|write|enter|press|scroll|focus)\b.*\b(?:notepad|vs\s*code|vscode|visual studio code|calculator|calc|chrome)\b/i.test(normalized)
        || /\b(?:ask|tell)\s+(?:it|chatgpt|the\s+(?:site|page|website))\s+to\b/i.test(normalized)
        || CRITICAL_DIRECT_CONTROL_RE.test(normalized);
      return {
        kind: "external",
        type: isOsAutomation ? "os-automation" : "browser-action",
        label: isOsAutomation ? "Controlled OS automation" : "Controlled browser action",
        taskKind: "external",
      };
    }

    const directUrlMatch = normalized.match(/\bhttps?:\/\/[^\s]+/i);
    if (directUrlMatch) {
      return {
        kind: "external",
        type: "web",
        label: "Website",
        url: directUrlMatch[0],
        taskKind: "external",
      };
    }

    for (const target of EXTERNAL_TARGETS) {
      if (target.pattern.test(normalized)) {
        return {
          kind: "external",
          type: target.type,
          label: target.label,
          url: target.url || "",
          taskKind: "external",
        };
      }
    }

    for (const hint of INTERNAL_HINTS) {
      if (hint.pattern.test(normalized)) {
        return {
          kind: "internal",
          label: hint.label,
          taskKind: hint.kind,
        };
      }
    }

    return {
      kind: "internal",
      label: "Chat task",
      taskKind: "chat",
    };
  }

  function normalizeHistoryMessage(message) {
    return {
      role: String(message.role || "assistant").toLowerCase() === "user" ? "user" : "assistant",
      text: String(message.message || "").trim(),
      badge: String(message.intent || message.mode || "").trim(),
      timestamp: message.timestamp || new Date().toISOString(),
    };
  }

  function ensureMessageId(message) {
    if (!message.id) {
      message.id = `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }
    return message.id;
  }

  function getMessageRowElement(messageId) {
    if (!messageId) {
      return null;
    }
    return state.messageDomById.get(messageId) || null;
  }

  function removeWelcomeCardIfPresent() {
    const welcome = el.conversationThread?.querySelector(".welcome-card");
    welcome?.remove();
  }

  function clearConversationView() {
    if (!el.conversationThread) {
      return;
    }
    el.conversationThread.replaceChildren();
    state.messageDomById.clear();
  }

  function mountMessage(message) {
    if (!el.conversationThread) {
      return null;
    }
    ensureMessageId(message);
    const existing = getMessageRowElement(message.id);
    if (existing) {
      return existing;
    }
    removeWelcomeCardIfPresent();
    const row = buildMessageRow(message);
    state.messageDomById.set(message.id, row);
    el.conversationThread.appendChild(row);
    return row;
  }

  function unmountMessage(messageId) {
    const row = getMessageRowElement(messageId);
    row?.remove();
    state.messageDomById.delete(messageId);
    if (!state.messages.length && el.conversationThread) {
      el.conversationThread.appendChild(buildWelcomeCard());
    }
  }

  function updateMessageText(message) {
    const row = getMessageRowElement(message.id);
    if (!row) {
      return;
    }
    const card = row.querySelector(".message-card");
    if (!card) {
      return;
    }
    let body = card.querySelector(".message-card__content");
    const nextBody = renderRichText(message.text);
    nextBody.classList.add("message-card__content");
    if (body) {
      body.replaceWith(nextBody);
      return;
    }
    const firstExtra = card.querySelector(".document-card, .action-plan-card, .message-card__image");
    if (firstExtra) {
      card.insertBefore(nextBody, firstExtra);
    } else {
      card.appendChild(nextBody);
    }
  }

  function syncMessageRowState(message) {
    const row = getMessageRowElement(message.id);
    if (!row) {
      return;
    }
    row.classList.toggle("message-row--streaming", Boolean(message.streaming));
    row.classList.toggle("message-row--response", message.effect === "response" && message.role !== "user");
    const badge = row.querySelector(".message-card__badge");
    if (badge && message.badge) {
      badge.textContent = humanizeBadge(message.badge);
    }
    const metaRight = row.querySelector(".message-card__meta-right");
    if (!metaRight) {
      return;
    }
    metaRight.querySelector(".message-actions")?.remove();
    if (message.role !== "user" && !message.streaming) {
      metaRight.appendChild(buildMessageActions(message));
    }
  }

  function refreshMessageRow(message) {
    ensureMessageId(message);
    const row = getMessageRowElement(message.id);
    const nextRow = buildMessageRow(message);
    if (row) {
      row.replaceWith(nextRow);
    } else {
      removeWelcomeCardIfPresent();
      el.conversationThread?.appendChild(nextRow);
    }
    state.messageDomById.set(message.id, nextRow);
  }

  function applyMessageEffect(message) {
    if (!message?.effect) {
      return;
    }
    const row = getMessageRowElement(message.id);
    if (message.effect === "response" && message.role !== "user") {
      row?.classList.add("message-row--response");
    }
    window.setTimeout(() => {
      delete message.effect;
      getMessageRowElement(message.id)?.classList.remove("message-row--response");
    }, 1000);
  }

  function appendMessage(message) {
    ensureMessageId(message);
    state.messages.push(message);
    mountMessage(message);
    scrollConversationToBottom();
    applyMessageEffect(message);
    return message;
  }

  async function requestChatPayload(commandText, classification) {
    if (!window.ReadableStream || !window.TextDecoder || !window.AbortController) {
      return {
        payload: await apiJson("/api/chat", {
          method: "POST",
          body: JSON.stringify({ message: commandText, mode: "hybrid" }),
        }),
        message: null,
      };
    }

    try {
      return await streamChatPayload(commandText, classification);
    } catch (error) {
      if (error?.name === "AbortError") {
        throw error;
      }
      return {
        payload: await apiJson("/api/chat", {
          method: "POST",
          body: JSON.stringify({ message: commandText, mode: "hybrid" }),
        }),
        message: null,
      };
    }
  }

  async function streamChatPayload(commandText, classification) {
    const controller = new AbortController();
    state.activeChatAbortController = controller;
    syncVoiceControls();

    const streamingMessage = appendMessage({
      role: "assistant",
      text: "",
      badge: humanizeBadge(classification.taskKind || "Assistant"),
      timestamp: new Date().toISOString(),
      streaming: true,
    });

    let finalPayload = null;
    let sawChunk = false;
    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
          "X-VORIS-Session-Id": state.sessionId,
        },
        body: JSON.stringify({ message: commandText, mode: "hybrid" }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`Streaming unavailable (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const rawEvent of events) {
          const event = parseSseEvent(rawEvent);
          if (!event) {
            continue;
          }
          if (event.event === "chunk" && event.data?.text) {
            sawChunk = true;
            streamingMessage.text += String(event.data.text);
            updateMessageText(streamingMessage);
            scrollConversationToBottom();
          } else if (event.event === "error") {
            streamingMessage.text = String(event.data?.message || streamingMessage.text || "I couldn't complete that yet.");
            updateMessageText(streamingMessage);
          } else if (event.event === "final") {
            finalPayload = event.data || {};
          }
        }
      }
      if (!finalPayload) {
        throw new Error("Streaming ended before the final response arrived.");
      }
      return { payload: finalPayload, message: streamingMessage };
    } catch (error) {
      if (error?.name === "AbortError") {
        streamingMessage.streaming = false;
        streamingMessage.text = streamingMessage.text || "Stopped.";
        updateMessageText(streamingMessage);
        syncMessageRowState(streamingMessage);
        throw error;
      }
      state.messages = state.messages.filter((message) => message.id !== streamingMessage.id);
      unmountMessage(streamingMessage.id);
      if (sawChunk) {
        setComposerStatus("Streaming stopped early. Falling back to the standard response path.");
      }
      throw error;
    } finally {
      state.activeChatAbortController = null;
      syncVoiceControls();
    }
  }

  function parseSseEvent(rawEvent) {
    const lines = String(rawEvent || "").split("\n");
    let eventName = "message";
    const dataLines = [];
    lines.forEach((line) => {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    });
    if (!dataLines.length) {
      return null;
    }
    try {
      return {
        event: eventName,
        data: JSON.parse(dataLines.join("\n")),
      };
    } catch (_error) {
      return null;
    }
  }

  function responseRevealDelay(message) {
    const textLength = String(message?.text || "").length;
    if (textLength > 900 || message?.delivery) {
      return 420;
    }
    if (textLength > 280) {
      return 320;
    }
    return 240;
  }

  async function revealAssistantMessage(message, options = {}) {
    if (options.stateName) {
      setAssistantState(options.stateName, options.event || "ui:assistant_reply_ready");
    }
    await delay(Number.isFinite(options.delayMs) ? options.delayMs : responseRevealDelay(message));
    const revealed = appendMessage({
      ...message,
      effect: options.effect || "response",
    });
    triggerOrbResponsePulse();
    maybeSpeakAssistantMessage(revealed, options);
    return revealed;
  }

  function maybeSpeakAssistantMessage(message, options = {}) {
    if (message.role !== "assistant") {
      return;
    }
    const shouldSpeak = Boolean(options.speak) || Boolean(state.speechEnabled && state.speechCommandInFlight);
    if (!shouldSpeak) {
      return;
    }
    speakMessage(message);
  }

  function renderConversation() {
    if (!el.conversationThread) {
      return;
    }

    clearConversationView();
    if (!state.messages.length) {
      el.conversationThread.appendChild(buildWelcomeCard());
      return;
    }
    state.messages.forEach((message) => {
      mountMessage(message);
    });
    scrollConversationToBottom();
  }

  function buildWelcomeCard() {
    const card = document.createElement("section");
    card.className = "welcome-card";

    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "VORIS ready";

    const title = document.createElement("h3");
    title.textContent = "What should we handle first?";

    const body = document.createElement("p");
    body.textContent = "Ask a question, generate a document, or route a safe desktop/browser action. Voice is optional beta, not required.";

    const hints = document.createElement("div");
    hints.className = "welcome-card__hints";
    ["Explain quantum computing", "Write assignment on AI", "Open Chrome and search AI trends"].forEach((value) => {
      const chip = document.createElement("span");
      chip.textContent = value;
      hints.appendChild(chip);
    });

    card.append(eyebrow, title, body, hints);
    return card;
  }

  function resolveMessageImageUrl(message) {
    return String(message?.imageUrl || message?.image_url || "").trim();
  }

  function isImageBypassMessage(message) {
    const executionMode = String(message?.executionMode || message?.execution_mode || "").trim().toLowerCase();
    return executionMode === "image_bypass" || Boolean(resolveMessageImageUrl(message));
  }

  function buildMessageImage(imageUrl) {
    const figure = document.createElement("figure");
    figure.className = "message-card__image";

    const img = document.createElement("img");
    img.src = imageUrl;
    img.alt = "Generated image";
    img.loading = "lazy";
    img.decoding = "async";
    img.referrerPolicy = "no-referrer";
    figure.appendChild(img);
    return figure;
  }

  function buildMessageMeta(message) {
    const meta = document.createElement("div");
    meta.className = "message-card__meta";

    const label = document.createElement("span");
    label.className = "message-card__label";
    label.textContent = message.role === "user" ? "You" : "VORIS";

    const metaRight = document.createElement("div");
    metaRight.className = "message-card__meta-right";

    if (message.badge) {
      const badge = document.createElement("span");
      badge.className = "message-card__badge";
      badge.textContent = humanizeBadge(message.badge);
      metaRight.appendChild(badge);
    }

    const time = document.createElement("span");
    time.textContent = formatClock(message.timestamp);
    metaRight.appendChild(time);

    if (message.role !== "user" && !message.streaming) {
      metaRight.appendChild(buildMessageActions(message));
    }

    meta.append(label, metaRight);
    return meta;
  }

  function buildMessageCardContent(message) {
    const fragment = document.createDocumentFragment();
    const imageUrl = resolveMessageImageUrl(message);
    if (isImageBypassMessage(message) && imageUrl) {
      fragment.appendChild(buildMessageImage(imageUrl));
    } else if (message.text || message.streaming) {
      const body = renderRichText(message.text);
      body.classList.add("message-card__content");
      fragment.appendChild(body);
    }
    if (message.delivery) {
      fragment.appendChild(buildDocumentCard(message.delivery));
    }
    if (message.actionPlan) {
      fragment.appendChild(buildActionPlanCard(message.actionPlan, message.actionSuggestions || []));
    }
    return fragment;
  }

  function buildMessageRow(message) {
    ensureMessageId(message);
    const row = document.createElement("article");
    row.className = `message-row message-row--${message.role === "user" ? "user" : "assistant"}`;
    row.dataset.messageId = message.id;
    if (message.effect === "response" && message.role !== "user") {
      row.classList.add("message-row--response");
    }
    if (message.streaming) {
      row.classList.add("message-row--streaming");
    }

    const card = document.createElement("div");
    card.className = "message-card";
    card.appendChild(buildMessageMeta(message));
    card.appendChild(buildMessageCardContent(message));
    row.appendChild(card);
    return row;
  }

  function buildMessageActions(message) {
    const actions = document.createElement("div");
    actions.className = "message-actions";

    const copy = document.createElement("button");
    copy.type = "button";
    const isCopied = state.copiedMessageId === message.id;
    copy.className = `message-action-button${isCopied ? " is-success" : ""}`;
    setIconButtonContent(copy, isCopied ? "check" : "copy", isCopied ? "Copied VORIS response" : "Copy VORIS response");
    copy.addEventListener("click", () => {
      void copyMessageText(message, copy);
    });
    actions.appendChild(copy);

    if (state.speechSynthesisSupported) {
      const isSpeakingThis = state.speakingMessageId === message.id;
      const speak = document.createElement("button");
      speak.type = "button";
      speak.className = `message-action-button${isSpeakingThis ? " is-active is-speaking" : ""}`;
      setIconButtonContent(
        speak,
        isSpeakingThis ? "stop" : "speaker",
        isSpeakingThis ? "Stop speaking this response" : "Speak this response",
      );
      speak.addEventListener("click", () => {
        if (state.speakingMessageId === message.id) {
          stopSpeaking("message:stop_clicked");
          return;
        }
        speakMessage(message);
      });
      actions.appendChild(speak);
    }

    return actions;
  }

  function setIconButtonContent(button, iconName, label, visibleText = "") {
    button.textContent = "";
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);

    const glyph = document.createElement("span");
    glyph.className = "icon-button__glyph";
    glyph.setAttribute("aria-hidden", "true");
    glyph.innerHTML = ICONS[iconName] || "";

    const text = document.createElement("span");
    text.className = visibleText ? "icon-button__text" : "sr-only";
    text.textContent = visibleText || label;

    button.append(glyph, text);
  }

  async function copyTextValue(text, trigger, successLabel = "Copied") {
    if (!text) {
      return false;
    }
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      fallbackCopyText(text);
    }
    if (trigger) {
      const originalText = trigger.textContent;
      trigger.textContent = successLabel;
      trigger.classList.add("is-success");
      window.setTimeout(() => {
        trigger.textContent = originalText || "Copy";
        trigger.classList.remove("is-success");
      }, 1400);
    }
    return true;
  }

  async function copyMessageText(message, trigger) {
    const text = messageTextForControls(message);
    if (!text) {
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        fallbackCopyText(text);
      }
      if (trigger) {
        state.copiedMessageId = message.id || "";
        setIconButtonContent(trigger, "check", "Copied VORIS response");
        trigger.classList.add("is-success");
        window.setTimeout(() => {
          if (state.copiedMessageId === message.id) {
            state.copiedMessageId = "";
            syncMessageRowState(message);
          }
        }, 1400);
      }
      setComposerStatus("Copied VORIS's response.");
    } catch (_error) {
      fallbackCopyText(text);
      setComposerStatus("Copied VORIS's response.");
    }
  }

  function messageTextForControls(message) {
    const parts = [String(message?.text || "").trim()];
    const imageUrl = resolveMessageImageUrl(message);
    if (imageUrl) {
      parts.push(imageUrl);
    }
    const delivery = message?.delivery;
    if (delivery?.files?.length) {
      if (delivery.title || delivery.previewText) {
        parts.push([delivery.title, delivery.previewText].filter(Boolean).join("\n\n"));
      }
      parts.push(
        delivery.files
          .map((file) => `${String(file.format || "").toUpperCase()}: ${file.downloadUrl}`)
          .join("\n")
      );
    }
    return parts.filter(Boolean).join("\n\n").trim();
  }

  function fallbackCopyText(text) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "readonly");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }

  function speakMessage(message) {
    const text = String(message?.text || "").trim();
    if (!text || !state.speechSynthesisSupported) {
      setComposerStatus("Speech is not available in this browser.");
      return;
    }
    stopSpeaking("speech:new_message");
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = state.voiceStatus?.settings?.language || "en-US";
    const voice = chooseVorisVoice(utterance.lang);
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang || utterance.lang;
    }
    utterance.rate = 0.94;
    utterance.pitch = 0.96;
    utterance.onstart = () => {
      state.speakingMessageId = message.id || "";
      setAssistantState("responding", "tts:speech_started");
      setComposerStatus("Speaking VORIS's response.");
      syncAssistantModeChrome();
      syncMessageRowState(message);
    };
    utterance.onend = () => {
      if (state.speakingMessageId === message.id) {
        state.speakingMessageId = "";
      }
      syncAssistantModeChrome();
      syncMessageRowState(message);
      if (!state.requestInFlight && !state.recognitionActive) {
        setAssistantState("idle", "tts:speech_finished");
        settleToIdleLayout();
      }
    };
    utterance.onerror = (event) => {
      const errorName = String(event?.error || "unknown error");
      const intentionalStop = /interrupted|canceled|cancelled/i.test(errorName)
        && Date.now() <= state.speechCancelUntil;
      state.speakingMessageId = "";
      syncAssistantModeChrome();
      syncMessageRowState(message);
      if (intentionalStop) {
        setComposerStatus("Speech stopped.");
        if (!state.requestInFlight && !state.recognitionActive) {
          setAssistantState("idle", "tts:speech_stopped");
          settleToIdleLayout();
        }
        return;
      }
      setAssistantState("error", "tts:speech_error");
      setComposerStatus(`Speech failed: ${errorName}`);
      resetToCalmIdle(1200);
    };
    window.speechSynthesis.speak(utterance);
  }

  function chooseVorisVoice(language) {
    if (!window.speechSynthesis?.getVoices) {
      return null;
    }
    const voices = window.speechSynthesis.getVoices() || [];
    if (!voices.length) {
      return null;
    }
    const normalizedLanguage = String(language || "en-US").toLowerCase();
    const englishVoices = voices.filter((voice) => String(voice.lang || "").toLowerCase().startsWith(normalizedLanguage.slice(0, 2)));
    const candidates = englishVoices.length ? englishVoices : voices;
    const preferredNamePattern = /(kokoro|koroko|natural|neural|aria|jenny|zira|samantha|google us english|microsoft)/i;
    return candidates.find((voice) => preferredNamePattern.test(String(voice.name || "")))
      || candidates.find((voice) => String(voice.lang || "").toLowerCase() === normalizedLanguage)
      || candidates[0]
      || null;
  }

  function stopSpeaking(eventName = "tts:stop") {
    if (window.speechSynthesis) {
      if (state.speakingMessageId || window.speechSynthesis.speaking || window.speechSynthesis.pending) {
        state.speechCancelUntil = Date.now() + 900;
      }
      window.speechSynthesis.cancel();
    }
    if (state.speakingMessageId) {
      const speakingId = state.speakingMessageId;
      state.speakingMessageId = "";
      syncAssistantModeChrome();
      const speakingMessage = state.messages.find((item) => item.id === speakingId);
      if (speakingMessage) {
        syncMessageRowState(speakingMessage);
      }
      setComposerStatus("Speech stopped.");
      if (!state.requestInFlight && !state.recognitionActive) {
        setAssistantState("idle", eventName);
      }
    }
  }

  function toggleSpeechEnabled() {
    state.speechEnabled = !state.speechEnabled;
    localStorage.setItem(STORAGE_KEYS.speechEnabled, state.speechEnabled ? "true" : "false");
    if (!state.speechEnabled) {
      stopSpeaking("tts:toggled_off");
    }
    syncAssistantModeChrome();
    setComposerStatus(state.speechEnabled
      ? "Speech is on for voice responses. Text chat stays silent unless you press Speak."
      : "Speech is off. You can still press Speak on any VORIS message.");
  }

  async function toggleDesktopVoice() {
    if (state.requestInFlight) {
      setComposerStatus("Wait for the current request to finish before changing desktop voice.");
      return;
    }
    const active = Boolean(state.desktopVoiceStatus?.active);
    const endpoint = active ? "/api/voice/desktop/stop" : "/api/voice/desktop/start";
    setComposerStatus(active ? "Stopping desktop voice." : "Starting desktop voice.");
    try {
      const payload = await apiJson(endpoint, { method: "POST" });
      state.desktopVoiceStatus = payload;
      await loadAssistantRuntime();
      syncVoiceControls();
      const failed = payload.success === false || payload.available === false;
      if (failed) {
        setAssistantState("error", "desktop_voice:unavailable");
        setComposerStatus(payload.message || "Desktop voice runtime is not available on this system.");
        updateWorkspaceSummary("Desktop voice could not start on this machine.");
        showPresence({
          mode: "docked",
          eyebrow: "Desktop voice",
          title: "Desktop voice is unavailable.",
          text: payload.message || "Required local voice dependencies or microphone access are missing.",
          duration: 2400,
        });
        resetToCalmIdle(1600);
        return;
      }
      if (payload.active) {
        setAssistantState("listening", "desktop_voice:started");
        setComposerStatus('Desktop voice is listening for "Hey VORIS".');
        updateWorkspaceSummary('Desktop voice is active locally and listening for "Hey VORIS".');
      } else {
        setAssistantState("idle", "desktop_voice:stopped");
        setComposerStatus("Desktop voice stopped.");
        updateWorkspaceSummary("VORIS is back to text mode and browser push-to-talk.");
      }
    } catch (error) {
      setAssistantState("error", "desktop_voice:toggle_failed");
      setComposerStatus(error.message || "Desktop voice could not be toggled.");
      updateWorkspaceSummary("The desktop voice endpoint did not complete cleanly.");
      resetToCalmIdle(1600);
    }
  }

  async function interruptDesktopVoice() {
    try {
      const payload = await apiJson("/api/voice/desktop/interrupt", { method: "POST" });
      state.desktopVoiceStatus = payload;
      await loadAssistantRuntime();
      syncVoiceControls();
      setComposerStatus(payload.message || "Desktop voice interrupted.");
      updateWorkspaceSummary("VORIS interrupted the desktop voice runtime and returned to a safe listening state.");
    } catch (error) {
      setComposerStatus(error.message || "Desktop voice interrupt failed.");
    }
  }

  function syncDesktopVoicePolling() {
    const active = Boolean(state.desktopVoiceStatus?.active);
    if (active && !state.desktopVoicePollId) {
      state.desktopVoicePollId = window.setInterval(() => {
        void loadAssistantRuntime().then(() => {
          syncVoiceControls();
        });
      }, 2000);
      return;
    }
    if (!active && state.desktopVoicePollId) {
      window.clearInterval(state.desktopVoicePollId);
      state.desktopVoicePollId = 0;
    }
  }

  function renderRichText(text) {
    const container = document.createElement("div");
    container.className = "rich-text";

    const source = String(text || "");
    if (!source.trim()) {
      const placeholder = document.createElement("p");
      placeholder.className = "rich-text__placeholder";
      placeholder.textContent = "VORIS is writing";
      container.appendChild(placeholder);
      return container;
    }

    let cursor = 0;
    const fencePattern = /```([a-zA-Z0-9_+\-.#]*)\n?([\s\S]*?)```/g;
    let match = fencePattern.exec(source);
    while (match) {
      renderMarkdownBlocks(source.slice(cursor, match.index), container);
      container.appendChild(buildCodeBlock(match[2] || "", match[1] || ""));
      cursor = fencePattern.lastIndex;
      match = fencePattern.exec(source);
    }
    renderMarkdownBlocks(source.slice(cursor), container);

    return container;
  }

  function renderMarkdownBlocks(source, container) {
    const lines = String(source || "").replace(/\r\n/g, "\n").split("\n");
    let paragraph = [];

    const flushParagraph = () => {
      const text = paragraph.join(" ").trim();
      paragraph = [];
      if (!text) {
        return;
      }
      const element = document.createElement("p");
      appendInlineMarkdown(element, text);
      container.appendChild(element);
    };

    for (let index = 0; index < lines.length; index += 1) {
      const rawLine = lines[index] || "";
      const line = rawLine.trim();
      if (!line) {
        flushParagraph();
        continue;
      }

      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        const level = Math.min(4, Math.max(2, heading[1].length + 1));
        const element = document.createElement(`h${level}`);
        appendInlineMarkdown(element, heading[2]);
        container.appendChild(element);
        continue;
      }

      if (/^>\s?/.test(line)) {
        flushParagraph();
        const quote = document.createElement("blockquote");
        while (index < lines.length && /^>\s?/.test(String(lines[index] || "").trim())) {
          const part = String(lines[index] || "").trim().replace(/^>\s?/, "");
          const paragraphElement = document.createElement("p");
          appendInlineMarkdown(paragraphElement, part);
          quote.appendChild(paragraphElement);
          index += 1;
        }
        index -= 1;
        container.appendChild(quote);
        continue;
      }

      if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
        flushParagraph();
        const ordered = /^\d+\.\s+/.test(line);
        const list = document.createElement(ordered ? "ol" : "ul");
        while (index < lines.length) {
          const current = String(lines[index] || "").trim();
          const matches = ordered ? current.match(/^\d+\.\s+(.+)$/) : current.match(/^[-*]\s+(.+)$/);
          if (!matches) {
            break;
          }
          const item = document.createElement("li");
          appendInlineMarkdown(item, matches[1]);
          list.appendChild(item);
          index += 1;
        }
        index -= 1;
        container.appendChild(list);
        continue;
      }

      if (looksLikeMarkdownTable(lines, index)) {
        flushParagraph();
        const tableLines = [];
        while (index < lines.length && String(lines[index] || "").includes("|")) {
          tableLines.push(String(lines[index] || "").trim());
          index += 1;
        }
        index -= 1;
        container.appendChild(buildMarkdownTable(tableLines));
        continue;
      }

      paragraph.push(line);
    }
    flushParagraph();
  }

  function looksLikeMarkdownTable(lines, index) {
    const current = String(lines[index] || "");
    const next = String(lines[index + 1] || "");
    return current.includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(next);
  }

  function buildMarkdownTable(lines) {
    const table = document.createElement("table");
    table.className = "markdown-table";
    const rows = lines
      .filter((line, index) => index !== 1)
      .map((line) => line.replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim()));
    rows.forEach((cells, rowIndex) => {
      const row = document.createElement("tr");
      cells.forEach((cell) => {
        const element = document.createElement(rowIndex === 0 ? "th" : "td");
        appendInlineMarkdown(element, cell);
        row.appendChild(element);
      });
      table.appendChild(row);
    });
    return table;
  }

  function buildCodeBlock(code, language) {
    const wrapper = document.createElement("div");
    wrapper.className = "code-block";

    const header = document.createElement("div");
    header.className = "code-block__header";
    const label = document.createElement("span");
    label.textContent = language ? language.toLowerCase() : "code";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "code-copy-button";
    copy.textContent = "Copy code";
    copy.setAttribute("aria-label", "Copy code block");
    copy.addEventListener("click", async () => {
      await copyTextValue(String(code || ""), copy, "Copied");
    });
    header.append(label, copy);

    const pre = document.createElement("pre");
    const codeElement = document.createElement("code");
    codeElement.textContent = String(code || "").replace(/^\n+|\n+$/g, "");
    pre.appendChild(codeElement);

    wrapper.append(header, pre);
    return wrapper;
  }

  function appendInlineMarkdown(parent, value) {
    const text = String(value || "");
    const tokenPattern = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/g;
    let cursor = 0;
    let match = tokenPattern.exec(text);
    while (match) {
      if (match.index > cursor) {
        parent.appendChild(document.createTextNode(text.slice(cursor, match.index)));
      }
      const token = match[0];
      const element = token.startsWith("`")
        ? document.createElement("code")
        : token.startsWith("**") || token.startsWith("__")
          ? document.createElement("strong")
          : document.createElement("em");
      element.textContent = token.replace(/^(`|\*\*|__|\*|_)|(`|\*\*|__|\*|_)$/g, "");
      parent.appendChild(element);
      cursor = tokenPattern.lastIndex;
      match = tokenPattern.exec(text);
    }
    if (cursor < text.length) {
      parent.appendChild(document.createTextNode(text.slice(cursor)));
    }
  }

  function cleanInlineMarkdown(value) {
    return String(value || "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .trim();
  }

  function cleanAssistantReply(value) {
    return String(value || "")
      .replace(/\s+Next,\s+based on your recent pattern around .+?\(\d+\),\s+I can keep the next step focused\.?$/i, "")
      .trim();
  }

  function normalizeDocumentDeliveryPayload(payload) {
    const raw = payload && typeof payload.document_delivery === "object" ? payload.document_delivery : {};
    const primaryFormat = String(raw.format || payload.format || "txt").trim().toLowerCase();
    const downloadUrl = String(raw.download_url || payload.download_url || "").trim();
    const fileName = String(raw.file_name || payload.file_name || "").trim();
    if (!downloadUrl || !fileName) {
      return null;
    }

    const formatLinks = {
      ...(payload.format_links && typeof payload.format_links === "object" ? payload.format_links : {}),
      ...(raw.format_links && typeof raw.format_links === "object" ? raw.format_links : {}),
    };
    if (!formatLinks[primaryFormat]) {
      formatLinks[primaryFormat] = downloadUrl;
    }

    const alternateFormatLinks = {
      ...(payload.alternate_format_links && typeof payload.alternate_format_links === "object" ? payload.alternate_format_links : {}),
      ...(raw.alternate_format_links && typeof raw.alternate_format_links === "object" ? raw.alternate_format_links : {}),
    };

    const files = [];
    const pushFile = (file) => {
      const format = String(file?.format || "").trim().toLowerCase();
      const name = String(file?.file_name || file?.fileName || "").trim();
      const href = String(file?.download_url || file?.downloadUrl || "").trim();
      if (!format || !name || !href) {
        return;
      }
      if (files.some((entry) => entry.format === format && entry.downloadUrl === href)) {
        return;
      }
      files.push({
        format,
        fileName: name,
        downloadUrl: href,
        primary: Boolean(file?.primary),
      });
    };

    (Array.isArray(payload.files) ? payload.files : []).forEach(pushFile);
    (Array.isArray(raw.files) ? raw.files : []).forEach(pushFile);
    Object.entries(formatLinks).forEach(([format, href]) => {
      pushFile({
        format,
        file_name: `${fileName.replace(/\.[^.]+$/, "")}.${format}`,
        download_url: href,
        primary: format === primaryFormat,
      });
    });
    Object.entries(alternateFormatLinks).forEach(([format, href]) => {
      pushFile({
        format,
        file_name: `${fileName.replace(/\.[^.]+$/, "")}.${format}`,
        download_url: href,
        primary: false,
      });
    });
    if (!files.length) {
      files.push({
        format: primaryFormat,
        fileName,
        downloadUrl,
        primary: true,
      });
    }

    const requestedFormats = Array.from(new Set([
      ...(Array.isArray(payload.requested_formats) ? payload.requested_formats : []),
      ...(Array.isArray(raw.requested_formats) ? raw.requested_formats : []),
      ...files.map((file) => file.format),
    ].map((item) => String(item).trim().toLowerCase()).filter(Boolean)));

    return {
      kind: "document_delivery",
      deliveryMessage: String(raw.delivery_message || payload.reply || payload.content || "Done. Your document is ready.").trim(),
      title: String(raw.title || payload.title || humanizeDocumentTitle(payload.document_type || raw.document_type || "document")).trim(),
      subtitle: String(raw.subtitle || payload.subtitle || "").trim(),
      previewText: String(raw.preview_text || payload.preview_text || "").trim(),
      documentType: String(raw.document_type || payload.document_type || "document").trim().toLowerCase(),
      format: primaryFormat,
      primaryFormat,
      fileName,
      downloadUrl,
      topic: String(raw.topic || payload.topic || "").trim(),
      pageTarget: Number(raw.page_target || payload.page_target || 0) || null,
      style: String(raw.style || payload.style || "").trim(),
      includeReferences: Boolean(raw.include_references || payload.include_references),
      citationStyle: String(raw.citation_style || payload.citation_style || "").trim(),
      files,
      requestedFormats,
    };
  }

  function buildDocumentCard(delivery) {
    const card = document.createElement("section");
    card.className = "document-card";

    const eyebrow = document.createElement("p");
    eyebrow.className = "document-card__eyebrow";
    eyebrow.textContent = humanizeDocumentTitle(delivery.documentType);

    const title = document.createElement("p");
    title.className = "document-card__title";
    title.textContent = delivery.title || humanizeDocumentTitle(delivery.documentType);

    const subtitle = document.createElement("p");
    subtitle.className = "document-card__subtitle";
    subtitle.textContent = delivery.deliveryMessage || `${humanizeDocumentTitle(delivery.documentType)} ready.`;

    const meta = document.createElement("p");
    meta.className = "document-card__meta";
    const metaParts = [
      delivery.subtitle || "",
      delivery.topic ? `Topic: ${delivery.topic}` : "",
      delivery.files.length > 1 ? `${delivery.files.length} files ready` : "Single file ready",
    ].filter(Boolean);
    meta.textContent = metaParts.join(" | ");

    const chips = document.createElement("div");
    chips.className = "document-card__chips";
    [
      `${String(delivery.primaryFormat || delivery.format).toUpperCase()} primary`,
      delivery.files.length > 1 ? `${delivery.files.length} formats` : "",
      delivery.pageTarget ? `~${delivery.pageTarget} pages` : "",
      delivery.style ? `${capitalize(delivery.style)} style` : "",
      delivery.includeReferences ? `References${delivery.citationStyle ? ` | ${String(delivery.citationStyle).toUpperCase()}` : ""}` : "",
    ].filter(Boolean).forEach((value) => {
      const chip = document.createElement("span");
      chip.className = "document-chip";
      chip.textContent = value;
      chips.appendChild(chip);
    });

    card.append(eyebrow, title, subtitle, meta);
    if (chips.childElementCount) {
      card.appendChild(chips);
    }

    if (delivery.previewText) {
      const preview = document.createElement("p");
      preview.className = "document-card__preview";
      preview.textContent = delivery.previewText;
      card.appendChild(preview);
    }

    const linksLabel = document.createElement("p");
    linksLabel.className = "links-label";
    linksLabel.textContent = delivery.files.length > 1 ? "Ready to download" : "Download";
    card.appendChild(linksLabel);

    const links = document.createElement("div");
    links.className = "document-links";

    const row = document.createElement("div");
    row.className = "document-links__row";
    delivery.files.forEach((file, index) => {
      row.appendChild(buildDocumentLink(`Download ${String(file.format || delivery.format).toUpperCase()}`, file.downloadUrl, index === 0));
    });
    if (delivery.previewText) {
      const copyPreview = document.createElement("button");
      copyPreview.type = "button";
      copyPreview.className = "document-link document-link--ghost";
      copyPreview.textContent = "Copy preview";
      copyPreview.addEventListener("click", async () => {
        await copyTextValue([delivery.title, delivery.previewText].filter(Boolean).join("\n\n"), copyPreview, "Copied");
      });
      row.appendChild(copyPreview);
    }
    links.appendChild(row);
    card.appendChild(links);
    return card;
  }

  function buildDocumentLink(label, href, primary) {
    const link = document.createElement("a");
    link.className = `document-link${primary ? " document-link--primary" : ""}`;
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    return link;
  }

  function normalizeActionPlanPayload(payload) {
    const rawPlan = payload && typeof payload.action_plan === "object" ? payload.action_plan : null;
    const rawSteps = Array.isArray(payload?.action_steps)
      ? payload.action_steps
      : Array.isArray(rawPlan?.steps)
        ? rawPlan.steps
        : [];
    if (!rawPlan && !rawSteps.length) {
      return null;
    }
    const confirmationRequired = Boolean(payload.automation_confirmation_required)
      || Boolean(rawPlan?.automation_confirmation_required);
    const steps = rawSteps.map((step, index) => {
      const result = step?.result && typeof step.result === "object" ? step.result : {};
      const screenValidation = result?.screen_validation && typeof result.screen_validation === "object"
        ? result.screen_validation
        : {};
      const controlFlow = result?.control_flow && typeof result.control_flow === "object"
        ? result.control_flow
        : {};
      const actionType = String(step?.action_type || "action").trim();
      const rawStatus = step?.status || controlFlow.state || result.status || "pending";
      const normalizedStatus = normalizeStepStatus(rawStatus);
      const blockedReason = String(
        result.error
        || screenValidation.reason
        || controlFlow.reason
        || ""
      ).trim();
      return {
        id: String(step?.step_id || `step-${index + 1}`),
        actionType,
        label: String(step?.label || step?.message || `Step ${index + 1}`).trim(),
        target: String(step?.target || "").trim(),
        status: actionType === "automation_critical_blocked" ? "blocked" : normalizedStatus,
        message: normalizeActionStepMessage(step?.message || result.message || blockedReason, confirmationRequired),
        resultStatus: actionType === "automation_critical_blocked"
          ? "blocked"
          : normalizeStepStatus(result.status || controlFlow.state || normalizedStatus),
        blockedReason,
        recovered: Boolean(result.recovered),
        controlFlow,
      };
    });
    const normalizedPlanStatus = normalizeStepStatus(payload.action_status || rawPlan?.status || "pending");
    const hasBlockedStep = steps.some((step) => step.status === "blocked");
    const planStatus = hasBlockedStep && normalizedPlanStatus === "failed"
      ? "blocked"
      : normalizedPlanStatus;
    return {
      planId: String(rawPlan?.plan_id || "").trim(),
      originalCommand: String(rawPlan?.original_command || "").trim(),
      status: planStatus,
      success: Boolean(payload.action_success),
      confirmationRequired,
      automationControl: Boolean(payload.automation_control)
        || steps.some((step) => {
          const actionType = String(step.actionType || "");
          return actionType.startsWith("automation_") && actionType !== "automation_critical_blocked";
        }),
      steps,
    };
  }

  function normalizeActionStepMessage(value, confirmationRequired) {
    const message = String(value || "").trim();
    if (confirmationRequired && /skipped because an earlier step failed/i.test(message)) {
      return "Waiting for approval before this step runs.";
    }
    return message;
  }

  function normalizeActionSuggestions(payload) {
    const suggestions = Array.isArray(payload?.action_suggestions) ? payload.action_suggestions : [];
    return suggestions.map((item) => ({
      kind: String(item?.kind || "").trim(),
      label: String(item?.label || "").trim(),
      text: String(item?.text || "").trim(),
      count: Number(item?.count || 0),
    })).filter((item) => item.text || item.label).slice(0, 3);
  }

  function normalizeStepStatus(value) {
    const status = String(value || "pending").trim().toLowerCase();
    if (["success", "completed", "opened", "searched", "typed", "key_pressed", "hotkey_pressed", "scrolled", "focused"].includes(status)) {
      return "success";
    }
    if (["approved", "confirmed"].includes(status)) {
      return "approved";
    }
    if (["running", "executing"].includes(status)) {
      return "executing";
    }
    if (["interrupted", "stopped", "focus_changed"].includes(status)) {
      return "interrupted";
    }
    if ([
      "blocked",
      "critical_blocked",
      "sensitive_screen_blocked",
      "sensitive_window_blocked",
      "wrong_active_window",
      "expected_ui_not_found",
      "screen_context_unavailable",
      "automation_busy",
      "unsupported",
      "unsupported_key",
      "unsupported_hotkey",
    ].includes(status)) {
      return "blocked";
    }
    if (["failed", "error", "unavailable", "launch_failed", "invalid_url", "invalid_query", "type_failed", "key_failed", "hotkey_failed", "scroll_failed"].includes(status)) {
      return "failed";
    }
    if (["needs_confirmation", "skipped", "pending"].includes(status)) {
      return "pending";
    }
    return "pending";
  }

  function actionStatusLabel(value) {
    const labels = {
      pending: "Pending",
      approved: "Approved",
      executing: "Executing",
      success: "Success",
      failed: "Failed",
      interrupted: "Interrupted",
      blocked: "Blocked",
    };
    return labels[normalizeStepStatus(value)] || "Pending";
  }

  function actionStatusMarker(value, index) {
    const markers = {
      pending: `${index + 1}`,
      approved: "OK",
      executing: "...",
      success: "OK",
      failed: "!",
      interrupted: "II",
      blocked: "NO",
    };
    return markers[normalizeStepStatus(value)] || `${index + 1}`;
  }

  function buildActionPlanCardLegacy(actionPlan, suggestions = []) {
    const card = document.createElement("section");
    card.className = "action-plan-card";

    const head = document.createElement("div");
    head.className = "action-plan-card__head";

    const copy = document.createElement("div");
    const eyebrow = document.createElement("p");
    eyebrow.className = "action-plan-card__eyebrow";
    eyebrow.textContent = "Controlled action plan";
    const title = document.createElement("p");
    title.className = "action-plan-card__title";
    title.textContent = actionPlan.originalCommand || "Browser action";
    copy.append(eyebrow, title);

    const status = document.createElement("span");
    status.className = `action-plan-status action-plan-status--${actionPlan.status}`;
    status.textContent = humanizeBadge(actionPlan.status);
    head.append(copy, status);

    const list = document.createElement("ol");
    list.className = "action-steps";
    actionPlan.steps.forEach((step) => {
      const item = document.createElement("li");
      item.className = `action-step action-step--${step.status}`;

      const marker = document.createElement("span");
      marker.className = "action-step__marker";
      marker.textContent = step.status === "success" ? "OK" : step.status === "failed" ? "!" : "...";

      const details = document.createElement("div");
      details.className = "action-step__details";
      const stepTitle = document.createElement("strong");
      stepTitle.textContent = step.label;
      const stepMeta = document.createElement("span");
      stepMeta.textContent = [
        humanizeBadge(step.actionType),
        step.resultStatus ? humanizeBadge(step.resultStatus) : "",
        step.recovered ? "Recovered safely" : "",
      ].filter(Boolean).join(" | ");
      details.append(stepTitle, stepMeta);
      if (step.message) {
        const message = document.createElement("p");
        message.textContent = step.message;
        details.appendChild(message);
      }

      item.append(marker, details);
      list.appendChild(item);
    });

    card.append(head, list);
    if (actionPlan.automationControl) {
      const warning = document.createElement("div");
      warning.className = `automation-warning${actionPlan.confirmationRequired ? " automation-warning--pending" : ""}`;

      const warningText = document.createElement("p");
      warningText.textContent = actionPlan.confirmationRequired
        ? "Keyboard/mouse control is pending. VORIS will not type, press keys, or scroll until you approve this one action."
        : "Controlled OS automation is visible and limited to whitelisted app windows.";
      warning.appendChild(warningText);

      const actions = document.createElement("div");
      actions.className = "automation-warning__actions";
      if (actionPlan.confirmationRequired) {
        const approve = document.createElement("button");
        approve.type = "button";
        approve.className = "link-button automation-confirm-button";
        approve.textContent = "Allow control once";
        approve.addEventListener("click", () => {
          void approveAutomationControl(actionPlan);
        });
        actions.appendChild(approve);
      }

      const stop = document.createElement("button");
      stop.type = "button";
      stop.className = "link-button automation-stop-button";
      stop.textContent = "Stop control";
      stop.addEventListener("click", () => {
        void stopAutomationControl();
      });
      actions.appendChild(stop);
      warning.appendChild(actions);
      card.appendChild(warning);
    }
    return card;
  }

  function buildActionPlanCard(actionPlan, suggestions = []) {
    const card = document.createElement("section");
    card.className = `action-plan-card action-plan-card--${actionPlan.status}`;

    const head = document.createElement("div");
    head.className = "action-plan-card__head";

    const copy = document.createElement("div");
    const eyebrow = document.createElement("p");
    eyebrow.className = "action-plan-card__eyebrow";
    eyebrow.textContent = actionPlan.automationControl ? "Controlled action plan" : "Action plan";
    const title = document.createElement("p");
    title.className = "action-plan-card__title";
    title.textContent = actionPlan.originalCommand || "Planned action";
    copy.append(eyebrow, title);

    const status = document.createElement("span");
    status.className = `action-plan-status action-plan-status--${actionPlan.status}`;
    status.textContent = actionStatusLabel(actionPlan.status);
    head.append(copy, status);

    const list = document.createElement("ol");
    list.className = "action-steps";
    actionPlan.steps.forEach((step, index) => {
      const item = document.createElement("li");
      item.className = `action-step action-step--${step.status}`;

      const marker = document.createElement("span");
      marker.className = "action-step__marker";
      marker.textContent = actionStatusMarker(step.status, index);

      const details = document.createElement("div");
      details.className = "action-step__details";
      const stepHead = document.createElement("div");
      stepHead.className = "action-step__head";
      const stepTitle = document.createElement("strong");
      stepTitle.textContent = step.label;
      const stepStatus = document.createElement("span");
      stepStatus.className = `action-step__status action-step__status--${step.status}`;
      stepStatus.textContent = actionStatusLabel(step.status);
      stepHead.append(stepTitle, stepStatus);

      const stepMeta = document.createElement("span");
      stepMeta.textContent = [
        humanizeBadge(step.actionType),
        step.resultStatus && step.resultStatus !== step.status ? actionStatusLabel(step.resultStatus) : "",
        step.recovered ? "Recovered safely" : "",
      ].filter(Boolean).join(" | ");
      details.append(stepHead, stepMeta);

      if (step.message) {
        const message = document.createElement("p");
        message.textContent = step.message;
        details.appendChild(message);
      }
      if (step.blockedReason && step.blockedReason !== step.message) {
        const reason = document.createElement("p");
        reason.className = "action-step__reason";
        reason.textContent = step.blockedReason;
        details.appendChild(reason);
      }

      item.append(marker, details);
      list.appendChild(item);
    });

    card.append(head, list);

    const criticalBlocked = actionPlan.steps.some((step) => step.actionType === "automation_critical_blocked");
    const visiblyBlocked = criticalBlocked
      || ["blocked", "failed", "interrupted"].includes(actionPlan.status)
      || actionPlan.steps.some((step) => ["blocked", "failed", "interrupted"].includes(step.status));

    if (actionPlan.automationControl || criticalBlocked || visiblyBlocked) {
      const warning = document.createElement("div");
      warning.className = [
        "automation-warning",
        actionPlan.confirmationRequired ? "automation-warning--pending" : "",
        visiblyBlocked ? "automation-warning--blocked" : "",
      ].filter(Boolean).join(" ");

      const warningText = document.createElement("p");
      warningText.textContent = criticalBlocked
        ? "Blocked for safety. VORIS will not run password, payment, banking, deletion, or credential actions."
        : actionPlan.confirmationRequired
      ? "Approval required. VORIS will not type, press keys, or scroll until you allow this one action."
          : actionPlan.status === "interrupted"
            ? "Control was interrupted. No further keyboard or mouse action will run."
            : visiblyBlocked
              ? "Control did not run because safety validation blocked or failed this path."
              : "Controlled OS automation is limited to whitelisted app windows and visible step results.";
      warning.appendChild(warningText);

      const actions = document.createElement("div");
      actions.className = "automation-warning__actions";
      if (actionPlan.confirmationRequired && !criticalBlocked && !visiblyBlocked) {
        const approve = document.createElement("button");
        approve.type = "button";
        approve.className = "link-button automation-confirm-button";
        approve.textContent = "Allow control once";
        approve.addEventListener("click", () => {
          void approveAutomationControl(actionPlan);
        });
        actions.appendChild(approve);
      }

      if (actionPlan.automationControl && !actionPlan.confirmationRequired && ["pending", "approved", "executing"].includes(actionPlan.status)) {
        const stop = document.createElement("button");
        stop.type = "button";
        stop.className = "link-button automation-stop-button";
        stop.textContent = "Stop control";
        stop.addEventListener("click", () => {
          void stopAutomationControl();
        });
        actions.appendChild(stop);
      }

      if (actions.childElementCount) {
        warning.appendChild(actions);
      }
      card.appendChild(warning);
    }

    const suggestionsBox = buildActionSuggestions(suggestions);
    if (suggestionsBox) {
      card.appendChild(suggestionsBox);
    }
    return card;
  }

  function buildActionSuggestions(suggestions = []) {
    if (!suggestions.length) {
      return null;
    }
    const box = document.createElement("div");
    box.className = "action-suggestions";
    const label = document.createElement("p");
    label.className = "action-suggestions__label";
    label.textContent = "Pattern noticed";
    box.appendChild(label);
    suggestions.forEach((suggestion) => {
      const item = document.createElement("p");
      item.className = "action-suggestions__item";
      item.textContent = suggestion.text || suggestion.label;
      box.appendChild(item);
    });
    return box;
  }

  async function approveAutomationControl(actionPlan) {
    const command = String(actionPlan?.originalCommand || "").trim();
    if (!command || state.requestInFlight) {
      return;
    }
    state.requestInFlight = true;
    setAssistantState("thinking", "automation:confirmation_submitted");
    setComposerStatus("Control approved for this one action.");
    updateWorkspaceSummary("VORIS is running the approved controlled automation path now.");

    appendMessage({
      role: "user",
      text: "Approved keyboard/mouse control for this action.",
      badge: "Confirm",
      timestamp: new Date().toISOString(),
    });

    try {
      const payload = await apiJson("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message: command, mode: "real", confirmed: true }),
      });
      const confirmedPlan = normalizeActionPlanPayload(payload);
      const actionSuggestions = normalizeActionSuggestions(payload);
      state.currentTask = {
        scope: "external",
        label: "Controlled OS automation",
        kind: "os_automation",
        text: command,
        actionPlan: confirmedPlan,
        actionSuggestions,
        launchStatus: payload.action_status || confirmedPlan?.status || "unknown",
        launchMessage: cleanAssistantReply(payload.reply || payload.content),
      };
      state.panelVisible = true;
      state.panelMode = "context";
      setOrbLayout("floating");
      await revealAssistantMessage({
        role: "assistant",
        text: cleanAssistantReply(payload.reply || payload.content) || "Control action finished.",
        badge: humanizeBadge(payload.execution_mode || "os_automation"),
        timestamp: new Date().toISOString(),
        actionPlan: confirmedPlan,
        actionSuggestions,
      }, {
        stateName: payload.action_success ? "responding" : "error",
        event: payload.action_success ? "automation:confirmed_complete" : "automation:confirmed_failed",
      });
      setComposerStatus(payload.action_success ? "Controlled action completed." : "Controlled action did not complete.");
    } catch (error) {
      setAssistantState("error", "automation:confirmation_failed");
      await revealAssistantMessage({
        role: "assistant",
        text: error.message || "I couldn't run the approved control action.",
        badge: "Automation error",
        timestamp: new Date().toISOString(),
      }, {
        delayMs: 220,
        stateName: "error",
        event: "automation:error_revealed",
      });
    } finally {
      state.requestInFlight = false;
      renderRightPanel();
      resetToCalmIdle();
    }
  }

  async function stopAutomationControl() {
    try {
      const payload = await apiJson("/api/os-automation/stop", { method: "POST" });
      const reply = String(payload.message || "Control stop requested.").trim();
      setAssistantState("error", "automation:stop_requested");
      setComposerStatus(reply);
      updateWorkspaceSummary("VORIS has requested the automation stop flag.");
      await revealAssistantMessage({
        role: "assistant",
        text: reply,
        badge: "Stop control",
        timestamp: new Date().toISOString(),
      }, {
        delayMs: 160,
        stateName: "error",
        event: "automation:stop_revealed",
      });
    } catch (error) {
      setAssistantState("error", "automation:stop_failed");
      setComposerStatus(error.message || "I couldn't request stop control.");
    } finally {
      renderRightPanel();
      resetToCalmIdle();
    }
  }

  function renderRightPanel() {
    if (!el.rightPanel || !el.rightPanelBody || !el.rightPanelTitle) {
      return;
    }

    const hasOutputs = state.recentOutputs.length > 0;
    const hasTaskContext = Boolean(state.currentTask);
    const shouldShowPanel = state.panelMode === "profile"
      || (state.panelVisible && (hasOutputs || hasTaskContext));

    if (!shouldShowPanel) {
      setPanelOpen(false);
      el.rightPanel.hidden = true;
      el.rightPanelBody.innerHTML = "";
      return;
    }

    setPanelOpen(true);
    el.rightPanel.hidden = false;
    el.rightPanelBody.innerHTML = "";

    if (state.panelMode === "profile") {
      el.rightPanelTitle.textContent = "Profile";
      el.rightPanelBody.appendChild(buildProfileCard());
      if (state.desktopApps.length) {
        el.rightPanelBody.appendChild(buildDesktopAppsCard());
      }
      return;
    }

    if (state.panelMode === "outputs" && state.recentOutputs.length) {
      el.rightPanelTitle.textContent = "Recent outputs";
    } else if (state.currentTask) {
      el.rightPanelTitle.textContent = state.currentTask.scope === "external" ? "External action" : "Current task";
      el.rightPanelBody.appendChild(buildTaskCard());
    } else {
      el.rightPanelTitle.textContent = "VORIS context";
    }

    if (state.panelMode === "outputs" && state.recentOutputs.length) {
      el.rightPanelBody.appendChild(buildOutputsCard());
    }

    if (!state.currentTask && !state.recentOutputs.length) {
      el.rightPanelBody.appendChild(buildProfileCard(true));
    }
  }

  function setPanelOpen(isOpen) {
    if (el.body) {
      el.body.dataset.panelOpen = isOpen ? "true" : "false";
    }
  }

  function buildProfileCard(compact) {
    const card = document.createElement("section");
    card.className = "panel-card";

    const title = document.createElement("p");
    title.className = "panel-card__title";
    title.textContent = compact ? "Account truth" : "Account and session";

    const body = document.createElement("p");
    body.className = "panel-card__body";
    body.textContent = state.auth?.authenticated
      ? "You're signed in. These are the real account and session details VORIS has right now."
      : "You're using public mode. Protected account work stays unavailable until you sign in.";

    const grid = document.createElement("div");
    grid.className = "panel-card__grid";

    const user = state.auth?.user || {};
    const fields = [
      ["Access mode", state.auth?.authenticated ? "Authenticated" : "Public"],
      ["Name", currentUserName() || "Guest"],
      ["Username", user.username || "Available after sign in"],
      ["Email", user.email || "Available after sign in"],
      ["Session", formatSessionSummary(state.auth)],
      ["Account status", state.auth?.authenticated ? "Signed in" : "Not signed in"],
    ];

    fields.forEach(([label, value]) => {
      const field = document.createElement("div");
      field.className = "panel-field";
      const labelNode = document.createElement("span");
      labelNode.textContent = label;
      const valueNode = document.createElement("strong");
      valueNode.textContent = value;
      field.append(labelNode, valueNode);
      grid.appendChild(field);
    });

    const actions = document.createElement("div");
    actions.className = "panel-actions";
    if (state.auth?.authenticated) {
      const logoutLink = document.createElement("a");
      logoutLink.className = "link-button";
      logoutLink.href = "/logout";
      logoutLink.textContent = "Log out";
      actions.appendChild(logoutLink);
    } else {
      actions.appendChild(buildNavLink("Sign in", "/login"));
      actions.appendChild(buildNavLink("Create account", "/register"));
      actions.appendChild(buildNavLink("Forgot password", "/forgot-password"));
    }

    card.append(title, body, grid, actions);
    return card;
  }

  function buildDesktopAppsCard(compact) {
    const card = document.createElement("section");
    card.className = "panel-card";

    const title = document.createElement("p");
    title.className = "panel-card__title";
    title.textContent = compact ? "Desktop apps" : "Desktop apps";

    const body = document.createElement("p");
    body.className = "panel-card__body";
    body.textContent = compact
      ? "These are the safe desktop apps VORIS can try to launch from this system."
      : "VORIS only launches a small safe allowlist. Availability reflects what the backend can actually find right now.";

    const list = document.createElement("div");
    list.className = "desktop-apps-list";

    state.desktopApps.forEach((app) => {
      const item = document.createElement("div");
      item.className = "desktop-app-item";

      const copy = document.createElement("div");
      copy.className = "desktop-app-item__copy";

      const name = document.createElement("strong");
      name.textContent = app.display_name || app.app_id || "Desktop app";

      const aliases = document.createElement("span");
      const aliasList = Array.isArray(app.aliases) ? app.aliases : [];
      aliases.textContent = aliasList.length ? aliasList.join(", ") : "No aliases";

      copy.append(name, aliases);

      const status = document.createElement("span");
      const isAvailable = Boolean(app.available);
      status.className = `desktop-app-status desktop-app-status--${isAvailable ? "available" : "unavailable"}`;
      status.textContent = isAvailable ? "Available" : "Unavailable";

      item.append(copy, status);
      list.appendChild(item);
    });

    card.append(title, body, list);
    return card;
  }

  function buildTaskCard() {
    const card = document.createElement("section");
    card.className = "panel-card";

    const title = document.createElement("p");
    title.className = "panel-card__title";
    title.textContent = state.currentTask.scope === "external"
      ? "External routing"
      : "Active workspace task";

    const body = document.createElement("p");
    body.className = "panel-card__body";
    body.textContent = state.currentTask.scope === "external"
      ? "VORIS routed this outside the workspace and stayed nearby in floating presence mode."
      : "VORIS kept this inside the workspace so the work can stay focused here.";

    const grid = document.createElement("div");
    grid.className = "panel-card__grid";
    const fields = [
      ["Task label", state.currentTask.label],
      ["Scope", capitalize(state.currentTask.scope)],
      ["Request", state.currentTask.text],
      ["Orb layout", humanizeBadge(state.orbLayout)],
    ];

    if (state.currentTask.scope === "external" && state.currentTask.launchStatus) {
      fields.push(["Launch status", humanizeBadge(state.currentTask.launchStatus)]);
    }

    fields.forEach(([label, value]) => {
      const field = document.createElement("div");
      field.className = "panel-field";
      const labelNode = document.createElement("span");
      labelNode.textContent = label;
      const valueNode = document.createElement("strong");
      valueNode.textContent = value;
      field.append(labelNode, valueNode);
      grid.appendChild(field);
    });

    card.append(title, body, grid);
    if (state.currentTask.actionPlan) {
      card.appendChild(buildActionPlanCard(state.currentTask.actionPlan, state.currentTask.actionSuggestions || []));
    }
    if (state.currentTask.scope === "external" && state.currentTask.launchMessage) {
      const note = document.createElement("p");
      note.className = "panel-card__body";
      note.textContent = state.currentTask.launchMessage;
      card.appendChild(note);
    }
    return card;
  }

  function buildScreenShareCard() {
    const card = document.createElement("section");
    card.className = "panel-card";

    const title = document.createElement("p");
    title.className = "panel-card__title";
    title.textContent = "Screen share";

    const body = document.createElement("p");
    body.className = "panel-card__body";
    body.textContent = state.screenShareActive
      ? "Screen capture is active. VORIS reflects that state clearly, but it still does not claim live visual understanding."
      : "Screen capture is off. If you start it, VORIS will only reflect the capture state honestly.";

    const grid = document.createElement("div");
    grid.className = "panel-card__grid";
    [
      ["Status", state.screenShareActive ? "Active" : "Off"],
      ["Source", state.screenShareLabel || "Off"],
      ["Vision truth", "UI capture only - analysis not implemented"],
    ].forEach(([label, value]) => {
      const field = document.createElement("div");
      field.className = "panel-field";
      const labelNode = document.createElement("span");
      labelNode.textContent = label;
      const valueNode = document.createElement("strong");
      valueNode.textContent = value;
      field.append(labelNode, valueNode);
      grid.appendChild(field);
    });

    card.append(title, body, grid);
    return card;
  }

  function buildOutputsCard() {
    const card = document.createElement("section");
    card.className = "panel-card";

    const title = document.createElement("p");
    title.className = "panel-card__title";
    title.textContent = "Recent outputs";

    const body = document.createElement("p");
    body.className = "panel-card__body";
    body.textContent = "Finished work stays here with previews and direct downloads when you need it again.";

    const list = document.createElement("div");
    list.className = "panel-card__grid";
    state.recentOutputs.forEach((delivery) => {
      list.appendChild(buildDocumentCard(delivery));
    });

    card.append(title, body, list);
    return card;
  }

  function buildNavLink(label, href) {
    const link = document.createElement("a");
    link.className = "link-button";
    link.href = href;
    link.textContent = label;
    return link;
  }

  function renderSidebarSessions() {
    if (!el.chatList || !el.chatListEmpty || !el.historyMeta) {
      return;
    }

    const visibleSessions = buildVisibleSessions();
    const filtered = visibleSessions.filter((session) => {
      if (!state.sidebarSearch) {
        return true;
      }
      const haystack = `${session.session_id} ${session.title || ""}`.toLowerCase();
      return haystack.includes(state.sidebarSearch);
    });

    el.chatList.innerHTML = "";
    el.historyMeta.textContent = `${visibleSessions.length} session${visibleSessions.length === 1 ? "" : "s"}`;
    el.chatListEmpty.hidden = filtered.length > 0;

    filtered.forEach((session) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `session-item${session.session_id === state.sessionId ? " is-active" : ""}`;
      button.addEventListener("click", async () => {
        if (session.session_id === state.sessionId) {
          return;
        }
        state.sessionId = session.session_id;
        localStorage.setItem(STORAGE_KEYS.sessionId, state.sessionId);
        await loadConversation(state.sessionId);
        state.currentTask = null;
        state.currentExternal = null;
        setTaskScope("none");
        setOrbLayout("topbar");
        setAssistantState("idle", "session:conversation_loaded");
        hidePresence(true);
        setComposerStatus("Conversation loaded. I'm here.");
        updateWorkspaceSummary("This workspace is ready again.");
        renderSidebarSessions();
        renderConversation();
        renderRightPanel();
        updateWorkspaceChrome();
      });

      const title = document.createElement("span");
      title.className = "session-item__title";
      title.textContent = session.title || `Chat ${shortSessionId(session.session_id)}`;

      const meta = document.createElement("span");
      meta.className = "session-item__meta";
      meta.innerHTML = `<span>${session.message_count || 0} messages</span><span>${formatSessionStamp(session.last_timestamp || session.started_at)}</span>`;

      button.append(title, meta);
      el.chatList.appendChild(button);
    });
  }

  function buildVisibleSessions() {
    const sessions = (Array.isArray(state.sessions) ? state.sessions : []).map((session) => ({
      ...session,
      title: state.sessionTitles[session.session_id] || "",
    }));
    if (!sessions.some((session) => session.session_id === state.sessionId)) {
      sessions.unshift({
        session_id: state.sessionId,
        title: state.sessionTitles[state.sessionId] || "Current chat",
        started_at: new Date().toISOString(),
        last_timestamp: new Date().toISOString(),
        message_count: state.messages.length,
      });
    }
    return sessions;
  }

  function startNewChat() {
    state.sessionId = generateSessionId();
    localStorage.setItem(STORAGE_KEYS.sessionId, state.sessionId);
    state.messages = [];
    state.currentTask = null;
    state.currentExternal = null;
    setTaskScope("none");
    state.panelVisible = false;
    state.panelMode = "";
    state.screenShareLabel = state.screenShareActive ? state.screenShareLabel : "Off";
    setOrbLayout("topbar");
    setAssistantState("idle", "chat:new_session_started");
    hidePresence(true);
    setComposerStatus("New chat ready. I'm here when you are.");
    updateWorkspaceSummary("A fresh VORIS workspace is ready for the next thing you want handled.");
    renderSidebarSessions();
    renderConversation();
    renderRightPanel();
    updateWorkspaceChrome();
  }

  async function toggleScreenShare() {
    state.screenShareActive = false;
    state.screenShareLabel = "Unavailable";
    setAssistantState("error", "ui:screen_capture_disabled");
    setComposerStatus("Screen capture is disabled in this shell.");
    updateWorkspaceSummary("This interface stays focused on chat, push-to-talk voice, and document generation.");
    showPresence({
      mode: state.currentTask?.scope === "external" ? "floating" : "docked",
      eyebrow: "Screen capture",
      title: "I couldn't complete that yet.",
      text: "Screen capture is hidden here until it becomes a real supported workflow.",
      duration: 2200,
    });
    renderRightPanel();
  }

  function stopScreenShare() {
    if (state.screenStream) {
      state.screenStream.getTracks().forEach((track) => track.stop());
    }
    state.screenStream = null;
    state.screenShareActive = false;
    state.screenShareLabel = "Off";
    el.screenShareButton?.classList.remove("is-active");
    setComposerStatus("Screen capture is off.");
    updateWorkspaceSummary("VORIS is ready for chat, push-to-talk voice, and document generation.");
    showPresence({
      mode: state.currentTask?.scope === "external" ? "floating" : "docked",
      eyebrow: "Screen capture",
      title: "Screen capture is off.",
      text: "VORIS is back to its normal workspace presence.",
      duration: 1500,
    });
    renderRightPanel();
    updateWorkspaceChrome();
  }

  async function processRecognizedTranscript(transcript, mode) {
    const spokenText = String(transcript || "").trim();
    if (!spokenText) {
      return;
    }

    if (mode === "wake") {
      const wakeMatch = detectWakePhrase(spokenText);
      if (!wakeMatch.detected) {
        state.wakeModeEnabled = false;
        syncVoiceControls();
        setComposerStatus('Wake beta listened once, but "Hey VORIS" was not detected.');
        setAssistantState("idle", "wake:phrase_not_detected");
        showPresence({
          mode: "center",
          eyebrow: "Wake beta",
          title: "I didn't catch the wake phrase.",
          text: 'Try "Hey VORIS" again when you want me.',
          duration: 1700,
        });
        settleToIdleLayout();
        return;
      }
      await runWakeSequence();
      state.wakeModeEnabled = false;
      syncVoiceControls();
      if (wakeMatch.remainingText) {
        appendMessage({
          role: "user",
          text: spokenText,
          badge: "Voice",
          timestamp: new Date().toISOString(),
        });
        rememberSessionTitle(spokenText);
        updateVoiceTranscript(wakeMatch.remainingText, { final: true });
        const classification = classifyCommand(wakeMatch.remainingText);
        if (classification.kind === "external") {
          await handleExternalCommand(wakeMatch.remainingText, classification);
        } else {
          await handleInternalCommand(wakeMatch.remainingText, classification);
        }
      }
      return;
    }

    appendMessage({
      role: "user",
      text: spokenText,
      badge: "Voice",
      timestamp: new Date().toISOString(),
    });
    rememberSessionTitle(spokenText);
    updateVoiceTranscript(spokenText, { final: true });
    const commandText = spokenText;

    setAssistantState("analyzing", "voice:transcript_ready_for_chat");
    setComposerStatus(`Heard: "${commandText}". Sending it now.`);
    updateWorkspaceSummary("VORIS captured your voice request and is sending it now.");

    const classification = classifyCommand(commandText);
    state.speechCommandInFlight = true;
    state.speechEnabled = true;
    localStorage.setItem(STORAGE_KEYS.speechEnabled, "true");
    syncAssistantModeChrome();
    try {
      if (classification.kind === "external") {
        await handleExternalCommand(commandText, classification);
        return;
      }

      await handleInternalCommand(commandText, classification);
    } finally {
      state.speechCommandInFlight = false;
      syncAssistantModeChrome();
    }
  }

  async function startSpeechCapture(mode) {
    if (state.requestInFlight) {
      setComposerStatus("Wait for the current response to finish before using voice.");
      return;
    }
    if (!state.voiceSupported || !RecognitionCtor) {
      surfaceVoiceFailure(
        "Voice input needs Chrome or Edge on localhost/HTTPS with microphone permission enabled.",
        {
          event: "voice:unsupported",
          title: "Voice input is unavailable.",
          text: "Use Chrome or Edge and allow microphone access.",
        },
      );
      return;
    }
    if (state.recognitionActive) {
      stopRecognition("Listening stopped.");
      return;
    }

    stopSpeaking("voice:listen_started");
    clearVoiceTranscript();
    const permissionState = await getMicrophonePermissionState();
    if (permissionState === "denied") {
      surfaceVoiceFailure("Microphone permission is blocked. Allow microphone access in the browser, then press the mic again.", {
        event: "voice:permission_denied",
        title: "Microphone is blocked.",
      });
      return;
    }

    const recognition = new RecognitionCtor();
    let finalTranscript = "";
    let failed = false;
    state.recognition = recognition;
    state.recognitionMode = mode || "talk";
    state.recognitionStopReason = "";

    recognition.lang = state.voiceStatus?.settings?.language || navigator.language || "en-US";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      state.recognitionActive = true;
      setAssistantState("listening", "voice:push_to_talk_started");
      setComposerStatus("Listening. Speak naturally.");
      updateWorkspaceSummary("VORIS is listening through your browser microphone.");
      updateVoiceTranscript("Listening...", { final: false });
      syncVoiceControls();
    };

    recognition.onresult = (event) => {
      let interimTranscript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = String(result?.[0]?.transcript || "").trim();
        if (!transcript) {
          continue;
        }
        if (result.isFinal) {
          finalTranscript = `${finalTranscript} ${transcript}`.trim();
        } else {
          interimTranscript = `${interimTranscript} ${transcript}`.trim();
        }
      }
      updateVoiceTranscript([finalTranscript, interimTranscript].filter(Boolean).join(" "), {
        final: Boolean(finalTranscript && !interimTranscript),
      });
    };

    recognition.onerror = (event) => {
      failed = true;
      state.recognitionActive = false;
      state.recognitionMode = "";
      state.recognition = null;
      const detail = formatSpeechErrorDetail(event);
      surfaceVoiceFailure(detail, {
        event: "voice:recognition_error",
        keepTranscript: true,
        resetMs: 1400,
      });
      syncVoiceControls();
    };

    recognition.onend = () => {
      const transcript = finalTranscript.trim();
      state.recognitionActive = false;
      state.recognitionMode = "";
      state.recognition = null;
      syncVoiceControls();
      if (failed || state.recognitionStopReason === "manual") {
        return;
      }
      if (!transcript) {
        setComposerStatus("I did not hear anything clearly. Press the mic and try again.");
        setAssistantState("idle", "voice:no_transcript");
        settleToIdleLayout();
        return;
      }
      void processRecognizedTranscript(transcript, mode || "talk");
    };

    try {
      recognition.start();
    } catch (error) {
      state.recognitionActive = false;
      state.recognitionMode = "";
      state.recognition = null;
      syncVoiceControls();
      surfaceVoiceFailure(voiceFailureMessageFromError(error, "Voice input could not start."), {
        event: "voice:start_failed",
      });
    }
  }

  function stopRecognition(statusMessage) {
    logVoiceDebug("stopRecognition()", {
      recognitionExists: Boolean(state.recognition),
      statusMessage: statusMessage || "",
    });
    state.recognitionStopReason = "manual";
    if (state.recognition) {
      try {
        state.recognition.stop();
      } catch (_error) {
        // Ignore browser stop errors.
      }
    }
    state.recognitionActive = false;
    state.recognitionMode = "";
    if (statusMessage) {
      setComposerStatus(statusMessage);
    }
    syncVoiceControls();
  }

  function setAssistantState(name, event = "system:unspecified") {
    const nextState = name in STATE_COPY ? name : "idle";
    const nextEvent = String(event || "system:unspecified");
    const shouldLog = state.assistantState !== nextState || state.assistantStateEvent !== nextEvent;

    state.assistantState = nextState;
    state.assistantStateEvent = nextEvent;
    el.body.dataset.assistantState = state.assistantState;
    const copy = STATE_COPY[state.assistantState];

    if (shouldLog) {
      logOrbState(nextState, nextEvent);
      triggerOrbStateShift();
    }

    if (el.stateChipLabel) {
      el.stateChipLabel.textContent = copy.label;
    }
    if (el.sidebarState) {
      el.sidebarState.textContent = copy.sidebar;
    }
    if (el.orbStateLabel) {
      el.orbStateLabel.textContent = copy.label;
    }
    if (el.orbModeLabel) {
      el.orbModeLabel.textContent = orbModeLabel(state.orbLayout, copy.orb);
    }
    syncAssistantModeChrome();
  }

  function setOrbLayout(layout) {
    if (state.orbLayout !== layout) {
      pulseOrbClass("assistant-orb--moving", 760);
    }
    state.orbLayout = layout;
    el.body.dataset.orbLayout = layout;
    if (el.orbModeLabel) {
      el.orbModeLabel.textContent = orbModeLabel(layout, STATE_COPY[state.assistantState]?.orb);
    }
  }

  function settleToIdleLayout() {
    if (state.currentTask?.scope === "external") {
      setTaskScope("external");
      setOrbLayout("floating");
      return;
    }
    if (state.currentTask?.scope === "internal" && state.messages.length) {
      if (state.currentTask.kind === "chat") {
        setTaskScope("none");
        setOrbLayout("topbar");
        return;
      }
      setTaskScope("internal");
      setOrbLayout("left");
      return;
    }
    setTaskScope("none");
    setOrbLayout("topbar");
  }

  function updateWorkspaceChrome() {
    if (el.accessChip) {
      el.accessChip.textContent = state.auth?.authenticated ? "Authenticated" : "Public";
    }
    if (el.profileEntryName) {
      el.profileEntryName.textContent = currentUserName() || "Guest";
    }
    if (el.profileEntryStatus) {
      el.profileEntryStatus.textContent = state.auth?.authenticated ? "Signed in" : "Public mode";
    }
    if (el.screenChipLabel) {
      el.screenChipLabel.textContent = state.screenShareActive ? "On" : "Off";
    }
    if (!el.workspaceSummary?.textContent) {
      updateWorkspaceSummary("VORIS is ready for chat, documents, and safe app actions.");
    }
    if (el.composerStatus && !state.requestInFlight && !state.recognitionActive && !state.speechCommandInFlight) {
      el.composerStatus.textContent = state.auth?.authenticated
        ? "Message VORIS. Talk is beta when available."
        : "Message VORIS. Click the orb to wake.";
    }
  }

  function updateWorkspaceSummary(message) {
    if (el.workspaceSummary) {
      el.workspaceSummary.textContent = message;
    }
  }

  function setComposerStatus(message) {
    if (el.composerStatus) {
      el.composerStatus.textContent = message;
    }
  }

  function autoResizeTextarea() {
    if (!el.messageInput) {
      return;
    }
    el.messageInput.style.height = "auto";
    el.messageInput.style.height = `${Math.min(el.messageInput.scrollHeight, 180)}px`;
  }

  function handleComposerKeydown(event) {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
      return;
    }
    event.preventDefault();
    if (state.requestInFlight) {
      return;
    }
    el.composerForm?.requestSubmit();
  }

  function handleOrbActivation() {
    if (state.requestInFlight || state.recognitionActive || state.speechCommandInFlight) {
      return;
    }
    triggerOrbRipple();
    void runWakeSequence().then(() => {
      resetToCalmIdle(1800);
      window.setTimeout(() => {
        el.messageInput?.focus();
      }, 120);
    });
  }

  function ensureSessionId() {
    const existing = localStorage.getItem(STORAGE_KEYS.sessionId);
    if (existing) {
      return existing;
    }
    const created = generateSessionId();
    localStorage.setItem(STORAGE_KEYS.sessionId, created);
    return created;
  }

  function generateSessionId() {
    return `v2-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function rememberSessionTitle(text) {
    if (!state.sessionTitles[state.sessionId]) {
      state.sessionTitles[state.sessionId] = buildTitleSnippet(text);
      persistSessionTitles();
      renderSidebarSessions();
    }
  }

  function deriveSessionTitle(messages) {
    const firstUser = (Array.isArray(messages) ? messages : []).find((message) => message.role === "user" && message.text);
    return firstUser ? buildTitleSnippet(firstUser.text) : "";
  }

  function buildTitleSnippet(text) {
    return String(text || "").replace(/\s+/g, " ").trim().slice(0, 46) || "Untitled chat";
  }

  function readSessionTitles() {
    try {
      const payload = JSON.parse(localStorage.getItem(STORAGE_KEYS.sessionTitles) || "{}");
      return payload && typeof payload === "object" ? payload : {};
    } catch (_error) {
      return {};
    }
  }

  function readSpeechEnabled() {
    return localStorage.getItem(STORAGE_KEYS.speechEnabled) === "true";
  }

  function persistSessionTitles() {
    localStorage.setItem(STORAGE_KEYS.sessionTitles, JSON.stringify(state.sessionTitles));
  }

  async function apiJson(url, options) {
    const response = await fetch(url, {
      method: options?.method || "GET",
      credentials: "same-origin",
      headers: {
        "Content-Type": options?.body ? "application/json" : "application/json",
        "X-VORIS-Session-Id": state.sessionId,
        ...(options?.headers || {}),
      },
      body: options?.body,
      signal: options?.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || payload.detail || `Request failed (${response.status})`);
    }
    return payload;
  }

  function currentUserName() {
    const user = state.auth?.user || {};
    return user.preferred_name || user.name || user.username || "";
  }

  function buildWakeGreeting() {
    const name = currentUserName();
    return name ? `Hey ${name}, I'm here.` : "Hey, I'm here.";
  }

  function normalizeWakeText(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[.,/#!$%^&*;:{}=_`~()?"']/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function detectWakePhrase(text) {
    const normalized = normalizeWakeText(text);
    const pattern = new RegExp(`^(?:${escapeRegex(WAKE_FALLBACK)})(?:\\s+|$)`);
    if (!pattern.test(normalized)) {
      return { detected: false, remainingText: normalized };
    }
    return {
      detected: true,
      remainingText: normalized.replace(pattern, "").trim(),
    };
  }

  function humanizeSpeechError(code) {
    const messages = {
      "no-speech": "I did not hear anything clearly enough to continue.",
      aborted: "Listening was stopped.",
      "audio-capture": "No microphone input is available.",
      "not-allowed": "Mic permission denied.",
      "service-not-allowed": "Mic permission denied.",
      network: "The browser speech service is unavailable right now.",
    };
    return messages[String(code || "").toLowerCase()] || "The voice path could not continue.";
  }

  function formatSpeechErrorDetail(event) {
    const code = String(event?.error || "").trim();
    const message = String(event?.message || "").trim();
    if (message && code) {
      return `${message} (${code})`;
    }
    if (message) {
      return message;
    }
    if (code) {
      return `${humanizeSpeechError(code)} (${code})`;
    }
    return "The voice path could not continue.";
  }

  function voiceFailureMessageFromError(error, fallback) {
    const message = String(error?.message || "").trim();
    return message || fallback || "The voice path could not continue.";
  }

  function surfaceVoiceFailure(message, options = {}) {
    const detail = String(message || "").trim() || "The voice path could not continue.";
    setAssistantState("error", options.event || "voice:failure");
    setComposerStatus(detail);
    if (options.workspaceSummary) {
      updateWorkspaceSummary(options.workspaceSummary);
    }
    showPresence({
      mode: options.mode || "center",
      eyebrow: options.eyebrow || "Voice input",
      title: options.title || "I couldn't complete that yet.",
      text: detail,
      duration: options.duration || 2200,
    });
    if (!options.keepTranscript) {
      clearVoiceTranscript();
    }
    if (options.resetMs !== false) {
      resetToCalmIdle(options.resetMs || 1600);
    }
  }

  function formatSessionSummary(authPayload) {
    const remaining = Number(authPayload?.session_remaining_seconds);
    if (authPayload?.session_valid && Number.isFinite(remaining) && remaining > 0) {
      if (remaining >= 3600) {
        return `Active for about ${Math.max(1, Math.round(remaining / 3600))}h more`;
      }
      return `Active for about ${Math.max(1, Math.round(remaining / 60))}m more`;
    }
    if (authPayload?.session_valid) {
      return "Active";
    }
    return authPayload?.authenticated ? "Signed in, session status unavailable" : "No active sign-in";
  }

  function humanizeDocumentTitle(type) {
    const normalized = String(type || "document").trim().toLowerCase();
    if (normalized === "assignment") {
      return "Assignment delivery";
    }
    if (normalized === "notes") {
      return "Notes delivery";
    }
    return `${capitalize(normalized)} delivery`;
  }

  function humanizeBadge(value) {
    const text = String(value || "").replace(/[_-]+/g, " ").trim();
    const normalized = text.toLowerCase();
    const direct = {
      pending: "Pending",
      approved: "Approved",
      confirmed: "Approved",
      executing: "Executing",
      running: "Executing",
      success: "Success",
      completed: "Success",
      failed: "Failed",
      error: "Attention",
      interrupted: "Interrupted",
      stopped: "Interrupted",
      blocked: "Blocked",
      "critical blocked": "Blocked",
      "needs confirmation": "Approval required",
      "degraded assistant": "Limited response",
      fallback: "Limited response",
      "fallback llm": "Limited response",
      "provider error": "Limited response",
      "rate limited": "Limited response",
      "action plan": "Action",
      "external action": "Action",
      "external desktop": "Action",
      "os automation": "Control",
      "automation control": "Control",
      "automation confirm": "Approval",
      "automation type": "Control",
      "automation press key": "Control",
      "automation hotkey": "Control",
      "automation scroll": "Control",
      "automation critical blocked": "Blocked",
      "desktop open": "Open app",
      "browser search": "Search",
      "browser open url": "Open website",
      "browser navigate url": "Open website",
      "browser open result": "Open result",
      "browser new tab": "New tab",
      "browser rerun search": "Search",
    };
    if (direct[normalized]) {
      return direct[normalized];
    }
    if (["assistant llm", "fallback llm", "conversation llm", "casual local", "general", "chat"].includes(normalized)) {
      return "Assistant";
    }
    if (normalized.includes("degraded") || normalized.includes("fallback") || normalized.includes("provider")) {
      return "Limited response";
    }
    if (normalized.includes("document")) {
      return "Document";
    }
    if (normalized.includes("action plan") || normalized.includes("browser action")) {
      return "Action";
    }
    if (normalized.includes("os automation")) {
      return "Control";
    }
    return text ? text.replace(/\b\w/g, (character) => character.toUpperCase()) : "Assistant";
  }

  function orbModeLabel(layout, fallback) {
    const labels = {
      topbar: "Header presence",
      center: "Wake focus",
      left: "Workspace active",
      floating: "External presence",
    };
    return labels[layout] || fallback || "Header presence";
  }

  function shortSessionId(sessionId) {
    const value = String(sessionId || "").trim();
    return value.length > 14 ? value.slice(-14) : value;
  }

  function formatSessionStamp(value) {
    if (!value) {
      return "Just now";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "Recent";
    }
    return new Intl.DateTimeFormat([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  function formatClock(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "now";
    }
    return new Intl.DateTimeFormat([], {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  function scrollConversationToBottom() {
    const scroll = () => {
      if (el.chatScroll) {
        el.chatScroll.scrollTo({
          top: el.chatScroll.scrollHeight,
          behavior: "smooth",
        });
      }
    };
    window.requestAnimationFrame(() => {
      scroll();
      window.requestAnimationFrame(scroll);
    });
  }

  function delay(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  function capitalize(value) {
    const text = String(value || "").trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
  }

  function escapeRegex(value) {
    return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
})();


// ==========================================
// VORIS FILE ATTACHMENT SYSTEM
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("file-upload-input");
    const composerForm = document.getElementById("composerForm");
    const inputRow = document.querySelector(".composer__main-input-row");
    const messageInput = document.getElementById("messageInput");

    // Global variable to hold our file until the user clicks Send
    window.vorisAttachedFile = null;

    if (fileInput && composerForm && inputRow) {
        fileInput.addEventListener("change", function(event) {
            const file = event.target.files[0];
            if (!file) return;

            console.log("[VORIS RAG] File grabbed:", file.name, "Size:", file.size);
            window.vorisAttachedFile = file;

            // 1. Wipe out any old previews if they attach a new file
            const oldPreview = document.getElementById("voris-file-preview");
            if (oldPreview) oldPreview.remove();

            // 2. Create the sleek preview chip
            const previewChip = document.createElement("div");
            previewChip.id = "voris-file-preview";
            previewChip.style.cssText = "display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: rgba(255, 255, 255, 0.05); border-radius: 8px; margin-bottom: 10px; width: fit-content; border: 1px solid rgba(255,255,255,0.1);";

            // 3. Add the file icon and name
            const fileText = document.createElement("span");
            // If it's an image, show an image emoji, otherwise a paperclip
            const icon = file.type.startsWith("image/") ? "🖼️" : "📎";
            fileText.textContent = `${icon} ${file.name}`;
            fileText.style.cssText = "font-size: 13px; color: #a1a1aa; font-family: 'IBM Plex Mono', monospace;";

            // 4. Add a tiny "X" button to cancel the upload
            const removeBtn = document.createElement("button");
            removeBtn.innerHTML = "✖";
            removeBtn.title = "Remove attachment";
            removeBtn.style.cssText = "background: none; border: none; color: #ef4444; cursor: pointer; padding: 0 4px; font-size: 12px; margin-left: 5px;";
            
            removeBtn.onclick = function() {
                window.vorisAttachedFile = null;
                fileInput.value = ""; // Clear the hidden HTML input
                previewChip.remove(); // Delete the visual chip
            };

            // 5. Put it all together and inject it just above the typing area
            previewChip.appendChild(fileText);
            previewChip.appendChild(removeBtn);
            composerForm.insertBefore(previewChip, inputRow);

            // Give the keyboard cursor back to the text box automatically
            if (messageInput) messageInput.focus();
        });
    }
});
