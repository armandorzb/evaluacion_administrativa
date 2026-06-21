(() => {
  const sessionStateNode = document.getElementById("live-session-state");
  const activityStateNode = document.getElementById("live-activity-state");
  const initialSession = parseJsonNode(sessionStateNode) || {};
  const initialActivity = parseJsonNode(activityStateNode);
  let liveChart = null;

  initializeTemplateForms();
  initializeSlideEditor();
  initializePresenter(initialSession);
  initializeParticipant(initialSession, initialActivity);

  function parseJsonNode(node) {
    if (!node) return null;
    try {
      return JSON.parse(node.textContent || "{}");
    } catch (_error) {
      return null;
    }
  }

  function initializeTemplateForms() {
    document.querySelectorAll("[data-live-template-type]").forEach((select) => {
      const form = select.closest("form");
      if (!form) return;
      const sync = () => {
        form.querySelectorAll("[data-live-config]").forEach((node) => {
          const hidden = node.dataset.liveConfig !== select.value;
          node.hidden = hidden;
          node.querySelectorAll("input, textarea, select").forEach((control) => {
            control.disabled = hidden;
          });
        });
      };
      select.addEventListener("change", sync);
      sync();
    });
  }

  function initializeSlideEditor() {
    document.querySelectorAll("[data-live-editor]").forEach((editor) => {
      const orderList = editor.querySelector("[data-live-slide-order]");
      const reorderStatus = editor.querySelector("[data-live-reorder-status]");
      let draggedItem = null;
      let pointerDrag = null;
      let saveTimer = null;
      const inlineTimers = new Map();

      const activate = (activityId) => {
        editor.querySelectorAll("[data-live-editor-slide]").forEach((button) => {
          button.classList.toggle("is-selected", button.dataset.liveEditorSlide === activityId);
        });
        editor.querySelectorAll("[data-live-editor-canvas]").forEach((panel) => {
          panel.hidden = panel.dataset.liveEditorCanvas !== activityId;
        });
        editor.querySelectorAll("[data-live-editor-properties]").forEach((panel) => {
          panel.hidden = panel.dataset.liveEditorProperties !== activityId;
        });
      };
      const setReorderStatus = (message, state = "") => {
        if (!reorderStatus) return;
        reorderStatus.textContent = message;
        reorderStatus.dataset.state = state;
      };
      const orderedIds = () =>
        Array.from(editor.querySelectorAll("[data-live-slide-order-item] input[name='slide_ids']"))
          .map((input) => Number(input.value))
          .filter(Boolean);
      const syncSlideNumbers = () => {
        editor.querySelectorAll("[data-live-slide-order-item]").forEach((item, index) => {
          const number = item.querySelector("[data-live-slide-index]");
          if (number) number.textContent = String(index + 1).padStart(2, "0");
        });
      };
      const saveOrder = () => {
        const endpoint = editor.dataset.liveReorderEndpoint;
        const activityIds = orderedIds();
        syncSlideNumbers();
        if (!endpoint || !activityIds.length) {
          setReorderStatus("Orden pendiente de guardar", "dirty");
          return;
        }
        setReorderStatus("Guardando orden...", "saving");
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(() => {
          fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ activity_ids: activityIds }),
          })
            .then((response) => response.json())
            .then((json) => {
              if (!json.ok) throw new Error(json.error || "No se pudo guardar el orden.");
              setReorderStatus("Orden guardado", "saved");
            })
            .catch(() => setReorderStatus("No se pudo guardar. Usa Guardar orden.", "error"));
        }, 350);
      };
      const moveItem = (item, direction) => {
        if (direction === "up" && item.previousElementSibling) {
          item.parentNode.insertBefore(item, item.previousElementSibling);
          saveOrder();
        }
        if (direction === "down" && item.nextElementSibling) {
          item.parentNode.insertBefore(item.nextElementSibling, item);
          saveOrder();
        }
      };
      const findActivityConfigNode = (activityId) =>
        Array.from(editor.querySelectorAll("[data-live-activity-config]")).find(
          (node) => node.dataset.liveActivityConfig === String(activityId),
        );
      const readActivityConfig = (activityId) => {
        const node = findActivityConfigNode(activityId);
        return { node, config: parseJsonNode(node) || {} };
      };
      const setInlineStatus = (activityId, message, state = "") => {
        editor.querySelectorAll(`[data-live-inline-status="${activityId}"]`).forEach((node) => {
          node.textContent = message;
          node.dataset.state = state;
        });
      };
      const textFromEditable = (node) =>
        (node.innerText || "")
          .replace(/\u00a0/g, " ")
          .replace(/\r/g, "")
          .replace(/\n{3,}/g, "\n\n")
          .trim();
      const updateEndpoint = (activityId) =>
        (editor.dataset.liveUpdateEndpointTemplate || "").replace("__ACTIVITY_ID__", activityId);
      const syncEditorFields = (activityId, field, value) => {
        const properties = editor.querySelector(`[data-live-editor-properties="${activityId}"]`);
        const form = properties?.querySelector("form.live-properties-form");
        if (field === "titulo") {
          const titleInput = form?.querySelector("[name='titulo']");
          const titleHeading = properties?.querySelector(`[data-live-properties-title="${activityId}"]`);
          const thumbTitle = editor
            .querySelector(`[data-live-editor-slide="${activityId}"]`)
            ?.querySelector("strong");
          if (titleInput) titleInput.value = value;
          if (titleHeading) titleHeading.textContent = value;
          if (thumbTitle) thumbTitle.textContent = value;
        }
        if (field === "prompt") {
          const promptInput = form?.querySelector("[name='prompt']");
          if (promptInput) promptInput.value = value;
        }
        if (field === "body") {
          const bodyInput = form?.querySelector("[name='body']");
          if (bodyInput) bodyInput.value = value;
        }
      };
      const currentTextValue = (activityId, field) => {
        const node = editor.querySelector(
          `[data-live-inline-edit][data-activity-id="${activityId}"][data-live-edit-field="${field}"]`,
        );
        return node ? textFromEditable(node) : "";
      };
      const buildActivityPayload = (activityId, field, value) => {
        const properties = editor.querySelector(`[data-live-editor-properties="${activityId}"]`);
        const form = properties?.querySelector("form.live-properties-form");
        const { node: configNode, config: baseConfig } = readActivityConfig(activityId);
        const config = { ...baseConfig };
        const tipo = form?.querySelector("[name='tipo']")?.value || "";
        const titulo =
          field === "titulo"
            ? value
            : form?.querySelector("[name='titulo']")?.value || currentTextValue(activityId, "titulo");
        const prompt =
          field === "prompt"
            ? value
            : form?.querySelector("[name='prompt']")?.value || currentTextValue(activityId, "prompt");

        const resultLayout = form?.querySelector("[name='result_layout']")?.value;
        if (resultLayout) config.result_layout = resultLayout;
        const showResults = form?.querySelector("input[type='checkbox'][name='show_results']");
        if (showResults) config.show_results = showResults.checked;

        if (tipo === "content_slide") {
          const layout = form?.querySelector("[name='layout']")?.value;
          if (layout) config.layout = layout;
          const timerSeconds = Number(form?.querySelector("[name='timer_seconds']")?.value || 0);
          config.timer_seconds = Number.isFinite(timerSeconds) ? timerSeconds : 0;
          config.body =
            field === "body" ? value : form?.querySelector("[name='body']")?.value ?? config.body ?? "";
          config.media_url = form?.querySelector("[name='media_url']")?.value || null;
        }

        return { configNode, payload: { tipo, titulo, prompt, config } };
      };
      const saveInlineEdit = (activityId, field, value) => {
        const endpoint = updateEndpoint(activityId);
        if (!endpoint) return;
        if ((field === "titulo" || field === "prompt") && value.length < 3) {
          setInlineStatus(activityId, "Faltan caracteres para guardar", "error");
          return;
        }
        const { configNode, payload } = buildActivityPayload(activityId, field, value);
        setInlineStatus(activityId, "Guardando...", "saving");
        fetch(endpoint, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
          .then((response) => response.json())
          .then((json) => {
            if (!json.ok) throw new Error(json.error || "No se pudo guardar.");
            if (configNode) configNode.textContent = JSON.stringify(json.activity?.config || payload.config || {});
            if (json.activity?.titulo) syncEditorFields(activityId, "titulo", json.activity.titulo);
            if (json.activity?.prompt) syncEditorFields(activityId, "prompt", json.activity.prompt);
            if (json.activity?.config?.body !== undefined) {
              syncEditorFields(activityId, "body", json.activity.config.body || "");
            }
            setInlineStatus(activityId, "Guardado", "saved");
          })
          .catch(() => setInlineStatus(activityId, "No se pudo guardar", "error"));
      };
      const scheduleInlineSave = (editable) => {
        const activityId = editable.dataset.activityId;
        const field = editable.dataset.liveEditField;
        const value = textFromEditable(editable);
        const key = `${activityId}:${field}`;
        syncEditorFields(activityId, field, value);
        setInlineStatus(activityId, "Cambios pendientes", "dirty");
        window.clearTimeout(inlineTimers.get(key));
        inlineTimers.set(
          key,
          window.setTimeout(() => saveInlineEdit(activityId, field, value), 650),
        );
      };

      editor.querySelectorAll("[data-live-inline-edit]").forEach((editable) => {
        if (editable.getAttribute("contenteditable") !== "true") return;
        editable.addEventListener("keydown", (event) => {
          if (editable.dataset.liveEditField === "titulo" && event.key === "Enter") {
            event.preventDefault();
            editable.blur();
          }
        });
        editable.addEventListener("input", () => scheduleInlineSave(editable));
        editable.addEventListener("blur", () => {
          const activityId = editable.dataset.activityId;
          const field = editable.dataset.liveEditField;
          const key = `${activityId}:${field}`;
          window.clearTimeout(inlineTimers.get(key));
          saveInlineEdit(activityId, field, textFromEditable(editable));
        });
      });

      editor.querySelector("[data-live-quick-add-slide]")?.addEventListener("click", (event) => {
        const endpoint = editor.dataset.liveAddEndpoint;
        if (!endpoint) return;
        const button = event.currentTarget;
        button.disabled = true;
        setReorderStatus("Creando diapositiva...", "saving");
        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            tipo: "content_slide",
            titulo: "Nueva diapositiva",
            prompt: "Haz clic para editar este texto.",
            config: {
              layout: "text",
              body: "Escribe el contenido principal.",
              timer_seconds: 0,
              show_results: true,
              result_layout: "chart",
            },
          }),
        })
          .then((response) => response.json())
          .then((json) => {
            if (!json.ok) throw new Error(json.error || "No se pudo crear.");
            window.location.assign(`${window.location.pathname}?slide=${json.activity.id}`);
          })
          .catch(() => {
            button.disabled = false;
            setReorderStatus("No se pudo crear la diapositiva", "error");
          });
      });

      editor.addEventListener("click", (event) => {
        const slideButton = event.target.closest("[data-live-editor-slide]");
        if (slideButton) {
          activate(slideButton.dataset.liveEditorSlide);
          return;
        }
        const moveButton = event.target.closest("[data-live-move-slide]");
        if (!moveButton) return;
        const item = moveButton.closest("[data-live-slide-order-item]");
        if (!item) return;
        moveItem(item, moveButton.dataset.liveMoveSlide);
      });

      if (!orderList) return;
      orderList.addEventListener("pointerdown", (event) => {
        const handle = event.target.closest(".live-slide-drag-handle");
        if (!handle) return;
        const item = handle.closest("[data-live-slide-order-item]");
        if (!item) return;
        event.preventDefault();
        pointerDrag = { item, moved: false };
        item.classList.add("is-dragging");
        setReorderStatus("Moviendo slide...", "dirty");
        handle.setPointerCapture?.(event.pointerId);
      });
      document.addEventListener("pointermove", (event) => {
        if (!pointerDrag) return;
        const target = document
          .elementFromPoint(event.clientX, event.clientY)
          ?.closest("[data-live-slide-order-item]");
        if (!target || target === pointerDrag.item || !orderList.contains(target)) return;
        const rect = target.getBoundingClientRect();
        const afterTarget = event.clientY > rect.top + rect.height / 2;
        target.parentNode.insertBefore(pointerDrag.item, afterTarget ? target.nextElementSibling : target);
        pointerDrag.moved = true;
        syncSlideNumbers();
        setReorderStatus("Orden modificado", "dirty");
      });
      document.addEventListener("pointerup", () => {
        if (!pointerDrag) return;
        pointerDrag.item.classList.remove("is-dragging");
        if (pointerDrag.moved) saveOrder();
        pointerDrag = null;
      });
      orderList.addEventListener("dragstart", (event) => {
        draggedItem = event.target.closest("[data-live-slide-order-item]");
        if (!draggedItem) return;
        draggedItem.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", draggedItem.querySelector("input[name='slide_ids']")?.value || "");
      });
      orderList.addEventListener("dragover", (event) => {
        if (!draggedItem) return;
        event.preventDefault();
        const target = event.target.closest("[data-live-slide-order-item]");
        if (!target || target === draggedItem) return;
        const rect = target.getBoundingClientRect();
        const afterTarget = event.clientY > rect.top + rect.height / 2;
        target.parentNode.insertBefore(draggedItem, afterTarget ? target.nextElementSibling : target);
        syncSlideNumbers();
        setReorderStatus("Orden modificado", "dirty");
      });
      orderList.addEventListener("drop", (event) => {
        if (!draggedItem) return;
        event.preventDefault();
        draggedItem.classList.remove("is-dragging");
        draggedItem = null;
        saveOrder();
      });
      orderList.addEventListener("dragend", () => {
        if (draggedItem) {
          draggedItem.classList.remove("is-dragging");
          draggedItem = null;
          saveOrder();
        }
      });
    });
  }

  function initializePresenter(state) {
    const root = document.querySelector("[data-live-presenter]");
    if (!root) return;
    const sessionId = Number(root.dataset.sessionId);
    const canControl = root.dataset.canControl === "true";
    let currentState = state;
    let socket = null;
    let pollTimer = null;

    const pollState = () => {
      fetch(`/live/api/sessions/${sessionId}/state`)
        .then((response) => response.json())
        .then((json) => {
          if (json.ok && json.session) {
            currentState = json.session;
            renderPresenter(root, currentState, canControl);
          }
        })
        .catch(() => {});
    };
    const startPolling = () => {
      if (pollTimer) return;
      pollState();
      pollTimer = window.setInterval(pollState, 4000);
    };
    const stopPolling = () => {
      if (!pollTimer) return;
      window.clearInterval(pollTimer);
      pollTimer = null;
    };

    renderPresenter(root, currentState, canControl);

    if (window.io) {
      socket = window.io();
      socket.emit("live:join_session", { session_id: sessionId });
      socket.on("live:session_state", (nextState) => {
        currentState = nextState;
        renderPresenter(root, currentState, canControl);
      });
      socket.on("live:activity_state", (activity) => {
        currentState.activities = (currentState.activities || []).map((item) =>
          item.id === activity.id ? activity : item,
        );
        renderPresenter(root, currentState, canControl);
      });
      socket.on("live:results_updated", (payload) => {
        currentState.activities = (currentState.activities || []).map((item) => {
          if (item.id !== payload.activity_id) return item;
          return { ...item, results: payload.results };
        });
        renderPresenter(root, currentState, canControl);
      });
      socket.on("live:participant_count", (payload) => {
        currentState = { ...currentState, ...payload };
        renderParticipantCounter(root, currentState);
        const status = root.querySelector("[data-live-status]");
        if (status) status.textContent = currentState.estado || "draft";
      });
      socket.on("connect", stopPolling);
      socket.on("connect_error", startPolling);
      socket.on("disconnect", startPolling);
      window.setTimeout(() => {
        if (!socket.connected) startPolling();
      }, 3000);
    } else {
      startPolling();
    }

    root.querySelectorAll("[data-live-fullscreen]").forEach((button) => {
      const syncLabel = () => {
        button.textContent = document.fullscreenElement ? "Salir de pantalla completa" : "Pantalla completa";
      };
      button.addEventListener("click", () => {
        if (document.fullscreenElement) {
          document.exitFullscreen?.();
          return;
        }
        const request = root.requestFullscreen?.();
        request?.catch?.(() => {
          button.textContent = "Usa F11 para pantalla completa";
          window.setTimeout(syncLabel, 2500);
        });
      });
      document.addEventListener("fullscreenchange", syncLabel);
      syncLabel();
    });

    root.querySelectorAll("[data-live-control]").forEach((button) => {
      button.addEventListener("click", () => {
        sendPresenterControl(socket, sessionId, { action: button.dataset.liveControl }, currentState, (nextState) => {
          currentState = nextState;
          renderPresenter(root, currentState, canControl);
        });
      });
    });

    root.addEventListener("click", (event) => {
      const activityButton = event.target.closest("[data-live-activity-control]");
      if (activityButton) {
        const payload = {
          action: activityButton.dataset.liveActivityControl,
          activity_id: Number(activityButton.dataset.activityId),
        };
        if (activityButton.dataset.timerSeconds) {
          payload.timer_seconds = Number(activityButton.dataset.timerSeconds);
        }
        sendPresenterControl(socket, sessionId, payload, currentState, (nextState) => {
          currentState = nextState;
          renderPresenter(root, currentState, canControl);
        });
        return;
      }

      const moderateButton = event.target.closest("[data-live-moderate-response]");
      if (moderateButton) {
        sendModeration(socket, sessionId, {
          activity_id: Number(moderateButton.dataset.activityId),
          response_id: Number(moderateButton.dataset.responseId),
          action: moderateButton.dataset.liveModerateResponse,
        });
      }
    });
  }

  function sendPresenterControl(socket, sessionId, payload, currentState, onState) {
    const body = { session_id: sessionId, ...payload };
    const fallback = () => fetch(`/live/api/sessions/${sessionId}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => response.json())
      .then((json) => {
        if (json.ok && json.session) onState(json.session);
      })
      .catch(() => onState(currentState));
    emitWithHttpFallback(
      socket,
      "live:presenter_control",
      body,
      (ack) => {
        if (ack && ack.ok && ack.session) onState(ack.session);
      },
      fallback,
    );
  }

  function sendModeration(socket, sessionId, payload) {
    if (socket) {
      socket.emit("live:moderate_response", { session_id: sessionId, ...payload });
      return;
    }
    fetch(
      `/live/api/sessions/${sessionId}/activities/${payload.activity_id}/responses/${payload.response_id}/moderate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: payload.action }),
      },
    ).catch(() => {});
  }

  function renderPresenter(root, state, canControl) {
    const status = root.querySelector("[data-live-status]");
    if (status) {
      status.textContent = state.estado || "draft";
    }
    renderParticipantCounter(root, state);
    const list = root.querySelector("[data-live-activity-list]");
    if (list) {
      list.innerHTML =
        (state.activities || [])
          .map((activity) => renderActivityListItem(activity, state.active_activity_id, canControl))
          .join("") || `<p class="muted">Sin actividades.</p>`;
    }
    const active =
      (state.activities || []).find((activity) => activity.id === state.active_activity_id) ||
      (state.activities || []).find((activity) => activity.estado === "open") ||
      (state.activities || [])[0];
    renderActivity(root, active);
  }

  function renderParticipantCounter(root, state) {
    const counter = root.querySelector("[data-live-connected-count]");
    if (!counter) return;
    const rawCount = state.connected_count ?? state.participant_count ?? 0;
    const connectedCount = Math.max(0, Number(rawCount) || 0);
    counter.textContent = String(connectedCount);
    const label = root.querySelector("[data-live-connected-label]");
    if (label) label.textContent = connectedCount === 1 ? "conectado" : "conectados";
  }

  function renderActivityListItem(activity, activeActivityId, canControl) {
    const activeClass = activity.id === activeActivityId || activity.estado === "open" ? " is-selected" : "";
    const timerSeconds = activity.payload?.timer_seconds || activity.config?.timer_seconds || "";
    const timerButton = timerSeconds
      ? `<button class="button" type="button" data-live-activity-control="set_timer" data-activity-id="${activity.id}" data-timer-seconds="${timerSeconds}">Timer</button>`
      : "";
    const typeLabel = activityTypeLabel(activity.tipo);
    const controls = canControl
      ? `<span class="actions">
          <button class="button button-primary" type="button" data-live-activity-control="go_to_slide" data-activity-id="${activity.id}">Ir</button>
          <button class="button" type="button" data-live-activity-control="close_activity" data-activity-id="${activity.id}">Cerrar</button>
          <button class="button" type="button" data-live-activity-control="hide_results" data-activity-id="${activity.id}">Ocultar</button>
          <button class="button" type="button" data-live-activity-control="reveal_results" data-activity-id="${activity.id}">Revelar</button>
          ${timerButton}
        </span>`
      : "";
    return `<div class="live-activity-item${activeClass}">
      <span class="live-activity-item-main">
        <span class="live-activity-kicker">Slide ${Number(activity.orden || 0)} - ${escapeHtml(typeLabel)}</span>
        <strong>${escapeHtml(activity.titulo)}</strong>
        <small>${escapeHtml(activity.estado || "draft")}</small>
      </span>
      ${controls}
    </div>`;
  }

  function initializeParticipant(sessionState, activityState) {
    const root = document.querySelector("[data-live-participant]");
    if (!root) return;
    const sessionId = Number(root.dataset.sessionId);
    const code = root.dataset.sessionCode;
    const participantToken = root.dataset.participantToken;
    let activityId = Number(root.dataset.activityId || 0);
    let socket = null;

    if (activityState) {
      renderActivity(root, activityState);
    }

    if (window.io) {
      socket = window.io();
      socket.emit("live:join_session", {
        session_id: sessionId,
        code,
        participant_token: participantToken,
      });
      socket.on("live:session_state", (state) => {
        if (state.mode === "guided" && state.active_activity_id && state.active_activity_id !== activityId) {
          window.location.href = `/live/s/${encodeURIComponent(code)}/activity/${state.active_activity_id}`;
        }
      });
      socket.on("live:activity_state", (activity) => {
        if (Number(activity.id) === activityId) {
          renderActivity(root, activity);
        }
      });
      socket.on("live:results_updated", (payload) => {
        if (Number(payload.activity_id) === activityId) {
          renderResults(root, payload.results);
        }
      });
    }

    const form = root.querySelector("[data-live-response-form]");
    if (form) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const payload = responsePayloadFromForm(form);
        submitParticipantResponse(root, socket, code, sessionId, activityId, participantToken, payload);
      });
    }

    root.addEventListener("click", (event) => {
      const button = event.target.closest("[data-live-upvote]");
      if (!button) return;
      sendUpvote(root, socket, code, sessionId, activityId, participantToken, Number(button.dataset.responseId));
    });
  }

  function submitParticipantResponse(root, socket, code, sessionId, activityId, participantToken, payload) {
    const status = root.querySelector("[data-live-response-status]");
    if (status) status.textContent = "Enviando...";
    const body = { session_id: sessionId, code, activity_id: activityId, participant_token: participantToken, payload };
    const done = (ack) => {
      if (!ack || !ack.ok) {
        if (status) status.textContent = ack?.error || "No se pudo enviar.";
        return;
      }
      if (status) status.textContent = "Respuesta guardada.";
      if (ack.results) renderResults(root, ack.results);
    };
    const fallback = () => fetch(`/live/api/s/${encodeURIComponent(code)}/activities/${activityId}/responses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    })
      .then((response) => response.json())
      .then(done)
      .catch(() => done({ ok: false, error: "No se pudo enviar." }));
    emitWithHttpFallback(socket, "live:submit_response", body, done, fallback);
  }

  function sendUpvote(root, socket, code, sessionId, activityId, participantToken, responseId) {
    const body = { session_id: sessionId, code, activity_id: activityId, response_id: responseId, participant_token: participantToken };
    const done = (ack) => {
      if (ack && ack.ok && ack.results) renderResults(root, ack.results);
    };
    const fallback = () => fetch(`/live/api/s/${encodeURIComponent(code)}/activities/${activityId}/responses/${responseId}/upvote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then((response) => response.json())
      .then(done)
      .catch(() => {});
    emitWithHttpFallback(socket, "live:upvote_response", body, done, fallback);
  }

  function emitWithHttpFallback(socket, eventName, body, onAck, fallback, timeoutMs = 3500) {
    if (!socket || !socket.connected) {
      fallback();
      return;
    }
    let settled = false;
    const timer = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      fallback();
    }, timeoutMs);
    socket.emit(eventName, body, (ack) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      onAck(ack);
    });
  }

  function responsePayloadFromForm(form) {
    const data = new FormData(form);
    if (data.has("idea")) return { idea: String(data.get("idea") || "") };
    if (data.has("choice")) return { choice: String(data.get("choice") || "") };
    if (data.has("question")) return { question: String(data.get("question") || "") };
    if (data.has("answer")) return { answer: String(data.get("answer") || "") };

    const ratings = {};
    const points = {};
    const matrix = {};
    data.forEach((value, key) => {
      if (key.startsWith("scale__")) {
        ratings[key.slice("scale__".length)] = Number(value);
      }
      if (key.startsWith("points__")) {
        points[key.slice("points__".length)] = Number(value || 0);
      }
      if (key.startsWith("matrix_x__")) {
        const item = key.slice("matrix_x__".length);
        matrix[item] = { ...(matrix[item] || {}), x: Number(value) };
      }
      if (key.startsWith("matrix_y__")) {
        const item = key.slice("matrix_y__".length);
        matrix[item] = { ...(matrix[item] || {}), y: Number(value) };
      }
    });
    if (Object.keys(ratings).length) return { ratings };
    if (Object.keys(points).length) return { points };
    if (Object.keys(matrix).length) return { ratings: matrix };
    return { ranking: data.getAll("ranking").map((item) => String(item || "").trim()).filter(Boolean) };
  }

  function renderActivity(root, activity) {
    root.dataset.liveShowResults = activity?.payload?.show_results === false ? "false" : "true";
    root.dataset.liveActivityType = activity?.tipo || "";
    const target = root.querySelector("[data-live-current-activity]");
    if (target) {
      const timer = renderTimer(activity);
      target.innerHTML = activity
        ? `<p class="eyebrow">${escapeHtml(activityTypeLabel(activity.tipo))} - Slide ${Number(activity.orden || 0)}</p><h2>${escapeHtml(activity.titulo)}</h2><p>${escapeHtml(activity.prompt)}</p>${timer}`
        : `<p class="muted">Sin actividad seleccionada.</p>`;
    }
    if (activity?.tipo === "content_slide") {
      renderContentSlide(root, activity);
      return;
    }
    renderResults(root, activity?.results);
  }

  function renderContentSlide(root, activity) {
    if (liveChart) {
      liveChart.destroy();
      liveChart = null;
    }
    const chartCanvas = root.querySelector("[data-live-chart]");
    const chartWrap = chartCanvas?.closest(".live-chart-wrap");
    const wordCloud = root.querySelector("[data-live-wordcloud]");
    const list = root.querySelector("[data-live-results-list]");
    if (chartCanvas) chartCanvas.hidden = true;
    if (chartWrap) chartWrap.hidden = true;
    if (wordCloud) {
      wordCloud.innerHTML = "";
      wordCloud.hidden = true;
    }
    if (!list) return;
    const config = activity.config || {};
    const body = config.body ? `<div class="live-content-slide-body">${escapeHtml(config.body)}</div>` : "";
    const media = config.media_url ? `<img class="live-content-slide-media" src="${escapeHtml(config.media_url)}" alt="">` : "";
    const qr = config.layout === "qr"
      ? `<div class="live-content-slide-qr">
          ${root.dataset.sessionQrUrl ? `<img src="${escapeHtml(root.dataset.sessionQrUrl)}" alt="">` : ""}
          <strong>${escapeHtml(root.dataset.sessionCode || "")}</strong>
          ${root.dataset.sessionJoinUrl ? `<code>${escapeHtml(root.dataset.sessionJoinUrl)}</code>` : ""}
        </div>`
      : "";
    list.innerHTML = `<article class="live-content-slide live-content-slide-${escapeHtml(config.layout || "text")}">${body}${media}${qr}</article>`;
  }

  function renderTimer(activity) {
    if (!activity?.payload?.timer_seconds) return "";
    return `<p class="tag">Timer: ${Number(activity.payload.timer_seconds)}s</p>`;
  }

  function activityTypeLabel(type) {
    const labels = {
      brainstorm: "Lluvia de ideas",
      multiple_choice: "Opción múltiple",
      scale: "Escala",
      ranking: "Ranking",
      points_100: "100 puntos",
      matrix_2x2: "Matriz 2x2",
      qa: "Q&A",
      quiz_choice: "Quiz",
      quiz_text: "Quiz texto",
      content_slide: "Diapositiva",
    };
    return labels[type] || String(type || "Slide");
  }

  function renderResults(root, results) {
    const chartCanvas = root.querySelector("[data-live-chart]");
    const chartWrap = chartCanvas?.closest(".live-chart-wrap");
    const wordCloud = root.querySelector("[data-live-wordcloud]");
    const list = root.querySelector("[data-live-results-list]");
    const resultsWrap = root.querySelector(".live-presentation-results");
    if (liveChart) {
      liveChart.destroy();
      liveChart = null;
    }
    resultsWrap?.classList.remove("is-list-only");
    if (wordCloud) {
      wordCloud.innerHTML = "";
      wordCloud.hidden = true;
    }
    if (list) list.innerHTML = "";
    if (chartCanvas) chartCanvas.hidden = true;
    if (chartWrap) chartWrap.hidden = true;
    if (!results) return;

    if (root.matches("[data-live-participant]") && root.dataset.liveShowResults === "false") {
      if (list) list.innerHTML = `<p class="muted">Los resultados se mostrarán cuando el presentador los revele.</p>`;
      return;
    }

    if (results.type === "multiple_choice") {
      renderBarResults(chartCanvas, results.options || [], "count", "Respuestas");
      if (list) list.innerHTML = `<p class="muted">${results.total || 0} respuestas</p>`;
      return;
    }

    if (results.type === "brainstorm") {
      renderBrainstorm(wordCloud, list, results);
      return;
    }

    if (results.type === "scale") {
      renderBarResults(chartCanvas, results.items || [], "average", "Promedio");
      renderSimpleList(list, results.items || [], (item) => `${item.label}: ${item.average} (${item.count})`);
      return;
    }

    if (results.type === "ranking") {
      renderBarResults(chartCanvas, results.items || [], "score", "Puntaje Borda");
      renderSimpleList(list, results.items || [], (item, index) => `${index + 1}. ${item.label}: ${item.score}`);
      return;
    }

    if (results.type === "points_100") {
      renderBarResults(chartCanvas, results.items || [], "points", "Puntos");
      renderSimpleList(list, results.items || [], (item) => `${item.label}: ${item.points} pts`);
      return;
    }

    if (results.type === "matrix_2x2") {
      renderMatrix(chartCanvas, results);
      renderSimpleList(list, results.items || [], (item) => `${item.label}: X ${item.x}, Y ${item.y}`);
      return;
    }

    if (results.type === "qa") {
      renderQa(root, list, results);
      return;
    }

    if (results.type === "quiz_choice") {
      renderBarResults(chartCanvas, results.options || [], "count", "Respuestas");
      renderLeaderboard(list, results);
      return;
    }

    if (results.type === "quiz_text") {
      renderBarResults(chartCanvas, results.answers || [], "count", "Respuestas");
      renderLeaderboard(list, results);
    }
  }

  function renderBarResults(canvas, items, valueKey, label) {
    if (!canvas || !window.Chart) return;
    const chartWrap = canvas.closest(".live-chart-wrap");
    if (chartWrap) chartWrap.hidden = false;
    canvas.hidden = false;
    liveChart = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: items.map((item) => item.label),
        datasets: [
          {
            label,
            data: items.map((item) => Number(item[valueKey] || 0)),
            backgroundColor: ["#2f5a74", "#e18024", "#728b50", "#8d6a0f", "#7a4968", "#547f8f"],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: { legend: { display: false } },
      },
    });
  }

  function renderMatrix(canvas, results) {
    if (!canvas || !window.Chart) return;
    const chartWrap = canvas.closest(".live-chart-wrap");
    if (chartWrap) chartWrap.hidden = false;
    canvas.hidden = false;
    const min = Number(results.min ?? -5);
    const max = Number(results.max ?? 5);
    liveChart = new Chart(canvas.getContext("2d"), {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Promedio",
            data: (results.items || []).map((item) => ({ x: Number(item.x || 0), y: Number(item.y || 0), label: item.label })),
            backgroundColor: "#e18024",
            pointRadius: 7,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { min, max, title: { display: true, text: axisLabel(results.x_axis) } },
          y: { min, max, title: { display: true, text: axisLabel(results.y_axis) } },
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (context) => `${context.raw.label}: X ${context.raw.x}, Y ${context.raw.y}`,
            },
          },
        },
      },
    });
  }

  function axisLabel(axis) {
    if (!axis) return "";
    return `${axis.min_label || "Bajo"} / ${axis.max_label || "Alto"}`;
  }

  function renderBrainstorm(wordCloud, list, results) {
    const hasWords = Boolean((results.words || []).length);
    const canRenderCloud = Boolean(wordCloud && window.WordCloud && hasWords);
    const resultsWrap = list?.closest(".live-presentation-results");
    const isPresentation = Boolean(list?.closest(".live-presentation-shell"));
    resultsWrap?.classList.toggle("is-list-only", !canRenderCloud);
    if (canRenderCloud) {
      wordCloud.hidden = false;
      const cloudWords = isPresentation ? (results.words || []).slice(0, 12) : results.words || [];
      const maxWeight = Math.max(...cloudWords.map((item) => Number(item[1] || 1)), 1);
      const cloudWordCount = cloudWords.length || 1;
      const cloudMinSide = Math.max(300, Math.min(wordCloud.clientWidth || 0, wordCloud.clientHeight || 0));
      const densityFactor = cloudWordCount <= 8 ? 4.6 : cloudWordCount <= 16 ? 7.2 : 8.8;
      const baseWeight = isPresentation ? Math.max(34, Math.min(88, cloudMinSide / densityFactor)) : 12;
      WordCloud(wordCloud, {
        list: cloudWords,
        weightFactor: (weight) => baseWeight * Math.sqrt(Number(weight || 1) / maxWeight),
        gridSize: isPresentation ? Math.max(8, Math.round(cloudMinSide / 70)) : 10,
        minSize: isPresentation ? 12 : 0,
        rotateRatio: isPresentation ? 0 : 0.2,
        ellipticity: isPresentation ? 0.5 : 0.65,
        shrinkToFit: isPresentation,
        drawOutOfBound: false,
        color: isPresentation ? "#1f3849" : "random-dark",
        backgroundColor: "transparent",
      });
    }
    if (list) {
      const ideas = isPresentation ? groupBrainstormIdeas(results.ideas || []) : (results.ideas || []).slice().reverse();
      list.innerHTML =
        ideas
          .map((item) => `<div class="live-idea">
            <span class="live-idea-text">${escapeHtml(item.idea)}</span>
            ${item.count > 1 ? `<span class="live-idea-count">${item.count} menciones</span>` : ""}
            ${statusTag(item.status)}
          </div>`)
          .join("") || `<p class="muted">Sin ideas todavía.</p>`;
    }
  }

  function groupBrainstormIdeas(ideas) {
    const grouped = new Map();
    ideas.forEach((item, index) => {
      const idea = String(item.idea || "").trim();
      if (!idea) return;
      const key = normalizeIdeaKey(idea);
      const createdAt = item.created_at ? Date.parse(item.created_at) || 0 : 0;
      const current = grouped.get(key);
      if (!current) {
        grouped.set(key, { ...item, idea, count: 1, latestAt: createdAt, latestIndex: index });
        return;
      }
      current.count += 1;
      if (createdAt > current.latestAt || (!createdAt && index > current.latestIndex)) {
        current.idea = idea;
        current.status = item.status;
        current.created_at = item.created_at;
        current.latestAt = createdAt;
        current.latestIndex = index;
      }
    });
    return Array.from(grouped.values()).sort((left, right) => {
      if (right.count !== left.count) return right.count - left.count;
      if (right.latestAt !== left.latestAt) return right.latestAt - left.latestAt;
      return right.latestIndex - left.latestIndex;
    });
  }

  function normalizeIdeaKey(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function renderQa(root, list, results) {
    if (!list) return;
    const canControl = root.dataset.canControl === "true";
    const canUpvote = root.matches("[data-live-participant]");
    const activityId = currentActivityId(root);
    list.innerHTML =
      (results.questions || [])
        .map((item) => {
          const controls = canControl
            ? `<span class="actions">
                <button class="button" type="button" data-live-moderate-response="approve" data-activity-id="${activityId}" data-response-id="${item.id}">Aprobar</button>
                <button class="button" type="button" data-live-moderate-response="show" data-activity-id="${activityId}" data-response-id="${item.id}">Mostrar</button>
                <button class="button" type="button" data-live-moderate-response="answer" data-activity-id="${activityId}" data-response-id="${item.id}">Respondida</button>
              </span>`
            : "";
          const upvote = canUpvote
            ? `<button class="button" type="button" data-live-upvote data-response-id="${item.id}">+1</button>`
            : "";
          return `<div class="live-qa-item">
            <strong>${escapeHtml(item.question)}</strong>
            <small>${Number(item.upvotes || 0)} votos ${statusTag(item.status)} ${item.shown ? '<span class="tag">En pantalla</span>' : ""}</small>
            <span class="actions">${upvote}${controls}</span>
          </div>`;
        })
        .join("") || `<p class="muted">Sin preguntas todavía.</p>`;
  }

  function currentActivityId(root) {
    const active = root.querySelector(".live-activity-item.is-selected [data-live-activity-control]");
    if (active) return active.dataset.activityId;
    return root.dataset.activityId || "";
  }

  function renderLeaderboard(list, results) {
    if (!list) return;
    const leaderboard = (results.leaderboard || [])
      .map((item) => `<div class="live-idea"><strong>${item.rank}. ${escapeHtml(item.label)}</strong> - ${item.score} pts</div>`)
      .join("");
    list.innerHTML = `<p class="muted">${results.correct || 0}/${results.total || 0} correctas</p>${leaderboard}`;
  }

  function renderSimpleList(list, items, formatter) {
    if (!list) return;
    list.innerHTML =
      items.map((item, index) => `<div class="live-idea">${escapeHtml(formatter(item, index))}</div>`).join("") ||
      `<p class="muted">Sin respuestas todavía.</p>`;
  }

  function statusTag(status) {
    if (!status || status === "approved") return "";
    return ` <span class="tag">${escapeHtml(status)}</span>`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
