(() => {
  document.documentElement.classList.add("js");

  const body = document.body;
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const menuToggle = document.querySelector("[data-menu-toggle]");
  const headerShell = document.querySelector("[data-header-shell]");
  const headerRegion = document.querySelector("[data-header-region]");
  const menuScrim = document.querySelector("[data-menu-scrim]");
  const dirtyForms = new Set();
  let isSubmittingForm = false;

  if (menuToggle && headerShell) {
    const closeMenu = () => {
      headerShell.dataset.open = "false";
      menuToggle.classList.remove("is-open");
      menuToggle.setAttribute("aria-expanded", "false");
      body.classList.remove("menu-open");
    };

    const openMenu = () => {
      headerShell.dataset.open = "true";
      menuToggle.classList.add("is-open");
      menuToggle.setAttribute("aria-expanded", "true");
      body.classList.add("menu-open");
    };

    menuToggle.addEventListener("click", () => {
      const isOpen = headerShell.dataset.open === "true";
      if (isOpen) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    if (menuScrim) {
      menuScrim.addEventListener("click", closeMenu);
    }

    headerShell.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        if (window.innerWidth <= 860) {
          closeMenu();
        }
      });
    });

    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && headerShell.dataset.open === "true") {
        closeMenu();
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 860) {
        closeMenu();
      }
    });

    document.addEventListener("click", (event) => {
      if (window.innerWidth > 860 || headerShell.dataset.open !== "true") {
        return;
      }
      if (headerRegion?.contains(event.target)) {
        return;
      }
      closeMenu();
    });
  }

  document.querySelectorAll("[data-dialog-open]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const dialogId = trigger.dataset.dialogOpen;
      const dialog = dialogId ? document.getElementById(dialogId) : null;
      if (dialog && typeof dialog.showModal === "function") {
        dialog.showModal();
      }
    });
  });

  document.querySelectorAll("dialog.catalog-dialog").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      const bounds = dialog.getBoundingClientRect();
      const clickedInside =
        bounds.top <= event.clientY &&
        event.clientY <= bounds.top + bounds.height &&
        bounds.left <= event.clientX &&
        event.clientX <= bounds.left + bounds.width;
      if (!clickedInside) {
        dialog.close();
      }
    });
  });

  const roleDefinitionsNode = document.getElementById("role-definitions-data");
  const roleDefinitions = roleDefinitionsNode ? JSON.parse(roleDefinitionsNode.textContent || "{}") : {};
  const importGuidesNode = document.getElementById("import-guide-definitions");
  const importGuides = importGuidesNode ? JSON.parse(importGuidesNode.textContent || "{}") : {};

  function syncRoleHelp(select) {
    const targetId = select.dataset.roleHelpTarget;
    if (!targetId) return;
    const target = document.getElementById(targetId);
    if (!target) return;
    const role = select.value;
    const label = role ? role.charAt(0).toUpperCase() + role.slice(1) : "Rol";
    const description = roleDefinitions[role] || "Selecciona un rol para ver su alcance operativo.";
    target.innerHTML = `<strong>${label}</strong><p>${description}</p>`;
  }

  function syncModuleAccessOptions(select) {
    const form = select.closest("form");
    if (!form) return;
    const wellbeingCheckbox = form.querySelector('input[name="acceso_bienestar"]');
    const iso9001Checkbox = form.querySelector('input[name="acceso_iso9001"]');
    const iso45001Checkbox = form.querySelector('input[name="acceso_iso45001"]');
    const liveCheckbox = form.querySelector('input[name="acceso_live"]');
    const allowsWellbeing = ["administrador", "consulta"].includes(select.value);
    const allowsIso9001 = ["administrador", "revisor", "evaluador", "respondente", "consulta"].includes(select.value);
    const allowsIso45001 = ["administrador", "revisor", "evaluador", "respondente", "consulta"].includes(select.value);
    const allowsLive = ["administrador", "consulta"].includes(select.value);

    if (wellbeingCheckbox) {
      const roleBasedDefault = wellbeingCheckbox.dataset.defaultMode === "admin-only";
      wellbeingCheckbox.disabled = !allowsWellbeing;
      if (!allowsWellbeing) {
        wellbeingCheckbox.checked = false;
      } else if (roleBasedDefault && wellbeingCheckbox.dataset.userTouched !== "true") {
        wellbeingCheckbox.checked = select.value === "administrador";
      }
    }

    if (iso9001Checkbox) {
      const roleBasedDefault = iso9001Checkbox.dataset.defaultMode === "admin-only";
      iso9001Checkbox.disabled = !allowsIso9001;
      if (!allowsIso9001) {
        iso9001Checkbox.checked = false;
      } else if (roleBasedDefault && iso9001Checkbox.dataset.userTouched !== "true") {
        iso9001Checkbox.checked = select.value === "administrador";
      }
    }

    if (iso45001Checkbox) {
      const roleBasedDefault = iso45001Checkbox.dataset.defaultMode === "admin-only";
      iso45001Checkbox.disabled = !allowsIso45001;
      if (!allowsIso45001) {
        iso45001Checkbox.checked = false;
      } else if (roleBasedDefault && iso45001Checkbox.dataset.userTouched !== "true") {
        iso45001Checkbox.checked = select.value === "administrador";
      }
    }

    if (liveCheckbox) {
      const roleBasedDefault = liveCheckbox.dataset.defaultMode === "admin-only";
      liveCheckbox.disabled = !allowsLive;
      if (!allowsLive) {
        liveCheckbox.checked = false;
      } else if (roleBasedDefault && liveCheckbox.dataset.userTouched !== "true") {
        liveCheckbox.checked = select.value === "administrador";
      }
    }
  }

  function buildGuideList(items) {
    if (!items || !items.length) {
      return "<li>Sin columnas opcionales.</li>";
    }
    return items.map((item) => `<li><code>${item}</code></li>`).join("");
  }

  function syncImportGuide(select) {
    const targetId = select.dataset.importGuideTarget;
    if (!targetId) return;
    const target = document.getElementById(targetId);
    if (!target) return;

    const guide = importGuides[select.value] || importGuides.dependencias;
    if (!guide) return;

    const title = target.querySelector("[data-import-guide-title]");
    const format = target.querySelector("[data-import-guide-format]");
    const description = target.querySelector("[data-import-guide-description]");
    const required = target.querySelector("[data-import-guide-required]");
    const optional = target.querySelector("[data-import-guide-optional]");
    const example = target.querySelector("[data-import-guide-example]");
    const noteTitle = target.querySelector("[data-import-guide-note-title]");
    const note = target.querySelector("[data-import-guide-note]");

    if (title) title.textContent = guide.title;
    if (format) format.textContent = guide.format;
    if (description) description.textContent = guide.description;
    if (required) required.innerHTML = buildGuideList(guide.required);
    if (optional) optional.innerHTML = buildGuideList(guide.optional);
    if (example) example.textContent = guide.example;
    if (noteTitle) noteTitle.textContent = guide.note_title;
    if (note) note.textContent = guide.note;

    triggerReveal(target);
  }

  function initializeResponsiveTables() {
    document.querySelectorAll(".table-wrap table").forEach((table) => {
      const headers = Array.from(table.querySelectorAll("thead th")).map((header) =>
        header.textContent.replace(/\s+/g, " ").trim(),
      );

      if (!headers.length) return;

      table.classList.add("js-responsive-table");

      table.querySelectorAll("tbody tr").forEach((row) => {
        const cells = Array.from(row.children).filter((cell) => cell.tagName === "TD");
        cells.forEach((cell, index) => {
          const colspan = Number(cell.getAttribute("colspan") || "1");
          if (colspan > 1 || !headers[index]) {
            cell.dataset.label = "";
            cell.classList.add("table-cell-full");
            return;
          }
          cell.dataset.label = headers[index];
        });
      });
    });
  }

  function syncAreaSelect(dependencySelect) {
    const targetId = dependencySelect.dataset.areaTarget;
    if (!targetId) return;
    const areaSelect = document.getElementById(targetId);
    if (!areaSelect) return;

    const dependencyId = dependencySelect.value;
    let selectedVisible = false;
    areaSelect.querySelectorAll("option[data-dependency-id]").forEach((option) => {
      const visible = !dependencyId || option.dataset.dependencyId === dependencyId;
      option.hidden = !visible;
      option.disabled = !visible;
      if (visible && option.selected) {
        selectedVisible = true;
      }
    });

    if (!selectedVisible) {
      areaSelect.value = "";
    }
  }

  document.querySelectorAll('input[name="acceso_bienestar"][data-default-mode], input[name="acceso_iso9001"][data-default-mode], input[name="acceso_iso45001"][data-default-mode], input[name="acceso_live"][data-default-mode]').forEach((checkbox) => {
    checkbox.dataset.userTouched = "false";
    checkbox.addEventListener("change", () => {
      checkbox.dataset.userTouched = "true";
    });
  });

  document.querySelectorAll("[data-role-help-target]").forEach((select) => {
    syncRoleHelp(select);
    syncModuleAccessOptions(select);
    select.addEventListener("change", () => {
      syncRoleHelp(select);
      syncModuleAccessOptions(select);
    });
  });

  document.querySelectorAll("[data-import-guide-target]").forEach((select) => {
    syncImportGuide(select);
    select.addEventListener("change", () => syncImportGuide(select));
  });

  document.querySelectorAll("[data-dependency-select]").forEach((select) => {
    syncAreaSelect(select);
    select.addEventListener("change", () => syncAreaSelect(select));
  });

  initializeResponsiveTables();

  if (window.Chart) {
    window.Chart.defaults.animation = prefersReducedMotion
      ? false
      : {
          duration: 800,
          easing: "easeOutQuart",
        };
    window.Chart.defaults.font.family = "Urbanist, sans-serif";
    window.Chart.defaults.color = "#183247";
  }

  const heartbeatUrl = body.dataset.heartbeatUrl;
  if (heartbeatUrl) {
    window.setInterval(() => {
      fetch(heartbeatUrl, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
      }).catch(() => {});
    }, 60000);
  }

  function clampProgress(value) {
    const numeric = Number(String(value ?? "").replace("%", ""));
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    return Math.max(0, Math.min(100, numeric));
  }

  function setProgressBar(node, value) {
    if (!node) return;
    const progress = clampProgress(value);
    node.dataset.progressValue = String(progress);
    node.style.width = `${progress}%`;
    node.setAttribute("aria-valuenow", String(progress));
  }

  function initializeProgressBars() {
    document.querySelectorAll("[data-progress-bar]").forEach((node, index) => {
      node.style.width = "0%";
      const targetValue = node.dataset.progressValue || 0;
      const delay = prefersReducedMotion ? 0 : 80 + index * 30;
      window.setTimeout(() => setProgressBar(node, targetValue), delay);
    });
  }

  function triggerReveal(node) {
    if (!node || prefersReducedMotion) return;
    node.classList.remove("is-entering");
    void node.offsetWidth;
    node.classList.add("is-entering");
    window.setTimeout(() => node.classList.remove("is-entering"), 320);
  }

  function toggleNode(node, visible) {
    if (!node) return;
    node.hidden = !visible;
    if (visible) {
      triggerReveal(node);
    }
  }

  function syncDependentController(controller) {
    const target = controller.dataset.dependentTarget;
    if (!target) return;

    const container =
      controller.closest("[data-axis-form]") ||
      controller.closest(".module-panel") ||
      controller.closest(".panel") ||
      document;
    const isVisible = Boolean(controller.value);

    container.querySelectorAll(`[data-dependent-block="${target}"]`).forEach((node) => {
      toggleNode(node, isVisible);
    });
    container.querySelectorAll(`[data-dependent-placeholder="${target}"]`).forEach((node) => {
      toggleNode(node, !isVisible);
    });
  }

  function pulseSelection(input) {
    const chip = input.closest(".choice-chip");
    const card = input.closest(".question-card");
    if (!chip) return;

    chip.classList.remove("just-selected");
    void chip.offsetWidth;
    chip.classList.add("just-selected");
    window.setTimeout(() => chip.classList.remove("just-selected"), 340);

    if (!card) return;
    card.classList.add("is-active");
    window.setTimeout(() => card.classList.remove("is-active"), 500);
  }

  function setChoiceState(form, changedInput = null) {
    form.querySelectorAll(".choice-chip").forEach((chip) => {
      const input = chip.querySelector('input[type="radio"]');
      chip.classList.toggle("is-selected", Boolean(input && input.checked));
    });
    if (changedInput) {
      pulseSelection(changedInput);
    }
  }

  function setSaveState(form, state, message) {
    const indicator = form.querySelector("[data-save-state]");
    if (!indicator) return;
    indicator.dataset.state = state;
    const label = indicator.querySelector("[data-save-label]");
    if (label && message) {
      label.textContent = message;
    }
  }

  function updateLastSaved(form, value) {
    const target = form.querySelector("[data-last-saved]");
    if (!target) return;
    target.textContent = value || "Sin registro";
  }

  function updateAxisProgress(form, progress) {
    const axisId = form.dataset.axisId;
    const value = clampProgress(progress);
    document.querySelectorAll(`[data-axis-progress="${axisId}"]`).forEach((target) => {
      target.textContent = `${value}%`;
    });
    document.querySelectorAll(`[data-axis-progress-bar="${axisId}"]`).forEach((bar) => {
      setProgressBar(bar, value);
    });
  }

  function updateAxisAnswered(form, answered) {
    const axisId = form.dataset.axisId;
    document.querySelectorAll(`[data-axis-answered="${axisId}"]`).forEach((target) => {
      target.textContent = String(answered);
    });
  }

  function computeAxisProgress(form) {
    const total = Number(form.dataset.axisTotal || form.querySelectorAll("[data-reactivo-id]").length || 0);
    const answered = form.querySelectorAll('[data-reactivo-id] input[type="radio"]:checked').length;
    const percent = total ? Number(((answered / total) * 100).toFixed(2)) : 0;
    return { total, answered, percent };
  }

  function computeOverallProgress() {
    const forms = Array.from(document.querySelectorAll("[data-axis-form]"));
    const total = forms.reduce(
      (count, form) => count + Number(form.dataset.axisTotal || form.querySelectorAll("[data-reactivo-id]").length || 0),
      0,
    );
    const answered = forms.reduce(
      (count, form) => count + form.querySelectorAll('[data-reactivo-id] input[type="radio"]:checked').length,
      0,
    );
    const percent = total ? Number(((answered / total) * 100).toFixed(2)) : 0;
    return { total, answered, percent };
  }

  function syncFormProgress(form) {
    const { answered, percent } = computeAxisProgress(form);
    updateAxisAnswered(form, answered);
    updateAxisProgress(form, percent);
    const overall = computeOverallProgress();
    updateOverallProgress(overall.percent);
  }

  function updateQuestionScore(card) {
    if (!card) return;
    const score = card.querySelector("[data-question-score]");
    if (!score) return;
    const selected = card.querySelector('input[type="radio"]:checked');
    if (!selected) {
      score.textContent = "Sin respuesta";
      score.classList.add("is-empty");
      return;
    }
    score.textContent = `Nivel ${selected.value}`;
    score.classList.remove("is-empty");
  }

  function updateOverallProgress(value) {
    const progress = clampProgress(value);
    document.querySelectorAll("[data-overall-completion]").forEach((node) => {
      node.textContent = `${progress}%`;
    });
    document.querySelectorAll('[data-progress-role="overall"]').forEach((node) => {
      setProgressBar(node, progress);
    });
  }

  function serializeAxisForm(form) {
    const responses = [];
    form.querySelectorAll("[data-reactivo-id]").forEach((card) => {
      const reactivoId = Number(card.dataset.reactivoId);
      const selected = form.querySelector(`input[name="valor_${reactivoId}"]:checked`);
      const area = form.querySelector(`[name="area_${reactivoId}"]`);
      const comment = form.querySelector(`[name="comentario_${reactivoId}"]`);
      responses.push({
        reactivo_id: reactivoId,
        valor: selected ? selected.value : null,
        area_id: area ? area.value || null : null,
        comentario: comment ? comment.value : "",
      });
    });

    const axisId = Number(form.dataset.axisId);
    const axisComment = form.querySelector(`[name="comentario_eje_${axisId}"]`);
    const axisArea = form.querySelector(`[name="comentario_eje_area_${axisId}"]`);
    return {
      eje_id: axisId,
      comentario_eje: axisComment ? axisComment.value : "",
      comentario_eje_area_id: axisArea ? axisArea.value || null : null,
      responses,
    };
  }

  function hasPendingFiles() {
    return Array.from(document.querySelectorAll('[data-axis-form] input[type="file"], [data-iso-form] input[type="file"], [data-iso-document-library] input[type="file"]')).some(
      (input) => input.files && input.files.length > 0,
    );
  }

  document.querySelectorAll("[data-axis-form]").forEach((form) => {
    setChoiceState(form);
    form.querySelectorAll("[data-reactivo-id]").forEach((card) => updateQuestionScore(card));
    syncFormProgress(form);
    form.querySelectorAll("[data-dependent-controller]").forEach((controller) => {
      syncDependentController(controller);
    });

    if (form.dataset.readonly === "true") {
      return;
    }

    let timerId = null;

    const queueAutosave = () => {
      dirtyForms.add(form);
      window.clearTimeout(timerId);
      timerId = window.setTimeout(() => {
        const url = form.dataset.autosaveUrl;
        if (!url) return;

        setSaveState(form, "saving", "Guardando...");
        fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "fetch",
          },
          body: JSON.stringify(serializeAxisForm(form)),
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error("No se pudo guardar");
            }
            return response.json();
          })
          .then((payload) => {
            setSaveState(form, "saved", "Guardado");
            updateLastSaved(form, payload.last_saved);
            updateAxisProgress(form, payload.axis_completion);
            updateOverallProgress(payload.completion);
            dirtyForms.delete(form);
          })
          .catch(() => {
            setSaveState(form, "error", "Error al guardar");
          });
      }, 700);
    };

    form.addEventListener("change", (event) => {
      if (event.target.matches("[data-dependent-controller]")) {
        syncDependentController(event.target);
      }
      if (event.target.matches('input[type="radio"]')) {
        setChoiceState(form, event.target);
        updateQuestionScore(event.target.closest("[data-reactivo-id]"));
        syncFormProgress(form);
      }
      if (event.target.matches('input[type="file"]')) {
        dirtyForms.add(form);
        setSaveState(form, "saving", "Archivos listos para guardar");
        return;
      }
      if (event.target.matches("input, select, textarea")) {
        queueAutosave();
      }
    });

    form.addEventListener("input", (event) => {
      if (event.target.matches("textarea")) {
        queueAutosave();
      }
    });

    form.addEventListener("submit", () => {
      isSubmittingForm = true;
      dirtyForms.delete(form);
      setSaveState(form, "saving", "Guardando módulo...");
    });
  });

  function updateIsoQuestionScore(input) {
    const card = input.closest(".iso-question-card");
    const score = card?.querySelector(".question-score");
    const label = input.closest(".choice-chip")?.querySelector("strong")?.textContent?.trim();
    if (!score || !label) return;
    score.textContent = label;
    score.classList.remove("is-empty");
    card?.classList.add("has-answer");
  }

  function serializeIsoSectionForm(form) {
    const responses = [];
    form.querySelectorAll(".iso-question-card[data-iso-reactivo-id]").forEach((card) => {
      const reactivoId = Number(card.dataset.isoReactivoId);
      const selected = card.querySelector('input[type="radio"]:checked');
      if (!selected) return;
      const observation = card.querySelector(`[name="observacion_${reactivoId}"]`);
      responses.push({
        reactivo_id: reactivoId,
        calificacion: selected.value,
        observacion: observation ? observation.value : "",
      });
    });
    return {
      apartado_id: Number(form.dataset.isoSectionId),
      responses,
    };
  }

  function updateIsoSectionProgress(form, payload) {
    const sectionId = form.dataset.isoSectionId;
    const answered = Number(payload.section_answered ?? 0);
    const total = Number(payload.section_total || form.dataset.isoSectionTotal || 0);
    document.querySelectorAll(`[data-iso-section-nav="${sectionId}"]`).forEach((node) => {
      node.textContent = `${answered}/${total}`;
    });
  }

  document.querySelectorAll("[data-iso-form]").forEach((form) => {
    setChoiceState(form);
    if (form.dataset.readonly === "true") {
      return;
    }

    let timerId = null;

    const queueIsoAutosave = () => {
      const url = form.dataset.isoAutosaveUrl;
      if (!url) return;
      dirtyForms.add(form);
      window.clearTimeout(timerId);
      timerId = window.setTimeout(() => {
        setSaveState(form, "saving", "Guardando...");
        fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "fetch",
          },
          body: JSON.stringify(serializeIsoSectionForm(form)),
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error("No se pudo guardar");
            }
            return response.json();
          })
          .then((payload) => {
            setSaveState(form, "saved", "Guardado");
            updateOverallProgress(payload.completion);
            updateIsoSectionProgress(form, payload);
            dirtyForms.delete(form);
          })
          .catch(() => {
            setSaveState(form, "error", "Error al guardar");
          });
      }, 700);
    };

    form.addEventListener("change", (event) => {
      if (event.target.matches('input[type="file"]')) {
        dirtyForms.add(form);
        setSaveState(form, "saving", "Archivos listos para guardar");
        return;
      }
      if (event.target.matches('.choice-chip input[type="radio"]')) {
        setChoiceState(form, event.target);
        updateIsoQuestionScore(event.target);
        queueIsoAutosave();
      }
      if (event.target.matches("textarea")) {
        queueIsoAutosave();
      }
    });

    form.addEventListener("input", (event) => {
      if (event.target.matches("textarea")) {
        queueIsoAutosave();
      }
    });

    form.addEventListener("submit", () => {
      isSubmittingForm = true;
      dirtyForms.delete(form);
      setSaveState(form, "saving", "Guardando...");
    });
  });

  function syncDocumentControlState(form) {
    const total = Number(form.dataset.documentTotal || 0);
    const covered = form.querySelectorAll("[data-document-point]:checked").length;
    const evidenceSelect = form.querySelector("[data-document-evidence]");
    const observation = form.querySelector('textarea[name="observacion"]');
    const hasEvidence = Boolean(
      evidenceSelect && Array.from(evidenceSelect.options).some((option) => option.selected),
    );
    const coveredTarget = form.querySelector("[data-document-covered]");
    const stateTarget = form.querySelector("[data-document-state]");
    const guidance = form.querySelector("[data-document-guidance]");

    if (coveredTarget) {
      coveredTarget.textContent = String(covered);
    }

    let label = "No cubierto";
    let slug = "low";
    if (covered > 0 && (!total || covered < total)) {
      label = "Cobertura parcial";
      slug = "medium";
    } else if (total > 0 && covered === total) {
      label = "Cubierto";
      slug = "high";
    }

    if (stateTarget) {
      stateTarget.textContent = label;
      stateTarget.classList.remove("status-low", "status-medium", "status-high", "status-empty");
      stateTarget.classList.add(`status-${slug}`);
    }

    if (guidance) {
      if (covered === 0) {
        guidance.textContent = "Sin puntos cubiertos: explica la brecha. No es necesario adjuntar un archivo.";
      } else if (!hasEvidence) {
        guidance.textContent = "La cobertura Parcial o S\u00ed requiere vincular al menos un archivo de la biblioteca antes de enviar a revisi\u00f3n.";
      } else {
        guidance.textContent = "Cobertura sustentada con archivo(s) de la biblioteca documental.";
      }
    }

    if (observation) {
      observation.required = covered === 0;
    }
    if (evidenceSelect) {
      evidenceSelect.required = covered > 0;
    }
  }

  document.querySelectorAll("[data-iso-document-control-form]").forEach((form) => {
    syncDocumentControlState(form);
    if (form.dataset.readonly === "true") {
      return;
    }

    form.addEventListener("change", (event) => {
      if (event.target.matches("[data-document-point], [data-document-evidence]")) {
        syncDocumentControlState(form);
      }
    });

    form.addEventListener("submit", () => {
      isSubmittingForm = true;
    });
  });

  document.querySelectorAll("[data-iso-document-library]").forEach((form) => {
    form.addEventListener("submit", () => {
      isSubmittingForm = true;
    });
  });

  const axisLinks = Array.from(document.querySelectorAll("[data-axis-link]"));
  const axisSections = Array.from(document.querySelectorAll("[data-axis-section]"));

  function setCurrentAxis(axisId) {
    axisLinks.forEach((link) => {
      link.classList.toggle("is-current", link.dataset.axisLink === String(axisId));
    });
  }

  axisLinks.forEach((link) => {
    link.addEventListener("click", () => setCurrentAxis(link.dataset.axisLink));
  });

  if (axisSections.length && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible) {
          setCurrentAxis(visible.target.dataset.axisSection);
        }
      },
      {
        rootMargin: "-24% 0px -46% 0px",
        threshold: [0.15, 0.35, 0.65],
      },
    );
    axisSections.forEach((section) => observer.observe(section));
    const initialAxis = window.location.hash?.replace("#eje-", "") || axisSections[0].dataset.axisSection;
    setCurrentAxis(initialAxis);
  }

  window.addEventListener("beforeunload", (event) => {
    if (isSubmittingForm || (!dirtyForms.size && !hasPendingFiles())) {
      return;
    }
    event.preventDefault();
    event.returnValue = "";
  });

  initializeProgressBars();
})();
