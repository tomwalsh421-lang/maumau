const input = document.querySelector("[data-team-search]");

if (input instanceof HTMLInputElement) {
  const targetId = input.dataset.teamSearchTarget;
  const results = targetId ? document.getElementById(targetId) : null;
  let timer = 0;

  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    const query = input.value.trim();
    if (!results) {
      return;
    }
    if (!query) {
      results.innerHTML = "";
      return;
    }
    timer = window.setTimeout(async () => {
      const response = await fetch(`/api/teams/search?q=${encodeURIComponent(query)}`);
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      results.innerHTML = payload
        .map(
          (team) =>
            `<a class="search-result-link" href="${team.url}"><div><strong>${team.team_name}</strong>${team.match_hint ? `<p class="muted team-card-hint">${team.match_hint}</p>` : ""}</div><span class="team-card-key">${team.team_key}</span></a>`
        )
        .join("");
    }, 160);
  });
}

const pendingDashboard = document.querySelector("[data-refresh-dashboard]");

if (pendingDashboard instanceof HTMLElement) {
  window.setTimeout(() => {
    window.location.reload();
  }, 3500);
}

const interactiveCharts = document.querySelectorAll("[data-interactive-chart]");

interactiveCharts.forEach((chart) => {
  if (!(chart instanceof HTMLElement)) {
    return;
  }

  const seriesLabel = chart.querySelector("[data-chart-series]");
  const valueLabel = chart.querySelector("[data-chart-value]");
  const pointLabel = chart.querySelector("[data-chart-label]");
  const detailLabel = chart.querySelector("[data-chart-detail]");
  const points = Array.from(chart.querySelectorAll("[data-chart-point]")).filter(
    (point) => point instanceof SVGElement
  );
  const toggles = Array.from(chart.querySelectorAll("[data-chart-toggle]")).filter(
    (toggle) => toggle instanceof HTMLButtonElement
  );

  const updateInspector = (point) => {
    if (!(point instanceof SVGElement)) {
      return;
    }
    const {
      chartSeriesLabel = "",
      chartValue = "",
      chartLabel = "",
      chartDetail = "",
    } = point.dataset;
    if (seriesLabel) {
      seriesLabel.textContent = chartSeriesLabel;
    }
    if (valueLabel) {
      valueLabel.textContent = chartValue;
    }
    if (pointLabel) {
      pointLabel.textContent = chartLabel;
    }
    if (detailLabel) {
      detailLabel.textContent = chartDetail;
    }
    points.forEach((candidate) => {
      candidate.classList.toggle("is-active", candidate === point);
    });
  };

  const resetInspector = () => {
    const activeSeries = chart.dataset.activeSeries || "";
    if (activeSeries) {
      const activePoint =
        points.find(
          (point) =>
            point.dataset.seriesKey === activeSeries &&
            point.classList.contains("is-terminal")
        ) || points.find((point) => point.dataset.seriesKey === activeSeries);
      if (activePoint) {
        updateInspector(activePoint);
        return;
      }
    }
    const {
      defaultSeries = "",
      defaultValue = "",
      defaultLabel = "",
      defaultDetail = "",
    } = chart.dataset;
    if (seriesLabel) {
      seriesLabel.textContent = defaultSeries;
    }
    if (valueLabel) {
      valueLabel.textContent = defaultValue;
    }
    if (pointLabel) {
      pointLabel.textContent = defaultLabel;
    }
    if (detailLabel) {
      detailLabel.textContent = defaultDetail;
    }
    points.forEach((point) => point.classList.remove("is-active"));
  };

  const syncSeriesVisibility = () => {
    const activeSeries = chart.dataset.activeSeries || "";
    const seriesNodes = chart.querySelectorAll("[data-series-key]");
    seriesNodes.forEach((node) => {
      if (!(node instanceof SVGElement)) {
        return;
      }
      const muted = activeSeries && node.dataset.seriesKey !== activeSeries;
      node.classList.toggle("is-muted", Boolean(muted));
    });
    toggles.forEach((toggle) => {
      const isActive = activeSeries === toggle.dataset.chartToggle;
      toggle.classList.toggle("is-active", isActive);
      toggle.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  };

  points.forEach((point) => {
    point.addEventListener("mouseenter", () => updateInspector(point));
    point.addEventListener("focus", () => updateInspector(point));
  });

  chart.addEventListener("mouseleave", () => {
    resetInspector();
  });

  toggles.forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const seriesKey = toggle.dataset.chartToggle || "";
      chart.dataset.activeSeries =
        chart.dataset.activeSeries === seriesKey ? "" : seriesKey;
      syncSeriesVisibility();
      const activeSeries = chart.dataset.activeSeries || "";
      const targetPoint =
        points.find(
          (point) =>
            point.dataset.seriesKey === activeSeries &&
            point.classList.contains("is-terminal")
        ) ||
        points.find((point) => point.dataset.seriesKey === activeSeries);
      if (targetPoint) {
        updateInspector(targetPoint);
        return;
      }
      resetInspector();
    });
  });

  resetInspector();
  syncSeriesVisibility();
});
