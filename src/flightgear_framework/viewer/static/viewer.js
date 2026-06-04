let payload = null;
let activeGroupId = null;
let rawSelected = new Set();
let resizeObserver = null;
let plotResizeTimer = null;

// Browser logic for rendering focused telemetry datasets and validation metrics.
const statusLabels = {
  pass: "PASS",
  warn: "WARN",
  fail: "FAIL",
  info: "INFO",
};

const themeStorageKey = "flightgear-telemetry-viewer-theme";

async function bootstrap() {
  initTheme();
  initReportButton();
  const response = await fetch("/api/dataset");
  payload = await response.json();
  activeGroupId = payload.plot_groups[0]?.id || null;
  rawSelected = new Set(payload.columns.numeric.filter((key) => !isXKey(key)).slice(0, 12));
  renderAll();
  await maybeRenderReportPreview();
  schedulePlotResize();
  window.addEventListener("resize", schedulePlotResize);
}

function renderAll() {
  renderHeader();
  renderFocus();
  renderPhases();
  renderLogs();
  renderMetrics();
  renderTabs();
  renderActiveGroup();
  renderRawExplorer();
}

function renderHeader() {
  document.getElementById("profile-title").textContent = payload.profile.name;
  const meta = document.getElementById("topbar-meta");
  meta.innerHTML = "";
  [
    `Test: ${payload.profile.name}`,
    `Samples: ${payload.csv.focused_rows} of ${payload.csv.full_rows}`,
    `Backend: ${payload.native_backend.backend.toUpperCase()}`,
    payload.focus_window.enabled ? "Mode: Focused window" : "Mode: Full CSV",
  ].forEach((item) => {
    const pill = document.createElement("span");
    pill.className = "meta-pill";
    pill.textContent = item;
    meta.appendChild(pill);
  });
}

function initTheme() {
  const stored = localStorage.getItem(themeStorageKey);
  const theme = stored === "dark" || stored === "light" ? stored : "light";
  applyTheme(theme);
  const button = document.getElementById("theme-toggle");
  button.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    redrawPlotsForTheme();
  });
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(themeStorageKey, theme);
  const button = document.getElementById("theme-toggle");
  if (!button) {
    return;
  }
  const dark = theme === "dark";
  button.textContent = dark ? "Light mode" : "Dark mode";
  button.setAttribute("aria-pressed", `${dark}`);
}

function renderFocus() {
  const focus = payload.focus_window;
  const rows = [
    ["CSV", payload.csv.name || basename(payload.csv.path)],
    ["X axis", focus.x_label],
    ["Source", focus.source],
    ["Pre", formatNumber(focus.pre_seconds, "s")],
    ["Post", formatNumber(focus.post_seconds, "s")],
    ["Event start", formatNumber(focus.event_start_elapsed_s, "s")],
    ["Visible start", formatNumber(focus.start_elapsed_s, "s")],
    ["Visible end", formatNumber(focus.end_elapsed_s, "s")],
  ];
  const target = document.getElementById("focus-summary");
  target.innerHTML = "";
  rows.forEach(([label, value]) => {
    const row = document.createElement("div");
    row.className = "kv-row";
    row.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "-")}</strong>`;
    target.appendChild(row);
  });
}

function renderPhases() {
  const target = document.getElementById("phase-list");
  target.innerHTML = "";
  const phases = countValues(payload.data.phase || []);
  Object.entries(phases).forEach(([phase, count]) => {
    const pill = document.createElement("span");
    pill.className = "phase-pill";
    pill.textContent = `${phase} (${count})`;
    target.appendChild(pill);
  });
  if (!target.children.length) {
    target.textContent = "No phase data";
  }
}

function renderLogs() {
  const target = document.getElementById("log-list");
  target.innerHTML = "";
  payload.logs.forEach((log) => {
    const block = document.createElement("div");
    block.className = "log-block";
    const lines = log.lines.length ? log.lines : ["Missing or empty."];
    block.innerHTML = `
      <h3>${escapeHtml(log.name)}</h3>
      <div class="log-lines">${lines.map(escapeHtml).join("<br>")}</div>
    `;
    target.appendChild(block);
  });
}

function renderMetrics() {
  const grid = document.getElementById("metrics-grid");
  grid.innerHTML = "";
  payload.validation_metrics.forEach((metric) => {
    const card = document.createElement("article");
    card.className = `metric-card ${metric.status}`;
    const status = statusLabels[metric.status] || metric.status.toUpperCase();
    card.innerHTML = `
      <div class="status-pill">${escapeHtml(status)}</div>
      <h3>${escapeHtml(metric.label)}</h3>
      <div class="metric-value">${escapeHtml(formatMetric(metric))}</div>
      <p class="metric-details">${escapeHtml(metric.details || "")}</p>
    `;
    grid.appendChild(card);
  });
}

function renderTabs() {
  const target = document.getElementById("group-tabs");
  target.innerHTML = "";
  payload.plot_groups.forEach((group) => {
    const button = document.createElement("button");
    button.textContent = group.title;
    button.className = group.id === activeGroupId ? "active" : "";
    button.addEventListener("click", () => {
      activeGroupId = group.id;
      renderTabs();
      renderActiveGroup();
    });
    target.appendChild(button);
  });
}

function renderActiveGroup() {
  const group = payload.plot_groups.find((item) => item.id === activeGroupId);
  const grid = document.getElementById("chart-grid");
  const description = document.getElementById("group-description");
  purgePlots(grid);
  grid.innerHTML = "";
  if (!group) {
    description.textContent = "";
    grid.innerHTML = `<div class="empty-state">No plot groups available.</div>`;
    return;
  }
  description.textContent = group.description;
  group.series.forEach((series) => {
    renderSeriesChart(grid, series);
  });
  observePlots();
  schedulePlotResize();
}

function renderRawExplorer() {
  const search = document.getElementById("raw-search");
  const list = document.getElementById("raw-variable-list");
  const count = document.getElementById("raw-count");
  const numeric = payload.columns.numeric.filter((key) => !isXKey(key));
  const filter = search.value.trim().toLowerCase();
  const visible = numeric.filter((key) => key.toLowerCase().includes(filter));
  count.textContent = `${numeric.length} numeric variables`;
  list.innerHTML = "";
  visible.forEach((key) => {
    const label = document.createElement("label");
    const checked = rawSelected.has(key) ? "checked" : "";
    label.innerHTML = `<input type="checkbox" data-key="${escapeHtml(key)}" ${checked} /> ${escapeHtml(key)}`;
    list.appendChild(label);
  });
  list.querySelectorAll("input[type='checkbox']").forEach((input) => {
    input.addEventListener("change", (event) => {
      const key = event.target.getAttribute("data-key");
      if (event.target.checked) {
        rawSelected.add(key);
      } else {
        rawSelected.delete(key);
      }
      renderRawCharts();
    });
  });
  renderRawCharts();
}

function renderRawCharts() {
  const grid = document.getElementById("raw-chart-grid");
  purgePlots(grid);
  grid.innerHTML = "";
  if (!rawSelected.size) {
    grid.innerHTML = `<div class="empty-state">No variables selected.</div>`;
    return;
  }
  [...rawSelected].forEach((key) => {
    renderSeriesChart(grid, { key, label: key, unit: "", kind: "line" });
  });
  observePlots();
  schedulePlotResize();
}

function renderSeriesChart(grid, series) {
  const values = payload.data[series.key];
  if (!values) {
    return;
  }
  const panel = document.createElement("article");
  panel.className = "chart-panel";
  const title = document.createElement("div");
  title.className = "chart-title";
  title.textContent = series.unit ? `${series.label} (${series.unit})` : series.label;
  const plot = document.createElement("div");
  plot.className = "plot";
  panel.appendChild(title);
  panel.appendChild(plot);
  grid.appendChild(panel);

  const xKey = payload.focus_window.x_key;
  const x = payload.data[xKey] || payload.data.elapsed_s;
  const traceInfo = buildTrace(series, x, values);
  const layout = buildLayout(series, traceInfo.yaxis);
  Plotly.newPlot(plot, [traceInfo.trace], layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
  }).then(() => {
    schedulePlotResize();
  });
}

function buildTrace(series, x, values) {
  if (isCategorical(values)) {
    const categories = [...new Set(values.filter((value) => value !== null && value !== ""))];
    const y = values.map((value) => categories.indexOf(value));
    return {
      trace: {
        x,
        y,
        text: values.map((value) => value ?? ""),
        mode: "markers+lines",
        type: "scatter",
        line: { color: "#0f766e", width: 1.5 },
        marker: { size: 6 },
        hovertemplate: "%{x:.2f}s<br>%{text}<extra></extra>",
      },
      yaxis: {
        tickmode: "array",
        tickvals: categories.map((_, index) => index),
        ticktext: categories.map((value) => `${value}`),
      },
    };
  }
  return {
    trace: {
      x,
      y: values.map(toPlotNumber),
      mode: "lines+markers",
      type: "scatter",
      line: { color: "#0f766e", width: 2 },
      marker: { size: 4 },
      hovertemplate: "%{x:.2f}s<br>%{y}<extra></extra>",
    },
    yaxis: {},
  };
}

function buildLayout(series, yaxisOverrides = {}, colorOverride = null) {
  const shapes = [];
  const colors = colorOverride || themeColors();
  if (payload.focus_window.enabled && payload.focus_window.x_key === "event_time_s") {
    shapes.push({
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: 0,
      x1: payload.focus_window.post_seconds ?? 0,
      y0: 0,
      y1: 1,
      fillcolor: colors.failureFill,
      line: { width: 0 },
    });
    shapes.push({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: 0,
      x1: 0,
      y0: 0,
      y1: 1,
      line: { color: colors.failureLine, width: 2 },
    });
  }
  return {
    margin: { l: 54, r: 14, t: 10, b: 38 },
    paper_bgcolor: colors.paper,
    plot_bgcolor: colors.plot,
    font: { color: colors.text },
    xaxis: {
      title: payload.focus_window.x_label,
      gridcolor: colors.grid,
      zerolinecolor: colors.failureLine,
      linecolor: colors.axis,
      tickcolor: colors.axis,
    },
    yaxis: {
      title: series.unit || "",
      gridcolor: colors.grid,
      linecolor: colors.axis,
      tickcolor: colors.axis,
      automargin: true,
      ...yaxisOverrides,
    },
    shapes,
  };
}

function themeColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    text: styles.getPropertyValue("--text").trim(),
    paper: styles.getPropertyValue("--plot-paper").trim(),
    plot: styles.getPropertyValue("--plot-paper").trim(),
    grid: styles.getPropertyValue("--plot-grid").trim(),
    axis: styles.getPropertyValue("--line").trim(),
    failureFill: styles.getPropertyValue("--plot-failure-fill").trim(),
    failureLine: styles.getPropertyValue("--red").trim(),
  };
}

function reportColors() {
  return {
    text: "#1f2933",
    paper: "#ffffff",
    plot: "#ffffff",
    grid: "#e7edf3",
    axis: "#d7dde5",
    failureFill: "rgba(180, 35, 24, 0.07)",
    failureLine: "#b42318",
  };
}

function initReportButton() {
  const button = document.getElementById("report-button");
  button.addEventListener("click", () => {
    generatePdfReport();
  });
}

async function generatePdfReport() {
  if (!payload) {
    return;
  }
  const button = document.getElementById("report-button");
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = "Preparing report...";
  try {
    await buildPrintableReport();
    window.setTimeout(() => {
      window.print();
    }, 120);
  } finally {
    window.setTimeout(() => {
      button.disabled = false;
      button.textContent = originalLabel;
    }, 400);
  }
}

async function buildPrintableReport() {
  const report = document.getElementById("print-report");
  report.innerHTML = "";
  report.setAttribute("aria-hidden", "false");
  report.appendChild(buildReportHeader());
  report.appendChild(buildReportMetrics());
  report.appendChild(buildReportTables());

  const chartSection = document.createElement("section");
  chartSection.className = "report-section";
  chartSection.innerHTML = `
    <h2>Generated Charts</h2>
    <p class="report-note">Configured profile charts are exported as fixed images for stable PDF output.</p>
  `;
  report.appendChild(chartSection);

  const groups = payload.plot_groups.filter((group) => group.id !== "all_numeric");
  for (const group of groups) {
    const groupBlock = document.createElement("section");
    groupBlock.className = "report-chart-group";
    groupBlock.innerHTML = `
      <h3>${escapeHtml(group.title)}</h3>
      <p>${escapeHtml(group.description || "")}</p>
    `;
    const grid = document.createElement("div");
    grid.className = "report-chart-grid";
    groupBlock.appendChild(grid);
    chartSection.appendChild(groupBlock);

    for (const series of group.series) {
      const imageUrl = await chartImageForSeries(series);
      if (!imageUrl) {
        continue;
      }
      const figure = document.createElement("figure");
      figure.className = "report-figure";
      figure.innerHTML = `
        <img src="${imageUrl}" alt="${escapeHtml(series.label)} chart" />
        <figcaption>${escapeHtml(series.unit ? `${series.label} (${series.unit})` : series.label)}</figcaption>
      `;
      grid.appendChild(figure);
    }
  }
}

async function maybeRenderReportPreview() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("report") !== "preview") {
    return;
  }
  await buildPrintableReport();
  document.body.classList.add("report-preview");
}

function buildReportHeader() {
  const summary = payload.report_summary || {};
  const focus = summary.focus_window || {};
  const header = document.createElement("section");
  header.className = "report-cover";
  header.innerHTML = `
    <p class="report-eyebrow">FlightGear Test Framework</p>
    <h1>${escapeHtml(summary.test_name || payload.profile.name)} Flight Test Report</h1>
    <div class="report-summary-grid">
      ${reportSummaryItem("Aircraft", summary.aircraft)}
      ${reportSummaryItem("Airport", summary.airport)}
      ${reportSummaryItem("Runway", summary.runway)}
      ${reportSummaryItem("CSV", summary.csv_name || payload.csv.name)}
      ${reportSummaryItem("Samples", `${summary.focused_rows ?? payload.csv.focused_rows} of ${summary.full_rows ?? payload.csv.full_rows}`)}
      ${reportSummaryItem("Native backend", payload.native_backend.backend.toUpperCase())}
      ${reportSummaryItem("Focus source", focus.source || payload.focus_window.source)}
      ${reportSummaryItem("Visible window", reportWindowLabel(focus))}
      ${reportSummaryItem("Generated", summary.generated_at)}
    </div>
  `;
  return header;
}

function buildReportMetrics() {
  const section = document.createElement("section");
  section.className = "report-section";
  section.innerHTML = "<h2>Validation Summary</h2>";
  const grid = document.createElement("div");
  grid.className = "report-metric-grid";
  payload.validation_metrics.forEach((metric) => {
    const card = document.createElement("article");
    card.className = `report-metric ${metric.status}`;
    card.innerHTML = `
      <span>${escapeHtml(statusLabels[metric.status] || metric.status.toUpperCase())}</span>
      <h3>${escapeHtml(metric.label)}</h3>
      <strong>${escapeHtml(formatMetric(metric))}</strong>
      <p>${escapeHtml(metric.details || "")}</p>
    `;
    grid.appendChild(card);
  });
  section.appendChild(grid);
  return section;
}

function buildReportTables() {
  const section = document.createElement("section");
  section.className = "report-section";
  section.innerHTML = "<h2>Flight And Control Summary</h2>";
  section.appendChild(buildStatsTable("Control surfaces", payload.report_summary?.control_surfaces || []));
  section.appendChild(buildStatsTable("Key flight signals", payload.report_summary?.key_signals || []));
  return section;
}

function buildStatsTable(title, rows) {
  const block = document.createElement("div");
  block.className = "report-table-block";
  if (!rows.length) {
    block.innerHTML = `<h3>${escapeHtml(title)}</h3><p class="report-note">No data available.</p>`;
    return block;
  }
  block.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <table class="report-table">
      <thead>
        <tr>
          <th>Signal</th>
          <th>Min</th>
          <th>Max</th>
          <th>Mean</th>
          <th>Final</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.label)}${row.unit ? ` (${escapeHtml(row.unit)})` : ""}</td>
            <td>${escapeHtml(formatReportValue(row.min))}</td>
            <td>${escapeHtml(formatReportValue(row.max))}</td>
            <td>${escapeHtml(formatReportValue(row.mean))}</td>
            <td>${escapeHtml(formatReportValue(row.final))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  return block;
}

async function chartImageForSeries(series) {
  const values = payload.data[series.key];
  if (!values) {
    return null;
  }
  const source = document.createElement("div");
  source.className = "report-plot-source";
  source.style.width = "760px";
  source.style.height = "300px";
  document.body.appendChild(source);

  const xKey = payload.focus_window.x_key;
  const x = payload.data[xKey] || payload.data.elapsed_s;
  const traceInfo = buildTrace(series, x, values);
  const layout = {
    ...buildLayout(series, traceInfo.yaxis, reportColors()),
    width: 760,
    height: 300,
    margin: { l: 58, r: 18, t: 16, b: 44 },
  };

  try {
    await Plotly.newPlot(source, [traceInfo.trace], layout, {
      staticPlot: true,
      displayModeBar: false,
    });
    return await Plotly.toImage(source, {
      format: "png",
      width: 760,
      height: 300,
      scale: 2,
    });
  } finally {
    Plotly.purge(source);
    source.remove();
  }
}

function reportSummaryItem(label, value) {
  return `
    <div>
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value ?? "-")}</strong>
    </div>
  `;
}

function reportWindowLabel(focus) {
  const start = focus.start_elapsed_s ?? payload.focus_window.start_elapsed_s;
  const end = focus.end_elapsed_s ?? payload.focus_window.end_elapsed_s;
  if (start === null || start === undefined || end === null || end === undefined) {
    return "Full CSV";
  }
  return `${formatNumber(start, "s")} to ${formatNumber(end, "s")}`;
}

function formatReportValue(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(3).replace(/\.?0+$/, "") : `${value}`;
}

function observePlots() {
  if (resizeObserver) {
    resizeObserver.disconnect();
  }
  resizeObserver = new ResizeObserver(() => {
    schedulePlotResize();
  });
  document.querySelectorAll(".chart-panel, .plot").forEach((element) => {
    resizeObserver.observe(element);
  });
}

function schedulePlotResize() {
  window.requestAnimationFrame(() => {
    resizeAllPlots();
    clearTimeout(plotResizeTimer);
    plotResizeTimer = setTimeout(resizeAllPlots, 180);
  });
}

function resizeAllPlots() {
  document.querySelectorAll(".js-plotly-plot").forEach((plot) => {
    Plotly.Plots.resize(plot);
  });
}

function purgePlots(container) {
  container.querySelectorAll(".js-plotly-plot").forEach((plot) => {
    Plotly.purge(plot);
  });
}

function redrawPlotsForTheme() {
  renderActiveGroup();
  renderRawCharts();
}

function isCategorical(values) {
  const present = values.filter((value) => value !== null && value !== "");
  if (!present.length) {
    return false;
  }
  return present.some((value) => Number.isNaN(Number(value)) && typeof value !== "boolean");
}

function toPlotNumber(value) {
  if (value === null || value === "") {
    return null;
  }
  if (value === true) {
    return 1;
  }
  if (value === false) {
    return 0;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function countValues(values) {
  return values.reduce((acc, value) => {
    const key = value || "blank";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function isXKey(key) {
  return key === "elapsed_s" || key === "event_time_s";
}

function formatMetric(metric) {
  if (metric.value === null || metric.value === undefined) {
    return "-";
  }
  return metric.unit ? `${metric.value} ${metric.unit}` : `${metric.value}`;
}

function formatNumber(value, unit) {
  if (value === null || value === undefined) {
    return "-";
  }
  const number = Number(value);
  const text = Number.isFinite(number) ? number.toFixed(2) : `${value}`;
  return unit ? `${text} ${unit}` : text;
}

function escapeHtml(value) {
  return `${value}`
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function basename(path) {
  return `${path}`.split(/[\\/]/).filter(Boolean).pop() || path;
}

document.getElementById("raw-search").addEventListener("input", renderRawExplorer);
document.getElementById("raw-first").addEventListener("click", () => {
  rawSelected = new Set(payload.columns.numeric.filter((key) => !isXKey(key)).slice(0, 12));
  renderRawExplorer();
});
document.getElementById("raw-all").addEventListener("click", () => {
  rawSelected = new Set(payload.columns.numeric.filter((key) => !isXKey(key)));
  renderRawExplorer();
});
document.getElementById("raw-clear").addEventListener("click", () => {
  rawSelected.clear();
  renderRawExplorer();
});

window.flightGearTelemetryViewer = {
  buildPrintableReport,
};

bootstrap().catch((error) => {
  document.body.innerHTML = `<main class="panel"><h1>Viewer error</h1><pre>${escapeHtml(error.stack || error)}</pre></main>`;
});
