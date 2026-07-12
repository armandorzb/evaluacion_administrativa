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
    selectedTextTargetId: null,
    selectedLayoutBlockId: null,
    textDrag: null,
    layoutBlockDrag: null,
    saveTimer: null,
    sessionSaveTimer: null,
    sessionSaveInFlight: false,
    fitTimer: null,
    lastSaveKey: "",
    history: [],
    future: [],
    historyInputAt: 0,
    clipboard: null,
    selectedElementKeys: [],
    selectedMediaId: null,
    selectedQr: false,
    mediaDrag: null,
    zoom: 100,
    grid: false,
    snap: true,
    assets: [],
    assetsSupported: null,
    assetUploadBusy: false,
    dirtyQuestionId: null,
    saveInFlight: false,
    conflict: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const LAYOUT_BLOCK_IDS = ["question", "activity", "results"];
  const GRID_STEP = 5;
  const HISTORY_LIMIT = 60;
  const DEFAULT_LAYOUT_BLOCKS = {
    question: { id: "question", x: 7, y: 12, w: 86, h: 25, z: 1 },
    activity: { id: "activity", x: 7, y: 42, w: 42, h: 43, z: 2 },
    results: { id: "results", x: 53, y: 42, w: 40, h: 43, z: 3 },
  };

  const createForm = $("[data-create-session]");
  const deckTitleInput = $("[data-deck-title]");
  const statusPill = $("[data-session-status]");
  const connectedCount = $("[data-connected-count]");
  const responseMonitor = $("[data-response-monitor]");
  const addSlideButton = $("[data-add-slide]");
  const addMenu = $("[data-add-menu]");
  const slideList = $("[data-slide-list]");
  const canvas = $("[data-slide-canvas]");
  const canvasStage = $("[data-canvas-stage]");
  const inspector = $("[data-slide-inspector]");
  const saveState = $("[data-save-state]");
  const joinCardTemplate = $("[data-join-card-template]");
  const editorToolbar = $("[data-editor-toolbar]");
  const liveEditWarning = $("[data-live-edit-warning]");
  const editConflict = $("[data-edit-conflict]");
  const zoomLabel = $("[data-zoom-label]");
  const activeSelectionControlActions = new Set(["start", "next_slide", "previous_slide", "go_to_slide", "reset"]);

  bindGlobalEvents();

  if (code) {
    connectSocket();
    loadTemplates();
    loadAssets();
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
        window.location.assign(`/admin/${json.session.code}`);
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
        state.sessionSaveTimer = null;
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
        if (action === "reset" && !window.confirm("Se cerrara la ejecucion activa y se preparara una nueva. Las respuestas historicas se conservaran.")) {
          return;
        }
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

      selectSlide(id, false);
    });

    canvas?.addEventListener("input", (event) => {
      if (!event.target.closest("[contenteditable='true']")) return;
      updateLocalQuestionFromCanvas();
      scheduleSlideTextFit();
      scheduleQuestionSave();
    });

    canvas?.addEventListener("beforeinput", (event) => {
      if (event.target.closest("[contenteditable='true']")) rememberUndo("texto", { coalesce: true });
    });

    canvas?.addEventListener("blur", (event) => {
      if (!event.target.closest("[contenteditable='true']")) return;
      flushQuestionSave();
    }, true);

    canvas?.addEventListener("pointerdown", handleCanvasPointerDown);

    canvas?.addEventListener("click", (event) => {
      const question = selectedQuestion();
      const textSelection = canvasTextSelectionFromEvent(event, question);
      const layoutBlock = event.target.closest("[data-layout-block-id]");
      const canvasElement = event.target.closest("[data-canvas-element]");
      if (question?.type === "content_slide" && canvasElement) {
        // La selección se resolvió en pointerdown para preservar Mayús + clic y el arrastre.
      } else if (textSelection) {
        selectCanvasTextSelection(textSelection);
      } else if (layoutBlock && question?.type !== "content_slide") {
        selectLayoutBlock(layoutBlock.dataset.layoutBlockId);
      } else if (!event.target.closest("button[data-canvas-action]") && !event.target.closest("[contenteditable='true']")) {
        selectTextBox(null);
        clearCanvasElementSelection();
        selectCanvasTextTarget(null, { render: false });
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

    inspector?.addEventListener("beforeinput", (event) => {
      if (event.target instanceof HTMLElement) rememberUndo("propiedad", { coalesce: true });
    });

    inspector?.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      handleInspectorInput(target, true);
    });

    inspector?.addEventListener("click", (event) => {
      const assetButton = event.target.closest("button[data-asset-action], button[data-background-action], button[data-element-action]");
      if (assetButton) {
        handleAssetOrElementAction(assetButton);
        return;
      }
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

    inspector?.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLInputElement && target.matches("[data-asset-upload]")) uploadSelectedAsset(target);
    });

    editorToolbar?.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-editor-command]");
      if (button) handleEditorCommand(button.dataset.editorCommand);
    });

    $("[data-conflict-reload]")?.addEventListener("click", () => resolveConflictByReload());

    document.addEventListener("click", (event) => {
      if (!addMenu || addMenu.hidden) return;
      if (event.target.closest("[data-add-menu]") || event.target.closest("[data-add-slide]")) return;
      addMenu.hidden = true;
    });

    document.addEventListener("pointermove", handleCanvasPointerMove);
    document.addEventListener("pointerup", finishCanvasDrag);
    document.addEventListener("keydown", handleDocumentKeydown);
    window.addEventListener("resize", updateCanvasZoom);
  }

  function connectSocket() {
    if (!window.io) return;
    state.socket = window.io({ reconnection: true });
    state.socket.on("connect", () => {
      state.socket.emit("presenter_join", { code }, (ack) => {
        if (!ack?.ok || !ack.session) return;
        state.session = ack.session;
        renderChrome();
      });
    });
    state.socket.on("session_state", (next) => {
      if (state.saveInFlight || state.sessionSaveInFlight) return;
      if (hasUnsavedLocalChanges() && state.session?.updated_at && next?.updated_at && next.updated_at !== state.session.updated_at) {
        showConflict({ session: next, error: "La presentación cambió en otra ventana." });
        return;
      }
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
      if (!state.session) {
        if (connectedCount) connectedCount.textContent = payload.connected_count || 0;
        return;
      }
      state.session.connected_count = payload.connected_count || 0;
      state.session.response_monitor = payload.response_monitor || state.session.response_monitor;
      renderLiveCounters();
    });
  }

  async function loadTemplates() {
    const json = await getJson("/api/question-templates");
    if (!json.ok) return;
    state.templates = json.templates || [];
    renderInspector();
  }

  async function loadAssets() {
    if (!code || window.MENTI_PRESENT_ONLY) return;
    const json = await getJson(`/api/sessions/${code}/assets`);
    if (!json.ok) {
      state.assetsSupported = false;
      return;
    }
    state.assetsSupported = true;
    state.assets = Array.isArray(json.assets) ? json.assets : [];
    renderInspector();
  }

  async function loadSession(fullRender = true) {
    if (!code) return;
    const privateQuery = window.MENTI_PRESENT_ONLY ? "" : "?include_private=1";
    const json = await getJson(`/api/sessions/${code}${privateQuery}`);
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
    renderEditorToolbar();
    updateCanvasZoom();
    scheduleSlideTextFit();
    if (!state.conflict) setSaveState("Listo");
  }

  function renderChrome() {
    if (!state.session) return;
    document.body.dataset.theme = state.session.theme || "civic";
    if (deckTitleInput && document.activeElement !== deckTitleInput) {
      deckTitleInput.value = state.session.title || "";
    }
    if (statusPill) {
      const runCount = Number(state.session.runs?.length || 0);
      const runLabel = state.session.active_run_id ? "ejecucion activa" : `${runCount} ejec.`;
      statusPill.textContent = `${state.session.code} - ${state.session.status} - ${runLabel}`;
    }
    if (liveEditWarning) {
      liveEditWarning.hidden = !(state.session.active_run_id || ["live", "active", "running"].includes(String(state.session.status || "").toLowerCase()));
    }
    renderConflictNotice();
    renderLiveCounters();
  }

  function renderLiveCounters() {
    if (connectedCount) connectedCount.textContent = state.session?.connected_count || 0;
    if (!responseMonitor) return;
    const monitor = state.session?.response_monitor || {};
    const activeQuestion = questions().find((question) => question.id === monitor.active_question_id);
    const show = Boolean(state.session && activeQuestion && activeQuestion.type !== "content_slide");
    responseMonitor.hidden = !show;
    if (!show) return;
    const pending = Number(monitor.pending_count || 0);
    const responded = Number(monitor.responded_count || 0);
    const connected = Number(monitor.connected_count ?? state.session.connected_count ?? 0);
    responseMonitor.classList.toggle("is-idle", !monitor.accepting_responses);
    $("[data-pending-response-count]", responseMonitor).textContent = pending;
    $("[data-responded-response-count]", responseMonitor).textContent = responded;
    $("[data-live-response-count]", responseMonitor).textContent = connected;
    responseMonitor.title = monitor.accepting_responses
      ? `${pending} pendientes de respuesta. ${responded} de ${connected} conectados ya respondieron.`
      : "La pregunta activa no esta recibiendo respuestas.";
  }

  function cloneValue(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function historySnapshot(question = selectedQuestion()) {
    if (!question) return null;
    return {
      questionId: question.id,
      question: cloneValue(question),
      selectedTextBoxId: state.selectedTextBoxId,
      selectedMediaId: state.selectedMediaId,
      selectedQr: state.selectedQr,
      selectedElementKeys: [...state.selectedElementKeys],
      selectedLayoutBlockId: state.selectedLayoutBlockId,
    };
  }

  function rememberUndo(label = "edición", options = {}) {
    if (window.MENTI_PRESENT_ONLY || !state.session || state.conflict) return;
    const snapshot = historySnapshot();
    if (!snapshot) return;
    const now = Date.now();
    const latest = state.history[state.history.length - 1];
    if (options.coalesce && latest?.questionId === snapshot.questionId && now - state.historyInputAt < 850) return;
    const serialized = JSON.stringify(snapshot.question);
    if (latest && latest.questionId === snapshot.questionId && JSON.stringify(latest.question) === serialized) return;
    state.history.push({ ...snapshot, label, at: now });
    if (state.history.length > HISTORY_LIMIT) state.history.shift();
    state.future = [];
    state.historyInputAt = now;
    renderEditorToolbar();
  }

  function restoreHistorySnapshot(snapshot) {
    if (!snapshot || !state.session) return;
    const index = state.session.questions.findIndex((item) => item.id === snapshot.questionId);
    if (index < 0) return;
    const current = state.session.questions[index];
    state.session.questions[index] = {
      ...current,
      ...cloneValue(snapshot.question),
      id: current.id,
      position: current.position,
    };
    state.selectedQuestionId = current.id;
    state.selectedTextBoxId = snapshot.selectedTextBoxId || null;
    state.selectedMediaId = snapshot.selectedMediaId || null;
    state.selectedQr = Boolean(snapshot.selectedQr);
    state.selectedElementKeys = Array.isArray(snapshot.selectedElementKeys) ? snapshot.selectedElementKeys : [];
    state.selectedLayoutBlockId = snapshot.selectedLayoutBlockId || null;
    state.lastSaveKey = "";
    state.dirtyQuestionId = current.id;
    render();
    scheduleQuestionSave({ rerender: false, force: true });
  }

  function undoLocal() {
    const snapshot = state.history.pop();
    if (!snapshot) return;
    const current = historySnapshot(state.session?.questions?.find((item) => item.id === snapshot.questionId));
    if (current) state.future.push({ ...current, label: snapshot.label, at: Date.now() });
    restoreHistorySnapshot(snapshot);
    renderEditorToolbar();
  }

  function redoLocal() {
    const snapshot = state.future.pop();
    if (!snapshot) return;
    const current = historySnapshot(state.session?.questions?.find((item) => item.id === snapshot.questionId));
    if (current) state.history.push({ ...current, label: snapshot.label, at: Date.now() });
    restoreHistorySnapshot(snapshot);
    renderEditorToolbar();
  }

  function renderEditorToolbar() {
    if (!editorToolbar) return;
    const command = (name) => $("[data-editor-command='" + name + "']", editorToolbar);
    const undo = command("undo");
    const redo = command("redo");
    if (undo) undo.disabled = !state.history.length || Boolean(state.conflict);
    if (redo) redo.disabled = !state.future.length || Boolean(state.conflict);
    if (zoomLabel) zoomLabel.textContent = `${Math.round(state.zoom)}%`;
    const grid = command("grid");
    const snap = command("snap");
    if (grid) {
      grid.setAttribute("aria-pressed", String(state.grid));
      grid.classList.toggle("is-active", state.grid);
    }
    if (snap) {
      snap.setAttribute("aria-pressed", String(state.snap));
      snap.classList.toggle("is-active", state.snap);
    }
  }

  function updateCanvasZoom() {
    if (!canvas || !canvasStage || window.MENTI_PRESENT_ONLY) return;
    const stageWidth = canvasStage.clientWidth;
    const stageHeight = canvasStage.clientHeight;
    if (!stageWidth || !stageHeight) return;
    const availableWidth = Math.max(320, stageWidth - 56);
    const availableHeight = Math.max(180, stageHeight - 56);
    const baseWidth = Math.min(1120, availableWidth, availableHeight * (16 / 9));
    const width = Math.max(320, baseWidth * (state.zoom / 100));
    canvas.style.width = `${Math.round(width)}px`;
    canvas.style.maxWidth = "none";
    canvas.style.maxHeight = "none";
    renderEditorToolbar();
  }

  function handleEditorCommand(command) {
    if (command === "undo") return undoLocal();
    if (command === "redo") return redoLocal();
    if (command === "copy") return copySelection();
    if (command === "paste") return pasteSelection();
    if (command === "duplicate") return duplicateSelection();
    if (command === "zoom-in") state.zoom = Math.min(200, state.zoom + 10);
    if (command === "zoom-out") state.zoom = Math.max(50, state.zoom - 10);
    if (command === "fit") state.zoom = 100;
    if (command === "grid") {
      state.grid = !state.grid;
      renderCanvas();
    }
    if (command === "snap") state.snap = !state.snap;
    updateCanvasZoom();
    renderEditorToolbar();
  }

  function copySelection() {
    const question = selectedQuestion();
    if (!question) return;
    if (question.type === "content_slide") {
      const element = selectedCanvasElement(question);
      if (element) {
        state.clipboard = { kind: "element", element: cloneValue(element) };
        setSaveState("Elemento copiado");
        return;
      }
    } else if (state.selectedLayoutBlockId) {
      const block = selectedLayoutBlock(question);
      if (block) {
        state.clipboard = { kind: "layout-block", block: cloneValue(block) };
        setSaveState("Bloque copiado");
        return;
      }
    }
    state.clipboard = { kind: "slide", payload: cloneValue(payloadForQuestion(question)) };
    setSaveState("Diapositiva copiada");
  }

  async function pasteSelection() {
    const question = selectedQuestion();
    const clipboard = state.clipboard;
    if (!question || !clipboard) return;
    if (clipboard.kind === "element" && question.type === "content_slide") {
      pasteCanvasElement(question, clipboard.element);
      return;
    }
    if (clipboard.kind === "layout-block" && question.type !== "content_slide") {
      const id = state.selectedLayoutBlockId || "question";
      const blocks = ensureLayoutBlocks(question);
      if (!blocks[id]) return;
      rememberUndo("pegar bloque");
      question.config.layout_blocks[id] = normalizeLayoutBlock({ ...clipboard.block, id, x: clipboard.block.x + 3, y: clipboard.block.y + 3 }, id, LAYOUT_BLOCK_IDS.indexOf(id));
      renderCanvas();
      renderInspector();
      scheduleQuestionSave({ rerender: false });
      return;
    }
    if (clipboard.kind === "slide" && state.session) {
      const json = await postJson(`/api/sessions/${state.session.code}/questions`, clipboard.payload);
      if (!json.ok) {
        alert(json.error || "No se pudo pegar la diapositiva.");
        return;
      }
      state.session = json.session;
      state.selectedQuestionId = json.question.id;
      render();
    }
  }

  function pasteCanvasElement(question, copied) {
    const source = copied?.element || copied;
    if (!source?.kind) return;
    if (source.kind === "text") {
      const boxes = ensureTextBoxes(question);
      rememberUndo("pegar texto");
      const clone = normalizeTextBox({ ...source.value, id: makeTextBoxId(), x: source.value.x + 4, y: source.value.y + 4, z: Math.max(...boxes.map((item) => item.z), 0) + 1 }, boxes.length, question);
      question.config.text_boxes = [...boxes, clone];
      state.selectedElementKeys = [canvasElementKey("text", clone.id)];
      state.selectedTextBoxId = clone.id;
    } else if (source.kind === "media") {
      const blocks = ensureMediaBlocks(question);
      rememberUndo("pegar imagen");
      const clone = normalizeMediaBlock({ ...source.value, id: `media-${Date.now().toString(36)}`, x: source.value.x + 4, y: source.value.y + 4, z: Math.max(...blocks.map((item) => item.z), 0) + 1 }, blocks.length);
      question.config.media_blocks = [...blocks, clone];
      state.selectedElementKeys = [canvasElementKey("media", clone.id)];
      state.selectedTextBoxId = null;
      state.selectedMediaId = clone.id;
    } else if (source.kind === "qr") {
      rememberUndo("pegar QR");
      question.config.show_qr = true;
      const clone = { id: "qr", ...normalizeCanvasBox({ ...source.value, x: source.value.x + 4, y: source.value.y + 4 }, { x: 66, y: 54, w: 27, h: 29, z: 20 }, 20) };
      question.config.qr_position = clone;
      question.config.qr_block = clone;
      state.selectedElementKeys = [canvasElementKey("qr", "qr")];
      state.selectedTextBoxId = null;
      state.selectedMediaId = null;
      state.selectedQr = true;
    }
    renderCanvas();
    renderInspector();
    renderSlideList();
    scheduleQuestionSave({ rerender: false });
  }

  function duplicateSelection() {
    const question = selectedQuestion();
    if (!question) return;
    if (question.type === "content_slide") {
      const element = selectedCanvasElement(question);
      if (element) return pasteCanvasElement(question, element);
    }
    duplicateSlide(question.id);
  }

  function nudgeSelectionWithKeyboard(question, event) {
    const delta = event.shiftKey ? 5 : 1;
    const horizontal = event.key === "ArrowLeft" || event.key === "ArrowRight";
    const sign = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
    if (question.type === "content_slide") {
      const selected = selectedCanvasElements(question).filter((element) => !element.value.locked);
      if (!selected.length) return false;
      rememberUndo("ajuste con teclado", { coalesce: true });
      selected.forEach((element) => {
        const patch = event.altKey
          ? (horizontal ? { w: element.value.w + sign * delta } : { h: element.value.h + sign * delta })
          : (horizontal ? { x: element.value.x + sign * delta } : { y: element.value.y + sign * delta });
        updateCanvasElement(question, element, snapGeometryPatch({ ...element.value, ...patch }), { save: false });
      });
      renderCanvas();
      renderInspector();
      scheduleQuestionSave({ rerender: false });
      return true;
    }
    const block = selectedLayoutBlock(question);
    if (!block || block.locked) return false;
    rememberUndo("ajuste con teclado", { coalesce: true });
    const patch = event.altKey
      ? (horizontal ? { w: block.w + sign * delta } : { h: block.h + sign * delta })
      : (horizontal ? { x: block.x + sign * delta } : { y: block.y + sign * delta });
    updateSelectedLayoutBlock(question, snapGeometryPatch({ ...block, ...patch }), { save: false });
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
    return true;
  }

  function renderSlideList() {
    if (!slideList || !state.session) return;
    const activeId = state.session.active_question_id;
    slideList.innerHTML = questions().map((question, index) => {
      const selected = question.id === state.selectedQuestionId ? " is-selected" : "";
      const live = question.id === activeId ? " is-live" : "";
      const background = thumbnailBackgroundStyle(question);
      const optionPreview = question.options?.length
        ? `<div class="thumb-lines">${question.options.slice(0, 3).map((option) => `<span>${escapeHtml(option.label)}</span>`).join("")}</div>`
        : `<p>${escapeHtml(question.prompt || question.config?.body || "Diapositiva de contenido")}</p>`;
      return `
        <article class="slide-thumb${selected}${live}" data-question-id="${question.id}">
          <button type="button" class="slide-drag" aria-label="Reordenar">::</button>
          <div class="thumb-number">${index + 1}</div>
          <div class="thumb-preview" style="${background}">
            <span class="thumb-type">${escapeHtml(labelForType(question.type))}</span>
            <strong>${escapeHtml(question.title)}</strong>
            ${optionPreview}
            ${thumbnailMediaMarkup(question)}
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
      state.selectedTextTargetId = null;
      ensureTextBoxes(question);
      canvas.innerHTML = contentSlideMarkup(question);
      scheduleSlideTextFit();
      return;
    }
    state.selectedTextBoxId = null;
    ensureTextTargetSelection(question);
    ensureLayoutBlocks(question);
    canvas.innerHTML = interactiveSlideMarkup(question);
    syncCanvasTextTargetSelection();
    scheduleSlideTextFit();
  }

  function contentSlideMarkup(question) {
    const layout = question.config?.layout || "title";
    const boxes = ensureTextBoxes(question);
    const showQr = Boolean(question.config?.show_qr || layout === "qr");
    const media = ensureMediaBlocks(question);
    const qr = showQr ? ensureQrBlock(question) : null;
    const background = backgroundStyle(question);
    return `
      <div class="slide-canvas-inner content-layout-${escapeHtml(layout)}" style="${background}">
        ${gridOverlayMarkup()}
        <div class="slide-type-row">
          <span>${escapeHtml(labelForType(question.type))}</span>
          <strong>${escapeHtml(layoutLabel(layout))}</strong>
        </div>
        <div class="slide-text-layer">
          ${boxes.map((box) => textBoxMarkup(box)).join("")}
          ${media.map((block) => mediaBlockMarkup(block)).join("")}
          ${qr ? qrBlockMarkup(qr) : ""}
        </div>
        ${resultsStageMarkup(true)}
      </div>
    `;
  }

  function textBoxMarkup(box) {
    const selected = state.selectedElementKeys.includes(canvasElementKey("text", box.id)) || box.id === state.selectedTextBoxId ? " is-selected" : "";
    const locked = box.locked ? " is-locked" : "";
    return `
      <div class="slide-text-box${selected}${locked}" data-canvas-element="text:${escapeAttr(box.id)}" data-text-box-id="${escapeAttr(box.id)}" data-auto-fit="${box.auto_fit ? "true" : "false"}" data-locked="${box.locked ? "true" : "false"}" style="${textBoxStyle(box)}">
        <div class="slide-text-content" contenteditable="${box.locked ? "false" : "true"}" spellcheck="true" data-text-box-content>${escapeHtml(box.text)}</div>
        ${elementHandleMarkup("cuadro de texto", box.locked)}
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
      `right:auto`,
      `bottom:auto`,
    ].join(";");
  }

  function gridOverlayMarkup() {
    if (!state.grid || window.MENTI_PRESENT_ONLY) return "";
    return `<div data-grid-overlay aria-hidden="true" style="position:absolute;inset:0;pointer-events:none;z-index:99;background-image:linear-gradient(to right,rgba(37,99,235,.12) 1px,transparent 1px),linear-gradient(to bottom,rgba(37,99,235,.12) 1px,transparent 1px);background-size:${GRID_STEP}% ${GRID_STEP}%;"></div>`;
  }

  function elementHandleMarkup(label, locked) {
    if (locked) return "";
    return `
      <button type="button" class="slide-text-move" data-element-move-handle aria-label="Mover ${escapeAttr(label)}"></button>
      <button type="button" class="slide-text-resize handle-nw" data-element-resize-handle="nw" aria-label="Redimensionar ${escapeAttr(label)}"></button>
      <button type="button" class="slide-text-resize handle-ne" data-element-resize-handle="ne" aria-label="Redimensionar ${escapeAttr(label)}"></button>
      <button type="button" class="slide-text-resize handle-sw" data-element-resize-handle="sw" aria-label="Redimensionar ${escapeAttr(label)}"></button>
      <button type="button" class="slide-text-resize handle-se" data-element-resize-handle="se" aria-label="Redimensionar ${escapeAttr(label)}"></button>
    `;
  }

  function normalizeCanvasBox(raw, defaults = {}, index = 0) {
    const width = roundPercent(clampNumber(raw?.w, 5, 100, defaults.w || 25));
    const height = roundPercent(clampNumber(raw?.h, 5, 100, defaults.h || 20));
    return {
      x: roundPercent(clampNumber(raw?.x, 0, Math.max(0, 100 - width), defaults.x || 0)),
      y: roundPercent(clampNumber(raw?.y, 0, Math.max(0, 100 - height), defaults.y || 0)),
      w: width,
      h: height,
      z: Math.round(clampNumber(raw?.z, 0, 100, defaults.z || index + 1)),
      locked: raw?.locked === true || raw?.locked === "true",
    };
  }

  function mediaBlockId(raw, index) {
    const candidate = String(raw?.id || "").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
    return candidate || `media-${Date.now().toString(36)}-${index}`;
  }

  function normalizeMediaBlock(raw, index = 0) {
    const geometry = normalizeCanvasBox(raw, { x: 65, y: 15, w: 27, h: 35, z: index + 3 }, index);
    return {
      id: mediaBlockId(raw, index),
      asset_id: raw?.asset_id || raw?.assetId || null,
      url: String(raw?.url || raw?.media_url || raw?.asset_url || raw?.src || "").trim().slice(0, 1400),
      alt_text: String(raw?.alt_text || raw?.alt || "").trim().slice(0, 280),
      fit: ["cover", "contain"].includes(raw?.fit) ? raw.fit : "cover",
      ...geometry,
    };
  }

  function ensureMediaBlocks(question) {
    if (!question) return [];
    question.config = question.config || {};
    let source = Array.isArray(question.config.media_blocks) ? question.config.media_blocks : null;
    if (!source && Array.isArray(question.config.media)) source = question.config.media;
    if (!source && question.config.media_url) source = [{ id: "legacy-media", url: question.config.media_url }];
    const blocks = (source || []).map((block, index) => normalizeMediaBlock(block, index)).filter((block) => block.url);
    question.config.media_blocks = blocks;
    return blocks;
  }

  function mediaBlockStyle(block) {
    return [
      "position:absolute",
      `left:${block.x}%`,
      `top:${block.y}%`,
      `width:${block.w}%`,
      `height:${block.h}%`,
      `z-index:${block.z}`,
      "right:auto",
      "bottom:auto",
      "margin:0",
      "padding:0",
      "display:block",
      "overflow:hidden",
    ].join(";");
  }

  function mediaBlockMarkup(block) {
    const selected = block.id === state.selectedMediaId ? " is-selected" : "";
    const locked = block.locked ? " is-locked" : "";
    return `
      <figure class="slide-text-box slide-media slide-media-block${selected}${locked}" data-canvas-element="media:${escapeAttr(block.id)}" data-media-block-id="${escapeAttr(block.id)}" data-locked="${block.locked ? "true" : "false"}" style="${mediaBlockStyle(block)}">
        <img src="${escapeAttr(block.url)}" alt="${escapeAttr(block.alt_text)}" style="width:100%;height:100%;object-fit:${block.fit};display:block">
        ${elementHandleMarkup("imagen", block.locked)}
      </figure>
    `;
  }

  function ensureQrBlock(question) {
    if (!question) return null;
    question.config = question.config || {};
    const raw = question.config.qr_position || question.config.qr_block || {};
    const block = { id: "qr", ...normalizeCanvasBox(raw, { x: 66, y: 54, w: 27, h: 29, z: 20 }, 20) };
    question.config.qr_position = { ...block };
    question.config.qr_block = { ...block };
    return block;
  }

  function qrBlockStyle(block) {
    return [
      "position:absolute",
      `left:${block.x}%`,
      `top:${block.y}%`,
      `width:${block.w}%`,
      `height:${block.h}%`,
      `z-index:${block.z}`,
      "right:auto",
      "bottom:auto",
      "margin:0",
    ].join(";");
  }

  function qrBlockMarkup(block) {
    const selected = state.selectedQr ? " is-selected" : "";
    const locked = block.locked ? " is-locked" : "";
    const qrUrl = state.session?.qr_url || `/qr/${encodeURIComponent(state.session?.code || code || "")}.png`;
    const joinUrl = state.session?.join_url || "";
    return `
      <div class="slide-text-box slide-join-card slide-qr-block${selected}${locked}" data-canvas-element="qr:qr" data-qr-block data-locked="${block.locked ? "true" : "false"}" style="${qrBlockStyle(block)}">
        <span>Código</span>
        <strong>${escapeHtml(state.session?.code || "")}</strong>
        <img src="${escapeAttr(qrUrl)}" alt="QR para unirse">
        <code>${escapeHtml(joinUrl)}</code>
        ${elementHandleMarkup("código QR", block.locked)}
      </div>
    `;
  }

  function normalizedBackground(question) {
    const raw = question?.config?.background;
    const object = raw && typeof raw === "object" ? raw : {};
    const color = normalizeHexColor(typeof raw === "string" ? raw : object.color, "#ffffff");
    return {
      color,
      image_url: String(object.image_url || object.url || object.asset_url || "").trim().slice(0, 1400),
      asset_id: object.asset_id || null,
      fit: ["cover", "contain"].includes(object.fit) ? object.fit : "cover",
    };
  }

  function cssUrl(value) {
    return String(value || "").replace(/[\\"'()\n\r]/g, (character) => encodeURIComponent(character));
  }

  function backgroundStyle(question) {
    const background = normalizedBackground(question);
    const declarations = [`background-color:${background.color}`];
    if (background.image_url) declarations.push(`background-image:url("${cssUrl(background.image_url)}")`, `background-size:${background.fit}`, "background-position:center", "background-repeat:no-repeat");
    return declarations.join(";");
  }

  function thumbnailBackgroundStyle(question) {
    return `${backgroundStyle(question)};position:relative;overflow:hidden;`;
  }

  function thumbnailMediaMarkup(question) {
    const media = ensureMediaBlocks(question)[0];
    if (!media) return "";
    return `<img src="${escapeAttr(media.url)}" alt="" style="position:absolute;right:.35rem;bottom:.35rem;width:24%;height:38%;object-fit:${media.fit};border-radius:3px;opacity:.78">`;
  }

  function optionTextTargetId(index) {
    return `option:${index}`;
  }

  function textTargetIds(question) {
    if (!question || question.type === "content_slide") return [];
    const ids = ["title", "prompt"];
    if (["multiple_choice", "quiz", "ranking"].includes(question.type)) {
      (question.options || []).forEach((_option, index) => ids.push(optionTextTargetId(index)));
    }
    return ids;
  }

  function textTargetLabel(id) {
    if (id === "title") return "Titulo";
    if (id === "prompt") return "Pregunta";
    if (String(id || "").startsWith("option:")) return `Opcion ${Number(String(id).split(":")[1] || 0) + 1}`;
    return "Texto";
  }

  function ensureTextTargetSelection(question) {
    if (!question || question.type === "content_slide") {
      state.selectedTextTargetId = null;
      return;
    }
    if (state.selectedTextTargetId && !textTargetIds(question).includes(state.selectedTextTargetId)) {
      state.selectedTextTargetId = null;
    }
  }

  function rawTextTargetStyle(question, id) {
    const styles = question?.config?.text_styles;
    const item = styles && typeof styles === "object" ? styles[id] : null;
    return item && typeof item === "object" ? item : {};
  }

  function defaultTextTargetStyle(id) {
    if (id === "title") return { font_size: 60, font_weight: 800, color: "#17212f", background: "transparent", align: "left", auto_fit: true };
    if (id === "prompt") return { font_size: 24, font_weight: 400, color: "#334155", background: "transparent", align: "left", auto_fit: true };
    return { font_size: 20, font_weight: 800, color: "#17212f", background: "transparent", align: "left", auto_fit: true };
  }

  function normalizedTextTargetStyle(question, id) {
    const defaults = defaultTextTargetStyle(id);
    const raw = rawTextTargetStyle(question, id);
    return {
      font_size: Math.round(clampNumber(raw.font_size, 8, 120, defaults.font_size)),
      font_weight: Number(raw.font_weight || defaults.font_weight) >= 600 ? 800 : 400,
      color: normalizeHexColor(raw.color, defaults.color),
      background: raw.background === "transparent" ? "transparent" : normalizeHexColor(raw.background, defaults.background),
      align: ["left", "center", "right"].includes(raw.align) ? raw.align : defaults.align,
      auto_fit: raw.auto_fit !== false && raw.auto_fit !== "false",
    };
  }

  function textTargetInlineStyle(style) {
    const css = [];
    if (style.font_size !== undefined) css.push(`font-size:${Math.round(clampNumber(style.font_size, 8, 120, 16))}px`);
    if (style.font_weight !== undefined) css.push(`font-weight:${Number(style.font_weight) >= 600 ? 800 : 400}`);
    if (style.color) css.push(`color:${normalizeHexColor(style.color, "#17212f")}`);
    if (style.background) css.push(`background:${style.background === "transparent" ? "transparent" : normalizeHexColor(style.background, "#ffffff")}`);
    if (["left", "center", "right"].includes(style.align)) css.push(`text-align:${style.align}`);
    return css.join(";");
  }

  function textTargetAttrs(question, id) {
    const raw = rawTextTargetStyle(question, id);
    const style = normalizedTextTargetStyle(question, id);
    const css = textTargetInlineStyle(raw);
    const baseSize = raw.font_size !== undefined ? ` data-text-base-size="${style.font_size}"` : "";
    return ` data-text-target="${escapeAttr(id)}" data-auto-fit="${style.auto_fit ? "true" : "false"}"${baseSize}${css ? ` style="${escapeAttr(css)}"` : ""}`;
  }

  function canvasTextSelectionFromEvent(event, question) {
    if (!question || !(event.target instanceof HTMLElement)) return null;
    if (event.target.closest("button[data-canvas-action]")) return null;
    const editable = event.target.closest("[contenteditable='true']");

    if (question.type === "content_slide") {
      const boxNode = event.target.closest("[data-text-box-id]");
      if (boxNode) {
        return {
          kind: "text-box",
          id: boxNode.dataset.textBoxId,
          rerenderCanvas: !boxNode.classList.contains("slide-text-box"),
        };
      }
      if (editable?.dataset.editField === "title") return { kind: "text-box", id: "title", rerenderCanvas: true };
      if (editable?.dataset.configField === "body") return { kind: "text-box", id: "body", rerenderCanvas: true };
      return null;
    }

    const targetNode = event.target.closest("[data-text-target]");
    if (targetNode) {
      return {
        kind: "text-target",
        id: targetNode.dataset.textTarget,
        blockId: targetNode.closest("[data-layout-block-id]")?.dataset.layoutBlockId || null,
        rerenderCanvas: false,
      };
    }
    if (editable?.dataset.editField === "title" || editable?.dataset.editField === "prompt") {
      return { kind: "text-target", id: editable.dataset.editField, blockId: "question", rerenderCanvas: true };
    }
    const optionCard = event.target.closest(".option-card[data-option-index]");
    if (optionCard && !event.target.closest("button")) {
      return {
        kind: "text-target",
        id: optionTextTargetId(Number(optionCard.dataset.optionIndex || 0)),
        blockId: "activity",
        rerenderCanvas: !optionCard.querySelector("[data-text-target]"),
      };
    }
    return null;
  }

  function selectCanvasTextSelection(selection) {
    const question = selectedQuestion();
    if (!question || !selection?.id) return;
    if (selection.kind === "text-box") {
      if (question.type !== "content_slide") return;
      ensureTextBoxes(question);
      state.selectedTextBoxId = selection.id;
      state.selectedTextTargetId = null;
      state.selectedLayoutBlockId = null;
      if (selection.rerenderCanvas) renderCanvas();
      else syncTextBoxSelection();
      renderInspector();
      return;
    }
    if (selection.kind !== "text-target" || question.type === "content_slide") return;
    const validId = textTargetIds(question).includes(selection.id) ? selection.id : null;
    if (!validId) return;
    state.selectedTextTargetId = validId;
    state.selectedTextBoxId = null;
    if (selection.blockId && LAYOUT_BLOCK_IDS.includes(selection.blockId)) {
      state.selectedLayoutBlockId = selection.blockId;
    }
    if (selection.rerenderCanvas) renderCanvas();
    else {
      syncCanvasTextTargetSelection();
      syncLayoutBlockSelection();
    }
    renderInspector();
  }

  function selectedTextTarget(question) {
    if (!question || question.type === "content_slide" || !state.selectedTextTargetId) return null;
    ensureTextTargetSelection(question);
    if (!state.selectedTextTargetId) return null;
    return {
      id: state.selectedTextTargetId,
      label: textTargetLabel(state.selectedTextTargetId),
      ...normalizedTextTargetStyle(question, state.selectedTextTargetId),
    };
  }

  function textTargetNode(id) {
    if (!canvas || !id) return null;
    return $$("[data-text-target]", canvas).find((node) => node.dataset.textTarget === id) || null;
  }

  function selectCanvasTextTarget(id, options = {}) {
    const question = selectedQuestion();
    if (!question || question.type === "content_slide") return;
    const validId = id && textTargetIds(question).includes(id) ? id : null;
    state.selectedTextTargetId = validId;
    if (validId) {
      const node = textTargetNode(validId);
      const block = node?.closest("[data-layout-block-id]");
      if (block) state.selectedLayoutBlockId = block.dataset.layoutBlockId;
      state.selectedTextBoxId = null;
    }
    syncCanvasTextTargetSelection();
    syncLayoutBlockSelection();
    if (options.render !== false) renderInspector();
  }

  function syncCanvasTextTargetSelection() {
    if (!canvas) return;
    $$("[data-text-target]", canvas).forEach((node) => {
      node.classList.toggle("is-text-selected", node.dataset.textTarget === state.selectedTextTargetId);
    });
  }

  function updateSelectedTextTarget(question, patch, options = {}) {
    if (!question || question.type === "content_slide" || !state.selectedTextTargetId) return;
    const id = state.selectedTextTargetId;
    question.config = question.config || {};
    const styles = { ...(question.config.text_styles || {}) };
    styles[id] = normalizedTextTargetStyle({ config: { text_styles: { [id]: { ...rawTextTargetStyle(question, id), ...patch } } } }, id);
    question.config.text_styles = styles;
    applyTextTargetDom(question, id);
    if (options.renderInspector) renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function applyTextTargetDom(question, id) {
    const node = textTargetNode(id);
    if (!node) return;
    const style = normalizedTextTargetStyle(question, id);
    node.style.cssText = textTargetInlineStyle(style);
    node.dataset.autoFit = style.auto_fit ? "true" : "false";
    node.dataset.textBaseSize = String(style.font_size);
    scheduleSlideTextFit();
  }

  function interactiveSlideMarkup(question) {
    const blocks = ensureLayoutBlocks(question);
    const background = backgroundStyle(question);
    return `
      <div class="slide-canvas-inner interactive-layout" style="${background}">
        ${gridOverlayMarkup()}
        <div class="slide-type-row">
          <span>${escapeHtml(labelForType(question.type))}</span>
          <strong>${question.is_open ? "Voto abierto" : "Voto cerrado"}</strong>
        </div>
        ${layoutBlockMarkup("question", blocks.question, `
          <h2 contenteditable="${blocks.question.locked ? "false" : "true"}" spellcheck="false" data-edit-field="title"${textTargetAttrs(question, "title")}>${escapeHtml(question.title)}</h2>
          <p class="slide-prompt" contenteditable="${blocks.question.locked ? "false" : "true"}" spellcheck="true" data-edit-field="prompt"${textTargetAttrs(question, "prompt")}>${escapeHtml(question.prompt)}</p>
        `)}
        ${layoutBlockMarkup("activity", blocks.activity, visualEditorFor(question, blocks.activity.locked))}
        ${layoutBlockMarkup("results", blocks.results, resultsStageMarkup(false))}
      </div>
    `;
  }

  function layoutBlockMarkup(id, block, content) {
    const selected = id === state.selectedLayoutBlockId ? " is-selected" : "";
    const locked = block.locked ? " is-locked" : "";
    return `
      <section class="slide-layout-block slide-layout-block-${escapeAttr(id)}${selected}${locked}" data-layout-block-id="${escapeAttr(id)}" data-locked="${block.locked ? "true" : "false"}" style="${layoutBlockStyle(block)}">
        ${block.locked ? "" : `<button type="button" class="slide-block-move" data-block-move-handle aria-label="Mover bloque"></button>`}
        <div class="slide-layout-block-content" data-layout-block-content>${content}</div>
        ${block.locked ? "" : `
          <button type="button" class="slide-block-resize handle-nw" data-block-resize-handle="nw" aria-label="Redimensionar bloque"></button>
          <button type="button" class="slide-block-resize handle-ne" data-block-resize-handle="ne" aria-label="Redimensionar bloque"></button>
          <button type="button" class="slide-block-resize handle-sw" data-block-resize-handle="sw" aria-label="Redimensionar bloque"></button>
          <button type="button" class="slide-block-resize handle-se" data-block-resize-handle="se" aria-label="Redimensionar bloque"></button>
        `}
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

  function visualEditorFor(question, locked = false) {
    if (["multiple_choice", "quiz", "ranking"].includes(question.type)) {
      const cards = (question.options || []).map((option, index) => {
        const correct = option.is_correct ? " is-correct" : "";
        return `
          <div class="option-card${correct}" data-option-index="${index}">
            <span class="option-order">${index + 1}</span>
            <span class="option-label" contenteditable="${locked ? "false" : "true"}" spellcheck="true"${textTargetAttrs(question, optionTextTargetId(index))}>${escapeHtml(option.label)}</span>
            ${question.type === "quiz" && !locked ? `<button type="button" data-canvas-action="toggle-correct" data-option-index="${index}">Correcta</button>` : ""}
            ${locked ? "" : `<button type="button" data-canvas-action="remove-option" data-option-index="${index}" aria-label="Eliminar opción">x</button>`}
          </div>
        `;
      }).join("");
      return `
        <div class="option-grid ${question.type === "ranking" ? "ranking-preview" : ""}">
          ${cards}
          ${locked ? "" : '<button type="button" class="add-option-card" data-canvas-action="add-option">+ Agregar opción</button>'}
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

      ${backgroundInspectorMarkup(question)}
      ${typeSpecificInspector(question)}
      ${question.type === "content_slide" ? "" : textTargetInspectorMarkup(question, selectedTextTarget(question))}
      ${elementInspectorMarkup(question)}
      ${resultPresentationInspector(question)}
      ${layoutBlockInspectorMarkup(question)}
      ${presenterNotesInspectorMarkup(question)}
      ${assetLibraryInspectorMarkup(question)}
      ${runHistoryMarkup()}

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

  function runHistoryMarkup() {
    const runs = state.session?.runs || [];
    const currentRunId = state.session?.active_run_id || state.session?.report_run_id;
    const rows = runs.slice().reverse().map((run) => {
      const selected = run.id === currentRunId ? " is-current" : "";
      const ended = run.ended_at ? formatDateTime(run.ended_at) : "En curso";
      return `
        <article class="run-history-row${selected}">
          <div>
            <strong>Ejecucion ${run.run_number}</strong>
            <span>${escapeHtml(run.status)} - ${escapeHtml(formatDateTime(run.started_at))} / ${escapeHtml(ended)}</span>
          </div>
          <small>${Number(run.participant_count || 0)} participantes · ${Number(run.response_count || 0)} respuestas</small>
          <div class="run-export-actions">
            <a href="${escapeAttr(run.xlsx_url || "#")}">Excel</a>
            <a href="${escapeAttr(run.pdf_url || "#")}">PDF</a>
          </div>
        </article>
      `;
    }).join("");
    return `
      <section class="inspector-section run-history">
        <h3>Historial de sesiones</h3>
        ${rows || "<p class=\"muted\">Aun no hay ejecuciones registradas.</p>"}
      </section>
    `;
  }

  function formatDateTime(value) {
    if (!value) return "N/D";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });
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
          <label>URL de imagen (compatibilidad)
            <input data-media-url value="${escapeAttr(question.config?.media_url || "")}" maxlength="800" placeholder="https://...">
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

  function backgroundInspectorMarkup(question) {
    const background = normalizedBackground(question);
    const assetButtons = state.assets.slice(0, 18).map((asset) => `
      <button type="button" class="inspector-chip" data-background-action="asset" data-asset-id="${escapeAttr(asset.id)}" title="Usar ${escapeAttr(asset.original_filename || asset.filename || "imagen")}">
        ${escapeHtml(asset.original_filename || asset.filename || "Imagen")}
      </button>
    `).join("");
    return `
      <section class="inspector-section">
        <h3>Fondo</h3>
        <label>Color
          <input type="color" data-background-key="color" value="${escapeAttr(background.color)}">
        </label>
        <label>Imagen de fondo
          <input data-background-key="image_url" value="${escapeAttr(background.image_url)}" maxlength="1400" placeholder="https://…">
        </label>
        <label>Ajuste
          <select data-background-key="fit">
            <option value="cover"${background.fit === "cover" ? " selected" : ""}>Cubrir</option>
            <option value="contain"${background.fit === "contain" ? " selected" : ""}>Contener</option>
          </select>
        </label>
        ${assetButtons ? `<div class="template-buttons"><span class="muted">Usar imagen cargada</span>${assetButtons}</div>` : ""}
        ${background.image_url ? '<button type="button" data-background-action="clear">Quitar imagen de fondo</button>' : ""}
      </section>
    `;
  }

  function elementInspectorMarkup(question) {
    if (question.type !== "content_slide") return "";
    const element = selectedCanvasElement(question);
    if (!element) {
      return `
        <section class="inspector-section">
          <h3>Capas y posición</h3>
          <p class="muted">Selecciona texto, una imagen o el código QR. Usa Mayús + clic para alinear varios elementos.</p>
        </section>
      `;
    }
    const multi = selectedCanvasElements(question);
    const label = element.kind === "text" ? "Cuadro de texto" : element.kind === "media" ? "Imagen" : "Código QR";
    const geometry = element.value;
    const assetControls = element.kind === "media" ? `
      <label>Texto alternativo
        <input data-media-field="alt_text" value="${escapeAttr(geometry.alt_text || "")}" maxlength="280" placeholder="Describe la imagen">
      </label>
      <label>Ajuste de imagen
        <select data-media-field="fit">
          <option value="cover"${geometry.fit === "cover" ? " selected" : ""}>Cubrir</option>
          <option value="contain"${geometry.fit === "contain" ? " selected" : ""}>Contener</option>
        </select>
      </label>
    ` : "";
    return `
      <section class="inspector-section">
        <h3>${label}</h3>
        <label class="check-row">
          <input type="checkbox" data-element-lock${geometry.locked ? " checked" : ""}>
          Bloquear elemento
        </label>
        <div class="two-columns">
          <label>X<input type="number" min="0" max="100" step="0.5" data-element-geometry="x" value="${Number(geometry.x || 0)}"></label>
          <label>Y<input type="number" min="0" max="100" step="0.5" data-element-geometry="y" value="${Number(geometry.y || 0)}"></label>
          <label>Ancho<input type="number" min="5" max="100" step="0.5" data-element-geometry="w" value="${Number(geometry.w || 0)}"></label>
          <label>Alto<input type="number" min="5" max="100" step="0.5" data-element-geometry="h" value="${Number(geometry.h || 0)}"></label>
        </div>
        ${assetControls}
        <div class="inspector-actions">
          <button type="button" data-element-action="forward">Subir capa</button>
          <button type="button" data-element-action="backward">Bajar capa</button>
          <button type="button" data-element-action="front">Al frente</button>
          <button type="button" data-element-action="back">Al fondo</button>
        </div>
        <div class="segmented-controls" aria-label="Alinear elementos">
          <button type="button" data-element-action="align-left">Izq.</button>
          <button type="button" data-element-action="align-center">Centro</button>
          <button type="button" data-element-action="align-right">Der.</button>
          <button type="button" data-element-action="align-top">Arriba</button>
          <button type="button" data-element-action="align-middle">Medio</button>
          <button type="button" data-element-action="align-bottom">Abajo</button>
        </div>
        ${multi.length > 1 ? `<div class="inspector-actions"><button type="button" data-element-action="distribute-horizontal">Distribuir horizontal</button><button type="button" data-element-action="distribute-vertical">Distribuir vertical</button></div>` : ""}
      </section>
    `;
  }

  function presenterNotesInspectorMarkup(question) {
    const notes = String(question.config?.presenter_notes ?? question.config?.notes ?? "");
    return `
      <section class="inspector-section">
        <h3>Notas del presentador</h3>
        <label>
          <textarea data-presenter-notes rows="4" maxlength="4000" placeholder="Solo visibles para la persona que presenta.">${escapeHtml(notes)}</textarea>
        </label>
      </section>
    `;
  }

  function assetLibraryInspectorMarkup(question) {
    if (state.assetsSupported === false) {
      return `<section class="inspector-section"><h3>Imágenes</h3><p class="muted">Esta versión aún no tiene biblioteca de imágenes. Puedes usar una URL en las diapositivas de contenido.</p></section>`;
    }
    const cards = state.assets.map((asset) => `
      <article class="run-history-row">
        <div><strong>${escapeHtml(asset.original_filename || asset.filename || "Imagen")}</strong><span>${escapeHtml(asset.alt_text || "Sin texto alternativo")}</span></div>
        <div class="run-export-actions">
          ${question.type === "content_slide" ? `<button type="button" data-asset-action="insert" data-asset-id="${escapeAttr(asset.id)}">Insertar</button>` : ""}
          <button type="button" data-asset-action="delete" data-asset-id="${escapeAttr(asset.id)}" class="danger">Eliminar</button>
        </div>
      </article>
    `).join("");
    return `
      <section class="inspector-section">
        <h3>Biblioteca de imágenes</h3>
        <label>Texto alternativo para la carga
          <input data-asset-upload-alt maxlength="280" placeholder="Descripción de la imagen">
        </label>
        <label>Cargar PNG, JPEG o WebP
          <input type="file" accept="image/png,image/jpeg,image/webp" data-asset-upload${state.assetUploadBusy ? " disabled" : ""}>
        </label>
        ${state.assetsSupported === null ? '<p class="muted">Cargando biblioteca…</p>' : (cards || '<p class="muted">Aún no hay imágenes en esta presentación.</p>')}
      </section>
    `;
  }

  function resultPresentationInspector(question) {
    if (question.type === "content_slide") return "";
    const layout = normalizeResultLayout(question.type, question.config?.result_layout);
    return `
      <section class="inspector-section">
        <h3>Resultados</h3>
        <label class="check-row">
          <input type="checkbox" data-config-key="show_results" data-rerender="true"${question.config?.show_results === false ? "" : " checked"}>
          Revelar resultados
        </label>
        <label>Vista
          <select data-config-key="result_layout" data-rerender="true">
            ${resultLayoutOptions(question.type, layout)}
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
        <label class="check-row">
          <input type="checkbox" data-layout-block-lock${block.locked ? " checked" : ""}>
          Bloquear bloque
        </label>
        <div class="inspector-actions">
          <button type="button" data-layout-block-action="forward">Subir capa</button>
          <button type="button" data-layout-block-action="backward">Bajar capa</button>
          <button type="button" data-layout-block-action="front">Al frente</button>
          <button type="button" data-layout-block-action="back">Al fondo</button>
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

  function textTargetInspectorMarkup(_question, target) {
    if (!target) {
      return `
        <section class="inspector-section text-box-panel">
          <h3>Texto seleccionado</h3>
          <p class="muted">Selecciona un titulo, pregunta u opcion del lienzo para ajustar tamano, color y alineacion.</p>
        </section>
      `;
    }
    const swatches = ["#17212f", "#334155", "#2563eb", "#647c3d", "#b45309", "#ffffff"];
    return `
      <section class="inspector-section text-box-panel">
        <h3>Texto seleccionado</h3>
        <p class="muted">${escapeHtml(target.label)}</p>
        <label>Tamano
          <div class="range-row">
            <input type="range" min="8" max="120" data-text-style-key="font_size" value="${Number(target.font_size || 32)}">
            <input type="number" min="8" max="120" data-text-style-key="font_size" value="${Number(target.font_size || 32)}">
          </div>
        </label>
        <label class="check-row">
          <input type="checkbox" data-text-style-key="font_weight"${Number(target.font_weight || 400) >= 600 ? " checked" : ""}>
          Negritas
        </label>
        <div class="style-row">
          <span>Color</span>
          <div class="swatch-row">
            ${swatches.map((color) => `<button type="button" class="color-swatch${target.color === color ? " is-active" : ""}" data-text-color="${color}" style="background:${color}" aria-label="Color ${color}"></button>`).join("")}
            <input type="color" data-text-style-key="color" value="${escapeAttr(target.color || "#17212f")}">
          </div>
        </div>
        <div class="style-row">
          <span>Fondo</span>
          <div class="swatch-row">
            <button type="button" class="color-swatch transparent-swatch${target.background === "transparent" ? " is-active" : ""}" data-text-color="transparent" data-text-color-target="background" aria-label="Fondo transparente"></button>
            <input type="color" data-text-style-key="background" value="${escapeAttr(target.background === "transparent" ? "#ffffff" : target.background)}">
          </div>
        </div>
        <div class="style-row">
          <span>Alineacion</span>
          <div class="segmented-controls">
            ${["left", "center", "right"].map((align) => `<button type="button" class="${target.align === align ? "is-active" : ""}" data-text-align="${align}">${alignLabel(align)}</button>`).join("")}
          </div>
        </div>
        <label class="check-row">
          <input type="checkbox" data-text-style-key="auto_fit"${target.auto_fit ? " checked" : ""}>
          Autoajustar fuente
        </label>
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
    const layout = normalizeResultLayout(question.type, question.config?.result_layout);
    if (question.type === "multiple_choice" || question.type === "quiz") {
      const items = (results.options || []).map((item) => ({ label: item.label, value: item.count }));
      if (question.type === "quiz" && layout === "leaderboard") {
        if (results.leaderboard?.length) renderLeaderboard(results.leaderboard);
        else renderResultList(items, "Respuestas de quiz");
        return;
      }
      if (layout === "list") {
        renderResultList(items, question.type === "quiz" ? "Respuestas de quiz" : "Votos");
        return;
      }
      if (layout === "grid") {
        renderResultGrid(items);
        return;
      }
      renderBarChart(
        items.map((item) => item.label),
        items.map((item) => item.value),
        question.type === "quiz" ? "Respuestas de quiz" : "Votos",
      );
      if (question.type === "quiz" && results.leaderboard?.length) renderLeaderboard(results.leaderboard);
      return;
    }
    if (question.type === "scale") {
      const items = (results.values || []).map((item) => ({ label: String(item.value), value: item.count }));
      if (layout === "list") {
        renderResultList(items, `Promedio ${results.average || 0}`);
        return;
      }
      if (layout === "grid") {
        renderResultGrid(items);
        return;
      }
      renderBarChart(
        items.map((item) => item.label),
        items.map((item) => item.value),
        `Promedio ${results.average || 0}`,
      );
      return;
    }
    if (question.type === "ranking") {
      const items = (results.options || []).map((item) => ({ label: item.label, value: item.score }));
      if (layout === "ranking") {
        renderResultList(items, "Puntaje ranking");
        return;
      }
      renderBarChart(
        items.map((item) => item.label),
        items.map((item) => item.value),
        "Puntaje ranking",
      );
      return;
    }
    if (question.type === "word_cloud") {
      if (layout === "list") renderWordList(results.words || []);
      else renderWordResults(results.words || []);
      return;
    }
    if (question.type === "open_text") {
      if (layout === "list") renderOpenTextList(results.cards || []);
      else renderOpenText(results.cards || []);
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
  }

  async function patchSession(payload) {
    if (!state.session) return;
    state.sessionSaveInFlight = true;
    const json = await patchJson(`/api/sessions/${state.session.code}`, {
      ...payload,
      updated_at: state.session.updated_at,
      if_updated_at: state.session.updated_at,
    });
    if (!json.ok) {
      if (json.status === 409 || json.code === "edit_conflict") {
        state.sessionSaveInFlight = false;
        showConflict(json);
        return;
      }
      state.sessionSaveInFlight = false;
      setSaveState("Error al guardar");
      alert(json.error || "No se pudo guardar la presentación.");
      return;
    }
    state.sessionSaveInFlight = false;
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
    if (!question || state.conflict) return;
    const payload = collectCanvasPayload(question);
    if (!payloadIsReady(payload)) {
      setSaveState("Completa la diapositiva");
      return;
    }
    const saveKey = `${question.id}:${JSON.stringify(payload)}`;
    if (!options.force && saveKey === state.lastSaveKey) return;
    state.dirtyQuestionId = question.id;
    setSaveState("Guardando...");
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(() => {
      state.saveTimer = null;
      saveQuestion(payload, options);
    }, 500);
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
    const saveKey = `${question.id}:${JSON.stringify(payload)}`;
    state.lastSaveKey = saveKey;
    state.saveInFlight = true;
    const json = await patchJson(`/api/sessions/${state.session.code}/questions/${question.id}`, {
      ...payload,
      updated_at: question.updated_at || state.session.updated_at,
      if_updated_at: question.updated_at || state.session.updated_at,
    });
    state.saveInFlight = false;
    if (!json.ok) {
      state.lastSaveKey = "";
      if (json.status === 409 || json.code === "edit_conflict") {
        showConflict(json);
        return;
      }
      setSaveState("Error al guardar");
      return;
    }
    state.session = json.session;
    state.selectedQuestionId = json.question.id;
    state.dirtyQuestionId = null;
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
      config.background = normalizedBackground(question);
      config.media_blocks = ensureMediaBlocks(question);
      config.media = config.media_blocks;
      if (config.show_qr || config.layout === "qr") {
        const qr = ensureQrBlock(question);
        config.qr_position = qr;
        config.qr_block = qr;
      }
      config.body = bodyFromTextBoxes(boxes, config.body || "");
      const title = titleFromTextBoxes(boxes, question.title);
      return payloadForQuestion(question, { title, prompt: "", config, options: [], correct_option_labels: [] });
    }
    const title = textValue("[data-edit-field='title']", canvas) || question.title;
    const prompt = textValue("[data-edit-field='prompt']", canvas);
    config.background = normalizedBackground(question);
    config.result_placement = "slide";
    config.show_results = config.show_results !== false;
    config.result_layout = normalizeResultLayout(question.type, config.result_layout);
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
      locked: block.locked === true || block.locked === "true",
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
    if (state.selectedLayoutBlockId) state.selectedTextTargetId = null;
    syncLayoutBlockSelection();
    syncCanvasTextTargetSelection();
    renderInspector();
  }

  function syncLayoutBlockSelection() {
    if (!canvas) return;
    $$(".slide-layout-block", canvas).forEach((node) => {
      node.classList.toggle("is-selected", node.dataset.layoutBlockId === state.selectedLayoutBlockId);
    });
  }

  function applyLayoutBlockDom(block, options = {}) {
    if (!canvas) return;
    const node = $$(".slide-layout-block", canvas).find((item) => item.dataset.layoutBlockId === block.id);
    if (!node) return;
    node.style.cssText = layoutBlockStyle(block);
    if (options.fit !== false) scheduleSlideTextFit();
    if (block.id === "results" && state.chart && options.resizeChart !== false) {
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
    const geometryChanged = Object.prototype.hasOwnProperty.call(patch, "w") || Object.prototype.hasOwnProperty.call(patch, "h");
    applyLayoutBlockDom(next, { fit: geometryChanged, resizeChart: geometryChanged });
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
    const autoNodes = nodes.filter((node) => node.dataset.autoFit !== "false");
    nodes.filter((node) => node.dataset.autoFit === "false").forEach((node) => node.classList.toggle("is-overflowing", elementOverflows(node)));
    fitTextGroup(block, autoNodes, { minScale: 0.18, minFont: 8 });
  }

  function fitActivityBlockText() {
    const block = $(".slide-layout-block-activity [data-layout-block-content]", canvas);
    if (!block) return;
    block.classList.remove("is-overflowing");
    const optionGrid = $(".option-grid", block);
    if (optionGrid) {
      optionGrid.classList.remove("is-compact", "is-overflowing");
      const labels = $$(".option-label", optionGrid);
      const autoLabels = labels.filter((label) => label.dataset.autoFit !== "false");
      labels.filter((label) => label.dataset.autoFit === "false").forEach((label) => label.classList.toggle("is-overflowing", elementOverflows(label)));
      autoLabels.forEach((label) => fitSingleTextNode(label, { min: 9 }));
      if (elementOverflows(block) || elementOverflows(optionGrid)) {
        optionGrid.classList.add("is-compact");
        fitTextGroup(block, autoLabels, { minScale: 0.18, minFont: 7 });
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
    const max = Math.min(options.max || parseFloat(node.dataset.textBaseSize || "") || parseFloat(computed.fontSize) || 16, 160);
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
    const bases = nodes.map((node) => parseFloat(node.dataset.textBaseSize || "") || parseFloat(window.getComputedStyle(node).fontSize) || 16);
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
      const baseSize = parseFloat(node.dataset.textBaseSize || "");
      if (Number.isFinite(baseSize)) node.style.fontSize = `${baseSize}px`;
      else node.style.removeProperty("font-size");
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
      locked: box.locked === true || box.locked === "true",
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

  function canvasElementKey(kind, id) {
    return `${kind}:${id}`;
  }

  function contentCanvasElements(question) {
    if (!question || question.type !== "content_slide") return [];
    const elements = ensureTextBoxes(question).map((value) => ({ kind: "text", id: value.id, value }));
    ensureMediaBlocks(question).forEach((value) => elements.push({ kind: "media", id: value.id, value }));
    if (question.config?.show_qr || question.config?.layout === "qr") {
      const value = ensureQrBlock(question);
      if (value) elements.push({ kind: "qr", id: "qr", value });
    }
    return elements;
  }

  function selectedCanvasElements(question) {
    const all = contentCanvasElements(question);
    const keys = state.selectedElementKeys.length
      ? state.selectedElementKeys
      : (state.selectedTextBoxId ? [canvasElementKey("text", state.selectedTextBoxId)]
        : state.selectedMediaId ? [canvasElementKey("media", state.selectedMediaId)]
          : state.selectedQr ? [canvasElementKey("qr", "qr")] : []);
    return keys.map((key) => all.find((item) => canvasElementKey(item.kind, item.id) === key)).filter(Boolean);
  }

  function selectedCanvasElement(question) {
    return selectedCanvasElements(question)[0] || null;
  }

  function clearCanvasElementSelection(options = {}) {
    state.selectedElementKeys = [];
    state.selectedMediaId = null;
    state.selectedQr = false;
    if (options.keepText !== true) state.selectedTextBoxId = null;
    syncCanvasElementSelection();
    if (options.render !== false) renderInspector();
  }

  function selectCanvasElement(kind, id, multi = false, options = {}) {
    const question = selectedQuestion();
    if (!question || question.type !== "content_slide") return;
    const key = canvasElementKey(kind, id);
    const exists = contentCanvasElements(question).some((item) => canvasElementKey(item.kind, item.id) === key);
    if (!exists) return;
    if (multi) {
      state.selectedElementKeys = state.selectedElementKeys.includes(key)
        ? state.selectedElementKeys.filter((item) => item !== key)
        : [...state.selectedElementKeys, key];
    } else {
      state.selectedElementKeys = [key];
    }
    const primary = selectedCanvasElement(question);
    state.selectedTextBoxId = primary?.kind === "text" ? primary.id : null;
    state.selectedMediaId = primary?.kind === "media" ? primary.id : null;
    state.selectedQr = primary?.kind === "qr";
    state.selectedTextTargetId = null;
    syncCanvasElementSelection();
    if (options.render !== false) renderInspector();
  }

  function selectCanvasElementFromNode(node, multi = false) {
    const [kind, ...parts] = String(node?.dataset.canvasElement || "").split(":");
    const id = parts.join(":");
    if (!kind || !id) return;
    selectCanvasElement(kind, id, multi);
  }

  function syncCanvasElementSelection() {
    if (!canvas) return;
    $$("[data-canvas-element]", canvas).forEach((node) => {
      node.classList.toggle("is-selected", state.selectedElementKeys.includes(node.dataset.canvasElement));
    });
  }

  function updateCanvasElement(question, element, patch, options = {}) {
    if (!question || !element) return null;
    if (element.kind === "text") {
      const boxes = ensureTextBoxes(question);
      const index = boxes.findIndex((box) => box.id === element.id);
      if (index < 0) return null;
      const next = normalizeTextBox({ ...boxes[index], ...patch }, index, question);
      question.config.text_boxes[index] = next;
      syncTitleAndBodyFromBoxes(question);
      applyTextBoxDom(next, { fit: true });
      if (options.save !== false) scheduleQuestionSave({ rerender: false });
      return { kind: "text", id: next.id, value: next };
    }
    if (element.kind === "media") {
      const blocks = ensureMediaBlocks(question);
      const index = blocks.findIndex((block) => block.id === element.id);
      if (index < 0) return null;
      const next = normalizeMediaBlock({ ...blocks[index], ...patch }, index);
      question.config.media_blocks[index] = next;
      applyMediaBlockDom(next);
      if (options.save !== false) scheduleQuestionSave({ rerender: false });
      return { kind: "media", id: next.id, value: next };
    }
    if (element.kind === "qr") {
      const current = ensureQrBlock(question);
      const next = { id: "qr", ...normalizeCanvasBox({ ...current, ...patch }, { x: 66, y: 54, w: 27, h: 29, z: 20 }, 20) };
      question.config.qr_position = { ...next };
      question.config.qr_block = { ...next };
      applyQrBlockDom(next);
      if (options.save !== false) scheduleQuestionSave({ rerender: false });
      return { kind: "qr", id: "qr", value: next };
    }
    return null;
  }

  function applyMediaBlockDom(block) {
    const node = $$('[data-media-block-id]', canvas).find((item) => item.dataset.mediaBlockId === block.id);
    if (!node) return;
    node.style.cssText = mediaBlockStyle(block);
    node.dataset.locked = block.locked ? "true" : "false";
    const image = $("img", node);
    if (image) {
      image.alt = block.alt_text || "";
      image.style.objectFit = block.fit;
    }
  }

  function applyQrBlockDom(block) {
    const node = $("[data-qr-block]", canvas);
    if (!node) return;
    node.style.cssText = qrBlockStyle(block);
    node.dataset.locked = block.locked ? "true" : "false";
  }

  function selectTextBox(id) {
    state.selectedTextBoxId = id || null;
    if (state.selectedTextBoxId) {
      state.selectedTextTargetId = null;
      state.selectedMediaId = null;
      state.selectedQr = false;
      state.selectedElementKeys = [canvasElementKey("text", state.selectedTextBoxId)];
    } else {
      state.selectedElementKeys = [];
    }
    syncTextBoxSelection();
    syncCanvasElementSelection();
    renderInspector();
  }

  function syncTextBoxSelection() {
    if (!canvas) return;
    $$(".slide-text-box", canvas).forEach((node) => {
      const key = node.dataset.canvasElement || (node.dataset.textBoxId ? canvasElementKey("text", node.dataset.textBoxId) : "");
      node.classList.toggle("is-selected", state.selectedElementKeys.includes(key) || node.dataset.textBoxId === state.selectedTextBoxId);
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
    rememberUndo("agregar texto");
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
    state.selectedElementKeys = [canvasElementKey("text", next.id)];
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function duplicateSelectedTextBox(question) {
    const box = selectedTextBox(question);
    if (!box) return;
    rememberUndo("duplicar texto");
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
    state.selectedElementKeys = [canvasElementKey("text", clone.id)];
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function deleteSelectedTextBox(question) {
    const boxes = ensureTextBoxes(question);
    if (!state.selectedTextBoxId || boxes.length <= 1) return;
    rememberUndo("eliminar texto");
    const index = boxes.findIndex((box) => box.id === state.selectedTextBoxId);
    question.config.text_boxes = boxes.filter((box) => box.id !== state.selectedTextBoxId);
    state.selectedTextBoxId = question.config.text_boxes[Math.max(index - 1, 0)]?.id || null;
    state.selectedElementKeys = state.selectedTextBoxId ? [canvasElementKey("text", state.selectedTextBoxId)] : [];
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
    if (boxes[index].locked && !Object.prototype.hasOwnProperty.call(patch, "locked")) return;
    const next = normalizeTextBox({ ...boxes[index], ...patch }, index, question);
    question.config.text_boxes[index] = next;
    syncTitleAndBodyFromBoxes(question);
    const textFitChanged = ["w", "h", "font_size", "font_weight", "align", "auto_fit"].some((key) =>
      Object.prototype.hasOwnProperty.call(patch, key),
    );
    applyTextBoxDom(next, { fit: textFitChanged });
    if (options.renderList !== false) renderSlideList();
    if (options.renderInspector) renderInspector();
    if (options.save !== false) scheduleQuestionSave({ rerender: false });
  }

  function applyTextBoxDom(box, options = {}) {
    if (!canvas) return;
    const node = $$(".slide-text-box", canvas).find((item) => item.dataset.textBoxId === box.id);
    if (!node) return;
    node.style.cssText = textBoxStyle(box);
    node.dataset.autoFit = box.auto_fit ? "true" : "false";
    if (options.fit !== false) scheduleSlideTextFit();
  }

  function handleCanvasPointerDown(event) {
    const question = selectedQuestion();
    if (!question || state.conflict) return;
    if (question.type !== "content_slide") {
      handleLayoutBlockPointerDown(event, question);
      return;
    }
    const node = event.target.closest("[data-canvas-element]");
    if (!node) return;
    selectCanvasElementFromNode(node, event.shiftKey);
    if (event.shiftKey) return;
    const element = selectedCanvasElement(question);
    if (!element || element.value.locked || !canvas) return;
    const handle = event.target.closest("[data-element-resize-handle]");
    const moveHandle = event.target.closest("[data-element-move-handle]");
    if (!handle && !moveHandle && event.target.closest("[data-text-box-content]")) return;
    rememberUndo("mover o redimensionar");
    state.textDrag = {
      kind: element.kind,
      id: element.id,
      mode: handle ? "resize" : "move",
      handle: handle?.dataset.elementResizeHandle || "se",
      startX: event.clientX,
      startY: event.clientY,
      startBox: { ...element.value },
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
    if (!block || block.locked) return;
    rememberUndo("mover bloque");
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
    const element = contentCanvasElements(question).find((item) => item.kind === drag.kind && item.id === drag.id);
    if (!element) return;
    const dx = ((event.clientX - drag.startX) / drag.rect.width) * 100;
    const dy = ((event.clientY - drag.startY) / drag.rect.height) * 100;
    const patch = drag.mode === "move"
      ? movedTextBoxPatch(drag.startBox, dx, dy)
      : resizedTextBoxPatch(drag.startBox, drag.handle, dx, dy);
    updateCanvasElement(question, element, patch, { save: false });
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

  function snapGeometryPatch(patch) {
    if (!state.snap) return patch;
    const step = GRID_STEP;
    const w = patch.w === undefined ? undefined : clampNumber(Math.round(patch.w / step) * step, 5, 100, patch.w);
    const h = patch.h === undefined ? undefined : clampNumber(Math.round(patch.h / step) * step, 5, 100, patch.h);
    const maxX = 100 - (w === undefined ? 0 : w);
    const maxY = 100 - (h === undefined ? 0 : h);
    return {
      ...patch,
      ...(w === undefined ? {} : { w: roundPercent(w) }),
      ...(h === undefined ? {} : { h: roundPercent(h) }),
      ...(patch.x === undefined ? {} : { x: roundPercent(clampNumber(Math.round(patch.x / step) * step, 0, maxX, patch.x)) }),
      ...(patch.y === undefined ? {} : { y: roundPercent(clampNumber(Math.round(patch.y / step) * step, 0, maxY, patch.y)) }),
    };
  }

  function movedTextBoxPatch(box, dx, dy) {
    return snapGeometryPatch({
      x: clampNumber(box.x + dx, 0, Math.max(0, 100 - box.w), box.x),
      y: clampNumber(box.y + dy, 0, Math.max(0, 100 - box.h), box.y),
      w: box.w,
      h: box.h,
    });
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
    return snapGeometryPatch(patch);
  }

  function movedLayoutBlockPatch(block, dx, dy) {
    return snapGeometryPatch({
      x: clampNumber(block.x + dx, 0, Math.max(0, 100 - block.w), block.x),
      y: clampNumber(block.y + dy, 0, Math.max(0, 100 - block.h), block.y),
      w: block.w,
      h: block.h,
    });
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
    return snapGeometryPatch({ x, y, w, h });
  }

  function handleDocumentKeydown(event) {
    const question = selectedQuestion();
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && !isEditing()) {
      const key = String(event.key || "").toLowerCase();
      if (key === "z") {
        event.preventDefault();
        if (event.shiftKey) redoLocal();
        else undoLocal();
        return;
      }
      if (key === "y") {
        event.preventDefault();
        redoLocal();
        return;
      }
      if (key === "c") {
        event.preventDefault();
        copySelection();
        return;
      }
      if (key === "v") {
        event.preventDefault();
        pasteSelection();
        return;
      }
      if (key === "d") {
        event.preventDefault();
        duplicateSelection();
        return;
      }
    }
    if (event.key === "Escape") {
      document.activeElement?.blur?.();
      clearCanvasElementSelection({ render: false });
      if (question?.type !== "content_slide") {
        selectCanvasTextTarget(null, { render: false });
        selectLayoutBlock(null);
      }
      renderInspector();
      return;
    }
    if (!question || isEditing()) return;
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      if (nudgeSelectionWithKeyboard(question, event)) event.preventDefault();
      return;
    }
    if (!["Delete", "Backspace"].includes(event.key)) return;
    event.preventDefault();
    if (question.type === "content_slide") deleteSelectedCanvasElement(question);
    else if (state.selectedLayoutBlockId) resetLayoutBlocks(question);
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
    if (!question) return;
    const action = button.dataset.textBoxAction;
    if (action === "add") {
      if (question.type !== "content_slide") return;
      addTextBox(question);
      return;
    }
    if (action === "duplicate") {
      if (question.type !== "content_slide") return;
      duplicateSelectedTextBox(question);
      return;
    }
    if (action === "delete") {
      if (question.type !== "content_slide") return;
      deleteSelectedTextBox(question);
      return;
    }
    if (button.dataset.textAlign) {
      rememberUndo("estilo de texto");
      updateSelectedTextStyle(question, { align: button.dataset.textAlign }, { renderInspector: true });
      return;
    }
    if (button.dataset.textColor) {
      const key = button.dataset.textColorTarget || "color";
      rememberUndo("estilo de texto");
      updateSelectedTextStyle(question, { [key]: button.dataset.textColor }, { renderInspector: true });
    }
  }

  function handleTextStyleInput(target) {
    const question = selectedQuestion();
    if (!question) return;
    const key = target.dataset.textStyleKey;
    let value = target instanceof HTMLInputElement && target.type === "checkbox" ? target.checked : target.value;
    const patch = {};
    rememberUndo("estilo de texto", { coalesce: true });
    if (key === "font_size") patch.font_size = clampNumber(value, 8, 120);
    if (key === "font_weight") patch.font_weight = value ? 800 : 400;
    if (key === "color") patch.color = normalizeHexColor(value, "#17212f");
    if (key === "background") patch.background = normalizeHexColor(value, "#ffffff");
    if (key === "auto_fit") patch.auto_fit = Boolean(value);
    updateSelectedTextStyle(question, patch, { renderInspector: false });
  }

  function updateSelectedTextStyle(question, patch, options = {}) {
    if (question.type === "content_slide") {
      updateSelectedTextBox(question, patch, options);
      return;
    }
    updateSelectedTextTarget(question, patch, options);
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
    rememberUndo("posición de bloque", { coalesce: true });
    updateSelectedLayoutBlock(question, { [key]: Number(target.value || 0) }, { renderInspector: false });
  }

  function handleLayoutBlockButton(button) {
    const question = selectedQuestion();
    if (!question || question.type === "content_slide") return;
    const action = button.dataset.layoutBlockAction;
    if (action === "reset") {
      rememberUndo("restablecer diseño");
      resetLayoutBlocks(question);
      return;
    }
    const block = selectedLayoutBlock(question);
    if (!block || block.locked) return;
    const values = Object.values(ensureLayoutBlocks(question));
    const maxZ = Math.max(...values.map((item) => Number(item.z || 0)), 0);
    const minZ = Math.min(...values.map((item) => Number(item.z || 0)), 0);
    const z = action === "front" ? maxZ + 1
      : action === "back" ? Math.max(0, minZ - 1)
        : action === "forward" ? block.z + 1
          : action === "backward" ? Math.max(0, block.z - 1)
            : block.z;
    rememberUndo("orden de bloque");
    updateSelectedLayoutBlock(question, { z }, { renderInspector: true });
  }

  function handleAssetOrElementAction(button) {
    const question = selectedQuestion();
    if (!question) return;
    const asset = state.assets.find((item) => String(item.id) === String(button.dataset.assetId));
    if (button.dataset.assetAction === "insert" && asset) {
      insertAssetIntoSlide(question, asset);
      return;
    }
    if (button.dataset.assetAction === "delete" && asset) {
      deleteAsset(asset);
      return;
    }
    if (button.dataset.backgroundAction === "asset" && asset) {
      rememberUndo("fondo");
      const current = normalizedBackground(question);
      question.config = {
        ...(question.config || {}),
        background: { ...current, image_url: asset.url, asset_id: asset.id },
      };
      renderCanvas();
      renderSlideList();
      scheduleQuestionSave({ rerender: false });
      return;
    }
    if (button.dataset.backgroundAction === "clear") {
      rememberUndo("fondo");
      const current = normalizedBackground(question);
      question.config = { ...(question.config || {}), background: { ...current, image_url: "", asset_id: null } };
      renderCanvas();
      renderSlideList();
      scheduleQuestionSave({ rerender: false });
      return;
    }
    const action = button.dataset.elementAction;
    if (!action) return;
    if (action.startsWith("align-")) {
      alignCanvasElements(question, action.slice("align-".length));
      return;
    }
    if (action.startsWith("distribute-")) {
      distributeCanvasElements(question, action.slice("distribute-".length));
      return;
    }
    const selected = selectedCanvasElement(question);
    if (!selected) return;
    if (action === "duplicate") {
      duplicateSelection();
      return;
    }
    if (selected.value.locked) return;
    const elements = contentCanvasElements(question);
    const maxZ = Math.max(...elements.map((item) => Number(item.value.z || 0)), 0);
    const minZ = Math.min(...elements.map((item) => Number(item.value.z || 0)), 0);
    const z = action === "front" ? maxZ + 1
      : action === "back" ? Math.max(0, minZ - 1)
        : action === "forward" ? selected.value.z + 1
          : action === "backward" ? Math.max(0, selected.value.z - 1)
            : selected.value.z;
    rememberUndo("orden de capa");
    updateCanvasElement(question, selected, { z }, { save: false });
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function updateBackground(question, key, value) {
    if (!["color", "image_url", "fit"].includes(key)) return;
    rememberUndo("fondo", { coalesce: true });
    const next = { ...normalizedBackground(question), [key]: key === "color" ? normalizeHexColor(value, "#ffffff") : String(value || "") };
    question.config = { ...(question.config || {}), background: next };
    renderCanvas();
    renderSlideList();
    scheduleQuestionSave({ rerender: false });
  }

  function setLegacyMediaUrl(question, value) {
    const url = String(value || "").trim().slice(0, 1400);
    rememberUndo("imagen", { coalesce: true });
    question.config = { ...(question.config || {}), media_url: url };
    const blocks = ensureMediaBlocks(question);
    const legacyIndex = blocks.findIndex((block) => block.id === "legacy-media");
    if (url) {
      const next = normalizeMediaBlock({ ...(blocks[legacyIndex] || {}), id: "legacy-media", url }, legacyIndex >= 0 ? legacyIndex : blocks.length);
      question.config.media_blocks = legacyIndex >= 0
        ? blocks.map((block, index) => index === legacyIndex ? next : block)
        : [...blocks, next];
    } else if (legacyIndex >= 0) {
      question.config.media_blocks = blocks.filter((block) => block.id !== "legacy-media");
    }
    renderCanvas();
    renderSlideList();
    scheduleQuestionSave({ rerender: false });
  }

  function insertAssetIntoSlide(question, asset) {
    if (question.type !== "content_slide") return;
    rememberUndo("insertar imagen");
    const blocks = ensureMediaBlocks(question);
    const block = normalizeMediaBlock({
      id: `media-${Date.now().toString(36)}`,
      asset_id: asset.id,
      url: asset.url,
      alt_text: asset.alt_text || asset.original_filename || "",
      x: 58,
      y: 19,
      w: 30,
      h: 40,
      z: Math.max(...blocks.map((item) => Number(item.z || 0)), 1) + 1,
    }, blocks.length);
    question.config.media_blocks = [...blocks, block];
    state.selectedTextBoxId = null;
    state.selectedMediaId = block.id;
    state.selectedQr = false;
    state.selectedElementKeys = [canvasElementKey("media", block.id)];
    renderCanvas();
    renderInspector();
    renderSlideList();
    scheduleQuestionSave({ rerender: false });
  }

  async function uploadSelectedAsset(input) {
    const file = input.files?.[0];
    if (!file || !state.session || state.assetUploadBusy) return;
    const allowed = ["image/png", "image/jpeg", "image/webp"];
    if (!allowed.includes(file.type)) {
      alert("Usa una imagen PNG, JPEG o WebP.");
      input.value = "";
      return;
    }
    const altText = String($("[data-asset-upload-alt]", inspector)?.value || "").trim();
    state.assetUploadBusy = true;
    renderInspector();
    const form = new FormData();
    form.append("file", file);
    form.append("alt_text", altText);
    const json = await fetchJson(`/api/sessions/${state.session.code}/assets`, { method: "POST", body: form });
    state.assetUploadBusy = false;
    if (!json.ok) {
      if (json.status === 404) state.assetsSupported = false;
      alert(json.error || "No se pudo cargar la imagen.");
      renderInspector();
      return;
    }
    state.assetsSupported = true;
    state.assets = [...state.assets, json.asset].filter(Boolean);
    renderInspector();
  }

  async function deleteAsset(asset) {
    if (!state.session || !window.confirm(`¿Eliminar ${asset.original_filename || asset.filename || "esta imagen"}?`)) return;
    const json = await fetchJson(`/api/sessions/${state.session.code}/assets/${asset.id}`, { method: "DELETE" });
    if (!json.ok && json.status !== 204) {
      alert(json.error || "No se pudo eliminar la imagen.");
      return;
    }
    state.assets = state.assets.filter((item) => String(item.id) !== String(asset.id));
    renderInspector();
  }

  function deleteSelectedCanvasElement(question) {
    const selected = selectedCanvasElement(question);
    if (!selected || selected.value.locked) return;
    if (selected.kind === "text") {
      deleteSelectedTextBox(question);
      return;
    }
    rememberUndo("eliminar elemento");
    if (selected.kind === "media") {
      question.config.media_blocks = ensureMediaBlocks(question).filter((block) => block.id !== selected.id);
    } else if (selected.kind === "qr") {
      question.config.show_qr = false;
    }
    clearCanvasElementSelection({ render: false });
    renderCanvas();
    renderInspector();
    renderSlideList();
    scheduleQuestionSave({ rerender: false });
  }

  function alignCanvasElements(question, alignment) {
    const selected = selectedCanvasElements(question).filter((element) => !element.value.locked);
    if (!selected.length) return;
    rememberUndo("alinear elementos");
    const horizontal = ["left", "center", "right"].includes(alignment);
    const starts = selected.map((element) => horizontal ? element.value.x : element.value.y);
    const ends = selected.map((element) => horizontal ? element.value.x + element.value.w : element.value.y + element.value.h);
    const groupStart = Math.min(...starts);
    const groupEnd = Math.max(...ends);
    const groupMiddle = (groupStart + groupEnd) / 2;
    selected.forEach((element) => {
      let patch = {};
      if (alignment === "left") patch = { x: selected.length === 1 ? 0 : groupStart };
      if (alignment === "center") patch = { x: (selected.length === 1 ? 50 : groupMiddle) - element.value.w / 2 };
      if (alignment === "right") patch = { x: (selected.length === 1 ? 100 : groupEnd) - element.value.w };
      if (alignment === "top") patch = { y: selected.length === 1 ? 0 : groupStart };
      if (alignment === "middle") patch = { y: (selected.length === 1 ? 50 : groupMiddle) - element.value.h / 2 };
      if (alignment === "bottom") patch = { y: (selected.length === 1 ? 100 : groupEnd) - element.value.h };
      updateCanvasElement(question, element, snapGeometryPatch({ ...element.value, ...patch }), { save: false });
    });
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function distributeCanvasElements(question, direction) {
    const selected = selectedCanvasElements(question).filter((element) => !element.value.locked);
    if (selected.length < 3) return;
    rememberUndo("distribuir elementos");
    const horizontal = direction === "horizontal";
    const ordered = selected.slice().sort((a, b) => (horizontal ? a.value.x - b.value.x : a.value.y - b.value.y));
    const first = ordered[0].value;
    const last = ordered[ordered.length - 1].value;
    const start = horizontal ? first.x : first.y;
    const end = horizontal ? last.x + last.w : last.y + last.h;
    const totalSize = ordered.reduce((total, element) => total + (horizontal ? element.value.w : element.value.h), 0);
    const gap = Math.max(0, (end - start - totalSize) / (ordered.length - 1));
    let cursor = start;
    ordered.forEach((element) => {
      const patch = horizontal ? { x: cursor } : { y: cursor };
      updateCanvasElement(question, element, snapGeometryPatch({ ...element.value, ...patch }), { save: false });
      cursor += (horizontal ? element.value.w : element.value.h) + gap;
    });
    renderCanvas();
    renderInspector();
    scheduleQuestionSave({ rerender: false });
  }

  function handleCanvasAction(action, button) {
    const question = selectedQuestion();
    if (!question) return;
    if (action === "add-option") {
      rememberUndo("agregar opción");
      question.options = [...(question.options || []), { id: `tmp-${Date.now()}`, label: `Opción ${(question.options || []).length + 1}`, is_correct: false }];
      renderCanvas();
      scheduleQuestionSave({ rerender: false });
      return;
    }
    const index = Number(button.dataset.optionIndex || -1);
    if (index < 0) return;
    if (action === "remove-option") {
      rememberUndo("eliminar opción");
      question.options.splice(index, 1);
      renderCanvas();
      scheduleQuestionSave({ rerender: false });
      return;
    }
    if (action === "toggle-correct") {
      rememberUndo("respuesta correcta");
      question.options[index].is_correct = !question.options[index].is_correct;
      renderCanvas();
      scheduleQuestionSave({ rerender: false });
    }
  }

  function handleInspectorInput(target, fromChange) {
    const question = selectedQuestion();
    if (!state.session || !question || state.conflict) return;

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

    if (target.matches("[data-layout-block-lock]")) {
      if (question.type !== "content_slide") {
        rememberUndo("bloquear bloque");
        updateSelectedLayoutBlock(question, { locked: Boolean(target.checked) }, { renderInspector: true });
      }
      return;
    }

    if (target.matches("[data-element-geometry]")) {
      const element = selectedCanvasElement(question);
      if (element && !element.value.locked) {
        updateCanvasElement(question, element, { [target.dataset.elementGeometry]: Number(target.value || 0) });
      }
      return;
    }

    if (target.matches("[data-element-lock]")) {
      const element = selectedCanvasElement(question);
      if (element) {
        rememberUndo("bloquear elemento");
        updateCanvasElement(question, element, { locked: Boolean(target.checked) }, { renderInspector: true });
        renderCanvas();
      }
      return;
    }

    if (target.matches("[data-media-field]")) {
      const element = selectedCanvasElement(question);
      if (element?.kind === "media") updateCanvasElement(question, element, { [target.dataset.mediaField]: target.value });
      return;
    }

    if (target.matches("[data-media-url]")) {
      setLegacyMediaUrl(question, target.value);
      return;
    }

    if (target.matches("[data-background-key]")) {
      updateBackground(question, target.dataset.backgroundKey, target.value);
      return;
    }

    if (target.matches("[data-presenter-notes]")) {
      question.config = { ...(question.config || {}), presenter_notes: String(target.value || "").slice(0, 4000) };
      scheduleQuestionSave({ rerender: false });
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
    rememberUndo("propiedad", { coalesce: !fromChange });
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
    rememberUndo("tipo de diapositiva");
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

  function renderResultList(items, heading = "Resultados") {
    const { altNode } = resultNodes();
    if (!altNode) return;
    const max = Math.max(...items.map((item) => Number(item.value || 0)), 1);
    altNode.innerHTML = `
      <div class="leaderboard-panel" data-result-layout="list">
        <strong>${escapeHtml(heading)}</strong>
        ${items.map((item, index) => {
          const value = Number(item.value || 0);
          return `<div><span>${index + 1}. ${escapeHtml(item.label)}</span><b>${value}</b><i style="display:block;width:${Math.max(3, (value / max) * 100)}%;height:.28rem;background:var(--primary);border-radius:999px"></i></div>`;
        }).join("") || '<p class="muted">Aún no hay resultados.</p>'}
      </div>
    `;
  }

  function renderResultGrid(items) {
    const { altNode } = resultNodes();
    if (!altNode) return;
    altNode.innerHTML = `
      <div class="response-card-grid" data-result-layout="grid">
        ${items.map((item) => `<article><strong>${escapeHtml(item.label)}</strong><b>${Number(item.value || 0)}</b></article>`).join("") || '<p class="muted">Aún no hay resultados.</p>'}
      </div>
    `;
  }

  function renderWordList(words) {
    const items = words.map((word) => ({ label: word.text, value: word.count }));
    renderResultList(items, "Palabras más mencionadas");
  }

  function renderOpenTextList(cards) {
    const { altNode } = resultNodes();
    if (!altNode) return;
    altNode.innerHTML = `
      <div class="leaderboard-panel" data-result-layout="list">
        <strong>Respuestas abiertas</strong>
        ${(cards || []).map((card, index) => `<div><span>${index + 1}. ${escapeHtml(card.text)}</span></div>`).join("") || '<p class="muted">Sin respuestas abiertas todavía.</p>'}
      </div>
    `;
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
          const count = Number(word.count || 0);
          const ratio = count / max;
          const size = 14 + ratio * 28;
          return `
            <span class="word-cloud-tag" data-count="${count}" data-text-base-size="${size.toFixed(1)}" style="font-size:${size.toFixed(1)}px;--word-ratio:${ratio.toFixed(3)}" aria-label="${escapeAttr(word.text)}: ${count} menciones">
              <b>${escapeHtml(word.text)}</b>
              <small>${count}</small>
            </span>
          `;
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
    if (type === "ranking") return "ranking";
    return "chart";
  }

  function resultConfig(type, overrides = {}) {
    return {
      show_results: true,
      result_layout: defaultResultLayout(type),
      layout_blocks: defaultLayoutBlocks(),
      background: { color: "#ffffff", image_url: "", fit: "cover" },
      presenter_notes: "",
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

  function resultLayoutsForType(type) {
    if (type === "word_cloud") return [["cloud", "Nube"], ["list", "Lista"]];
    if (type === "open_text") return [["cards", "Tarjetas"], ["list", "Lista"]];
    if (type === "quiz") return [["leaderboard", "Ranking"], ["chart", "Gráfica"]];
    if (type === "ranking") return [["ranking", "Ranking"], ["chart", "Gráfica"]];
    return [["chart", "Gráfica"], ["list", "Lista"], ["grid", "Matriz"]];
  }

  function normalizeResultLayout(type, value) {
    const choices = resultLayoutsForType(type).map(([key]) => key);
    return choices.includes(value) ? value : defaultResultLayout(type);
  }

  function resultLayoutOptions(type, current) {
    const normalized = normalizeResultLayout(type, current);
    return resultLayoutsForType(type)
      .map(([value, label]) => `<option value="${value}"${value === normalized ? " selected" : ""}>${label}</option>`)
      .join("");
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
            background: { color: "#ffffff", image_url: "", fit: "cover" },
            media_blocks: [],
            presenter_notes: "",
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
          background: { color: "#ffffff", image_url: "", fit: "cover" },
          media_blocks: [],
          presenter_notes: "",
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

  function hasUnsavedLocalChanges() {
    return Boolean(state.dirtyQuestionId || state.saveTimer || state.saveInFlight || state.sessionSaveTimer || state.sessionSaveInFlight);
  }

  function showConflict(payload = {}) {
    state.conflict = payload;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = null;
    setSaveState("Cambios externos detectados");
    renderConflictNotice();
    renderEditorToolbar();
  }

  function renderConflictNotice() {
    if (!editConflict) return;
    editConflict.hidden = !state.conflict;
  }

  async function resolveConflictByReload() {
    state.conflict = null;
    state.dirtyQuestionId = null;
    state.lastSaveKey = "";
    renderConflictNotice();
    setSaveState("Recargando versión actual…");
    await loadSession(true);
    renderEditorToolbar();
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
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : {};
      return { ...payload, ok: payload.ok === true, status: response.status };
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
