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
            primarySoft: styles.getPropertyValue("--primary-soft").trim(),
            lime: styles.getPropertyValue("--lime").trim(),
            surface: styles.getPropertyValue("--surface").trim(),
            grid: styles.getPropertyValue("--chart-grid").trim()
        };
        var palette = [colors.primary, "#29a7a1", "#ef9d2f", "#7d62d9", "#2f9f7f", "#d95f76", "#5f86d9", "#9a7635"];
        var config = {responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"]};
        var selectorConfig = {responsive: true, displaylogo: false, modeBarButtonsToRemove: ["zoomIn2d", "zoomOut2d", "autoScale2d"]};
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

        function renderTimeline(scopeStudents) {
            if (!hasSnapshots) return renderLegacyTimeline();
            var grouped = {};
            scopeStudents.forEach(function (student) {
                student.assessments.forEach(function (item) {
                    if (!grouped[item.date]) grouped[item.date] = [];
                    grouped[item.date].push(item);
                });
            });
            var dates = Object.keys(grouped).sort();
            if (!dates.length) {
                Plotly.react("timeline-chart", [], emptyLayout("Sem autoavaliações no recorte"), config);
                return;
            }
            function averages(key) {
                return dates.map(function (date) {
                    var values = grouped[date].map(function (item) { return item[key]; });
                    return values.reduce(function (sum, value) { return sum + value; }, 0) / values.length;
                });
            }
            Plotly.react("timeline-chart", [
                {x: dates, y: averages("score"), name: "Índice geral (%)", type: "scatter", mode: "lines+markers", line: {color: colors.primary, width: 3}, marker: {size: 6}},
                {x: dates, y: averages("focus"), name: "Foco (1–5)", type: "scatter", mode: "lines", yaxis: "y2", line: {color: colors.lime, width: 2}},
                {x: dates, y: averages("comprehension"), name: "Compreensão (1–5)", type: "scatter", mode: "lines", yaxis: "y2", line: {color: "#29a7a1", width: 2}}
            ], layout({
                xaxis: axis,
                yaxis: Object.assign({title: "Índice (%)", range: [0, 100]}, axis),
                yaxis2: {title: "Escala 1–5", range: [1, 5], overlaying: "y", side: "right", showgrid: false, tickfont: {color: colors.faint, size: 9}},
                margin: {l: 48, r: 48, t: 16, b: 45}, hovermode: "x unified"
            }), config);
        }

        function renderLegacyTimeline() {
            var timeline = data.timeline;
            if (!timeline.dates.length) {
                Plotly.react("timeline-chart", [], emptyLayout("Sem autoavaliações no período"), config);
                return;
            }
            Plotly.react("timeline-chart", [
                {x: timeline.dates, y: timeline.score, name: "Índice geral (%)", type: "scatter", mode: "lines+markers", line: {color: colors.primary, width: 3}, marker: {size: 6}},
                {x: timeline.dates, y: timeline.focus, name: "Foco (1–5)", type: "scatter", mode: "lines", yaxis: "y2", line: {color: colors.lime, width: 2}},
                {x: timeline.dates, y: timeline.comprehension, name: "Compreensão (1–5)", type: "scatter", mode: "lines", yaxis: "y2", line: {color: "#29a7a1", width: 2}}
            ], layout({
                xaxis: axis, yaxis: Object.assign({title: "Índice (%)", range: [0, 100]}, axis),
                yaxis2: {title: "Escala 1–5", range: [1, 5], overlaying: "y", side: "right", showgrid: false, tickfont: {color: colors.faint, size: 9}},
                margin: {l: 48, r: 48, t: 16, b: 45}, hovermode: "x unified"
            }), config);
        }

        function renderScatter3d(scopeStudents) {
            if (!scopeStudents.length) {
                Plotly.react("scatter-3d-chart", [], emptyLayout("Sem dados para o mapa tridimensional"), config);
                return;
            }
            Plotly.react("scatter-3d-chart", [{
                x: scopeStudents.map(function (item) { return item.latest.focus; }),
                y: scopeStudents.map(function (item) { return item.latest.comprehension; }),
                z: scopeStudents.map(function (item) { return item.latest.motivation; }),
                text: scopeStudents.map(function (item) { return item.name; }),
                customdata: scopeStudents.map(function (item) { return item.classrooms.map(function (room) { return room.name; }).join(", ") || "Sem turma"; }),
                type: "scatter3d", mode: "markers",
                marker: {size: 8, color: scopeStudents.map(function (item) { return item.latest.motivation; }), colorscale: [[0, colors.primarySoft], [1, colors.primary]], opacity: 0.9},
                hovertemplate: "<b>%{text}</b><br>%{customdata}<br>Foco: %{x}<br>Compreensão: %{y}<br>Motivação: %{z}<extra></extra>"
            }], layout({
                margin: {l: 0, r: 0, t: 0, b: 0}, showlegend: false,
                scene: {
                    bgcolor: "rgba(0,0,0,0)",
                    xaxis: {title: "Foco", range: [1, 5], gridcolor: colors.grid, color: colors.soft},
                    yaxis: {title: "Compreensão", range: [1, 5], gridcolor: colors.grid, color: colors.soft},
                    zaxis: {title: "Motivação", range: [1, 5], gridcolor: colors.grid, color: colors.soft},
                    camera: {eye: {x: 1.45, y: 1.45, z: 1.1}}
                }
            }), config);
        }

        function renderHeatmap(scopeStudents) {
            if (!scopeStudents.length) {
                Plotly.react("heatmap-chart", [], emptyLayout("Sem perfis acadêmicos para comparar"), config);
                return;
            }
            Plotly.react("heatmap-chart", [{
                x: ["Foco", "Organização", "Compreensão", "Motivação"],
                y: scopeStudents.map(function (item) { return item.name; }),
                z: scopeStudents.map(function (item) { return [item.latest.focus, item.latest.organization, item.latest.comprehension, item.latest.motivation]; }),
                type: "heatmap", zmin: 1, zmax: 5,
                colorscale: [[0, colors.primarySoft], [0.5, "#9b82ff"], [1, colors.primary]],
                xgap: 3, ygap: 3, hovertemplate: "<b>%{y}</b><br>%{x}: %{z}/5<extra></extra>",
                colorbar: {title: "1–5", thickness: 10}
            }], layout({
                xaxis: {side: "top", tickfont: {color: colors.soft, size: 10}},
                yaxis: {automargin: true, tickfont: {color: colors.soft, size: 10}},
                margin: {l: 105, r: 30, t: 45, b: 18}
            }), config);
        }

        var classrooms = data.classrooms;
        if (classrooms.labels.length) {
            Plotly.newPlot("classroom-chart", [
                {x: classrooms.labels, y: classrooms.students, name: "Alunos", type: "bar", marker: {color: colors.primary}},
                {x: classrooms.labels, y: classrooms.tests, name: "Testes", type: "bar", marker: {color: colors.lime}}
            ], layout({xaxis: axis, yaxis: Object.assign({dtick: 1}, axis), barmode: "group"}), config);
        } else Plotly.newPlot("classroom-chart", [], emptyLayout("Nenhuma turma no escopo"), config);

        var roleTotal = data.roles.values.reduce(function (sum, value) { return sum + value; }, 0);
        if (roleTotal) {
            Plotly.newPlot("roles-chart", [{
                labels: data.roles.labels, values: data.roles.values, type: "pie", hole: 0.62,
                marker: {colors: [colors.primary, colors.lime, "#29a7a1"]}, textinfo: "label+percent",
                hovertemplate: "%{label}: %{value}<extra></extra>"
            }], layout({showlegend: false, margin: {l: 14, r: 14, t: 8, b: 12}}), config);
        } else Plotly.newPlot("roles-chart", [], emptyLayout("Nenhum vínculo no escopo"), config);

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
            updateScatterSelection(ids);
            renderTimeline(scoped);
            renderScatter3d(scoped);
            renderHeatmap(scoped);
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
            renderTimeline([]); renderScatter3d([]); renderHeatmap([]); updateTable([]);
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

        var resizeTimer;
        window.addEventListener("resize", function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(function () {
                document.querySelectorAll(".analytics-chart").forEach(function (node) { Plotly.Plots.resize(node); });
            }, 120);
        });
    }
}());
