(() => {
  const root = document.querySelector("[data-audience]");
  if (!root) return;

  const code = root.dataset.code;
  let participantToken = root.dataset.token || window.MENTI_PARTICIPANT_TOKEN || localStorage.getItem(`menti:${code}:token`);
  const state = { session: null, socket: null, timer: null, score: 0 };

  const questionArea = document.querySelector("[data-question-area]");
  const statusNode = document.querySelector("[data-audience-status]");
  const scoreNode = document.querySelector("[data-score]");
  const connectedNode = document.querySelector("[data-connected-count]");

  connect();
  loadSession();

  function connect() {
    if (!window.io) return;
    state.socket = window.io({ reconnection: true });
    state.socket.on("connect", join);
    state.socket.on("session_state", (next) => {
      state.session = next;
      render();
    });
    state.socket.on("participant_count", (payload) => {
      if (connectedNode) connectedNode.textContent = `${payload.connected_count || 0} conectados`;
    });
    state.socket.on("disconnect", () => {
      if (statusNode) statusNode.textContent = "Reconectando...";
    });
  }

  function join() {
    if (!state.socket) return;
    state.socket.emit("join_session", { code, participant_token: participantToken }, (ack) => {
      if (!ack?.ok) {
        if (statusNode) statusNode.textContent = ack?.error || "No se pudo unir.";
        return;
      }
      participantToken = ack.participant_token;
      localStorage.setItem(`menti:${code}:token`, participantToken);
      state.session = ack.session;
      if (statusNode) statusNode.textContent = "Conectado";
      render();
    });
  }

  async function loadSession() {
    const response = await fetch(`/api/sessions/${code}`);
    const json = await response.json();
    if (json.ok) {
      state.session = json.session;
      render();
    }
  }

  function render() {
    clearTimer();
    const question = activeQuestion();
    if (!question) {
      questionArea.innerHTML = "<h2>Esperando al presentador</h2><p class=\"muted\">La pregunta activa aparecera automaticamente.</p>";
      return;
    }
    if (state.session.status !== "active") {
      questionArea.innerHTML = `<h2>${escapeHtml(question.title)}</h2><p class="muted">La sesion aun no esta activa.</p>`;
      return;
    }
    if (!question.is_open) {
      questionArea.innerHTML = `<h2>${escapeHtml(question.title)}</h2><p class="muted">La votacion esta cerrada.</p>`;
      return;
    }
    questionArea.innerHTML = `
      <p class="eyebrow">${labelForType(question.type)}</p>
      <h2>${escapeHtml(question.title)}</h2>
      <p>${escapeHtml(question.prompt)}</p>
      ${contentMarkup(question)}
      ${answerMarkup(question)}
      <p class="muted" data-submit-status></p>
    `;
    if (question.type === "quiz") startTimer(question.timer?.remaining ?? question.config?.timer_seconds ?? 30);
    wireAnswer(question);
  }

  function answerMarkup(question) {
    if (question.type === "content_slide") {
      return "";
    }
    if (question.type === "multiple_choice" || question.type === "quiz") {
      const buttons = question.options
        .map((option) => `<button type="button" data-option-id="${option.id}">${escapeHtml(option.label)}</button>`)
        .join("");
      return `<div class="answer-options">${buttons}</div>${question.type === "quiz" ? '<strong data-timer></strong>' : ""}`;
    }
    if (question.type === "word_cloud") {
      return `
        <form data-answer-form>
          <input name="text" maxlength="80" placeholder="Escribe una palabra o frase corta" required>
          <button type="submit">Enviar</button>
        </form>
      `;
    }
    if (question.type === "open_text") {
      return `
        <form data-answer-form>
          <textarea name="text" rows="4" maxlength="500" placeholder="Escribe tu respuesta" required></textarea>
          <button type="submit">Enviar</button>
        </form>
      `;
    }
    if (question.type === "scale") {
      const min = question.config?.min || 1;
      const max = question.config?.max || 5;
      const buttons = [];
      for (let value = min; value <= max; value += 1) {
        buttons.push(`<button type="button" data-scale-value="${value}">${value}</button>`);
      }
      return `<div class="scale-options">${buttons.join("")}</div>`;
    }
    if (question.type === "ranking") {
      return `
        <div class="ranking-list" data-ranking-list>
          ${question.options.map((option) => rankingRow(option)).join("")}
        </div>
        <button type="button" data-submit-ranking>Enviar ranking</button>
      `;
    }
    return "";
  }

  function contentMarkup(question) {
    if (question.type !== "content_slide") return "";
    const body = question.config?.body ? `<p class="content-body">${escapeHtml(question.config.body)}</p>` : "";
    const qr = question.config?.show_qr
      ? `<img class="audience-qr" src="${escapeHtml(state.session.qr_url)}" alt="QR para entrar">`
      : "";
    return `<div class="audience-content-slide">${body}${qr}</div>`;
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
      if (button.dataset.move === "up" && row.previousElementSibling) {
        rankingList.insertBefore(row, row.previousElementSibling);
      }
      if (button.dataset.move === "down" && row.nextElementSibling) {
        rankingList.insertBefore(row.nextElementSibling, row);
      }
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
      </div>
    `;
  }

  function submit(question, payload) {
    setSubmitStatus("Enviando...");
    const body = { code, question_id: question.id, participant_token: participantToken, payload };
    if (state.socket?.connected) {
      state.socket.emit("submit_response", body, handleSubmitAck);
      return;
    }
    fetch(`/api/sessions/${code}/questions/${question.id}/responses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((response) => response.json())
      .then(handleSubmitAck)
      .catch(() => setSubmitStatus("No se pudo enviar. Revisa tu conexion."));
  }

  function handleSubmitAck(ack) {
    if (!ack?.ok) {
      setSubmitStatus(ack?.error || "No se pudo enviar.");
      return;
    }
    participantToken = ack.participant_token || participantToken;
    localStorage.setItem(`menti:${code}:token`, participantToken);
    state.score = ack.score || state.score;
    if (scoreNode) scoreNode.textContent = `${state.score} pts`;
    setSubmitStatus("Respuesta recibida.");
  }

  function activeQuestion() {
    return state.session?.questions.find((question) => question.id === state.session.active_question_id) || null;
  }

  function startTimer(seconds) {
    const timerNode = questionArea.querySelector("[data-timer]");
    if (!timerNode) return;
    let remaining = Number(seconds || 0);
    const paint = () => {
      timerNode.textContent = `${remaining}s`;
      if (remaining <= 0) {
        clearTimer();
        setSubmitStatus("Tiempo agotado.");
        questionArea.querySelectorAll("button, input, textarea").forEach((control) => {
          control.disabled = true;
        });
      }
      remaining -= 1;
    };
    paint();
    state.timer = window.setInterval(paint, 1000);
  }

  function clearTimer() {
    if (state.timer) window.clearInterval(state.timer);
    state.timer = null;
  }

  function setSubmitStatus(message) {
    const node = questionArea.querySelector("[data-submit-status]");
    if (node) node.textContent = message;
  }

  function labelForType(type) {
    return {
      multiple_choice: "Opcion multiple",
      content_slide: "Contenido",
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
