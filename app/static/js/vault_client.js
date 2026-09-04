/**
 * VAULT-404 — Operator Terminal Controller
 * Ground-up rebuild: Matrix rain BG · WebSocket telemetry · Auth animation
 */

/* ══════════════════════════════════════════════════════════════
   MATRIX RAIN BACKGROUND
   Uses a 2D canvas that always fills the full viewport.
   Characters fall at variable speed with 3-tier green brightness.
   ══════════════════════════════════════════════════════════════ */

function startMatrixRain() {
  const cv  = document.getElementById('bg');
  const ctx = cv.getContext('2d');

  const fit = () => {
    cv.width  = window.innerWidth;
    cv.height = window.innerHeight;
    ctx.fillStyle = '#05000f';
    ctx.fillRect(0, 0, cv.width, cv.height);
  };
  fit();
  window.addEventListener('resize', fit);

  const SYM = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF<>[]{}#|!';
  const FS  = 13;

  let cols  = Math.floor(cv.width / FS);
  let drops = Array.from({ length: cols }, () => -Math.random() * 60);

  (function tick() {
    requestAnimationFrame(tick);

    const nc = Math.floor(cv.width / FS);
    if (nc !== cols) {
      cols  = nc;
      drops = Array.from({ length: cols }, () => -Math.random() * 60);
    }

    // slow trail fade → long glowing streaks
    ctx.fillStyle = 'rgba(5,0,15,0.052)';
    ctx.fillRect(0, 0, cv.width, cv.height);

    ctx.font = `${FS}px "Share Tech Mono", monospace`;

    for (let i = 0; i < cols; i++) {
      const y = drops[i] * FS;
      if (y < 0) { drops[i] += 0.55; continue; }

      const ch = SYM[Math.floor(Math.random() * SYM.length)];
      const r  = Math.random();

      if (r > 0.97) {
        // bright tip — white-violet flash
        ctx.fillStyle   = '#e8d5ff';
        ctx.globalAlpha = 0.95;
      } else if (r > 0.5) {
        // main violet
        ctx.fillStyle   = '#a855f7';
        ctx.globalAlpha = 0.38 + Math.random() * 0.35;
      } else {
        // deep shadow violet
        ctx.fillStyle   = '#3b0764';
        ctx.globalAlpha = 0.22 + Math.random() * 0.20;
      }

      ctx.fillText(ch, i * FS, y);
      ctx.globalAlpha = 1;

      if (y > cv.height && Math.random() > 0.974) {
        drops[i] = -Math.random() * 20;
      }
      drops[i] += 0.55;
    }
  })();
}

/* ══════════════════════════════════════════════════════════════
   LIVE CLOCK
   ══════════════════════════════════════════════════════════════ */

function startClock() {
  const el = document.getElementById('clock');
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString('en-GB', { hour12: false });
  };
  tick();
  setInterval(tick, 1000);
}

/* ══════════════════════════════════════════════════════════════
   VAULT CLIENT
   ══════════════════════════════════════════════════════════════ */

class VaultClient {
  constructor() {
    this.ws           = null;
    this.retries      = 0;
    this.mediaStream  = null;
    this._busy        = {};          // per-action busy guard
    this._currentState = 'IDLE';    // last known FSM state (updated on every HUD render)
    this._rfidLockout  = false;     // debounce: ignore duplicate RFID scans for 4s after first

    this._el = id => document.getElementById(id);
    this._bind();
    this._wsConnect();
    this._fetch('/api/v1/vault/status').then(d => d && this._renderHUD(d));
    this._fetchLogs();
  }

  /* ── event bindings ── */
  _bind() {
    const on = (id, fn) => this._el(id)?.addEventListener('click', fn);

    on('btnStart',     () => this._post('/api/v1/vault/start', {}).then(r => { this._toast(r.message, r.success?'s':'e'); this._fetchAll(); }));
    on('btnReset',     () => this._post('/api/v1/vault/reset', {}).then(r => { this._toast(r.message, r.success?'s':'e'); this._fetchAll(); }));
    on('btnTamper',    () => this._post('/api/v1/simulate/tamper', { reason: 'Operator tamper test' }).then(r => { this._toast('⚠ TAMPER TRIGGERED', 'e'); this._fetchAll(); }));
    on('btnAdmin',     () => { const k = prompt('Admin override key:', 'ADMIN_RESET_9999'); if (k) this._post('/api/v1/vault/reset', { admin_override_key: k }).then(r => { this._toast(r.message, r.success?'s':'e'); this._fetchAll(); }); });
    on('btnRefresh',   () => this._fetchLogs());

    on('btnRfidAuth',    () => {
      const inputVal = this._el('rfidIn')?.value?.trim() || '';
      // Use scanned UID if present, otherwise default to enrolled operator UID 39D74320
      const uid = inputVal || '39D74320';
      this._post('/api/v1/simulate/rfid', { card_uid: uid }).then(r => {
        if (!r.success) this._showFailAnimation();
        this._toast(r.message, r.success ? 's' : 'e');
        this._fetchAll();
      });
    });
    on('btnRfidBad',     () => {
      this._post('/api/v1/simulate/rfid', { card_uid: 'INVALID_TAG_DENIED' }).then(r => {
        this._showFailAnimation();
        this._toast(r.message, 'e');
        this._fetchAll();
      });
    });
    on('btnRfidCustom',  () => {
      const inputVal = this._el('rfidIn')?.value?.trim() || '';
      if (!inputVal) {
        this._toast('Please enter a custom UID to submit', 'w');
        return;
      }
      this._rfid(inputVal);
    });

    on('btnCamStart',  () => this._camStart());
    on('btnCamCap',    () => this._camCapture());
    on('btnFaceAuth',  () => this._face(777));
    on('btnFaceBad',   () => this._face(999));

    on('btnPinAuth',   () => {
      const val = this._el('pinIn').value;
      if (!val) {
        this._toast('Please enter your configured password in the input box', 'w');
        return;
      }
      this._pin(val);
    });
    on('btnPinBad',    () => { this._pin('__INVALID_TEST_PASSWORD__'); });
    on('btnPinSubmit', () => this._pin(this._el('pinIn').value));
    on('togglePinMask', () => {
      const pinEl = this._el('pinIn');
      const btn = this._el('togglePinMask');
      if (pinEl && btn) {
        if (pinEl.type === 'password') {
          pinEl.type = 'text';
          btn.textContent = '👁 HIDE';
        } else {
          pinEl.type = 'password';
          btn.textContent = '👁 SHOW';
        }
      }
    });

    on('btnMic',       () => this._micRecord());
    on('btnVoiceAuth', () => this._voice(1));
    on('btnVoiceBad',  () => this._voice(2));
  }

  /* ── auth actions ── */
  _rfid(uid, autoSubmit = false)  {
    if (!uid) return;
    const cleanUid = uid.replace(/[\s\:\-\_]/g, '').toUpperCase();
    // Store actual UID in input
    const rfidIn = this._el('rfidIn');
    if (rfidIn) rfidIn.value = cleanUid || uid;
    // Show clear UID badge on screen
    const rfidBadge = this._el('rfidLiveVal');
    const rfidCard  = this._el('rfidLiveBadge');
    if (rfidBadge) {
      rfidBadge.textContent = `${cleanUid} (SCANNED)`;
      rfidBadge.style.color = '#00ff9d';
      rfidBadge.style.fontWeight = 'bold';
    }
    if (rfidCard) {
      rfidCard.classList.remove('pulse-highlight');
      void rfidCard.offsetWidth;
      rfidCard.classList.add('pulse-highlight');
    }
    // Hardware scan: only auto-submit if the FSM is expecting RFID and no recent duplicate
    if (autoSubmit) {
      const stateOk = this._currentState === 'IDLE' || this._currentState === 'AWAITING_RFID';
      if (!stateOk || this._rfidLockout) return; // drop duplicate / out-of-order scan silently
      // Set debounce lock for 4 seconds to absorb repeated MFRC522 reads of same card
      this._rfidLockout = true;
      setTimeout(() => { this._rfidLockout = false; }, 4000);

      this._post('/api/v1/simulate/rfid', { card_uid: cleanUid || uid }).then(r => {
        // Only show fail animation when genuinely denied (state stayed AWAITING_RFID)
        const responseState = r?.data?.state;
        const genuineDenial = !r.success && (responseState === 'AWAITING_RFID' || responseState === 'IDLE');
        if (genuineDenial) {
          this._rfidLockout = false; // allow retry after denial
          this._showFailAnimation();
        }
        this._toast(r.message, r.success ? 's' : 'e');
        this._fetchAll();
      });
    }
  }
  _face(seed) {
    this._post('/api/v1/simulate/face', { subject_seed: seed, noise_level: 0.01 }).then(r => {
      if (!r.success) this._showFailAnimation();
      this._toast(r.message, r.success?'s':'e');
      this._fetchAll();
    });
  }
  _pin(val)   {
    if (!val) return;
    const cleanVal = String(val).trim();
    if (!cleanVal) return;
    this._post('/api/v1/auth/password', { pin: cleanVal }).then(r => {
      if (!r.success) this._showFailAnimation();
      this._toast(r.message, r.success ? 's' : 'e');
      this._fetchAll();
    });
  }
  _voice(seed){
    this._post('/api/v1/simulate/voice', { speaker_seed: seed, spoken_phrase: this._el('phraseIn')?.value || 'OPEN SESAME OVERENGINEERED', noise_level: 0.01 }).then(r => {
      if (!r.success) this._showFailAnimation();
      this._toast(r.message, r.success?'s':'e');
      this._fetchAll();
    });
  }

  /* ── camera ── */
  async _camStart() {
    try {
      if (!navigator.mediaDevices?.getUserMedia) return this._toast('WebRTC not available', 'w');
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width:320, height:240 } });
      const v = this._el('camVid');
      v.srcObject = this.mediaStream;
      v.style.display = 'block';
      this._toast('Camera active', 's');
    } catch(e) { this._toast('Camera error — use mock buttons', 'w'); }
  }

  async _camCapture() {
    if (this._busy.face) return;          // prevent double-fire
    this._busy.face = true;
    try {
      if (!this._el('camVid').srcObject) await this._camStart();
      const cv = this._el('camCvs');
      cv.width = 320; cv.height = 240;
      cv.getContext('2d').drawImage(this._el('camVid'), 0, 0, 320, 240);
      const b64 = cv.toDataURL('image/jpeg', 0.82).split(',')[1];
      const r = await this._post('/api/v1/simulate/face', { image_base64: b64 });
      if (!r.success) this._showFailAnimation();
      this._toast(r.message, r.success ? 's' : 'e');
      this._fetchAll();
    } finally {
      setTimeout(() => { this._busy.face = false; }, 2000);
    }
  }

  async _micRecord() {
    if (this._busy.voice) return;         // prevent double-fire
    this._busy.voice = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec    = new MediaRecorder(stream);
      const chunks = [];
      this._toastReplace('Recording 2s… speak now!', 'i', 'mic-status');
      rec.ondataavailable = e => chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = async () => {
          const b64 = reader.result.split(',')[1];
          const r = await this._post('/api/v1/simulate/voice', {
            audio_base64:  b64,
            speaker_seed:  1,
            spoken_phrase: this._el('phraseIn')?.value || 'OPEN SESAME OVERENGINEERED',
            noise_level:   0.01
          });
          if (!r.success) this._showFailAnimation();
          this._toastReplace(r.message, r.success ? 's' : 'e', 'mic-status');
          this._fetchAll();
          setTimeout(() => { this._busy.voice = false; }, 1500);
        };
      };
      rec.start();
      setTimeout(() => rec.stop(), 2000);
    } catch(e) {
      this._toast('Mic unavailable — use mock voice', 'w');
      this._busy.voice = false;
    }
  }

  /* ══════════════════════════════════════════════════════════════
     AUTO-MOCK HELPERS
     Stage 2 — CV (face biometrics): uses operator face_id
     Stage 4 — Acoustic (voice):     uses operator passphrase
     ══════════════════════════════════════════════════════════════ */
  async _autoMockFace() {
    if (this._currentState !== 'AWAITING_FACE') return; // guard: state may have changed
    if (this._busy.autoFace) return;
    this._busy.autoFace = true;
    try {
      const r = await this._post('/api/v1/simulate/face', {
        face_id: 'SUBJECT_001_OPERATOR',  // known-good operator identity
        noise_level: 0.0
      });
      if (!r.success) this._showFailAnimation();
      this._toast(r.success ? '[ CV ] Face matched ✓' : '[ CV ] Face rejected ✗', r.success ? 's' : 'e');
      this._fetchAll();
    } finally {
      setTimeout(() => { this._busy.autoFace = false; }, 3000);
    }
  }

  async _autoMockVoice() {
    if (this._currentState !== 'AWAITING_VOICE') return; // guard
    if (this._busy.autoVoice) return;
    this._busy.autoVoice = true;
    try {
      const r = await this._post('/api/v1/simulate/voice', {
        spoken_phrase: 'OPEN SESAME OVERENGINEERED',  // enrolled passphrase
        noise_level: 0.0
      });
      if (!r.success) this._showFailAnimation();
      this._toast(r.success ? '[ ACOUSTIC ] Voice verified ✓' : '[ ACOUSTIC ] Voice rejected ✗', r.success ? 's' : 'e');
      this._fetchAll();
    } finally {
      setTimeout(() => { this._busy.autoVoice = false; }, 3000);
    }
  }

  /* ── WebSocket ── */
  _wsConnect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.ws = new WebSocket(`${proto}//${location.host}/ws/vault`);

    this.ws.onopen = () => {
      this.retries = 0;
      const b = this._el('wsStatus');
      b.className = 'ws-badge ws-on';
      this._el('wsText').textContent = 'TELEMETRY LIVE';
      this._toast('WebSocket connected', 's');
    };

    this.ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        /* ── State transition handling ── */
        if (msg.event === 'STATE_CHANGE' || msg.event === 'INITIAL_STATE') {
          const newState = msg.data?.current_state;
          const reason   = (msg.data?.reason || '').toLowerCase();

          if (newState === 'UNLOCKED') {
            this._showAuthAnimation();

          } else if (newState === 'AWAITING_FACE') {
            // ── Stage 2: auto mock CV / face biometrics ──
            this._toast('[ STAGE 2 ] Running CV face match...', 'i');
            setTimeout(() => this._autoMockFace(), 800);

          } else if (newState === 'AWAITING_KEYPAD_PIN') {
            // ── Stage 3: keypad — wait for hardware PIN entry ──
            this._toast('[ STAGE 3 ] Enter PIN on keypad then press #', 'i');

          } else if (newState === 'AWAITING_VOICE') {
            // ── Stage 4: auto mock acoustic / voice ──
            this._toast('[ STAGE 4 ] Running acoustic voice match...', 'i');
            setTimeout(() => this._autoMockVoice(), 800);

          } else if (newState === 'IDLE' && (reason.includes('denied') || reason.includes('chain stopped') || reason.includes('failed') || reason.includes('timeout'))) {
            this._showFailAnimation();
          }

          this._fetchAll();
        } else if (msg.event === 'HARDWARE_EVENT') {
          const hw = msg.data;
          if (hw) {
            const evType = hw.event_type;
            const payload = hw.payload || {};

            // 1. RFID Card Scan
            // The engine listener on the backend ALREADY calls submit_rfid() directly from
            // the hardware event. JS must NOT make a second HTTP call — just update the badge
            // and wait for the STATE_CHANGE broadcast.
            if (evType === 'RFID_SCANNED' || payload.card_uid) {
              const uid = payload.card_uid || payload.uid;
              if (uid) {
                // Update badge (masked) only — NO auto-submit
                this._rfid(uid, false);
                this._toast('[ RFID ] Tag detected — verifying...', 'i');
              }
            }

            // 2. Keypad Key Pressed / Cleared
            if (evType === 'KEYPAD_STATUS') {
              const pIn = this._el('pinIn');
              const pBadge = this._el('pinLiveVal');
              if (payload.status === 'CLEARED') {
                if (pIn) pIn.value = '';
                if (pBadge) pBadge.textContent = 'EMPTY';
                this._toast('Keypad cleared (*)', 'i');
              } else if (payload.key !== undefined) {
                const key = String(payload.key);
                if (pIn) {
                  if (payload.length === 1) {
                    pIn.value = key;
                  } else {
                    pIn.value = (pIn.value || '') + key;
                  }
                }
                // Show masked dots instead of actual chars in badge
                if (pBadge && pIn) pBadge.textContent = '●'.repeat(pIn.value.length);
              }
            }

            // 3. Keypad Pin Submitted (#)
            // Engine listener ALREADY calls submit_keypad_pin() from KEYPAD_PIN_RESULT.
            // JS only updates the badge — no second HTTP post.
            if (evType === 'KEYPAD_PIN_RESULT' || payload.pin !== undefined) {
              const pin = payload.pin;
              const pIn = this._el('pinIn');
              const pBadge = this._el('pinLiveVal');
              if (pin) {
                if (pIn) pIn.value = pin;
                if (pBadge) pBadge.textContent = '●'.repeat(pin.length) + ' (SUBMITTED)';
                this._toast('[ PIN ] Submitted — verifying...', 'i');
              }
            }
          }
          this._fetchAll();
        }
      } catch {}
    };

    this.ws.onclose = () => {
      const b = this._el('wsStatus');
      b.className = 'ws-badge ws-off';
      this._el('wsText').textContent = 'DISCONNECTED';
      const delay = Math.min(12000, 1000 * Math.pow(1.5, this.retries++));
      setTimeout(() => this._wsConnect(), delay);
    };

    this.ws.onerror = () => this.ws.close();
  }

  /* ── HTTP helpers ── */
  async _fetch(url) {
    try { const r = await fetch(url); return r.ok ? r.json() : null; }
    catch { return null; }
  }

  async _post(url, body) {
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return await r.json();
    } catch(e) { return { success: false, message: `Error: ${e.message}` }; }
  }

  _fetchAll() {
    this._fetch('/api/v1/vault/status').then(d => d && this._renderHUD(d));
    this._fetchLogs();
  }

  async _fetchLogs() {
    const d = await this._fetch('/api/v1/audit/logs?limit=8');
    if (d) this._renderLogs(d);
  }

  /* ── HUD renderer ── */
  _renderHUD(s) {
    if (!s) return;
    // Track current FSM state so hardware events can gate correctly
    this._currentState = s.state || 'IDLE';

    // OLED
    if (s.display) {
      this._el('oLn1').textContent = s.display.line1 || '---';
      this._el('oLn2').textContent = s.display.line2 || '';
      const col = (s.display.led_color || 'blue').toLowerCase();
      const bulb = this._el('ledBulb');
      bulb.className = `led-bulb ${col}`;
      this._el('ledLbl').textContent = col.toUpperCase();
    }

    this._el('stateLbl').textContent = s.state || '---';
    this._el('opLbl').textContent    = s.active_username || (s.active_user_id ? `ID#${s.active_user_id}` : 'UNIDENTIFIED');
    this._el('atkLbl').textContent   = `${s.failed_attempts} / ${s.max_failed_attempts}`;

    const icon = this._el('lockIcon');
    const lbl  = this._el('lockLbl');
    if (!s.is_locked) {
      icon.className   = 'lock-icon unlocked';
      lbl.textContent  = 'UNLOCKED';
    } else {
      icon.className   = 'lock-icon locked';
      lbl.textContent  = s.state === 'LOCKOUT' ? 'SECURITY LOCKOUT' : 'LOCKED';
    }

    // Stepper
    const ORDER = ['IDLE','AWAITING_RFID','AWAITING_FACE','AWAITING_KEYPAD_PIN','AWAITING_VOICE','UNLOCKED'];
    const MAP   = { IDLE:'sIdle', AWAITING_RFID:'sRfid', AWAITING_FACE:'sFace', AWAITING_KEYPAD_PIN:'sPin', AWAITING_VOICE:'sVoice', UNLOCKED:'sUnlock' };
    const cur   = ORDER.indexOf(s.state);

    ORDER.forEach((key, i) => {
      const el = this._el(MAP[key]);
      if (!el) return;
      el.classList.remove('active','done','unlocked');
      if (s.state === 'UNLOCKED') {
        el.classList.add(key === 'UNLOCKED' ? 'unlocked' : 'done');
      } else if (i < cur) {
        el.classList.add('done');
      } else if (i === cur) {
        el.classList.add('active');
      }
    });
  }

  /* ── Audit log renderer ── */
  _renderLogs(d) {
    const pill = this._el('chainPill');
    const txt  = this._el('chainTxt');
    if (d.is_chain_valid) {
      pill.className = 'chain-pill valid';
      txt.textContent = 'CHAIN VALID (SHA-256)';
    } else {
      pill.className = 'chain-pill bad';
      txt.textContent = 'TAMPER DETECTED!';
    }

    const tbody = this._el('atbody');
    tbody.innerHTML = '';
    (d.logs || []).forEach(log => {
      const ts = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '---';
      const sh = log.entry_hash    ? log.entry_hash.slice(0,10)+'…'    : '---';
      const sp = log.previous_hash ? log.previous_hash.slice(0,10)+'…' : '---';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>#${log.id}</td>
        <td>${ts}</td>
        <td><span class="sbadge">${log.stage}</span></td>
        <td><strong>${log.event_type}</strong></td>
        <td>${log.user_id ? 'ID#'+log.user_id : '---'}</td>
        <td><span class="hbadge" title="${log.entry_hash}">${sh}</span></td>
        <td><span class="hbadge" title="${log.previous_hash}">${sp}</span></td>`;
      tbody.appendChild(tr);
    });
  }

  /* ── Toast ── */
  /* ── toast: max 3 visible, auto-dismiss after 3.5s ── */
  _toast(msg, type = 'i') {
    const container = this._el('toasts');
    // evict oldest if already at limit
    while (container.children.length >= 3) container.firstChild.remove();
    const el = document.createElement('div');
    el.className   = `toast ${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => {
      el.style.opacity    = '0';
      el.style.transition = 'opacity .4s';
      setTimeout(() => el.remove(), 400);
    }, 3500);
  }

  /* replace a specific keyed toast (avoids stacking same message) */
  _toastReplace(msg, type, key) {
    const container = this._el('toasts');
    const existing  = container.querySelector(`[data-key="${key}"]`);
    if (existing) existing.remove();
    const el = document.createElement('div');
    el.className      = `toast ${type}`;
    el.textContent    = msg;
    el.dataset.key    = key;
    container.appendChild(el);
    setTimeout(() => {
      el.style.opacity    = '0';
      el.style.transition = 'opacity .4s';
      setTimeout(() => el.remove(), 400);
    }, 3500);
  }

  /* ══════════════════════════════════════════════════════════════
     AUTHENTICATED OVERLAY
     Ported from Privix BreachReveal — green/cyan theme.
     Fixed: reads msg.data.current_state (not msg.state)
     ══════════════════════════════════════════════════════════════ */
  _showAuthAnimation() {
    if (document.getElementById('authOv')) return;   // debounce

    const ov = document.createElement('div');
    ov.id        = 'authOv';
    ov.className = 'auth-ov';

    ov.innerHTML = `
      <div class="ov-scan"></div>
      <div class="ov-vign"></div>
      <div class="ov-grid"></div>

      <!-- Phase 1 — spinner -->
      <div class="ov-phase-scan" id="ovPScan">
        <div class="ov-spinner"></div>
        <div class="ov-scan-txt">VERIFYING CREDENTIALS...</div>
        <div class="ov-bar"><div class="ov-bar-fill"></div></div>
      </div>

      <!-- Phase 2 — AUTHENTICATED headline -->
      <div class="ov-phase-alert" id="ovPAlert">
        <div class="ov-icon">✓</div>
        <h1 class="ov-headline" data-text="AUTHENTICATED">AUTHENTICATED</h1>
        <div class="ov-sub">ACCESS GRANTED — ALL 4 STAGES CLEARED</div>
      </div>

      <!-- Phase 3 — stage checklist -->
      <div class="ov-phase-stats" id="ovPStats">
        <div class="ov-stat" id="ovS0"><span class="ov-stat-lbl">[ STAGE 1 ] RFID SCAN</span><span class="ov-stat-val">✓ CLEARED</span></div>
        <div class="ov-stat" id="ovS1"><span class="ov-stat-lbl">[ STAGE 2 ] FACE BIOMETRICS</span><span class="ov-stat-val">✓ MATCHED</span></div>
        <div class="ov-stat" id="ovS2"><span class="ov-stat-lbl">[ STAGE 3 ] SECRET KEY</span><span class="ov-stat-val">✓ ACCEPTED</span></div>
        <div class="ov-stat" id="ovS3"><span class="ov-stat-lbl">[ STAGE 4 ] VOICE PHRASE</span><span class="ov-stat-val">✓ VERIFIED</span></div>
      </div>

      <div class="ov-hint">— CLICK ANYWHERE TO DISMISS —</div>
    `;

    ov.addEventListener('click', () => {
      ov.classList.add('out');
      setTimeout(() => ov.remove(), 900);
    });

    document.body.appendChild(ov);

    // ── Phase timeline ──
    const show = (id, asBlock = false) => {
      const el = document.getElementById(id);
      if (el) el.style.display = asBlock ? 'flex' : 'flex';
    };
    const hide = (id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    };

    // t=1.3s → switch to AUTHENTICATED
    setTimeout(() => {
      hide('ovPScan');
      show('ovPAlert');
    }, 1300);

    // t=3.0s → show checklist rows
    setTimeout(() => {
      show('ovPStats');
      ['ovS0','ovS1','ovS2','ovS3'].forEach((id, i) => {
        setTimeout(() => {
          const el = document.getElementById(id);
          if (el) { el.style.opacity = '1'; el.style.transform = 'translateY(0)'; }
        }, i * 220);
      });
    }, 3000);

    // t=6.2s → auto dismiss
    setTimeout(() => {
      ov.classList.add('out');
      setTimeout(() => { if (ov.parentNode) ov.remove(); }, 900);
    }, 6200);
  }

  /* ══════════════════════════════════════════════════════════════
     AUTHENTICATION FAILED OVERLAY
     Red-themed mirror of _showAuthAnimation
     ══════════════════════════════════════════════════════════════ */
  _showFailAnimation() {
    if (document.getElementById('failOv')) return;   // debounce

    const ov = document.createElement('div');
    ov.id        = 'failOv';
    ov.className = 'fail-ov';

    ov.innerHTML = `
      <div class="fov-scan"></div>
      <div class="fov-vign"></div>
      <div class="fov-grid"></div>

      <!-- Phase 1 — spinner -->
      <div class="fov-phase-scan" id="fovPScan">
        <div class="fov-spinner"></div>
        <div class="fov-scan-txt">VERIFYING CREDENTIALS...</div>
        <div class="fov-bar"><div class="fov-bar-fill"></div></div>
      </div>

      <!-- Phase 2 — FAILED headline -->
      <div class="fov-phase-alert" id="fovPAlert">
        <div class="fov-icon">✗</div>
        <h1 class="fov-headline" data-text="ACCESS DENIED">ACCESS DENIED</h1>
        <div class="fov-sub">AUTHENTICATION FAILED — CHAIN TERMINATED</div>
      </div>

      <!-- Phase 3 — failure info -->
      <div class="fov-phase-stats" id="fovPStats">
        <div class="fov-stat" id="fovS0"><span class="fov-stat-lbl">[ CHAIN RESET ]</span><span class="fov-stat-val">⚠ STAGE DENIED</span></div>
        <div class="fov-stat" id="fovS1"><span class="fov-stat-lbl">[ STATUS ]</span><span class="fov-stat-val">VAULT LOCKED</span></div>
        <div class="fov-stat" id="fovS2"><span class="fov-stat-lbl">[ ACTION ]</span><span class="fov-stat-val">RESTART REQUIRED</span></div>
      </div>

      <div class="fov-hint">— CLICK ANYWHERE TO DISMISS —</div>
    `;

    ov.addEventListener('click', () => {
      ov.classList.add('out');
      setTimeout(() => ov.remove(), 900);
    });

    document.body.appendChild(ov);

    const show = (id) => { const el = document.getElementById(id); if (el) el.style.display = 'flex'; };
    const hide = (id) => { const el = document.getElementById(id); if (el) el.style.display = 'none'; };

    // t=1.1s → switch to ACCESS DENIED
    setTimeout(() => { hide('fovPScan'); show('fovPAlert'); }, 1100);

    // t=2.5s → show failure rows
    setTimeout(() => {
      show('fovPStats');
      ['fovS0','fovS1','fovS2'].forEach((id, i) => {
        setTimeout(() => {
          const el = document.getElementById(id);
          if (el) { el.style.opacity = '1'; el.style.transform = 'translateY(0)'; }
        }, i * 200);
      });
    }, 2500);

    // t=5.5s → auto dismiss
    setTimeout(() => {
      ov.classList.add('out');
      setTimeout(() => { if (ov.parentNode) ov.remove(); }, 900);
    }, 5500);
  }
}

/* ══════════════════════════════════════════════════════════════
   BOOTSTRAP
   ══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
  startMatrixRain();
  startClock();
  window.vc = new VaultClient();
});
