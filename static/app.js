(function () {
  "use strict";

  // ─────────────────────────────────────────────────────────
  //  DOM
  // ─────────────────────────────────────────────────────────
  const stage = document.getElementById("stage");
  const canvas = document.getElementById("orbCanvas");
  const ctx = canvas.getContext("2d");
  const stateLabel = document.getElementById("stateLabel");
  const wordmark = document.getElementById("wordmark");
  const userLine = document.getElementById("userLine");
  const responseLine = document.getElementById("responseLine");
  const startOverlay = document.getElementById("startOverlay");
  const menuBtn = document.getElementById("menuBtn");
  const settingsOverlay = document.getElementById("settingsOverlay");
  const settingsCancel = document.getElementById("settingsCancel");
  const settingsSave = document.getElementById("settingsSave");
  const apiKeyInput = document.getElementById("apiKeyInput");
  const nameInput = document.getElementById("nameInput");
  const promptInput = document.getElementById("promptInput");
  const textFallback = document.getElementById("textFallback");
  const textFallbackInput = document.getElementById("textFallbackInput");
  const textFallbackSend = document.getElementById("textFallbackSend");
  const micFallbackHint = document.getElementById("micFallbackHint");

  let assistantName = stage.dataset.name || "JARVIS";
  let uiLang = (navigator.language || "ko-KR").toLowerCase().startsWith("en") ? "en" : "ko";

  // ─────────────────────────────────────────────────────────
  //  파티클 오브(Orb) 렌더러 — Iron Man식 글로우 파티클 스피어
  // ─────────────────────────────────────────────────────────
  const Orb = (function () {
    let W = 0, H = 0, DPR = 1;
    const isSmall = () => window.innerWidth < 700;

    let N = isSmall() ? 360 : 720;
    const K = isSmall() ? 2 : 3;

    let points = [];   // {x,y,z, phase}
    let edges = [];    // [i, j]

    function fibonacciSphere(n) {
      const pts = [];
      const golden = Math.PI * (3 - Math.sqrt(5));
      for (let i = 0; i < n; i++) {
        const y = 1 - (i / (n - 1)) * 2;
        const radius = Math.sqrt(1 - y * y);
        const theta = golden * i;
        const x = Math.cos(theta) * radius;
        const z = Math.sin(theta) * radius;
        pts.push({ x, y, z, phase: Math.random() * Math.PI * 2 });
      }
      return pts;
    }

    function buildEdges(pts, k) {
      // 각 점마다 각도상 가장 가까운 k개를 연결 (구 회전에도 이웃관계 불변)
      const es = [];
      const seen = new Set();
      for (let i = 0; i < pts.length; i++) {
        const dists = [];
        for (let j = 0; j < pts.length; j++) {
          if (i === j) continue;
          const d = pts[i].x * pts[j].x + pts[i].y * pts[j].y + pts[i].z * pts[j].z; // dot (클수록 가까움)
          dists.push([d, j]);
        }
        dists.sort((a, b) => b[0] - a[0]);
        for (let n = 0; n < k; n++) {
          const j = dists[n][1];
          const key = i < j ? i + "_" + j : j + "_" + i;
          if (!seen.has(key)) {
            seen.add(key);
            es.push([i, j]);
          }
        }
      }
      return es;
    }

    points = fibonacciSphere(N);
    edges = buildEdges(points, K);

    function resize() {
      DPR = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth;
      H = window.innerHeight;
      canvas.style.width = W + "px";
      canvas.style.height = H + "px";
      canvas.width = W * DPR;
      canvas.height = H * DPR;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    window.addEventListener("resize", resize);
    resize();

    // 상태별 파라미터
    const STATES = {
      idle:      { radius: 1.00, noise: 0.045, rot: 0.16, jitter: 1.0, pulse: 0.02, pulseFreq: 0.6, color: [180, 220, 255], core: 0.55 },
      listening: { radius: 1.16, noise: 0.13,  rot: 0.38, jitter: 2.3, pulse: 0.07, pulseFreq: 1.5, color: [200, 235, 255], core: 0.95 },
      thinking:  { radius: 0.86, noise: 0.06,  rot: 1.05, jitter: 1.4, pulse: 0.03, pulseFreq: 0.9, color: [175, 190, 255], core: 0.65 },
      speaking:  { radius: 1.08, noise: 0.19,  rot: 0.26, jitter: 3.6, pulse: 0.09, pulseFreq: 2.1, color: [210, 240, 255], core: 1.0 },
      error:     { radius: 0.9,  noise: 0.03,  rot: 0.1,  jitter: 0.8, pulse: 0.02, pulseFreq: 0.5, color: [255, 130, 130], core: 0.45 },
    };

    let current = { ...STATES.idle };
    let target = STATES.idle;
    let targetName = "idle";

    function setState(name) {
      if (!STATES[name]) return;
      target = STATES[name];
      targetName = name;
    }

    function lerp(a, b, t) { return a + (b - a) * t; }

    let angleY = 0;
    let t0 = performance.now();
    let speakEnvelope = 0.8;
    let speakEnvelopeTarget = 0.8;
    let lastEnvelopeChange = 0;

    function frame(now) {
      const dt = Math.min((now - t0) / 1000, 0.05);
      t0 = now;
      const t = now / 1000;

      // 상태 파라미터 부드럽게 보간
      const ease = 1 - Math.pow(0.001, dt);
      for (const k of ["radius", "noise", "rot", "jitter", "pulse", "pulseFreq", "core"]) {
        current[k] = lerp(current[k], target[k], ease);
      }
      current.color = current.color.map((c, i) => lerp(c, target.color[i], ease));

      // 말하는 중일 때 "목소리처럼" 흔들리는 랜덤 엔벌로프
      if (targetName === "speaking") {
        if (t - lastEnvelopeChange > 0.09) {
          speakEnvelopeTarget = 0.55 + Math.random() * 0.5;
          lastEnvelopeChange = t;
        }
        speakEnvelope = lerp(speakEnvelope, speakEnvelopeTarget, 0.25);
      } else {
        speakEnvelope = lerp(speakEnvelope, 1, 0.1);
      }

      angleY += current.rot * dt;
      const tiltX = Math.sin(t * 0.13) * 0.18;
      const pulseScale = 1 + Math.sin(t * current.pulseFreq * Math.PI * 2) * current.pulse * speakEnvelope;

      const cx = W / 2;
      const cy = H * 0.42;
      const scaleBase = Math.min(W, H) * 0.16;
      const focal = 3.2;

      ctx.clearRect(0, 0, W, H);

      const cosY = Math.cos(angleY), sinY = Math.sin(angleY);
      const cosX = Math.cos(tiltX), sinX = Math.sin(tiltX);

      const projected = new Array(points.length);

      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        const rJitter = 1 + Math.sin(t * current.jitter + p.phase) * current.noise;
        let x = p.x * current.radius * rJitter;
        let y = p.y * current.radius * rJitter;
        let z = p.z * current.radius * rJitter;

        // Y축 회전
        let x1 = x * cosY - z * sinY;
        let z1 = x * sinY + z * cosY;
        // X축 살짝 틸트
        let y1 = y * cosX - z1 * sinX;
        let z2 = y * sinX + z1 * cosX;

        x1 *= pulseScale; y1 *= pulseScale; z2 *= pulseScale;

        const depth = focal / (focal + z2);
        const sx = cx + x1 * scaleBase * depth;
        const sy = cy + y1 * scaleBase * depth;
        projected[i] = { sx, sy, depth, z: z2 };
      }

      const [r, g, b] = current.color;

      // 중심 글로우
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, scaleBase * 1.9);
      glow.addColorStop(0, `rgba(${r},${g},${b},${0.35 * current.core})`);
      glow.addColorStop(1, `rgba(${r},${g},${b},0)`);
      ctx.fillStyle = glow;
      ctx.fillRect(cx - scaleBase * 2, cy - scaleBase * 2, scaleBase * 4, scaleBase * 4);

      // 엣지(선)
      ctx.lineWidth = 0.6;
      for (const [i, j] of edges) {
        const a = projected[i], bpt = projected[j];
        const avgDepth = (a.depth + bpt.depth) / 2;
        const alpha = Math.max(0, Math.min(0.35, (avgDepth - 0.7) * 0.9));
        if (alpha <= 0.01) continue;
        ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(bpt.sx, bpt.sy);
        ctx.stroke();
      }

      // 점(파티클) — 깊이순 정렬 후 그리기
      const order = projected.map((_, i) => i).sort((a, b2) => projected[a].depth - projected[b2].depth);
      for (const i of order) {
        const pr = projected[i];
        const size = Math.max(0.4, 1.5 * pr.depth);
        const alpha = Math.max(0.15, Math.min(1, (pr.depth - 0.55) * 1.8));
        ctx.beginPath();
        ctx.fillStyle = `rgba(${Math.min(255,r+20)},${Math.min(255,g+20)},${Math.min(255,b+10)},${alpha})`;
        ctx.arc(pr.sx, pr.sy, size, 0, Math.PI * 2);
        ctx.fill();
      }

      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    return { setState };
  })();

  // ─────────────────────────────────────────────────────────
  //  상태 표시 / 텍스트
  // ─────────────────────────────────────────────────────────
  const STATE_TEXT = { listening: "LISTENING", thinking: "THINKING", speaking: "SPEAKING", error: "ERROR" };
  let wordmarkTimer = null;

  function setUiState(name) {
    Orb.setState(name);
    if (STATE_TEXT[name]) {
      stateLabel.textContent = STATE_TEXT[name];
      stateLabel.style.opacity = "1";
      wordmark.style.opacity = "0";
    } else {
      stateLabel.style.opacity = "0";
      wordmark.style.opacity = "1";
    }
  }

  function showResponse(userText, replyText) {
    userLine.textContent = userText ? `“${userText}”` : "";
    userLine.classList.toggle("show", !!userText);
    responseLine.textContent = replyText || "";
    responseLine.classList.toggle("show", !!replyText);

    clearTimeout(wordmarkTimer);
    wordmarkTimer = setTimeout(() => {
      userLine.classList.remove("show");
      responseLine.classList.remove("show");
    }, 14000);
  }

  // ─────────────────────────────────────────────────────────
  //  TTS
  // ─────────────────────────────────────────────────────────
  function speak(text, lang, onDone) {
    if (!("speechSynthesis" in window) || !text) {
      onDone && onDone();
      return;
    }
    try {
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = lang === "en" ? "en-US" : "ko-KR";
      utter.rate = 1.03;
      utter.onstart = () => setUiState("speaking");
      utter.onend = () => onDone && onDone();
      utter.onerror = () => onDone && onDone();
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utter);
    } catch (e) {
      onDone && onDone();
    }
  }

  // ─────────────────────────────────────────────────────────
  //  서버와 대화
  // ─────────────────────────────────────────────────────────
  let busy = false;

  async function sendText(text) {
    if (!text || !text.trim() || busy) return;
    busy = true;
    setUiState("thinking");
    showResponse(text, "");

    try {
      const resp = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, lang_hint: uiLang }),
      });
      const data = await resp.json();

      if (data.kind === "action" && data.action === "open_url" && data.url) {
        window.open(data.url, "_blank");
      }

      showResponse(text, data.text || "");

      speak(data.text, data.lang || uiLang, () => {
        busy = false;
        resumeListening();
      });
    } catch (e) {
      showResponse(text, "⚠️ 서버에 연결할 수 없어요.");
      setUiState("error");
      busy = false;
      setTimeout(resumeListening, 1500);
    }
  }

  // ─────────────────────────────────────────────────────────
  //  연속 음성 인식 루프 (핸즈프리)
  // ─────────────────────────────────────────────────────────
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognizer = null;
  let active = false;      // 전체 루프 on/off
  let recognizing = false; // 현재 recognizer.start() 상태

  function resumeListening() {
    if (!active || busy) return;
    setUiState("listening");
    startRecognizer();
  }

  function startRecognizer() {
    if (!recognizer || recognizing) return;
    try {
      recognizer.lang = uiLang === "en" ? "en-US" : "ko-KR";
      recognizer.start();
    } catch (e) {
      /* 이미 시작된 경우 무시 */
    }
  }

  if (SpeechRecognition) {
    recognizer = new SpeechRecognition();
    recognizer.continuous = false;
    recognizer.interimResults = false;

    recognizer.onstart = () => {
      recognizing = true;
    };
    recognizer.onend = () => {
      recognizing = false;
      // 계속 듣기 모드면 자동 재시작 (말하는 중/처리 중이 아닐 때만)
      if (active && !busy) {
        setTimeout(startRecognizer, 250);
      }
    };
    recognizer.onerror = (e) => {
      recognizing = false;
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setUiState("error");
        showResponse("", "🎤 마이크 권한을 허용해주세요.");
        active = false;
        return;
      }
      // no-speech, aborted 등은 조용히 재시도
      if (active && !busy) {
        setTimeout(startRecognizer, 400);
      }
    };
    recognizer.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      if (transcript && transcript.trim()) {
        sendText(transcript.trim());
      }
    };
  } else {
    micFallbackHint.textContent = "이 브라우저는 음성 인식을 지원하지 않아요. 아래에 입력해주세요. (Chrome 권장)";
    textFallback.classList.add("show");
  }

  function beginHandsFree() {
    active = true;
    if (SpeechRecognition) {
      resumeListening();
    } else {
      setUiState("idle");
    }
  }

  // ─────────────────────────────────────────────────────────
  //  시작 오버레이 (오디오 자동재생 정책 대응)
  // ─────────────────────────────────────────────────────────
  startOverlay.addEventListener("click", () => {
    startOverlay.classList.add("hidden");
    // 무음 발화로 오디오 컨텍스트 언락
    try {
      const warm = new SpeechSynthesisUtterance(" ");
      warm.volume = 0;
      window.speechSynthesis.speak(warm);
    } catch (e) {}
    beginHandsFree();
  }, { once: true });

  // ─────────────────────────────────────────────────────────
  //  텍스트 폴백 입력
  // ─────────────────────────────────────────────────────────
  function submitFallback() {
    const v = textFallbackInput.value.trim();
    if (!v) return;
    textFallbackInput.value = "";
    sendText(v);
  }
  textFallbackSend.addEventListener("click", submitFallback);
  textFallbackInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitFallback();
  });

  // ─────────────────────────────────────────────────────────
  //  설정 오버레이
  // ─────────────────────────────────────────────────────────
  menuBtn.addEventListener("click", () => settingsOverlay.classList.remove("hidden"));
  settingsCancel.addEventListener("click", () => settingsOverlay.classList.add("hidden"));

  settingsSave.addEventListener("click", async () => {
    const payload = {
      assistant_name: nameInput.value.trim() || "JARVIS",
      system_prompt: promptInput.value.trim(),
    };
    if (apiKeyInput.value.trim()) payload.api_key = apiKeyInput.value.trim();

    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    assistantName = payload.assistant_name;
    wordmark.textContent = assistantName;
    document.title = assistantName;
    document.querySelector("#startOverlay .brand").textContent = assistantName;
    apiKeyInput.value = "";
    settingsOverlay.classList.add("hidden");
  });

  // ─────────────────────────────────────────────────────────
  //  PWA 서비스 워커
  // ─────────────────────────────────────────────────────────
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  }

  // 초기 상태
  setUiState("idle");
})();
