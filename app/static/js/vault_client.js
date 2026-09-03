/**
 * ============================================================================
 * THE INCONVENIENT VAULT — OPERATOR CLIENT CONTROLLER
 * Real-Time WebSocket Telemetry, WebRTC Media Ingestion, and REST Dispatches
 * ============================================================================
 */

class VaultClient {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 30;
    this.reconnectInterval = 1000;
    this.mediaStream = null;
    this.audioRecorder = null;
    this.audioChunks = [];

    this.initElements();
    this.initEventListeners();
    this.connectWebSocket();
    this.fetchStatus();
    this.fetchAuditLogs();
  }

  initElements() {
    // Top Bar
    this.wsStatusEl = document.getElementById("wsStatusIndicator");

    // HUD Telemetry
    this.oledLine1El = document.getElementById("oledLine1");
    this.oledLine2El = document.getElementById("oledLine2");
    this.ledLampEl = document.getElementById("ledLamp");
    this.ledColorLabelEl = document.getElementById("ledColorLabel");
    this.stateLabelEl = document.getElementById("stateLabel");
    this.lockGraphicEl = document.getElementById("lockGraphic");
    this.lockStatusLabelEl = document.getElementById("lockStatusLabel");
    this.operatorLabelEl = document.getElementById("operatorLabel");
    this.attemptsLabelEl = document.getElementById("attemptsLabel");

    // Stepper Nodes
    this.stepNodes = {
      IDLE: document.getElementById("stepNodeIdle"),
      AWAITING_RFID: document.getElementById("stepNodeRfid"),
      AWAITING_FINGERPRINT: document.getElementById("stepNodeFp"),
      AWAITING_FACE: document.getElementById("stepNodeFace"),
      AWAITING_PASSWORD: document.getElementById("stepNodePwd"),
      AWAITING_VOICE: document.getElementById("stepNodeVoice"),
      UNLOCKED: document.getElementById("stepNodeUnlocked"),
    };

    // Stage Inputs
    this.rfidInput = document.getElementById("rfidInput");
    this.fpIdInput = document.getElementById("fpIdInput");
    this.pwdInput = document.getElementById("pwdInput");
    this.voicePhraseInput = document.getElementById("voicePhraseInput");

    // Camera Preview
    this.camVideo = document.getElementById("camVideo");
    this.camCanvas = document.getElementById("camCanvas");

    // Audit Table & Integrity Pill
    this.auditTableBody = document.getElementById("auditTableBody");
    this.integrityPill = document.getElementById("integrityPill");
    this.integrityStatusText = document.getElementById("integrityStatusText");
    this.toastContainer = document.getElementById("toastContainer");
  }

  initEventListeners() {
    // Master Actions
    document.getElementById("btnStartAuth")?.addEventListener("click", () => this.startAuthentication());
    document.getElementById("btnResetVault")?.addEventListener("click", () => this.resetVault());
    document.getElementById("btnTamper")?.addEventListener("click", () => this.simulateTamper());
    document.getElementById("btnAdminReset")?.addEventListener("click", () => this.promptAdminReset());
    document.getElementById("btnRefreshLogs")?.addEventListener("click", () => this.fetchAuditLogs());

    // Stage 1: RFID
    document.getElementById("btnScanAuthRfid")?.addEventListener("click", () => this.submitRfid("E2806894"));
    document.getElementById("btnScanInvalidRfid")?.addEventListener("click", () => this.submitRfid("DEADBEEF"));
    document.getElementById("btnScanCustomRfid")?.addEventListener("click", () => this.submitRfid(this.rfidInput.value));

    // Stage 2: Fingerprint
    document.getElementById("btnScanAuthFp")?.addEventListener("click", () => this.submitFingerprint(1, true, 0.98));
    document.getElementById("btnScanInvalidFp")?.addEventListener("click", () => this.submitFingerprint(99, false, 0.20));

    // Stage 3: Face
    document.getElementById("btnStartCam")?.addEventListener("click", () => this.initWebcam());
    document.getElementById("btnCaptureFace")?.addEventListener("click", () => this.captureWebcamAndSubmit());
    document.getElementById("btnAuthFaceMock")?.addEventListener("click", () => this.submitFaceSynthetic(777));
    document.getElementById("btnIntruderFaceMock")?.addEventListener("click", () => this.submitFaceSynthetic(999));

    // Stage 4: Password
    document.getElementById("btnSubmitPwd")?.addEventListener("click", () => this.submitPassword(this.pwdInput.value));
    document.getElementById("btnInjectAuthPwd")?.addEventListener("click", () => {
      this.pwdInput.value = "VaultMasterKey#2026!";
      this.submitPassword("VaultMasterKey#2026!");
    });
    document.getElementById("btnInjectWrongPwd")?.addEventListener("click", () => {
      this.pwdInput.value = "WrongPassword123";
      this.submitPassword("WrongPassword123");
    });

    // Stage 5: Voice
    document.getElementById("btnRecordMic")?.addEventListener("click", () => this.recordMicAndSubmit());
    document.getElementById("btnAuthVoiceMock")?.addEventListener("click", () =>
      this.submitVoiceSynthetic(1, this.voicePhraseInput.value || "OPEN SESAME OVERENGINEERED")
    );
    document.getElementById("btnIntruderVoiceMock")?.addEventListener("click", () =>
      this.submitVoiceSynthetic(2, this.voicePhraseInput.value || "OPEN SESAME OVERENGINEERED")
    );
  }

  // =========================================================================
  // WebSocket Telemetry Connection
  // =========================================================================

  connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/vault`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.wsStatusEl.className = "ws-status-indicator ws-connected";
      this.wsStatusEl.querySelector(".status-text").textContent = "TELEMETRY LIVE";
      this.showToast("Connected to Vault Telemetry Stream", "success");
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.handleWebSocketMessage(msg);
      } catch (err) {
        console.error("Error parsing WebSocket message:", err);
      }
    };

    this.ws.onclose = () => {
      this.wsStatusEl.className = "ws-status-indicator ws-disconnected";
      this.wsStatusEl.querySelector(".status-text").textContent = "DISCONNECTED";
      this.scheduleReconnect();
    };

    this.ws.onerror = (err) => {
      console.warn("WebSocket encountered error:", err);
      this.ws.close();
    };
  }

  scheduleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const timeout = Math.min(10000, this.reconnectInterval * Math.pow(1.5, this.reconnectAttempts - 1));
      setTimeout(() => this.connectWebSocket(), timeout);
    }
  }

  handleWebSocketMessage(msg) {
    if (msg.event === "INITIAL_STATE" || msg.event === "STATE_CHANGE") {
      this.fetchStatus();
      this.fetchAuditLogs();
    } else if (msg.event === "HARDWARE_EVENT") {
      this.fetchStatus();
    }
  }

  // =========================================================================
  // REST API Helpers & Action Dispatches
  // =========================================================================

  async fetchStatus() {
    try {
      const res = await fetch("/api/v1/vault/status");
      if (res.ok) {
        const data = await res.json();
        this.updateHUD(data);
      }
    } catch (ex) {
      console.warn("Status fetch error:", ex);
    }
  }

  async fetchAuditLogs() {
    try {
      const res = await fetch("/api/v1/audit/logs?limit=30");
      if (res.ok) {
        const data = await res.json();
        this.updateAuditTable(data);
      }
    } catch (ex) {
      console.warn("Audit logs fetch error:", ex);
    }
  }

  async startAuthentication() {
    const res = await this.postJSON("/api/v1/vault/start", {});
    if (res.success) {
      this.showToast(res.message, "success");
      this.fetchStatus();
    } else {
      this.showToast(res.message || "Failed to start authentication", "error");
    }
  }

  async resetVault(adminKey = null) {
    const payload = adminKey ? { admin_override_key: adminKey } : {};
    const res = await this.postJSON("/api/v1/vault/reset", payload);
    if (res.success) {
      this.showToast(res.message, "success");
      this.fetchStatus();
      this.fetchAuditLogs();
    } else {
      this.showToast(res.message || "Reset failed", "error");
    }
  }

  promptAdminReset() {
    const key = prompt("Enter Emergency Administrator Override Key:", "ADMIN_RESET_9999");
    if (key) {
      this.resetVault(key);
    }
  }

  async simulateTamper() {
    const res = await this.postJSON("/api/v1/simulate/tamper", {
      reason: "Operator initiated emergency tamper breach test",
    });
    this.showToast("Chassis tamper triggered! Security Lockout activated.", "error");
    this.fetchStatus();
    this.fetchAuditLogs();
  }

  async submitRfid(cardUid) {
    if (!cardUid) return this.showToast("Please enter an RFID card UID", "warning");
    const res = await this.postJSON("/api/v1/simulate/rfid", { card_uid: cardUid });
    this.showToast(res.message, res.success ? "success" : "error");
    this.fetchStatus();
  }

  async submitFingerprint(fingerId, matched, confidence) {
    const res = await this.postJSON("/api/v1/simulate/fingerprint", {
      finger_id: fingerId,
      matched: matched,
      confidence: confidence,
    });
    this.showToast(res.message, res.success ? "success" : "error");
    this.fetchStatus();
  }

  async submitFaceSynthetic(subjectSeed) {
    const res = await this.postJSON("/api/v1/simulate/face", {
      subject_seed: subjectSeed,
      noise_level: 0.01,
    });
    this.showToast(res.message, res.success ? "success" : "error");
    this.fetchStatus();
  }

  async submitPassword(pwd) {
    if (!pwd) return this.showToast("Please enter a password", "warning");
    const res = await this.postJSON("/api/v1/auth/password", { password: pwd });
    this.showToast(res.message, res.success ? "success" : "error");
    this.fetchStatus();
  }

  async submitVoiceSynthetic(speakerSeed, phrase) {
    const res = await this.postJSON("/api/v1/simulate/voice", {
      speaker_seed: speakerSeed,
      spoken_phrase: phrase,
      noise_level: 0.01,
    });
    this.showToast(res.message, res.success ? "success" : "error");
    this.fetchStatus();
  }

  async postJSON(url, body) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return await res.json();
    } catch (ex) {
      return { success: false, message: `Request error: ${ex.message}` };
    }
  }

  // =========================================================================
  // WebRTC Camera & Microphone Helpers
  // =========================================================================

  async initWebcam() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return this.showToast("WebRTC camera not supported in this browser.", "warning");
      }
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } });
      this.camVideo.srcObject = this.mediaStream;
      this.camVideo.style.display = "block";
      this.showToast("Webcam connected.", "success");
    } catch (ex) {
      this.showToast(`Camera permission error: ${ex.message}. Use Mock buttons.`, "warning");
    }
  }

  async captureWebcamAndSubmit() {
    if (!this.camVideo.srcObject) {
      await this.initWebcam();
    }
    const ctx = this.camCanvas.getContext("2d");
    this.camCanvas.width = 320;
    this.camCanvas.height = 240;
    ctx.drawImage(this.camVideo, 0, 0, 320, 240);
    const dataUrl = this.camCanvas.toDataURL("image/jpeg", 0.85);
    const base64Bytes = dataUrl.split(",")[1];

    const res = await this.postJSON("/api/v1/simulate/face", { image_base64: base64Bytes });
    this.showToast(res.message, res.success ? "success" : "error");
    this.fetchStatus();
  }

  async recordMicAndSubmit() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return this.showToast("WebRTC audio recording not supported.", "warning");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks = [];

      this.showToast("Recording 2s audio challenge phrase... Speak now!", "info");

      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: "audio/webm" });
        const reader = new FileReader();
        reader.onloadend = async () => {
          const base64data = reader.result.split(",")[1];
          const phrase = this.voicePhraseInput.value || "OPEN SESAME OVERENGINEERED";
          // Submit to backend
          const res = await this.postJSON("/api/v1/simulate/voice", {
            spoken_phrase: phrase,
            speaker_seed: 1, // Fallback profile
          });
          this.showToast(res.message, res.success ? "success" : "error");
          this.fetchStatus();
        };
        reader.readAsDataURL(blob);
      };

      recorder.start();
      setTimeout(() => recorder.stop(), 2000);
    } catch (ex) {
      this.showToast(`Microphone error: ${ex.message}. Use Mock voice buttons.`, "warning");
    }
  }

  // =========================================================================
  // UI Rendering & HUD Updaters
  // =========================================================================

  updateHUD(status) {
    if (!status) return;

    // 1. OLED Display
    if (status.display) {
      this.oledLine1El.textContent = status.display.line1 || "---";
      this.oledLine2El.textContent = status.display.line2 || "";

      const color = (status.display.led_color || "BLUE").toLowerCase();
      this.ledLampEl.className = `indicator-lamp lamp-${color}`;
      this.ledColorLabelEl.textContent = color.toUpperCase();
    }

    // 2. FSM State & Operator
    this.stateLabelEl.textContent = status.state;
    this.operatorLabelEl.textContent = status.active_username || (status.active_user_id ? `ID #${status.active_user_id}` : "UNIDENTIFIED");
    this.attemptsLabelEl.textContent = `${status.failed_attempts} / ${status.max_failed_attempts}`;

    // 3. Lock Solenoid Visualizer
    if (status.is_locked) {
      this.lockGraphicEl.className = "lock-solenoid-graphic";
      this.lockStatusLabelEl.textContent = status.state === "LOCKOUT" ? "SECURITY LOCKOUT" : "LOCKED";
    } else {
      this.lockGraphicEl.className = "lock-solenoid-graphic unlocked";
      this.lockStatusLabelEl.textContent = "UNLOCKED";
    }

    // 4. Stepper Pipeline Highlighting
    const stateOrder = [
      "IDLE",
      "AWAITING_RFID",
      "AWAITING_FINGERPRINT",
      "AWAITING_FACE",
      "AWAITING_PASSWORD",
      "AWAITING_VOICE",
      "UNLOCKED",
    ];

    const currentIdx = stateOrder.indexOf(status.state);

    Object.keys(this.stepNodes).forEach((stateKey) => {
      const node = this.stepNodes[stateKey];
      if (!node) return;
      const nodeIdx = stateOrder.indexOf(stateKey);

      node.classList.remove("active", "completed", "unlocked");

      if (status.state === "UNLOCKED") {
        if (stateKey === "UNLOCKED") node.classList.add("unlocked");
        else node.classList.add("completed");
      } else if (nodeIdx < currentIdx) {
        node.classList.add("completed");
      } else if (nodeIdx === currentIdx) {
        node.classList.add("active");
      }
    });
  }

  updateAuditTable(auditData) {
    if (!auditData) return;

    // Update Integrity Badge
    if (auditData.is_chain_valid) {
      this.integrityPill.className = "integrity-pill";
      this.integrityStatusText.textContent = "CHAIN VALID (SHA-256)";
    } else {
      this.integrityPill.className = "integrity-pill corrupted";
      this.integrityStatusText.textContent = "TAMPER DETECTED";
    }

    // Populate table
    this.auditTableBody.innerHTML = "";
    (auditData.logs || []).forEach((log) => {
      const tr = document.createElement("tr");
      const tsFormatted = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "---";
      const shortHash = log.entry_hash ? `${log.entry_hash.substring(0, 10)}...` : "---";
      const shortPrev = log.previous_hash ? `${log.previous_hash.substring(0, 10)}...` : "---";

      tr.innerHTML = `
        <td>#${log.id}</td>
        <td>${tsFormatted}</td>
        <td><span class="stage-badge">${log.stage}</span></td>
        <td><strong>${log.event_type}</strong></td>
        <td>${log.user_id ? `ID #${log.user_id}` : "---"}</td>
        <td><span class="hash-badge" title="${log.entry_hash}">${shortHash}</span></td>
        <td><span class="hash-badge" title="${log.previous_hash}">${shortPrev}</span></td>
      `;
      this.auditTableBody.appendChild(tr);
    });
  }

  showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    this.toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }
}

// Instantiate on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  window.vaultClient = new VaultClient();
});
