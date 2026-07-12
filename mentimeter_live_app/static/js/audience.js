(() => {
  const root = document.querySelector("[data-audience]");
  if (!root) return;

  const code = root.dataset.code;
  let participantToken = root.dataset.token || window.MENTI_PARTICIPANT_TOKEN || localStorage.getItem(`menti:${code}:token`);
  const state = { session: null, socket: null, timer: null, score: 0, submitting: false };

  const questionArea = document.querySelector("[data-question-area]");
  const statusNode = document.querySelector("[data-audience-status]");
  const scoreNode = document.querySelector("[data-score]");
  const connectedNode = document.querySelector("[data-connected-count]");

  connect();
  loadSession();

  function connect() {
    if (!window.io) {
      setConnectionStatus("Sin conexión en vivo. Mostramos la última actualización.");
      return;
    }
    state.socket = window.io({ reconnection: true });
    state.socket.on("connect", join);
    state.socket.on("session_state", (next) => {
      state.session = next;
      render();
    });
    state.socket.on("results_updated", () => {
      // La audiencia no muestra resultados agregados, pero conserva una conexión viva.
      setConnectionStatus("Conectado");
    });
    state.socket.on("participant_count", (payload) => {
      if (connectedNode) connectedNode.textContent = `${payload?.connected_count || 0} conectados`;
    });
    state.socket.on("disconnect", () => setConnectionStatus("Reconectando…"));
    state.socket.on("connect_error", () => setConnectionStatus("Reconectando…"));
  }

  function join() {
    if (!state.socket) return;
    state.socket.emit("join_session", { code, participant_token: participantToken }, (ack) => {
      if (!ack?.ok) {
        setConnectionStatus(ack?.error || "No se pudo unir a la sesión.");
        return;
      }
      participantToken = ack.participant_token || participantToken;
      if (participantToken) localStorage.setItem(`menti:${code}:token`, participantToken);
      state.session = ack.session;
      setConnectionStatus("Conectado");
      render();
    });
  }

  async function loadSession() {
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(code)}`, { headers: { Accept: "application/json" } });
      const json = await response.json();
      if (json?.ok && json.session) {
        state.session = json.session;
        render();
      }
    } catch (_error) {
      setConnectionStatus("No pudimos cargar la sesión. Revisa tu conexión.");
    }
  }

  function render() {
    clearTimer();
    const question = activeQuestion();
    if (!question) {
      questionArea.innerHTML = waitingMarkup();
      return;
    }

    if (question.type === "content_slide") {
      questionArea.innerHTML = contentSlideMarkup(question);
      return;
    }

    if (state.session.status !== "active") {
      questionArea.innerHTML = `
        <div class="audience-waiting">
          <p class="eyebrow">${escapeHtml(labelForType(question.type))}</p>
          <h2>${escapeHtml(question.title)}</h2>
          <p class="muted">El presentador aún no inicia esta sesión.</p>
        </div>`;
      return;
    }

    if (!question.is_open) {
      questionArea.innerHTML = `
        <div class="audience-waiting">
          <p class="eyebrow">${escapeHtml(labelForType(question.type))}</p>
          <h2>${escapeHtml(question.title)}</h2>
          <p>${lineBreaks(question.prompt)}</p>
          <p class="muted">La participación está cerrada. Espera la siguiente indicación.</p>
        </div>`;
      return;
    }

    questionArea.innerHTML = `
      <p class="eyebrow">${escapeHtml(labelForType(question.type))}</p>
      <h2>${escapeHtml(question.title)}</h2>
      <p class="audience-question-prompt">${lineBreaks(question.prompt)}</p>
      ${answerMarkup(question)}
      <p class="muted audience-submit-status" data-submit-status role="status"></p>
    `;
    if (question.type === "quiz") startTimer(question);
    wireAnswer(question);
  }

  function waitingMarkup() {
    return `
      <div class="audience-waiting">
        <span class="audience-waiting-mark" aria-hidden="true">L</span>
        <h2>Esperando al presentador</h2>
        <p class="muted">La diapositiva activa aparecerá automáticamente.</p>
      </div>`;
  }

  function answerMarkup(question) {
    if (question.type === "multiple_choice" || question.type === "quiz") {
      const buttons = (question.options || [])
        .map((option) => `<button type="button" data-option-id="${option.id}">${escapeHtml(option.label)}</button>`)
        .join("");
      return `<div class="answer-options">${buttons}</div>${question.type === "quiz" ? '<strong class="audience-timer" data-timer></strong>' : ""}`;
    }
    if (question.type === "word_cloud") {
      return `
        <form data-answer-form>
          <label class="visually-hidden" for="word-answer">Tu palabra o frase</label>
          <input id="word-answer" name="text" maxlength="80" placeholder="Escribe una palabra o frase corta" required>
          <button type="submit">Enviar respuesta</button>
        </form>`;
    }
    if (question.type === "open_text") {
      return `
        <form data-answer-form>
          <label class="visually-hidden" for="open-answer">Tu respuesta</label>
          <textarea id="open-answer" name="text" rows="4" maxlength="500" placeholder="Escribe tu respuesta" required></textarea>
          <button type="submit">Enviar respuesta</button>
        </form>`;
    }
    if (question.type === "scale") {
      const minimum = number(question.config?.min, 1, 1, 10);
      const maximum = number(question.config?.max, 5, minimum + 1, 10);
      const buttons = [];
      for (let value = minimum; value <= maximum; value += 1) {
        buttons.push(`<button type="button" data-scale-value="${value}" aria-label="Seleccionar ${value}">${value}</button>`);
      }
      return `<div class="scale-options">${buttons.join("")}</div>`;
    }
    if (question.type === "ranking") {
      return `
        <p class="muted">Ordena las opciones desde la prioridad mayor hasta la menor.</p>
        <div class="ranking-list" data-ranking-list>
          ${(question.options || []).map((option) => rankingRow(option)).join("")}
        </div>
        <button type="button" data-submit-ranking>Enviar ranking</button>`;
    }
    return "";
  }

  function contentSlideMarkup(question) {
    const config = question.config || {};
    const background = backgroundInfo(config);
    const sessionState = state.session?.status === "active" ? "" : '<p class="audience-content-state">El presentador está preparando esta sesión.</p>';
    return `
      <section class="audience-content-slide audience-content-slide--${safeClass(config.layout || "content")}" style="--audience-slide-background:${escapeAttr(background.color)}">
        ${background.image ? `<img class="audience-background-image" src="${escapeAttr(background.image)}" alt="" style="object-fit:${background.fit};opacity:${background.opacity}">` : ""}
        <div class="audience-content-copy">
          ${contentTextBoxesMarkup(question)}
        </div>
        ${mediaBlocksMarkup(question)}
        ${qrMarkup(question)}
        ${sessionState}
      </section>`;
  }

  function contentTextBoxes(question) {
    const config = question.config || {};
    let boxes = Array.isArray(config.text_boxes) ? config.text_boxes.filter((box) => box && typeof box === "object") : [];
    if (!boxes.length) {
      boxes = [
        { id: "title", text: question.title, font_size: 38, font_weight: 800, color: "#17212f", align: "left" },
        ...(config.body ? [{ id: "body", text: config.body, font_size: 20, font_weight: 400, color: "#334155", align: "left" }] : []),
      ];
    } else if (!boxes.some((box) => box.id === "title")) {
      boxes.unshift({ id: "title", text: question.title, font_size: 38, font_weight: 800, color: "#17212f", align: "left", z: -1 });
    }
    return boxes;
  }

  function contentTextBoxesMarkup(question) {
    return contentTextBoxes(question)
      .sort((left, right) => number(left.y, 0, 0, 100) - number(right.y, 0, 0, 100) || number(left.z, 0, -1, 100) - number(right.z, 0, -1, 100))
      .map((box, index) => {
        const size = number(box.font_size, index ? 20 : 38, 8, 120);
        const weight = number(box.font_weight, index ? 400 : 800, 100, 900) >= 600 ? 800 : 400;
        const style = [
          `--audience-text-size:${Math.max(1, size / 8).toFixed(2)}vw`,
          `--audience-text-max:${Math.round(Math.min(46, size * 1.08))}px`,
          `--audience-text-weight:${weight}`,
          `--audience-text-color:${safeColor(box.color, "#17212f")}`,
          `--audience-text-background:${box.background === "transparent" ? "transparent" : safeColor(box.background, "transparent")}`,
          `--audience-text-align:${["left", "center", "right"].includes(box.align) ? box.align : "left"}`,
        ].join(";");
        return `<div class="audience-content-text" style="${escapeAttr(style)}">${lineBreaks(box.text)}</div>`;
      }).join("");
  }

  function backgroundInfo(config) {
    const raw = config?.background;
    let color = config?.background_color || config?.backgroundColor || "#f8fafc";
    let image = config?.background_image_url || config?.backgroundImage || "";
    let fit = "cover";
    let opacity = 0.16;
    if (typeof raw === "string") {
      color = raw;
    } else if (raw && typeof raw === "object") {
      color = raw.color || raw.background_color || color;
      image = raw.asset_url || raw.image_url || raw.media_url || raw.url || raw.src || image;
      if (!image && raw.asset_id) image = assetUrl(raw.asset_id, config);
      fit = raw.fit === "contain" ? "contain" : "cover";
      opacity = number(raw.opacity, 100, 0, 100) / 100;
    }
    if (!image && config?.background_asset_id) image = assetUrl(config.background_asset_id, config);
    return { color: safeColor(color, "#f8fafc"), image: safeUrl(image), fit, opacity };
  }

  function mediaBlocks(question) {
    const config = question.config || {};
    const raw = config.media_blocks;
    let blocks = Array.isArray(raw) ? raw : raw && typeof raw === "object" ? [raw] : [];
    blocks = blocks.filter((block) => block && typeof block === "object");
    if (!blocks.length && config.media_url) blocks = [{ url: config.media_url, alt: config.media_alt || "" }];
    return blocks.map((block) => ({
      url: safeUrl(block.url || block.src || block.media_url || block.asset_url || block.asset?.url || (block.asset_id ? assetUrl(block.asset_id, config) : "")),
      alt: block.alt || block.alt_text || block.description || "",
    })).filter((block) => block.url);
  }

  function assetUrl(assetId, config) {
    const assets = [
      ...(Array.isArray(state.session?.assets) ? state.session.assets : []),
      ...(Array.isArray(config?.assets) ? config.assets : []),
      ...(Array.isArray(state.session?.presentation_assets) ? state.session.presentation_assets : []),
    ];
    const asset = assets.find((item) => String(item?.id) === String(assetId));
    return asset?.url || asset?.public_url || asset?.media_url || asset?.path || "";
  }

  function mediaBlocksMarkup(question) {
    return mediaBlocks(question).map((block) => `
      <figure class="audience-media-block">
        <img src="${escapeAttr(block.url)}" alt="${escapeAttr(block.alt)}" loading="lazy">
      </figure>`).join("");
  }

  function qrMarkup(question) {
    const config = question.config || {};
    const raw = config.qr_position || config.qr_block;
    const qrBlock = raw && typeof raw === "object" ? raw : {};
    const visible = Boolean(
      config.show_qr || config.layout === "qr" || raw === true ||
      qrBlock.enabled === true || qrBlock.visible === true,
    );
    const qrUrl = safeUrl(state.session?.qr_url);
    if (!visible || !qrUrl) return "";
    return `
      <aside class="audience-qr-card">
        <img class="audience-qr" src="${escapeAttr(qrUrl)}" alt="Código QR para unirse a la sesión ${escapeAttr(code)}">
        <span>${escapeHtml(qrBlock.label || "Participa")}</span>
        <strong>${escapeHtml(code)}</strong>
      </aside>`;
  }

  function wireAnswer(question) {
    questionArea.querySelectorAll("[data-option-id]").forEach((button) => {
      button.addEventListener("click", () => submit(question, { option_id: Number(button.dataset.optionId) }));
    });
    questionArea.querySelectorAll("[data-scale-value]").forEach((button) => {
      button.addEventListener("click", () => submit(question, { value: Number(button.dataset.scaleValue) }));
    });
    questionArea.querySelector("[data-answer-form]")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      submit(question, { text: form.get("text") });
      event.currentTarget.reset();
    });
    const rankingList = questionArea.querySelector("[data-ranking-list]");
    rankingList?.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-move]");
      if (!button) return;
      const row = button.closest("[data-ranking-option]");
      if (!row) return;
      if (button.dataset.move === "up" && row.previousElementSibling) rankingList.insertBefore(row, row.previousElementSibling);
      if (button.dataset.move === "down" && row.nextElementSibling) rankingList.insertBefore(row.nextElementSibling, row);
    });
    questionArea.querySelector("[data-submit-ranking]")?.addEventListener("click", () => {
      submit(question, {
        ranking: Array.from(questionArea.querySelectorAll("[data-ranking-option]")).map((row) => Number(row.dataset.rankingOption)),
      });
    });
  }

  function rankingRow(option) {
    return `
      <div class="ranking-option" data-ranking-option="${option.id}">
        <strong>${escapeHtml(option.label)}</strong>
        <button type="button" data-move="up">Subir</button>
        <button type="button" data-move="down">Bajar</button>
      </div>`;
  }

  function submit(question, payload) {
    if (state.submitting) return;
    state.submitting = true;
    setSubmitStatus("Enviando…");
    disableAnswerControls(true);
    const body = { code, question_id: question.id, participant_token: participantToken, payload };
    if (state.socket?.connected) {
      state.socket.emit("submit_response", body, handleSubmitAck);
      return;
    }
    fetch(`/api/sessions/${encodeURIComponent(code)}/questions/${question.id}/responses`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    })
      .then((response) => response.json())
      .then(handleSubmitAck)
      .catch(() => handleSubmitAck({ ok: false, error: "No se pudo enviar. Revisa tu conexión." }));
  }

  function handleSubmitAck(ack) {
    state.submitting = false;
    disableAnswerControls(false);
    if (!ack?.ok) {
      setSubmitStatus(ack?.error || "No se pudo enviar.");
      return;
    }
    participantToken = ack.participant_token || participantToken;
    if (participantToken) localStorage.setItem(`menti:${code}:token`, participantToken);
    state.score = ack.score ?? state.score;
    if (scoreNode) scoreNode.textContent = `${state.score} pts`;
    setSubmitStatus("Respuesta recibida.");
  }

  function disableAnswerControls(disabled) {
    questionArea.querySelectorAll("button, input, textarea").forEach((control) => { control.disabled = disabled; });
  }

  function activeQuestion() {
    return state.session?.questions?.find((question) => question.id === state.session.active_question_id) || null;
  }

  function startTimer(question) {
    const timerNode = questionArea.querySelector("[data-timer]");
    if (!timerNode) return;
    const paint = () => {
      const remaining = timerRemaining(question);
      timerNode.textContent = `${remaining}s`;
      if (remaining <= 0) {
        clearTimer();
        setSubmitStatus("Tiempo agotado.");
        disableAnswerControls(true);
      }
    };
    paint();
    state.timer = window.setInterval(paint, 500);
  }

  function timerRemaining(question) {
    const timer = question.timer || {};
    const duration = number(timer.duration ?? question.config?.timer_seconds, 30, 0, 600);
    if (!timer.started_at) return number(timer.remaining, duration, 0, duration);
    const source = String(timer.started_at);
    const started = Date.parse(source.endsWith("Z") ? source : `${source}Z`);
    if (Number.isNaN(started)) return number(timer.remaining, duration, 0, duration);
    return Math.max(0, duration - Math.floor((Date.now() - started) / 1000));
  }

  function clearTimer() {
    if (state.timer) window.clearInterval(state.timer);
    state.timer = null;
  }

  function setConnectionStatus(message) {
    if (statusNode) statusNode.textContent = message;
  }

  function setSubmitStatus(message) {
    const node = questionArea.querySelector("[data-submit-status]");
    if (node) node.textContent = message;
  }

  function labelForType(type) {
    return {
      multiple_choice: "Opción múltiple",
      content_slide: "Contenido",
      word_cloud: "Nube de palabras",
      scale: "Escala",
      open_text: "Pregunta abierta",
      ranking: "Ranking",
      quiz: "Quiz",
    }[type] || String(type || "Diapositiva");
  }

  function number(value, fallback, minimum, maximum) {
    const parsed = Number(value);
    return Math.min(maximum, Math.max(minimum, Number.isFinite(parsed) ? parsed : fallback));
  }

  function safeClass(value) {
    return String(value || "").replace(/[^a-z0-9_-]/gi, "") || "content";
  }

  function safeColor(value, fallback) {
    const color = String(value || "").trim();
    if (!color || /[;{}<>]/.test(color)) return fallback;
    if (/^#[0-9a-f]{3,8}$/i.test(color)) return color;
    if (window.CSS?.supports?.("color", color)) return color;
    return fallback;
  }

  function safeUrl(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (/^data:image\/(png|jpe?g|webp);base64,/i.test(raw)) return raw;
    try {
      const url = new URL(raw, window.location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function lineBreaks(value) {
    return escapeHtml(value).replace(/\n/g, "<br>");
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
    }[character]));
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
  }
})();
