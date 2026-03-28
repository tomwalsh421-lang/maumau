import { startTransition, useDeferredValue, useEffect, useState } from "react";
import type { FormEvent, JSX } from "react";

type AppRoute = "overview" | "models" | "performance" | "upcoming" | "picks";
type WindowKey = "7" | "14" | "30" | "90" | "season";

type OverviewCard = {
  label: string;
  value: string;
  detail: string;
  why_it_matters: string;
};

type MetricDefinition = {
  slug: string;
  label: string;
  summary: string;
  repo_meaning: string;
};

type AvailabilityUsageView = {
  state: string;
  label: string;
  note: string;
};

type AvailabilityDiagnosticStat = {
  label: string;
  value: string;
};

type AvailabilityStatusBadge = {
  label: string;
  value: string;
};

type AvailabilityDiagnosticsSection = {
  usage: AvailabilityUsageView;
  stats: AvailabilityDiagnosticStat[];
  season_labels: string[];
  scope_labels: string[];
  source_labels: string[];
  status_badges: AvailabilityStatusBadge[];
  empty_message: string | null;
};

type PerformanceWindowSummary = {
  key: WindowKey;
  label: string;
  bets: number;
  anchor_label: string;
  wins: number;
  losses: number;
  pushes: number;
  profit_label: string;
  roi_label: string;
  total_staked_label: string;
  drawdown_label: string;
  bankroll_exposure_label: string;
  average_edge_label: string;
  average_ev_label: string;
  close_ev_label: string;
  price_clv_label: string;
  line_clv_label: string;
  positive_clv_rate_label: string;
  explanation: string;
  min_stake_label: string;
  max_stake_label: string;
};

type PickTableRow = {
  game_id: number;
  season_label: string;
  matchup_label: string;
  commence_label: string;
  market_label: string;
  side_label: string;
  sportsbook_label: string;
  line_label: string;
  price_label: string;
  status_label: string;
  status_tone: string;
  stake_label: string;
  edge_label: string;
  expected_value_label: string;
  coverage_label: string;
  profit_label: string;
  books_label: string;
};

type SeasonChartBar = {
  season: number;
  profit_label: string;
  roi_label: string;
  height_pct: number;
  tone: string;
};

type SeasonSummaryCard = {
  season: number;
  bets: number;
  profit_label: string;
  roi_label: string;
  drawdown_label: string;
  close_ev_label: string;
  tone: string;
};

type WindowOption = {
  key: WindowKey;
  label: string;
  selected: boolean;
  min_stake_label: string;
  max_stake_label: string;
};

type ModelArtifactCard = {
  market: string;
  artifact_name: string;
  model_family: string;
  role_label: string;
  trained_range: string;
  trained_at_label: string;
  feature_count: number;
  market_blend_weight_label: string;
  max_market_delta_label: string;
};

type PerformanceChartMarker = {
  label: string;
  offset_pct: number;
};

type PerformanceChartPoint = {
  x_pct: number;
  y_pct: number;
  label: string;
  value_label: string;
  detail: string;
};

type PerformanceChartSeries = {
  label: string;
  style_class: string;
  tone: string;
  points: string[];
  interactive_points: PerformanceChartPoint[];
  value_label: string | null;
  detail: string | null;
  area_points: string[];
};

type PerformanceHistoryChart = {
  title: string;
  subtitle: string;
  start_label: string;
  end_label: string;
  min_label: string;
  max_label: string;
  zero_y: number;
  series: PerformanceChartSeries[];
  markers: PerformanceChartMarker[];
};

type DashboardPage = {
  overview_cards: OverviewCard[];
  recent_summary: PerformanceWindowSummary;
  recent_rows: PickTableRow[];
  upcoming_rows: PickTableRow[];
  strategy_note: string;
  board_note: string;
  availability_usage: AvailabilityUsageView | null;
  season_bars: SeasonChartBar[];
  report_pending: boolean;
  report_message: string | null;
};

type DashboardPayload = {
  selected_window: WindowKey;
  page: DashboardPage;
};

type ModelsPage = {
  overview_cards: OverviewCard[];
  season_cards: SeasonSummaryCard[];
  artifacts: ModelArtifactCard[];
  metric_definitions: MetricDefinition[];
  strategy_note: string;
  availability_usage: AvailabilityUsageView | null;
  availability_diagnostics: AvailabilityDiagnosticsSection | null;
  season_bars: SeasonChartBar[];
};

type ModelsPayload = {
  page: ModelsPage;
};

type PerformancePage = {
  windows: WindowOption[];
  summary: PerformanceWindowSummary;
  rows: PickTableRow[];
  season_cards: SeasonSummaryCard[];
  season_bars: SeasonChartBar[];
  full_history_chart: PerformanceHistoryChart | null;
  season_comparison_chart: PerformanceHistoryChart | null;
};

type PerformancePayload = {
  selected_window: WindowKey;
  page: PerformancePage;
};

type PickHistoryFilters = {
  start: string;
  end: string;
  season: string;
  team: string;
  result: string;
  market: string;
  sportsbook: string;
};

type PicksPage = {
  filters: PickHistoryFilters;
  seasons: string[];
  sportsbooks: string[];
  rows: PickTableRow[];
  total_rows: number;
  truncated: boolean;
};

type PicksPayload = {
  page: PicksPage;
};

type UpcomingAvailabilitySummary = {
  label: string;
  detail: string;
  freshness_note: string | null;
  matching_note: string | null;
  status_note: string | null;
  source_note: string | null;
};

type LiveBoardRow = {
  commence_label: string;
  matchup_label: string;
  game_status_label: string;
  game_status_tone: string;
  board_status_label: string;
  board_status_tone: string;
  side_label: string;
  result_label: string;
  result_tone: string;
  note_label: string;
  availability_label: string | null;
  availability_note: string | null;
};

type UpcomingPage = {
  generated_at_label: string;
  expires_at_label: string;
  policy_note: string;
  recommendation_rows: PickTableRow[];
  watch_rows: PickTableRow[];
  availability_usage: AvailabilityUsageView | null;
  availability_summary: UpcomingAvailabilitySummary | null;
  live_board_rows: LiveBoardRow[];
};

type UpcomingPayload = {
  page: UpcomingPage;
};

const WINDOW_KEYS: WindowKey[] = ["7", "14", "30", "90", "season"];
const PICK_RESULT_OPTIONS = ["all", "win", "loss", "push"] as const;
const PICK_MARKET_OPTIONS = ["all", "spread", "moneyline"] as const;
const DEFAULT_PICK_FILTERS: PickHistoryFilters = {
  start: "",
  end: "",
  season: "all",
  team: "",
  result: "all",
  market: "all",
  sportsbook: "all",
};

function readAppPath(rootElement: HTMLDivElement): string {
  return rootElement.dataset.appPath ?? window.location.pathname;
}

function readAppRoute(rootElement: HTMLDivElement): AppRoute {
  const rawPath = readAppPath(rootElement);
  if (rawPath.includes("/picks")) {
    return "picks";
  }
  if (rawPath.includes("/models")) {
    return "models";
  }
  if (rawPath.includes("/performance")) {
    return "performance";
  }
  return rawPath.includes("/upcoming") ? "upcoming" : "overview";
}

function readInitialWindow(rootElement: HTMLDivElement): WindowKey {
  const datasetWindow = rootElement.dataset.window;
  const searchWindow = new URLSearchParams(window.location.search).get("window");
  const rawWindow = searchWindow ?? datasetWindow ?? "14";
  return WINDOW_KEYS.includes(rawWindow as WindowKey)
    ? (rawWindow as WindowKey)
    : "14";
}

function buildDashboardApiUrl(
  rootElement: HTMLDivElement,
  windowKey: WindowKey,
): string {
  const apiUrl = rootElement.dataset.dashboardApi ?? "/api/dashboard";
  const url = new URL(apiUrl, window.location.origin);
  url.searchParams.set("window", windowKey);
  return url.toString();
}

function buildUpcomingApiUrl(rootElement: HTMLDivElement): string {
  const apiUrl = rootElement.dataset.upcomingApi ?? "/api/upcoming";
  return new URL(apiUrl, window.location.origin).toString();
}

function buildModelsApiUrl(rootElement: HTMLDivElement): string {
  const apiUrl = rootElement.dataset.modelsApi ?? "/api/models";
  return new URL(apiUrl, window.location.origin).toString();
}

function buildPerformanceApiUrl(
  rootElement: HTMLDivElement,
  windowKey: WindowKey,
): string {
  const apiUrl = rootElement.dataset.performanceApi ?? "/api/performance";
  const url = new URL(apiUrl, window.location.origin);
  url.searchParams.set("window", windowKey);
  return url.toString();
}

function buildPicksApiUrl(rootElement: HTMLDivElement, queryString: string): string {
  const apiUrl = rootElement.dataset.picksApi ?? "/api/picks";
  const url = new URL(apiUrl, window.location.origin);
  const search = new URLSearchParams(queryString);
  search.forEach((value, key) => {
    url.searchParams.set(key, value);
  });
  return url.toString();
}

function renderEmptyState(message: string): JSX.Element {
  return (
    <div className="react-row-card">
      <p className="react-row-meta">{message}</p>
    </div>
  );
}

function renderPickRows(
  rows: PickTableRow[],
  options: {
    emptyMessage: string;
    variant: "qualified" | "watch" | "overview" | "settled" | "history";
  },
): JSX.Element {
  const { emptyMessage, variant } = options;
  if (rows.length === 0) {
    return renderEmptyState(emptyMessage);
  }
  return (
    <>
      {rows.map((row) => (
        <article
          className="react-row-card"
          key={`${variant}-${row.game_id}-${row.market_label}-${row.side_label}`}
        >
          <div className="react-row-topline">
            <strong>{row.matchup_label}</strong>
            <span className={`tone-${row.status_tone}`}>{row.status_label}</span>
          </div>
          <p className="react-row-meta">
            {row.commence_label} · {row.side_label}
          </p>
          {variant === "qualified" ? (
            <p className="react-row-meta">
              {row.sportsbook_label} · Edge {row.edge_label} · EV{" "}
              {row.expected_value_label} · Stake {row.stake_label}
            </p>
          ) : null}
          {variant === "watch" ? (
            <p className="react-row-meta">
              Edge {row.edge_label} · Close chance {row.profit_label}
            </p>
          ) : null}
          {variant === "overview" ? (
            <p className="react-row-meta">
              Coverage {row.coverage_label} · Edge {row.edge_label}
            </p>
          ) : null}
          {variant === "settled" ? (
            <p className="react-row-meta">
              {row.sportsbook_label} · {row.status_label} · Profit {row.profit_label}
            </p>
          ) : null}
          {variant === "history" ? (
            <>
              <p className="react-row-meta">
                Season {row.season_label} · {row.commence_label} · {row.market_label}
              </p>
              <p className="react-row-meta">
                {row.sportsbook_label} · {row.side_label} · {row.price_label} ·
                Stake {row.stake_label}
              </p>
              <p className="react-row-meta">
                Edge {row.edge_label} · EV {row.expected_value_label} · Coverage{" "}
                {row.coverage_label} · Books {row.books_label} · Profit{" "}
                {row.profit_label}
              </p>
            </>
          ) : null}
        </article>
      ))}
    </>
  );
}

function renderLiveBoardRows(rows: LiveBoardRow[]): JSX.Element {
  if (rows.length === 0) {
    return renderEmptyState(
      "No live-board rows are available for the recent slate window.",
    );
  }
  return (
    <>
      {rows.map((row) => (
        <article
          className="react-row-card"
          key={`board-${row.matchup_label}-${row.commence_label}`}
        >
          <div className="react-row-topline">
            <strong>{row.matchup_label}</strong>
            <span className={`tone-${row.board_status_tone}`}>
              {row.board_status_label}
            </span>
          </div>
          <p className="react-row-meta">
            {row.commence_label} · {row.game_status_label} · {row.result_label}
          </p>
          <p className="react-row-meta">
            {row.side_label} · {row.note_label}
          </p>
          {row.availability_label ? (
            <p className="react-row-meta">
              Availability {row.availability_label}
              {row.availability_note ? ` · ${row.availability_note}` : ""}
            </p>
          ) : null}
        </article>
      ))}
    </>
  );
}

function renderHistoryChart(
  chart: PerformanceHistoryChart | null,
  options: {
    eyebrow: string;
    emptyMessage: string;
    multiSeries?: boolean;
  },
): JSX.Element {
  const { eyebrow, emptyMessage, multiSeries = false } = options;
  if (chart === null || chart.series.length === 0) {
    return (
      <article className="react-board-panel react-chart-panel">
        <div className="react-panel-heading">
          <div>
            <p className="react-sidecar-label">{eyebrow}</p>
            <h3>Chart pending</h3>
          </div>
        </div>
        {renderEmptyState(emptyMessage)}
      </article>
    );
  }

  const primarySeries = chart.series[0];

  return (
    <article className="react-board-panel react-chart-panel">
      <div className="react-panel-heading">
        <div>
          <p className="react-sidecar-label">{eyebrow}</p>
          <h3>{chart.title}</h3>
        </div>
        {primarySeries.value_label ? (
          <span className={`tone-${primarySeries.tone}`}>
            {primarySeries.value_label}
          </span>
        ) : null}
      </div>
      <div className="react-chart-frame">
        <svg
          className="react-history-svg"
          viewBox="0 0 100 48"
          preserveAspectRatio="none"
        >
          <line
            className="react-chart-zero"
            x1="0"
            y1={chart.zero_y}
            x2="100"
            y2={chart.zero_y}
          />
          {chart.markers.map((marker) => (
            <line
              className="react-chart-marker"
              key={`${eyebrow}-${marker.label}`}
              x1={marker.offset_pct}
              y1="0"
              x2={marker.offset_pct}
              y2="48"
            />
          ))}
          {!multiSeries && primarySeries.area_points.length > 0 ? (
            <polygon
              className="react-history-area"
              points={primarySeries.area_points.join(" ")}
            />
          ) : null}
          {chart.series.map((series) => (
            <polyline
              className={`react-history-line tone-${series.tone}`}
              key={`${eyebrow}-${series.label}`}
              points={series.points.join(" ")}
            />
          ))}
        </svg>
      </div>
      <div className="react-chart-scale">
        <span>{chart.min_label}</span>
        <span>{chart.start_label}</span>
        <span>{chart.end_label}</span>
        <span>{chart.max_label}</span>
      </div>
      <div className="react-chart-legend">
        {chart.series.map((series) => (
          <article
            className="react-chart-legend-item"
            key={`${eyebrow}-legend-${series.label}`}
          >
            <p className="react-sidecar-label">{series.label}</p>
            <strong className={`tone-${series.tone}`}>
              {series.value_label ?? chart.end_label}
            </strong>
            <p className="react-row-meta">{series.detail ?? chart.subtitle}</p>
          </article>
        ))}
      </div>
      <p className="react-summary-note">{chart.subtitle}</p>
    </article>
  );
}

function applyPickHistoryQuery(filters: PickHistoryFilters): string {
  const url = new URL(window.location.href);
  url.search = "";
  for (const [key, value] of Object.entries(filters)) {
    const trimmed = value.trim();
    if (trimmed === "" || trimmed === "all") {
      continue;
    }
    url.searchParams.set(key, trimmed);
  }
  window.history.replaceState({}, "", url);
  return url.search;
}

function readPickHistoryFilters(form: HTMLFormElement): PickHistoryFilters {
  const formData = new FormData(form);
  const readValue = (key: keyof PickHistoryFilters): string => {
    const value = formData.get(key);
    return typeof value === "string" ? value : "";
  };
  return {
    start: readValue("start"),
    end: readValue("end"),
    season: readValue("season") || "all",
    team: readValue("team"),
    result: readValue("result") || "all",
    market: readValue("market") || "all",
    sportsbook: readValue("sportsbook") || "all",
  };
}

function summarizePickFilters(filters: PickHistoryFilters): string[] {
  const summary: string[] = [];
  if (filters.season !== "all") {
    summary.push(`Season ${filters.season}`);
  }
  if (filters.start !== "") {
    summary.push(`Start ${filters.start}`);
  }
  if (filters.end !== "") {
    summary.push(`End ${filters.end}`);
  }
  if (filters.team !== "") {
    summary.push(`Team ${filters.team}`);
  }
  if (filters.result !== "all") {
    summary.push(`Result ${filters.result}`);
  }
  if (filters.market !== "all") {
    summary.push(`Market ${filters.market}`);
  }
  if (filters.sportsbook !== "all") {
    summary.push(`Book ${filters.sportsbook}`);
  }
  return summary;
}

export function App({
  rootElement,
}: {
  rootElement: HTMLDivElement;
}): JSX.Element {
  const appPath = readAppPath(rootElement);
  const route = readAppRoute(rootElement);
  const isBetaRoute = appPath.startsWith("/app");
  const classicHref =
    rootElement.dataset.classicHref ??
    (route === "overview"
      ? "/classic"
      : route === "models"
        ? "/classic/models"
      : route === "performance"
        ? "/classic/performance"
        : route === "picks"
          ? "/classic/picks"
        : "/classic/upcoming");
  const classicLabel =
    rootElement.dataset.classicLabel ??
    (route === "overview"
      ? "Open the server-rendered dashboard fallback"
      : route === "models"
        ? "Open the server-rendered model review fallback"
      : route === "performance"
        ? "Open the server-rendered performance fallback"
        : route === "picks"
          ? "Open the server-rendered picks fallback"
        : "Open the server-rendered recommendations fallback");
  const [windowKey, setWindowKey] = useState<WindowKey>(() =>
    readInitialWindow(rootElement),
  );
  const [picksQuery, setPicksQuery] = useState(() => window.location.search);
  const overviewHref = isBetaRoute
    ? `/app?window=${windowKey}`
    : `/?window=${windowKey}`;
  const modelsHref = isBetaRoute ? "/app/models" : "/models";
  const performanceHref = isBetaRoute
    ? `/app/performance?window=${windowKey}`
    : `/performance?window=${windowKey}`;
  const upcomingHref = isBetaRoute ? "/app/upcoming" : "/upcoming";
  const picksHref = isBetaRoute ? "/app/picks" : "/picks";
  const deferredWindowKey = useDeferredValue(windowKey);
  const deferredPicksQuery = useDeferredValue(picksQuery);
  const [dashboardPayload, setDashboardPayload] = useState<DashboardPayload | null>(
    null,
  );
  const [modelsPayload, setModelsPayload] = useState<ModelsPayload | null>(null);
  const [performancePayload, setPerformancePayload] =
    useState<PerformancePayload | null>(null);
  const [picksPayload, setPicksPayload] = useState<PicksPayload | null>(null);
  const [upcomingPayload, setUpcomingPayload] = useState<UpcomingPayload | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    async function loadView(): Promise<void> {
      try {
        const apiUrl =
          route === "overview"
            ? buildDashboardApiUrl(rootElement, deferredWindowKey)
            : route === "models"
              ? buildModelsApiUrl(rootElement)
            : route === "performance"
              ? buildPerformanceApiUrl(rootElement, deferredWindowKey)
              : route === "picks"
                ? buildPicksApiUrl(rootElement, deferredPicksQuery)
              : buildUpcomingApiUrl(rootElement);
        const response = await fetch(apiUrl, {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Dashboard request failed with ${response.status}.`);
        }
        const data = await response.json();
        startTransition(() => {
          if (route === "overview") {
            setDashboardPayload(data as DashboardPayload);
            setModelsPayload(null);
            setPerformancePayload(null);
            setPicksPayload(null);
            setUpcomingPayload(null);
          } else if (route === "models") {
            setModelsPayload(data as ModelsPayload);
            setDashboardPayload(null);
            setPerformancePayload(null);
            setPicksPayload(null);
            setUpcomingPayload(null);
          } else if (route === "performance") {
            setPerformancePayload(data as PerformancePayload);
            setDashboardPayload(null);
            setModelsPayload(null);
            setPicksPayload(null);
            setUpcomingPayload(null);
          } else if (route === "picks") {
            setPicksPayload(data as PicksPayload);
            setDashboardPayload(null);
            setModelsPayload(null);
            setPerformancePayload(null);
            setUpcomingPayload(null);
          } else {
            setUpcomingPayload(data as UpcomingPayload);
            setDashboardPayload(null);
            setModelsPayload(null);
            setPerformancePayload(null);
            setPicksPayload(null);
          }
          setLoading(false);
        });
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        startTransition(() => {
          setError(err instanceof Error ? err.message : "Unknown dashboard error.");
          setLoading(false);
        });
      }
    }

    void loadView();

    return () => controller.abort();
  }, [deferredPicksQuery, deferredWindowKey, rootElement, route]);

  function handleWindowChange(nextWindow: WindowKey): void {
    const url = new URL(window.location.href);
    url.searchParams.set("window", nextWindow);
    window.history.replaceState({}, "", url);
    setWindowKey(nextWindow);
  }

  function handlePickFiltersSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setPicksQuery(applyPickHistoryQuery(readPickHistoryFilters(event.currentTarget)));
  }

  function handlePickReset(): void {
    setPicksQuery(applyPickHistoryQuery(DEFAULT_PICK_FILTERS));
  }

  function handlePickSeasonChange(season: string): void {
    setPicksQuery(
      applyPickHistoryQuery({
        ...DEFAULT_PICK_FILTERS,
        season,
      }),
    );
  }

  const pickFilterSummary = picksPayload
    ? summarizePickFilters(picksPayload.page.filters)
    : [];

  const heroTitle =
    route === "overview"
      ? isBetaRoute
        ? "Best-path posture without leaving the dashboard contract"
        : "Dashboard posture on the primary route"
      : route === "models"
        ? isBetaRoute
          ? "Model review without leaving the React beta"
          : "Model review on the primary route"
      : route === "performance"
        ? isBetaRoute
          ? "Performance without leaving the React beta"
          : "Performance on the primary route"
      : route === "picks"
        ? isBetaRoute
          ? "Bet history without leaving the React beta"
          : "Bet history on the primary route"
      : isBetaRoute
        ? "Recommendations without leaving the React beta"
        : "Recommendations on the primary route";
  const heroCopy =
    route === "overview"
      ? isBetaRoute
        ? "This surface reads the same middleware payload as the classic overview. It is the first migration slice, not a separate product."
        : "This route now serves the React overview against the existing dashboard contract while the server-rendered overview remains available as a documented fallback."
      : route === "models"
        ? isBetaRoute
          ? "This review surface reuses the existing models-page contract, including artifact inventory, availability diagnostics, and glossary copy."
          : "This route now serves the React models client by default while the classic server-rendered review page remains available as a documented fallback."
      : route === "performance"
        ? isBetaRoute
          ? "This performance view reuses the existing performance-page contract, including window switching, season comparisons, and settled-row detail."
          : "This route now serves the React performance client by default while the classic server-rendered performance page remains available as a documented fallback."
      : route === "picks"
        ? isBetaRoute
          ? "This history view reuses the existing picks-page contract, including normalized filters, season choices, and matched historical rows."
          : "This route now serves the React picks client by default while the classic server-rendered history page remains available as a documented fallback."
      : isBetaRoute
        ? "This recommendations view reuses the existing upcoming-page contract, including live picks, the timing watchlist, and the recent board state."
        : "This route now serves the React recommendations client by default while the classic server-rendered page remains available as a documented fallback.";
  const heroKicker =
    route === "overview"
      ? isBetaRoute
        ? "React beta overview"
        : "React dashboard"
      : route === "models"
        ? isBetaRoute
          ? "React beta model review"
          : "React model review"
      : route === "performance"
        ? isBetaRoute
          ? "React beta performance"
          : "React performance"
      : route === "picks"
        ? isBetaRoute
          ? "React beta picks"
          : "React bet history"
      : isBetaRoute
        ? "React beta recommendations"
        : "React recommendations";

  return (
    <div className="react-overview-shell">
      <section className="react-beta-hero">
        <div>
          <p className="react-kicker">{heroKicker}</p>
          <h2>{heroTitle}</h2>
          <p className="react-hero-copy">{heroCopy}</p>
        </div>
        <div className="react-beta-sidecar">
          <p className="react-sidecar-label">React routes</p>
          <nav className="react-beta-nav" aria-label="React routes">
            <a
              className={route === "overview" ? "is-active" : undefined}
              href={overviewHref}
            >
              Overview
            </a>
            <a
              className={route === "models" ? "is-active" : undefined}
              href={modelsHref}
            >
              Model Review
            </a>
            <a
              className={route === "performance" ? "is-active" : undefined}
              href={performanceHref}
            >
              Performance
            </a>
            <a
              className={route === "picks" ? "is-active" : undefined}
              href={picksHref}
            >
              Bet History
            </a>
            <a
              className={route === "upcoming" ? "is-active" : undefined}
              href={upcomingHref}
            >
              Recommendations
            </a>
          </nav>
          <a className="react-classic-link" href={classicHref}>
            {classicLabel}
          </a>
        </div>
      </section>

      {route === "overview" ? (
        <section className="react-window-bar">
          <div>
            <p className="react-sidecar-label">Recent window</p>
            <div className="react-window-pills">
              {WINDOW_KEYS.map((candidate) => (
                <button
                  key={candidate}
                  className={candidate === windowKey ? "is-active" : undefined}
                  onClick={() => handleWindowChange(candidate)}
                  type="button"
                >
                  {candidate === "season" ? "Season" : `${candidate}d`}
                </button>
              ))}
            </div>
          </div>
          {dashboardPayload ? (
            <p className="react-summary-note">
              {dashboardPayload.page.recent_summary.explanation}
            </p>
          ) : null}
        </section>
      ) : null}

      {route === "performance" ? (
        <section className="react-window-bar">
          <div>
            <p className="react-sidecar-label">Window selection</p>
            <div className="react-window-pills">
              {(performancePayload?.page.windows ?? []).map((candidate) => (
                <button
                  key={candidate.key}
                  className={candidate.key === windowKey ? "is-active" : undefined}
                  onClick={() => handleWindowChange(candidate.key)}
                  type="button"
                >
                  {candidate.label} · Stake {candidate.min_stake_label} to{" "}
                  {candidate.max_stake_label}
                </button>
              ))}
            </div>
          </div>
          {performancePayload ? (
            <p className="react-summary-note">
              {performancePayload.page.summary.explanation}
            </p>
          ) : null}
        </section>
      ) : null}

      {route === "picks" && picksPayload ? (
        <section className="react-window-bar">
          <div>
            <p className="react-sidecar-label">Season jump</p>
            <div className="react-window-pills">
              <button
                className={
                  picksPayload.page.filters.season === "all" ? "is-active" : undefined
                }
                onClick={() => handlePickSeasonChange("all")}
                type="button"
              >
                All seasons
              </button>
              {picksPayload.page.seasons.map((season) => (
                <button
                  key={season}
                  className={
                    season === picksPayload.page.filters.season
                      ? "is-active"
                      : undefined
                  }
                  onClick={() => handlePickSeasonChange(season)}
                  type="button"
                >
                  {season}
                </button>
              ))}
            </div>
          </div>
          <p className="react-summary-note">
            Start with season, then narrow by date, team, result, market, or
            sportsbook without scraping report text.
          </p>
        </section>
      ) : null}

      {loading &&
      ((route === "overview" && dashboardPayload === null) ||
        (route === "models" && modelsPayload === null) ||
        (route === "performance" && performancePayload === null) ||
        (route === "picks" && picksPayload === null) ||
        (route === "upcoming" && upcomingPayload === null)) ? (
        <section className="react-loading-state">
          <p>
            {route === "overview"
              ? "Loading the dashboard snapshot and current board."
              : route === "models"
                ? "Loading the promoted-path review, artifacts, and diagnostics."
              : route === "performance"
                ? "Loading the performance history and settled-window summary."
              : route === "picks"
                ? "Loading the historical picks and current filters."
              : "Loading the current recommendations and recent board state."}
          </p>
        </section>
      ) : null}

      {error ? (
        <section className="react-error-state">
          <p className="react-sidecar-label">React beta error</p>
          <p>{error}</p>
        </section>
      ) : null}

      {route === "overview" && dashboardPayload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Strategy note</p>
              <p>{dashboardPayload.page.strategy_note}</p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Board note</p>
              <p>{dashboardPayload.page.board_note}</p>
            </article>
            {dashboardPayload.page.availability_usage ? (
              <article className="react-status-card">
                <p className="react-sidecar-label">Availability usage</p>
                <strong>{dashboardPayload.page.availability_usage.label}</strong>
                <p>{dashboardPayload.page.availability_usage.note}</p>
              </article>
            ) : null}
            <article className="react-status-card">
              <p className="react-sidecar-label">Recent summary</p>
              <strong>
                {dashboardPayload.page.recent_summary.label}:{" "}
                {dashboardPayload.page.recent_summary.profit_label}
              </strong>
              <p>
                ROI {dashboardPayload.page.recent_summary.roi_label} across{" "}
                {dashboardPayload.page.recent_summary.bets} bets with drawdown{" "}
                {dashboardPayload.page.recent_summary.drawdown_label}.
              </p>
            </article>
          </section>

          <section className="react-card-grid">
            {dashboardPayload.page.overview_cards.map((card) => (
              <article className="react-metric-card" key={card.label}>
                <p className="react-sidecar-label">{card.label}</p>
                <h3>{card.value}</h3>
                <p>{card.detail}</p>
                <p className="react-muted-copy">{card.why_it_matters}</p>
              </article>
            ))}
          </section>

          {dashboardPayload.page.season_bars.length > 0 ? (
            <section className="react-season-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Season shape</p>
                  <h3>Per-season profit posture</h3>
                </div>
              </div>
              <div className="react-season-bars">
                {dashboardPayload.page.season_bars.map((bar) => (
                  <article className="react-season-bar" key={bar.season}>
                    <div className="react-season-bar-copy">
                      <strong>{bar.season}</strong>
                      <span>{bar.profit_label}</span>
                      <span>{bar.roi_label}</span>
                    </div>
                    <div className="react-season-bar-track">
                      <div
                        className={`react-season-bar-fill tone-${bar.tone}`}
                        style={{ height: `${Math.max(bar.height_pct, 8)}%` }}
                      />
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <section className="react-board-grid">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Recent bets</p>
                  <h3>Last settled window</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderPickRows(dashboardPayload.page.recent_rows, {
                  emptyMessage: "No recent settled bets match the selected window.",
                  variant: "qualified",
                })}
              </div>
            </article>

            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Current board</p>
                  <h3>Upcoming recommendations</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderPickRows(dashboardPayload.page.upcoming_rows, {
                  emptyMessage: "No current board rows are available.",
                  variant: "overview",
                })}
              </div>
            </article>
          </section>
        </>
      ) : null}

      {route === "models" && modelsPayload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Promoted path</p>
              <strong>Spread-first deployment</strong>
              <p>{modelsPayload.page.strategy_note}</p>
            </article>
            {modelsPayload.page.availability_usage ? (
              <article className="react-status-card">
                <p className="react-sidecar-label">Availability state</p>
                <strong>{modelsPayload.page.availability_usage.label}</strong>
                <p>{modelsPayload.page.availability_usage.note}</p>
              </article>
            ) : null}
            <article className="react-status-card">
              <p className="react-sidecar-label">Artifact inventory</p>
              <strong>{modelsPayload.page.artifacts.length} stored files</strong>
              <p>
                The React route reads the same artifact summary payload as the
                classic review page.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Season stability</p>
              <strong>{modelsPayload.page.season_cards.length} season cards</strong>
              <p>
                Use the per-season bars and cards below to spot weak years
                before trusting the promoted path.
              </p>
            </article>
          </section>

          <section className="react-card-grid">
            {modelsPayload.page.overview_cards.map((card) => (
              <article className="react-metric-card" key={card.label}>
                <p className="react-sidecar-label">{card.label}</p>
                <h3>{card.value}</h3>
                <p>{card.detail}</p>
                <p className="react-muted-copy">{card.why_it_matters}</p>
              </article>
            ))}
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Artifact inventory</p>
                <h3>Stored model files</h3>
              </div>
            </div>
            <div className="react-card-grid">
              {modelsPayload.page.artifacts.length > 0 ? (
                modelsPayload.page.artifacts.map((artifact) => (
                  <article
                    className="react-metric-card"
                    key={`${artifact.market}-${artifact.artifact_name}`}
                  >
                    <p className="react-sidecar-label">
                      {artifact.market} · {artifact.role_label}
                    </p>
                    <h3>{artifact.market}_{artifact.artifact_name}</h3>
                    <p>Family {artifact.model_family}</p>
                    <p className="react-muted-copy">
                      Seasons {artifact.trained_range} · Trained{" "}
                      {artifact.trained_at_label}
                    </p>
                    <p className="react-muted-copy">
                      Features {artifact.feature_count} · Blend{" "}
                      {artifact.market_blend_weight_label} · Market cap{" "}
                      {artifact.max_market_delta_label}
                    </p>
                  </article>
                ))
              ) : (
                renderEmptyState(
                  "No trained artifacts are currently stored in the local artifact directory.",
                )
              )}
            </div>
          </section>

          {modelsPayload.page.season_bars.length > 0 ? (
            <section className="react-season-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Season shape</p>
                  <h3>Per-season stability</h3>
                </div>
              </div>
              <div className="react-season-bars">
                {modelsPayload.page.season_bars.map((bar) => (
                  <article className="react-season-bar" key={bar.season}>
                    <div className="react-season-bar-copy">
                      <strong>{bar.season}</strong>
                      <span>{bar.profit_label}</span>
                      <span>{bar.roi_label}</span>
                    </div>
                    <div className="react-season-bar-track">
                      <div
                        className={`react-season-bar-fill tone-${bar.tone}`}
                        style={{ height: `${Math.max(bar.height_pct, 8)}%` }}
                      />
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {modelsPayload.page.season_cards.length > 0 ? (
            <section className="react-card-grid">
              {modelsPayload.page.season_cards.map((card) => (
                <article className="react-metric-card" key={card.season}>
                  <p className="react-sidecar-label">{card.season}</p>
                  <h3>{card.profit_label}</h3>
                  <p>
                    ROI {card.roi_label} across {card.bets} bets.
                  </p>
                  <p className="react-muted-copy">
                    Drawdown {card.drawdown_label} · Close EV {card.close_ev_label}
                  </p>
                  <a className="react-classic-link" href={`${picksHref}?season=${card.season}`}>
                    Open {card.season} history
                  </a>
                </article>
              ))}
            </section>
          ) : null}

          {modelsPayload.page.availability_diagnostics ? (
            <section className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Availability diagnostics</p>
                  <h3>Official availability coverage</h3>
                </div>
                <span className="tone-flat">
                  {modelsPayload.page.availability_diagnostics.usage.label}
                </span>
              </div>
              <p className="react-summary-note">
                {modelsPayload.page.availability_diagnostics.usage.note}
              </p>
              <section className="react-status-grid">
                {modelsPayload.page.availability_diagnostics.stats.map((stat) => (
                  <article className="react-status-card" key={stat.label}>
                    <p className="react-sidecar-label">{stat.label}</p>
                    <strong>{stat.value}</strong>
                  </article>
                ))}
              </section>
              <div className="react-callout-stack">
                {modelsPayload.page.availability_diagnostics.empty_message ? (
                  <p>{modelsPayload.page.availability_diagnostics.empty_message}</p>
                ) : null}
                {modelsPayload.page.availability_diagnostics.season_labels.length > 0 ? (
                  <p>
                    Seasons:{" "}
                    {modelsPayload.page.availability_diagnostics.season_labels.join(
                      ", ",
                    )}
                  </p>
                ) : null}
                {modelsPayload.page.availability_diagnostics.scope_labels.length > 0 ? (
                  <p>
                    Scope:{" "}
                    {modelsPayload.page.availability_diagnostics.scope_labels.join(
                      ", ",
                    )}
                  </p>
                ) : null}
                {modelsPayload.page.availability_diagnostics.source_labels.length > 0 ? (
                  <p>
                    Sources:{" "}
                    {modelsPayload.page.availability_diagnostics.source_labels.join(
                      ", ",
                    )}
                  </p>
                ) : null}
                {modelsPayload.page.availability_diagnostics.status_badges.length > 0 ? (
                  <p>
                    Status mix:{" "}
                    {modelsPayload.page.availability_diagnostics.status_badges
                      .map((badge) => `${badge.label} ${badge.value}`)
                      .join(" · ")}
                  </p>
                ) : null}
              </div>
            </section>
          ) : null}

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Glossary</p>
                <h3>Metric meanings</h3>
              </div>
            </div>
            <div className="react-card-grid">
              {modelsPayload.page.metric_definitions.map((metric) => (
                <article className="react-metric-card" key={metric.slug}>
                  <p className="react-sidecar-label">{metric.label}</p>
                  <h3>{metric.label}</h3>
                  <p>{metric.summary}</p>
                  <p className="react-muted-copy">{metric.repo_meaning}</p>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}

      {route === "performance" && performancePayload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Window summary</p>
              <strong>
                {performancePayload.page.summary.label}:{" "}
                {performancePayload.page.summary.profit_label}
              </strong>
              <p>
                ROI {performancePayload.page.summary.roi_label} across{" "}
                {performancePayload.page.summary.bets} bets with drawdown{" "}
                {performancePayload.page.summary.drawdown_label}.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Stake range</p>
              <strong>
                {performancePayload.page.summary.min_stake_label} to{" "}
                {performancePayload.page.summary.max_stake_label}
              </strong>
              <p>Risked {performancePayload.page.summary.total_staked_label}.</p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Close quality</p>
              <strong>{performancePayload.page.summary.close_ev_label}</strong>
              <p>
                Price CLV {performancePayload.page.summary.price_clv_label} ·
                Line CLV {performancePayload.page.summary.line_clv_label}
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Risk posture</p>
              <strong>
                {performancePayload.page.summary.bankroll_exposure_label}
              </strong>
              <p>
                Anchor {performancePayload.page.summary.anchor_label} ·{" "}
                {performancePayload.page.summary.wins}-
                {performancePayload.page.summary.losses}-
                {performancePayload.page.summary.pushes}
              </p>
            </article>
          </section>

          <section className="react-board-grid">
            {renderHistoryChart(performancePayload.page.full_history_chart, {
              eyebrow: "Full report history",
              emptyMessage:
                "The full-window history chart will appear after the report snapshot has settled picks.",
            })}
            {renderHistoryChart(performancePayload.page.season_comparison_chart, {
              eyebrow: "Season overlays",
              emptyMessage:
                "Season overlays need at least one settled season in the report snapshot.",
              multiSeries: true,
            })}
          </section>

          {performancePayload.page.season_cards.length > 0 ? (
            <section className="react-card-grid">
              {performancePayload.page.season_cards.map((card) => (
                <article className="react-metric-card" key={card.season}>
                  <p className="react-sidecar-label">{card.season}</p>
                  <h3>{card.profit_label}</h3>
                  <p>
                    ROI {card.roi_label} across {card.bets} bets.
                  </p>
                  <p className="react-muted-copy">
                    Drawdown {card.drawdown_label} · Close EV {card.close_ev_label}
                  </p>
                </article>
              ))}
            </section>
          ) : null}

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Settled rows</p>
                <h3>Window detail</h3>
              </div>
            </div>
            <div className="react-row-list">
              {renderPickRows(performancePayload.page.rows, {
                emptyMessage:
                  "No settled rows match the selected performance window.",
                variant: "settled",
              })}
            </div>
          </section>
        </>
      ) : null}

      {route === "picks" && picksPayload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Matched rows</p>
              <strong>{picksPayload.page.total_rows} historical picks</strong>
              <p>
                {picksPayload.page.truncated
                  ? "Showing the most recent 250 rows in the current filter scope."
                  : "Showing every row that matched the current filter scope."}
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Current scope</p>
              <strong>
                {pickFilterSummary.length > 0
                  ? pickFilterSummary.join(" · ")
                  : "All settled history"}
              </strong>
              <p>
                Use the form below to narrow by season, date, team, result,
                market, or sportsbook.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Available filters</p>
              <strong>
                {picksPayload.page.seasons.length} seasons ·{" "}
                {picksPayload.page.sportsbooks.length} books
              </strong>
              <p>
                The React route reads the same normalized filter surface as the
                classic page.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Fallback path</p>
              <strong>{classicHref}</strong>
              <p>
                The server-rendered picks page stays available while the React
                history route becomes primary.
              </p>
            </article>
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Filter review</p>
                <h3>Historical picks filters</h3>
              </div>
            </div>
            <form
              key={JSON.stringify(picksPayload.page.filters)}
              className="react-filter-grid"
              onSubmit={handlePickFiltersSubmit}
            >
              <label>
                <span>Season</span>
                <select
                  defaultValue={picksPayload.page.filters.season}
                  name="season"
                >
                  <option value="all">all</option>
                  {picksPayload.page.seasons.map((season) => (
                    <option key={season} value={season}>
                      {season}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Start</span>
                <input
                  defaultValue={picksPayload.page.filters.start}
                  name="start"
                  type="date"
                />
              </label>
              <label>
                <span>End</span>
                <input
                  defaultValue={picksPayload.page.filters.end}
                  name="end"
                  type="date"
                />
              </label>
              <label>
                <span>Team</span>
                <input
                  defaultValue={picksPayload.page.filters.team}
                  name="team"
                  placeholder="Duke, Auburn, Saint Mary's"
                  type="search"
                />
              </label>
              <label>
                <span>Result</span>
                <select
                  defaultValue={picksPayload.page.filters.result}
                  name="result"
                >
                  {PICK_RESULT_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Market</span>
                <select
                  defaultValue={picksPayload.page.filters.market}
                  name="market"
                >
                  {PICK_MARKET_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Sportsbook</span>
                <select
                  defaultValue={picksPayload.page.filters.sportsbook}
                  name="sportsbook"
                >
                  <option value="all">all</option>
                  {picksPayload.page.sportsbooks.map((sportsbook) => (
                    <option key={sportsbook} value={sportsbook}>
                      {sportsbook}
                    </option>
                  ))}
                </select>
              </label>
              <div className="react-filter-actions">
                <button type="submit">Apply filters</button>
                <button onClick={handlePickReset} type="button">
                  Reset
                </button>
              </div>
            </form>
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Settled history</p>
                <h3>Matched picks</h3>
              </div>
              <span className={picksPayload.page.truncated ? "tone-warn" : "tone-flat"}>
                {picksPayload.page.truncated
                  ? "Latest 250 rows shown"
                  : "Full matched set shown"}
              </span>
            </div>
            <div className="react-row-list">
              {renderPickRows(picksPayload.page.rows, {
                emptyMessage: "No picks matched the current filters.",
                variant: "history",
              })}
            </div>
          </section>
        </>
      ) : null}

      {route === "upcoming" && upcomingPayload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Policy note</p>
              <p>{upcomingPayload.page.policy_note}</p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Refresh window</p>
              <strong>Generated {upcomingPayload.page.generated_at_label}</strong>
              <p>Expires {upcomingPayload.page.expires_at_label}</p>
            </article>
            {upcomingPayload.page.availability_usage ? (
              <article className="react-status-card">
                <p className="react-sidecar-label">Availability usage</p>
                <strong>{upcomingPayload.page.availability_usage.label}</strong>
                <p>{upcomingPayload.page.availability_usage.note}</p>
              </article>
            ) : null}
            {upcomingPayload.page.availability_summary ? (
              <article className="react-status-card">
                <p className="react-sidecar-label">Availability summary</p>
                <strong>{upcomingPayload.page.availability_summary.label}</strong>
                <div className="react-callout-stack">
                  <p>{upcomingPayload.page.availability_summary.detail}</p>
                  {upcomingPayload.page.availability_summary.freshness_note ? (
                    <p>{upcomingPayload.page.availability_summary.freshness_note}</p>
                  ) : null}
                  {upcomingPayload.page.availability_summary.matching_note ? (
                    <p>{upcomingPayload.page.availability_summary.matching_note}</p>
                  ) : null}
                  {upcomingPayload.page.availability_summary.status_note ? (
                    <p>{upcomingPayload.page.availability_summary.status_note}</p>
                  ) : null}
                  {upcomingPayload.page.availability_summary.source_note ? (
                    <p>{upcomingPayload.page.availability_summary.source_note}</p>
                  ) : null}
                </div>
              </article>
            ) : null}
          </section>

          <section className="react-board-grid">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Qualified</p>
                  <h3>Live picks</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderPickRows(upcomingPayload.page.recommendation_rows, {
                  emptyMessage: "No current picks are qualified.",
                  variant: "qualified",
                })}
              </div>
            </article>

            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Timing layer</p>
                  <h3>Watchlist</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderPickRows(upcomingPayload.page.watch_rows, {
                  emptyMessage: "No timing-layer watch candidates right now.",
                  variant: "watch",
                })}
              </div>
            </article>
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Board state</p>
                <h3>Recent, in-progress, and upcoming board</h3>
              </div>
            </div>
            <p className="react-summary-note">
              This table keeps the pregame board decision visible after tip-off,
              adds the live or final score when the database has it, and surfaces
              row-level availability context only when stored official report
              coverage already exists for that row.
            </p>
            <div className="react-row-list">
              {renderLiveBoardRows(upcomingPayload.page.live_board_rows)}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
