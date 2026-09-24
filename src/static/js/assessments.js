(function () {
    "use strict";

    var modal = document.getElementById("assessment-modal");
    if (!modal) return;

    var form = document.getElementById("assessment-form");
    var title = document.getElementById("assessment-modal-title");
    var observationInput = document.getElementById("observation-entry");
    var observationValue = document.getElementById("id_observations");
    var observationList = document.getElementById("observation-list");
    var defaultTechniques = JSON.parse(document.getElementById("assessment-default-techniques").textContent);
    var createAction = form.dataset.createAction;
    var observations = [];
    var activeModal = null;
    var previouslyFocused = null;
    var inertRegions = [];

    function focusableElements(dialog) {
        return Array.from(dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'))
            .filter(function (element) { return !element.hidden && element.offsetParent !== null; });
    }

    function setPageInert(dialog, isInert) {
        if (isInert) {
            var main = dialog.parentElement;
            inertRegions = Array.from(document.body.children).filter(function (element) {
                return element !== main && element.tagName !== "SCRIPT";
            }).concat(Array.from(main.children).filter(function (element) {
                return element !== dialog && element.tagName !== "SCRIPT";
            }));
            inertRegions.forEach(function (element) { element.inert = true; });
        } else {
            inertRegions.forEach(function (element) { element.inert = false; });
            inertRegions = [];
        }
    }

    function openDialog(dialog, initialFocus) {
        previouslyFocused = document.activeElement;
        activeModal = dialog;
        dialog.hidden = false;
        setPageInert(dialog, true);
        document.body.classList.add("modal-open");
        window.setTimeout(function () { initialFocus.focus(); }, 20);
    }

    function closeDialog(dialog) {
        dialog.hidden = true;
        setPageInert(dialog, false);
        document.body.classList.remove("modal-open");
        activeModal = null;
        if (previouslyFocused && document.contains(previouslyFocused)) previouslyFocused.focus();
    }

    function escapeText(value) {
        var element = document.createElement("span");
        element.textContent = value;
        return element.innerHTML;
    }

    function syncObservations() {
        observationValue.value = observations.join("\n");
        observationList.innerHTML = observations.map(function (item, index) {
            return '<span class="observation-chip">' + escapeText(item) + '<button type="button" data-remove-observation="' + index + '" aria-label="Remover ' + escapeText(item) + '">×</button></span>';
        }).join("");
    }

    function seedObservations(value) {
        observations = (value || "").split(/\r?\n/).map(function (item) { return item.trim(); }).filter(Boolean);
        observations = observations.filter(function (item, index) { return observations.indexOf(item) === index; });
        syncObservations();
    }

    function addObservation() {
        var value = observationInput.value.trim();
        if (!value) return;
        if (observations.indexOf(value) === -1) observations.push(value);
        observationInput.value = "";
        syncObservations();
        observationInput.focus();
    }

    function updateTechniqueHint() {
        var technique = form.querySelector("#id_technique");
        var checkedType = form.querySelector('input[name="assessment_types"]:checked');
        var hint = document.getElementById("automatic-technique-hint");
        if (technique.value) {
            hint.textContent = "A técnica escolhida por você será utilizada nesta avaliação.";
        } else if (checkedType && defaultTechniques[checkedType.value]) {
            hint.textContent = "Seleção automática: " + defaultTechniques[checkedType.value] + ".";
        } else {
            hint.textContent = "Selecione um tipo para visualizar a técnica padrão que será aplicada.";
        }
    }

    function setCheckedTypes(ids) {
        var selected = (ids || "").split(",").filter(Boolean);
        form.querySelectorAll('input[name="assessment_types"]').forEach(function (input) {
            input.checked = selected.indexOf(input.value) !== -1;
        });
    }

    function updateAssemblyFields() {
        var method = form.querySelector("#id_assembly_method").value;
        var countField = document.getElementById("assessment-question-count-field");
        var promptField = document.getElementById("assessment-generation-prompt-field");
        countField.hidden = method === "manual";
        promptField.hidden = method !== "ai_curated" && method !== "ai_generated";
    }

    function openModal(editButton) {
        if (editButton) {
            form.action = editButton.dataset.action;
            title.textContent = "Editar avaliação";
            form.querySelector("#id_subject").value = editButton.dataset.subject;
            form.querySelector("#id_topic").value = editButton.dataset.topic;
            form.querySelector("#id_technique").value = editButton.dataset.technique || "";
            form.querySelector("#id_assembly_method").value = editButton.dataset.assemblyMethod || "manual";
            form.querySelector("#id_desired_question_count").value = editButton.dataset.questionCount || "0";
            form.querySelector("#id_generation_prompt").value = editButton.dataset.generationPrompt || "";
            setCheckedTypes(editButton.dataset.types);
            seedObservations(editButton.dataset.observations);
        } else {
            form.reset();
            form.action = createAction;
            title.textContent = "Nova avaliação";
            seedObservations("");
        }
        updateTechniqueHint();
        updateAssemblyFields();
        openDialog(modal, form.querySelector("#id_subject"));
    }

    function closeModal() {
        closeDialog(modal);
    }

    document.getElementById("new-assessment").addEventListener("click", function () { openModal(); });
    document.querySelectorAll(".open-assessment-modal").forEach(function (button) {
        button.addEventListener("click", function () { openModal(); });
    });
    document.querySelectorAll(".edit-assessment").forEach(function (button) {
        button.addEventListener("click", function () { openModal(button); });
    });
    document.querySelectorAll(".close-assessment-modal").forEach(function (button) {
        button.addEventListener("click", closeModal);
    });
    document.getElementById("add-observation").addEventListener("click", addObservation);
    observationInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") { event.preventDefault(); addObservation(); }
    });
    observationList.addEventListener("click", function (event) {
        var button = event.target.closest("[data-remove-observation]");
        if (!button) return;
        observations.splice(Number(button.dataset.removeObservation), 1);
        syncObservations();
    });
    form.addEventListener("change", function (event) {
        if (event.target.name === "assessment_types" || event.target.name === "technique") updateTechniqueHint();
        if (event.target.name === "assembly_method") updateAssemblyFields();
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !modal.hidden) closeModal();
        if (event.key === "Tab" && activeModal) {
            var focusable = focusableElements(activeModal);
            if (!focusable.length) return;
            var first = focusable[0];
            var last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    });
    form.addEventListener("submit", function () { syncObservations(); });

    seedObservations(observationValue.value);
    if (document.documentElement.dataset.openAssessmentModal === "true") {
        openDialog(modal, form.querySelector("#id_subject"));
        updateTechniqueHint();
        updateAssemblyFields();
    }

    var questionModal = document.getElementById("question-modal");
    var questionForm = document.getElementById("question-form");
    var questionType = document.getElementById("id_question_type");
    var questionOptionsField = document.getElementById("question-options-field");
    var questionAnswerLabel = document.getElementById("question-answer-label");
    var questionAnswerHint = document.getElementById("question-answer-hint");
    var questionAssessmentName = document.getElementById("question-assessment-name");

    function updateQuestionFields() {
        var isMultipleChoice = questionType.value === "multiple_choice";
        questionOptionsField.hidden = !isMultipleChoice;
        questionAnswerLabel.textContent = isMultipleChoice ? "Alternativa correta" : "Resposta esperada";
        questionAnswerHint.textContent = isMultipleChoice
            ? "Copie exatamente uma das alternativas informadas."
            : "Opcional: descreva os elementos esperados na resposta do aluno.";
    }

    function openQuestionModal(button) {
        questionForm.reset();
        questionForm.action = button.dataset.questionAction;
        questionAssessmentName.textContent = button.dataset.assessment;
        updateQuestionFields();
        openDialog(questionModal, document.getElementById("id_statement"));
    }

    function closeQuestionModal() {
        closeDialog(questionModal);
    }

    document.querySelectorAll(".add-question").forEach(function (button) {
        button.addEventListener("click", function () { openQuestionModal(button); });
    });
    document.querySelectorAll(".close-question-modal").forEach(function (button) {
        button.addEventListener("click", closeQuestionModal);
    });
    questionType.addEventListener("change", updateQuestionFields);
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !questionModal.hidden) closeQuestionModal();
    });
    if (document.documentElement.dataset.openQuestionModal === "true") {
        openDialog(questionModal, document.getElementById("id_statement"));
        updateQuestionFields();
    }
}());
