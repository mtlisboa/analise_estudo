(function () {
    "use strict";

    function ready(callback) {
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", callback);
        else callback();
    }

    function waitForPlotly(callback, attempts) {
        if (window.Plotly) return callback();
        if (attempts > 0) window.setTimeout(function () { waitForPlotly(callback, attempts - 1); }, 100);
    }

    ready(function () {
        var dataNode = document.getElementById("analytics-dashboard-data");
        if (!dataNode) return;
        var dashboardData = JSON.parse(dataNode.textContent);
        waitForPlotly(function () { renderDashboard(dashboardData); }, 100);
    });

    function renderDashboard(data) {
        var styles = getComputedStyle(document.documentElement);
        var colors = {
            text: styles.getPropertyValue("--text").trim(),
            soft: styles.getPropertyValue("--text-soft").trim(),
            faint: styles.getPropertyValue("--text-faint").trim(),
            primary: styles.getPropertyValue("--primary").trim(),
            surface: styles.getPropertyValue("--surface").trim(),
            grid: styles.getPropertyValue("--chart-grid").trim()
        };
        var palette = [colors.primary, "#29a7a1", "#ef9d2f", "#7d62d9", "#2f9f7f", "#d95f76", "#5f86d9", "#9a7635"];
        var selectorConfig = {
            responsive: true,
            displaylogo: false,
            displayModeBar: true,
            scrollZoom: true,
            modeBarButtonsToRemove: ["toImage"]
        };
        var baseLayout = {
            autosize: true,
            margin: {l: 48, r: 20, t: 12, b: 46},
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: {family: "Inter, system-ui, sans-serif", color: colors.soft, size: 11},
            legend: {orientation: "h", y: 1.13, x: 0, font: {size: 10}},
            hoverlabel: {bgcolor: colors.surface, bordercolor: colors.grid, font: {color: colors.text}}
        };
        var axis = {gridcolor: colors.grid, zeroline: false, tickfont: {color: colors.faint, size: 9}};

        function layout(extra) { return Object.assign({}, baseLayout, extra || {}); }
        function emptyLayout(message, extra) {
            return layout(Object.assign({
                xaxis: {visible: false}, yaxis: {visible: false},
                annotations: [{text: message, showarrow: false, font: {color: colors.faint, size: 12}}]
            }, extra || {}));
        }
        function unique(values) {
            return values.filter(function (value, index) { return values.indexOf(value) === index; });
        }

        var hasSnapshots = Array.isArray(data.students);
        var students = hasSnapshots ? data.students : (data.scatter2d.names || []).map(function (name, index) {
            var heatmapIndex = (data.heatmap.y || []).indexOf(name);
            var heatmapValues = heatmapIndex === -1 ? [] : data.heatmap.z[heatmapIndex];
            return {
                id: "legacy-" + index,
                name: name,
                classrooms: [],
                averageScore: data.scatter2d.score[index],
                latest: {
                    focus: data.scatter2d.focus[index], comprehension: data.scatter2d.comprehension[index],
                    motivation: data.scatter2d.motivation[index], organization: heatmapValues[1] || 0, score: data.scatter2d.score[index]
                },
                assessments: []
            };
        });
        var studentById = {};
        students.forEach(function (student) { studentById[String(student.id)] = student; });

        function selectedStudents(ids) {
            var selected = {};
            ids.forEach(function (id) { selected[String(id)] = true; });
            return students.filter(function (student) { return selected[String(student.id)]; });
        }

        var classroomMap = {};
        students.forEach(function (student) {
            (student.classrooms || []).forEach(function (room) { classroomMap[String(room.id)] = room.name; });
        });
        var classroomIds = Object.keys(classroomMap).sort(function (a, b) { return classroomMap[a].localeCompare(classroomMap[b]); });
        if (students.some(function (student) { return !(student.classrooms || []).length; })) {
            classroomMap.unassigned = "Sem turma";
            classroomIds.push("unassigned");
        }
        var classroomSelect = document.getElementById("classroom-scope-select");
        classroomIds.forEach(function (id) {
            var option = document.createElement("option");
            option.value = id; option.textContent = classroomMap[id]; classroomSelect.appendChild(option);
        });

        var selectorTraces = classroomIds.map(function (classroomId, traceIndex) {
            var classroomStudents = students.filter(function (student) {
                if (classroomId === "unassigned") return !(student.classrooms || []).length;
                return (student.classrooms || []).some(function (room) { return String(room.id) === classroomId; });
            });
            return {
                name: classroomMap[classroomId],
                x: classroomStudents.map(function (item) { return item.latest.focus; }),
                y: classroomStudents.map(function (item) { return item.latest.comprehension; }),
                text: classroomStudents.map(function (item) { return item.name; }),
                customdata: classroomStudents.map(function (item) {
                    return [String(item.id), item.latest.score, item.classrooms.map(function (room) { return room.name; }).join(", ") || "Sem turma"];
                }),
                type: "scatter", mode: "markers",
                marker: {size: classroomStudents.map(function (item) { return 10 + item.latest.motivation * 4; }), color: palette[traceIndex % palette.length], line: {color: colors.surface, width: 1}},
                selected: {marker: {opacity: 1, line: {color: colors.text, width: 3}}},
                unselected: {marker: {opacity: 0.18}},
                hovertemplate: "<b>%{text}</b><br>%{customdata[2]}<br>Foco: %{x}<br>Compreensão: %{y}<br>Índice: %{customdata[1]}%<extra></extra>"
            };
        });

        var selectorNode = document.getElementById("classroom-scatter-chart");
        var allIds = students.map(function (student) { return String(student.id); });
        var originalAverageText = document.getElementById("metric-average").textContent;
        var savedStudentSelection = document.getElementById("id_selected_students");
        var savedSelectionLabel = document.getElementById("id_selection_label");

        function updateScatterSelection(ids) {
            var selectingAll = ids.length === allIds.length;
            selectorTraces.forEach(function (trace, traceIndex) {
                var points = [];
                trace.customdata.forEach(function (custom, pointIndex) {
                    if (ids.indexOf(String(custom[0])) !== -1) points.push(pointIndex);
                });
                Plotly.restyle(selectorNode, {selectedpoints: selectingAll ? null : [points]}, [traceIndex]);
            });
        }

        function updateTable(ids) {
            var selected = {};
            ids.forEach(function (id) { selected[String(id)] = true; });
            var visible = 0;
            document.querySelectorAll(".analytics-table tbody tr[data-student-id]").forEach(function (row) {
                var show = Boolean(selected[row.dataset.studentId]);
                row.hidden = !show;
                if (show) visible += 1;
            });
            var count = document.getElementById("ranking-count");
            if (count) count.textContent = visible + (visible === 1 ? " registro" : " registros");
        }

        function applyScope(ids, title, description, classroomId) {
            ids = unique(ids.map(String));
            var scoped = selectedStudents(ids);
            classroomSelect.value = classroomId || "";
            var summary = document.getElementById("analysis-selection-summary");
            summary.querySelector("strong").textContent = title;
            summary.querySelector("p").textContent = description;
            document.getElementById("metric-students").textContent = scoped.length;
            var scores = [];
            scoped.forEach(function (student) { student.assessments.forEach(function (item) { scores.push(item.score); }); });
            if (!hasSnapshots) scores = scoped.map(function (student) { return student.averageScore; });
            var average = !hasSnapshots && ids.length === allIds.length ? originalAverageText : (scores.length ? Math.round(scores.reduce(function (sum, value) { return sum + value; }, 0) / scores.length) + "%" : "—");
            document.getElementById("metric-average").textContent = average;
            if (savedStudentSelection) savedStudentSelection.value = ids.length === allIds.length ? "" : ids.join(",");
            if (savedSelectionLabel) savedSelectionLabel.value = ids.length === allIds.length ? "" : title;
            updateScatterSelection(ids);
            updateTable(ids);
        }

        function resetScope() {
            applyScope(allIds, "Todos os alunos", "Use o gráfico para selecionar uma turma, um grupo ou um aluno.", "");
        }

        if (selectorTraces.length) {
            Plotly.newPlot(selectorNode, selectorTraces, layout({
                dragmode: "lasso", clickmode: "event+select",
                xaxis: Object.assign({title: "Foco", range: [0.5, 5.5], dtick: 1}, axis),
                yaxis: Object.assign({title: "Compreensão", range: [0.5, 5.5], dtick: 1}, axis),
                margin: {l: 48, r: 20, t: 35, b: 48}
            }), selectorConfig).then(function () {
                selectorNode.on("plotly_click", function (eventData) {
                    var point = eventData.points[0];
                    var id = String(point.customdata[0]);
                    applyScope([id], point.text, "Aluno selecionado no mapa de dispersão.", "");
                });
                selectorNode.on("plotly_selected", function (eventData) {
                    if (!eventData || !eventData.points || !eventData.points.length) return;
                    var ids = unique(eventData.points.map(function (point) { return String(point.customdata[0]); }));
                    applyScope(ids, "Grupo de " + ids.length + " alunos", "Grupo selecionado diretamente no mapa de dispersão.", "");
                });
                selectorNode.on("plotly_legendclick", function (eventData) {
                    var classroomId = classroomIds[eventData.curveNumber];
                    classroomSelect.value = classroomId;
                    classroomSelect.dispatchEvent(new Event("change"));
                    return false;
                });
                selectorNode.on("plotly_doubleclick", function () { resetScope(); return false; });
                resetScope();
            });
        } else {
            Plotly.newPlot(selectorNode, [], emptyLayout("Sem alunos com autoavaliações no período"), selectorConfig);
            updateTable([]);
        }

        classroomSelect.addEventListener("change", function () {
            if (!this.value) return resetScope();
            var classroomId = this.value;
            var ids = students.filter(function (student) {
                if (classroomId === "unassigned") return !(student.classrooms || []).length;
                return (student.classrooms || []).some(function (room) { return String(room.id) === classroomId; });
            }).map(function (student) { return String(student.id); });
            applyScope(ids, classroomMap[classroomId], ids.length + (ids.length === 1 ? " aluno nesta turma." : " alunos nesta turma."), classroomId);
        });
        document.getElementById("clear-analysis-selection").addEventListener("click", resetScope);

        var selectorCard = selectorNode.closest(".analytics-selector-card");
        var sizeToggle = document.getElementById("toggle-analysis-chart-size");
        function setExpanded(expanded) {
            selectorCard.classList.toggle("is-expanded", expanded);
            document.body.classList.toggle("analytics-chart-expanded", expanded);
            sizeToggle.setAttribute("aria-expanded", String(expanded));
            sizeToggle.textContent = expanded ? "Recolher gráfico" : "Expandir gráfico";
            window.setTimeout(function () { Plotly.Plots.resize(selectorNode); }, 80);
        }
        sizeToggle.addEventListener("click", function () {
            setExpanded(!selectorCard.classList.contains("is-expanded"));
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && selectorCard.classList.contains("is-expanded")) {
                setExpanded(false);
            }
        });

        var resizeTimer;
        window.addEventListener("resize", function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(function () {
                document.querySelectorAll(".analytics-chart").forEach(function (node) { Plotly.Plots.resize(node); });
            }, 120);
        });
    }
}());
