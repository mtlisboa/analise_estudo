(function () {
    "use strict";

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    function waitForPlotly(callback, attempts) {
        if (window.Plotly) {
            callback();
            return;
        }
        if (attempts > 0) {
            window.setTimeout(function () { waitForPlotly(callback, attempts - 1); }, 100);
        }
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
        var config = {responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"]};
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

        function layout(extra) {
            return Object.assign({}, baseLayout, extra || {});
        }

        function emptyLayout(message, extra) {
            return layout(Object.assign({
                xaxis: {visible: false}, yaxis: {visible: false},
                annotations: [{text: message, showarrow: false, font: {color: colors.faint, size: 12}}]
            }, extra || {}));
        }

        var timeline = data.timeline;
        if (timeline.dates.length) {
            Plotly.newPlot("timeline-chart", [
                {x: timeline.dates, y: timeline.score, name: "Índice geral (%)", type: "scatter", mode: "lines+markers", line: {color: colors.primary, width: 3}, marker: {size: 6}},
                {x: timeline.dates, y: timeline.focus, name: "Foco (1–5)", type: "scatter", mode: "lines", yaxis: "y2", line: {color: colors.lime, width: 2}},
                {x: timeline.dates, y: timeline.comprehension, name: "Compreensão (1–5)", type: "scatter", mode: "lines", yaxis: "y2", line: {color: "#29a7a1", width: 2}}
            ], layout({
                xaxis: axis,
                yaxis: Object.assign({title: "Índice (%)", range: [0, 100]}, axis),
                yaxis2: {title: "Escala 1–5", range: [1, 5], overlaying: "y", side: "right", showgrid: false, tickfont: {color: colors.faint, size: 9}},
                margin: {l: 48, r: 48, t: 16, b: 45},
                hovermode: "x unified"
            }), config);
        } else {
            Plotly.newPlot("timeline-chart", [], emptyLayout("Sem autoavaliações no período"), config);
        }

        var classrooms = data.classrooms;
        if (classrooms.labels.length) {
            Plotly.newPlot("classroom-chart", [
                {x: classrooms.labels, y: classrooms.students, name: "Alunos", type: "bar", marker: {color: colors.primary}},
                {x: classrooms.labels, y: classrooms.tests, name: "Testes", type: "bar", marker: {color: colors.lime}}
            ], layout({xaxis: axis, yaxis: Object.assign({dtick: 1}, axis), barmode: "group"}), config);
        } else {
            Plotly.newPlot("classroom-chart", [], emptyLayout("Nenhuma turma no escopo"), config);
        }

        var roleTotal = data.roles.values.reduce(function (sum, value) { return sum + value; }, 0);
        if (roleTotal) {
            Plotly.newPlot("roles-chart", [{
                labels: data.roles.labels, values: data.roles.values, type: "pie", hole: 0.62,
                marker: {colors: [colors.primary, colors.lime, "#29a7a1"]}, textinfo: "label+percent",
                hovertemplate: "%{label}: %{value}<extra></extra>"
            }], layout({showlegend: false, margin: {l: 14, r: 14, t: 8, b: 12}}), config);
        } else {
            Plotly.newPlot("roles-chart", [], emptyLayout("Nenhum vínculo no escopo"), config);
        }

        var scatter = data.scatter2d;
        if (scatter.names.length) {
            Plotly.newPlot("scatter-2d-chart", [{
                x: scatter.focus, y: scatter.comprehension, text: scatter.names,
                customdata: scatter.score, type: "scatter", mode: "markers",
                marker: {size: scatter.motivation.map(function (value) { return 9 + value * 4; }), color: scatter.score, colorscale: [[0, colors.primarySoft], [1, colors.primary]], cmin: 20, cmax: 100, showscale: true, colorbar: {title: "%", thickness: 9}},
                hovertemplate: "<b>%{text}</b><br>Foco: %{x}<br>Compreensão: %{y}<br>Índice: %{customdata}%<extra></extra>"
            }], layout({
                xaxis: Object.assign({title: "Foco", range: [0.5, 5.5], dtick: 1}, axis),
                yaxis: Object.assign({title: "Compreensão", range: [0.5, 5.5], dtick: 1}, axis),
                showlegend: false
            }), config);
        } else {
            Plotly.newPlot("scatter-2d-chart", [], emptyLayout("Sem dados para a distribuição"), config);
        }

        var scatter3d = data.scatter3d;
        if (scatter3d.names.length) {
            Plotly.newPlot("scatter-3d-chart", [{
                x: scatter3d.focus, y: scatter3d.comprehension, z: scatter3d.motivation,
                text: scatter3d.names, customdata: scatter3d.organization,
                type: "scatter3d", mode: "markers",
                marker: {size: 8, color: scatter3d.motivation, colorscale: [[0, colors.primarySoft], [1, colors.primary]], opacity: 0.9},
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
        } else {
            Plotly.newPlot("scatter-3d-chart", [], emptyLayout("Sem dados para o mapa tridimensional"), config);
        }

        var heatmap = data.heatmap;
        if (heatmap.y.length) {
            Plotly.newPlot("heatmap-chart", [{
                x: heatmap.x, y: heatmap.y, z: heatmap.z, type: "heatmap", zmin: 1, zmax: 5,
                colorscale: [[0, colors.primarySoft], [0.5, "#9b82ff"], [1, colors.primary]],
                xgap: 3, ygap: 3, hovertemplate: "<b>%{y}</b><br>%{x}: %{z}/5<extra></extra>",
                colorbar: {title: "1–5", thickness: 10}
            }], layout({
                xaxis: {side: "top", tickfont: {color: colors.soft, size: 10}},
                yaxis: {automargin: true, tickfont: {color: colors.soft, size: 10}},
                margin: {l: 105, r: 30, t: 45, b: 18}
            }), config);
        } else {
            Plotly.newPlot("heatmap-chart", [], emptyLayout("Sem perfis acadêmicos para comparar"), config);
        }

        var resizeTimer;
        window.addEventListener("resize", function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(function () {
                document.querySelectorAll(".analytics-chart").forEach(function (node) {
                    Plotly.Plots.resize(node);
                });
            }, 120);
        });
    }
}());
