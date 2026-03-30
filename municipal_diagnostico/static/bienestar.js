(() => {
  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.mensaje || "No se pudo completar la operación.");
    }
    return data;
  }

  function setSaveState(container, label, state = "idle") {
    if (!container) return;
    container.dataset.state = state;
    const target = container.querySelector("[id='wellbeing-save-label']") || document.getElementById("wellbeing-save-label");
    if (target) {
      target.textContent = label;
    }
  }

  const homeForm = document.querySelector("[data-wellbeing-home]");
  if (homeForm) {
    homeForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const startUrl = homeForm.dataset.startUrl;
      const surveyUrl = homeForm.dataset.surveyUrl;
      const formData = new FormData(homeForm);
      const estrato = String(formData.get("estrato") || "E1");
      const button = homeForm.querySelector("button[type='submit']");
      if (button) button.disabled = true;

      try {
        const payload = await postJson(startUrl, { estrato });
        window.location.href = `${surveyUrl}?folio=${encodeURIComponent(payload.hash)}`;
      } catch (error) {
        window.alert(error.message);
      } finally {
        if (button) button.disabled = false;
      }
    });
  }

  const surveyRoot = document.querySelector("[data-wellbeing-survey]");
  if (!surveyRoot) return;

  const folio = surveyRoot.dataset.folio;
  const questionsUrl = surveyRoot.dataset.questionsUrl;
  const surveyUrl = surveyRoot.dataset.surveyUrl;
  const saveUrl = surveyRoot.dataset.saveUrl;

  const dimensionLabel = document.getElementById("wellbeing-dimension-label");
  const progressLabel = document.getElementById("wellbeing-question-progress");
  const statusLabel = document.getElementById("wellbeing-status-label");
  const progressBar = document.getElementById("wellbeing-progress-bar");
  const questionOrder = document.getElementById("wellbeing-question-order");
  const questionDimension = document.getElementById("wellbeing-question-dimension");
  const questionScore = document.getElementById("wellbeing-question-score");
  const questionText = document.getElementById("wellbeing-question-text");
  const questionHint = document.getElementById("wellbeing-question-hint");
  const questionCard = document.getElementById("wellbeing-question-card");
  const optionsContainer = document.getElementById("wellbeing-options");
  const prevButton = document.getElementById("wellbeing-prev");
  const nextButton = document.getElementById("wellbeing-next");
  const saveIndicator = document.getElementById("wellbeing-save-state");
  const percentLabel = document.getElementById("wellbeing-percent-label");
  const answeredCountLabel = document.getElementById("wellbeing-answered-count");
  const pendingCountLabel = document.getElementById("wellbeing-pending-count");
  const stratumLabel = document.getElementById("wellbeing-stratum-label");
  const progressSummary = document.getElementById("wellbeing-progress-summary");
  const progressPending = document.getElementById("wellbeing-progress-pending");
  const progressRestore = document.getElementById("wellbeing-progress-restore");
  const mapStatus = document.getElementById("wellbeing-map-status");
  const questionNav = document.getElementById("wellbeing-question-nav");
  const jumpPendingButton = document.getElementById("wellbeing-jump-pending");
  const feedbackTitle = document.getElementById("wellbeing-feedback-title");
  const feedbackText = document.getElementById("wellbeing-feedback-text");

  let questions = [];
  let currentIndex = 0;
  let completed = false;
  const responses = new Map();
  const surveyMeta = {
    estrato: "--",
    ultimaPregunta: 0,
  };
  let latestSaveToken = 0;

  function currentQuestion() {
    return questions[currentIndex];
  }

  function answeredCount() {
    return Array.from(responses.values()).filter((value) => Number.isFinite(value)).length;
  }

  function firstPendingIndex() {
    const pendingIndex = questions.findIndex((question) => !responses.has(question.id));
    return pendingIndex === -1 ? Math.max(questions.length - 1, 0) : pendingIndex;
  }

  function progressPercent() {
    return questions.length ? Number(((answeredCount() / questions.length) * 100).toFixed(2)) : 0;
  }

  function setFeedback(title, text) {
    if (feedbackTitle) feedbackTitle.textContent = title;
    if (feedbackText) feedbackText.textContent = text;
  }

  function scrollQuestionCard() {
    if (!questionCard) return;
    questionCard.scrollIntoView({ behavior: "smooth", block: "start" });
    if (typeof questionCard.focus === "function") {
      questionCard.focus({ preventScroll: true });
    }
  }

  function pulseQuestionCard() {
    if (!questionCard) return;
    questionCard.classList.remove("is-entering");
    void questionCard.offsetWidth;
    questionCard.classList.add("is-entering");
  }

  function renderProgress() {
    const percent = progressPercent();
    progressBar.dataset.progressValue = String(percent);
    progressBar.style.width = `${percent}%`;
    progressBar.setAttribute("aria-valuenow", String(percent));
  }

  function renderSummary() {
    const answered = answeredCount();
    const pending = Math.max(questions.length - answered, 0);
    const percent = progressPercent();
    if (percentLabel) percentLabel.textContent = `${percent.toFixed(0)}%`;
    if (answeredCountLabel) answeredCountLabel.textContent = String(answered);
    if (pendingCountLabel) pendingCountLabel.textContent = String(pending);
    if (stratumLabel) stratumLabel.textContent = surveyMeta.estrato || "--";
    if (progressSummary) {
      progressSummary.textContent = `${answered} respondidos`;
    }
    if (progressPending) {
      progressPending.textContent = `${pending} pendientes`;
    }
    if (progressRestore) {
      progressRestore.textContent = surveyMeta.ultimaPregunta
        ? `Retoma sugerido desde el reactivo ${Math.min(surveyMeta.ultimaPregunta, questions.length)}.`
        : "La encuesta puede retomarse con el mismo folio.";
    }
    if (mapStatus) {
      mapStatus.textContent = `${currentIndex + 1}/${questions.length}`;
    }
    if (jumpPendingButton) {
      jumpPendingButton.disabled = pending === 0 || firstPendingIndex() === currentIndex;
    }
  }

  function renderQuestionNav() {
    if (!questionNav) return;
    questionNav.innerHTML = "";
    questions.forEach((question, index) => {
      const answered = responses.has(question.id);
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `survey-question-chip ${answered ? "is-answered" : "is-pending"} ${
        index === currentIndex ? "is-current" : ""
      }`;
      chip.innerHTML = `<span>${index + 1}</span>`;
      chip.setAttribute(
        "aria-label",
        `${answered ? "Respondido" : "Pendiente"}: reactivo ${index + 1} de ${questions.length}, ${question.dim}`,
      );
      if (index === currentIndex) {
        chip.setAttribute("aria-current", "step");
      }
      chip.addEventListener("click", () => {
        currentIndex = index;
        renderQuestion();
        scrollQuestionCard();
      });
      questionNav.appendChild(chip);
    });
  }

  async function selectAnswer(value) {
    const question = currentQuestion();
    if (!question || completed) return;
    responses.set(question.id, value);
    renderQuestion();
    renderProgress();
    renderSummary();
    renderQuestionNav();
    setSaveState(saveIndicator, "Guardando avance...", "saving");
    setFeedback("Guardando respuesta", "Estamos protegiendo tu avance para que el folio pueda retomarse.");
    const saveToken = ++latestSaveToken;
    try {
      await saveProgress("en_progreso");
      if (saveToken !== latestSaveToken) return;
      surveyMeta.ultimaPregunta = Math.min(Math.max(currentIndex + 1, answeredCount()), questions.length);
      setSaveState(saveIndicator, "Avance guardado", "saved");
      setFeedback("Respuesta guardada", "Puedes continuar al siguiente reactivo o revisar cualquier respuesta desde el mapa.");
      renderSummary();
    } catch (error) {
      if (saveToken !== latestSaveToken) return;
      setSaveState(saveIndicator, error.message, "error");
      setFeedback("No se pudo guardar", error.message);
    }
  }

  function renderQuestion() {
    const question = currentQuestion();
    if (!question) return;

    const selectedValue = responses.get(question.id);
    const answered = answeredCount();
    const pending = Math.max(questions.length - answered, 0);
    const isLastQuestion = currentIndex === questions.length - 1;
    dimensionLabel.textContent = question.dim;
    progressLabel.textContent = `Reactivo ${currentIndex + 1} de ${questions.length}`;
    statusLabel.textContent = completed
      ? "La encuesta ya fue completada."
      : Number.isFinite(selectedValue)
        ? isLastQuestion
          ? "Último reactivo respondido. Puedes revisar o finalizar la encuesta."
          : "Respuesta registrada. Continúa o ajusta tu selección antes de seguir."
        : pending === questions.length
          ? "Selecciona la opción que mejor describa tu situación actual para iniciar la captura."
          : "Selecciona la opción que mejor refleje tu experiencia reciente.";
    questionOrder.textContent = `Reactivo ${question.orden}`;
    questionDimension.textContent = question.dim;
    questionText.textContent = question.txt;
    questionScore.textContent = Number.isFinite(selectedValue) ? `Nivel ${selectedValue}` : "Sin respuesta";
    questionScore.classList.toggle("is-empty", !Number.isFinite(selectedValue));
    questionCard?.classList.toggle("has-answer", Number.isFinite(selectedValue));

    if (questionHint) {
      questionHint.textContent = completed
        ? "La encuesta ya fue enviada."
        : isLastQuestion
          ? "Estás en el último reactivo. Al continuar se enviará la encuesta completa."
          : Number.isFinite(selectedValue)
            ? "Si lo necesitas, puedes cambiar esta respuesta antes de pasar al siguiente reactivo."
            : "Tus respuestas se guardan automáticamente al seleccionar una opción.";
    }

    optionsContainer.innerHTML = "";
    question.t_opc.forEach((label, index) => {
      const value = question.opc[index];
      const wrapper = document.createElement("label");
      wrapper.className = `choice-chip ${selectedValue === value ? "is-selected" : ""}`;
      wrapper.tabIndex = completed ? -1 : 0;
      wrapper.setAttribute("role", "button");
      wrapper.setAttribute("aria-pressed", selectedValue === value ? "true" : "false");
      wrapper.innerHTML = `
        <input type="radio" name="wellbeing_option" value="${value}" ${selectedValue === value ? "checked" : ""} ${completed ? "disabled" : ""}>
        <span>Nivel ${value}</span>
        <strong>${label}</strong>
      `;
      const input = wrapper.querySelector("input");
      input.addEventListener("change", async () => {
        await selectAnswer(value);
      });
      wrapper.addEventListener("keydown", async (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        if (input.disabled) return;
        input.checked = true;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
      optionsContainer.appendChild(wrapper);
    });

    prevButton.disabled = currentIndex === 0;
    nextButton.disabled = !responses.has(question.id) || completed;
    nextButton.textContent = currentIndex === questions.length - 1 ? "Finalizar encuesta" : "Continuar";
    renderSummary();
    renderQuestionNav();
    renderProgress();
    pulseQuestionCard();
  }

  async function saveProgress(requestedState) {
    const payload = {
      hash: folio,
      estado: requestedState,
      ultima_pregunta: Math.min(Math.max(currentIndex + 1, answeredCount()), questions.length),
      respuestas: questions
        .filter((question) => responses.has(question.id))
        .map((question) => ({
          id: question.id,
          dim: question.dim,
          val: responses.get(question.id),
        })),
    };
    return postJson(saveUrl, payload);
  }

  prevButton.addEventListener("click", () => {
    if (currentIndex > 0) {
      currentIndex -= 1;
      renderQuestion();
      scrollQuestionCard();
    }
  });

  nextButton.addEventListener("click", async () => {
    if (!responses.has(currentQuestion().id)) return;

    if (currentIndex === questions.length - 1) {
      setSaveState(saveIndicator, "Enviando encuesta...", "saving");
      setFeedback("Enviando encuesta", "Estamos cerrando el folio y consolidando tus respuestas.");
      try {
        const result = await saveProgress("completada");
        completed = true;
        window.location.href = result.redirect_url || "/bienestar/gracias";
      } catch (error) {
        setSaveState(saveIndicator, error.message, "error");
      }
      return;
    }

    currentIndex += 1;
    renderQuestion();
    scrollQuestionCard();
  });

  jumpPendingButton?.addEventListener("click", () => {
    currentIndex = firstPendingIndex();
    renderQuestion();
    scrollQuestionCard();
  });

  Promise.all([fetch(questionsUrl), fetch(surveyUrl)])
    .then(async ([questionsResponse, surveyResponse]) => {
      const questionsPayload = await questionsResponse.json();
      const surveyPayload = await surveyResponse.json();
      questions = questionsPayload.preguntas || [];
      surveyMeta.estrato = surveyPayload.estrato || "--";
      surveyMeta.ultimaPregunta = Math.max(Number(surveyPayload.ultima_pregunta || 0), 0);
      (surveyPayload.respuestas || []).forEach((response) => {
        responses.set(response.id, response.val);
      });
      completed = surveyPayload.estado === "completada";
      currentIndex = firstPendingIndex();
      if (completed) {
        window.location.href = "/bienestar/gracias";
        return;
      }
      setSaveState(saveIndicator, "Captura lista", "idle");
      setFeedback("Captura lista", "Selecciona la opción que mejor describa tu situación. Puedes volver a cualquier reactivo antes de finalizar.");
      renderQuestion();
    })
    .catch(() => {
      questionText.textContent = "No se pudo cargar la encuesta.";
      setSaveState(saveIndicator, "No se pudo recuperar el folio", "error");
      setFeedback("No se pudo iniciar la captura", "Recarga la página o genera un nuevo folio anónimo.");
      prevButton.disabled = true;
      nextButton.disabled = true;
    });
})();
