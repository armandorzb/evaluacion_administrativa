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

  async function fetchJson(url) {
    const response = await fetch(url, {
      headers: {
        "X-Requested-With": "fetch",
      },
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.mensaje || "No se pudo recuperar la información.");
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

  function average(values, digits = 1) {
    if (!values.length) return null;
    const total = values.reduce((sum, value) => sum + value, 0);
    return Number((total / values.length).toFixed(digits));
  }

  function formatValue(value, digits = 1, fallback = "—") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return fallback;
    }
    return Number(value).toFixed(digits);
  }

  function formatPercent(value, digits = 1, fallback = "—") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return fallback;
    }
    return `${Number(value).toFixed(digits)}%`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function truncateText(value, limit = 72) {
    const text = String(value ?? "").trim();
    if (text.length <= limit) return text;
    return `${text.slice(0, Math.max(limit - 1, 0)).trim()}…`;
  }

  function formatTimestamp(value) {
    if (!value) return "sin corte";
    const normalizedValue =
      typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value) && !/[zZ]|[+\-]\d{2}:\d{2}$/.test(value)
        ? `${value}Z`
        : value;
    const date = new Date(normalizedValue);
    if (Number.isNaN(date.getTime())) return value;
    const dateLabel = new Intl.DateTimeFormat("es-MX", {
      timeZone: "America/Hermosillo",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(date);
    const timeLabel = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Hermosillo",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
    })
      .format(date)
      .replace(/\s+/g, " ")
      .trim()
      .toUpperCase();
    return `${dateLabel} ${timeLabel}`;
  }

  function updateSelectOptions(select, values, currentValue, allLabel) {
    if (!select) return;
    const allowedValues = new Set(values);
    const nextValue = allowedValues.has(currentValue) ? currentValue : "all";
    select.innerHTML = "";
    const allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = allLabel;
    select.appendChild(allOption);
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
    select.value = nextValue;
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

  const dashboardRoot = document.querySelector("[data-wellbeing-dashboard]");
  if (dashboardRoot) {
    initWellbeingDashboard(dashboardRoot);
  }

  const surveyRoot = document.querySelector("[data-wellbeing-survey]");
  if (surveyRoot) {
    initWellbeingSurvey(surveyRoot);
  }

  function initWellbeingDashboard(root) {
    const apiUrl = root.dataset.apiUrl;
    const refreshMs = Number.parseInt(root.dataset.refreshMs || "30000", 10);
    const stratumFilter = document.getElementById("wellbeing-filter-stratum");
    const stateFilter = document.getElementById("wellbeing-filter-state");
    const dimensionFilter = document.getElementById("wellbeing-filter-dimension");
    const cubeGroup = document.getElementById("wellbeing-cube-group");
    const cubeSort = document.getElementById("wellbeing-cube-sort");
    const syncLabel = document.getElementById("wellbeing-live-sync");
    const updatedLabel = document.getElementById("wellbeing-live-updated");
    const insights = document.getElementById("wellbeing-insights");
    const cubeBody = document.getElementById("wellbeing-cube-body");
    const historyBody = document.getElementById("wellbeing-history-body");
    const publicUrlField = document.getElementById("wellbeing-public-url");
    const publicUrlLink = document.getElementById("wellbeing-public-link-action");
    const kpis = {
      total: document.getElementById("wellbeing-kpi-total"),
      completed: document.getElementById("wellbeing-kpi-completed"),
      iibp: document.getElementById("wellbeing-kpi-iibp"),
      ivsp: document.getElementById("wellbeing-kpi-ivsp"),
      progress: document.getElementById("wellbeing-kpi-progress"),
      strata: document.getElementById("wellbeing-kpi-strata"),
      totalCaption: document.getElementById("wellbeing-kpi-total-caption"),
      completedCaption: document.getElementById("wellbeing-kpi-completed-caption"),
      iibpCaption: document.getElementById("wellbeing-kpi-iibp-caption"),
      ivspCaption: document.getElementById("wellbeing-kpi-ivsp-caption"),
      progressCaption: document.getElementById("wellbeing-kpi-progress-caption"),
      strataCaption: document.getElementById("wellbeing-kpi-strata-caption"),
    };
    const chartNodes = {
      strata: document.getElementById("wellbeing-chart-strata"),
      states: document.getElementById("wellbeing-chart-states"),
      dimensions: document.getElementById("wellbeing-chart-dimensions"),
      questions: document.getElementById("wellbeing-chart-questions"),
    };

    const state = {
      payload: null,
      filters: {
        stratum: "all",
        state: "all",
        dimension: "all",
        cubeGroup: "estrato",
        cubeSort: "sample",
      },
      charts: {},
      timer: null,
      refreshing: false,
    };

    [stratumFilter, stateFilter, dimensionFilter, cubeGroup, cubeSort].forEach((control) => {
      control?.addEventListener("change", () => {
        state.filters = {
          stratum: stratumFilter?.value || "all",
          state: stateFilter?.value || "all",
          dimension: dimensionFilter?.value || "all",
          cubeGroup: cubeGroup?.value || "estrato",
          cubeSort: cubeSort?.value || "sample",
        };
        renderDashboard();
      });
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && state.payload) {
        refreshDashboard(false);
      }
    });

    refreshDashboard(true);
    state.timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        refreshDashboard(false);
      }
    }, Number.isFinite(refreshMs) ? refreshMs : 30000);

    window.addEventListener(
      "beforeunload",
      () => {
        if (state.timer) {
          window.clearInterval(state.timer);
        }
      },
      { once: true },
    );

    async function refreshDashboard(showLoading) {
      if (state.refreshing) return;
      state.refreshing = true;
      if (showLoading && syncLabel) {
        syncLabel.textContent = "Sincronizando…";
        syncLabel.className = "status status-medium";
      }

      try {
        const payload = await fetchJson(apiUrl);
        state.payload = payload;
        updateSelectOptions(
          stratumFilter,
          (payload.strata_order || []).filter((value) => value),
          state.filters.stratum,
          "Todos los estratos",
        );
        updateSelectOptions(
          dimensionFilter,
          (payload.dimension_order || []).filter((value) => value),
          state.filters.dimension,
          "Todas las dimensiones",
        );
        if (publicUrlField) {
          publicUrlField.value = payload.public_url || publicUrlField.value;
        }
        if (publicUrlLink && payload.public_url) {
          publicUrlLink.href = payload.public_url;
        }
        if (updatedLabel) {
          updatedLabel.textContent = `Última actualización: ${formatTimestamp(payload.generated_at)}`;
        }
        if (syncLabel) {
          syncLabel.textContent = "Actualizado en tiempo real";
          syncLabel.className = "status status-opportune";
        }
        state.filters = {
          stratum: stratumFilter?.value || "all",
          state: stateFilter?.value || "all",
          dimension: dimensionFilter?.value || "all",
          cubeGroup: cubeGroup?.value || "estrato",
          cubeSort: cubeSort?.value || "sample",
        };
        renderDashboard();
      } catch (error) {
        if (syncLabel) {
          syncLabel.textContent = "Sincronización pendiente";
          syncLabel.className = "status status-low";
        }
        if (updatedLabel) {
          updatedLabel.textContent = error.message;
        }
        if (!state.payload && insights) {
          insights.innerHTML = `
            <div class="wellbeing-insight-card">
              <strong>No se pudo cargar el tablero</strong>
              <p class="muted">${escapeHtml(error.message)}</p>
            </div>
          `;
        }
      } finally {
        state.refreshing = false;
      }
    }

    function renderDashboard() {
      if (!state.payload) return;
      const questionById = new Map(
        (state.payload.question_catalog || []).map((question) => [String(question.id), question]),
      );
      const filteredSurveys = getFilteredSurveys(state.payload.survey_rows || [], state.filters);
      const filteredResponses = flattenResponses(filteredSurveys, questionById, state.filters.dimension);
      const overview = buildOverview(filteredSurveys);
      const dimensionStats = buildDimensionStats(filteredResponses);
      const questionStats = buildQuestionStats(filteredResponses);
      const cubeRows = buildCubeRows(filteredSurveys, filteredResponses, state.filters.cubeGroup, state.filters.cubeSort);

      renderKpis(overview);
      renderInsights(overview, dimensionStats, questionStats, filteredSurveys);
      renderCube(cubeRows);
      renderHistory(filteredSurveys);
      renderStrataChart(filteredSurveys, state.payload.strata_order || []);
      renderStatesChart(overview);
      renderDimensionChart(dimensionStats);
      renderQuestionChart(questionStats);
    }

    function getFilteredSurveys(surveys, filters) {
      return surveys.filter((survey) => {
        if (filters.stratum !== "all" && survey.estrato !== filters.stratum) return false;
        if (filters.state !== "all" && survey.estado !== filters.state) return false;
        return true;
      });
    }

    function flattenResponses(surveys, questionById, dimensionValue) {
      const rows = [];
      surveys.forEach((survey) => {
        (survey.responses || []).forEach((response) => {
          if (dimensionValue !== "all" && response.dimension !== dimensionValue) return;
          const question = questionById.get(String(response.question_id)) || {};
          rows.push({
            surveyHash: survey.hash,
            stratum: survey.estrato,
            state: survey.estado,
            completionPercent: Number(survey.completion_percent || 0),
            iibp: survey.iibp,
            ivsp: survey.ivsp,
            dimension: response.dimension,
            questionId: String(response.question_id),
            questionLabel: question.orden ? `R${question.orden}` : `R${response.orden || response.question_id}`,
            questionText: question.texto || `Reactivo ${response.orden || response.question_id}`,
            questionOrder: question.orden || response.orden || 0,
            value: Number(response.value || 0),
          });
        });
      });
      return rows;
    }

    function buildOverview(surveys) {
      const completed = surveys.filter((survey) => survey.estado === "completada");
      return {
        total: surveys.length,
        completed: completed.length,
        inProgress: surveys.filter((survey) => survey.estado === "en_progreso").length,
        abandoned: surveys.filter((survey) => survey.estado === "abandonada").length,
        avgIibp: average(completed.map((survey) => Number(survey.iibp)).filter(Number.isFinite)),
        avgIvsp: average(completed.map((survey) => Number(survey.ivsp)).filter(Number.isFinite)),
        avgProgress: average(surveys.map((survey) => Number(survey.completion_percent || 0)).filter(Number.isFinite)),
        activeStrata: new Set(surveys.map((survey) => survey.estrato)).size,
      };
    }

    function buildDimensionStats(responses) {
      const buckets = new Map();
      responses.forEach((response) => {
        if (!buckets.has(response.dimension)) {
          buckets.set(response.dimension, []);
        }
        buckets.get(response.dimension).push(response.value);
      });
      return Array.from(buckets.entries())
        .map(([label, values]) => {
          const avg = average(values, 2);
          return {
            label,
            average: avg,
            percent: avg === null ? null : Number(((avg / 4) * 100).toFixed(1)),
            sample: values.length,
          };
        })
        .sort((left, right) => (right.percent || 0) - (left.percent || 0));
    }

    function buildQuestionStats(responses) {
      const buckets = new Map();
      responses.forEach((response) => {
        if (!buckets.has(response.questionId)) {
          buckets.set(response.questionId, {
            label: response.questionLabel,
            detail: response.questionText,
            order: response.questionOrder,
            values: [],
          });
        }
        buckets.get(response.questionId).values.push(response.value);
      });
      return Array.from(buckets.values())
        .map((item) => {
          const avg = average(item.values, 2);
          return {
            label: item.label,
            detail: item.detail,
            order: item.order,
            average: avg,
            percent: avg === null ? null : Number(((avg / 4) * 100).toFixed(1)),
            sample: item.values.length,
          };
        })
        .sort((left, right) => (right.percent || 0) - (left.percent || 0));
    }

    function buildCubeRows(surveys, responses, groupMode, sortMode) {
      const rows = [];

      if (groupMode === "estrato" || groupMode === "estado") {
        const buckets = new Map();
        surveys.forEach((survey) => {
          const key = groupMode === "estrato" ? survey.estrato : survey.estado_label;
          if (!buckets.has(key)) {
            buckets.set(key, { label: key, surveys: [], responses: [] });
          }
          buckets.get(key).surveys.push(survey);
        });
        responses.forEach((response) => {
          const key = groupMode === "estrato" ? response.stratum : humanizeState(response.state);
          if (buckets.has(key)) {
            buckets.get(key).responses.push(response);
          }
        });
        buckets.forEach((bucket) => rows.push(summarizeSurveyBucket(bucket.label, bucket.surveys, bucket.responses)));
      } else if (groupMode === "dimension") {
        const buckets = new Map();
        responses.forEach((response) => {
          if (!buckets.has(response.dimension)) {
            buckets.set(response.dimension, []);
          }
          buckets.get(response.dimension).push(response);
        });
        buckets.forEach((bucket, label) => rows.push(summarizeResponseBucket(label, bucket)));
      } else {
        const buckets = new Map();
        responses.forEach((response) => {
          if (!buckets.has(response.questionId)) {
            buckets.set(response.questionId, []);
          }
          buckets.get(response.questionId).push(response);
        });
        buckets.forEach((bucket) => {
          const first = bucket[0];
          rows.push(
            summarizeResponseBucket(
              `${first.questionLabel} · ${truncateText(first.questionText, 46)}`,
              bucket,
            ),
          );
        });
      }

      const sorted = rows.sort((left, right) => {
        const sortMap = {
          sample: [left.sample, right.sample],
          score: [left.scorePercent, right.scorePercent],
          completion: [left.avgProgress, right.avgProgress],
          iibp: [left.avgIibp, right.avgIibp],
          ivsp: [left.avgIvsp, right.avgIvsp],
        };
        const [leftValue, rightValue] = sortMap[sortMode] || sortMap.sample;
        return (Number(rightValue) || -1) - (Number(leftValue) || -1);
      });

      return sorted.slice(0, 12);
    }

    function summarizeSurveyBucket(label, surveys, responses) {
      const completed = surveys.filter((survey) => survey.estado === "completada");
      const responseAverage = average(responses.map((response) => response.value), 2);
      return {
        label,
        sample: surveys.length,
        responseAverage,
        scorePercent: responseAverage === null ? null : Number(((responseAverage / 4) * 100).toFixed(1)),
        avgIibp: average(completed.map((survey) => Number(survey.iibp)).filter(Number.isFinite)),
        avgIvsp: average(completed.map((survey) => Number(survey.ivsp)).filter(Number.isFinite)),
        avgProgress: average(surveys.map((survey) => Number(survey.completion_percent || 0)).filter(Number.isFinite)),
      };
    }

    function summarizeResponseBucket(label, responses) {
      const surveys = Array.from(new Map(responses.map((response) => [response.surveyHash, response])).values());
      const completedSurveys = surveys.filter((survey) => survey.state === "completada");
      const responseAverage = average(responses.map((response) => response.value), 2);
      return {
        label,
        sample: responses.length,
        responseAverage,
        scorePercent: responseAverage === null ? null : Number(((responseAverage / 4) * 100).toFixed(1)),
        avgIibp: average(completedSurveys.map((survey) => Number(survey.iibp)).filter(Number.isFinite)),
        avgIvsp: average(completedSurveys.map((survey) => Number(survey.ivsp)).filter(Number.isFinite)),
        avgProgress: average(surveys.map((survey) => Number(survey.completionPercent || 0)).filter(Number.isFinite)),
      };
    }

    function renderKpis(overview) {
      if (kpis.total) kpis.total.textContent = String(overview.total);
      if (kpis.completed) kpis.completed.textContent = String(overview.completed);
      if (kpis.iibp) kpis.iibp.textContent = formatValue(overview.avgIibp);
      if (kpis.ivsp) kpis.ivsp.textContent = formatValue(overview.avgIvsp);
      if (kpis.progress) kpis.progress.textContent = formatPercent(overview.avgProgress);
      if (kpis.strata) kpis.strata.textContent = String(overview.activeStrata);
      if (kpis.totalCaption) kpis.totalCaption.textContent = `${overview.inProgress} en progreso y ${overview.abandoned} abandonadas`;
      if (kpis.completedCaption) kpis.completedCaption.textContent = `${overview.completed} folios cerrados para análisis`;
      if (kpis.iibpCaption) kpis.iibpCaption.textContent = overview.avgIibp === null ? "Aún sin corte completado" : "Promedio del universo completado filtrado";
      if (kpis.ivspCaption) kpis.ivspCaption.textContent = overview.avgIvsp === null ? "Aún sin corte completado" : "Riesgo agregado del corte filtrado";
      if (kpis.progressCaption) kpis.progressCaption.textContent = "Promedio de avance de la captura";
      if (kpis.strataCaption) kpis.strataCaption.textContent = "Estratos con muestra visible";
    }

    function renderInsights(overview, dimensionStats, questionStats, surveys) {
      if (!insights) return;
      if (!surveys.length) {
        insights.innerHTML = `
          <div class="wellbeing-insight-card">
            <strong>Sin datos en el corte actual</strong>
            <p class="muted">Ajusta los filtros o espera nuevas respuestas para ver hallazgos ejecutivos.</p>
          </div>
        `;
        return;
      }

      const strongestDimension = dimensionStats[0];
      const weakestDimension = [...dimensionStats].reverse().find((item) => item.percent !== null);
      const topQuestion = questionStats[0];
      const completionRatio = overview.total ? Number(((overview.completed / overview.total) * 100).toFixed(1)) : 0;

      const cards = [
        {
          title: "Ritmo del corte",
          text: `${overview.total} sesiones visibles, con ${overview.completed} encuestas completadas (${completionRatio}%).`,
        },
        {
          title: "Dimensión mejor posicionada",
          text: strongestDimension
            ? `${strongestDimension.label} lidera con ${formatPercent(strongestDimension.percent)} y ${strongestDimension.sample} respuestas consolidadas.`
            : "Todavía no hay suficiente captura para consolidar dimensiones.",
        },
        {
          title: "Dimensión a vigilar",
          text: weakestDimension
            ? `${weakestDimension.label} marca la lectura más baja con ${formatPercent(weakestDimension.percent)}.`
            : "Aún no hay dimensión crítica identificable en este corte.",
        },
        {
          title: "Reactivo de mayor tracción",
          text: topQuestion
            ? `${topQuestion.label} alcanza ${formatPercent(topQuestion.percent)} con ${topQuestion.sample} respuestas observadas.`
            : "Aún no hay reactivos con muestra suficiente para ranking.",
        },
      ];

      insights.innerHTML = cards
        .map(
          (item) => `
            <div class="wellbeing-insight-card">
              <strong>${escapeHtml(item.title)}</strong>
              <p class="muted">${escapeHtml(item.text)}</p>
            </div>
          `,
        )
        .join("");
    }

    function renderCube(rows) {
      if (!cubeBody) return;
      if (!rows.length) {
        cubeBody.innerHTML = `<tr><td colspan="7" class="muted">No hay datos suficientes para el cubo con el corte seleccionado.</td></tr>`;
        return;
      }
      cubeBody.innerHTML = rows
        .map(
          (row) => `
            <tr>
              <td><strong>${escapeHtml(row.label)}</strong></td>
              <td>${row.sample}</td>
              <td>${formatValue(row.responseAverage, 2)}</td>
              <td>${formatPercent(row.scorePercent)}</td>
              <td>${formatValue(row.avgIibp)}</td>
              <td>${formatValue(row.avgIvsp)}</td>
              <td>${formatPercent(row.avgProgress)}</td>
            </tr>
          `,
        )
        .join("");
    }

    function renderHistory(surveys) {
      if (!historyBody) return;
      const rows = [...surveys]
        .sort((left, right) => new Date(right.created_at || 0) - new Date(left.created_at || 0))
        .slice(0, 12);
      if (!rows.length) {
        historyBody.innerHTML = `<tr><td colspan="7" class="muted">No hay sesiones para el corte seleccionado.</td></tr>`;
        return;
      }
      historyBody.innerHTML = rows
        .map(
          (survey) => `
            <tr>
              <td><strong>${escapeHtml(survey.hash)}</strong></td>
              <td>${escapeHtml(survey.fecha)}</td>
              <td>${escapeHtml(survey.estrato)}</td>
              <td><span class="status ${statusClassForState(survey.estado)}">${escapeHtml(survey.estado_label)}</span></td>
              <td>${formatPercent(survey.completion_percent)}</td>
              <td>${formatValue(survey.iibp)}</td>
              <td>${formatValue(survey.ivsp)}</td>
            </tr>
          `,
        )
        .join("");
    }

    function renderStrataChart(surveys, strataOrder) {
      const labels = strataOrder.filter((label) => surveys.some((survey) => survey.estrato === label));
      const effectiveLabels = labels.length ? labels : ["Sin datos"];
      const datasets = [
        {
          label: "Completadas",
          backgroundColor: "rgba(55, 117, 142, 0.82)",
          data: effectiveLabels.map((label) => countBy(surveys, (survey) => survey.estrato === label && survey.estado === "completada")),
        },
        {
          label: "En progreso",
          backgroundColor: "rgba(245, 176, 100, 0.82)",
          data: effectiveLabels.map((label) => countBy(surveys, (survey) => survey.estrato === label && survey.estado === "en_progreso")),
        },
        {
          label: "Abandonadas",
          backgroundColor: "rgba(181, 68, 33, 0.82)",
          data: effectiveLabels.map((label) => countBy(surveys, (survey) => survey.estrato === label && survey.estado === "abandonada")),
        },
      ];

      upsertChart("strata", chartNodes.strata, {
        type: "bar",
        data: { labels: effectiveLabels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          resizeDelay: 120,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { position: "bottom" } },
          scales: {
            x: { stacked: true, grid: { display: false } },
            y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
          },
        },
      });
    }

    function renderStatesChart(overview) {
      const values = [overview.completed, overview.inProgress, overview.abandoned];
      const hasData = values.some((value) => value > 0);
      upsertChart("states", chartNodes.states, {
        type: "doughnut",
        data: {
          labels: hasData ? ["Completadas", "En progreso", "Abandonadas"] : ["Sin datos"],
          datasets: [
            {
              data: hasData ? values : [1],
              backgroundColor: hasData
                ? ["rgba(55, 117, 142, 0.88)", "rgba(245, 176, 100, 0.88)", "rgba(181, 68, 33, 0.88)"]
                : ["rgba(201, 212, 220, 0.88)"],
              borderWidth: 0,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          resizeDelay: 120,
          plugins: { legend: { position: "bottom" } },
          cutout: "64%",
        },
      });
    }

    function renderDimensionChart(rows) {
      const hasData = rows.length > 0;
      upsertChart("dimensions", chartNodes.dimensions, {
        type: "radar",
        data: {
          labels: hasData ? rows.map((row) => row.label) : ["Sin datos"],
          datasets: [
            {
              label: "Puntaje %",
              data: hasData ? rows.map((row) => row.percent || 0) : [0],
              borderColor: "rgba(36, 98, 124, 0.96)",
              backgroundColor: "rgba(36, 98, 124, 0.18)",
              pointBackgroundColor: "rgba(223, 106, 47, 0.96)",
              pointBorderColor: "#ffffff",
              pointBorderWidth: 1.5,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          resizeDelay: 120,
          plugins: { legend: { display: false } },
          scales: {
            r: {
              suggestedMin: 0,
              suggestedMax: 100,
              ticks: { backdropColor: "transparent" },
            },
          },
        },
      });
    }

    function renderQuestionChart(rows) {
      const topRows = rows.slice(0, 7);
      const hasData = topRows.length > 0;
      upsertChart("questions", chartNodes.questions, {
        type: "bar",
        data: {
          labels: hasData ? topRows.map((row) => row.label) : ["Sin datos"],
          datasets: [
            {
              label: "Puntaje %",
              data: hasData ? topRows.map((row) => row.percent || 0) : [0],
              backgroundColor: "rgba(15, 36, 56, 0.88)",
              borderRadius: 10,
              borderSkipped: false,
            },
          ],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          resizeDelay: 120,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label(context) {
                  const row = topRows[context.dataIndex];
                  if (!row) return "";
                  return `${formatPercent(row.percent)} | ${row.sample} respuestas`;
                },
                afterLabel(context) {
                  const row = topRows[context.dataIndex];
                  return row ? truncateText(row.detail, 120) : "";
                },
              },
            },
          },
          scales: {
            x: { beginAtZero: true, suggestedMax: 100 },
            y: { grid: { display: false } },
          },
        },
      });
    }

    function upsertChart(key, canvas, config) {
      if (!canvas || typeof Chart === "undefined") return;
      if (state.charts[key]) {
        state.charts[key].data = config.data;
        state.charts[key].options = config.options;
        state.charts[key].resize();
        state.charts[key].update();
        return;
      }
      state.charts[key] = new Chart(canvas.getContext("2d"), config);
    }

    function countBy(items, predicate) {
      return items.reduce((total, item) => total + (predicate(item) ? 1 : 0), 0);
    }

    function humanizeState(stateValue) {
      const labels = {
        completada: "Completada",
        en_progreso: "En progreso",
        abandonada: "Abandonada",
      };
      return labels[stateValue] || stateValue;
    }

    function statusClassForState(stateValue) {
      if (stateValue === "completada") return "status-opportune";
      if (stateValue === "en_progreso") return "status-medium";
      return "status-low";
    }
  }

  function initWellbeingSurvey(surveyRoot) {
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
      if (progressSummary) progressSummary.textContent = `${answered} respondidos`;
      if (progressPending) progressPending.textContent = `${pending} pendientes`;
      if (progressRestore) {
        progressRestore.textContent = surveyMeta.ultimaPregunta
          ? `Retoma sugerido desde el reactivo ${Math.min(surveyMeta.ultimaPregunta, questions.length)}.`
          : "La encuesta puede retomarse con el mismo folio.";
      }
      if (mapStatus) mapStatus.textContent = `${currentIndex + 1}/${questions.length}`;
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
  }
})();
