(() => {
  const consoleRoot = document.querySelector("[data-presenter-console]");
  const projectionRoot = document.querySelector("[data-projection]");
  const root = consoleRoot || projectionRoot;
  if (!root) return;

  const code = root.dataset.code || window.MENTI_SESSION_CODE;
  if (!code) return;

  const mode = consoleRoot ? "presenter" : "projection";
  const canvas = document.querySelector(mode === "presenter" ? "[data-presenter-canvas]" : "[data-projection-canvas]");
  const canvasClasses = canvas?.className || "projection-canvas";
  const state = {
    session: null,
    socket: null,
    connection: "Conectando a la sesión en vivo…",
    busy: false,
  };

  const nodes = {
    projectionStatus: document.querySelector("[data-projection-status]"),
    projectionSummary: document.querySelector("[data-projection-summary]"),
    title: document.querySelector("[data-presenter-title]"),
    status: document.querySelector("[data-presenter-status]"),
    connected: document.querySelector("[data-presenter-connected]"),
    position: document.querySelector("[data-presenter-position]"),
    slideCount: document.querySelector("[data-presenter-slide-count]"),
    slideList: document.querySelector("[data-presenter-slide-list]"),
    liveState: document.querySelector("[data-presenter-live-state]"),
    feedback: document.querySelector("[data-presenter-feedback]"),
    notes: document.querySelector("[data-presenter-notes]"),
    moderationSection: document.querySelector("[data-presenter-moderation-section]"),
    pendingCount: document.querySelector("[data-presenter-pending-count]"),
    moderation: document.querySelector("[data-presenter-moderation]"),
  };

  bindConsoleEvents();
  connect();
  loadSession();
  window.setInterval(updateCountdowns, 500);

  function bindConsoleEvents() {
    if (!consoleRoot) return;

    consoleRoot.addEventListener("click", (event) => {
      const actionButton = event.target.closest("button[data-presenter-action]");
      if (actionButton) {
        const action = actionButton.dataset.presenterAction;
        if (action === "reset" && !window.confirm("Se cerrará la ejecución actual y se preparará una nueva. Las respuestas históricas se conservarán.")) {
          return;
        }
        controlSession(action);
        return;
      }

      const slideButton = event.target.closest("button[data-go-to-slide]");
      if (slideButton) {
        controlSession("go_to_slide", { index: Number(slideButton.dataset.goToSlide || 0) });
        return;
      }

      const moderationButton = event.target.closest("button[data-presenter-moderate]");
      if (moderationButton) {
        moderateResponse(Number(moderationButton.dataset.responseId || 0), moderationButton.dataset.presenterModerate);
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.defaultPrevented || isTypingTarget(event.target)) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        controlSession("next");
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        controlSession("previous");
      } else if (event.key.toLowerCase() === "o") {
        controlSession("open_question");
      } else if (event.key.toLowerCase() === "c") {
        controlSession("close_question");
      }
    });
  }

  function isTypingTarget(target) {
    return target instanceof HTMLElement && (target.matches("input, textarea, select") || target.isContentEditable);
  }

  function connect() {
    if (!window.io) {
      setConnection("Actualización en vivo no disponible; se usa la última carga.", "warning");
      return;
    }

    state.socket = window.io({ reconnection: true });
    state.socket.on("connect", () => {
      setConnection("Conectado en vivo", "connected");
      const joinEvent = mode === "presenter" ? "presenter_join" : "projection_join";
      state.socket.emit(joinEvent, { code }, (ack) => {
        if (!ack?.ok || !ack.session) {
          setConnection(ack?.error || "No fue posible conectar la presentaci\u00f3n.", "error");
          return;
        }
        setSession(ack.session);
      });
    });
    state.socket.on("session_state", (next) => setSession(next));
    if (mode === "presenter") {
      // Only the authenticated presenter console can receive speaker notes.
      state.socket.on("presenter_session_state", (next) => setSession(next));
    }
    state.socket.on("results_updated", (payload) => {
      if (!state.session || !payload?.question_id) return;
      state.session.questions = (state.session.questions || []).map((question) => (
        question.id === payload.question_id ? { ...question, results: payload.results } : question
      ));
      render();
    });
    state.socket.on("participant_count", (payload) => {
      if (!state.session) return;
      state.session.connected_count = Number(payload?.connected_count || 0);
      state.session.response_monitor = payload?.response_monitor || state.session.response_monitor;
      renderConsoleChrome();
    });
    state.socket.on("disconnect", () => setConnection("Reconectando a la sesión…", "warning"));
    state.socket.on("connect_error", () => setConnection("No se pudo conectar en vivo. Reintentando…", "warning"));
  }

  async function loadSession() {
    try {
      const privateQuery = mode === "presenter" ? "?include_private=1" : "";
      const response = await fetch(`/api/sessions/${encodeURIComponent(code)}${privateQuery}`, { headers: { Accept: "application/json" } });
      const json = await response.json();
      if (json?.ok && json.session) {
        setSession(json.session);
      } else if (!state.session) {
        setConnection(json?.error || "No se pudo cargar la presentación.", "error");
      }
    } catch (_error) {
      if (!state.session) setConnection("No se pudo cargar la presentación. Revisa tu conexión.", "error");
    }
  }

  function setSession(session) {
    if (!session || typeof session !== "object") return;
    state.session = session;
    document.body.dataset.theme = session.theme || "civic";
    render();
  }

  function setConnection(message, kind = "") {
    state.connection = message;
    if (nodes.projectionStatus) {
      nodes.projectionStatus.textContent = message;
      nodes.projectionStatus.dataset.state = kind;
    }
    if (nodes.feedback && !state.busy) {
      nodes.feedback.textContent = kind === "connected" ? "" : message;
      nodes.feedback.dataset.state = kind;
    }
  }

  function render() {
    renderCanvas();
    renderConsoleChrome();
  }

  function activeQuestion() {
    const questions = state.session?.questions || [];
    return questions.find((question) => question.id === state.session?.active_question_id) || questions[0] || null;
  }

  function activeIndex() {
    const question = activeQuestion();
    return Math.max(0, (state.session?.questions || []).findIndex((item) => item.id === question?.id));
  }

  function renderCanvas() {
    if (!canvas) return;
    const question = activeQuestion();
    canvas.className = `${canvasClasses}${question ? ` projection-kind-${safeClass(question.type)}` : ""}`;
    canvas.setAttribute("aria-busy", "false");
    if (!question) {
      canvas.innerHTML = `
        <div class="projection-empty">
          <span class="projection-empty-mark" aria-hidden="true">L</span>
          <h2>La presentación todavía no tiene diapositivas</h2>
          <p>Vuelve al editor para crear la primera.</p>
        </div>
      `;
      updateProjectionSummary("La presentación todavía no tiene diapositivas.");
      return;
    }
    canvas.innerHTML = slideMarkup(question);
    updateProjectionSummary(`${question.position || activeIndex() + 1}. ${question.title}. ${labelForType(question.type)}.`);
    updateCountdowns();
  }

  function updateProjectionSummary(text) {
    if (nodes.projectionSummary) nodes.projectionSummary.textContent = text;
  }

  function slideMarkup(question) {
    const config = question.config || {};
    const background = backgroundInfo(config);
    const backgroundStyle = ` style="--projection-background:${escapeAttr(background.color)}"`;
    const backgroundImage = background.image
      ? `<img class="projection-background-image" src="${escapeAttr(background.image)}" alt="" style="object-fit:${background.fit};opacity:${background.opacity}">`
      : "";
    const label = labelForType(question.type);
    const stateLabel = question.type === "content_slide"
      ? "Contenido"
      : question.is_open && state.session?.status === "active" ? "Participación abierta" : "Participación cerrada";
    const shellStart = `
      <div class="projection-slide projection-slide--${safeClass(question.type)}"${backgroundStyle}>
        ${backgroundImage}
        <div class="projection-slide-header" aria-hidden="true">
          <span>${escapeHtml(label)}</span>
          <span>${escapeHtml(stateLabel)}</span>
        </div>`;
    const overlays = `${mediaBlocksMarkup(question, "projection")}${qrMarkup(question, "projection")}`;

    if (question.type === "content_slide") {
      return `${shellStart}
        <div class="projection-content-text-layer">
          ${contentTextBoxesMarkup(question, "projection")}
        </div>
        ${overlays}
      </div>`;
    }

    const blocks = layoutBlocks(config);
    return `${shellStart}
      <section class="projection-layout-block projection-question-block" style="${layoutStyle(blocks.question)}">
        <h1${textStyleAttribute(config, "title", { font_size: 60, font_weight: 800, color: "#17212f", align: "left" })}>${escapeHtml(question.title)}</h1>
        <p${textStyleAttribute(config, "prompt", { font_size: 24, font_weight: 400, color: "#334155", align: "left" })}>${lineBreaks(question.prompt)}</p>
      </section>
      <section class="projection-layout-block projection-activity-block" style="${layoutStyle(blocks.activity)}">
        ${activityMarkup(question)}
      </section>
      <section class="projection-layout-block projection-results-block" style="${layoutStyle(blocks.results)}" data-slide-results-stage>
        ${resultsMarkup(question)}
      </section>
      ${overlays}
    </div>`;
  }

  function backgroundInfo(config) {
    const raw = config?.background;
    let color = config?.background_color || config?.backgroundColor || "#f8fafc";
    let image = config?.background_image_url || config?.backgroundImage || "";
    let fit = "cover";
    let opacity = 0.24;
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

  function contentTextBoxes(question) {
    const config = question.config || {};
    let boxes = Array.isArray(config.text_boxes) ? config.text_boxes.filter((box) => box && typeof box === "object") : [];
    if (!boxes.length) {
      boxes = [
        { id: "title", text: question.title, x: 8, y: 16, w: 64, h: 22, font_size: 60, font_weight: 800, color: "#17212f", align: "left" },
        ...(config.body ? [{ id: "body", text: config.body, x: 8, y: 44, w: 58, h: 30, font_size: 28, font_weight: 400, color: "#334155", align: "left" }] : []),
      ];
    } else if (!boxes.some((box) => box.id === "title")) {
      boxes.unshift({ id: "title", text: question.title, x: 8, y: 16, w: 64, h: 22, font_size: 60, font_weight: 800, color: "#17212f", align: "left", z: 1 });
    }
    return boxes;
  }

  function contentTextBoxesMarkup(question, surface) {
    return contentTextBoxes(question)
      .sort((left, right) => number(left.z, 0, 0, 100) - number(right.z, 0, 0, 100))
      .map((box, index) => textBoxMarkup(box, surface, index))
      .join("");
  }

  function textBoxMarkup(box, surface, index) {
    const fontSize = number(box.font_size, index ? 28 : 60, 8, 120);
    const geometry = {
      x: number(box.x, index ? 8 : 8, 0, 100),
      y: number(box.y, index ? 44 : 16, 0, 100),
      w: number(box.w, index ? 58 : 64, 5, 100),
      h: number(box.h, index ? 24 : 22, 5, 100),
      z: number(box.z, index + 1, 0, 100),
    };
    const style = [
      `left:${geometry.x}%`, `top:${geometry.y}%`, `width:${geometry.w}%`, `height:${geometry.h}%`, `z-index:${geometry.z}`,
      `--projection-text-size:${Math.max(0.8, fontSize / 11).toFixed(2)}vw`,
      `--projection-text-max:${Math.round(fontSize * 1.12)}px`,
      `--projection-text-weight:${number(box.font_weight, index ? 400 : 800, 100, 900) >= 600 ? 800 : 400}`,
      `--projection-text-color:${safeColor(box.color, "#17212f")}`,
      `--projection-text-background:${box.background === "transparent" ? "transparent" : safeColor(box.background, "transparent")}`,
      `--projection-text-align:${["left", "center", "right"].includes(box.align) ? box.align : "left"}`,
    ].join(";");
    const className = surface === "audience" ? "audience-content-text" : "projection-content-text";
    return `<div class="${className}" style="${escapeAttr(style)}">${lineBreaks(box.text)}</div>`;
  }

  function layoutBlocks(config) {
    const source = config?.layout_blocks && typeof config.layout_blocks === "object" ? config.layout_blocks : {};
    return {
      question: normalizeBlock(source.question, { x: 7, y: 12, w: 86, h: 25, z: 1 }),
      activity: normalizeBlock(source.activity, { x: 7, y: 42, w: 42, h: 43, z: 2 }),
      results: normalizeBlock(source.results, { x: 53, y: 42, w: 40, h: 43, z: 3 }),
    };
  }

  function normalizeBlock(block, defaults) {
    const source = block && typeof block === "object" ? block : {};
    const width = number(source.w, defaults.w, 12, 100);
    const height = number(source.h, defaults.h, 10, 100);
    return {
      x: number(source.x, defaults.x, 0, Math.max(0, 100 - width)),
      y: number(source.y, defaults.y, 0, Math.max(0, 100 - height)),
      w: width,
      h: height,
      z: number(source.z, defaults.z, 0, 100),
    };
  }

  function layoutStyle(block) {
    return `left:${block.x}%;top:${block.y}%;width:${block.w}%;height:${block.h}%;z-index:${block.z};`;
  }

  function textStyleAttribute(config, key, defaults) {
    const style = config?.text_styles?.[key] || {};
    const fontSize = number(style.font_size, defaults.font_size, 8, 120);
    const css = [
      `--projection-target-size:${Math.max(0.8, fontSize / 11).toFixed(2)}vw`,
      `--projection-target-max:${Math.round(fontSize * 1.12)}px`,
      `--projection-target-weight:${number(style.font_weight, defaults.font_weight, 100, 900) >= 600 ? 800 : 400}`,
      `--projection-target-color:${safeColor(style.color, defaults.color)}`,
      `--projection-target-background:${style.background === "transparent" ? "transparent" : safeColor(style.background, "transparent")}`,
      `--projection-target-align:${["left", "center", "right"].includes(style.align) ? style.align : defaults.align}`,
    ].join(";");
    return ` style="${escapeAttr(css)}"`;
  }

  function activityMarkup(question) {
    const options = question.options || [];
    if (["multiple_choice", "quiz", "ranking"].includes(question.type)) {
      return `<ol class="projection-option-list projection-option-list--${safeClass(question.type)}">
        ${options.map((option, index) => `
          <li${textStyleAttribute(question.config || {}, `option:${index}`, { font_size: 20, font_weight: 800, color: "#17212f", align: "left" })}>
            <span>${String.fromCharCode(65 + index)}</span><b>${escapeHtml(option.label)}</b>
          </li>`).join("")}
      </ol>${question.type === "quiz" ? timerMarkup(question) : ""}`;
    }
    if (question.type === "scale") {
      const minimum = number(question.config?.min, 1, 1, 10);
      const maximum = number(question.config?.max, 5, minimum + 1, 10);
      const values = Array.from({ length: maximum - minimum + 1 }, (_item, offset) => minimum + offset);
      return `<div class="projection-scale-preview" aria-label="Escala de ${minimum} a ${maximum}">
        ${values.map((value) => `<span>${value}</span>`).join("")}
      </div>`;
    }
    if (question.type === "word_cloud") {
      return `<div class="projection-activity-placeholder"><strong>Una palabra a la vez</strong><span>Las ideas aparecerán en vivo.</span></div>`;
    }
    if (question.type === "open_text") {
      return `<div class="projection-activity-placeholder"><strong>Comparte una respuesta</strong><span>Las participaciones aprobadas se mostrarán aquí.</span></div>`;
    }
    return `<div class="projection-activity-placeholder"><strong>Participación en vivo</strong></div>`;
  }

  function timerMarkup(question) {
    const remaining = countdownFor(question);
    return `<div class="projection-timer" data-projection-countdown data-question-id="${question.id}"><span>Tiempo</span><strong>${remaining}s</strong></div>`;
  }

  function countdownFor(question) {
    const timer = question?.timer || {};
    const duration = number(timer.duration ?? question?.config?.timer_seconds, 30, 0, 600);
    if (!timer.started_at) return number(timer.remaining, duration, 0, duration);
    const started = Date.parse(timer.started_at.endsWith("Z") ? timer.started_at : `${timer.started_at}Z`);
    if (Number.isNaN(started)) return number(timer.remaining, duration, 0, duration);
    return Math.max(0, duration - Math.floor((Date.now() - started) / 1000));
  }

  function updateCountdowns() {
    document.querySelectorAll("[data-projection-countdown]").forEach((node) => {
      const question = (state.session?.questions || []).find((item) => item.id === Number(node.dataset.questionId));
      const strong = node.querySelector("strong");
      if (question && strong) strong.textContent = `${countdownFor(question)}s`;
    });
  }

  function resultsMarkup(question) {
    const config = question.config || {};
    const results = question.results || {};
    if (config.show_results === false) {
      return `<div class="projection-results projection-results--hidden"><strong>Resultados ocultos</strong><span>El presentador los mostrará cuando corresponda.</span></div>`;
    }
    const total = Number(results.total || 0);
    const layout = String(config.result_layout || defaultResultLayout(question.type)).toLowerCase();
    const heading = `<header class="projection-results-head"><span>Resultados en vivo</span><strong>${total} respuesta${total === 1 ? "" : "s"}</strong></header>`;
    let body = "";
    if (["multiple_choice", "quiz"].includes(question.type)) {
      body = choiceResults(results, layout, question.type);
    } else if (question.type === "scale") {
      body = scaleResults(results, layout);
    } else if (question.type === "ranking") {
      body = rankingResults(results, layout);
    } else if (question.type === "word_cloud") {
      body = wordResults(results, layout);
    } else if (question.type === "open_text") {
      body = textResults(results, layout);
    }
    return `<div class="projection-results projection-results--${safeClass(layout)}">${heading}${body || emptyResultsMarkup()}</div>`;
  }

  function choiceResults(results, layout, type) {
    const items = Array.isArray(results.options) ? results.options : [];
    if (layout === "leaderboard" && type === "quiz" && results.leaderboard?.length) return leaderboardMarkup(results.leaderboard);
    if (layout === "grid" || layout === "cards") {
      return `<div class="projection-result-grid">${items.map((item) => `<article><strong>${escapeHtml(item.label)}</strong><b>${Number(item.count || 0)}</b></article>`).join("")}</div>`;
    }
    if (layout === "list") return listResultsMarkup(items, "count");
    return chartResultsMarkup(items, "count");
  }

  function scaleResults(results, layout) {
    const items = Array.isArray(results.values) ? results.values.map((item) => ({ label: item.value, count: item.count })) : [];
    if (layout === "grid") {
      return `${choiceResults({ options: items }, "grid", "scale")}<p class="projection-average">Promedio <strong>${escapeHtml(results.average || 0)}</strong></p>`;
    }
    if (layout === "list") return `${listResultsMarkup(items, "count")}<p class="projection-average">Promedio <strong>${escapeHtml(results.average || 0)}</strong></p>`;
    return `${chartResultsMarkup(items, "count")}<p class="projection-average">Promedio <strong>${escapeHtml(results.average || 0)}</strong></p>`;
  }

  function rankingResults(results, layout) {
    const items = Array.isArray(results.options) ? results.options : [];
    if (layout === "ranking" || layout === "list") {
      const ordered = [...items].sort((left, right) => Number(right.score || 0) - Number(left.score || 0));
      return `<ol class="projection-ranking-results">${ordered.map((item, index) => `<li><span>${index + 1}</span><strong>${escapeHtml(item.label)}</strong><b>${Number(item.score || 0)}</b></li>`).join("")}</ol>`;
    }
    return chartResultsMarkup(items.map((item) => ({ ...item, count: item.score })), "count");
  }

  function wordResults(results, layout) {
    const items = Array.isArray(results.words) ? results.words : [];
    if (!items.length) return emptyResultsMarkup("Todavía no hay palabras.");
    if (layout === "list") return listResultsMarkup(items, "count");
    const largest = Math.max(...items.map((item) => Number(item.count || 0)), 1);
    return `<div class="projection-word-cloud">${items.slice(0, 36).map((item) => {
      const ratio = Number(item.count || 0) / largest;
      return `<span style="font-size:clamp(0.55rem, ${((0.8 + ratio * 1.7) * 0.8).toFixed(2)}vw, 1.6rem);--word-alpha:${(0.12 + ratio * 0.3).toFixed(2)}">${escapeHtml(item.text)} <b>${Number(item.count || 0)}</b></span>`;
    }).join("")}</div>`;
  }

  function textResults(results, layout) {
    const items = Array.isArray(results.cards) ? results.cards : [];
    if (!items.length) return emptyResultsMarkup("Todavía no hay respuestas aprobadas.");
    if (layout === "list") return `<ul class="projection-open-list">${items.slice(0, 8).map((item) => `<li>${escapeHtml(item.text)}</li>`).join("")}</ul>`;
    return `<div class="projection-open-grid">${items.slice(0, 8).map((item) => `<article>${escapeHtml(item.text)}</article>`).join("")}</div>`;
  }

  function chartResultsMarkup(items, valueKey) {
    if (!items.length) return emptyResultsMarkup();
    const maximum = Math.max(...items.map((item) => Number(item[valueKey] || 0)), 1);
    return `<div class="projection-bar-chart">${items.map((item) => {
      const value = Number(item[valueKey] || 0);
      const width = Math.max(0, Math.min(100, value / maximum * 100));
      return `<div><span>${escapeHtml(item.label)}</span><i><b style="width:${width.toFixed(2)}%"></b></i><strong>${value}</strong></div>`;
    }).join("")}</div>`;
  }

  function listResultsMarkup(items, valueKey) {
    if (!items.length) return emptyResultsMarkup();
    return `<ul class="projection-result-list">${items.map((item) => `<li><span>${escapeHtml(item.label ?? item.text)}</span><b>${Number(item[valueKey] || 0)}</b></li>`).join("")}</ul>`;
  }

  function leaderboardMarkup(items) {
    return `<ol class="projection-leaderboard">${items.slice(0, 6).map((item, index) => `<li><span>${index + 1}</span><strong>Participante ${escapeHtml(item.participant_id ?? item.label ?? "")}</strong><b>${Number(item.score || 0)} pts</b></li>`).join("")}</ol>`;
  }

  function emptyResultsMarkup(message = "Esperando las primeras respuestas.") {
    return `<p class="projection-results-empty">${escapeHtml(message)}</p>`;
  }

  function mediaBlocks(question) {
    const config = question.config || {};
    const raw = config.media_blocks;
    let blocks = Array.isArray(raw) ? raw : raw && typeof raw === "object" ? [raw] : [];
    blocks = blocks.filter((block) => block && typeof block === "object");
    if (!blocks.length && config.media_url) blocks = [{ id: "legacy-media", url: config.media_url, alt: config.media_alt || "" }];
    return blocks.map((block, index) => ({
      ...block,
      id: block.id || `media-${index}`,
      url: mediaUrl(block, config),
      alt: block.alt || block.alt_text || block.description || "",
      x: number(block.x, 67, 0, 100),
      y: number(block.y, 14, 0, 100),
      w: number(block.w, 25, 5, 100),
      h: number(block.h, 42, 5, 100),
      z: number(block.z, 8 + index, 0, 100),
      fit: ["contain", "cover", "fill"].includes(block.fit || block.object_fit) ? (block.fit || block.object_fit) : "cover",
    })).filter((block) => block.url);
  }

  function mediaUrl(block, config) {
    return safeUrl(
      block.url || block.src || block.media_url || block.asset_url || block.asset?.url ||
      (block.asset_id ? assetUrl(block.asset_id, config) : ""),
    );
  }

  function assetUrl(assetId, config) {
    const candidates = [
      ...(Array.isArray(state.session?.assets) ? state.session.assets : []),
      ...(Array.isArray(config?.assets) ? config.assets : []),
      ...(Array.isArray(state.session?.presentation_assets) ? state.session.presentation_assets : []),
    ];
    const asset = candidates.find((item) => String(item?.id) === String(assetId));
    return asset?.url || asset?.public_url || asset?.media_url || asset?.path || "";
  }

  function mediaBlocksMarkup(question, surface) {
    return mediaBlocks(question).map((block) => {
      const geometry = surface === "projection"
        ? `left:${block.x}%;top:${block.y}%;width:${block.w}%;height:${block.h}%;z-index:${block.z};--media-fit:${block.fit};`
        : "";
      return `<figure class="${surface === "audience" ? "audience-media-block" : "projection-media-block"}"${geometry ? ` style="${escapeAttr(geometry)}"` : ""}>
        <img src="${escapeAttr(block.url)}" alt="${escapeAttr(block.alt)}" loading="lazy">
      </figure>`;
    }).join("");
  }

  function qrDetails(question) {
    const config = question.config || {};
    const raw = config.qr_position || config.qr_block;
    const rawObject = raw && typeof raw === "object" ? raw : {};
    const visible = Boolean(
      config.show_qr || config.layout === "qr" || raw === true ||
      rawObject.enabled === true || rawObject.visible === true,
    );
    if (!visible || !state.session?.qr_url) return null;
    return {
      x: number(rawObject.x, 74, 0, 100),
      y: number(rawObject.y, 61, 0, 100),
      w: number(rawObject.w, 18, 8, 45),
      h: number(rawObject.h, 28, 8, 48),
      z: number(rawObject.z, 20, 0, 100),
      label: rawObject.label || "Participa",
      url: safeUrl(state.session.qr_url),
    };
  }

  function qrMarkup(question, surface) {
    const qr = qrDetails(question);
    if (!qr) return "";
    const geometry = surface === "projection" ? `left:${qr.x}%;top:${qr.y}%;width:${qr.w}%;height:${qr.h}%;z-index:${qr.z};` : "";
    return `<aside class="${surface === "audience" ? "audience-qr-card" : "projection-qr-block"}"${geometry ? ` style="${escapeAttr(geometry)}"` : ""}>
      <img src="${escapeAttr(qr.url)}" alt="Código QR para unirse a la sesión ${escapeAttr(state.session.code)}">
      <span>${escapeHtml(qr.label)}</span>
      <strong>${escapeHtml(state.session.code)}</strong>
    </aside>`;
  }

  function renderConsoleChrome() {
    if (!consoleRoot || !state.session) return;
    const question = activeQuestion();
    const index = activeIndex();
    const questions = state.session.questions || [];
    if (nodes.title) nodes.title.textContent = state.session.title || "Presentación sin título";
    if (nodes.status) {
      nodes.status.textContent = statusLabel(state.session.status);
      nodes.status.dataset.status = state.session.status || "draft";
    }
    if (nodes.connected) nodes.connected.textContent = String(state.session.connected_count || 0);
    if (nodes.position) nodes.position.textContent = question ? `${index + 1} / ${questions.length}` : "0 / 0";
    if (nodes.slideCount) nodes.slideCount.textContent = `${questions.length}`;
    if (nodes.liveState) nodes.liveState.textContent = question?.is_open && state.session.status === "active" ? "Abierta" : "Pausada";

    renderSlideList(questions, index);
    renderNotes(question);
    renderModeration(question);
    updateControlButtons(question, questions.length);
  }

  function renderSlideList(questions, currentIndex) {
    if (!nodes.slideList) return;
    nodes.slideList.innerHTML = questions.map((question, index) => `
      <button type="button" class="presenter-slide-item${index === currentIndex ? " is-active" : ""}${question.id === state.session.active_question_id ? " is-live" : ""}" data-go-to-slide="${index}" aria-current="${index === currentIndex ? "step" : "false"}">
        <span class="presenter-slide-number">${index + 1}</span>
        <span class="presenter-slide-copy"><strong>${escapeHtml(question.title)}</strong><small>${escapeHtml(labelForType(question.type))}</small></span>
        <span class="presenter-slide-indicator" aria-label="${question.is_open ? "Participación abierta" : "Participación cerrada"}"></span>
      </button>`).join("") || `<p class="muted">Aún no hay diapositivas.</p>`;
  }

  function renderNotes(question) {
    if (!nodes.notes) return;
    const config = question?.config || {};
    const note = config.presenter_notes || config.presenter_note || config.notes || config.speaker_notes || "";
    nodes.notes.textContent = String(note || "Sin notas para esta diapositiva.");
  }

  function renderModeration(question) {
    if (!nodes.moderation || !nodes.moderationSection) return;
    const pending = Array.isArray(question?.pending_responses) ? question.pending_responses : [];
    nodes.moderationSection.hidden = !pending.length;
    if (nodes.pendingCount) nodes.pendingCount.textContent = String(pending.length);
    if (!pending.length) {
      nodes.moderation.innerHTML = "";
      return;
    }
    nodes.moderation.innerHTML = pending.map((response) => `
      <article class="presenter-moderation-item">
        <p>${escapeHtml(response.text)}</p>
        <div>
          <button type="button" class="secondary" data-presenter-moderate="approve" data-response-id="${response.id}">Aprobar</button>
          <button type="button" class="danger" data-presenter-moderate="reject" data-response-id="${response.id}">Rechazar</button>
        </div>
      </article>`).join("");
  }

  function updateControlButtons(question, questionCount) {
    const hasQuestion = Boolean(question && questionCount);
    const interactive = Boolean(question && question.type !== "content_slide");
    document.querySelectorAll("[data-presenter-action]").forEach((button) => {
      const action = button.dataset.presenterAction;
      const disabled = !hasQuestion && !["reset", "close"].includes(action) || (!interactive && ["open_question", "close_question"].includes(action));
      button.disabled = disabled || state.busy;
    });
  }

  async function controlSession(action, extra = {}) {
    if (!state.session || state.busy) return;
    state.busy = true;
    updateControlButtons(activeQuestion(), (state.session.questions || []).length);
    if (nodes.feedback) {
      nodes.feedback.textContent = "Actualizando sesión…";
      nodes.feedback.dataset.state = "pending";
    }
    const payload = { code: state.session.code, action, ...extra };
    try {
      let ack;
      if (state.socket?.connected) {
        ack = await socketCall("presenter_control", payload);
      } else {
        ack = await postJson(`/api/sessions/${encodeURIComponent(state.session.code)}/control`, { action, ...extra });
      }
      if (!ack?.ok || !ack.session) throw new Error(ack?.error || "No se pudo actualizar la sesión.");
      setSession(ack.session);
      if (nodes.feedback) {
        nodes.feedback.textContent = "Actualizado";
        nodes.feedback.dataset.state = "success";
      }
    } catch (error) {
      if (nodes.feedback) {
        nodes.feedback.textContent = error.message || "No se pudo actualizar la sesión.";
        nodes.feedback.dataset.state = "error";
      }
    } finally {
      state.busy = false;
      updateControlButtons(activeQuestion(), (state.session?.questions || []).length);
    }
  }

  async function moderateResponse(responseId, action) {
    const question = activeQuestion();
    if (!state.session || !question || !responseId || !action || state.busy) return;
    state.busy = true;
    try {
      let ack;
      const payload = { code: state.session.code, question_id: question.id, response_id: responseId, action };
      if (state.socket?.connected) {
        ack = await socketCall("moderate_response", payload);
      } else {
        ack = await postJson(
          `/api/sessions/${encodeURIComponent(state.session.code)}/questions/${question.id}/responses/${responseId}/moderate`,
          { action },
        );
      }
      if (!ack?.ok) throw new Error(ack?.error || "No se pudo moderar la respuesta.");
      if (ack.results) {
        state.session.questions = (state.session.questions || []).map((item) => (
          item.id === question.id ? { ...item, results: ack.results, pending_responses: (item.pending_responses || []).filter((response) => response.id !== responseId) } : item
        ));
      }
      render();
    } catch (error) {
      if (nodes.feedback) {
        nodes.feedback.textContent = error.message || "No se pudo moderar la respuesta.";
        nodes.feedback.dataset.state = "error";
      }
    } finally {
      state.busy = false;
      updateControlButtons(activeQuestion(), (state.session?.questions || []).length);
    }
  }

  function socketCall(event, payload) {
    return new Promise((resolve) => {
      state.socket.emit(event, payload, (ack) => resolve(ack || { ok: false, error: "Sin respuesta del servidor." }));
    });
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const json = await response.json().catch(() => ({}));
    return json;
  }

  function defaultResultLayout(type) {
    return {
      word_cloud: "cloud",
      open_text: "cards",
      quiz: "leaderboard",
      ranking: "ranking",
    }[type] || "chart";
  }

  function statusLabel(status) {
    return { active: "En vivo", closed: "Cerrada", draft: "Borrador" }[status] || "Borrador";
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
    const result = Number.isFinite(parsed) ? parsed : fallback;
    return Math.min(maximum, Math.max(minimum, result));
  }

  function safeClass(value) {
    return String(value || "").replace(/[^a-z0-9_-]/gi, "") || "slide";
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
      if (!["http:", "https:"].includes(url.protocol)) return "";
      return url.href;
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
