(() => {
  const code = window.MENTI_SESSION_CODE;
  const state = { session: null, socket: null, chart: null };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const createForm = $("[data-create-session]");
  const questionForm = $("[data-question-form]");
  const questionType = $("[data-question-type]");
  const questionList = $("[data-question-list]");
  const stage = $("[data-stage]");
  const alt = $("[data-result-alt]");
  const chartCanvas = $("[data-result-chart]");
  const statusPill = $("[data-session-status]");
  const connectedCount = $("[data-connected-count]");
  const templateStrip = $("[data-template-strip]");
  const moderationPanel = $("[data-moderation-panel]");
  const insightsBox = $("[data-insights-box]");
  const themeSelect = $("[data-theme-select]");

  createForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = new FormData(createForm).get("title");
    const json = await postJson("/api/sessions", { title });
    if (json.ok) window.location.assign(`/admin?code=${json.session.code}`);
    else alert(json.error || "No se pudo crear la sesion.");
  });

  questionType?.addEventListener("change", syncQuestionFields);
  questionForm?.addEventListener("submit", saveQuestion);
  $("[data-cancel-edit]")?.addEventListener("click", resetQuestionForm);
  themeSelect?.addEventListener("change", () => controlSession("set_theme", { theme: themeSelect.value }));
  templateStrip?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-template-index]");
    if (!button || !state.templates) return;
    const template = state.templates[Number(button.dataset.templateIndex)];
    if (template) populateQuestionPayload(template.payload);
  });

  $$("[data-control]").forEach((button) => {
    button.addEventListener("click", () => controlSession(button.dataset.control));
  });

  questionList?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button || !state.session) return;
    const id = Number(button.closest("[data-question-id]")?.dataset.questionId || 0);
    const action = button.dataset.action;
    if (action === "edit") populateQuestionForm(id);
    if (action === "delete" && confirm("Eliminar esta pregunta?")) {
      await fetch(`/api/sessions/${state.session.code}/questions/${id}`, { method: "DELETE" });
      await loadSession();
    }
    if (action === "duplicate") {
      const json = await postJson(`/api/sessions/${state.session.code}/questions/${id}/duplicate`, {});
      if (json.ok) {
        state.session = json.session;
        render();
      }
    }
    if (action === "up" || action === "down") moveQuestion(id, action);
    if (action === "go") controlSession("go", { index: questionIndex(id) });
  });

  if (code) {
    connectSocket();
    loadTemplates();
    loadSession();
  } else {
    syncQuestionFields();
  }

  function connectSocket() {
    if (!window.io) return;
    state.socket = window.io({ reconnection: true });
    state.socket.on("connect", () => state.socket.emit("join_session", { code }));
    state.socket.on("session_state", (next) => {
      state.session = next;
      render();
    });
    state.socket.on("results_updated", (payload) => {
      if (!state.session) return;
      state.session.questions = state.session.questions.map((question) =>
        question.id === payload.question_id ? { ...question, results: payload.results } : question,
      );
      renderStage();
    });
    state.socket.on("participant_count", (payload) => {
      if (connectedCount) connectedCount.textContent = payload.connected_count || 0;
    });
  }

  async function loadTemplates() {
    const json = await getJson("/api/question-templates");
    if (!json.ok) return;
    state.templates = json.templates || [];
    renderTemplates();
  }

  async function loadSession() {
    const json = await getJson(`/api/sessions/${code}`);
    if (json.ok) {
      state.session = json.session;
      render();
    }
  }

  async function saveQuestion(event) {
    event.preventDefault();
    if (!state.session) return alert("Selecciona una sesion primero.");
    const form = new FormData(questionForm);
    const payload = {
      type: String(form.get("type") || ""),
      title: String(form.get("title") || ""),
      prompt: String(form.get("prompt") || ""),
      options: splitLines(form.get("options")),
      config: {},
    };
    if (payload.type === "scale") {
      payload.config = { min: Number(form.get("min") || 1), max: Number(form.get("max") || 5) };
      payload.options = [];
    }
    if (payload.type === "quiz") {
      payload.correct_option_labels = splitLines(form.get("correct"));
      payload.config = {
        timer_seconds: Number(form.get("timer_seconds") || 30),
        points: Number(form.get("points") || 100),
      };
    }
    if (payload.type === "word_cloud" || payload.type === "open_text") {
      payload.config.moderation = String(form.get("moderation") || "none");
    }
    if (payload.type === "word_cloud" || payload.type === "open_text") payload.options = [];

    const id = form.get("question_id");
    const url = id
      ? `/api/sessions/${state.session.code}/questions/${id}`
      : `/api/sessions/${state.session.code}/questions`;
    const json = await postJson(url, payload, id ? "PATCH" : "POST");
    if (!json.ok) return alert(json.error || "No se pudo guardar.");
    state.session = json.session;
    resetQuestionForm();
    render();
  }

  function syncQuestionFields() {
    const type = questionType?.value || "multiple_choice";
    const optionsField = $("[data-options-field]");
    const scaleField = $("[data-scale-field]");
    const quizField = $("[data-quiz-field]");
    const moderationField = $("[data-moderation-field]");
    if (optionsField) optionsField.hidden = !["multiple_choice", "ranking", "quiz"].includes(type);
    if (scaleField) scaleField.hidden = type !== "scale";
    if (quizField) quizField.hidden = type !== "quiz";
    if (moderationField) moderationField.hidden = !["word_cloud", "open_text"].includes(type);
  }

  function populateQuestionForm(id) {
    const question = state.session?.questions.find((item) => item.id === id);
    if (!question) return;
    questionForm.question_id.value = question.id;
    questionForm.type.value = question.type;
    questionForm.title.value = question.title;
    questionForm.prompt.value = question.prompt;
    questionForm.options.value = (question.options || []).map((option) => option.label).join("\n");
    questionForm.min.value = question.config?.min || 1;
    questionForm.max.value = question.config?.max || 5;
    questionForm.correct.value = (question.options || [])
      .filter((option) => option.is_correct)
      .map((option) => option.label)
      .join("\n");
    questionForm.timer_seconds.value = question.config?.timer_seconds || 30;
    questionForm.points.value = question.config?.points || 100;
    questionForm.moderation.value = question.config?.moderation || "none";
    $("[data-save-question]").textContent = "Guardar cambios";
    syncQuestionFields();
    questionForm.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function resetQuestionForm() {
    questionForm?.reset();
    if (questionForm?.question_id) questionForm.question_id.value = "";
    if ($("[data-save-question]")) $("[data-save-question]").textContent = "Agregar pregunta";
    syncQuestionFields();
  }

  function populateQuestionPayload(payload) {
    resetQuestionForm();
    questionForm.type.value = payload.type || "multiple_choice";
    questionForm.title.value = payload.title || "";
    questionForm.prompt.value = payload.prompt || "";
    questionForm.options.value = (payload.options || []).join("\n");
    questionForm.correct.value = (payload.correct_option_labels || []).join("\n");
    questionForm.min.value = payload.config?.min || 1;
    questionForm.max.value = payload.config?.max || 5;
    questionForm.timer_seconds.value = payload.config?.timer_seconds || 30;
    questionForm.points.value = payload.config?.points || 100;
    questionForm.moderation.value = payload.config?.moderation || "none";
    syncQuestionFields();
  }

  async function moveQuestion(id, direction) {
    const questions = state.session.questions.slice();
    const index = questions.findIndex((item) => item.id === id);
    const nextIndex = direction === "up" ? index - 1 : index + 1;
    if (index < 0 || nextIndex < 0 || nextIndex >= questions.length) return;
    [questions[index], questions[nextIndex]] = [questions[nextIndex], questions[index]];
    const json = await postJson(`/api/sessions/${state.session.code}/questions/reorder`, {
      question_ids: questions.map((item) => item.id),
    });
    if (json.ok) {
      state.session = json.session;
      render();
    }
  }

  function questionIndex(id) {
    return state.session.questions.findIndex((item) => item.id === id);
  }

  async function controlSession(action, extra = {}) {
    if (!state.session) return;
    if (state.socket?.connected) {
      state.socket.emit("presenter_control", { code: state.session.code, action, ...extra }, (ack) => {
        if (ack?.ok) {
          state.session = ack.session;
          render();
        } else if (ack?.error) {
          alert(ack.error);
        }
      });
      return;
    }
    const json = await postJson(`/api/sessions/${state.session.code}/control`, { action, ...extra });
    if (json.ok) {
      state.session = json.session;
      render();
    }
  }

  function render() {
    if (!state.session) return;
    document.body.dataset.theme = state.session.theme || "civic";
    if (themeSelect) themeSelect.value = state.session.theme || "civic";
    if (statusPill) statusPill.textContent = `${state.session.code} · ${state.session.status}`;
    if (connectedCount) connectedCount.textContent = state.session.connected_count || 0;
    renderQuestionList();
    renderStage();
    renderInsights();
  }

  function renderTemplates() {
    if (!templateStrip) return;
    templateStrip.innerHTML = (state.templates || [])
      .map((template, index) => `<button type="button" class="secondary" data-template-index="${index}">${escapeHtml(template.name)}</button>`)
      .join("");
  }

  function renderQuestionList() {
    if (!questionList || !state.session) return;
    questionList.innerHTML = state.session.questions
      .map((question, index) => {
        const active = question.id === state.session.active_question_id ? " is-active" : "";
        return `
          <article class="question-item${active}" data-question-id="${question.id}">
            <small>${String(index + 1).padStart(2, "0")} · ${labelForType(question.type)} · ${question.is_open ? "abierta" : "cerrada"}</small>
            <h3>${escapeHtml(question.title)}</h3>
            <p>${escapeHtml(question.prompt)}</p>
            <div class="question-actions">
              <button type="button" data-action="go">Ir</button>
              <button type="button" data-action="edit">Editar</button>
              <button type="button" data-action="duplicate">Duplicar</button>
              <button type="button" data-action="up">Subir</button>
              <button type="button" data-action="down">Bajar</button>
              <button type="button" class="danger" data-action="delete">Eliminar</button>
            </div>
          </article>
        `;
      })
      .join("") || '<p class="muted">Agrega preguntas para construir la sesion.</p>';
  }

  function renderStage() {
    const question = activeQuestion();
    clearChart();
    alt.innerHTML = "";
    if (moderationPanel) moderationPanel.innerHTML = "";
    if (!question) {
      stage.innerHTML = '<p class="eyebrow">Sin pregunta activa</p><h2>Agrega una pregunta</h2>';
      return;
    }
    stage.innerHTML = `
      <p class="eyebrow">${labelForType(question.type)} · ${question.is_open ? "votacion abierta" : "votacion cerrada"}</p>
      <h2>${escapeHtml(question.title)}</h2>
      <p>${escapeHtml(question.prompt)}</p>
      ${question.type === "quiz" ? `<strong>${question.config.timer_seconds || 30}s · ${question.config.points || 100} pts</strong>` : ""}
    `;
    renderResults(question);
    renderModeration(question);
  }

  function renderResults(question) {
    const results = question.results || {};
    if (["multiple_choice", "quiz"].includes(question.type)) {
      renderBarChart(
        results.options.map((option) => option.label),
        results.options.map((option) => option.count),
        question.type === "quiz" ? results.options.map((option) => option.is_correct) : null,
      );
      if (question.type === "quiz" && results.leaderboard?.length) {
        alt.innerHTML = `<ol class="leaderboard">${results.leaderboard
          .map((item) => `<li><strong>${escapeHtml(item.label)}</strong><span>${item.score} pts</span></li>`)
          .join("")}</ol>`;
      }
      return;
    }
    if (question.type === "scale") {
      renderBarChart(
        results.values.map((item) => String(item.value)),
        results.values.map((item) => item.count),
      );
      alt.innerHTML = `<h3>Promedio: ${results.average || 0}</h3>`;
      return;
    }
    if (question.type === "ranking") {
      renderBarChart(
        results.options.map((item) => item.label),
        results.options.map((item) => item.score),
      );
      return;
    }
    if (question.type === "word_cloud") {
      alt.innerHTML = `<div class="word-cloud">${(results.words || [])
        .map((word) => `<span style="font-size:${Math.min(4, 1 + word.count * 0.45)}rem">${escapeHtml(word.text)}</span>`)
        .join("") || '<p class="muted">Sin palabras todavia.</p>'}</div>`;
      return;
    }
    if (question.type === "open_text") {
      alt.innerHTML = `<div class="cards">${(results.cards || [])
        .map((card) => `<article>${escapeHtml(card.text)}</article>`)
        .join("") || '<p class="muted">Sin respuestas todavia.</p>'}</div>`;
    }
  }

  function renderModeration(question) {
    if (!moderationPanel) return;
    const pending = question.pending_responses || [];
    if (!pending.length) {
      moderationPanel.innerHTML = "";
      return;
    }
    moderationPanel.innerHTML = `
      <h3>Moderacion pendiente</h3>
      <div class="cards">${pending
        .map(
          (item) => `
            <article data-response-id="${item.id}">
              <p>${escapeHtml(item.text)}</p>
              <div class="actions">
                <button type="button" data-moderate="approve">Aprobar</button>
                <button type="button" class="danger" data-moderate="reject">Rechazar</button>
              </div>
            </article>
          `,
        )
        .join("")}</div>
    `;
    moderationPanel.querySelectorAll("[data-moderate]").forEach((button) => {
      button.addEventListener("click", () => moderateResponse(question, button));
    });
  }

  function moderateResponse(question, button) {
    const responseId = Number(button.closest("[data-response-id]")?.dataset.responseId || 0);
    const payload = { code: state.session.code, question_id: question.id, response_id: responseId, action: button.dataset.moderate };
    if (state.socket?.connected) {
      state.socket.emit("moderate_response", payload, (ack) => {
        if (!ack?.ok) alert(ack?.error || "No se pudo moderar.");
      });
      return;
    }
    postJson(
      `/api/sessions/${state.session.code}/questions/${question.id}/responses/${responseId}/moderate`,
      { action: button.dataset.moderate },
    ).then((json) => {
      if (!json.ok) alert(json.error || "No se pudo moderar.");
      else loadSession();
    });
  }

  async function renderInsights() {
    if (!insightsBox || !state.session) return;
    const json = await getJson(`/api/sessions/${state.session.code}/insights`);
    if (!json.ok) return;
    insightsBox.hidden = false;
    insightsBox.textContent = `Preguntas: ${json.insights.question_count}\nParticipantes: ${json.insights.participant_count}\nRespuestas: ${json.insights.response_count}`;
  }

  function renderBarChart(labels, values, correctness = null) {
    if (!window.Chart) {
      alt.innerHTML = labels.map((label, index) => `<div class="rank-row">${escapeHtml(label)}: ${values[index]}</div>`).join("");
      return;
    }
    const colors = labels.map((_, index) => {
      if (!correctness) return "#2764e8";
      return correctness[index] ? "#13a976" : "#cbd5e1";
    });
    state.chart = new Chart(chartCanvas, {
      type: "bar",
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 10 }] },
      options: {
        animation: { duration: 350 },
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  function clearChart() {
    if (state.chart) state.chart.destroy();
    state.chart = null;
  }

  function activeQuestion() {
    return state.session?.questions.find((item) => item.id === state.session.active_question_id) || null;
  }

  async function getJson(url) {
    const response = await fetch(url);
    return response.json();
  }

  async function postJson(url, payload, method = "POST") {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
  }

  function splitLines(value) {
    return String(value || "")
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function labelForType(type) {
    return {
      multiple_choice: "Opcion multiple",
      word_cloud: "Nube de palabras",
      scale: "Escala",
      open_text: "Pregunta abierta",
      ranking: "Ranking",
      quiz: "Quiz",
    }[type] || type;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]));
  }
})();
