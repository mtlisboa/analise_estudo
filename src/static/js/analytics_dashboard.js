(function () {
    "use strict";

    function ready(callback) {
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", callback, {once: true});
        else callback();
    }
    function state(node, kind, title, description) {
        node.dataset.state = kind;
        node.setAttribute("role", "status");
        node.replaceChildren();
        var heading = document.createElement("strong");
        var copy = document.createElement("p");
        heading.textContent = title;
        copy.textContent = description;
        node.append(heading, copy);
    }
    function waitForPlotly(callback, attempts) {
        if (window.Plotly) return callback();
        if (attempts > 0) window.setTimeout(function () { waitForPlotly(callback, attempts - 1); }, 100);
        else document.querySelectorAll(".analytics-chart:not(.classroom-scatter-chart)").forEach(function (node) {
            state(node, "error", "Não foi possível carregar o gráfico", "Os indicadores e tabelas continuam disponíveis. Recarregue a página para tentar novamente.");
        });
    }
    ready(function () {
        var filters = document.querySelector(".analytics-filters, [data-analysis-filters]");
        if (filters) filters.addEventListener("change", function (event) {
            var fields = {organization: ["group", "teacher", "classroom", "student"], group: ["classroom", "student"], teacher: ["classroom", "student"], classroom: ["student"]}[event.target.name];
            if (fields) fields.forEach(function (name) {
                var field = filters.elements.namedItem(name);
                if (field) field.value = "";
            });
        });
        var dataNode = document.getElementById("analytics-dashboard-data");
        if (!dataNode) return;
        document.querySelectorAll(".analytics-chart:not(.classroom-scatter-chart)").forEach(function (node) {
            state(node, "loading", "Preparando visualização", "Carregando os dados do recorte selecionado.");
        });
        var data = JSON.parse(dataNode.textContent);
        waitForPlotly(function () { initialize(data); }, 100);
    });

    function initialize(data) {
        var root = document.querySelector(".analytics-page");
        var mode = document.getElementById("timeline-mode");
        var explore = document.querySelector(".analytics-explore");
        var plotted = new Set();
        var descriptions = {};
        document.querySelectorAll(".analytics-chart:not(.classroom-scatter-chart)").forEach(function (node) { descriptions[node.id] = node.getAttribute("aria-label"); });
        var config = {
            responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false,
            toImageButtonOptions: {format: "png", scale: 2}
        };
        function escapeText(value) {
            return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }
        function colors() {
            var styles = getComputedStyle(root);
            function get(name) { return styles.getPropertyValue("--a-" + name).trim(); }
            return {text: get("text"), muted: get("muted"), grid: get("grid"), surface: get("surface"),
                accent: get("accent"), blue: get("blue"), teal: get("teal"), violet: get("violet"), low: get("low")};
        }
        function render() {
            var c = colors();
            var mobile = root.clientWidth < 600;
            var base = {
                autosize: true, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
                margin: {l: 48, r: 18, t: 18, b: 50},
                font: {family: 'Inter, system-ui, sans-serif', size: 12, color: c.muted},
                legend: {orientation: "h", x: 0, y: -0.24, font: {size: 11, color: c.muted}},
                hoverlabel: {bgcolor: c.surface, bordercolor: c.grid, font: {color: c.text, size: 12}},
                separators: ",.", uirevision: "analytics"
            };
            function axis(extra) {
                return Object.assign({gridcolor: c.grid, zeroline: false, showline: false,
                    tickfont: {size: 11, color: c.muted}, automargin: true, fixedrange: true}, extra || {});
            }
            function plot(id, traces, extra, empty) {
                var node = document.getElementById(id);
                if (!traces.length) {
                    if (plotted.has(id)) { Plotly.purge(node); plotted.delete(id); }
                    state(node, "empty", empty || "Ainda não há dados", "Ajuste os filtros ou aguarde novos registros para visualizar esta análise.");
                    return;
                }
                if (!plotted.has(id)) node.replaceChildren();
                delete node.dataset.state;
                node.setAttribute("role", "img");
                node.setAttribute("aria-label", descriptions[id]);
                var layout = Object.assign({}, base, extra || {});
                try {
                    var result = Plotly.react(node, traces, layout, config);
                    plotted.add(id);
                    Promise.resolve(result).catch(function () {
                        plotted.delete(id);
                        state(node, "error", "Visualização indisponível", "Consulte os indicadores e tabelas abaixo ou recarregue a página.");
                    });
                } catch (error) {
                    plotted.delete(id);
                    state(node, "error", "Visualização indisponível", "Consulte os indicadores e tabelas abaixo ou recarregue a página.");
                }
            }
            var timeline = data.timeline;
            var dimensions = mode && mode.value === "dimensions";
            var lineTraces = [];
            if (timeline.dates.length) {
                if (dimensions) {
                    [["focus", "Foco", c.blue, "solid"], ["organization", "Organização", c.violet, "dot"],
                        ["comprehension", "Compreensão", c.teal, "dash"], ["motivation", "Motivação", c.accent, "dashdot"]].forEach(function (series) {
                        lineTraces.push({x: timeline.dates, y: timeline[series[0]], name: series[1], type: "scatter", mode: "lines+markers",
                            line: {color: series[2], width: 2, dash: series[3]}, marker: {size: 5},
                            hovertemplate: series[1] + ": %{y:.2f}/5<extra></extra>"});
                    });
                } else lineTraces = [{x: timeline.dates, y: timeline.score, name: "Índice geral", type: "scatter", mode: "lines+markers",
                    line: {color: c.accent, width: 3}, marker: {size: 6, color: c.surface, line: {color: c.accent, width: 2}},
                    fill: "tozeroy", fillcolor: document.documentElement.dataset.theme === "dark" ? "rgba(255,173,117,.08)" : "rgba(183,70,8,.06)",
                    hovertemplate: "%{y:.1f}%<extra>Índice geral</extra>"}];
            }
            plot("timeline-chart", lineTraces, {
                xaxis: axis({type: "date", showgrid: false, tickformat: "%d/%m", nticks: mobile ? 4 : 7}),
                yaxis: axis({range: dimensions ? [0.8, 5.2] : [0, 100], dtick: dimensions ? 1 : 25, ticksuffix: dimensions ? "" : "%"}),
                showlegend: dimensions, hovermode: "x unified", margin: {l: 48, r: 14, t: 12, b: dimensions ? 76 : 42}
            }, "Sem autoavaliações no período");

            var classrooms = data.classrooms;
            var roomIndex = classrooms.labels.map(function (_, index) { return index; });
            var roomNode = document.getElementById("classroom-chart");
            roomNode.style.height = Math.max(310, classrooms.labels.length * 58 + 85) + "px";
            plot("classroom-chart", classrooms.labels.length ? [
                {y: roomIndex, x: classrooms.students, name: "Alunos", type: "bar", orientation: "h", marker: {color: c.blue}, customdata: classrooms.labels.map(escapeText), hovertemplate: "%{customdata}<br>%{x} alunos<extra></extra>"},
                {y: roomIndex, x: classrooms.tests, name: "Testes", type: "bar", orientation: "h", marker: {color: c.teal}, customdata: classrooms.labels.map(escapeText), hovertemplate: "%{customdata}<br>%{x} testes<extra></extra>"}
            ] : [], {xaxis: axis({rangemode: "tozero", tickformat: ",d"}), yaxis: axis({showgrid: false, tickvals: roomIndex,
                ticktext: classrooms.labels.map(function (name) { return escapeText(name.length > 25 ? name.slice(0, 24) + "…" : name); }), autorange: "reversed"}),
                barmode: "group", bargap: .35, bargroupgap: .18, margin: {l: mobile ? 100 : 145, r: 18, t: 12, b: 64}
            }, "Nenhuma turma neste recorte");

            var total = data.roles.values.reduce(function (sum, value) { return sum + value; }, 0);
            plot("roles-chart", total ? [{labels: data.roles.labels, values: data.roles.values, type: "pie", hole: .76, sort: false,
                marker: {colors: [c.blue, c.teal, c.violet], line: {color: c.surface, width: 3}}, textinfo: "none",
                hovertemplate: "%{label}: %{value}<br>%{percent}<extra></extra>"}] : [], {
                margin: {l: 12, r: 12, t: 16, b: 70}, legend: {orientation: "h", x: .5, xanchor: "center", y: -.15, font: {size: 12}},
                annotations: [{x: .5, y: .54, text: String(total), showarrow: false, font: {size: 34, color: c.text}},
                    {x: .5, y: .39, text: "pessoas", showarrow: false, font: {size: 12, color: c.muted}}]
            }, "Nenhum vínculo neste recorte");

            var scatter = data.scatter2d;
            plot("scatter-2d-chart", scatter.names.length ? [{x: scatter.focus, y: scatter.comprehension, text: scatter.names.map(escapeText),
                customdata: scatter.score, type: "scatter", mode: "markers", marker: {
                    size: scatter.motivation.map(function (value) { return 8 + value * 4; }), opacity: .75,
                    color: scatter.score, colorscale: [[0, c.low], [1, c.teal]], cmin: 20, cmax: 100,
                    line: {color: c.teal, width: 1}, showscale: true, colorbar: {title: {text: "%", side: "top"}, thickness: 8, len: .8, tickfont: {size: 10}}},
                hovertemplate: "<b>%{text}</b><br>Foco: %{x}/5<br>Compreensão: %{y}/5<br>Índice: %{customdata}%<extra></extra>"}] : [], {
                xaxis: axis({title: {text: "Foco", standoff: 12}, range: [.5, 5.5], dtick: 1}),
                yaxis: axis({title: {text: "Compreensão", standoff: 10}, range: [.5, 5.5], dtick: 1}), showlegend: false,
                margin: {l: 58, r: 42, t: 18, b: 58}
            }, "Sem perfis para comparar");

            var heatmap = data.heatmap;
            var heatRows = heatmap.y.map(function (_, index) { return index; });
            document.getElementById("heatmap-chart").style.height = Math.max(280, heatmap.y.length * 38 + 110) + "px";
            plot("heatmap-chart", heatmap.y.length ? [{x: heatmap.x, y: heatRows, z: heatmap.z, type: "heatmap", zmin: 1, zmax: 5,
                customdata: heatmap.y.map(function (name) { return heatmap.x.map(function () { return escapeText(name); }); }),
                colorscale: [[0, c.low], [1, c.teal]], xgap: 4, ygap: 4,
                hovertemplate: "<b>%{customdata}</b><br>%{x}: %{z}/5<extra></extra>",
                colorbar: {title: {text: "1–5", side: "top"}, thickness: 8, dtick: 1, len: .85}
            }] : [], {xaxis: axis({side: "top", showgrid: false, tickfont: {size: 12}, tickangle: 0}),
                yaxis: axis({tickvals: heatRows, ticktext: heatmap.y.map(escapeText), autorange: "reversed", showgrid: false}),
                margin: {l: 150, r: 40, t: 42, b: 16}
            }, "Sem autoavaliações para comparar");

            if (explore && explore.open) {
                var three = data.scatter3d;
                function sceneAxis(title) { return {title: {text: title}, range: [.5, 5.5], dtick: 1, gridcolor: c.grid, color: c.muted, showbackground: false, zeroline: false}; }
                plot("scatter-3d-chart", three.names.length ? [{x: three.focus, y: three.comprehension, z: three.motivation,
                    text: three.names.map(escapeText), customdata: three.organization.map(escapeText), type: "scatter3d", mode: "markers",
                    marker: {size: 6, color: three.motivation, cmin: 1, cmax: 5, colorscale: [[0, c.low], [1, c.teal]], opacity: .85},
                    hovertemplate: "<b>%{text}</b><br>%{customdata}<br>Foco: %{x}<br>Compreensão: %{y}<br>Motivação: %{z}<extra></extra>"}] : [], {
                    showlegend: false, margin: {l: 0, r: 0, t: 10, b: 0}, scene: {bgcolor: "rgba(0,0,0,0)", xaxis: sceneAxis("Foco"),
                        yaxis: sceneAxis("Compreensão"), zaxis: sceneAxis("Motivação"), camera: {eye: {x: 1.5, y: 1.5, z: 1.2}}}
                }, "Sem dados para o mapa tridimensional");
            }
        }
        if (mode) mode.addEventListener("change", render);
        if (explore) explore.addEventListener("toggle", function () { if (explore.open) render(); });
        var themeObserver = new MutationObserver(render);
        themeObserver.observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
        var resizeTimer;
        window.addEventListener("resize", function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(render, 150);
        });
        render();
    }
}());
