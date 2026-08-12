(function () {
  "use strict";

  const STORAGE_KEY_SESSION = "voris-static-session-id";
  const ORB_CAPTIONS = {
    idle: "Calm presence",
    thinking: "Working with you",
    responding: "Delivering the result",
    error: "Needs a clean retry",
  };

  const el = {};
  const state = {
    sessionId: localStorage.getItem(STORAGE_KEY_SESSION) || createSessionId(),
    messages: [],
    messageDomById: new Map(),
    requestInFlight: false,
    assistantState: "idle",
    activeAbort: null,
  };

  function createSessionId() {
    return `voris-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function cacheElements() {
    el.app = document.getElementById("vorisApp");
    el.conversationThread = document.getElementById("conversationThread");
    el.chatScroll = document.getElementById("chatScroll");
    el.messageInput = document.getElementById("messageInput");
    el.systemFileInput = document.getElementById("systemFileInput");
    el.composerForm = document.getElementById("composerForm");
    el.sendButton = document.getElementById("sendButton");
    el.composerStatus = document.getElementById("composerStatus");
    el.workspaceSummary = document.getElementById("workspaceSummary");
    el.orbCaption = document.getElementById("orbCaption");
    el.runtimeDot = document.getElementById("runtimeDot");
    el.runtimeLabel = document.getElementById("runtimeLabel");
    el.assistantStateLabel = document.getElementById("assistantStateLabel");
    el.sessionLabel = document.getElementById("sessionLabel");
    el.capabilityList = document.getElementById("capabilityList");
    el.providerList = document.getElementById("providerList");
    el.newChatButton = document.getElementById("newChatButton");
  }

  function setAssistantState(next) {
    const normalized = String(next || "idle").toLowerCase();
    state.assistantState = normalized;
    if (el.app) {
      el.app.dataset.assistantState = normalized;
    }
    if (el.orbCaption) {
      el.orbCaption.textContent = ORB_CAPTIONS[normalized] || ORB_CAPTIONS.idle;
    }
    if (el.assistantStateLabel) {
      el.assistantStateLabel.textContent = normalized;
    }
    if (el.runtimeDot) {
      el.runtimeDot.className = "status-dot";
      if (normalized === "thinking" || normalized === "responding") {
        el.runtimeDot.classList.add("status-dot--busy");
      } else if (normalized === "error") {
        el.runtimeDot.classList.add("status-dot--error");
      } else {
        el.runtimeDot.classList.add("status-dot--idle");
      }
    }
  }

  function setComposerStatus(text) {
    if (el.composerStatus) {
      el.composerStatus.textContent = text;
    }
  }

  function setWorkspaceSummary(text) {
    if (el.workspaceSummary) {
      el.workspaceSummary.textContent = text;
    }
  }

  async function apiJson(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-VORIS-Session-Id": state.sessionId,
        ...(options.headers || {}),
      },
      ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = body.error || body.message || body.detail || `Request failed (${response.status})`;
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return body;
  }

  function humanizeBadge(value) {
    return String(value || "Assistant")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function formatClock(iso) {
    try {
      return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    } catch (_error) {
      return "";
    }
  }

  function shortSessionId(id) {
    const value = String(id || "");
    return value.length > 10 ? `${value.slice(0, 6)}…${value.slice(-4)}` : value;
  }

  function scrollToBottom() {
    if (!el.chatScroll) {
      return;
    }
    const scroll = () => {
      el.chatScroll.scrollTo({ top: el.chatScroll.scrollHeight, behavior: "smooth" });
    };
    requestAnimationFrame(() => {
      scroll();
      requestAnimationFrame(scroll);
    });
  }

  function ensureMessageId(message) {
    if (!message.id) {
      message.id = `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }
    return message.id;
  }

  function getMessageRow(messageId) {
    return messageId ? state.messageDomById.get(messageId) || null : null;
  }

  function removeWelcomeCard() {
    el.conversationThread?.querySelector(".welcome-card")?.remove();
  }

  function showWelcomeCard() {
    if (!el.conversationThread || el.conversationThread.querySelector(".welcome-card")) {
      return;
    }
    const card = document.createElement("section");
    card.className = "welcome-card";
    const title = document.createElement("h3");
    title.textContent = "What should we handle first?";
    const body = document.createElement("p");
    body.textContent =
      "Chat, documents, safe desktop actions, or image prompts like “draw a picture of a cyberpunk city.”";
    card.append(title, body);
    el.conversationThread.appendChild(card);
  }

  function clearConversationView() {
    if (!el.conversationThread) {
      return;
    }
    el.conversationThread.replaceChildren();
    state.messageDomById.clear();
  }

  function renderTextBody(text) {
    const body = document.createElement("div");
    body.className = "message__body";
    const source = String(text || "").trim();
    if (!source) {
      const placeholder = document.createElement("p");
      placeholder.className = "message__placeholder";
      placeholder.textContent = "VORIS is writing…";
      body.appendChild(placeholder);
      return body;
    }

    const fence = /```([a-zA-Z0-9_+\-.#]*)\n?([\s\S]*?)```/g;
    let cursor = 0;
    let match = fence.exec(source);
    while (match) {
      appendParagraphs(source.slice(cursor, match.index), body);
      const pre = document.createElement("pre");
      pre.textContent = match[2] || "";
      body.appendChild(pre);
      cursor = fence.lastIndex;
      match = fence.exec(source);
    }
    appendParagraphs(source.slice(cursor), body);
    return body;
  }

  function appendParagraphs(source, container) {
    const chunks = String(source || "")
      .split(/\n{2,}/)
      .map((part) => part.trim())
      .filter(Boolean);
    chunks.forEach((chunk) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = chunk.replace(/\n/g, " ");
      container.appendChild(paragraph);
    });
  }

  function resolveImageUrl(message) {
    return String(message.imageUrl || message.image_url || "").trim();
  }

  function isImageBypass(message) {
    const mode = String(message.executionMode || message.execution_mode || "").toLowerCase();
    return mode === "image_bypass" || Boolean(resolveImageUrl(message));
  }

  function buildMessageImage(url) {
    const figure = document.createElement("figure");
    figure.className = "message__image";
    const img = document.createElement("img");
    img.src = url;
    img.alt = "Generated image";
    img.loading = "lazy";
    img.decoding = "async";
    img.referrerPolicy = "no-referrer";
    figure.appendChild(img);
    return figure;
  }

  function buildMessageRow(message) {
    ensureMessageId(message);
    const row = document.createElement("article");
    row.className = `message message--${message.role === "user" ? "user" : "assistant"}`;
    if (message.streaming) {
      row.classList.add("message--streaming");
    }
    row.dataset.messageId = message.id;

    const card = document.createElement("div");
    card.className = "message__card";

    const meta = document.createElement("div");
    meta.className = "message__meta";
    const label = document.createElement("span");
    label.textContent = message.role === "user" ? "You" : "VORIS";
    const metaRight = document.createElement("span");
    if (message.badge) {
      const badge = document.createElement("span");
      badge.className = "message__badge";
      badge.textContent = humanizeBadge(message.badge);
      metaRight.appendChild(badge);
    }
    const time = document.createElement("span");
    time.textContent = formatClock(message.timestamp);
    metaRight.appendChild(time);
    meta.append(label, metaRight);
    card.appendChild(meta);

    const imageUrl = resolveImageUrl(message);
    if (isImageBypass(message) && imageUrl) {
      card.appendChild(buildMessageImage(imageUrl));
    } else {
      const body = renderTextBody(message.text);
      body.classList.add("message-card__content");
      card.appendChild(body);
    }

    row.appendChild(card);
    return row;
  }

  function mountMessage(message) {
    if (!el.conversationThread) {
      return null;
    }
    ensureMessageId(message);
    const existing = getMessageRow(message.id);
    if (existing) {
      return existing;
    }
    removeWelcomeCard();
    const row = buildMessageRow(message);
    state.messageDomById.set(message.id, row);
    el.conversationThread.appendChild(row);
    return row;
  }

  function unmountMessage(messageId) {
    getMessageRow(messageId)?.remove();
    state.messageDomById.delete(messageId);
    if (!state.messages.length) {
      showWelcomeCard();
    }
  }

  function updateMessageText(message) {
    const row = getMessageRow(message.id);
    if (!row) {
      return;
    }
    const card = row.querySelector(".message__card");
    if (!card) {
      return;
    }
    const nextBody = renderTextBody(message.text);
    nextBody.classList.add("message-card__content");
    const current = card.querySelector(".message-card__content");
    if (current) {
      current.replaceWith(nextBody);
      return;
    }
    const image = card.querySelector(".message__image");
    if (image) {
      image.replaceWith(nextBody);
    } else {
      card.appendChild(nextBody);
    }
  }

  function syncMessageRowState(message) {
    const row = getMessageRow(message.id);
    if (!row) {
      return;
    }
    row.classList.toggle("message--streaming", Boolean(message.streaming));
    const badge = row.querySelector(".message__badge");
    if (badge && message.badge) {
      badge.textContent = humanizeBadge(message.badge);
    }
  }

  function refreshMessageRow(message) {
    ensureMessageId(message);
    const row = getMessageRow(message.id);
    const nextRow = buildMessageRow(message);
    if (row) {
      row.replaceWith(nextRow);
    } else {
      removeWelcomeCard();
      el.conversationThread?.appendChild(nextRow);
    }
    state.messageDomById.set(message.id, nextRow);
  }

  function appendMessage(message) {
    ensureMessageId(message);
    state.messages.push(message);
    mountMessage(message);
    scrollToBottom();
    return message;
  }

  function resetConversation() {
    state.messages = [];
    clearConversationView();
    showWelcomeCard();
    setComposerStatus("New chat ready.");
    setWorkspaceSummary("Fresh workspace — ask anything.");
    setAssistantState("idle");
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
      return { event: eventName, data: JSON.parse(dataLines.join("\n")) };
    } catch (_error) {
      return null;
    }
  }

  async function requestChat(commandText) {
    if (!window.ReadableStream || !window.TextDecoder) {
      return {
        payload: await apiJson("/api/chat", {
          method: "POST",
          body: JSON.stringify({ message: commandText, mode: "hybrid" }),
        }),
        streamed: null,
      };
    }

    const controller = new AbortController();
    state.activeAbort = controller;

    const streamed = appendMessage({
      role: "assistant",
      text: "",
      badge: "Assistant",
      timestamp: new Date().toISOString(),
      streaming: true,
    });

    let finalPayload = null;
    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
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
        for (const raw of events) {
          const event = parseSseEvent(raw);
          if (!event) {
            continue;
          }
          if (event.event === "chunk" && event.data?.text) {
            streamed.text += String(event.data.text);
            updateMessageText(streamed);
            scrollToBottom();
          } else if (event.event === "error") {
            streamed.text = String(event.data?.message || streamed.text || "Request failed.");
            updateMessageText(streamed);
          } else if (event.event === "final") {
            finalPayload = event.data || {};
          }
        }
      }
      if (!finalPayload) {
        throw new Error("Stream ended before final payload.");
      }
      return { payload: finalPayload, streamed };
    } finally {
      state.activeAbort = null;
    }
  }

  async function requestChatWithFile(commandText, file) {
    const formData = new FormData();
    formData.append("message", commandText || "");
    formData.append("file", file);

    const response = await fetch("/api/chat/file", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-VORIS-Session-Id": state.sessionId,
      },
      body: formData,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = payload.error || payload.message || payload.detail || `Upload failed (${response.status})`;
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return { payload, streamed: null };
  }

  function applyFinalPayload(streamed, payload) {
    const imageUrl = String(payload.image_url || "").trim();
    const isImageBypass = payload.execution_mode === "image_bypass" || Boolean(imageUrl);
    Object.assign(streamed, {
      streaming: false,
      text: isImageBypass ? "" : String(payload.reply || payload.content || streamed.text || "").trim(),
      imageUrl: imageUrl || undefined,
      executionMode: payload.execution_mode,
      badge: humanizeBadge(payload.execution_mode || "Assistant"),
    });
    refreshMessageRow(streamed);
    syncMessageRowState(streamed);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (state.requestInFlight) {
      return;
    }
    const text = String(el.messageInput?.value || "").trim();
    const file = el.systemFileInput?.files?.[0] || null;
    if (!text && !file) {
      return;
    }

    state.requestInFlight = true;
    el.messageInput.value = "";
    el.sendButton.disabled = true;
    setAssistantState("thinking");
    setComposerStatus(file ? "Reading your file..." : "Working on that…");

    appendMessage({
      role: "user",
      text: file ? `${text || "Analyze this file."}\n\nAttached: ${file.name}` : text,
      badge: "You",
      timestamp: new Date().toISOString(),
    });

    try {
      const { payload, streamed } = file ? await requestChatWithFile(text, file) : await requestChat(text);
      if (streamed) {
        applyFinalPayload(streamed, payload);
      } else {
        const imageUrl = String(payload.image_url || "").trim();
        const isImageBypass = payload.execution_mode === "image_bypass" || Boolean(imageUrl);
        appendMessage({
          role: "assistant",
          text: isImageBypass ? "" : String(payload.reply || payload.content || "Done."),
          imageUrl: imageUrl || undefined,
          executionMode: payload.execution_mode,
          badge: humanizeBadge(payload.execution_mode || "Assistant"),
          timestamp: new Date().toISOString(),
        });
      }
      setAssistantState("responding");
      if (el.systemFileInput) {
        el.systemFileInput.value = "";
      }
      if (el.composerStatus) {
        el.composerStatus.style.color = "";
      }
      setComposerStatus("Ready");
      setWorkspaceSummary("Last response delivered.");
      window.setTimeout(() => setAssistantState("idle"), 1200);
    } catch (error) {
      setAssistantState("error");
      setComposerStatus(error.message || "Something went wrong.");
      appendMessage({
        role: "assistant",
        text: "I couldn't complete that request. Please try again.",
        badge: "Error",
        timestamp: new Date().toISOString(),
      });
      window.setTimeout(() => setAssistantState("idle"), 2000);
    } finally {
      state.requestInFlight = false;
      el.sendButton.disabled = false;
      scrollToBottom();
    }
  }

  function renderCapabilityList(items) {
    if (!el.capabilityList) {
      return;
    }
    el.capabilityList.replaceChildren();
    const list = Array.isArray(items) ? items.slice(0, 8) : [];
    if (!list.length) {
      const li = document.createElement("li");
      li.className = "capability-list__item";
      li.textContent = "Loading…";
      el.capabilityList.appendChild(li);
      return;
    }
    list.forEach((item) => {
      const li = document.createElement("li");
      li.className = "capability-list__item";
      const name = document.createElement("span");
      name.textContent = item.name || item.id || "Capability";
      const mode = document.createElement("span");
      mode.textContent = item.mode || item.status || "—";
      li.append(name, mode);
      el.capabilityList.appendChild(li);
    });
  }

  function renderProviderList(items) {
    if (!el.providerList) {
      return;
    }
    el.providerList.replaceChildren();
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      const li = document.createElement("li");
      li.className = "provider-list__item";
      li.textContent = "No provider data";
      el.providerList.appendChild(li);
      return;
    }
    list.slice(0, 6).forEach((item) => {
      const li = document.createElement("li");
      li.className = "provider-list__item";
      const name = document.createElement("span");
      name.textContent = item.name || item.provider || "Provider";
      const status = document.createElement("span");
      status.textContent = item.status || item.health || "unknown";
      li.append(name, status);
      el.providerList.appendChild(li);
    });
  }

  async function refreshSystemPanels() {
    if (el.sessionLabel) {
      el.sessionLabel.textContent = shortSessionId(state.sessionId);
    }
    if (el.runtimeLabel) {
      el.runtimeLabel.textContent = "Online";
    }

    try {
      const [health, capabilities, providers] = await Promise.all([
        apiJson("/api/system/health").catch(() => null),
        apiJson("/api/capabilities").catch(() => null),
        apiJson("/api/providers").catch(() => null),
      ]);
      if (health?.status) {
        el.runtimeLabel.textContent = String(health.status);
      }
      renderCapabilityList(capabilities?.items || []);
      renderProviderList(providers?.items || []);
    } catch (_error) {
      renderCapabilityList([]);
      renderProviderList([]);
    }
  }

  function bindEvents() {
    el.composerForm?.addEventListener("submit", handleSubmit);
    el.newChatButton?.addEventListener("click", () => {
      state.sessionId = createSessionId();
      localStorage.setItem(STORAGE_KEY_SESSION, state.sessionId);
      resetConversation();
      void refreshSystemPanels();
    });
    el.messageInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        el.composerForm?.requestSubmit();
      }
    });
  }

  async function boot() {
    cacheElements();
    localStorage.setItem(STORAGE_KEY_SESSION, state.sessionId);
    bindEvents();
    showWelcomeCard();
    setAssistantState("idle");
    setComposerStatus("Ready");
    await refreshSystemPanels();
    window.setInterval(refreshSystemPanels, 60000);
  }

  boot();
})();

document.addEventListener("DOMContentLoaded", () => {
  const uploadButton = document.getElementById("uploadButton");
  const systemFileInput = document.getElementById("systemFileInput");
  const backendPingDot = document.getElementById("backendPingDot");
  const composerStatus = document.getElementById("composerStatus");

  uploadButton?.addEventListener("click", () => {
    systemFileInput?.click();
  });

  systemFileInput?.addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file && composerStatus) {
      composerStatus.innerText = `Selected: ${file.name}`;
      composerStatus.style.color = "#00f0ff";
    }
  });

  async function checkBackendHealth() {
    try {
      const response = await fetch("http://localhost:8000/ping");
      const data = await response.json();

      if (response.ok && data.status === "online") {
        if (backendPingDot) {
          backendPingDot.style.background = "#00ffcc";
          backendPingDot.style.boxShadow = "0 0 10px #00ffcc";
        }
        if (composerStatus && !systemFileInput?.files?.length) {
          composerStatus.textContent = "Core Stable";
        }
        return;
      }

      throw new Error("Backend offline");
    } catch (_error) {
      if (backendPingDot) {
        backendPingDot.style.background = "#ff4444";
        backendPingDot.style.boxShadow = "0 0 10px #ff4444";
      }
      if (composerStatus && !systemFileInput?.files?.length) {
        composerStatus.textContent = "Core Offline";
      }
    }
  }

  void checkBackendHealth();
  setInterval(checkBackendHealth, 15000);
});
