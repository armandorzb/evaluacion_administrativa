(() => {
  const code = window.MENTI_SESSION_CODE;
  const state = {
    session: null,
    templates: [],
    socket: null,
    chart: null,
    sortable: null,
    selectedQuestionId: null,
    selectedTextBoxId: null,
    selectedLayoutBlockId: null,
    textDrag: null,
    layoutBlockDrag: null,
    saveTimer: null,
    sessionSaveTimer: null,
    fitTimer: null,
    lastSaveKey: "",
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const LAYOUT_BLOCK_IDS = ["question", "activity", "results"];
  const DEFAULT_LAYOUT_BLOCKS = {
    question: { id: "question", x: 7, y: 12, w: 86, h: 25, z: 1 },
    activity: { id: "activity", x: 7, y: 42, w: 42, h: 43, z: 2 },
    results: { id: "results", x: 53, y: 42, w: 40, h: 43, z: 3 },
  };

  const createForm = $("[data-create-session]");
  const deckTitleInput = $("[data-deck-title]");
  const statusPill = $("[data-session-status]");
  const connectedCount = $("[data-connected-count]");
  const addSlideButton = $("[data-add-slide]");
  const addMenu = $("[data-add-menu]");
  const slideList = $("[data-slide-list]");
  const canvas = $("[data-slide-canvas]");
  const inspector = $("[data-slide-inspector]");
  const saveState = $("[data-save-state]");
  const joinCardTemplate = $("[data-join-card-template]");
  const activeSelectionControlActions = new Set(["start", "next_slide", "previous_slide", "go_to_slide", "reset"]);

  bindGlobalEvents();

  if (code) {
    connectSocket();
    loadTemplates();
    loadSession();
  } else {
    setSaveState("Sin presentación");
  }

  function bindGlobalEvents() {
    createForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const title = String(new FormData(createForm).get("title") || "").trim();
      const json = await postJson("/api/sessions", { title: title || "Nueva presentación live" });
      if (json.ok) {
        window.location.assign(`/admin?code=${json.session.code}`);
        return;
      }
      alert(json.error || "No se pudo crear la presentación.");
    });

    deckTitleInput?.addEventListener("input", () => {
      if (!state.session) return;
      state.session.title = deckTitleInput.value;
      setSaveState("Guardando título...");
      window.clearTimeout(state.sessionSaveTimer);
      state.sessionSaveTimer = window.setTimeout(() => {
        patchSession({ title: deckTitleInput.value.trim() || "Presentación sin título" });
      }, 450);
    });

    addSlideButton?.addEventListener("click", () => {
      if (!addMenu) return;
      addMenu.hidden = !addMenu.hidden;
    });

    addMenu?.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-add-type]");
      if (!button) return;
      addMenu.hidden = true;
      await addSlide(button.dataset.addType, button.dataset.layout || "");
    });

    $$("[data-control]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = normalizeControlAction(button.dataset.control);
        controlSession(action);
      });
    });

    slideList?.addEventListener("click", (event) => {
      const actionButton = event.target.closest("button[data-slide-action]");
      const thumb = event.target.closest("[data-question-id]");
      if (!thumb || !state.session) return;
      const id = Number(thumb.dataset.questionId || 0);

      if (actionButton) {
        handleSlideAction(actionButton.dataset.slideAction, id);
        return;
      }

      selectSlide(id, true);
    });

    canvas?.addEventListener("input", (event) => {
      if (!event.target.closest("[contenteditable='true']")) return;
      updateLocalQuestionFromCanvas();
      scheduleSlideTextFit();
      scheduleQuestionSave();
    });

    canvas?.addEventListener("blur", (event) => {
      if (!event.target.closest("[contenteditable='true']")) return;
      flushQuestionSave();
    }, true);

    canvas?.addEventListener("pointerdown", handleCanvasPointerDown);

    canvas?.addEventListener("click", (event) => {
      const question = selectedQuestion();
      const textBox = event.target.closest("[data-text-box-id]");
      const layoutBlock = event.target.closest("[data-layout-block-id]");
      if (textBox && question?.type === "content_slide") {
        selectTextBox(textBox.dataset.textBoxId);
      } else if (layoutBlock && question?.type !== "content_slide") {
        selectLayoutBlock(layoutBlock.dataset.layoutBlockId);
      } else if (!event.target.closest("button[data-canvas-action]") && !event.target.closest("[contenteditable='true']")) {
        selectTextBox(null);
        if (question?.type !== "content_slide") selectLayoutBlock(null);
      }
      const button = event.target.closest("button[data-canvas-action]");
      if (!button) return;
      handleCanvasAction(button.dataset.canvasAction, button);
    });

    inspector?.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      handleInspectorInput(target, false);
    });

    inspector?.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      handleInspectorInput(target, true);
    });

    inspector?.addEventListener("click", (event) => {
      const textButton = event.target.closest("button[data-text-box-action], button[data-text-align], button[data-text-color]");
      if (textButton) {
        handleTextInspectorButton(textButton);
        return;
      }
      const layoutButton = event.target.closest("button[data-layout-block-action]");
      if (layoutButton) {
        handleLayoutBlockButton(layoutButton);
        return;
      }
      const moderationButton = event.target.closest("button[data-moderate]");
      if (moderationButton) {
        handleModerationButton(moderationButton);
        return;
      }
      const button = event.target.closest("button[data-inspector-action], button[data-template-index]");
      if (!button) return;
      if (button.dataset.templateIndex) {
        const template = state.templates[Number(button.dataset.templateIndex)];
        if (template) createFromTemplate(template);
        return;
      }
      handleInspectorAction(button.dataset.inspectorAction);
    });

    document.addEventListener("click", (event) => {
      if (!addMenu || addMenu.hidden) return;
      if (event.target.closest("[data-add-menu]") || event.target.closest("[data-add-slide]")) return;
      addMenu.hidden = true;
    });

    document.addEventListener("pointermove", handleCanvasPointerMove);
    document.addEventListener("pointerup", finishCanvasDrag);
    document.addEventListener("keydown", handleDocumentKeydown);
  }

  function connectSocket() {
    if (!window.io) return;
    state.socket = window.io({ reconnection: true });
    state.socket.on("connect", () => {
      state.socket.emit("join_session", { code });
    });
    state.socket.on("session_state", (next) => {
      state.session = next;
      if (isEditing()) {
        renderChrome();
        renderSlideList();
        renderResults();
        scheduleSlideTextFit();
        return;
      }
      render();
    });
    state.socket.on("results_updated", (payload) => {
      if (!state.session) return;
      state.session.questions = state.session.questions.map((question) =>
        question.id === payload.question_id ? { ...question, results: payload.results } : question,
      );
      renderResults();
      scheduleSlideTextFit();
    });
    state.socket.on("participant_count", (payload) => {
      if (connectedCount) connectedCount.textContent = payload.connected_count || 0;
    });
  }

  async function loadTemplates() {
    const json = await getJson("/api/question-templates");
    if (!json.ok) return;
    state.templates = json.templates || [];
    renderInspector();
  }

  async function loadSession(fullRender = true) {
    if (!code) return;
    const json = await getJson(`/api/sessions/${code}`);
    if (!json.ok) return;
    state.session = json.session;
    if (fullRender) render();
    else {
      renderChrome();
      renderSlideList();
      renderInspector();
      renderResults();
      scheduleSlideTextFit();
    }
  }

  function render() {
    if (!state.session) return;
    ensureSelectedQuestion();
    renderChrome();
    renderSlideList();
    renderCanvas();
    renderInspector();
    renderResults();
    renderInsights();
    setupSortable();
    scheduleSlideTextFit();
    setSaveState("Listo");
  }

  function renderChrome() {
    if (!state.session) return;
    document.body.dataset.theme = state.session.theme || "civic";
    if (deckTitleInput && document.activeElement !== deckTitleInput) {
      deckTitleInput.value = state.session.title || "";
    }
    if (statusPill) statusPill.textContent = `${state.session.code} - ${state.session.status}`;
    if (connectedCount) connectedCount.textContent = state.session.connected_count || 0;
  }

  function renderSlideList() {
    if (!slideList || !state.session) return;
    const activeId = state.session.active_question_id;
    slideList.innerHTML = questions().map((question, index) => {
      const selected = question.id === state.selectedQuestionId ? " is-selected" : "";
      const live = question.id === activeId ? " is-live" : "";
      const optionPreview = question.options?.length
        ? `<div class="thumb-lines">${question.options.slice(0, 3).map((option) => `<span>${escapeHtml(option.label)}</span>`).join("")}</div>`
        : `<p>${escapeHtml(question.prompt || question.config?.body || "Diapositiva de contenido")}</p>`;
      return `
        <article class="slide-thumb${selected}${live}" data-question-id="${question.id}">
          <button type="button" class="slide-drag" aria-label="Reordenar">::</button>
          <div class="thumb-number">${index + 1}</div>
          <div class="thumb-preview">
            <span class="thumb-type">${escapeHtml(labelForType(question.type))}</span>
            <strong>${escapeHtml(question.title)}</strong>
            ${optionPreview}
          </div>
          <div class="thumb-actions">
            <button type="button" data-slide-action="duplicate" title="Duplicar">+</button>
            <button type="button" data-slide-action="delete" title="Eliminar">x</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderCanvas() {
    if (!canvas || !state.session) return;
    const question = selectedQuestion();
    if (!question) {
      canvas.innerHTML = `
        <div class="slide-empty">
          <h2>Agrega tu primera diapositiva</h2>
          <p>Usa el botón Añadir para insertar una portada, pregunta o dinámica.</p>
        </div>
      `;
      return;
    }

    const liveClass = question.id === state.session.active_question_id ? " is-live" : "";
    const closedClass = question.is_open ? "" : " is-closed";
    canvas.className = `slide-canvas slide-kind-${question.type}${liveClass}${closedClass}`;
    if (question.type === "content_slide") {
      state.selectedLayoutBlockId = null;
      ensureTextBoxes(question);
      canvas.innerHTML = contentSlideMarkup(question);
      scheduleSlideTextFit();
      return;
    }
    state.selectedTextBoxId = null;
    ensureLayoutBlocks(question);
    canvas.innerHTML = interactiveSlideMarkup(question);
    scheduleSlideTextFit();
  }

  function contentSlideMarkup(question) {
    const layout = question.config?.layout || "title";
    const boxes = ensureTextBoxes(question);
    const showQr = Boolean(question.config?.show_qr || layout === "qr");
    const joinCard = showQr ? joinCardMarkup() : "";
    const media = question.config?.media_url
      ? `<figure class="slide-media"><img src="${escapeHtml(question.config.media_url)}" alt=""></figure>`
      : "";
    return `
      <div class="slide-canvas-inner content-layout-${escapeHtml(layout)}">
        <div class="slide-type-row">
          <span>${escapeHtml(labelForType(question.type))}</span>
          <strong>${escapeHtml(layoutLabel(layout))}</strong>
        </div>
        <div class="slide-text-layer">
          ${boxes.map((box) => textBoxMarkup(box)).join("")}
        </div>
        ${media}
        ${joinCard}
        ${resultsStageMarkup(true)}
      </div>
    `;
  }

  function textBoxMarkup(box) {
    const selected = box.id === state.selectedTextBoxId ? " is-selected" : "";
    return `
      <div class="slide-text-box${selected}" data-text-box-id="${escapeAttr(box.id)}" data-auto-fit="${box.auto_fit ? "true" : "false"}" style="${textBoxStyle(box)}">
        <div class="slide-text-content" contenteditable="true" spellcheck="true" data-text-box-content>${escapeHtml(box.text)}</div>
        <button type="button" class="slide-text-move" data-text-move-handle aria-label="Mover cuadro"></button>
        <button type="button" class="slide-text-resize handle-nw" data-resize-handle="nw" aria-label="Redimensionar"></button>
        <button type="button" class="slide-text-resize handle-ne" data-resize-handle="ne" aria-label="Redimensionar"></button>
        <button type="button" class="slide-text-resize handle-sw" data-resize-handle="sw" aria-label="Redimensionar"></button>
        <button type="button" class="slide-text-resize handle-se" data-resize-handle="se" aria-label="Redimensionar"></button>
      </div>
    `;
  }

  function textBoxStyle(box) {
    return [
      `left:${box.x}%`,
      `top:${box.y}%`,
      `width:${box.w}%`,
      `height:${box.h}%`,
      `z-index:${box.z}`,
      `font-size:${box.font_size}px`,
      `font-weight:${box.font_weight}`,
      `color:${box.color}`,
      `background:${box.background}`,
      `text-align:${box.align}`,
    ].join(";");
  }

  function interactiveSlideMarkup(question) {
    const blocks = ensureLayoutBlocks(question);
    return `
      <div class="slide-canvas-inner interactive-layout">
        <div class="slide-type-row">
          <span>${escapeHtml(labelForType(question.type))}</span>
          <strong>${question.is_open ? "Voto abierto" : "Voto cerrado"}</strong>
        </div>
        ${layoutBlockMarkup("question", blocks.question, `
          <h2 contenteditable="true" spellcheck="false" data-edit-field="title">${escapeHtml(question.title)}</h2>
          <p class="slide-prompt" contenteditable="true" spellcheck="true" data-edit-field="prompt">${escapeHtml(question.prompt)}</p>
        `)}
        ${layoutBlockMarkup("activity", blocks.activity, visualEditorFor(question))}
        ${layoutBlockMarkup("results", blocks.results, resultsStageMarkup(false))}
      </div>
    `;
  }

  function layoutBlockMarkup(id, block, content) {
    const selected = id === state.selectedLayoutBlockId ? " is-selected" : "";
    return `
      <section class="slide-layout-block slide-layout-block-${escapeAttr(id)}${selected}" data-layout-block-id="${escapeAttr(id)}" style="${layoutBlockStyle(block)}">
        <button type="button" class="slide-block-move" data-block-move-handle aria-label="Mover bloque"></button>
        <div class="slide-layout-block-content" data-layout-block-content>${content}</div>
        <button type="button" class="slide-block-resize handle-nw" data-block-resize-handle="nw" aria-label="Redimensionar bloque"></button>
        <button type="button" class="slide-block-resize handle-ne" data-block-resize-handle="ne" aria-label="Redimensionar bloque"></button>
        <button type="button" class="slide-block-resize handle-sw" data-block-resize-handle="sw" aria-label="Redimensionar bloque"></button>
        <button type="button" class="slide-block-resize handle-se" data-block-resize-handle="se" aria-label="Redimensionar bloque"></button>
      </section>
    `;
  }

  function layoutBlockStyle(block) {
    return [
      `left:${block.x}%`,
      `top:${block.y}%`,
      `width:${block.w}%`,
      `height:${block.h}%`,
      `z-index:${block.z}`,
    ].join(";");
  }

  function resultsStageMarkup(hidden) {
    return `
      <section class="slide-results-stage" data-slide-results-stage aria-label="Resultados en vivo"${hidden ? " hidden" : ""}>
        <div class="results-head">
          <strong>Resultados en vivo</strong>
          <span data-result-summary></span>
        </div>
        <div class="slide-results-body">
          <canvas class="result-chart" data-result-chart hidden></canvas>
          <div class="result-alt" data-result-alt></div>
        </div>
      </section>
    `;
  }

  function visualEditorFor(question) {
    if (["multiple_choice", "quiz", "ranking"].includes(question.type)) {
      const cards = (question.options || []).map((option, index) => {
        const correct = option.is_correct ? " is-correct" : "";
        return `
          <div class="option-card${correct}" data-option-index="${index}">
            <span class="option-order">${index + 1}</span>
            <span class="option-label" contenteditable="true" spellcheck="true">${escapeHtml(option.label)}</span>
            ${question.type === "quiz" ? `<button type="button" data-canvas-action="toggle-correct" data-option-index="${index}">Correcta</button>` : ""}
            <button type="button" data-canvas-action="remove-option" data-option-index="${index}" aria-label="Eliminar opción">x</button>
          </div>
        `;
      }).join("");
      return `
        <div class="option-grid ${question.type === "ranking" ? "ranking-preview" : ""}">
          ${cards}
          <button type="button" class="add-option-card" data-canvas-action="add-option">+ Agregar opción</button>
        </div>
      `;
    }
    if (question.type === "scale") {
      const min = Number(question.config?.min || 1);
      const max = Number(question.config?.max || 5);
      const ticks = [];
      for (let value = min; value <= max; value += 1) {
        ticks.push(`<span>${value}</span>`);
      }
      return `<div class="scale-preview">${ticks.join("")}</div>`;
    }
    if (question.type === "word_cloud") {
      return `
        <div class="live-placeholder word-placeholder">
          <strong>Nube de palabras</strong>
          <span>Las respuestas apareceran como conceptos agrupados.</span>
        </div>
      `;
    }
    if (question.type === "open_text") {
      return `
        <div class="live-placeholder cards-placeholder">
          <strong>Tarjetas abiertas</strong>
          <span>Las participaciones se mostraran en una cuadricula moderable.</span>
        </div>
      `;
    }
    return "";
  }

  function renderInspector() {
    if (!inspector || !state.session) return;
    const question = selectedQuestion();
    if (!question) {
      inspector.innerHTML = `<p class="muted">Agrega una diapositiva para editar propiedades.</p>`;
      return;
    }

    const templateButtons = (state.templates || []).slice(0, 8).map((template, index) => (
      `<button type="button" class="inspector-chip" data-template-index="${index}">${escapeHtml(template.name)}</button>`
    )).join("");

    inspector.innerHTML = `
      <section class="inspector-section">
        <p class="inspector-kicker">Diapositiva ${slideIndex(question.id) + 1}</p>
        <h3>${escapeHtml(question.title)}</h3>
        <label>Tipo
          <select data-inspector-type>
            ${typeOptions(question.type)}
          </select>
        </label>
      </section>

      ${typeSpecificInspector(question)}
      ${resultPresentationInspector(question)}
      ${layoutBlockInspectorMarkup(question)}

      <section class="inspector-section">
        <h3>Presentación</h3>
        <label>Tema
          <select data-session-theme>
            <option value="civic"${state.session.theme === "civic" ? " selected" : ""}>Institucional</option>
            <option value="ocean"${state.session.theme === "ocean" ? " selected" : ""}>Claro azul</option>
            <option value="contrast"${state.session.theme === "contrast" ? " selected" : ""}>Alto contraste</option>
          </select>
        </label>
        <div class="inspector-actions">
          <button type="button" data-inspector-action="go">Mostrar slide</button>
          <button type="button" data-inspector-action="toggle-open">${question.is_open ? "Cerrar voto" : "Abrir voto"}</button>
          <button type="button" data-inspector-action="duplicate">Duplicar</button>
          <button type="button" class="danger" data-inspector-action="delete">Eliminar</button>
        </div>
      </section>

      <section class="inspector-section">
        <h3>Insertar desde plantillas</h3>
        <div class="template-buttons">${templateButtons || "<p class=\"muted\">Cargando plantillas...</p>"}</div>
      </section>
    `;
  }

  function typeSpecificInspector(question) {
    if (question.type === "content_slide") {
      const layout = question.config?.layout || "title";
      const selectedBox = selectedTextBox(question);
      return `
        <section class="inspector-section">
          <h3>Contenido</h3>
          <button type="button" class="wide-action" data-text-box-action="add">Añadir texto</button>
          <label>Layout
            <select data-config-key="layout" data-rerender="true">
              <option value="title"${layout === "title" ? " selected" : ""}>Portada</option>
              <option value="text"${layout === "text" ? " selected" : ""}>Texto</option>
              <option value="instructions"${layout === "instructions" ? " selected" : ""}>Instrucciones</option>
              <option value="qr"${layout === "qr" ? " selected" : ""}>QR de acceso</option>
            </select>
          </label>
          <label>URL de imagen
            <input data-config-key="media_url" value="${escapeAttr(question.config?.media_url || "")}" maxlength="800" placeholder="https://...">
          </label>
          <label class="check-row">
            <input type="checkbox" data-config-key="show_qr" data-rerender="true"${question.config?.show_qr ? " checked" : ""}>
            Mostrar QR
          </label>
        </section>
        ${textBoxInspectorMarkup(question, selectedBox)}
      `;
    }
    if (["word_cloud", "open_text"].includes(question.type)) {
      const moderation = question.config?.moderation || "none";
      return `
        <section class="inspector-section">
          <h3>Moderación</h3>
          <label>Revisión
            <select data-config-key="moderation">
              <option value="none"${moderation === "none" ? " selected" : ""}>Publicar inmediato</option>
              <option value="manual"${moderation === "manual" ? " selected" : ""}>Revisión manual</option>
            </select>
          </label>
        </section>
      `;
    }
    if (question.type === "scale") {
      return `
        <section class="inspector-section">
          <h3>Escala</h3>
          <div class="two-columns">
            <label>Mínimo
              <input type="number" min="1" max="9" data-config-key="min" data-rerender="true" value="${Number(question.config?.min || 1)}">
            </label>
            <label>Máximo
              <input type="number" min="2" max="10" data-config-key="max" data-rerender="true" value="${Number(question.config?.max || 5)}">
            </label>
          </div>
        </section>
      `;
    }
    if (question.type === "quiz") {
      return `
        <section class="inspector-section">
          <h3>Quiz</h3>
          <div class="two-columns">
            <label>Timer
              <input type="number" min="5" max="600" data-config-key="timer_seconds" value="${Number(question.config?.timer_seconds || 30)}">
            </label>
            <label>Puntos
              <input type="number" min="1" max="1000" data-config-key="points" value="${Number(question.config?.points || 100)}">
            </label>
          </div>
        </section>
      `;
    }
    return `
      <section class="inspector-section">
        <h3>Opciones</h3>
        <p class="muted">Edita las opciones directamente en el lienzo central.</p>
      </section>
    `;
  }

  function resultPresentationInspector(question) {
    if (question.type === "content_slide") return "";
    const layout = question.config?.result_layout || defaultResultLayout(question.type);
    return `
      <section class="inspector-section">
        <h3>Resultados</h3>
        <label class="check-row">
          <input type="checkbox" data-config-key="show_results" data-rerender="true"${question.config?.show_results === false ? "" : " checked"}>
          Revelar resultados
        </label>
        <label>Vista
          <select data-config-key="result_layout" data-rerender="true">
            ${resultLayoutOptions(layout)}
          </select>
        </label>
      </section>
      ${["word_cloud", "open_text"].includes(question.type) ? '<section class="inspector-section moderation-panel" data-moderation-panel hidden></section>' : ""}
    `;
  }

  function layoutBlockInspectorMarkup(question) {
    if (question.type === "content_slide") return "";
    const blocks = ensureLayoutBlocks(question);
    const selectedId = state.selectedLayoutBlockId && blocks[state.selectedLayoutBlockId] ? state.selectedLayoutBlockId : "question";
    const block = blocks[selectedId] || blocks.question;
    const labels = {
      question: "Pregunta",
      activity: "Dinámica",
      results: "Resultados",
    };
    return `
      <section class="inspector-section layout-block-panel">
        <h3>Diseño</h3>
        <label>Bloque
          <select data-layout-block-select>
            ${LAYOUT_BLOCK_IDS.map((id) => `<option value="${id}"${id === selectedId ? " selected" : ""}>${labels[id]}</option>`).join("")}
          </select>
        </label>
        <div class="two-columns">
          <label>X
            <input type="number" min="0" max="100" step="0.5" data-layout-block-key="x" value="${Number(block.x || 0)}">
          </label>
          <label>Y
            <input type="number" min="0" max="100" step="0.5" data-layout-block-key="y" value="${Number(block.y || 0)}">
          </label>
          <label>Ancho
            <input type="number" min="12" max="100" step="0.5" data-layout-block-key="w" value="${Number(block.w || 0)}">
          </label>
          <label>Alto
            <input type="number" min="10" max="100" step="0.5" data-layout-block-key="h" value="${Number(block.h || 0)}">
          </label>
        </div>
        <button type="button" class="wide-action" data-layout-block-action="reset">Restablecer layout</button>
      </section>
    `;
  }

  function textBoxInspectorMarkup(question, box) {
    const totalBoxes = ensureTextBoxes(question).length;
    if (!box) {
      return `
        <section class="inspector-section text-box-panel">
          <h3>Texto seleccionado</h3>
          <p class="muted">Selecciona un cuadro del lienzo para ajustar tamaño, color y alineación.</p>
        </section>
      `;
    }
    const swatches = ["#17212f", "#334155", "#2563eb", "#647c3d", "#b45309", "#ffffff"];
    return `
      <section class="inspector-section text-box-panel">
        <h3>Texto seleccionado</h3>
        <label>Tamaño
          <div class="range-row">
            <input type="range" min="12" max="120" data-text-style-key="font_size" value="${Number(box.font_size || 32)}">
            <input type="number" min="12" max="120" data-text-style-key="font_size" value="${Number(box.font_size || 32)}">
          </div>
        </label>
        <label class="check-row">
          <input type="checkbox" data-text-style-key="font_weight"${Number(box.font_weight || 400) >= 600 ? " checked" : ""}>
          Negritas
        </label>
        <div class="style-row">
          <span>Color</span>
          <div class="swatch-row">
            ${swatches.map((color) => `<button type="button" class="color-swatch${box.color === color ? " is-active" : ""}" data-text-color="${color}" style="background:${color}" aria-label="Color ${color}"></button>`).join("")}
            <input type="color" data-text-style-key="color" value="${escapeAttr(box.color || "#17212f")}">
          </div>
        </div>
        <div class="style-row">
          <span>Fondo</span>
          <div class="swatch-row">
            <button type="button" class="color-swatch transparent-swatch${box.background === "transparent" ? " is-active" : ""}" data-text-color="transparent" data-text-color-target="background" aria-label="Fondo transparente"></button>
            <input type="color" data-text-style-key="background" value="${escapeAttr(box.background === "transparent" ? "#ffffff" : box.background)}">
          </div>
        </div>
        <div class="style-row">
          <span>Alineación</span>
          <div class="segmented-controls">
            ${["left", "center", "right"].map((align) => `<button type="button" class="${box.align === align ? "is-active" : ""}" data-text-align="${align}">${alignLabel(align)}</button>`).join("")}
          </div>
        </div>
        <label class="check-row">
          <input type="checkbox" data-text-style-key="auto_fit"${box.auto_fit ? " checked" : ""}>
          Autoajustar fuente
        </label>
        <div class="inspector-actions">
          <button type="button" data-text-box-action="duplicate">Duplicar cuadro</button>
          <button type="button" class="danger" data-text-box-action="delete"${totalBoxes <= 1 ? " disabled" : ""}>Eliminar cuadro</button>
        </div>
      </section>
    `;
  }

  function resultNodes() {
    const root = canvas || document;
    return {
      stage: $("[data-slide-results-stage]", root),
      summaryNode: $("[data-result-summary]", root),
      chartCanvas: $("[data-result-chart]", root),
      altNode: $("[data-result-alt]", root),
    };
  }

  function moderationPanelNode() {
    return $("[data-moderation-panel]");
  }

  function insightsBoxNode() {
    return $("[data-insights-box]");
  }

  function renderResults() {
    if (!state.session) return;
    const question = selectedQuestion();
    const results = question?.results;
    const { stage, summaryNode, altNode } = resultNodes();
    if (summaryNode) summaryNode.textContent = question ? `${labelForType(question.type)} - ${results?.total || 0} respuestas` : "";
    if (altNode) altNode.innerHTML = "";
    const moderationPanel = moderationPanelNode();
    if (moderationPanel) {
      moderationPanel.innerHTML = "";
      moderationPanel.hidden = true;
    }
    hideChart();
    if (!stage || !question || !results) return;

    if (question.type === "content_slide") {
      stage.hidden = true;
      return;
    }

    stage.hidden = false;
    renderModeration(question);

    if (question.config?.show_results === false) {
      if (altNode) altNode.innerHTML = `<p class="muted">Resultados ocultos para esta diapositiva.</p>`;
      return;
    }
    if (question.type === "multiple_choice" || question.type === "quiz") {
      renderBarChart(
        results.options.map((item) => item.label),
        results.options.map((item) => item.count),
        question.type === "quiz" ? "Respuestas de quiz" : "Votos",
      );
      if (question.type === "quiz" && results.leaderboard?.length) renderLeaderboard(results.leaderboard);
      return;
    }
    if (question.type === "scale") {
      renderBarChart(
        results.values.map((item) => String(item.value)),
        results.values.map((item) => item.count),
        `Promedio ${results.average || 0}`,
      );
      return;
    }
    if (question.type === "ranking") {
      renderBarChart(
        results.options.map((item) => item.label),
        results.options.map((item) => item.score),
        "Puntaje ranking",
      );
      return;
    }
    if (question.type === "word_cloud") {
      renderWordResults(results.words || []);
      return;
    }
    if (question.type === "open_text") {
      renderOpenText(results.cards || []);
    }
  }

  function renderModeration(question) {
    const moderationPanel = moderationPanelNode();
    if (!moderationPanel || !question.pending_responses?.length) return;
    moderationPanel.hidden = false;
    moderationPanel.innerHTML = `
      <strong>Pendientes de moderación</strong>
      ${question.pending_responses.map((response) => `
        <div class="moderation-item">
          <span>${escapeHtml(response.text)}</span>
          <button type="button" data-moderate="approve" data-response-id="${response.id}">Aprobar</button>
          <button type="button" class="danger" data-moderate="reject" data-response-id="${response.id}">Rechazar</button>
        </div>
      `).join("")}
    `;
  }

  function renderInsights() {
    const insightsBox = insightsBoxNode();
    if (!insightsBox || !state.session) return;
    insightsBox.hidden = true;
  }

  async function addSlide(type, layout) {
    if (!state.session) return;
    const payload = defaultSlidePayload(type, layout);
    const json = await postJson(`/api/sessions/${state.session.code}/questions`, payload);
    if (!json.ok) {
      alert(json.error || "No se pudo agregar la diapositiva.");
      return;
    }
    state.session = json.session;
    state.selectedQuestionId = json.question.id;
    render();
    await controlSession("go_to_slide", { index: slideIndex(json.question.id) }, false);
  }

  async function createFromTemplate(template) {
    if (!state.session) return;
    const json = await postJson(`/api/sessions/${state.session.code}/questions`, template.payload);
    if (!json.ok) {
      alert(json.error || "No se pudo insertar la plantilla.");
      return;
    }
    state.session = json.session;
    state.selectedQuestionId = json.question.id;
    render();
    await controlSession("go_to_slide", { index: slideIndex(json.question.id) }, false);
  }

  async function patchSession(payload) {
    if (!state.session) return;
    const json = await patchJson(`/api/sessions/${state.session.code}`, payload);
    if (!json.ok) {
      setSaveState("Error al guardar");
      alert(json.error || "No se pudo guardar la presentación.");
      return;
    }
    state.session = json.session;
    renderChrome();
    renderSlideList();
    setSaveState("Guardado");
  }

  function updateLocalQuestionFromCanvas() {
    const question = selectedQuestion();
    if (!question || !canvas) return;
    const payload = collectCanvasPayload(question);
    mergeQuestionPayload(question, payload);
    renderSlideList();
  }

  function scheduleQuestionSave(options = {}) {
    const question = selectedQuestion();
    if (!question) return;
    const payload = collectCanvasPayload(question);
    if (!payloadIsReady(payload)) {
      setSaveState("Completa la diapositiva");
      return;
    }
    const saveKey = JSON.stringify(payload);
    if (saveKey === state.lastSaveKey) return;
    setSaveState("Guardando...");
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(() => saveQuestion(payload, options), 500);
  }

  function flushQuestionSave() {
    if (!state.saveTimer) return;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = null;
    const question = selectedQuestion();
    if (!question) return;
    const payload = collectCanvasPayload(question);
    if (payloadIsReady(payload)) saveQuestion(payload, { rerender: false });
  }

  async function saveQuestion(payload, options = {}) {
    const question = selectedQuestion();
    if (!state.session || !question) return;
    const saveKey = JSON.stringify(payload);
    state.lastSaveKey = saveKey;
    const json = await patchJson(`/api/sessions/${state.session.code}/questions/${question.id}`, payload);
    if (!json.ok) {
      setSaveState("Error al guardar");
      return;
    }
    state.session = json.session;
    state.selectedQuestionId = json.question.id;
    if (options.rerender && !isEditing()) renderCanvas();
    renderChrome();
    renderSlideList();
    renderInspector();
    renderResults();
    scheduleSlideTextFit();
    setSaveState("Guardado");
  }

  function collectCanvasPayload(question) {
    const config = { ...(question.config || {}) };
    if (question.type === "content_slide") {
      const boxes = collectTextBoxesFromCanvas(question);
      config.text_boxes = boxes;
      config.body = bodyFromTextBoxes(boxes, config.body || "");
      const title = titleFromTextBoxes(boxes, question.title);
      return payloadForQuestion(question, { title, prompt: "", config, options: [], correct_option_labels: [] });
    }
    const title = textValue("[data-edit-field='title']", canvas) || question.title;
    const prompt = textValue("[data-edit-field='prompt']", canvas);
    config.result_placement = "slide";
    config.show_results = config.show_results !== false;
    config.result_layout = config.result_layout || defaultResultLayout(question.type);
    config.layout_blocks = collectLayoutBlocksFromCanvas(question);
    const options = $$(".option-label", canvas).map((node) => node.textContent.trim()).filter(Boolean);
    const correct = $$(".option-card.is-correct .option-label", canvas).map((node) => node.textContent.trim()).filter(Boolean);
    return payloadForQuestion(question, { title, prompt, config, options, correct_option_labels: correct });
  }

  function payloadForQuestion(question, overrides = {}) {
    return {
      type: overrides.type || question.type,
      title: overrides.title ?? question.title,
      prompt: overrides.prompt ?? question.prompt,
      config: overrides.config || { ...(question.config || {}) },
      options: overrides.options ?? (question.options || []).map((option) => option.label),
      correct_option_labels: overrides.correct_option_labels ?? (question.options || [])
        .filter((option) => option.is_correct)
        .map((option) => option.label),
    };
  }

  function mergeQuestionPayload(question, payload) {
    question.type = payload.type;
    question.title = payload.title;
    question.prompt = payload.prompt;
    question.config = payload.config || {};
    const correct = new Set(payload.correct_option_labels || []);
    question.options = (payload.options || []).map((label, index) => ({
      id: question.options?.[index]?.id || `tmp-${index}`,
      label,
      position: index + 1,
      is_correct: correct.has(label),
    }));
  }

  function payloadIsReady(payload) {
    if (!payload.title?.trim()) return false;
    if (payload.type !== "content_slide" && !payload.prompt?.trim()) return false;
    if (["multiple_choice", "ranking", "quiz"].includes(payload.type) && (payload.options || []).length < 2) return false;
    if (payload.type === "quiz" && !(payload.correct_option_labels || []).length) return false;
    return true;
  }

  function ensureLayoutBlocks(question, options = {}) {
    if (!question || question.type === "content_slide") return {};
    question.config = question.config || {};
    const source = question.config.layout_blocks && typeof question.config.layout_blocks === "object"
      ? question.config.layout_blocks
      : {};
    const blocks = {};
    LAYOUT_BLOCK_IDS.forEach((id, index) => {
      blocks[id] = normalizeLayoutBlock({ ...DEFAULT_LAYOUT_BLOCKS[id], ...(source[id] || {}) }, id, index);
    });
    question.config.layout_blocks = blocks;
    const hasSelected = Boolean(state.selectedLayoutBlockId && blocks[state.selectedLayoutBlockId]);
    if (!hasSelected) state.selectedLayoutBlockId = options.selectFallback ? "question" : null;
    return blocks;
  }

  function normalizeLayoutBlock(block, id, index = 0) {
    const width = clampNumber(block.w, 12, 100, DEFAULT_LAYOUT_BLOCKS[id]?.w || 40);
    const height = clampNumber(block.h, 10, 100, DEFAULT_LAYOUT_BLOCKS[id]?.h || 35);
    return {
      id,
      x: roundPercent(clampNumber(block.x, 0, Math.max(0, 100 - width), DEFAULT_LAYOUT_BLOCKS[id]?.x || 0)),
      y: roundPercent(clampNumber(block.y, 0, Math.max(0, 100 - height), DEFAULT_LAYOUT_BLOCKS[id]?.y || 0)),
      w: roundPercent(width),
      h: roundPercent(height),
      z: Math.round(clampNumber(block.z, 0, 100, index + 1)),
    };
  }

  function collectLayoutBlocksFromCanvas(question) {
    const blocks = ensureLayoutBlocks(question);
    $$(".slide-layout-block", canvas).forEach((node, index) => {
      const id = node.dataset.layoutBlockId;
      if (!LAYOUT_BLOCK_IDS.includes(id)) return;
      blocks[id] = normalizeLayoutBlock(blocks[id], id, index);
    });
    question.config.layout_blocks = blocks;
    return blocks;
  }

  function selectedLayoutBlock(question) {
    if (!question || question.type === "content_slide" || !state.selectedLayoutBlockId) return null;
    return ensureLayoutBlocks(question)[state.selectedLayoutBlockId] || null;
  }

  function selectLayoutBlock(id) {
    const question = selectedQuestion();
    if (!question || question.type === "content_slide") return;
    const blocks = ensureLayoutBlocks(question);
    state.selectedLayoutBlockId = id && blocks[id] ? id : null;
    syncLayoutBlockSelection();
    renderInspector();
  }

  function syncLayoutBlockSelection() {
    if (!canvas) return;
    $$(".slide-layout-block", canvas).forEach((node) => {
      node.classList.toggle("is-selected", node.dataset.layoutBlockId === state.selectedLayoutBlockId);
    });
  }

  function applyLayoutBlockDom(block) {
    if (!canvas) return;
    const node = $$(".slide-layout-block", canvas).find((item) => item.dataset.layoutBlockId === block.id);
    if (!node) return;
    node.style.cssText = layoutBlockStyle(block);
    scheduleSlideTextFit();
    if (block.id === "results" && state.chart) {
      window.requestAnimationFrame(() => state.chart?.resize?.());
    }
  }

  function updateSelectedLayoutBlock(question, patch, options = {}) {
    const blocks = ensureLayoutBlocks(question);
    const id = state.selectedLayoutBlockId;
    if (!id || !blocks[id]) return;
    const index = LAYOUT_BLOCK_IDS.indexOf(id);
    const next = normalizeLayoutBlock({ ...blocks[id], ...patch }, id, index);
    question.config.layout_blocks[id] = next;
    applyLayoutBlockDom(next);
    if (options.renderInspector) renderInspector();
    if (options.save !== false) scheduleQuestionSave({ rerender: false });
  }

  function resetLayoutBlocks(question) {
    if (!question || question.type === "content_slide") return;
    question.config = { ...(question.config || {}), layout_blocks: {} };
    ensureLayoutBlocks(question, { selectFallback: true });
    renderCanvas();
    renderInspector();
    renderResults();
    scheduleSlideTextFit();
    scheduleQuestionSave({ rerender: false });
  }

  function scheduleSlideTextFit() {
    if (!canvas || typeof window.requestAnimationFrame !== "function") return;
    if (state.fitTimer) window.cancelAnimationFrame(state.fitTimer);
    state.fitTimer = window.requestAnimationFrame(() => {
      state.fitTimer = null;
      fitSlideText();
    });
  }

  function fitSlideText() {
    if (!canvas || !canvas.isConnected) return;
    fitContentTextBoxes();
    fitQuestionBlockText();
    fitActivityBlockText();
    fitResultsText();
  }

  function fitContentTextBoxes() {
    $$(".slide-text-box", canvas).forEach((box) => {
      const content = $("[data-text-box-content]", box);
      if (!content) return;
      const baseSize = parseFloat(box.style.fontSize || window.getComputedStyle(box).fontSize) || 32;
      resetFitStyles([content]);
      if (box.dataset.autoFit === "false") {
        content.classList.toggle("is-overflowing", elementOverflows(content));
        return;
      }
      fitSingleTextNode(content, { max: baseSize, min: 6 });
    });
  }

  function fitQuestionBlockText() {
    const block = $(".slide-layout-block-question [data-layout-block-content]", canvas);
    if (!block) return;
    const nodes = [block.querySelector("h2"), block.querySelector(".slide-prompt")].filter(Boolean);
    fitTextGroup(block, nodes, { minScale: 0.18, minFont: 8 });
  }

  function fitActivityBlockText() {
    const block = $(".slide-layout-block-activity [data-layout-block-content]", canvas);
    if (!block) return;
    block.classList.remove("is-overflowing");
    const optionGrid = $(".option-grid", block);
    if (optionGrid) {
      optionGrid.classList.remove("is-compact", "is-overflowing");
      const labels = $$(".option-label", optionGrid);
      labels.forEach((label) => fitSingleTextNode(label, { min: 9 }));
      if (elementOverflows(block) || elementOverflows(optionGrid)) {
        optionGrid.classList.add("is-compact");
        fitTextGroup(block, labels, { minScale: 0.18, minFont: 7 });
      }
      block.classList.toggle("is-overflowing", elementOverflows(block) || elementOverflows(optionGrid));
      optionGrid.classList.toggle("is-overflowing", elementOverflows(optionGrid));
      return;
    }
    const scalePreview = $(".scale-preview", block);
    if (scalePreview) {
      fitTextGroup(block, $$("span", scalePreview), { minScale: 0.5, minFont: 10 });
      block.classList.toggle("is-overflowing", elementOverflows(block));
      return;
    }
    const placeholder = $(".live-placeholder", block);
    if (placeholder) {
      fitTextGroup(block, $$("strong, span", placeholder), { minScale: 0.45, minFont: 10 });
      block.classList.toggle("is-overflowing", elementOverflows(block));
    }
  }

  function fitResultsText() {
    const stage = $("[data-slide-results-stage]", canvas);
    if (!stage || stage.hidden) return;
    const headNodes = $$(".results-head strong, .results-head span", stage);
    fitTextGroup($(".results-head", stage) || stage, headNodes, { minScale: 0.62, minFont: 9 });
    $$(".response-card-grid article", stage).forEach((card) => fitSingleTextNode(card, { min: 9 }));
    fitTextGroup($(".word-cloud-preview", stage), $$(".word-cloud-preview span", stage), { minScale: 0.55, minFont: 8 });
    fitTextGroup($(".leaderboard-panel", stage), $$(".leaderboard-panel strong, .leaderboard-panel span, .leaderboard-panel b", stage), { minScale: 0.65, minFont: 9 });
  }

  function fitSingleTextNode(node, options = {}) {
    if (!node || node.clientWidth <= 0 || node.clientHeight <= 0) return;
    const computed = window.getComputedStyle(node);
    const max = Math.min(options.max || parseFloat(computed.fontSize) || 16, 160);
    const min = Math.min(max, options.min || 9);
    node.style.fontSize = `${max}px`;
    node.classList.remove("is-overflowing");
    if (!elementOverflows(node)) return;
    let low = min;
    let high = max;
    for (let step = 0; step < 8; step += 1) {
      const mid = (low + high) / 2;
      node.style.fontSize = `${mid}px`;
      if (elementOverflows(node)) high = mid;
      else low = mid;
    }
    node.style.fontSize = `${Math.max(min, low).toFixed(2)}px`;
    node.classList.toggle("is-overflowing", elementOverflows(node));
  }

  function fitTextGroup(container, nodes, options = {}) {
    if (!container || !nodes?.length || container.clientWidth <= 0 || container.clientHeight <= 0) return;
    resetFitStyles(nodes);
    container.classList.remove("is-overflowing");
    const bases = nodes.map((node) => parseFloat(window.getComputedStyle(node).fontSize) || 16);
    if (!groupOverflows(container, nodes)) return;
    const minScale = options.minScale || 0.4;
    const minFont = options.minFont || 9;
    let low = minScale;
    let high = 1;
    for (let step = 0; step < 8; step += 1) {
      const scale = (low + high) / 2;
      nodes.forEach((node, index) => {
        node.style.fontSize = `${Math.max(minFont, bases[index] * scale).toFixed(2)}px`;
      });
      if (groupOverflows(container, nodes)) high = scale;
      else low = scale;
    }
    nodes.forEach((node, index) => {
      node.style.fontSize = `${Math.max(minFont, bases[index] * low).toFixed(2)}px`;
      node.classList.toggle("is-overflowing", elementOverflows(node));
    });
    container.classList.toggle("is-overflowing", groupOverflows(container, nodes));
  }

  function resetFitStyles(nodes) {
    nodes.forEach((node) => {
      node.style.removeProperty("font-size");
      node.classList.remove("is-overflowing");
    });
  }

  function elementOverflows(node) {
    if (!node) return false;
    return node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1;
  }

  function groupOverflows(container, nodes) {
    return elementOverflows(container) || nodes.some((node) => elementOverflows(node));
  }

  function ensureTextBoxes(question, options = {}) {
    question.config = question.config || {};
    const source = Array.isArray(question.config.text_boxes) && question.config.text_boxes.length
      ? question.config.text_boxes
      : defaultTextBoxes(question);
    question.config.text_boxes = source.map((box, index) => normalizeTextBox(box, index, question)).filter(Boolean);
    if (!question.config.text_boxes.length) {
      question.config.text_boxes = defaultTextBoxes(question);
    }
    const hasSelected = question.config.text_boxes.some((box) => box.id === state.selectedTextBoxId);
    if (!hasSelected) state.selectedTextBoxId = options.selectFallback ? question.config.text_boxes[0]?.id || null : null;
    if (options.selectFallback && !state.selectedTextBoxId) {
      state.selectedTextBoxId = question.config.text_boxes[0]?.id || null;
    }
    syncTitleAndBodyFromBoxes(question);
    return question.config.text_boxes;
  }

  function defaultTextBoxes(question) {
    const body = question.config?.body || "";
    const boxes = [
      normalizeTextBox({
        id: "title",
        text: question.title || "Título",
        x: 8,
        y: 14,
        w: 64,
        h: 24,
        font_size: 60,
        font_weight: 800,
        color: "#17212f",
        background: "transparent",
        align: "left",
        auto_fit: true,
        z: 1,
      }, 0, question),
    ];
    if (body) {
      boxes.push(normalizeTextBox({
        id: "body",
        text: body,
        x: 8,
        y: 43,
        w: 62,
        h: 24,
        font_size: 28,
        font_weight: 400,
        color: "#334155",
        background: "transparent",
        align: "left",
        auto_fit: true,
        z: 2,
      }, 1, question));
    }
    return boxes;
  }

  function normalizeTextBox(box, index) {
    const background = box.background === "transparent" ? "transparent" : normalizeHexColor(box.background, "transparent");
    return {
      id: sanitizeTextBoxId(box.id, index),
      text: String(box.text ?? "").trim().slice(0, 1200),
      x: clampNumber(box.x, 0, 100, 8),
      y: clampNumber(box.y, 0, 100, 14),
      w: clampNumber(box.w, 5, 100, 50),
      h: clampNumber(box.h, 5, 100, 16),
      font_size: Math.round(clampNumber(box.font_size, 12, 120, 32)),
      font_weight: Number(box.font_weight || 400) >= 600 ? 800 : 400,
      color: normalizeHexColor(box.color, "#17212f"),
      background,
      align: ["left", "center", "right"].includes(box.align) ? box.align : "left",
      auto_fit: box.auto_fit !== false && box.auto_fit !== "false",
      z: Math.round(clampNumber(box.z, 0, 100, index + 1)),
    };
  }

  function sanitizeTextBoxId(value, index) {
    const text = String(value || "").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
    return text || `box-${Date.now().toString(36)}-${index}`;
  }

  function makeTextBoxId() {
    return `box-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
  }

  function selectedTextBox(question) {
    if (!question || question.type !== "content_slide" || !state.selectedTextBoxId) return null;
    return ensureTextBoxes(question).find((box) => box.id === state.selectedTextBoxId) || null;
  }

  function selectTextBox(id) {
    state.selectedTextBoxId = id || null;
    syncTextBoxSelection();
    renderInspector();
  }

  function syncTextBoxSelection() {
    if (!canvas) return;
    $$(".slide-text-box", canvas).forEach((node) => {
      node.classList.toggle("is-selected", node.dataset.textBoxId === state.selectedTextBoxId);
    });
  }

  function collectTextBoxesFromCanvas(question) {
    const boxes = ensureTextBoxes(question);
    const nodes = $$(".slide-text-box", canvas);
    if (!nodes.length) return boxes;
    return nodes.map((node, index) => {
      const base = boxes.find((box) => box.id === node.dataset.textBoxId) || boxes[index] || {};
      const content = node.querySelector("[data-text-box-content]");
      return normalizeTextBox({ ...base, text: content?.textContent || "" }, index, question);
    });
  }

  function titleFromTextBoxes(boxes, fallback) {
    return boxes.find((box) => box.id === "title" && box.text)?.text
      || boxes.find((box) => box.text)?.text
      || fallback
      || "Diapositiva";
  }

  function bodyFromTextBoxes(boxes, fallback) {
    return boxes.find((box) => box.id === "body" && box.text)?.text
      || boxes.find((box) => box.id !== "title" && box.text)?.text
      || fallback
      || "";
  }

  function syncTitleAndBodyFromBoxes(question) {
    const boxes = question.config?.text_boxes || [];
    question.title = titleFromTextBoxes(boxes, question.title);
    question.config.body = bodyFromTextBoxes(boxes, question.config.body || "");
  }

  function addTextBox(question) {
    const boxes = ensureTextBoxes(question);
    const topZ = Math.max(...boxes.map((box) => Number(box.z || 0)), 0);
    const next = normalizeTextBox({
      id: makeTextBoxId(),
      text: "Nuevo texto",
      x: 14,
      y: 18 + Math.min(boxes.length * 6, 42),
      w: 38,
      h: 14,
      font_size: 32,
      font_weight: 400,
      color: "#17212f",
      background: "transparent",
      align: "left",
      auto_fit: true,
      z: topZ + 1,
    }, boxes.length, question);
    question.config.text_boxes = [...boxes, next];
    state.selectedTextBoxId = next.id;
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function duplicateSelectedTextBox(question) {
    const box = selectedTextBox(question);
    if (!box) return;
    const boxes = ensureTextBoxes(question);
    const clone = normalizeTextBox({
      ...box,
      id: makeTextBoxId(),
      x: Math.min(box.x + 4, 100 - box.w),
      y: Math.min(box.y + 4, 100 - box.h),
      z: Math.max(...boxes.map((item) => Number(item.z || 0)), 0) + 1,
    }, boxes.length, question);
    question.config.text_boxes = [...boxes, clone];
    state.selectedTextBoxId = clone.id;
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function deleteSelectedTextBox(question) {
    const boxes = ensureTextBoxes(question);
    if (!state.selectedTextBoxId || boxes.length <= 1) return;
    const index = boxes.findIndex((box) => box.id === state.selectedTextBoxId);
    question.config.text_boxes = boxes.filter((box) => box.id !== state.selectedTextBoxId);
    state.selectedTextBoxId = question.config.text_boxes[Math.max(index - 1, 0)]?.id || null;
    syncTitleAndBodyFromBoxes(question);
    renderCanvas();
    renderInspector();
    renderSlideList();
    scheduleQuestionSave({ rerender: false });
  }

  function updateSelectedTextBox(question, patch, options = {}) {
    const boxes = ensureTextBoxes(question);
    const index = boxes.findIndex((box) => box.id === state.selectedTextBoxId);
    if (index < 0) return;
    const next = normalizeTextBox({ ...boxes[index], ...patch }, index, question);
    question.config.text_boxes[index] = next;
    syncTitleAndBodyFromBoxes(question);
    applyTextBoxDom(next);
    if (options.renderList !== false) renderSlideList();
    if (options.renderInspector) renderInspector();
    if (options.save !== false) scheduleQuestionSave({ rerender: false });
  }

  function applyTextBoxDom(box) {
    if (!canvas) return;
    const node = $$(".slide-text-box", canvas).find((item) => item.dataset.textBoxId === box.id);
    if (!node) return;
    node.style.cssText = textBoxStyle(box);
    node.dataset.autoFit = box.auto_fit ? "true" : "false";
    scheduleSlideTextFit();
  }

  function handleCanvasPointerDown(event) {
    const question = selectedQuestion();
    if (!question) return;
    if (question.type !== "content_slide") {
      handleLayoutBlockPointerDown(event, question);
      return;
    }
    const node = event.target.closest("[data-text-box-id]");
    if (!node) return;
    state.selectedTextBoxId = node.dataset.textBoxId;
    syncTextBoxSelection();
    renderInspector();
    const handle = event.target.closest("[data-resize-handle]");
    const moveHandle = event.target.closest("[data-text-move-handle]");
    if (!handle && !moveHandle && event.target.closest("[data-text-box-content]")) return;
    const box = selectedTextBox(question);
    if (!box || !canvas) return;
    state.textDrag = {
      id: box.id,
      mode: handle ? "resize" : "move",
      handle: handle?.dataset.resizeHandle || "se",
      startX: event.clientX,
      startY: event.clientY,
      startBox: { ...box },
      rect: canvas.getBoundingClientRect(),
    };
    event.preventDefault();
  }

  function handleLayoutBlockPointerDown(event, question) {
    const node = event.target.closest("[data-layout-block-id]");
    if (!node || !canvas) return;
    const blockId = node.dataset.layoutBlockId;
    if (!LAYOUT_BLOCK_IDS.includes(blockId)) return;
    state.selectedLayoutBlockId = blockId;
    syncLayoutBlockSelection();
    renderInspector();
    const resizeHandle = event.target.closest("[data-block-resize-handle]");
    const moveHandle = event.target.closest("[data-block-move-handle]");
    if (!resizeHandle && !moveHandle) return;
    const block = selectedLayoutBlock(question);
    if (!block) return;
    state.layoutBlockDrag = {
      id: block.id,
      mode: resizeHandle ? "resize" : "move",
      handle: resizeHandle?.dataset.blockResizeHandle || "se",
      startX: event.clientX,
      startY: event.clientY,
      startBlock: { ...block },
      rect: canvas.getBoundingClientRect(),
    };
    event.preventDefault();
  }

  function handleCanvasPointerMove(event) {
    const question = selectedQuestion();
    if (!question) return;
    if (state.layoutBlockDrag && question.type !== "content_slide") {
      const drag = state.layoutBlockDrag;
      const dx = ((event.clientX - drag.startX) / drag.rect.width) * 100;
      const dy = ((event.clientY - drag.startY) / drag.rect.height) * 100;
      const patch = drag.mode === "move"
        ? movedLayoutBlockPatch(drag.startBlock, dx, dy)
        : resizedLayoutBlockPatch(drag.startBlock, drag.handle, dx, dy);
      updateSelectedLayoutBlock(question, patch, { save: false });
      return;
    }
    if (!state.textDrag || question.type !== "content_slide") return;
    const drag = state.textDrag;
    const dx = ((event.clientX - drag.startX) / drag.rect.width) * 100;
    const dy = ((event.clientY - drag.startY) / drag.rect.height) * 100;
    const patch = drag.mode === "move"
      ? movedTextBoxPatch(drag.startBox, dx, dy)
      : resizedTextBoxPatch(drag.startBox, drag.handle, dx, dy);
    updateSelectedTextBox(question, patch, { save: false, renderList: false });
  }

  function finishCanvasDrag() {
    if (state.layoutBlockDrag) {
      state.layoutBlockDrag = null;
      renderInspector();
      scheduleQuestionSave({ rerender: false });
    }
    if (state.textDrag) {
      state.textDrag = null;
      renderInspector();
      scheduleQuestionSave({ rerender: false });
    }
  }

  function movedTextBoxPatch(box, dx, dy) {
    return {
      x: clampNumber(box.x + dx, 0, Math.max(0, 100 - box.w), box.x),
      y: clampNumber(box.y + dy, 0, Math.max(0, 100 - box.h), box.y),
    };
  }

  function resizedTextBoxPatch(box, handle, dx, dy) {
    let x = box.x;
    let y = box.y;
    let w = box.w;
    let h = box.h;
    if (handle.includes("e")) w = box.w + dx;
    if (handle.includes("s")) h = box.h + dy;
    if (handle.includes("w")) {
      x = box.x + dx;
      w = box.w - dx;
    }
    if (handle.includes("n")) {
      y = box.y + dy;
      h = box.h - dy;
    }
    w = clampNumber(w, 5, 100, box.w);
    h = clampNumber(h, 5, 100, box.h);
    x = clampNumber(x, 0, Math.max(0, 100 - w), box.x);
    y = clampNumber(y, 0, Math.max(0, 100 - h), box.y);
    const patch = { x, y, w, h };
    if (box.auto_fit) {
      const scale = Math.max(0.4, Math.min(w / box.w, h / box.h));
      patch.font_size = Math.round(clampNumber(box.font_size * scale, 12, 120, box.font_size));
    }
    return patch;
  }

  function movedLayoutBlockPatch(block, dx, dy) {
    return {
      x: clampNumber(block.x + dx, 0, Math.max(0, 100 - block.w), block.x),
      y: clampNumber(block.y + dy, 0, Math.max(0, 100 - block.h), block.y),
    };
  }

  function resizedLayoutBlockPatch(block, handle, dx, dy) {
    let x = block.x;
    let y = block.y;
    let w = block.w;
    let h = block.h;
    if (handle.includes("e")) w = block.w + dx;
    if (handle.includes("s")) h = block.h + dy;
    if (handle.includes("w")) {
      x = block.x + dx;
      w = block.w - dx;
    }
    if (handle.includes("n")) {
      y = block.y + dy;
      h = block.h - dy;
    }
    w = clampNumber(w, 12, 100, block.w);
    h = clampNumber(h, 10, 100, block.h);
    x = clampNumber(x, 0, Math.max(0, 100 - w), block.x);
    y = clampNumber(y, 0, Math.max(0, 100 - h), block.y);
    return { x, y, w, h };
  }

  function handleDocumentKeydown(event) {
    const question = selectedQuestion();
    if (event.key === "Escape") {
      document.activeElement?.blur?.();
      selectTextBox(null);
      if (question?.type !== "content_slide") selectLayoutBlock(null);
      return;
    }
    if (!question || question.type !== "content_slide") return;
    if (!["Delete", "Backspace"].includes(event.key) || isEditing()) return;
    event.preventDefault();
    deleteSelectedTextBox(question);
  }

  async function handleSlideAction(action, id) {
    if (!state.session) return;
    if (action === "duplicate") {
      await duplicateSlide(id);
      return;
    }
    if (action === "delete") {
      await deleteSlide(id);
    }
  }

  async function handleInspectorAction(action) {
    const question = selectedQuestion();
    if (!question) return;
    if (action === "duplicate") await duplicateSlide(question.id);
    if (action === "delete") await deleteSlide(question.id);
    if (action === "go") selectSlide(question.id, true);
    if (action === "toggle-open") controlSession(question.is_open ? "close_question" : "open_question");
  }

  async function handleModerationButton(button) {
    const question = selectedQuestion();
    if (!button || !question || !state.session) return;
    const responseId = Number(button.dataset.responseId || 0);
    const json = await postJson(
      `/api/sessions/${state.session.code}/questions/${question.id}/responses/${responseId}/moderate`,
      { action: button.dataset.moderate },
    );
    if (!json.ok) {
      alert(json.error || "No se pudo moderar la respuesta.");
      return;
    }
    await loadSession(false);
  }

  function handleTextInspectorButton(button) {
    const question = selectedQuestion();
    if (!question || question.type !== "content_slide") return;
    const action = button.dataset.textBoxAction;
    if (action === "add") {
      addTextBox(question);
      return;
    }
    if (action === "duplicate") {
      duplicateSelectedTextBox(question);
      return;
    }
    if (action === "delete") {
      deleteSelectedTextBox(question);
      return;
    }
    if (button.dataset.textAlign) {
      updateSelectedTextBox(question, { align: button.dataset.textAlign }, { renderInspector: true });
      return;
    }
    if (button.dataset.textColor) {
      const key = button.dataset.textColorTarget || "color";
      updateSelectedTextBox(question, { [key]: button.dataset.textColor }, { renderInspector: true });
    }
  }

  function handleTextStyleInput(target) {
    const question = selectedQuestion();
    if (!question || question.type !== "content_slide") return;
    const key = target.dataset.textStyleKey;
    let value = target instanceof HTMLInputElement && target.type === "checkbox" ? target.checked : target.value;
    const patch = {};
    if (key === "font_size") patch.font_size = clampNumber(value, 12, 120);
    if (key === "font_weight") patch.font_weight = value ? 800 : 400;
    if (key === "color") patch.color = normalizeHexColor(value, "#17212f");
    if (key === "background") patch.background = normalizeHexColor(value, "#ffffff");
    if (key === "auto_fit") patch.auto_fit = Boolean(value);
    updateSelectedTextBox(question, patch, { renderInspector: false });
  }

  function handleLayoutBlockInput(target) {
    const question = selectedQuestion();
    if (!question || question.type === "content_slide") return;
    const key = target.dataset.layoutBlockKey;
    if (!["x", "y", "w", "h"].includes(key)) return;
    if (!state.selectedLayoutBlockId) {
      state.selectedLayoutBlockId = "question";
      syncLayoutBlockSelection();
    }
    updateSelectedLayoutBlock(question, { [key]: Number(target.value || 0) }, { renderInspector: false });
  }

  function handleLayoutBlockButton(button) {
    const question = selectedQuestion();
    if (!question || question.type === "content_slide") return;
    if (button.dataset.layoutBlockAction === "reset") resetLayoutBlocks(question);
  }

  function handleCanvasAction(action, button) {
    const question = selectedQuestion();
    if (!question) return;
    if (action === "add-option") {
      question.options = [...(question.options || []), { id: `tmp-${Date.now()}`, label: `Opción ${(question.options || []).length + 1}`, is_correct: false }];
      renderCanvas();
      scheduleQuestionSave({ rerender: false });
      return;
    }
    const index = Number(button.dataset.optionIndex || -1);
    if (index < 0) return;
    if (action === "remove-option") {
      question.options.splice(index, 1);
      renderCanvas();
      scheduleQuestionSave({ rerender: false });
      return;
    }
    if (action === "toggle-correct") {
      question.options[index].is_correct = !question.options[index].is_correct;
      renderCanvas();
      scheduleQuestionSave({ rerender: false });
    }
  }

  function handleInspectorInput(target, fromChange) {
    const question = selectedQuestion();
    if (!state.session || !question) return;

    if (target.matches("[data-text-style-key]")) {
      handleTextStyleInput(target);
      return;
    }

    if (target.matches("[data-layout-block-select]")) {
      selectLayoutBlock(target.value);
      return;
    }

    if (target.matches("[data-layout-block-key]")) {
      handleLayoutBlockInput(target);
      return;
    }

    if (target.matches("[data-session-theme]")) {
      patchSession({ theme: target.value });
      return;
    }

    if (target.matches("[data-inspector-type]")) {
      changeSlideType(target.value);
      return;
    }

    const key = target.dataset.configKey;
    if (!key) return;
    const value = target instanceof HTMLInputElement && target.type === "checkbox"
      ? target.checked
      : target.value;
    question.config = { ...(question.config || {}), [key]: numericConfigValue(key, value) };
    const shouldRender = target.dataset.rerender === "true";
    if (shouldRender) {
      renderCanvas();
      renderResults();
      scheduleSlideTextFit();
    }
    scheduleQuestionSave({ rerender: fromChange || shouldRender });
  }

  function changeSlideType(type) {
    const question = selectedQuestion();
    if (!question) return;
    const defaults = defaultSlidePayload(type, type === "content_slide" ? "title" : "");
    const payload = {
      ...defaults,
      title: question.title || defaults.title,
      prompt: type === "content_slide" ? "" : (question.prompt || defaults.prompt),
    };
    mergeQuestionPayload(question, payload);
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: true });
  }

  async function duplicateSlide(id) {
    if (!state.session) return;
    const json = await postJson(`/api/sessions/${state.session.code}/questions/${id}/duplicate`, {});
    if (!json.ok) {
      alert(json.error || "No se pudo duplicar.");
      return;
    }
    state.session = json.session;
    state.selectedQuestionId = json.question.id;
    render();
  }

  async function deleteSlide(id) {
    if (!state.session) return;
    if (!confirm("¿Eliminar esta diapositiva?")) return;
    const json = await fetchJson(`/api/sessions/${state.session.code}/questions/${id}`, { method: "DELETE" });
    if (!json.ok) {
      alert(json.error || "No se pudo eliminar.");
      return;
    }
    state.session = json.session;
    state.selectedQuestionId = state.session.active_question_id || state.session.questions?.[0]?.id || null;
    render();
  }

  async function selectSlide(id, updatePresentation) {
    state.selectedQuestionId = id;
    render();
    if (updatePresentation) {
      await controlSession("go_to_slide", { index: slideIndex(id) }, false);
    }
  }

  async function controlSession(action, extra = {}, fullRender = true) {
    if (!state.session) return null;
    const payload = { code: state.session.code, action, ...extra };
    if (state.socket?.connected) {
      return new Promise((resolve) => {
        state.socket.emit("presenter_control", payload, (ack) => {
          if (ack?.ok) {
            state.session = ack.session;
            syncSelectionAfterControl(action);
            if (fullRender) render();
          } else if (ack?.error) {
            alert(ack.error);
          }
          resolve(ack || null);
        });
      });
    }
    const json = await postJson(`/api/sessions/${state.session.code}/control`, { action, ...extra });
    if (json.ok) {
      state.session = json.session;
      syncSelectionAfterControl(action);
      if (fullRender) render();
    } else {
      alert(json.error || "No se pudo controlar la presentación.");
    }
    return json;
  }

  function setupSortable() {
    if (!slideList || !window.Sortable || state.sortable || !state.session) return;
    state.sortable = window.Sortable.create(slideList, {
      animation: 120,
      handle: ".slide-drag",
      onEnd: async () => {
        const ids = $$("[data-question-id]", slideList).map((node) => Number(node.dataset.questionId));
        const json = await postJson(`/api/sessions/${state.session.code}/questions/reorder`, { question_ids: ids });
        if (json.ok) {
          state.session = json.session;
          render();
        }
      },
    });
  }

  function renderBarChart(labels, data, label) {
    const { chartCanvas } = resultNodes();
    if (!chartCanvas || !window.Chart) return;
    chartCanvas.hidden = false;
    if (state.chart) state.chart.destroy();
    state.chart = new window.Chart(chartCanvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label,
          data,
          backgroundColor: "rgba(37, 99, 235, 0.72)",
          borderColor: "rgba(37, 99, 235, 1)",
          borderWidth: 1,
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
          x: { ticks: { color: "#334155" } },
        },
      },
    });
  }

  function renderWordResults(words) {
    const { altNode } = resultNodes();
    if (!altNode) return;
    if (!words.length) {
      altNode.innerHTML = `<p class="muted">Sin palabras todavía.</p>`;
      return;
    }
    const max = Math.max(...words.map((word) => word.count), 1);
    altNode.innerHTML = `
      <div class="word-cloud-preview">
        ${words.slice(0, 60).map((word) => {
          const size = 0.9 + (word.count / max) * 1.8;
          return `<span style="font-size:${size.toFixed(2)}rem">${escapeHtml(word.text)}${word.count > 1 ? ` <small>${word.count}</small>` : ""}</span>`;
        }).join("")}
      </div>
    `;
  }

  function renderOpenText(cards) {
    const { altNode } = resultNodes();
    if (!altNode) return;
    if (!cards.length) {
      altNode.innerHTML = `<p class="muted">Sin respuestas abiertas todavía.</p>`;
      return;
    }
    altNode.innerHTML = `
      <div class="response-card-grid">
        ${cards.map((card) => `<article>${escapeHtml(card.text)}</article>`).join("")}
      </div>
    `;
  }

  function renderLeaderboard(items) {
    const { altNode } = resultNodes();
    if (!altNode) return;
    altNode.innerHTML = `
      <div class="leaderboard-panel">
        <strong>Leaderboard</strong>
        ${items.slice(0, 8).map((item, index) => `
          <div><span>${index + 1}. Participante ${item.participant_id}</span><b>${item.score} pts</b></div>
        `).join("")}
      </div>
    `;
  }

  function hideChart() {
    const { chartCanvas } = resultNodes();
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    if (chartCanvas) chartCanvas.hidden = true;
  }

  function joinCardMarkup() {
    if (!joinCardTemplate) return "";
    return joinCardTemplate.innerHTML;
  }

  function questions() {
    return (state.session?.questions || []).slice().sort((a, b) => a.position - b.position);
  }

  function selectedQuestion() {
    const items = questions();
    return items.find((question) => question.id === state.selectedQuestionId)
      || items.find((question) => question.id === state.session?.active_question_id)
      || items[0]
      || null;
  }

  function ensureSelectedQuestion() {
    if (shouldFollowActiveQuestion() && state.session?.active_question_id) {
      state.selectedQuestionId = state.session.active_question_id;
      return;
    }
    const question = selectedQuestion();
    state.selectedQuestionId = question ? question.id : null;
  }

  function syncSelectionAfterControl(action) {
    if (activeSelectionControlActions.has(action) && state.session?.active_question_id) {
      state.selectedQuestionId = state.session.active_question_id;
      return;
    }
    ensureSelectedQuestion();
  }

  function shouldFollowActiveQuestion() {
    return document.body.classList.contains("present-only");
  }

  function slideIndex(id) {
    return questions().findIndex((question) => question.id === id);
  }

  function normalizeControlAction(action) {
    if (action === "next") return "next_slide";
    if (action === "previous") return "previous_slide";
    return action;
  }

  function typeOptions(current) {
    return [
      ["content_slide", "Contenido"],
      ["multiple_choice", "Opción múltiple"],
      ["word_cloud", "Nube de ideas"],
      ["scale", "Escala"],
      ["open_text", "Respuesta abierta"],
      ["ranking", "Ranking"],
      ["quiz", "Quiz"],
    ].map(([value, label]) => `<option value="${value}"${value === current ? " selected" : ""}>${label}</option>`).join("");
  }

  function defaultResultLayout(type) {
    if (type === "word_cloud") return "cloud";
    if (type === "open_text") return "cards";
    if (type === "quiz") return "leaderboard";
    return "chart";
  }

  function resultConfig(type, overrides = {}) {
    return {
      show_results: true,
      result_layout: defaultResultLayout(type),
      layout_blocks: defaultLayoutBlocks(),
      ...overrides,
      result_placement: "slide",
    };
  }

  function defaultLayoutBlocks() {
    return LAYOUT_BLOCK_IDS.reduce((blocks, id) => {
      blocks[id] = { ...DEFAULT_LAYOUT_BLOCKS[id] };
      return blocks;
    }, {});
  }

  function resultLayoutOptions(current) {
    return [
      ["auto", "Automatica"],
      ["chart", "Grafica"],
      ["list", "Lista"],
      ["grid", "Matriz"],
      ["cloud", "Nube"],
      ["cards", "Tarjetas"],
      ["leaderboard", "Ranking"],
    ].map(([value, label]) => `<option value="${value}"${value === current ? " selected" : ""}>${label}</option>`).join("");
  }

  function defaultSlidePayload(type, layout = "") {
    if (type === "content_slide") {
      const finalLayout = layout || "title";
      if (finalLayout === "qr") {
        return {
          type,
          title: "Participa con tu celular",
          prompt: "",
          config: {
            layout: "qr",
            body: "Escanea el QR o entra con el código de la presentación.",
            show_qr: true,
          },
          options: [],
        };
      }
      return {
        type,
        title: finalLayout === "instructions" ? "Instrucciones" : "Título de la presentación",
        prompt: "",
        config: {
          layout: finalLayout,
          body: finalLayout === "text" ? "Escribe aquí el contenido de la diapositiva." : "Subtítulo o contexto del taller.",
          show_qr: false,
        },
        options: [],
      };
    }
    if (type === "word_cloud") {
      return { type, title: "Lluvia de ideas", prompt: "Escribe una palabra o frase corta.", config: resultConfig(type, { moderation: "none" }), options: [] };
    }
    if (type === "open_text") {
      return { type, title: "Pregunta abierta", prompt: "Comparte tu respuesta.", config: resultConfig(type, { moderation: "none" }), options: [] };
    }
    if (type === "scale") {
      return { type, title: "Escala de opinion", prompt: "Califica del 1 al 5.", config: resultConfig(type, { min: 1, max: 5 }), options: [] };
    }
    if (type === "ranking") {
      return { type, title: "Prioriza opciones", prompt: "Ordena de mayor a menor prioridad.", options: ["Opción 1", "Opción 2", "Opción 3"], config: resultConfig(type) };
    }
    if (type === "quiz") {
      return {
        type,
        title: "Quiz rápido",
        prompt: "Elige la respuesta correcta.",
        options: ["Respuesta A", "Respuesta B", "Respuesta C"],
        correct_option_labels: ["Respuesta A"],
        config: resultConfig(type, { timer_seconds: 30, points: 100 }),
      };
    }
    return { type: "multiple_choice", title: "Pregunta de opción múltiple", prompt: "Elige una opción.", options: ["Opción 1", "Opción 2"], config: resultConfig("multiple_choice") };
  }

  function labelForType(type) {
    return {
      content_slide: "Contenido",
      multiple_choice: "Opción múltiple",
      word_cloud: "Lluvia de ideas",
      scale: "Escala",
      open_text: "Pregunta abierta",
      ranking: "Ranking",
      quiz: "Quiz",
    }[type] || type;
  }

  function layoutLabel(layout) {
    return {
      title: "Portada",
      text: "Texto",
      instructions: "Instrucciones",
      qr: "Código QR",
    }[layout] || "Contenido";
  }

  function alignLabel(align) {
    return {
      left: "Izq.",
      center: "Centro",
      right: "Der.",
    }[align] || align;
  }

  function clampNumber(value, minimum, maximum, fallback = minimum) {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.min(Math.max(number, minimum), maximum);
  }

  function roundPercent(value) {
    return Math.round(Number(value || 0) * 100) / 100;
  }

  function normalizeHexColor(value, fallback) {
    const color = String(value || "").trim();
    return /^#[0-9a-fA-F]{6}$/.test(color) ? color.toLowerCase() : fallback;
  }

  function numericConfigValue(key, value) {
    if (["min", "max", "timer_seconds", "points"].includes(key)) return Number(value || 0);
    return value;
  }

  function textValue(selector, root) {
    return (root.querySelector(selector)?.textContent || "").trim();
  }

  function isEditing() {
    const active = document.activeElement;
    return Boolean(active && (active.closest("[contenteditable='true']") || active.closest("[data-slide-inspector]")));
  }

  function setSaveState(message) {
    if (saveState) saveState.textContent = message;
  }

  async function getJson(url) {
    return fetchJson(url, { method: "GET" });
  }

  async function postJson(url, payload) {
    return fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
  }

  async function patchJson(url, payload) {
    return fetchJson(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
  }

  async function fetchJson(url, options) {
    try {
      const response = await fetch(url, options);
      return await response.json();
    } catch (error) {
      return { ok: false, error: "Error de conexión." };
    }
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }
})();
