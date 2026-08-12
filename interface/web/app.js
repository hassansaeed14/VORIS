(() => {
  const STORAGE_KEYS = {
    sessionId: "aura_live_session_id",
    detailsOpen: "aura_details_open",
  };

  const FALLBACK_REPLY = "Something went wrong on my side. Try again.";
  const WAKE_FALLBACK = "Hey VORIS";
  const DEFAULT_WAKE_GREETING = "Hey. I'm here.";
  const COMMAND_NO_SPEECH_RETRY_LIMIT = 1;
  const CHAT_REQUEST_TIMEOUT_MS = 90000;
  const REFRESH_INTERVAL_MS = 120000;
  const WAKE_RESUME_DELAY_MS = 900;
  const NO_SPEECH_RECOVERY_DELAY_MS = 1400;
  const RECOGNITION_IDLE_TIMEOUT_MS = 1500;
  const IDLE_MINIMIZE_DELAY_MS = 120000; // 2 minutes

  const ORB_COLORS = {
    blue:   { primary: "#7ed6ff", glow: "rgba(126,214,255,0.22)", outer: "rgba(61,134,199,0.16)",  soft: "rgba(126,214,255,0.16)", border: "rgba(126,214,255,0.22)" },
    red:    { primary: "#ef8794", glow: "rgba(239,135,148,0.22)", outer: "rgba(161,44,62,0.16)",   soft: "rgba(239,135,148,0.16)", border: "rgba(239,135,148,0.22)" },
    green:  { primary: "#6ad7a0", glow: "rgba(106,215,160,0.22)", outer: "rgba(47,130,91,0.16)",   soft: "rgba(106,215,160,0.16)", border: "rgba(106,215,160,0.22)" },
    purple: { primary: "#c084fc", glow: "rgba(192,132,252,0.22)", outer: "rgba(109,40,217,0.16)",  soft: "rgba(192,132,252,0.16)", border: "rgba(192,132,252,0.22)" },
    gold:   { primary: "#f3c56f", glow: "rgba(243,197,111,0.22)", outer: "rgba(196,120,28,0.16)",  soft: "rgba(243,197,111,0.16)", border: "rgba(243,197,111,0.22)" },
    cyan:   { primary: "#67e8f9", glow: "rgba(103,232,249,0.22)", outer: "rgba(21,148,168,0.16)",  soft: "rgba(103,232,249,0.16)", border: "rgba(103,232,249,0.22)" },
    white:  { primary: "#f5f8fd", glow: "rgba(245,248,253,0.18)", outer: "rgba(200,210,230,0.12)", soft: "rgba(245,248,253,0.14)", border: "rgba(245,248,253,0.2)"  },
  };

  const state = {
    sessionId: "default",
    detailsOpen: false,
    auth: null,
    providerSnapshot: null,
    systemHealth: null,
    voiceStatus: null,
    currentProvider: null,
    providerRefreshInFlight: false,
    voicePhase: "idle",
    wakeModeEnabled: false,
    wakeModeGestureNeeded: false,
    wakeStandbyActive: false,
    recognition: null,
    recognitionActive: false,
    recognitionMode: "off",
    recognitionHandoffPending: false,
    listening: false,
    speaking: false,
    busy: false,
    voiceActionInFlight: false,
    activeSpeechRunId: 0,
    currentUtterance: null,
    recognitionStopReason: "idle",
    bargeInArmed: false,
    bargeInTriggered: false,
    currentSpokenText: "",
    partialTranscript: "",
    commandRetryCount: 0,
    currentRequestController: null,
    refreshInFlight: false,
    refreshQueuedForce: false,
    refreshIntervalId: null,
    lastStatusRefreshAt: 0,
    recognitionStartTimer: null,
    activity: [],
    activeNav: "chat",
    orbColor: "blue",
    idleMinimized: false,
    idleTimer: null,
    overlayMode: false,
    screenSharing: false,
    screenStream: null,
    orbLayout: "topbar",
    chatLocked: false,
    chatMessages: [],
    archivedChats: [],
    pendingSecurityPayload: null,
    pendingSecurityResolve: null,
    pendingSecurityReject: null,
    browserVoice: {
      mode: "Checking",
      permission: "Checking",
      inputDevice: "Checking",
      lastTranscript: "No data yet",
      lastIssue: "No issues yet",
      lastEvent: "idle",
      heardSpeech: false,
    },
  };

  const el = {};

  document.addEventListener("DOMContentLoaded", () => {
    void init();
  });

  async function init() {
    cacheDom();
    state.sessionId = ensureSessionId();
    state.detailsOpen = readBoolean(STORAGE_KEYS.detailsOpen, window.innerWidth >= 1200);
    bindEvents();
    syncDetailsDrawer();
    setupRecognition();
    loadSavedOrbColor();
    setOrbLayout("topbar");
    switchNav("chat");
    resetIdleTimer();
    renderConversationThread();
    renderArchivedChats();
    await refreshBrowserVoiceDiagnostics({ requestPermission: false });
    renderProviderList();
    renderActivityList();
    setAssistantState("idle", {
      pill: "Idle",
      kicker: "Standby",
      headline: "Ready when you are.",
      description: `Say "${preferredWakePhrase()}" after wake mode is active, or use Talk and the text command field below.`,
    });
    updateLiveTranscript("Waiting for your voice or text command.");
    updateLiveResponse("VORIS is standing by.");
    updateWakeBanner("Checking voice and provider status...");
    await bootstrap();
    scheduleRefresh();
  }

  function cacheDom() {
    const ids = [
      "presenceSummary",
      "statePillLabel",
      "detailsToggle",
      "mobileBackdrop",
      "assistantCoreButton",
      "stateKicker",
      "stateHeadline",
      "stateDescription",
      "liveTranscript",
      "liveResponse",
      "documentDeliveryPanel",
      "responseMetaProvider",
      "responseMetaMode",
      "detailsDrawer",
      "refreshStatusButton",
      "accessMode",
      "brainState",
      "activeProvider",
      "wakeModeStatus",
      "routeSummary",
      "providersList",
      "browserVoiceMode",
      "micPermissionState",
      "inputDeviceSummary",
      "lastTranscriptSummary",
      "lastVoiceIssue",
      "accountSummary",
      "authActionLink",
      "adminLink",
      "activityList",
      "wakeBanner",
      "wakeModeButton",
      "talkButton",
      "interruptButton",
      "textCommandInput",
      "sendButton",
      // new elements
      "orbMini",
      "navChat", "navMemory", "navTools", "navProfile", "navSettings",
      "navBrandSub", "navNewChat", "navConversations", "navConvEmpty",
      "navUserName", "navUserStatus",
      "chatView",
      "panelMemory", "panelTools", "panelProfile", "panelSettings",
      "colorSwatches",
      "screenShareButton", "screenShareBadge", "screenShareStatus",
      "screenPreviewWrap", "screenPreviewVideo",
      "outputList",
      "livePanels",
      "profileAuthLink", "profileRegisterLink", "profilePasswordLink", "profileSummaryText",
      "profileGuestView", "profileUserView",
      "profileWelcome", "profileFieldName", "profileFieldEmail", "profileFieldPhone", "profileFieldSession",
      "profileLogoutLink",
      "profileOtpRow", "profileOtpToggle", "profileOtpLabel",
      "idleSuggestions", "overlayToggle",
      "settingsClearHistory", "settingsVoiceLang",
      "clearMemoryBtn",
      "toolGrid",
      "memEpisodic", "memSemantic", "memWorking",
      "archiveCurrentChat", "navArchiveList", "navArchiveEmpty", "lockChatButton",
      "conversationThread", "conversationEmpty",
      // security modals
      "modalConfirm", "modalConfirmReason", "modalConfirmHint", "modalConfirmCancel", "modalConfirmOk",
      "modalSession", "modalSessionReason", "modalSessionHint", "modalSessionCancel", "modalSessionApprove",
      "modalPin", "modalPinReason", "modalPinHint", "modalPinInput", "modalPinError", "modalPinCancel", "modalPinSubmit",
    ];

    ids.forEach((id) => {
      el[id] = document.getElementById(id);
    });
    el.body = document.body;
  }

  function bindEvents() {
    document.addEventListener("click", resetIdleTimer, { passive: true });
    document.addEventListener("keydown", resetIdleTimer, { passive: true });
    if (el.detailsToggle) el.detailsToggle.addEventListener("click", () => setDetailsOpen(!state.detailsOpen));
    if (el.mobileBackdrop) el.mobileBackdrop.addEventListener("click", () => setDetailsOpen(false));
    if (el.refreshStatusButton) el.refreshStatusButton.addEventListener("click", () => {
      void refreshStatus({ force: true, includeProviderRefresh: true });
    });
    if (el.navSearch) {
      el.navSearch.addEventListener("input", () => {
        filterConversationLists(String(el.navSearch.value || ""));
      });
    }
    if (el.archiveCurrentChat) {
      el.archiveCurrentChat.addEventListener("click", archiveCurrentChat);
    }
    if (el.lockChatButton) {
      el.lockChatButton.addEventListener("click", toggleChatLock);
    }
    if (el.wakeModeButton) el.wakeModeButton.addEventListener("click", () => {
      void toggleWakeMode();
    });
    if (el.talkButton) el.talkButton.addEventListener("click", () => {
      void startTalkCapture();
    });
    if (el.interruptButton) el.interruptButton.addEventListener("click", interruptAssistant);
    if (el.sendButton) el.sendButton.addEventListener("click", () => {
      void submitTextCommand();
    });
    if (el.textCommandInput) el.textCommandInput.addEventListener("keydown", handleTextInputKeydown);
    if (el.assistantCoreButton) el.assistantCoreButton.addEventListener("click", () => {
      void handleCoreButtonClick();
    });
    window.addEventListener("resize", handleResize);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    // Nav sidebar
    ["navChat", "navMemory", "navTools", "navProfile", "navSettings"].forEach((id) => {
      if (el[id]) {
        el[id].addEventListener("click", () => {
          const nav = el[id].dataset.nav;
          if (nav) switchNav(nav);
        });
      }
    });

    // New chat button
    if (el.navNewChat) {
      el.navNewChat.addEventListener("click", () => {
        switchNav("chat");
        clearConversationHistory({ keepArchiveState: true });
      });
    }

    // Screen share
    if (el.screenShareButton) {
      el.screenShareButton.addEventListener("click", () => void toggleScreenShare());
    }

    // Overlay toggle
    if (el.overlayToggle) {
      el.overlayToggle.addEventListener("click", toggleOverlayMode);
    }

    // Idle suggestion chips
    document.addEventListener("click", (event) => {
      const chip = event.target.closest(".idle-chip[data-fill]");
      if (!chip) return;
      const fill = chip.dataset.fill || "";
      if (el.textCommandInput) {
        restoreFromIdleMinimize();
        el.textCommandInput.value = fill;
        el.textCommandInput.focus();
        // Position cursor at end
        el.textCommandInput.selectionStart = el.textCommandInput.selectionEnd = fill.length;
      }
    });

    // Orb mini click — restore
    if (el.orbMini) {
      el.orbMini.addEventListener("click", restoreFromIdleMinimize);
    }

    // Color swatches
    if (el.colorSwatches) {
      el.colorSwatches.addEventListener("click", (event) => {
        const swatch = event.target.closest("[data-color]");
        if (swatch) applyOrbColor(swatch.dataset.color);
      });
    }

    // Clear history
    if (el.settingsClearHistory) {
      el.settingsClearHistory.addEventListener("click", () => {
        clearConversationHistory({ keepArchiveState: true });
        addActivity("Settings", "Chat history cleared.", "neutral");
        updateLiveResponse("Chat history cleared.");
      });
    }

    // Clear working memory
    if (el.clearMemoryBtn) {
      el.clearMemoryBtn.addEventListener("click", () => {
        addActivity("Memory", "Working memory cleared.", "neutral");
      });
    }

    // Security modals
    if (el.modalConfirmCancel) el.modalConfirmCancel.addEventListener("click", () => resolveSecurityModal(false));
    if (el.modalConfirmOk)     el.modalConfirmOk.addEventListener("click",     () => resolveSecurityModal(true));
    if (el.modalSessionCancel) el.modalSessionCancel.addEventListener("click", () => resolveSecurityModal(false));
    if (el.modalSessionApprove) el.modalSessionApprove.addEventListener("click", () => resolveSecurityModal(true));
    if (el.modalPinCancel)     el.modalPinCancel.addEventListener("click",     () => resolveSecurityModal(false));
    if (el.modalPinSubmit)     el.modalPinSubmit.addEventListener("click",     () => {
      const pin = String(el.modalPinInput?.value || "").trim();
      if (!pin) {
        showPinError("Please enter your PIN.");
        return;
      }
      resolveSecurityModal(true, { pin });
    });
    if (el.modalPinInput) {
      el.modalPinInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          const pin = String(el.modalPinInput.value || "").trim();
          if (pin) resolveSecurityModal(true, { pin });
        }
      });
    }
  }

  async function bootstrap() {
    await refreshStatus({ force: true, quiet: true });
    if (state.auth?.authenticated) {
      await attemptAutomaticWakeStandby();
    } else {
      updateWakeBanner(publicWakeBanner());
    }
  }

  async function refreshStatus({ force = false, quiet = false, includeProviderRefresh = false } = {}) {
    if (state.refreshInFlight) {
      if (force) {
        state.refreshQueuedForce = true;
      }
      return;
    }

    state.refreshInFlight = true;

    try {
      const authPayload = await fetchStatusPayload("/api/auth/session");
      if (authPayload) {
        state.auth = authPayload;
      }

      const healthPayload = await fetchStatusPayload("/api/system/health");
      if (healthPayload) {
        state.systemHealth = healthPayload;
      }

      const voicePayload = await fetchStatusPayload("/api/voice/status");
      if (voicePayload) {
        state.voiceStatus = voicePayload;
      }

      state.lastStatusRefreshAt = Date.now();
      renderStatusSurfaces();
      if (!quiet && !state.busy && !state.speaking && !state.listening) {
        updateWakeBanner(currentWakeBanner());
      }
      if (includeProviderRefresh) {
        window.setTimeout(() => {
          void refreshProviderSnapshot({ force });
        }, quiet ? 1200 : 0);
      }
    } finally {
      state.refreshInFlight = false;
      if (state.refreshQueuedForce) {
        state.refreshQueuedForce = false;
        window.setTimeout(() => {
          void refreshStatus({ force: true, quiet: true });
        }, 200);
      }
    }
  }

  async function refreshProviderSnapshot({ force = false } = {}) {
    if (state.providerRefreshInFlight) {
      return;
    }

    state.providerRefreshInFlight = true;
    const refreshSuffix = force ? "?refresh=1" : "";

    try {
      const payload = await fetchJson(`/api/providers${refreshSuffix}`);
      state.providerSnapshot = payload;
      renderStatusSurfaces();
    } catch (_error) {
      renderProviderList();
    } finally {
      state.providerRefreshInFlight = false;
    }
  }

  async function fetchStatusPayload(url) {
    try {
      return await fetchJson(url);
    } catch (_error) {
      return null;
    }
  }

  function renderStatusSurfaces() {
    const assistantRuntime = currentRuntime();
    const authPayload = state.auth || {};
    const activeProvider = assistantRuntime.active_provider || assistantRuntime.preferred_provider || "No data yet";
    const brain = state.systemHealth?.brain || "unknown";

    el.accessMode.textContent = authPayload.authenticated ? "Authenticated" : "Public";
    el.brainState.textContent = humanizeStatus(brain);
    el.activeProvider.textContent = humanizeProviderName(activeProvider);
    renderWakeModeStatus();
    el.routeSummary.textContent = assistantRuntime.message || "No live routing data yet.";
    el.presenceSummary.textContent = assistantRuntime.message || "Private voice-first assistant console.";
    el.responseMetaProvider.textContent = `Provider: ${humanizeProviderName(activeProvider)}`;
    el.responseMetaMode.textContent = `Mode: ${authPayload.authenticated ? "account" : "public"}`;
    renderProviderList();
    renderVoiceDiagnostics();
    renderAccountSummary();
    renderWakeControls();
  }

  function renderProviderList() {
    const items = state.providerSnapshot?.items || state.systemHealth?.provider_details || [];
    el.providersList.innerHTML = "";

    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "provider-empty";
      empty.textContent = "Provider details are unavailable right now. Use Refresh status to check them again.";
      el.providersList.appendChild(empty);
      return;
    }

    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = `provider-card provider-card--${String(item.status || "unknown").toLowerCase()}`;

      const header = document.createElement("div");
      header.className = "provider-card__header";

      const title = document.createElement("strong");
      title.textContent = humanizeProviderName(item.provider);

      const badge = document.createElement("span");
      badge.className = `provider-badge provider-badge--${String(item.status || "unknown").toLowerCase()}`;
      badge.textContent = humanizeStatus(item.status || "unknown");

      header.append(title, badge);

      const model = document.createElement("p");
      model.className = "provider-card__model";
      model.textContent = item.model ? `Model: ${item.model}` : "Model: not available";

      const reason = document.createElement("p");
      reason.className = "provider-card__reason";
      reason.textContent = item.reason || "No provider diagnostics yet.";

      card.append(header, model, reason);

      if (item.error) {
        const error = document.createElement("p");
        error.className = "provider-card__error";
        error.textContent = `Error: ${item.error}`;
        card.appendChild(error);
      }

      el.providersList.appendChild(card);
    });
  }

  function renderAccountSummary() {
    const authPayload = state.auth || {};
    const user = authPayload.user || null;

    if (authPayload.authenticated && user) {
      const name = user.preferred_name || user.name || user.username || "there";
      el.accountSummary.textContent = `Signed in as ${name}. ${formatAuthenticatedSessionLabel(authPayload)} Protected account features are available now.`;
      el.authActionLink.textContent = "Signed in";
      el.authActionLink.removeAttribute("href");
      el.authActionLink.setAttribute("aria-disabled", "true");
      el.adminLink.hidden = !Boolean(user.admin);
      // Update sidebar user area
      if (el.navUserName) el.navUserName.textContent = name;
      if (el.navUserStatus) el.navUserStatus.textContent = "Signed in";
      return;
    }

    el.accountSummary.textContent = "You are in public mode. Text and one-tap voice are available now. Sign in for protected account features. New accounts currently require an invitation.";
    el.authActionLink.textContent = "Sign in";
    el.authActionLink.href = "/login";
    el.authActionLink.removeAttribute("aria-disabled");
    el.adminLink.hidden = true;
    // Update sidebar user area
    if (el.navUserName) el.navUserName.textContent = "Guest";
    if (el.navUserStatus) el.navUserStatus.textContent = "Public mode";
  }

  function renderVoiceDiagnostics() {
    const diagnostics = state.browserVoice;
    el.browserVoiceMode.textContent = diagnostics.mode || "No data yet";
    el.micPermissionState.textContent = diagnostics.permission || "No data yet";
    el.inputDeviceSummary.textContent = diagnostics.inputDevice || "No data yet";
    el.lastTranscriptSummary.textContent = diagnostics.lastTranscript || "No data yet";
    el.lastVoiceIssue.textContent = diagnostics.lastIssue || "No issues yet";
  }

  function renderActivityList() {
    el.activityList.innerHTML = "";

    if (!state.activity.length) {
      const empty = document.createElement("p");
      empty.className = "activity-empty";
      empty.textContent = "No assistant activity yet.";
      el.activityList.appendChild(empty);
      return;
    }

    state.activity.slice(0, 6).forEach((item) => {
      const row = document.createElement("article");
      row.className = `activity-item activity-item--${item.tone || "neutral"}`;

      const head = document.createElement("div");
      head.className = "activity-item__head";

      const label = document.createElement("strong");
      label.textContent = item.label;

      const time = document.createElement("span");
      time.textContent = item.time;

      head.append(label, time);

      const detail = document.createElement("p");
      detail.textContent = item.detail;

      row.append(head, detail);
      el.activityList.appendChild(row);
    });
  }

  function addActivity(label, detail, tone = "neutral") {
    state.activity.unshift({
      label,
      detail,
      tone,
      time: formatTime(new Date()),
    });
    state.activity = state.activity.slice(0, 12);
    renderActivityList();
  }

  function setOrbLayout(layout) {
    state.orbLayout = layout;
    if (el.body) {
      el.body.dataset.orbLayout = layout;
    }
  }

  function renderChatLockState() {
    const locked = Boolean(state.chatLocked);
    if (el.lockChatButton) {
      el.lockChatButton.textContent = locked ? "Unlock chat" : "Lock chat";
      el.lockChatButton.classList.toggle("is-locked", locked);
    }
    if (el.textCommandInput) {
      el.textCommandInput.readOnly = locked;
      el.textCommandInput.placeholder = locked ? "Chat is locked" : "Message VORIS";
    }
  }

  function toggleChatLock() {
    state.chatLocked = !state.chatLocked;
    renderChatLockState();
    addActivity("Chat", state.chatLocked ? "This conversation was locked." : "This conversation was unlocked.", "neutral");
    if (state.chatLocked) {
      updateWakeBanner("This chat is locked. Unlock it to continue.");
    } else {
      updateWakeBanner(currentWakeBanner());
    }
    renderWakeControls();
  }

  function renderConversationThread() {
    if (!el.conversationThread) {
      return;
    }

    el.conversationThread.innerHTML = "";
    const messages = Array.isArray(state.chatMessages) ? state.chatMessages : [];
    if (!messages.length) {
      if (el.conversationEmpty) {
        el.conversationEmpty.hidden = false;
        el.conversationThread.appendChild(el.conversationEmpty);
      }
      return;
    }

    if (el.conversationEmpty) {
      el.conversationEmpty.hidden = true;
    }

    messages.forEach((message) => {
      const item = document.createElement("article");
      item.className = `conversation-message conversation-message--${message.role}`;

      const label = document.createElement("p");
      label.className = "conversation-label";
      label.textContent = message.role === "assistant" ? "VORIS" : "You";

      const bubble = document.createElement("div");
      bubble.className = "conversation-bubble";

      const body = document.createElement("div");
      body.className = "conversation-body";
      if (message.role === "assistant") {
        renderResponseContent(body, message.text);
      } else {
        body.textContent = message.text;
      }

      bubble.appendChild(body);

      if (message.meta) {
        const meta = document.createElement("p");
        meta.className = "chat-meta";
        meta.textContent = message.meta;
        item.append(label, bubble, meta);
      } else {
        item.append(label, bubble);
      }

      el.conversationThread.appendChild(item);
    });

    el.conversationThread.scrollTop = el.conversationThread.scrollHeight;
  }

  function appendConversationMessage(role, text, { meta = "" } = {}) {
    const safeText = String(text || "").trim();
    if (!safeText) {
      return;
    }
    state.chatMessages.push({
      id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      role,
      text: safeText,
      meta: String(meta || "").trim(),
    });
    renderConversationThread();
  }

  function archiveCurrentChat() {
    if (!state.chatMessages.length) {
      addActivity("Archive", "Nothing to archive yet.", "neutral");
      return;
    }

    const firstUserMessage = state.chatMessages.find((item) => item.role === "user")?.text || "Archived chat";
    const preview = state.chatMessages.find((item) => item.role === "assistant")?.text || firstUserMessage;
    state.archivedChats.unshift({
      id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      title: firstUserMessage.slice(0, 56),
      preview: preview.slice(0, 96),
      messages: state.chatMessages.map((item) => ({ ...item })),
      createdAt: formatTime(new Date()),
    });
    state.archivedChats = state.archivedChats.slice(0, 24);
    renderArchivedChats();
    clearConversationHistory({ keepArchiveState: true });
    addActivity("Archive", "Current chat archived.", "good");
  }

  function restoreArchivedChat(chatId) {
    const archived = state.archivedChats.find((item) => item.id === chatId);
    if (!archived) {
      return;
    }
    state.chatMessages = archived.messages.map((item) => ({ ...item }));
    switchNav("chat");
    setOrbLayout("left");
    renderConversationThread();
    const lastUser = [...state.chatMessages].reverse().find((item) => item.role === "user");
    const lastAssistant = [...state.chatMessages].reverse().find((item) => item.role === "assistant");
    updateLiveTranscript(lastUser?.text || "Waiting for your voice or text command.");
    updateLiveResponse(lastAssistant?.text || "VORIS is standing by.");
    addActivity("Archive", "Archived conversation restored.", "neutral");
  }

  function renderArchivedChats(filterValue = String(el.navSearch?.value || "")) {
    if (!el.navArchiveList) {
      return;
    }
    const query = String(filterValue || "").trim().toLowerCase();
    el.navArchiveList.innerHTML = "";

    const visibleChats = state.archivedChats.filter((item) => {
      if (!query) {
        return true;
      }
      return `${item.title} ${item.preview}`.toLowerCase().includes(query);
    });

    if (!visibleChats.length) {
      if (el.navArchiveEmpty) {
        el.navArchiveEmpty.hidden = false;
        el.navArchiveList.appendChild(el.navArchiveEmpty);
      }
      return;
    }

    if (el.navArchiveEmpty) {
      el.navArchiveEmpty.hidden = true;
    }

    visibleChats.forEach((chat) => {
      const item = document.createElement("button");
      item.className = "nav-conv-item";
      item.type = "button";
      item.title = chat.preview;

      const dot = document.createElement("span");
      dot.className = "nav-conv-item__dot";

      const text = document.createElement("span");
      text.className = "nav-conv-item__text";
      text.textContent = chat.title;

      const time = document.createElement("span");
      time.className = "nav-conv-item__time";
      time.textContent = chat.createdAt;

      item.append(dot, text, time);
      item.addEventListener("click", () => restoreArchivedChat(chat.id));
      el.navArchiveList.appendChild(item);
    });
  }

  function filterConversationLists(filterValue) {
    const query = String(filterValue || "").trim().toLowerCase();
    if (el.navConversations) {
      const items = Array.from(el.navConversations.querySelectorAll(".nav-conv-item"));
      let visibleCount = 0;
      items.forEach((item) => {
        const matches = !query || String(item.textContent || "").toLowerCase().includes(query);
        item.hidden = !matches;
        if (matches) {
          visibleCount += 1;
        }
      });
      if (el.navConvEmpty) {
        el.navConvEmpty.hidden = visibleCount > 0;
      }
    }
    renderArchivedChats(query);
  }

  function renderWakeControls() {
    el.wakeModeButton.classList.toggle("is-active", state.wakeModeEnabled);
    renderChatLockState();
    if (!canUseVoice()) {
      el.wakeModeButton.textContent = "Wake unavailable";
    } else if (state.voicePhase === "wake_listening") {
      el.wakeModeButton.textContent = "Wake mode on";
    } else if (state.voicePhase === "command_listening") {
      el.wakeModeButton.textContent = "Listening";
    } else if (state.voicePhase === "interrupted") {
      el.wakeModeButton.textContent = "Interrupted";
    } else if (state.voicePhase === "processing") {
      el.wakeModeButton.textContent = "Analyzing";
    } else if (state.voicePhase === "speaking") {
      el.wakeModeButton.textContent = "Speaking";
    } else if (state.wakeModeEnabled) {
      el.wakeModeButton.textContent = "Wake mode on";
    } else {
      el.wakeModeButton.textContent = "Wake mode";
    }
    el.wakeModeButton.disabled = state.voiceActionInFlight || state.chatLocked;
    el.talkButton.disabled = !canUseVoice() || state.busy || state.voicePhase !== "idle" || state.voiceActionInFlight || state.chatLocked;
    el.interruptButton.disabled = !(state.busy || state.recognitionActive || state.voicePhase !== "idle");
    if (el.sendButton) {
      el.sendButton.disabled = state.busy || state.chatLocked;
    }
  }

  function setBrowserVoiceDiagnostics(patch) {
    state.browserVoice = {
      ...state.browserVoice,
      ...patch,
    };
    renderVoiceDiagnostics();
  }

  function setVoicePhase(phase) {
    state.voicePhase = phase;
    state.listening = phase === "wake_listening" || phase === "command_listening";
    state.speaking = phase === "speaking";
    state.wakeStandbyActive = phase === "wake_listening" && state.recognitionActive;
    updateOrbForPhase(phase);
    renderWakeModeStatus();
    renderWakeControls();
  }

  // Orb state colors — temporary overlays that restore to user preference on idle
  const ORB_STATE_PALETTE = {
    wake_listening:    "cyan",
    command_listening: "cyan",
    processing:        "purple",
    speaking:          "gold",
    interrupted:       "red",
  };

  function updateOrbForPhase(phase) {
    const stateName = ORB_STATE_PALETTE[phase];
    if (stateName && ORB_COLORS[stateName]) {
      // Apply state color without persisting — don't update state.orbColor
      const palette = ORB_COLORS[stateName];
      const root = document.documentElement;
      root.style.setProperty("--orb-primary",    palette.primary);
      root.style.setProperty("--orb-glow",       palette.glow);
      root.style.setProperty("--orb-glow-outer", palette.outer);
      root.style.setProperty("--orb-glow-soft",  palette.soft);
      root.style.setProperty("--orb-border-idle",palette.border);
    } else {
      // Restore user preference
      applyOrbColor(state.orbColor || "blue");
    }
    // Update sidebar brand subtitle
    const phaseLabels = {
      wake_listening:    "Listening…",
      command_listening: "Listening…",
      processing:        "Analyzing…",
      speaking:          "Speaking…",
      interrupted:       "Interrupted",
    };
    if (el.navBrandSub) {
      el.navBrandSub.textContent = phaseLabels[phase] || "Standby";
    }
  }

  function renderWakeModeStatus() {
    if (!el.wakeModeStatus) {
      return;
    }
    if (state.voicePhase === "wake_listening") {
      el.wakeModeStatus.textContent = "Standby active";
    } else if (state.voicePhase === "command_listening") {
      el.wakeModeStatus.textContent = "Listening";
    } else if (state.voicePhase === "interrupted") {
      el.wakeModeStatus.textContent = "Interrupted";
    } else if (state.voicePhase === "processing") {
      el.wakeModeStatus.textContent = "Analyzing";
    } else if (state.voicePhase === "speaking") {
      el.wakeModeStatus.textContent = "Speaking";
    } else if (state.wakeModeEnabled) {
      el.wakeModeStatus.textContent = "Wake ready";
    } else if (state.wakeModeGestureNeeded) {
      el.wakeModeStatus.textContent = "Needs tap";
    } else {
      el.wakeModeStatus.textContent = "Standby off";
    }
  }

  function clearBargeInState({ keepTriggered = false } = {}) {
    state.bargeInArmed = false;
    state.currentSpokenText = "";
    if (!keepTriggered) {
      state.bargeInTriggered = false;
    }
  }

  function hasBrowserMicPermission() {
    return String(state.browserVoice.permission || "").trim().toLowerCase() === "granted";
  }

  function normalizeSpeechEchoText(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[^\w\s']/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function isLikelySpeechEcho(transcript) {
    const heard = normalizeSpeechEchoText(transcript);
    const spoken = normalizeSpeechEchoText(state.currentSpokenText);
    if (!heard || !spoken) {
      return false;
    }
    if (spoken.includes(heard) || heard.includes(spoken)) {
      return true;
    }

    const heardWords = heard.split(" ").filter(Boolean);
    const spokenWords = new Set(spoken.split(" ").filter(Boolean));
    if (!heardWords.length || !spokenWords.size) {
      return false;
    }

    const overlap = heardWords.filter((word) => spokenWords.has(word)).length;
    return (overlap / heardWords.length) >= 0.75;
  }

  function triggerBargeIn(transcript) {
    if (state.bargeInTriggered) {
      return;
    }
    state.bargeInTriggered = true;
    state.bargeInArmed = false;
    stopSpeech();
    setVoicePhase("interrupted");
    setAssistantState("interrupted", {
      pill: "Interrupted",
      kicker: "Voice override",
      headline: "Go ahead.",
      description: "I stopped speaking. I'm listening to you now.",
    });
    updateWakeBanner("Interrupted. Listening for your command now.");
    addActivity("Interrupted", `VORIS stopped speaking when it heard: ${transcript}`, "warn");
  }

  function handleSpeechStopPhrase(transcript) {
    state.bargeInTriggered = true;
    state.bargeInArmed = false;
    stopSpeech();
    clearRecognitionStartTimer();
    stopRecognition("speech_stop_phrase");
    setVoicePhase("idle");
    setAssistantState("idle", {
      pill: "Silenced",
      kicker: "Standby",
      headline: "Silenced.",
      description: "I stopped speaking. Waiting for your next command.",
    });
    updateWakeBanner("Silenced. Waiting for your next command.");
    addActivity("Silenced", `VORIS stopped speaking when it heard: ${transcript}`, "warn");
    if (state.wakeModeEnabled) {
      scheduleRecognitionStart("wake", { reason: "after_silence" });
    }
  }

  async function armBargeInListener() {
    if (!canUseVoice() || !hasBrowserMicPermission() || state.bargeInArmed || state.recognitionActive || state.voicePhase !== "speaking") {
      return false;
    }

    state.bargeInArmed = true;
    state.bargeInTriggered = false;
    const started = await transitionRecognitionMode("command", {
      automatic: true,
      resetCommandRetryCount: true,
    });
    if (!started) {
      state.bargeInArmed = false;
    }
    return started;
  }

  function browserPermissionLabel(value) {
    const normalized = String(value || "").trim().toLowerCase();
    const labels = {
      granted: "Granted",
      prompt: "Prompt required",
      denied: "Denied",
      unsupported: "Unsupported",
      "not-allowed": "Denied",
      "service-not-allowed": "Denied",
    };
    return labels[normalized] || humanizeStatus(normalized || "unknown");
  }

  function logVoiceEvent(eventName, detail = {}) {
    try {
      console.debug("[VORIS voice]", eventName, detail);
    } catch (_error) {
      // keep diagnostics lightweight
    }
  }

  function clearRecognitionStartTimer() {
    if (!state.recognitionStartTimer) {
      return;
    }
    window.clearTimeout(state.recognitionStartTimer);
    state.recognitionStartTimer = null;
  }

  function scheduleRecognitionStart(
    mode,
    { delay = WAKE_RESUME_DELAY_MS, automatic = true, resetCommandRetryCount = false, reason = "resume" } = {},
  ) {
    clearRecognitionStartTimer();
    state.recognitionStartTimer = window.setTimeout(() => {
      state.recognitionStartTimer = null;
      if (state.recognitionActive || state.busy || state.speaking) {
        return;
      }
      if (mode === "wake" && !state.wakeModeEnabled) {
        return;
      }
      logVoiceEvent("recognition_restart", { mode, reason, automatic });
      void transitionRecognitionMode(mode, { automatic, resetCommandRetryCount });
    }, delay);
  }

  async function waitForRecognitionIdle(timeoutMs = RECOGNITION_IDLE_TIMEOUT_MS) {
    if (!state.recognitionActive) {
      return true;
    }

    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      await new Promise((resolve) => {
        window.setTimeout(resolve, 50);
      });
      if (!state.recognitionActive) {
        return true;
      }
    }
    return !state.recognitionActive;
  }

  async function transitionRecognitionMode(mode, { automatic = false, resetCommandRetryCount = false } = {}) {
    clearRecognitionStartTimer();

    if (state.recognitionActive) {
      state.recognitionHandoffPending = true;
      stopRecognition("handoff");
      const idle = await waitForRecognitionIdle();
      if (!idle) {
        state.recognitionHandoffPending = false;
        setVoicePhase("idle");
        setBrowserVoiceDiagnostics({
          lastEvent: "handoff_timeout",
          lastIssue: "The microphone session did not close cleanly.",
        });
        setAssistantState("error", {
          pill: "Error",
          kicker: "Voice issue",
          headline: "I could not reset the microphone cleanly.",
          description: "Try Talk again in a moment.",
        });
        return false;
      }
    }

    return startRecognitionSession(mode, { automatic, resetCommandRetryCount });
  }

  function handleNoSpeechDetected(partialTranscript) {
    const transcript = String(partialTranscript || "").trim();
    const hadPartial = Boolean(transcript);
    const activeMode = state.recognitionMode;
    const message = hadPartial
      ? "I caught part of that, so I will use what I heard."
      : activeMode === "wake"
        ? `I did not hear the wake phrase. Say "${preferredWakePhrase()}" when you are ready.`
        : "I did not hear anything clearly enough to continue.";

    setBrowserVoiceDiagnostics({
      lastTranscript: hadPartial ? transcript : state.browserVoice.lastTranscript,
      heardSpeech: hadPartial,
      lastEvent: activeMode === "wake" ? "wake_no_speech" : "command_no_speech",
      lastIssue: message,
    });

    if (activeMode === "command" && hadPartial) {
      addActivity("Partial voice", "VORIS used the speech it captured instead of discarding it.", "warn");
      void handleCommandTranscript(transcript);
      return;
    }

    if (activeMode === "command" && state.commandRetryCount < COMMAND_NO_SPEECH_RETRY_LIMIT) {
      state.commandRetryCount += 1;
      setVoicePhase("idle");
      setAssistantState("no_speech", {
        pill: "No speech",
        kicker: "Voice",
        headline: "I did not catch that.",
        description: "Please say it once more. I am listening again now.",
      });
      updateWakeBanner("I did not catch that. Please say it once more.");
      scheduleRecognitionStart("command", {
        delay: NO_SPEECH_RECOVERY_DELAY_MS,
        automatic: true,
        resetCommandRetryCount: false,
        reason: "command_retry",
      });
      return;
    }

    state.commandRetryCount = 0;
    setVoicePhase("idle");
    if (activeMode === "wake") {
      setIdleState();
    } else {
      setAssistantState("no_speech", {
        pill: "No speech",
        kicker: "Voice",
        headline: "I did not hear a clear command.",
        description: "Try again with Talk, or use the text command field below.",
      });
    }
    updateWakeBanner(message);

    if (state.wakeModeEnabled) {
      scheduleRecognitionStart("wake", {
        delay: NO_SPEECH_RECOVERY_DELAY_MS,
        automatic: true,
        reason: activeMode === "wake" ? "wake_retry" : "return_to_standby",
      });
    }
  }

  async function refreshBrowserVoiceDiagnostics({ requestPermission = false } = {}) {
    const mode = state.voiceStatus?.wake_word?.mode === "browser_assisted"
      ? "Browser-assisted wake mode"
      : "Browser voice";
    const updates = { mode };

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setBrowserVoiceDiagnostics({
        ...updates,
        permission: "Unsupported",
        inputDevice: "Browser microphone API is unavailable",
        lastIssue: "This browser cannot provide the microphone path VORIS needs.",
      });
      return false;
    }

    let permissionState = state.browserVoice.permission || "Unknown";
    if (navigator.permissions?.query) {
      try {
        const permission = await navigator.permissions.query({ name: "microphone" });
        permissionState = permission.state;
      } catch (_error) {
        permissionState = state.browserVoice.permission || "Unknown";
      }
    }

    if (requestPermission && permissionState !== "granted") {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        const track = stream.getAudioTracks()[0] || null;
        permissionState = "granted";
        updates.inputDevice = track?.label || "Browser-selected microphone";
        stream.getTracks().forEach((mediaTrack) => mediaTrack.stop());
      } catch (error) {
        const message = humanizeSpeechError(error?.name || error?.message || "not-allowed");
        setBrowserVoiceDiagnostics({
          ...updates,
          permission: browserPermissionLabel(error?.name || "denied"),
          lastIssue: message,
        });
        return false;
      }
    }

    if (navigator.mediaDevices.enumerateDevices) {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const inputs = devices.filter((device) => device.kind === "audioinput");
        if (!updates.inputDevice && inputs.length) {
          const labeled = inputs.find((device) => device.label);
          updates.inputDevice = labeled?.label || `${inputs.length} audio input device${inputs.length === 1 ? "" : "s"} available`;
        } else if (!updates.inputDevice) {
          updates.inputDevice = "No audio input device was reported";
        }
      } catch (_error) {
        if (!updates.inputDevice) {
          updates.inputDevice = "Browser did not expose input device details";
        }
      }
    }

    setBrowserVoiceDiagnostics({
      ...updates,
      permission: browserPermissionLabel(permissionState),
      inputDevice: updates.inputDevice || state.browserVoice.inputDevice || "No data yet",
    });
    return permissionState === "granted";
  }

  function handleResize() {
    if (window.innerWidth >= 1200) {
      el.mobileBackdrop.hidden = true;
    } else if (!state.detailsOpen) {
      el.mobileBackdrop.hidden = true;
    }
  }

  function handleVisibilityChange() {
    if (document.hidden || state.refreshInFlight || state.busy || state.recognitionActive) {
      return;
    }
    if ((Date.now() - state.lastStatusRefreshAt) >= REFRESH_INTERVAL_MS) {
      void refreshStatus({ quiet: true });
    }
  }

  function setDetailsOpen(open) {
    state.detailsOpen = Boolean(open);
    localStorage.setItem(STORAGE_KEYS.detailsOpen, String(state.detailsOpen));
    syncDetailsDrawer();
  }

  function syncDetailsDrawer() {
    el.body.classList.toggle("details-open", state.detailsOpen);
    el.detailsToggle.setAttribute("aria-expanded", state.detailsOpen ? "true" : "false");
    el.mobileBackdrop.hidden = !state.detailsOpen || window.innerWidth >= 1200;
  }

  async function attemptAutomaticWakeStandby() {
    if (!canUseVoice()) {
      updateWakeBanner(currentWakeBanner());
      return;
    }

    const started = await enableWakeMode({ automatic: true });
    if (!started) {
      state.wakeModeGestureNeeded = true;
      updateWakeBanner('Wake mode needs one tap in this browser before "Hey VORIS" can work reliably.');
    }
  }

  async function handleCoreButtonClick() {
    if (state.auth?.authenticated) {
      if (state.wakeModeEnabled) {
        await startTalkCapture();
        return;
      }
      await toggleWakeMode();
      return;
    }

    await startTalkCapture();
  }

  async function toggleWakeMode() {
    if (state.voiceActionInFlight) {
      return;
    }
    if (state.wakeModeEnabled) {
      disableWakeMode();
      return;
    }
    await enableWakeMode({ automatic: false });
  }

  async function enableWakeMode({ automatic = false } = {}) {
    if (state.voiceActionInFlight) {
      return false;
    }
    state.voiceActionInFlight = true;
    renderWakeControls();

    try {
      if (!canUseVoice()) {
        updateWakeBanner(currentWakeBanner());
        return false;
      }

      const microphoneReady = await refreshBrowserVoiceDiagnostics({ requestPermission: !automatic });
      if (!microphoneReady) {
        const micMessage = state.browserVoice.lastIssue || "Mic permission denied.";
        updateWakeBanner(micMessage);
        if (!automatic) {
          addActivity("Microphone", micMessage, "error");
        }
        return false;
      }

    state.wakeModeEnabled = true;
    state.wakeModeGestureNeeded = false;
    setOrbLayout("center");
      state.commandRetryCount = 0;
      clearRecognitionStartTimer();

      if (state.busy || state.voicePhase === "processing" || state.voicePhase === "speaking") {
        updateWakeBanner(`Wake mode will arm as soon as VORIS is free. Then say "${preferredWakePhrase()}".`);
        return true;
      }

      const started = await transitionRecognitionMode("wake", { automatic, resetCommandRetryCount: false });
      if (!started) {
        state.wakeModeEnabled = false;
        updateWakeBanner(state.browserVoice.lastIssue || currentWakeBanner());
        return false;
      }

      addActivity("Wake mode", `Standby listening is active for "${preferredWakePhrase()}".`, "good");
      updateWakeBanner(currentWakeBanner());
      return true;
    } finally {
      state.voiceActionInFlight = false;
      renderWakeControls();
    }
  }

  function disableWakeMode() {
    clearRecognitionStartTimer();
    state.wakeModeEnabled = false;
    state.wakeModeGestureNeeded = false;
    state.commandRetryCount = 0;
    state.recognitionHandoffPending = false;
    stopRecognition("manual");
    stopSpeech();
    clearBargeInState();
    setVoicePhase("idle");
    setIdleState();
    updateWakeBanner(currentWakeBanner());
    addActivity("Wake mode", "Standby listening was turned off.", "neutral");
  }

  async function startTalkCapture() {
    console.log("[VORIS Voice] Talk button clicked — voiceActionInFlight:", state.voiceActionInFlight, "recognition:", state.recognition, "phase:", state.voicePhase);
    if (state.voiceActionInFlight) {
      return;
    }
    state.voiceActionInFlight = true;
    renderWakeControls();

    try {
      if (!canUseVoice() || state.busy || state.voicePhase === "processing" || state.voicePhase === "speaking") {
        updateWakeBanner(currentWakeBanner());
        return;
      }

      const microphoneReady = await refreshBrowserVoiceDiagnostics({ requestPermission: true });
      if (!microphoneReady) {
        updateWakeBanner(state.browserVoice.lastIssue || "Mic permission denied.");
        return;
      }

      const started = await transitionRecognitionMode("command", {
        automatic: false,
        resetCommandRetryCount: true,
      });
      if (!started) {
        updateWakeBanner("I couldn't start listening. Try again.");
      }
    } finally {
      state.voiceActionInFlight = false;
      renderWakeControls();
    }
  }

  function setupRecognition() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    console.log("[VORIS Voice] setupRecognition — SpeechRecognition available:", !!Recognition);
    if (!Recognition) {
      const errMsg = "SpeechRecognition is not supported in this browser.";
      console.error("[VORIS Voice] FATAL:", errMsg);
      setBrowserVoiceDiagnostics({
        mode: "Browser voice is unavailable",
        permission: "Unsupported",
        inputDevice: "SpeechRecognition is not available here",
        lastIssue: "Use text commands or a browser with Web Speech support.",
      });
      renderWakeControls();
      return;
    }

    const recognition = new Recognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      console.log("[VORIS Voice] recognition.onstart — mode:", state.recognitionMode, "lang:", recognition.lang, "continuous:", recognition.continuous, "interimResults:", recognition.interimResults);
      clearRecognitionStartTimer();
      state.recognitionActive = true;
      state.recognitionStopReason = "running";
      state.partialTranscript = "";
      setBrowserVoiceDiagnostics({
        lastEvent: state.recognitionMode === "wake" ? "wake_standby" : "listening",
        lastIssue: state.recognitionMode === "wake"
          ? `Waiting for "${preferredWakePhrase()}".`
          : "Listening for your command.",
      });

      if (state.recognitionMode === "wake") {
        setVoicePhase("wake_listening");
        setAssistantState("idle", {
          pill: "Standby",
          kicker: "Standby",
          headline: "Wake mode is on.",
          description: `Say "${preferredWakePhrase()}" while this page stays open.`,
        });
      } else if (state.bargeInArmed && state.currentSpokenText) {
        setBrowserVoiceDiagnostics({
          lastEvent: "barge_in_ready",
          lastIssue: "Listening for a live interruption while VORIS is speaking.",
        });
      } else {
        setVoicePhase("command_listening");
        setAssistantState("listening", {
          pill: "Listening",
          kicker: "Listening",
          headline: "Go ahead.",
          description: "I am listening for your request.",
        });
      }

      updateWakeBanner(currentWakeBanner());
    };

    recognition.onresult = (event) => {
      const results = Array.from(event.results || []);
      const finalTranscript = results
        .filter((result) => result.isFinal)
        .map((result) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      const interimTranscript = results
        .filter((result) => !result.isFinal)
        .map((result) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      const transcript = finalTranscript || interimTranscript;
      console.log("[VORIS Voice] recognition.onresult — final:", JSON.stringify(finalTranscript), "interim:", JSON.stringify(interimTranscript), "resultCount:", event.results.length);

      if (!transcript) {
        console.warn("[VORIS Voice] onresult fired but transcript is empty");
        return;
      }

      state.partialTranscript = transcript;
      if (state.bargeInArmed && isLikelySpeechEcho(transcript)) {
        setBrowserVoiceDiagnostics({
          lastTranscript: transcript,
          heardSpeech: true,
          lastEvent: "barge_in_echo_ignored",
          lastIssue: "Ignoring VORIS's own speech while waiting for an interruption.",
        });
        return;
      }

      if (state.bargeInArmed && finalTranscript && isSpeechStopPhrase(finalTranscript)) {
        handleSpeechStopPhrase(finalTranscript);
        return;
      }

      if (state.bargeInArmed && !state.bargeInTriggered) {
        triggerBargeIn(transcript);
        if (!finalTranscript) {
          return;
        }
      }

      updateLiveTranscript(transcript);
      setBrowserVoiceDiagnostics({
        lastTranscript: transcript,
        heardSpeech: true,
        lastEvent: state.recognitionMode === "wake" ? "wake_heard" : "speech_heard",
        lastIssue: finalTranscript ? "Speech captured cleanly." : "Speech is coming in.",
      });
      logVoiceEvent("speech_result", {
        mode: state.recognitionMode,
        transcript,
        final: Boolean(finalTranscript),
      });

      if (!finalTranscript) {
        if (state.recognitionMode === "command") {
          if (state.voicePhase === "interrupted") {
            setVoicePhase("command_listening");
          }
          setAssistantState("listening", {
            pill: "Listening",
            kicker: "Listening",
            headline: "I'm listening.",
            description: "Keep going. I have your voice but I am waiting for the full command.",
          });
        }
        return;
      }

      const activeMode = state.recognitionMode;
      if (state.bargeInTriggered && activeMode === "command") {
        setVoicePhase("command_listening");
      }
      console.log("[VORIS Voice] Final transcript ready to send:", JSON.stringify(finalTranscript), "mode:", activeMode);
      state.recognitionHandoffPending = true;
      stopRecognition("handoff");
      if (activeMode === "wake") {
        void handleWakeTranscript(finalTranscript);
      } else {
        void handleCommandTranscript(finalTranscript);
      }
    };

    recognition.onerror = (event) => {
      const code = String(event.error || "").trim().toLowerCase();
      console.error("[VORIS Voice] recognition.onerror — error:", code, "raw event:", event.error, "phase:", state.voicePhase, "mode:", state.recognitionMode);
      updateWakeBanner(`Voice error: ${code}`);
      const partialTranscript = String(state.partialTranscript || "").trim();
      const phaseBeforeError = state.voicePhase;
      state.recognitionActive = false;
      if (phaseBeforeError !== "speaking") {
        setVoicePhase("idle");
      }
      logVoiceEvent("speech_error", {
        mode: state.recognitionMode,
        error: code,
        partialTranscript,
      });

      if (state.recognitionHandoffPending && code === "aborted") {
        state.recognitionStopReason = "handoff";
        return;
      }

      if (code === "no-speech") {
        state.recognitionStopReason = "handled_no_speech";
        if (state.bargeInArmed && phaseBeforeError === "speaking") {
          state.bargeInArmed = false;
          return;
        }
        handleNoSpeechDetected(partialTranscript);
        return;
      }

      if (code === "aborted") {
        state.recognitionStopReason = "manual";
        setBrowserVoiceDiagnostics({
          lastEvent: "voice_aborted",
          lastIssue: partialTranscript ? "Listening stopped after partial speech." : "Listening was stopped.",
        });
        if (!state.busy && !state.speaking) {
          setIdleState();
        }
        return;
      }

      const permissionDenied = code === "not-allowed" || code === "service-not-allowed";
      const message = permissionDenied ? "Mic permission denied." : humanizeSpeechError(code);
      if (phaseBeforeError === "speaking") {
        state.bargeInArmed = false;
        if (permissionDenied) {
          state.wakeModeEnabled = false;
          state.wakeModeGestureNeeded = true;
        }
        setBrowserVoiceDiagnostics({
          lastEvent: "barge_in_error",
          permission: permissionDenied ? "Denied" : state.browserVoice.permission,
          lastIssue: message,
        });
        return;
      }
      state.recognitionStopReason = "handled_error";
      state.wakeModeEnabled = false;
      if (permissionDenied) {
        state.wakeModeEnabled = false;
        state.wakeModeGestureNeeded = true;
      } else {
        state.wakeModeGestureNeeded = false;
      }
      setBrowserVoiceDiagnostics({
        lastEvent: "voice_error",
        permission: permissionDenied ? "Denied" : state.browserVoice.permission,
        lastIssue: message,
      });
      setAssistantState("error", {
        pill: "Error",
        kicker: "Voice issue",
        headline: "I lost the microphone flow.",
        description: message,
      });
      updateWakeBanner(message);
      addActivity("Voice error", message, "error");
    };

    recognition.onend = () => {
      const endedMode = state.recognitionMode;
      const stopReason = state.recognitionStopReason || "idle";
      console.log("[VORIS Voice] recognition.onend — endedMode:", endedMode, "stopReason:", stopReason, "handoffPending:", state.recognitionHandoffPending);
      state.recognitionActive = false;
      state.recognitionMode = "off";
      if (state.voicePhase === "wake_listening" || state.voicePhase === "command_listening") {
        setVoicePhase("idle");
      }

      if (state.recognitionHandoffPending) {
        state.recognitionHandoffPending = false;
        state.recognitionStopReason = "idle";
        return;
      }

      if (!state.busy && !state.speaking) {
        setIdleState();
      }

      if (state.voicePhase === "speaking" && state.currentSpokenText && !state.bargeInTriggered) {
        state.bargeInArmed = false;
        window.setTimeout(() => {
          void armBargeInListener();
        }, 150);
        state.recognitionStopReason = "idle";
        return;
      }

      if (stopReason === "running" && state.wakeModeEnabled && !state.busy && !state.speaking) {
        scheduleRecognitionStart("wake", {
          reason: endedMode === "wake" ? "wake_end" : "return_to_standby",
        });
      }

      state.recognitionStopReason = "idle";
    };

    state.recognition = recognition;
    renderWakeControls();
  }

  function startRecognitionSession(mode, { automatic = false, resetCommandRetryCount = false } = {}) {
    if (!state.recognition) {
      return false;
    }
    if (!isVoiceAllowedHere()) {
      updateWakeBanner(currentWakeBanner());
      return false;
    }
    if (state.recognitionActive) {
      return false;
    }
    if (mode === "wake" && !state.wakeModeEnabled) {
      return false;
    }

    clearRecognitionStartTimer();
    state.recognitionMode = mode;
    state.recognitionStopReason = "starting";
    state.partialTranscript = "";
    if (mode === "command" && resetCommandRetryCount) {
      state.commandRetryCount = 0;
    }
    state.recognition.lang = preferredRecognitionLanguage();
    state.recognition.continuous = mode === "command" && state.bargeInArmed;
    state.recognition.interimResults = mode === "command";
    state.recognition.maxAlternatives = 1;

    try {
      console.log("[VORIS Voice] recognition.start() called — mode:", mode, "lang:", state.recognition.lang, "continuous:", state.recognition.continuous, "interimResults:", state.recognition.interimResults);
      state.recognition.start();
      logVoiceEvent("speech_start", { mode, automatic });
      return true;
    } catch (error) {
      console.error("[VORIS Voice] recognition.start() threw:", error.message, error);
      updateWakeBanner(`Failed to start mic: ${error.message}`);
      if (!automatic) {
        updateWakeBanner(error.message || "Voice listening could not start.");
      }
      setBrowserVoiceDiagnostics({
        lastEvent: "start_failed",
        lastIssue: error.message || "Voice listening could not start.",
      });
      return false;
    }
  }

  function stopRecognition(reason = "manual") {
    if (!state.recognition || (!state.recognitionActive && state.recognitionMode === "off")) {
      return;
    }
    state.recognitionStopReason = reason;
    try {
      state.recognition.stop();
    } catch (_error) {
      // ignore browser stop races
    }
  }

  async function handleWakeTranscript(transcript) {
    updateLiveTranscript(transcript);
    const wakeMatch = detectWakePhrase(transcript);
    setBrowserVoiceDiagnostics({
      lastTranscript: transcript,
      heardSpeech: true,
      lastEvent: wakeMatch.detected ? "wake_match" : "wake_miss",
      lastIssue: wakeMatch.detected
        ? (wakeMatch.remainingText
          ? "Wake phrase matched. Using the spoken command now."
          : "Wake phrase matched. Waiting for your command.")
        : `Heard speech, but not "${preferredWakePhrase()}".`,
    });

    if (!wakeMatch.detected) {
      logVoiceEvent("wake_miss", { transcript });
      addActivity("Standby", "Heard speech, but the wake phrase was not detected.", "neutral");
      updateWakeBanner(`Standby is active. Say "${preferredWakePhrase()}" to wake VORIS.`);
      setVoicePhase("idle");
      setIdleState();
      if (state.wakeModeEnabled && !state.busy && state.voicePhase === "idle") {
        scheduleRecognitionStart("wake", {
          delay: NO_SPEECH_RECOVERY_DELAY_MS,
          automatic: true,
          reason: "wake_miss",
        });
      }
      return;
    }

    logVoiceEvent("wake_detected", {
      transcript,
      remainingText: wakeMatch.remainingText,
    });
    addActivity("Wake detected", `VORIS heard ${preferredWakePhrase()}.`, "good");
    setOrbLayout("center");
    // Expand orb if minimized
    if (state.idleMinimized) restoreFromIdleMinimize();

    if (!wakeMatch.remainingText) {
      const wakeGreeting = buildWakeGreeting();
      updateLiveResponse(wakeGreeting, { provider: "local_wake", mode: "wake" });
      setAssistantState("listening", {
        pill: "Listening",
        kicker: "Wake detected",
        headline: wakeGreeting,
        description: "I'm listening for your command now.",
      });
      updateWakeBanner("Wake detected. Go ahead.");
      appendConversationMessage("assistant", wakeGreeting, { meta: "Wake greeting" });
      await speakAssistant(wakeGreeting, { resumeWakeAfter: false });
      await transitionRecognitionMode("command", {
        automatic: true,
        resetCommandRetryCount: true,
      });
      return;
    }

    await processVoiceCommand(wakeMatch.remainingText);
  }

  async function handleCommandTranscript(transcript) {
    const cleanedTranscript = String(transcript || "").trim();
    if (!cleanedTranscript) {
      handleNoSpeechDetected("");
      return;
    }
    updateLiveTranscript(cleanedTranscript);
    await processVoiceCommand(cleanedTranscript);
  }

  async function processVoiceCommand(transcript) {
    const commandText = String(transcript || "").trim();
    if (!commandText) {
      handleNoSpeechDetected("");
      return;
    }

    resetIdleTimer();

    // Handle orb color command locally — never hit the LLM
    const colorRequest = detectColorChangeCommand(commandText);
    if (colorRequest && ORB_COLORS[colorRequest]) {
      applyOrbColor(colorRequest);
      const colorName = colorRequest.charAt(0).toUpperCase() + colorRequest.slice(1);
      const reply = `Orb color changed to ${colorName}.`;
      updateLiveTranscript(commandText);
      updateLiveResponse(reply, { provider: "local", mode: "system" });
      addActivity("Color", reply, "good");
      await speakAssistant(reply, { resumeWakeAfter: true });
      return;
    }

    // Handle navigation commands locally
    const navRequest = detectNavCommand(commandText);
    if (navRequest) {
      switchNav(navRequest);
      const navLabels = { chat: "Chat", memory: "Memory", tools: "Tools", profile: "Profile", settings: "Settings" };
      const reply = `Opening ${navLabels[navRequest] || navRequest}.`;
      updateLiveTranscript(commandText);
      addActivity("Navigation", reply, "neutral");
      await speakAssistant(reply, { resumeWakeAfter: true });
      return;
    }

    const routedCommand = classifyAssistantCommand(commandText);
    if (routedCommand.route === "external") {
      executeExternalRoute(commandText, routedCommand, { source: "voice" });
      return;
    }

    state.bargeInTriggered = false;
    setVoicePhase("processing");
    beginInternalRoute(commandText, routedCommand);
    setAssistantState("thinking", {
      pill: "Thinking",
      kicker: routedCommand.taskType === "chat" ? "Conversation" : routedCommand.taskType,
      headline: "One second.",
      description: "I'm working through that now.",
    });
    updateWakeBanner("Working on that now.");

    try {
      let payload = await submitChatMessage(commandText);
      payload = await resolveSecurityIfNeeded(payload, commandText);
      if (!payload) { setVoicePhase("idle"); setIdleState(); return; }

      const assistantPayload = extractAssistantReplyPayload(payload);
      const answer = assistantPayload.answer || FALLBACK_REPLY;
      const provider = assistantPayload.provider || "local";

      state.currentProvider = provider;
      updateLiveResponse(answer, {
        provider,
        mode: assistantPayload.documentDelivery ? "document delivery" : "voice",
        documentDelivery: assistantPayload.documentDelivery,
      });
      appendConversationMessage("assistant", answer, {
        meta: assistantPayload.documentDelivery ? "document delivery" : provider,
      });
      if (assistantPayload.documentDelivery) addOutputCard(assistantPayload.documentDelivery);
      addConversationEntry(commandText, answer);
      addActivity("Voice request", commandText, "neutral");
      addActivity("Answer ready", answer.slice(0, 140), assistantPayload.success === false ? "warn" : "good");
      await speakAssistant(answer, { resumeWakeAfter: true });
    } catch (error) {
      if (error?.name === "AbortError") {
        setVoicePhase("idle");
        setIdleState();
        return;
      }
      handleAssistantFailure(error.message || FALLBACK_REPLY);
    }
  }

  async function submitTextCommand() {
    if (state.busy) {
      return;
    }
    if (state.chatLocked) {
      updateWakeBanner("This chat is locked. Unlock it to continue.");
      return;
    }

    const text = String(el.textCommandInput.value || "").trim();
    if (!text) {
      return;
    }

    resetIdleTimer();

    // Handle orb color command locally
    const colorRequest = detectColorChangeCommand(text);
    if (colorRequest && ORB_COLORS[colorRequest]) {
      applyOrbColor(colorRequest);
      el.textCommandInput.value = "";
      const colorName = colorRequest.charAt(0).toUpperCase() + colorRequest.slice(1);
      const reply = `Orb color changed to ${colorName}.`;
      updateLiveTranscript(text);
      updateLiveResponse(reply, { provider: "local", mode: "system" });
      addActivity("Color", reply, "good");
      return;
    }

    // Handle navigation commands locally
    const navRequest = detectNavCommand(text);
    if (navRequest) {
      el.textCommandInput.value = "";
      switchNav(navRequest);
      const navLabels = { chat: "Chat", memory: "Memory", tools: "Tools", profile: "Profile", settings: "Settings" };
      const reply = `Opening ${navLabels[navRequest] || navRequest}.`;
      updateLiveTranscript(text);
      updateLiveResponse(reply, { provider: "local", mode: "system" });
      addActivity("Navigation", reply, "neutral");
      return;
    }

    const routedCommand = classifyAssistantCommand(text);
    el.textCommandInput.value = "";
    if (routedCommand.route === "external") {
      executeExternalRoute(text, routedCommand, { source: "text" });
      return;
    }
    beginInternalRoute(text, routedCommand);
    if (state.recognitionActive) {
      state.recognitionHandoffPending = true;
      stopRecognition();
      await waitForRecognitionIdle();
    }
    setAssistantState("thinking", {
      pill: "Thinking",
      kicker: routedCommand.taskType === "chat" ? "Conversation" : routedCommand.taskType,
      headline: "One second.",
      description: "I'm working through that now.",
    });

    try {
      let payload = await submitChatMessage(text);
      payload = await resolveSecurityIfNeeded(payload, text);
      if (!payload) { setIdleState(); resumeWakeStandby(); return; }

      const assistantPayload = extractAssistantReplyPayload(payload);
      const answer = assistantPayload.answer || FALLBACK_REPLY;
      const provider = assistantPayload.provider || "local";
      state.currentProvider = provider;
      updateLiveResponse(answer, {
        provider,
        mode: assistantPayload.documentDelivery ? "document delivery" : (assistantPayload.mode || "text"),
        documentDelivery: assistantPayload.documentDelivery,
      });
      appendConversationMessage("assistant", answer, {
        meta: assistantPayload.documentDelivery ? "document delivery" : provider,
      });
      if (assistantPayload.documentDelivery) addOutputCard(assistantPayload.documentDelivery);
      addConversationEntry(text, answer);
      addActivity("Text command", text, "neutral");
      addActivity("Answer ready", answer.slice(0, 140), assistantPayload.success === false ? "warn" : "good");

      await speakAssistant(answer, { resumeWakeAfter: false });

      if (assistantPayload.success === false || assistantPayload.degraded) {
        setAssistantState("error", {
          pill: "Degraded",
          kicker: "Fallback answer",
          headline: "I still have an answer for you.",
          description: assistantPayload.error || assistantRuntimeMessage(),
        });
      } else {
        setIdleState();
      }
      updateWakeBanner(currentWakeBanner());
    } catch (error) {
      if (error?.name === "AbortError") {
        setIdleState();
        return;
      }
      handleAssistantFailure(error.message || FALLBACK_REPLY);
    } finally {
      resumeWakeStandby();
    }
  }

  function handleTextInputKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitTextCommand();
    }
  }

  async function submitChatMessage(message) {
    return requestJson("/api/chat", {
      message,
      mode: "hybrid",
    }, {
      timeoutMs: CHAT_REQUEST_TIMEOUT_MS,
    });
  }

  async function requestJson(url, payload, { timeoutMs = 0 } = {}) {
    if (state.currentRequestController) {
      state.currentRequestController.abort();
    }

    const controller = new AbortController();
    let timedOut = false;
    let timeoutId = null;
    state.currentRequestController = controller;
    state.busy = true;
    renderWakeControls();

    try {
      if (timeoutMs > 0) {
        timeoutId = window.setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs);
      }

      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-VORIS-Session-Id": state.sessionId,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      let body = {};
      try {
        body = await response.json();
      } catch (_error) {
        body = {};
      }

      if (!response.ok && !body.content && !body.reply && !body.result) {
        throw new Error(body.error || `Request failed (${response.status})`);
      }
      if (response.ok && !body.content && !body.reply && !body.result && body.success !== false) {
        throw new Error("The assistant returned an empty response.");
      }
      return body;
    } catch (error) {
      if (timedOut) {
        throw new Error("The assistant took too long to respond. Try again.");
      }
      if (error?.name === "AbortError") {
        throw error;
      }
      throw error;
    } finally {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      if (state.currentRequestController === controller) {
        state.currentRequestController = null;
      }
      state.busy = false;
      renderWakeControls();
    }
  }

  function extractAssistantReplyPayload(payload) {
    const safePayload = payload && typeof payload === "object" ? payload : {};
    const nestedResult = safePayload.result && typeof safePayload.result === "object" ? safePayload.result : {};
    const answer = normalizeAssistantText(
      safePayload.content
        || safePayload.reply
        || nestedResult.content
        || nestedResult.reply
        || nestedResult.response
        || "",
    );
    const documentDelivery = normalizeDocumentDeliveryPayload(safePayload, nestedResult);

    return {
      answer,
      provider: safePayload.provider || nestedResult.provider || "local",
      mode: safePayload.mode || nestedResult.mode || "text",
      success: safePayload.success !== false && nestedResult.success !== false,
      degraded: Boolean(safePayload.degraded || nestedResult.degraded || safePayload.status === "degraded"),
      error: safePayload.error || nestedResult.error || "",
      documentDelivery,
    };
  }

  function interruptAssistant() {
    if (state.currentRequestController) {
      state.currentRequestController.abort();
      state.currentRequestController = null;
    }
    clearRecognitionStartTimer();
    stopRecognition("manual");
    stopSpeech();
    clearBargeInState();
    addActivity("Interrupted", "The current assistant action was stopped.", "warn");
    setVoicePhase("idle");
    setIdleState();
    if (state.wakeModeEnabled) {
      scheduleRecognitionStart("wake", {
        reason: "interrupt",
      });
    }
  }

  function stopSpeech() {
    const wasSpeaking = state.voicePhase === "speaking";
    state.activeSpeechRunId += 1;
    state.currentUtterance = null;
    state.bargeInArmed = false;
    state.currentSpokenText = "";
    if (window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel();
      } catch (_error) {
        // ignore browser cancellation races
      }
    }
    if (wasSpeaking) {
      setVoicePhase("idle");
    } else {
      renderWakeControls();
    }
  }

  async function speakAssistant(text, { resumeWakeAfter = true } = {}) {
    const spokenText = prepareSpokenText(text);
    if (!spokenText) {
      if (resumeWakeAfter) {
        setIdleState();
        resumeWakeStandby();
      }
      return;
    }

    if (!window.speechSynthesis || typeof window.SpeechSynthesisUtterance === "undefined") {
      addActivity("Voice", "Browser speech synthesis is unavailable here.", "warn");
      setVoicePhase("idle");
      if (resumeWakeAfter) {
        setIdleState();
        resumeWakeStandby();
      }
      return;
    }

    stopSpeech();
    state.currentSpokenText = spokenText;
    state.bargeInTriggered = false;
    const speechRunId = state.activeSpeechRunId;

    await new Promise((resolve) => {
      let settled = false;
      const utterance = new SpeechSynthesisUtterance(spokenText);
      state.currentUtterance = utterance;
      utterance.lang = preferredSpeechLanguage();
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.volume = 1;

      const finishSpeech = () => {
        if (settled) {
          return;
        }
        settled = true;
        if (state.activeSpeechRunId === speechRunId && state.currentUtterance === utterance) {
          state.currentUtterance = null;
          clearBargeInState();
          setVoicePhase("idle");
        }
        resolve();
      };

      utterance.onstart = () => {
        if (state.activeSpeechRunId !== speechRunId || state.currentUtterance !== utterance) {
          return;
        }
        setVoicePhase("speaking");
        setAssistantState("speaking", {
          pill: "Speaking",
          kicker: "Responding",
          headline: "Done.",
          description: "I have the answer for you.",
        });
        window.setTimeout(() => {
          void armBargeInListener();
        }, 120);
      };

      utterance.onend = finishSpeech;

      utterance.onerror = () => {
        addActivity("Voice", "Browser speech playback could not finish cleanly.", "warn");
        finishSpeech();
      };

      window.setTimeout(() => {
        if (state.activeSpeechRunId !== speechRunId || state.currentUtterance !== utterance) {
          finishSpeech();
          return;
        }
        try {
          window.speechSynthesis.speak(utterance);
        } catch (_error) {
          finishSpeech();
        }
      }, 0);
    });

    const speechCompletedNormally = state.activeSpeechRunId === speechRunId;
    if (resumeWakeAfter && speechCompletedNormally) {
      setIdleState();
      resumeWakeStandby();
    }
  }

  function handleAssistantFailure(message) {
    const safeMessage = normalizeAssistantText(message || FALLBACK_REPLY) || FALLBACK_REPLY;
    setVoicePhase("idle");
    updateLiveResponse(safeMessage, { provider: "degraded", mode: "fallback" });
    addActivity("Assistant issue", safeMessage, "error");
    setAssistantState("error", {
      pill: "Error",
      kicker: "Assistant issue",
      headline: "I couldn't complete that cleanly.",
      description: safeMessage,
    });
    updateWakeBanner(safeMessage);
    resumeWakeStandby();
  }

  function setIdleState() {
    const wakePhrase = preferredWakePhrase();
    const standbyActive = state.voicePhase === "wake_listening";
    if (standbyActive) {
      setOrbLayout("center");
    } else if (state.chatMessages.length) {
      setOrbLayout("left");
    } else if (state.orbLayout !== "floating") {
      setOrbLayout("topbar");
    }
    setAssistantState("idle", {
      pill: standbyActive ? "Standby" : "Idle",
      kicker: standbyActive ? "Standby" : "Idle",
      headline: standbyActive ? "Wake mode is on." : "Ready when you are.",
      description: standbyActive
        ? `Say "${wakePhrase}" while this page stays open.`
        : "Use Wake mode, Talk, or the text command field when you want me.",
    });
    updateWakeBanner(currentWakeBanner());
  }

  function resumeWakeStandby() {
    if (!state.wakeModeEnabled || state.recognitionActive || state.busy || state.voicePhase !== "idle") {
      return;
    }
    scheduleRecognitionStart("wake", {
      reason: "resume_standby",
    });
  }

  function setAssistantState(stateName, copy) {
    el.body.dataset.assistantState = stateName;
    el.statePillLabel.textContent = copy.pill;
    el.stateKicker.textContent = copy.kicker;
    el.stateHeadline.textContent = copy.headline;
    el.stateDescription.textContent = copy.description;
  }

  function updateLiveTranscript(text) {
    el.liveTranscript.textContent = text || "Waiting for your voice or text command.";
  }

  function normalizeDocumentDeliveryPayload(payload, nestedResult = {}) {
    const rawDelivery = payload.document_delivery && typeof payload.document_delivery === "object"
      ? payload.document_delivery
      : nestedResult.document_delivery && typeof nestedResult.document_delivery === "object"
        ? nestedResult.document_delivery
        : null;

    const primaryFormat = String(
      payload.document_format
        || payload.format
        || rawDelivery?.format
        || nestedResult.document_format
        || nestedResult.format
        || "txt",
    ).trim().toLowerCase();

    const downloadUrl = rawDelivery?.download_url || payload.download_url || nestedResult.download_url || "";
    const fileName = rawDelivery?.file_name || payload.file_name || nestedResult.file_name || "";
    if (!downloadUrl || !fileName) {
      return null;
    }

    const formatLinks = {
      ...(nestedResult.format_links && typeof nestedResult.format_links === "object" ? nestedResult.format_links : {}),
      ...(payload.format_links && typeof payload.format_links === "object" ? payload.format_links : {}),
      ...(rawDelivery?.format_links && typeof rawDelivery.format_links === "object" ? rawDelivery.format_links : {}),
    };
    if (!formatLinks[primaryFormat]) {
      formatLinks[primaryFormat] = downloadUrl;
    }

    const alternateFormatLinks = {
      ...(nestedResult.alternate_format_links && typeof nestedResult.alternate_format_links === "object" ? nestedResult.alternate_format_links : {}),
      ...(payload.alternate_format_links && typeof payload.alternate_format_links === "object" ? payload.alternate_format_links : {}),
      ...(rawDelivery?.alternate_format_links && typeof rawDelivery.alternate_format_links === "object" ? rawDelivery.alternate_format_links : {}),
    };

    const rawFiles = []
      .concat(Array.isArray(nestedResult.files) ? nestedResult.files : [])
      .concat(Array.isArray(payload.files) ? payload.files : [])
      .concat(Array.isArray(rawDelivery?.files) ? rawDelivery.files : []);
    const files = rawFiles
      .map((item) => ({
        format: String(item?.format || "").trim().toLowerCase(),
        fileName: String(item?.file_name || item?.fileName || "").trim(),
        downloadUrl: String(item?.download_url || item?.downloadUrl || "").trim(),
        primary: Boolean(item?.primary),
      }))
      .filter((item) => item.format && item.fileName && item.downloadUrl);
    if (!files.length) {
      files.push({
        format: primaryFormat,
        fileName,
        downloadUrl,
        primary: true,
      });
    }

    const availableFormats = Array.from(
      new Set([
        ...(Array.isArray(rawDelivery?.available_formats) ? rawDelivery.available_formats : []),
        ...(Array.isArray(payload.available_formats) ? payload.available_formats : []),
        ...(Array.isArray(nestedResult.available_formats) ? nestedResult.available_formats : []),
        ...Object.keys(formatLinks),
      ].filter(Boolean).map((item) => String(item).trim().toLowerCase())),
    );

    return {
      kind: "document_delivery",
      deliveryMessage: rawDelivery?.delivery_message || payload.reply || payload.content || "Your document is ready.",
      title: rawDelivery?.title || payload.document_title || nestedResult.document_title || "Document ready",
      subtitle: rawDelivery?.subtitle || payload.document_subtitle || nestedResult.document_subtitle || "",
      previewText: rawDelivery?.preview_text || payload.document_preview || payload.preview_text || nestedResult.document_preview || nestedResult.preview_text || "",
      documentType: rawDelivery?.document_type || payload.document_type || nestedResult.document_type || "document",
      format: primaryFormat,
      primaryFormat: String(rawDelivery?.primary_format || payload.primary_format || nestedResult.primary_format || primaryFormat).trim().toLowerCase(),
      fileName,
      downloadUrl,
      topic: rawDelivery?.topic || payload.document_topic || nestedResult.document_topic || "",
      pageTarget: rawDelivery?.page_target || payload.page_target || nestedResult.page_target || null,
      style: rawDelivery?.style || payload.document_style || payload.style || nestedResult.document_style || nestedResult.style || "",
      includeReferences: Boolean(rawDelivery?.include_references || payload.include_references || nestedResult.include_references),
      citationStyle: rawDelivery?.citation_style || payload.citation_style || nestedResult.citation_style || "",
      requestedFormats: Array.from(
        new Set([
          ...(Array.isArray(rawDelivery?.requested_formats) ? rawDelivery.requested_formats : []),
          ...(Array.isArray(payload.requested_formats) ? payload.requested_formats : []),
          ...(Array.isArray(nestedResult.requested_formats) ? nestedResult.requested_formats : []),
          ...files.map((item) => item.format),
        ].filter(Boolean).map((item) => String(item).trim().toLowerCase())),
      ),
      files,
      availableFormats,
      formatLinks,
      alternateFormatLinks,
    };
  }

  function clearDocumentDelivery() {
    if (!el.documentDeliveryPanel) {
      return;
    }
    el.documentDeliveryPanel.hidden = true;
    el.documentDeliveryPanel.innerHTML = "";
  }

  function buildDocumentLink(label, href, { primary = false } = {}) {
    const link = document.createElement("a");
    link.className = `document-link${primary ? " document-link--primary" : ""}`;
    link.href = href;
    link.textContent = label;
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
    return link;
  }

  function renderDocumentDelivery(delivery) {
    if (!el.documentDeliveryPanel || !delivery) {
      clearDocumentDelivery();
      return;
    }

    const panel = el.documentDeliveryPanel;
    panel.innerHTML = "";
    panel.hidden = false;

    const header = document.createElement("div");
    header.className = "document-delivery__header";

    const title = document.createElement("p");
    title.className = "document-delivery__title";
    title.textContent = delivery.title || `${humanizeProviderName(delivery.documentType)} ready`;

    const subtitle = document.createElement("p");
    subtitle.className = "document-delivery__subtitle";
    subtitle.textContent = delivery.deliveryMessage || delivery.subtitle || delivery.fileName;

    const meta = document.createElement("p");
    meta.className = "document-delivery__meta";
    const metaParts = [
      `Primary format: ${String(delivery.primaryFormat || delivery.format || "txt").toUpperCase()}`,
      delivery.pageTarget ? `Target length: ~${delivery.pageTarget} pages` : "",
      delivery.style ? `Style: ${String(delivery.style).replace(/^\w/, (letter) => letter.toUpperCase())}` : "",
      delivery.includeReferences ? `References${delivery.citationStyle ? `: ${String(delivery.citationStyle).toUpperCase()}` : ""}` : "",
      delivery.subtitle ? delivery.subtitle : "",
    ].filter(Boolean);
    meta.textContent = metaParts.join(" | ");

    header.append(title, subtitle, meta);

    if (delivery.previewText) {
      const preview = document.createElement("div");
      preview.className = "document-delivery__preview";
      preview.textContent = delivery.previewText;
      panel.appendChild(header);
      panel.appendChild(preview);
    } else {
      panel.appendChild(header);
    }

    const links = document.createElement("div");
    links.className = "document-links";

    const fileEntries = Array.isArray(delivery.files) && delivery.files.length
      ? delivery.files
      : [{
        format: delivery.format,
        downloadUrl: delivery.downloadUrl,
        primary: true,
      }];

    const primaryLabel = document.createElement("p");
    primaryLabel.className = "document-links__label";
    primaryLabel.textContent = fileEntries.length > 1 ? "Files ready" : "Download";

    const primaryRow = document.createElement("div");
    primaryRow.className = "document-links__row";
    fileEntries.forEach((item, index) => {
      const isPrimary = Boolean(item.primary) || index === 0;
      primaryRow.appendChild(
        buildDocumentLink(
          `Download ${String(item.format || delivery.format || "txt").toUpperCase()}`,
          item.downloadUrl || delivery.downloadUrl,
          { primary: isPrimary },
        ),
      );
    });

    links.append(primaryLabel, primaryRow);

    const deliveredFormats = new Set(fileEntries.map((item) => String(item.format || "").trim().toLowerCase()).filter(Boolean));
    const alternateEntries = Object.entries(delivery.alternateFormatLinks || {})
      .filter(([format]) => !deliveredFormats.has(String(format || "").trim().toLowerCase()));
    if (alternateEntries.length) {
      const alternateLabel = document.createElement("p");
      alternateLabel.className = "document-links__label";
      alternateLabel.textContent = "Also available";

      const alternateRow = document.createElement("div");
      alternateRow.className = "document-links__row";
      alternateEntries.forEach(([format, href]) => {
        alternateRow.appendChild(buildDocumentLink(`Download ${String(format).toUpperCase()}`, href));
      });
      links.append(alternateLabel, alternateRow);
    }

    panel.appendChild(links);
  }

  function updateLiveResponse(text, { provider = null, mode = null, documentDelivery = null } = {}) {
    renderResponseContent(el.liveResponse, text || "VORIS is standing by.");
    if (documentDelivery) {
      renderDocumentDelivery(documentDelivery);
    } else {
      clearDocumentDelivery();
    }
    if (provider) {
      el.responseMetaProvider.textContent = `Provider: ${humanizeProviderName(provider)}`;
    }
    if (mode) {
      el.responseMetaMode.textContent = `Mode: ${mode}`;
    }
  }

  function renderResponseContent(container, rawText) {
    if (!container) return;
    container.innerHTML = "";
    const text = String(rawText || "").trim();
    if (!text) {
      const placeholder = document.createElement("p");
      placeholder.className = "response-body";
      placeholder.textContent = "VORIS is standing by.";
      container.appendChild(placeholder);
      return;
    }

    const lines = text.split(/\r?\n/);
    const blocks = [];
    let currentParagraph = [];
    let currentList = null;

    const flushParagraph = () => {
      if (currentParagraph.length) {
        blocks.push({ type: "paragraph", lines: currentParagraph });
        currentParagraph = [];
      }
    };

    const flushList = () => {
      if (currentList) {
        blocks.push(currentList);
        currentList = null;
      }
    };

    const titleDetected = (() => {
      for (const raw of lines) {
        const trimmed = raw.trim();
        if (!trimmed) continue;
        const looksLikeTitle =
          trimmed.length <= 90
          && !/[.:!?-]$/.test(trimmed)
          && !/^[-*•\d]/.test(trimmed)
          && trimmed.split(" ").length <= 14;
        return looksLikeTitle ? trimmed : null;
      }
      return null;
    })();

    let firstNonEmptyConsumed = false;
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) {
        flushParagraph();
        flushList();
        continue;
      }

      if (!firstNonEmptyConsumed && titleDetected && line === titleDetected) {
        blocks.push({ type: "title", text: line });
        firstNonEmptyConsumed = true;
        continue;
      }
      firstNonEmptyConsumed = true;

      const bulletMatch = line.match(/^[-*•]\s+(.*)$/);
      const numberedMatch = line.match(/^(\d{1,2})[.)]\s+(.*)$/);

      if (bulletMatch) {
        flushParagraph();
        if (!currentList || currentList.ordered) {
          flushList();
          currentList = { type: "list", ordered: false, items: [] };
        }
        currentList.items.push(bulletMatch[1]);
        continue;
      }

      if (numberedMatch) {
        flushParagraph();
        if (!currentList || !currentList.ordered) {
          flushList();
          currentList = { type: "list", ordered: true, items: [] };
        }
        currentList.items.push(numberedMatch[2]);
        continue;
      }

      if (/^#{1,6}\s+/.test(line)) {
        flushParagraph();
        flushList();
        blocks.push({ type: "heading", text: line.replace(/^#{1,6}\s+/, "") });
        continue;
      }

      if (line.length <= 70 && line.endsWith(":")) {
        flushParagraph();
        flushList();
        blocks.push({ type: "heading", text: line.replace(/:$/, "") });
        continue;
      }

      flushList();
      currentParagraph.push(line);
    }
    flushParagraph();
    flushList();

    for (const block of blocks) {
      if (block.type === "title") {
        const node = document.createElement("h3");
        node.className = "response-title";
        node.textContent = block.text;
        container.appendChild(node);
      } else if (block.type === "heading") {
        const node = document.createElement("h4");
        node.className = "response-heading";
        node.textContent = block.text;
        container.appendChild(node);
      } else if (block.type === "paragraph") {
        const node = document.createElement("p");
        node.className = "response-body";
        node.textContent = block.lines.join(" ");
        container.appendChild(node);
      } else if (block.type === "list") {
        const list = document.createElement(block.ordered ? "ol" : "ul");
        list.className = block.ordered ? "response-list response-list--ordered" : "response-list";
        for (const item of block.items) {
          const li = document.createElement("li");
          li.textContent = item;
          list.appendChild(li);
        }
        container.appendChild(list);
      }
    }
  }

  function updateWakeBanner(text) {
    el.wakeBanner.textContent = text;
  }

  function currentWakeBanner() {
    if (!state.recognition) {
      return "Browser wake mode is not available here. Text commands still work.";
    }
    if (!isVoiceAllowedHere()) {
      return "Wake mode needs localhost or HTTPS in this browser.";
    }
    if (state.voicePhase === "wake_listening") {
      return `Wake mode is on. Say "${preferredWakePhrase()}" while this page stays open.`;
    }
    if (state.voicePhase === "interrupted") {
      return "Interrupted. Listening for your command now.";
    }
    if (state.voicePhase === "command_listening") {
      return "Listening for your command now.";
    }
    if (state.voicePhase === "processing") {
      return "Working on your request now.";
    }
    if (state.voicePhase === "speaking") {
      return "Responding now.";
    }
    if (state.wakeModeEnabled) {
      return `Wake mode is ready. Say "${preferredWakePhrase()}" when you're ready.`;
    }
    if (state.wakeModeGestureNeeded) {
      return `Wake mode needs one tap before "${preferredWakePhrase()}" can work in this browser.`;
    }
    if (state.auth?.authenticated) {
      return `Wake mode is available. Tap Wake mode if the browser still needs microphone permission, then say "${preferredWakePhrase()}".`;
    }
    return publicWakeBanner();
  }

  function publicWakeBanner() {
    return `Public mode keeps text and one-tap Talk available now. Sign in if you want standby wake mode for "${preferredWakePhrase()}".`;
  }

  function currentRuntime() {
    return state.providerSnapshot?.assistant_runtime || state.systemHealth?.assistant_runtime || {};
  }

  function assistantRuntimeMessage() {
    return currentRuntime().message || "VORIS is routing around an unhealthy path right now.";
  }

  function currentUserName() {
    const user = state.auth?.user || {};
    return user.preferred_name || user.name || user.username || "";
  }

  function formatAuthenticatedSessionLabel(authPayload) {
    const remaining = Number(authPayload?.session_remaining_seconds);
    if (authPayload?.session_valid && Number.isFinite(remaining) && remaining > 0) {
      if (remaining >= 3600) {
        return `Session active for about ${Math.max(1, Math.round(remaining / 3600))}h more.`;
      }
      return `Session active for about ${Math.max(1, Math.round(remaining / 60))}m more.`;
    }
    if (authPayload?.session_valid) {
      return "Session active.";
    }
    return "Session status unavailable.";
  }

  function buildWakeGreeting() {
    const name = String(currentUserName() || "").trim();
    return name ? `Hey ${name}, I'm here.` : DEFAULT_WAKE_GREETING;
  }

  function preferredWakePhrase() {
    return state.voiceStatus?.wake_word?.default_phrase || state.voiceStatus?.settings?.wake_words?.[0] || WAKE_FALLBACK;
  }

  function preferredRecognitionLanguage() {
    return state.voiceStatus?.settings?.language || "en-US";
  }

  function preferredSpeechLanguage() {
    return state.voiceStatus?.settings?.language || "en-US";
  }

  function isVoiceAllowedHere() {
    return Boolean(window.isSecureContext || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");
  }

  function canUseVoice() {
    return Boolean(state.recognition && isVoiceAllowedHere());
  }

  function normalizeWakeText(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[.,/#!$%^&*;:{}=_`~()?"']/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function buildWakeVariants(wakeWord) {
    const canonical = normalizeWakeText(wakeWord);
    if (!canonical) {
      return [];
    }
    const variants = new Set([
      canonical,
      canonical.replace(/^hey\s+/, "hi "),
      canonical.replace(/^hey\s+/, "hello "),
      canonical.replace(/^hey\s+/, "heya "),
      canonical.replace(/\baura\b/g, "ora"),
    ]);
    return Array.from(variants).filter(Boolean);
  }

  function detectWakePhrase(transcript) {
    const wakeWords = state.voiceStatus?.settings?.wake_words || [WAKE_FALLBACK];
    const normalized = normalizeWakeText(transcript);

    for (const wakeWord of wakeWords) {
      const variants = buildWakeVariants(wakeWord);
      for (const candidate of variants) {
        const pattern = new RegExp(`^(?:${escapeRegex(candidate)})(?:\\s+|$)`);
        if (pattern.test(normalized)) {
          return {
            detected: true,
            wakeWord: candidate,
            remainingText: normalized.replace(pattern, "").trim(),
          };
        }
      }
    }

    return {
      detected: false,
      wakeWord: null,
      remainingText: normalized,
    };
  }

  async function fetchJson(url) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "X-VORIS-Session-Id": state.sessionId,
      },
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (!response.ok) {
      throw new Error(payload.error || payload.detail || `Request failed (${response.status})`);
    }
    return payload;
  }

  function scheduleRefresh() {
    if (state.refreshIntervalId) {
      window.clearInterval(state.refreshIntervalId);
    }
    state.refreshIntervalId = window.setInterval(() => {
      if (document.hidden || state.refreshInFlight || state.recognitionActive || state.busy || state.speaking) {
        return;
      }
      void refreshStatus({ quiet: true });
    }, REFRESH_INTERVAL_MS);
  }

  function ensureSessionId() {
    const existing = localStorage.getItem(STORAGE_KEYS.sessionId);
    if (existing) {
      return existing;
    }
    const generated = `live-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(STORAGE_KEYS.sessionId, generated);
    return generated;
  }

  function readBoolean(key, fallback) {
    const raw = localStorage.getItem(key);
    if (raw === null) {
      return fallback;
    }
    return raw === "true";
  }

  function humanizeProviderName(value) {
    const normalized = String(value || "").trim();
    if (!normalized) {
      return "No data yet";
    }
    return normalized.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
  }

  function humanizeStatus(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) {
      return "No data yet";
    }
    return normalized.replace(/_/g, " ");
  }

  function humanizeSpeechError(code) {
    const normalized = String(code || "").trim().toLowerCase();
    const messages = {
      "no-speech": "I did not hear anything clearly enough to continue.",
      aborted: "Listening was stopped.",
      "audio-capture": "No microphone input is available.",
      "not-allowed": "Mic permission denied.",
      "service-not-allowed": "Mic permission denied.",
      network: "The browser voice service is unavailable right now.",
    };
    return messages[normalized] || "The voice path could not continue.";
  }

  function normalizeAssistantText(value) {
    return String(value || "")
      .replace(/\r\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function prepareSpokenText(text) {
    const cleaned = String(text || "")
      .replace(/```[\s\S]*?```/g, "I've prepared the code for you.")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/#{1,6}\s*/g, "")
      .replace(/(?:^|\s)\d+\.\s+/g, ". ")
      .replace(/\n\s*-\s+/g, ". ")
      .replace(/\n+/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();

    if (!cleaned) {
      return "";
    }

    const SPEECH_FULL_READ_LIMIT = 1200;
    if (cleaned.length <= SPEECH_FULL_READ_LIMIT) {
      return cleaned;
    }

    const sentences = cleaned.match(/[^.!?]+[.!?]?/g) || [cleaned];
    const trimmedSentences = sentences.map((sentence) => sentence.trim()).filter(Boolean);

    const summary = [];
    let summaryLength = 0;
    for (const sentence of trimmedSentences) {
      if (summaryLength + sentence.length > SPEECH_FULL_READ_LIMIT && summary.length >= 2) {
        break;
      }
      summary.push(sentence);
      summaryLength += sentence.length + 1;
      if (summaryLength >= SPEECH_FULL_READ_LIMIT) {
        break;
      }
    }
    const summaryText = summary.join(" ").trim();
    if (!summaryText) {
      return cleaned.slice(0, SPEECH_FULL_READ_LIMIT);
    }
    return `${summaryText} The full response is on screen — say stop or I'll read it myself to silence me.`;
  }

  const SPEECH_STOP_PHRASES = [
    "stop",
    "okay stop",
    "ok stop",
    "stop it",
    "stop stop",
    "stop speaking",
    "stop talking",
    "be quiet",
    "quiet",
    "shut up",
    "enough",
    "that's enough",
    "thats enough",
    "i'll read it myself",
    "ill read it myself",
    "i will read it myself",
    "i can read",
    "let me read",
    "silence",
    "pause",
  ];

  function isSpeechStopPhrase(transcript) {
    const normalized = String(transcript || "")
      .toLowerCase()
      .replace(/[^a-z'\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!normalized) {
      return false;
    }
    if (SPEECH_STOP_PHRASES.includes(normalized)) {
      return true;
    }
    const firstWords = normalized.split(" ").slice(0, 5).join(" ");
    return SPEECH_STOP_PHRASES.some((phrase) => {
      if (!phrase) return false;
      return firstWords === phrase || firstWords.startsWith(`${phrase} `);
    });
  }

  function formatTime(date) {
    return new Intl.DateTimeFormat([], {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  function escapeRegex(value) {
    return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  // ─────────────────────────────────────────────
  // SECURITY RESOLUTION (API layer)
  // ─────────────────────────────────────────────

  async function resolveSecurityIfNeeded(payload, originalMessage) {
    if (!payload || typeof payload !== "object") return payload;

    const permissionInfo = payload.permission && typeof payload.permission === "object"
      ? payload.permission
      : null;

    if (!permissionInfo) return payload;

    const trustLevel = String(permissionInfo.trust_level || "").toLowerCase();
    const requiresApproval = Boolean(permissionInfo.requires_approval) || Boolean(permissionInfo.approval_type && permissionInfo.approval_type !== "none");
    const statusBlocked = String(payload.status || "").toLowerCase() === "blocked" || payload.success === false;

    if (!requiresApproval || !statusBlocked) return payload;
    if (trustLevel === "safe") return payload;

    // Show the appropriate security modal and wait
    return handleSecurityRequired(permissionInfo, originalMessage);
  }

  // ─────────────────────────────────────────────
  // ORB COLOR SYSTEM
  // ─────────────────────────────────────────────

  function applyOrbColor(colorName) {
    const palette = ORB_COLORS[String(colorName || "blue").toLowerCase()] || ORB_COLORS.blue;
    const root = document.documentElement;
    root.style.setProperty("--orb-primary",    palette.primary);
    root.style.setProperty("--orb-glow",        palette.glow);
    root.style.setProperty("--orb-glow-outer",  palette.outer);
    root.style.setProperty("--orb-glow-soft",   palette.soft);
    root.style.setProperty("--orb-border-idle", palette.border);

    state.orbColor = String(colorName || "blue").toLowerCase();

    // Update active swatch
    if (el.colorSwatches) {
      el.colorSwatches.querySelectorAll("[data-color]").forEach((swatch) => {
        swatch.classList.toggle("color-swatch--active", swatch.dataset.color === state.orbColor);
      });
    }

    // Update nav active item color
    document.querySelectorAll(".nav-item--active").forEach((item) => {
      item.style.color = palette.primary;
    });

    try {
      localStorage.setItem("aura_orb_color", state.orbColor);
    } catch (_error) {
      // ignore
    }
  }

  function loadSavedOrbColor() {
    try {
      const saved = localStorage.getItem("aura_orb_color");
      if (saved && ORB_COLORS[saved]) {
        applyOrbColor(saved);
      }
    } catch (_error) {
      // ignore
    }
  }

  function detectColorChangeCommand(text) {
    const lower = String(text || "").toLowerCase().trim();
    const match = lower.match(/\b(?:change|set|switch|make)\s+(?:orb\s+)?(?:color|colour)\s+(?:to\s+)?(\w+)\b/);
    if (match) return match[1];
    const shortMatch = lower.match(/^(?:color|colour)\s+(\w+)$/);
    if (shortMatch) return shortMatch[1];
    return null;
  }

  function detectNavCommand(text) {
    const lower = String(text || "").toLowerCase().trim();
    const patterns = [
      { nav: "profile",  re: /\b(?:open|go\s+to|show|switch\s+to|view|click|navigate\s+to)\s+(?:my\s+)?profile\b/ },
      { nav: "settings", re: /\b(?:open|go\s+to|show|switch\s+to|view|click|navigate\s+to)\s+settings\b/ },
      { nav: "memory",   re: /\b(?:open|go\s+to|show|switch\s+to|view|click|navigate\s+to)\s+memory\b/ },
      { nav: "tools",    re: /\b(?:open|go\s+to|show|switch\s+to|view|click|navigate\s+to)\s+tools\b/ },
      { nav: "chat",     re: /\b(?:open|go\s+to|show|switch\s+to|go\s+back\s+to|click)\s+(?:main\s+)?(?:chat|home|assistant)\b/ },
    ];
    for (const { nav, re } of patterns) {
      if (re.test(lower)) return nav;
    }
    return null;
  }

  function normalizeCommandText(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
  }

  function resolveExternalTarget(text) {
    const normalized = normalizeCommandText(text);
    const websiteMap = [
      { label: "YouTube", pattern: /\b(?:open|launch|go to)\s+youtube\b/, url: "https://www.youtube.com" },
      { label: "Google", pattern: /\b(?:open|launch|go to)\s+google\b/, url: "https://www.google.com" },
      { label: "GitHub", pattern: /\b(?:open|launch|go to)\s+github\b/, url: "https://www.github.com" },
      { label: "Gmail", pattern: /\b(?:open|launch|go to)\s+gmail\b/, url: "https://mail.google.com" },
      { label: "WhatsApp", pattern: /\b(?:open|launch|go to)\s+whatsapp\b/, url: "https://web.whatsapp.com" },
      { label: "Spotify", pattern: /\b(?:open|launch|go to)\s+spotify\b/, url: "https://open.spotify.com" },
    ];

    for (const entry of websiteMap) {
      if (entry.pattern.test(normalized)) {
        return { ...entry, kind: "website" };
      }
    }

    const rawUrlMatch = normalized.match(/\b((?:https?:\/\/)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:\/[^\s]*)?)\b/i);
    if (/\b(?:open|launch|go to|visit)\b/.test(normalized) && rawUrlMatch) {
      const rawUrl = rawUrlMatch[1];
      const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;
      return {
        label: rawUrl.replace(/^https?:\/\//i, "").replace(/^www\./i, ""),
        kind: "website",
        url,
      };
    }

    return null;
  }

  function classifyAssistantCommand(text) {
    const normalized = normalizeCommandText(text);
    const externalTarget = resolveExternalTarget(normalized);
    if (externalTarget) {
      return {
        route: "external",
        taskType: "website",
        label: externalTarget.label,
        target: externalTarget,
      };
    }

    const internalMatchers = [
      { taskType: "coding", re: /\b(?:write|build|generate|show)\b.*\b(?:python|javascript|java|code|program|script|app)\b/ },
      { taskType: "assignment", re: /\b(?:assignment|notes|slides|presentation|document|pdf|docx|pptx)\b/ },
      { taskType: "research", re: /\b(?:research|search|find|look up|latest|current|compare)\b/ },
      { taskType: "writing", re: /\b(?:write|draft|compose|create)\b/ },
    ];

    for (const matcher of internalMatchers) {
      if (matcher.re.test(normalized)) {
        return {
          route: "internal",
          taskType: matcher.taskType,
          label: matcher.taskType,
          target: null,
        };
      }
    }

    return {
      route: "internal",
      taskType: "chat",
      label: "chat",
      target: null,
    };
  }

  function beginInternalRoute(commandText, route) {
    setOrbLayout("left");
    setAssistantState("understanding", {
      pill: "Analyzing",
      kicker: route.taskType === "chat" ? "Conversation" : route.taskType,
      headline: "Working on it.",
      description: "I'm routing this through VORIS now.",
    });
    updateLiveTranscript(commandText);
    appendConversationMessage("user", commandText, { meta: route.taskType });
  }

  function executeExternalRoute(commandText, route, { source = "text" } = {}) {
    setOrbLayout("floating");
    updateLiveTranscript(commandText);
    appendConversationMessage("user", commandText, { meta: "external" });
    setAssistantState("understanding", {
      pill: "Analyzing",
      kicker: "External task",
      headline: `Opening ${route.label}.`,
      description: "I'll keep the orb available while the external action runs.",
    });

    let opened = false;
    try {
      const popup = window.open(route.target.url, "_blank", "noopener,noreferrer");
      opened = Boolean(popup);
    } catch (_error) {
      opened = false;
    }

    const reply = opened
      ? `Opening ${route.label}.`
      : `I tried to open ${route.label}, but this browser blocked the action.`;
    updateLiveResponse(reply, { provider: "local", mode: "external" });
    appendConversationMessage("assistant", reply, { meta: opened ? "external action" : "browser blocked" });
    addConversationEntry(commandText, reply);
    addActivity("External task", reply, opened ? "good" : "warn");
    updateWakeBanner(opened ? `${route.label} is opening now.` : "This browser blocked the external action.");

    if (source !== "text") {
      void speakAssistant(reply, { resumeWakeAfter: true });
    } else if (opened) {
      setAssistantState("idle", {
        pill: "Idle",
        kicker: "External task",
        headline: `${route.label} is opening.`,
        description: "VORIS is still here when you need the next command.",
      });
    } else {
      setAssistantState("error", {
        pill: "Error",
        kicker: "External task",
        headline: "The action was blocked.",
        description: "This browser blocked the external command. Try again from a direct click if needed.",
      });
    }

    return true;
  }

  // ─────────────────────────────────────────────
  // IDLE MINIMIZE SYSTEM
  // ─────────────────────────────────────────────

  function resetIdleTimer() {
    if (state.idleTimer) {
      window.clearTimeout(state.idleTimer);
      state.idleTimer = null;
    }
    if (state.idleMinimized) {
      restoreFromIdleMinimize();
    }
    state.idleTimer = window.setTimeout(() => {
      if (!state.busy && !state.speaking && !state.listening && state.voicePhase === "idle") {
        minimizeOrb();
      }
    }, IDLE_MINIMIZE_DELAY_MS);
  }

  function minimizeOrb() {
    if (state.idleMinimized) return;
    state.idleMinimized = true;
    el.body.classList.add("orb-minimized");
    if (el.idleSuggestions) el.idleSuggestions.hidden = false;
    addActivity("Idle", "Orb minimized after 2 minutes of inactivity.", "neutral");
  }

  function restoreFromIdleMinimize() {
    if (!state.idleMinimized) return;
    state.idleMinimized = false;
    el.body.classList.remove("orb-minimized");
    if (el.idleSuggestions) el.idleSuggestions.hidden = true;
    // Wake expand spring animation
    const orbEl = document.querySelector(".core-orb");
    if (orbEl) {
      orbEl.classList.add("orb-awakening");
      window.setTimeout(() => orbEl.classList.remove("orb-awakening"), 700);
    }
    resetIdleTimer();
  }

  // ─────────────────────────────────────────────
  // NAVIGATION PANEL SYSTEM
  // ─────────────────────────────────────────────

  function switchNav(navName) {
    state.activeNav = navName;
    const panelMap = {
      chat:     "chatView",
      memory:   "panelMemory",
      tools:    "panelTools",
      profile:  "panelProfile",
      settings: "panelSettings",
    };
    const navMap = {
      chat:     "navChat",
      memory:   "navMemory",
      tools:    "navTools",
      profile:  "navProfile",
      settings: "navSettings",
    };

    Object.entries(panelMap).forEach(([key, elId]) => {
      const panelEl = el[elId];
      if (!panelEl) return;
      panelEl.hidden = key !== navName;
    });

    Object.entries(navMap).forEach(([key, elId]) => {
      const navEl = el[elId];
      if (!navEl) return;
      navEl.classList.toggle("nav-item--active", key === navName);
      if (key === navName) {
        navEl.style.color = ORB_COLORS[state.orbColor]?.primary || "";
      } else {
        navEl.style.color = "";
      }
    });

    // live-panels (transcript/response) only visible in chat view
    if (el.livePanels) el.livePanels.hidden = navName !== "chat";

    // Load panel data
    if (navName === "memory") loadMemoryPanel();
    if (navName === "tools") loadToolsPanel();
    if (navName === "profile") loadProfilePanel();
    if (navName === "settings") loadSettingsPanel();
  }

  function loadMemoryPanel() {
    // Fetch memory stats if available
    fetchJson("/api/memory/stats").then((data) => {
      if (el.memEpisodic) el.memEpisodic.textContent = String(data?.episodic_count ?? "—");
      if (el.memSemantic) el.memSemantic.textContent = String(data?.semantic_count ?? "—");
      if (el.memWorking)  el.memWorking.textContent  = String(data?.working_count ?? "—");
    }).catch(() => {
      if (el.memEpisodic) el.memEpisodic.textContent = "—";
      if (el.memSemantic) el.memSemantic.textContent = "—";
      if (el.memWorking)  el.memWorking.textContent  = "—";
    });
  }

  function loadToolsPanel() {
    if (!el.toolGrid) return;
    const capabilities = [
      { name: "Document Generation", desc: "Create PDF, DOCX, PPTX, TXT files." },
      { name: "Content Extraction", desc: "YouTube, PDF, DOCX, image OCR." },
      { name: "Web Search", desc: "Live information retrieval." },
      { name: "Voice Pipeline", desc: "Speech-to-text and text-to-speech." },
      { name: "Memory System", desc: "Episodic, semantic, working memory." },
      { name: "Agent Routing", desc: "245+ specialized task agents." },
      { name: "Code Execution", desc: "Run Python code safely." },
      { name: "File Management", desc: "Read, write, transform files." },
    ];
    el.toolGrid.innerHTML = "";
    capabilities.forEach((cap) => {
      const card = document.createElement("div");
      card.className = "tool-card";
      const name = document.createElement("p");
      name.className = "tool-card__name";
      name.textContent = cap.name;
      const desc = document.createElement("p");
      desc.className = "tool-card__desc";
      desc.textContent = cap.desc;
      card.append(name, desc);
      el.toolGrid.appendChild(card);
    });
  }

  function loadProfilePanel() {
    const authPayload = state.auth || {};
    const user = authPayload.user || null;
    if (authPayload.authenticated && user) {
      const name = user.preferred_name || user.name || user.username || "there";
      const email = user.email || "—";
      const phone = user.phone || user.phone_number || "";
      // Show authenticated view, hide guest view
      if (el.profileGuestView) el.profileGuestView.hidden = true;
      if (el.profileUserView) el.profileUserView.hidden = false;
      if (el.profileWelcome) el.profileWelcome.textContent = `Welcome back, ${name}`;
      if (el.profileSummaryText) el.profileSummaryText.textContent = authPayload.session_valid ? "Authenticated session active" : "Signed in";
      if (el.profileFieldName) el.profileFieldName.textContent = name;
      if (el.profileFieldEmail) el.profileFieldEmail.textContent = email;
      if (el.profileFieldPhone) el.profileFieldPhone.textContent = phone || "Not set";
      if (el.profileFieldSession) el.profileFieldSession.textContent = formatAuthenticatedSessionLabel(authPayload);
      if (el.profileLogoutLink) {
        el.profileLogoutLink.href = "/logout";
        el.profileLogoutLink.hidden = false;
      }
    } else {
      // Show guest view, hide authenticated view
      if (el.profileGuestView) el.profileGuestView.hidden = false;
      if (el.profileUserView) el.profileUserView.hidden = true;
    }
  }

  function loadSettingsPanel() {
    if (el.settingsVoiceLang) {
      el.settingsVoiceLang.textContent = preferredRecognitionLanguage();
    }
    // Refresh active swatch
    if (el.colorSwatches) {
      el.colorSwatches.querySelectorAll("[data-color]").forEach((swatch) => {
        swatch.classList.toggle("color-swatch--active", swatch.dataset.color === state.orbColor);
      });
    }
  }

  // ─────────────────────────────────────────────
  // SCREEN SHARE SYSTEM
  // ─────────────────────────────────────────────

  async function toggleScreenShare() {
    if (state.screenSharing) {
      stopScreenShare();
      return;
    }
    await startScreenShare();
  }

  async function startScreenShare() {
    if (!navigator.mediaDevices?.getDisplayMedia) {
      addActivity("Screen share", "Screen capture is not available in this browser.", "warn");
      updateWakeBanner("Screen sharing is not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: "always" },
        audio: false,
      });
      state.screenStream = stream;
      state.screenSharing = true;
      el.body.classList.add("screen-sharing");
      if (el.screenShareBadge) el.screenShareBadge.hidden = false;
      if (el.screenShareStatus) el.screenShareStatus.textContent = "Active";
      if (el.screenShareButton) {
        el.screenShareButton.title = "Stop screen share";
        el.screenShareButton.classList.add("dock-button--active");
      }
      if (el.screenPreviewVideo && el.screenPreviewWrap) {
        el.screenPreviewVideo.srcObject = stream;
        el.screenPreviewWrap.hidden = false;
        if (!state.detailsOpen) setDetailsOpen(true);
      }

      stream.getVideoTracks().forEach((track) => {
        track.addEventListener("ended", () => stopScreenShare());
      });

      addActivity("Screen share", "Screen is being shared with VORIS. Visual context is captured — analysis pending.", "good");
      updateWakeBanner("Screen sharing active. VORIS has your screen captured.");
    } catch (error) {
      if (error?.name !== "NotAllowedError") {
        addActivity("Screen share", error?.message || "Could not start screen capture.", "error");
      }
    }
  }

  function stopScreenShare() {
    if (state.screenStream) {
      state.screenStream.getTracks().forEach((track) => track.stop());
      state.screenStream = null;
    }
    state.screenSharing = false;
    el.body.classList.remove("screen-sharing");
    if (el.screenShareBadge) el.screenShareBadge.hidden = true;
    if (el.screenShareStatus) el.screenShareStatus.textContent = "Off";
    if (el.screenShareButton) {
      el.screenShareButton.title = "Share your screen with VORIS";
      el.screenShareButton.classList.remove("dock-button--active");
    }
    if (el.screenPreviewVideo) el.screenPreviewVideo.srcObject = null;
    if (el.screenPreviewWrap) el.screenPreviewWrap.hidden = true;
    addActivity("Screen share", "Screen sharing stopped.", "neutral");
  }

  // ─────────────────────────────────────────────
  // OVERLAY MODE
  // ─────────────────────────────────────────────

  function toggleOverlayMode() {
    state.overlayMode = !state.overlayMode;
    el.body.classList.toggle("orb-overlay", state.overlayMode);
    if (el.overlayToggle) {
      el.overlayToggle.classList.toggle("is-active", state.overlayMode);
      el.overlayToggle.setAttribute("aria-pressed", String(state.overlayMode));
      el.overlayToggle.title = state.overlayMode ? "Exit overlay mode" : "Toggle floating orb overlay";
    }
    addActivity("Overlay", state.overlayMode ? "Floating orb overlay enabled." : "Overlay mode off.", "neutral");
  }

  // ─────────────────────────────────────────────
  // SECURITY MODAL SYSTEM
  // ─────────────────────────────────────────────

  function showPinError(message) {
    if (!el.modalPinError) return;
    el.modalPinError.textContent = message;
    el.modalPinError.hidden = false;
  }

  function clearPinError() {
    if (!el.modalPinError) return;
    el.modalPinError.textContent = "";
    el.modalPinError.hidden = true;
  }

  function resolveSecurityModal(confirmed, extras = {}) {
    hideAllSecurityModals();
    if (state.pendingSecurityResolve) {
      const fn = state.pendingSecurityResolve;
      state.pendingSecurityResolve = null;
      state.pendingSecurityReject = null;
      fn({ confirmed, ...extras });
    }
  }

  function hideAllSecurityModals() {
    if (el.modalConfirm) el.modalConfirm.hidden = true;
    if (el.modalSession) el.modalSession.hidden = true;
    if (el.modalPin) el.modalPin.hidden = true;
    if (el.modalPinInput) el.modalPinInput.value = "";
    clearPinError();
  }

  function askSecurityConfirmation({ trustLevel, reason, hint, actionName }) {
    return new Promise((resolve, reject) => {
      state.pendingSecurityResolve = resolve;
      state.pendingSecurityReject  = reject;

      hideAllSecurityModals();

      if (trustLevel === "critical") {
        if (el.modalPinReason) el.modalPinReason.textContent = reason || "A security PIN is required for this action.";
        if (el.modalPinHint)   el.modalPinHint.textContent   = hint || "";
        if (el.modalPinTitle)  el.modalPinTitle.textContent  = actionName ? `PIN required for: ${actionName}` : "PIN Required";
        clearPinError();
        if (el.modalPin) el.modalPin.hidden = false;
        window.setTimeout(() => el.modalPinInput?.focus(), 60);
      } else if (trustLevel === "sensitive") {
        if (el.modalSessionReason) el.modalSessionReason.textContent = reason || "Session-level approval is needed.";
        if (el.modalSessionHint)   el.modalSessionHint.textContent   = hint || "";
        if (el.modalSession) el.modalSession.hidden = false;
      } else {
        // private — simple confirm
        if (el.modalConfirmReason) el.modalConfirmReason.textContent = reason || "Confirm you want to do this.";
        if (el.modalConfirmHint)   el.modalConfirmHint.textContent   = hint || "";
        if (el.modalConfirm) el.modalConfirm.hidden = false;
      }
    });
  }

  async function handleSecurityRequired(permissionInfo, originalMessage) {
    const trustLevel = String(permissionInfo?.trust_level || "private").toLowerCase();
    const reason = String(permissionInfo?.reason || "This action needs your approval.");
    const hint = String(permissionInfo?.next_step_hint || "");
    const actionName = String(permissionInfo?.action_name || "");

    addActivity("Security", `${humanizeStatus(trustLevel)} approval needed for: ${actionName || "action"}`, "warn");

    let result;
    try {
      result = await askSecurityConfirmation({ trustLevel, reason, hint, actionName });
    } catch (_error) {
      return null;
    }

    if (!result?.confirmed) {
      addActivity("Security", "Action cancelled by user.", "neutral");
      return null;
    }

    const retryPayload = {
      message: originalMessage,
      mode: "hybrid",
      confirmed: true,
    };

    if (trustLevel === "critical" && result.pin) {
      retryPayload.pin = result.pin;
    } else if (trustLevel === "sensitive") {
      retryPayload.confirmed = true;
    }

    addActivity("Security", "Retrying with approval…", "neutral");
    return requestJson("/api/chat", retryPayload, { timeoutMs: CHAT_REQUEST_TIMEOUT_MS });
  }

  // ─────────────────────────────────────────────
  // RECENT OUTPUTS PANEL (right context panel)
  // ─────────────────────────────────────────────

  function addOutputCard(delivery) {
    if (!el.outputList || !delivery) return;

    const existing = el.outputList.querySelector(".provider-empty");
    if (existing) existing.remove();

    const card = document.createElement("div");
    card.className = "output-card";

    const name = document.createElement("p");
    name.className = "output-card__name";
    name.textContent = delivery.title || delivery.fileName || "Document";

    const row = document.createElement("div");
    row.className = "output-card__row";

    if (delivery.downloadUrl) {
      const link = document.createElement("a");
      link.className = "output-card__link";
      link.href = delivery.downloadUrl;
      link.textContent = String(delivery.format || "Download").toUpperCase();
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
      row.appendChild(link);
    }

    const altLinks = Object.entries(delivery.alternateFormatLinks || {});
    altLinks.slice(0, 3).forEach(([fmt, href]) => {
      const link = document.createElement("a");
      link.className = "output-card__link";
      link.href = href;
      link.textContent = String(fmt).toUpperCase();
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
      row.appendChild(link);
    });

    card.append(name, row);

    // Keep last 5 outputs
    el.outputList.insertBefore(card, el.outputList.firstChild);
    const cards = el.outputList.querySelectorAll(".output-card");
    cards.forEach((c, index) => {
      if (index >= 5) c.remove();
    });
  }

  // ─────────────────────────────────────────────
  // SIDEBAR CONVERSATION TRACKING
  // ─────────────────────────────────────────────

  function addConversationEntry(userText, answerText) {
    if (!el.navConversations) return;
    // Remove empty state message
    if (el.navConvEmpty) el.navConvEmpty.hidden = true;

    const item = document.createElement("button");
    item.className = "nav-conv-item";
    item.type = "button";

    const dot = document.createElement("span");
    dot.className = "nav-conv-item__dot";

    const text = document.createElement("span");
    text.className = "nav-conv-item__text";
    text.textContent = String(userText || "").slice(0, 48);

    const now = new Date();
    const time = document.createElement("span");
    time.className = "nav-conv-item__time";
    time.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    item.append(dot, text, time);
    item.title = String(userText || "");
    item.addEventListener("click", () => {
      // Clicking a history item scrolls response into view / switches to chat
      switchNav("chat");
    });

    el.navConversations.insertBefore(item, el.navConversations.firstChild);
    // Keep max 20 entries
    const items = el.navConversations.querySelectorAll(".nav-conv-item");
    items.forEach((c, i) => { if (i >= 20) c.remove(); });
    filterConversationLists(String(el.navSearch?.value || ""));
  }

  function clearConversationHistory({ keepArchiveState = false } = {}) {
    if (!el.navConversations) return;
    el.navConversations.querySelectorAll(".nav-conv-item").forEach((c) => c.remove());
    if (el.navConvEmpty) el.navConvEmpty.hidden = false;
    if (!keepArchiveState) {
      state.archivedChats = [];
      renderArchivedChats();
    }
    state.chatMessages = [];
    renderConversationThread();
    state.chatLocked = false;
    renderChatLockState();
    setOrbLayout("topbar");
    updateLiveTranscript("Waiting for your voice or text command.");
    updateLiveResponse("VORIS is standing by.");
    updateWakeBanner(currentWakeBanner());
  }

})();
