(() => {
  const code = window.MENTI_SESSION_CODE;
  const state = {
    session: null,
    templates: [],
    socket: null,
    chart: null,
    sortable: null,
    selectedQuestionId: null,
    saveTimer: null,
    sessionSaveTimer: null,
    lastSaveKey: "",
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

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
  const summaryNode = $("[data-result-summary]");
  const chartCanvas = $("[data-result-chart]");
  const altNode = $("[data-result-alt]");
  const moderationPanel = $("[data-moderation-panel]");
  const insightsBox = $("[data-insights-box]");
  const joinCardTemplate = $("[data-join-card-template]");

  bindGlobalEvents();

  if (code) {
    connectSocket();
    loadTemplates();
    loadSession();
  } else {
    setSaveState("Sin presentacion");
  }

  function bindGlobalEvents() {
    createForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const title = String(new FormData(createForm).get("title") || "").trim();
      const json = await postJson("/api/sessions", { title: title || "Nueva presentacion live" });
      if (json.ok) {
        window.location.assign(`/admin?code=${json.session.code}`);
        return;
      }
      alert(json.error || "No se pudo crear la presentacion.");
    });

    deckTitleInput?.addEventListener("input", () => {
      if (!state.session) return;
      state.session.title = deckTitleInput.value;
      setSaveState("Guardando titulo...");
      window.clearTimeout(state.sessionSaveTimer);
      state.sessionSaveTimer = window.setTimeout(() => {
        patchSession({ title: deckTitleInput.value.trim() || "Presentacion sin titulo" });
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
      scheduleQuestionSave();
    });

    canvas?.addEventListener("blur", (event) => {
      if (!event.target.closest("[contenteditable='true']")) return;
      flushQuestionSave();
    }, true);

    canvas?.addEventListener("click", (event) => {
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
      const button = event.target.closest("button[data-inspector-action], button[data-template-index]");
      if (!button) return;
      if (button.dataset.templateIndex) {
        const template = state.templates[Number(button.dataset.templateIndex)];
        if (template) createFromTemplate(template);
        return;
      }
      handleInspectorAction(button.dataset.inspectorAction);
    });

    moderationPanel?.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-moderate]");
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
    });

    document.addEventListener("click", (event) => {
      if (!addMenu || addMenu.hidden) return;
      if (event.target.closest("[data-add-menu]") || event.target.closest("[data-add-slide]")) return;
      addMenu.hidden = true;
    });
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
      renderResults();
      renderInspector();
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
          <p>Usa el boton Anadir para insertar una portada, pregunta o dinamica.</p>
        </div>
      `;
      return;
    }

    const liveClass = question.id === state.session.active_question_id ? " is-live" : "";
    const closedClass = question.is_open ? "" : " is-closed";
    canvas.className = `slide-canvas slide-kind-${question.type}${liveClass}${closedClass}`;
    if (question.type === "content_slide") {
      canvas.innerHTML = contentSlideMarkup(question);
      return;
    }
    canvas.innerHTML = interactiveSlideMarkup(question);
  }

  function contentSlideMarkup(question) {
    const layout = question.config?.layout || "title";
    const body = question.config?.body || "";
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
        <h2 contenteditable="true" spellcheck="false" data-edit-field="title">${escapeHtml(question.title)}</h2>
        <div class="content-body-edit" contenteditable="true" spellcheck="true" data-config-field="body">${escapeHtml(body)}</div>
        ${media}
        ${joinCard}
      </div>
    `;
  }

  function interactiveSlideMarkup(question) {
    return `
      <div class="slide-canvas-inner interactive-layout">
        <div class="slide-type-row">
          <span>${escapeHtml(labelForType(question.type))}</span>
          <strong>${question.is_open ? "Voto abierto" : "Voto cerrado"}</strong>
        </div>
        <h2 contenteditable="true" spellcheck="false" data-edit-field="title">${escapeHtml(question.title)}</h2>
        <p class="slide-prompt" contenteditable="true" spellcheck="true" data-edit-field="prompt">${escapeHtml(question.prompt)}</p>
        ${visualEditorFor(question)}
      </div>
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
            <button type="button" data-canvas-action="remove-option" data-option-index="${index}" aria-label="Eliminar opcion">x</button>
          </div>
        `;
      }).join("");
      return `
        <div class="option-grid ${question.type === "ranking" ? "ranking-preview" : ""}">
          ${cards}
          <button type="button" class="add-option-card" data-canvas-action="add-option">+ Agregar opcion</button>
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

      <section class="inspector-section">
        <h3>Presentacion</h3>
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
      return `
        <section class="inspector-section">
          <h3>Contenido</h3>
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
      `;
    }
    if (["word_cloud", "open_text"].includes(question.type)) {
      const moderation = question.config?.moderation || "none";
      return `
        <section class="inspector-section">
          <h3>Moderacion</h3>
          <label>Revision
            <select data-config-key="moderation">
              <option value="none"${moderation === "none" ? " selected" : ""}>Publicar inmediato</option>
              <option value="manual"${moderation === "manual" ? " selected" : ""}>Revision manual</option>
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
            <label>Minimo
              <input type="number" min="1" max="9" data-config-key="min" data-rerender="true" value="${Number(question.config?.min || 1)}">
            </label>
            <label>Maximo
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

  function renderResults() {
    if (!state.session) return;
    const question = selectedQuestion();
    const results = question?.results;
    if (summaryNode) summaryNode.textContent = question ? `${labelForType(question.type)} - ${results?.total || 0} respuestas` : "";
    if (altNode) altNode.innerHTML = "";
    if (moderationPanel) moderationPanel.innerHTML = "";
    hideChart();
    if (!question || !results) return;

    renderModeration(question);

    if (question.type === "content_slide") {
      if (altNode) altNode.innerHTML = `<p class="muted">Esta diapositiva no recibe respuestas.</p>`;
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
    if (!moderationPanel || !question.pending_responses?.length) return;
    moderationPanel.innerHTML = `
      <strong>Pendientes de moderacion</strong>
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
      alert(json.error || "No se pudo guardar la presentacion.");
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
    setSaveState("Guardado");
  }

  function collectCanvasPayload(question) {
    const title = textValue("[data-edit-field='title']", canvas) || question.title;
    const prompt = question.type === "content_slide" ? "" : textValue("[data-edit-field='prompt']", canvas);
    const config = { ...(question.config || {}) };
    if (question.type === "content_slide") {
      config.body = textValue("[data-config-field='body']", canvas);
    }
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

  function handleCanvasAction(action, button) {
    const question = selectedQuestion();
    if (!question) return;
    if (action === "add-option") {
      question.options = [...(question.options || []), { id: `tmp-${Date.now()}`, label: `Opcion ${(question.options || []).length + 1}`, is_correct: false }];
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
    if (shouldRender) renderCanvas();
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
    if (!confirm("Eliminar esta diapositiva?")) return;
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
            ensureSelectedQuestion();
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
      ensureSelectedQuestion();
      if (fullRender) render();
    } else {
      alert(json.error || "No se pudo controlar la presentacion.");
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
    if (!altNode) return;
    if (!words.length) {
      altNode.innerHTML = `<p class="muted">Sin palabras todavia.</p>`;
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
    if (!altNode) return;
    if (!cards.length) {
      altNode.innerHTML = `<p class="muted">Sin respuestas abiertas todavia.</p>`;
      return;
    }
    altNode.innerHTML = `
      <div class="response-card-grid">
        ${cards.map((card) => `<article>${escapeHtml(card.text)}</article>`).join("")}
      </div>
    `;
  }

  function renderLeaderboard(items) {
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
    const question = selectedQuestion();
    state.selectedQuestionId = question ? question.id : null;
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
      ["multiple_choice", "Opcion multiple"],
      ["word_cloud", "Nube de ideas"],
      ["scale", "Escala"],
      ["open_text", "Respuesta abierta"],
      ["ranking", "Ranking"],
      ["quiz", "Quiz"],
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
            body: "Escanea el QR o entra con el codigo de la presentacion.",
            show_qr: true,
          },
          options: [],
        };
      }
      return {
        type,
        title: finalLayout === "instructions" ? "Instrucciones" : "Titulo de la presentacion",
        prompt: "",
        config: {
          layout: finalLayout,
          body: finalLayout === "text" ? "Escribe aqui el contenido de la diapositiva." : "Subtitulo o contexto del taller.",
          show_qr: false,
        },
        options: [],
      };
    }
    if (type === "word_cloud") {
      return { type, title: "Lluvia de ideas", prompt: "Escribe una palabra o frase corta.", config: { moderation: "none" }, options: [] };
    }
    if (type === "open_text") {
      return { type, title: "Pregunta abierta", prompt: "Comparte tu respuesta.", config: { moderation: "none" }, options: [] };
    }
    if (type === "scale") {
      return { type, title: "Escala de opinion", prompt: "Califica del 1 al 5.", config: { min: 1, max: 5 }, options: [] };
    }
    if (type === "ranking") {
      return { type, title: "Prioriza opciones", prompt: "Ordena de mayor a menor prioridad.", options: ["Opcion 1", "Opcion 2", "Opcion 3"], config: {} };
    }
    if (type === "quiz") {
      return {
        type,
        title: "Quiz rapido",
        prompt: "Elige la respuesta correcta.",
        options: ["Respuesta A", "Respuesta B", "Respuesta C"],
        correct_option_labels: ["Respuesta A"],
        config: { timer_seconds: 30, points: 100 },
      };
    }
    return { type: "multiple_choice", title: "Pregunta de opcion multiple", prompt: "Elige una opcion.", options: ["Opcion 1", "Opcion 2"], config: {} };
  }

  function labelForType(type) {
    return {
      content_slide: "Contenido",
      multiple_choice: "Opcion multiple",
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
      qr: "Codigo QR",
    }[layout] || "Contenido";
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
      return { ok: false, error: "Error de conexion." };
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
