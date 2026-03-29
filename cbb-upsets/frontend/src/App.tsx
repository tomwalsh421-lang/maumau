import { startTransition, useDeferredValue, useEffect, useState } from "react";
import type { FormEvent, JSX } from "react";

type AppRoute =
  | "overview"
  | "models"
  | "performance"
  | "upcoming"
  | "picks"
  | "teams";
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

type TeamSearchResult = {
  team_key: string;
  team_name: string;
  match_hint: string | null;
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
  cached_rows: PickTableRow[];
  cached_generated_at_label: string | null;
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
  cached_rows: PickTableRow[];
  cached_generated_at_label: string | null;
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
  board_rows: PickTableRow[];
  availability_usage: AvailabilityUsageView | null;
  availability_summary: UpcomingAvailabilitySummary | null;
  live_board_rows: LiveBoardRow[];
};

type UpcomingPayload = {
  page: UpcomingPage;
};

type TeamsPage = {
  query: string;
  results: TeamSearchResult[];
  featured: TeamSearchResult[];
};

type TeamsPayload = {
  page: TeamsPage;
};

type TeamResultRow = {
  commence_label: string;
  opponent_name: string;
  venue_label: string;
  score_label: string;
  result_label: string;
  result_tone: string;
};

type ScheduleRow = {
  commence_label: string;
  matchup_label: string;
  status_label: string;
  status_tone: string;
  score_label: string;
  price_label: string;
};

type TeamDetailPage = {
  team: TeamSearchResult;
  recent_results: TeamResultRow[];
  scheduled_games: ScheduleRow[];
  history_rows: PickTableRow[];
  upcoming_rows: PickTableRow[];
  pick_summary: string;
};

type TeamDetailPayload = {
  page: TeamDetailPage;
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
  if (rawPath.includes("/teams")) {
    return "teams";
  }
  if (rawPath.includes("/models")) {
    return "models";
  }
  if (rawPath.includes("/performance")) {
    return "performance";
  }
  return rawPath.includes("/upcoming") ? "upcoming" : "overview";
}

function readTeamDetailKey(rootElement: HTMLDivElement): string | null {
  const rawPath = readAppPath(rootElement);
  const match = rawPath.match(/^\/teams\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : null;
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

function buildTeamsApiUrl(rootElement: HTMLDivElement, queryString: string): string {
  const apiUrl = rootElement.dataset.teamsApi ?? "/api/teams";
  const url = new URL(apiUrl, window.location.origin);
  const search = new URLSearchParams(queryString);
  search.forEach((value, key) => {
    url.searchParams.set(key, value);
  });
  return url.toString();
}

function buildTeamDetailApiUrl(
  rootElement: HTMLDivElement,
  teamKey: string,
): string {
  const apiUrl = rootElement.dataset.teamsApi ?? "/api/teams";
  const trimmedBase = apiUrl.endsWith("/") ? apiUrl.slice(0, -1) : apiUrl;
  return new URL(
    `${trimmedBase}/${encodeURIComponent(teamKey)}`,
    window.location.origin,
  ).toString();
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

function pickRowIdentity(row: PickTableRow): string {
  return `${row.game_id}:${row.market_label}:${row.side_label}`;
}

function filterBoardQueueRows(
  boardRows: PickTableRow[],
  selectedRows: PickTableRow[],
): PickTableRow[] {
  const selectedKeys = new Set(selectedRows.map(pickRowIdentity));
  return boardRows.filter((row) => !selectedKeys.has(pickRowIdentity(row)));
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

function renderTeamLinks(
  teams: TeamSearchResult[],
  options: {
    basePath: string;
    emptyMessage: string;
  },
): JSX.Element {
  const { basePath, emptyMessage } = options;
  if (teams.length === 0) {
    return renderEmptyState(emptyMessage);
  }
  return (
    <>
      {teams.map((team) => (
        <a
          className="react-row-card"
          href={`${basePath}/${team.team_key}`}
          key={team.team_key}
        >
          <div className="react-row-topline">
            <strong>{team.team_name}</strong>
            <span className="tone-flat">{team.team_key}</span>
          </div>
          {team.match_hint ? (
            <p className="react-row-meta">{team.match_hint}</p>
          ) : (
            <p className="react-row-meta">
              Open the current board, schedule, and team pick history.
            </p>
          )}
        </a>
      ))}
    </>
  );
}

function renderTeamResultRows(
  rows: TeamResultRow[],
  options: {
    emptyMessage: string;
  },
): JSX.Element {
  if (rows.length === 0) {
    return renderEmptyState(options.emptyMessage);
  }
  return (
    <>
      {rows.map((row) => (
        <article
          className="react-row-card"
          key={`${row.commence_label}-${row.opponent_name}-${row.score_label}`}
        >
          <div className="react-row-topline">
            <strong>
              {row.venue_label} {row.opponent_name}
            </strong>
            <span className={`tone-${row.result_tone}`}>{row.result_label}</span>
          </div>
          <p className="react-row-meta">{row.commence_label}</p>
          <p className="react-row-meta">
            Score {row.score_label === "" ? "n/a" : row.score_label}
          </p>
        </article>
      ))}
    </>
  );
}

function renderScheduleRows(
  rows: ScheduleRow[],
  options: {
    emptyMessage: string;
  },
): JSX.Element {
  if (rows.length === 0) {
    return renderEmptyState(options.emptyMessage);
  }
  return (
    <>
      {rows.map((row) => (
        <article
          className="react-row-card"
          key={`${row.commence_label}-${row.matchup_label}-${row.status_label}`}
        >
          <div className="react-row-topline">
            <strong>{row.matchup_label}</strong>
            <span className={`tone-${row.status_tone}`}>{row.status_label}</span>
          </div>
          <p className="react-row-meta">{row.commence_label}</p>
          <p className="react-row-meta">
            Score {row.score_label === "" ? "n/a" : row.score_label} · Pregame{" "}
            {row.price_label}
          </p>
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

function applyTeamsQuery(query: string): string {
  const url = new URL(window.location.href);
  url.search = "";
  const trimmed = query.trim();
  if (trimmed !== "") {
    url.searchParams.set("q", trimmed);
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
  const route = readAppRoute(rootElement);
  const teamDetailKey = readTeamDetailKey(rootElement);
  const [windowKey, setWindowKey] = useState<WindowKey>(() =>
    readInitialWindow(rootElement),
  );
  const [picksQuery, setPicksQuery] = useState(() => window.location.search);
  const [teamsQuery, setTeamsQuery] = useState(() => window.location.search);
  const overviewHref = `/?window=${windowKey}`;
  const modelsHref = "/models";
  const teamsHref = "/teams";
  const performanceHref = `/performance?window=${windowKey}`;
  const upcomingHref = "/upcoming";
  const picksHref = "/picks";
  const deferredWindowKey = useDeferredValue(windowKey);
  const deferredPicksQuery = useDeferredValue(picksQuery);
  const deferredTeamsQuery = useDeferredValue(teamsQuery);
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
  const [teamsPayload, setTeamsPayload] = useState<TeamsPayload | null>(null);
  const [teamDetailPayload, setTeamDetailPayload] = useState<TeamDetailPayload | null>(
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
            : route === "teams"
              ? teamDetailKey !== null
                ? buildTeamDetailApiUrl(rootElement, teamDetailKey)
                : buildTeamsApiUrl(rootElement, deferredTeamsQuery)
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
            setTeamsPayload(null);
            setTeamDetailPayload(null);
            setModelsPayload(null);
            setPerformancePayload(null);
            setPicksPayload(null);
            setUpcomingPayload(null);
          } else if (route === "teams") {
            if (teamDetailKey !== null) {
              setTeamDetailPayload(data as TeamDetailPayload);
              setTeamsPayload(null);
            } else {
              setTeamsPayload(data as TeamsPayload);
              setTeamDetailPayload(null);
            }
            setDashboardPayload(null);
            setModelsPayload(null);
            setPerformancePayload(null);
            setPicksPayload(null);
            setUpcomingPayload(null);
          } else if (route === "models") {
            setModelsPayload(data as ModelsPayload);
            setDashboardPayload(null);
            setTeamsPayload(null);
            setTeamDetailPayload(null);
            setPerformancePayload(null);
            setPicksPayload(null);
            setUpcomingPayload(null);
          } else if (route === "performance") {
            setPerformancePayload(data as PerformancePayload);
            setDashboardPayload(null);
            setTeamsPayload(null);
            setTeamDetailPayload(null);
            setModelsPayload(null);
            setPicksPayload(null);
            setUpcomingPayload(null);
          } else if (route === "picks") {
            setPicksPayload(data as PicksPayload);
            setDashboardPayload(null);
            setTeamsPayload(null);
            setTeamDetailPayload(null);
            setModelsPayload(null);
            setPerformancePayload(null);
            setUpcomingPayload(null);
          } else {
            setUpcomingPayload(data as UpcomingPayload);
            setDashboardPayload(null);
            setTeamsPayload(null);
            setTeamDetailPayload(null);
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
  }, [
    deferredPicksQuery,
    deferredTeamsQuery,
    deferredWindowKey,
    rootElement,
    route,
    teamDetailKey,
  ]);

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
  const currentCardCount = dashboardPayload?.page.cached_rows.length ?? 0;
  const boardRowCount = dashboardPayload?.page.upcoming_rows.length ?? 0;
  const recentWindowCount = dashboardPayload?.page.recent_rows.length ?? 0;
  const upcomingQualifiedCount = upcomingPayload?.page.recommendation_rows.length ?? 0;
  const upcomingWatchCount = upcomingPayload?.page.watch_rows.length ?? 0;
  const upcomingBoardQueueRows = upcomingPayload
    ? filterBoardQueueRows(upcomingPayload.page.board_rows, [
        ...upcomingPayload.page.recommendation_rows,
        ...upcomingPayload.page.watch_rows,
      ])
    : [];
  const upcomingBoardQueueCount = upcomingBoardQueueRows.length;
  const currentCardHeadline =
    currentCardCount === 0
      ? "No bets are qualified on the live card"
      : currentCardCount === 1
        ? "1 bet is ready for review right now"
        : `${currentCardCount} bets are ready for review right now`;

  function handleTeamsSearchSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const queryValue = formData.get("q");
    setTeamsQuery(
      applyTeamsQuery(typeof queryValue === "string" ? queryValue : ""),
    );
  }

  function handleTeamsReset(): void {
    setTeamsQuery(applyTeamsQuery(""));
  }

  const heroTitle =
    route === "overview"
      ? "Start with tonight's board"
      : route === "teams"
        ? teamDetailKey !== null
          ? "One team, one board context"
          : "Find a team and check the card"
      : route === "models"
        ? "Know what is shaping the card"
      : route === "performance"
        ? "Check form before following the card"
      : route === "picks"
        ? "Compare today's card with settled history"
      : "Work the current slate";
  const heroCopy =
    route === "overview"
      ? "Use the latest cached recommendations, recent performance, and board context to decide whether the current slate is worth action."
      : route === "teams"
        ? teamDetailKey !== null
          ? "Stay on one team to see its near-term schedule, current board involvement, recent results, and matched history without leaving the main workspace."
          : "Search by school or alias, jump into one team, and come back to the live board without switching surfaces."
      : route === "models"
        ? "Review the promoted path, stored artifacts, and season stability before trusting the current recommendations."
      : route === "performance"
        ? "Scan recent windows, season overlays, and settled detail to see whether the edge is still showing up where the model says it should."
      : route === "picks"
        ? "Use the settled log to compare the current job-backed card with what has actually cleared, filtered down to the dates, teams, and books you care about."
      : "Start with the qualified bets, then the close-watch queue, then the rest of the active slate before dropping into live or final context.";
  const heroKicker =
    route === "overview"
      ? "Daily board"
      : route === "teams"
        ? teamDetailKey !== null
          ? "Team detail"
          : "Team explorer"
      : route === "models"
        ? "Model review"
      : route === "performance"
        ? "Performance"
      : route === "picks"
        ? "Bet history"
      : "Slate workspace";

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
              className={route === "teams" ? "is-active" : undefined}
              href={teamsHref}
            >
              Team Explorer
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
              Slate
            </a>
          </nav>
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
        (route === "teams" &&
          (teamDetailKey !== null
            ? teamDetailPayload === null
            : teamsPayload === null)) ||
        (route === "models" && modelsPayload === null) ||
        (route === "performance" && performancePayload === null) ||
        (route === "picks" && picksPayload === null) ||
        (route === "upcoming" && upcomingPayload === null)) ? (
        <section className="react-loading-state">
          <p>
            {route === "overview"
              ? "Loading the dashboard snapshot and current board."
              : route === "teams"
                ? teamDetailKey !== null
                  ? "Loading the team slate, recent results, and pick history."
                  : "Loading featured teams and the current search matches."
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
          <p className="react-sidecar-label">Dashboard error</p>
          <p>{error}</p>
        </section>
      ) : null}

      {route === "overview" && dashboardPayload ? (
        <>
          <section className="react-day-board-strip">
            <article className="react-day-board-summary">
              <p className="react-sidecar-label">Day board</p>
              <h3>{currentCardHeadline}</h3>
              <p className="react-hero-copy">
                {currentCardCount > 0
                  ? "Start with the current recommendations, then scan the rest of the board and the recent settled window before adding anything."
                  : "No bet has cleared the current policy yet. Use the board context and recent settled window below to decide whether this is a wait slate."}
              </p>
              <p className="react-summary-note">{dashboardPayload.page.board_note}</p>
              <div className="react-day-board-actions">
                <a className="react-day-link is-primary" href={upcomingHref}>
                  Open full board
                </a>
                <a className="react-day-link" href={performanceHref}>
                  Check recent form
                </a>
                <a className="react-day-link" href={`${picksHref}?season=2026`}>
                  Review settled history
                </a>
              </div>
            </article>

            <div className="react-day-board-stats">
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Current card</p>
                <strong>
                  {currentCardCount} {currentCardCount == 1 ? "bet" : "bets"}
                </strong>
                <p>
                  {dashboardPayload.page.cached_generated_at_label ??
                    "No cached refresh has landed yet."}
                </p>
              </article>
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Board depth</p>
                <strong>
                  {boardRowCount} {boardRowCount == 1 ? "board row" : "board rows"}
                </strong>
                <p>
                  Near-term games stay visible here even when they do not
                  qualify as bets.
                </p>
              </article>
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Recent window</p>
                <strong>{dashboardPayload.page.recent_summary.profit_label}</strong>
                <p>
                  ROI {dashboardPayload.page.recent_summary.roi_label} across{" "}
                  {dashboardPayload.page.recent_summary.bets} settled bets.
                </p>
              </article>
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Availability note</p>
                <strong>
                  {dashboardPayload.page.availability_usage?.label ??
                    "No availability note"}
                </strong>
                <p>
                  {dashboardPayload.page.availability_usage?.note ??
                    dashboardPayload.page.strategy_note}
                </p>
              </article>
            </div>
          </section>

          <section className="react-board-grid react-board-grid-priority">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Current card</p>
                  <h3>Job-backed recommendations</h3>
                </div>
                {dashboardPayload.page.cached_generated_at_label ? (
                  <span className="tone-flat">
                    {dashboardPayload.page.cached_generated_at_label}
                  </span>
                ) : null}
              </div>
              <div className="react-row-list">
                {renderPickRows(dashboardPayload.page.cached_rows, {
                  emptyMessage: "No cached picks are available yet.",
                  variant: "qualified",
                })}
              </div>
            </article>

            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Near-term slate</p>
                  <h3>What else is on the board</h3>
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

          <section className="react-board-grid">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Last settled window</p>
                  <h3>Recent form behind the card</h3>
                </div>
                <span className="tone-flat">
                  {recentWindowCount}{" "}
                  {recentWindowCount === 1 ? "settled row" : "settled rows"}
                </span>
              </div>
              <p className="react-summary-note">
                {dashboardPayload.page.recent_summary.label}:{" "}
                {dashboardPayload.page.recent_summary.profit_label} with ROI{" "}
                {dashboardPayload.page.recent_summary.roi_label} and drawdown{" "}
                {dashboardPayload.page.recent_summary.drawdown_label}.
              </p>
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
                  <p className="react-sidecar-label">Trust checks</p>
                  <h3>Why the card looks this way</h3>
                </div>
              </div>
              <div className="react-callout-stack">
                <p>{dashboardPayload.page.strategy_note}</p>
                <p>{dashboardPayload.page.board_note}</p>
              </div>
              <div className="react-card-grid react-card-grid-compact">
                {dashboardPayload.page.overview_cards.map((card) => (
                  <article className="react-metric-card" key={card.label}>
                    <p className="react-sidecar-label">{card.label}</p>
                    <h3>{card.value}</h3>
                    <p>{card.detail}</p>
                    <p className="react-muted-copy">{card.why_it_matters}</p>
                  </article>
                ))}
              </div>
            </article>
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
        </>
      ) : null}

      {route === "teams" && teamDetailPayload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Team workspace</p>
              <strong>{teamDetailPayload.page.team.team_name}</strong>
              <p>{teamDetailPayload.page.pick_summary}</p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Current board</p>
              <strong>{teamDetailPayload.page.upcoming_rows.length} live rows</strong>
              <p>
                Current qualified bets involving this team stay visible next to
                the near-term schedule.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Scheduled games</p>
              <strong>{teamDetailPayload.page.scheduled_games.length} games</strong>
              <p>
                Upcoming and in-progress games use the same middleware payload
                as the old server-rendered view.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Settled history</p>
              <strong>{teamDetailPayload.page.history_rows.length} picks</strong>
              <p>
                Backtest history and recent results stay available without
                leaving the React route.
              </p>
            </article>
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Navigation</p>
                <h3>Back to the team explorer</h3>
              </div>
              <a className="react-classic-link" href={teamsHref}>
                All teams
              </a>
            </div>
            <p className="react-summary-note">
              Use the search route to jump to another team, then stay on this
              page for current board involvement, near-term games, recent
              results, and report-window history.
            </p>
          </section>

          <section className="react-board-grid">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Board involvement</p>
                  <h3>Current recommendations</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderPickRows(teamDetailPayload.page.upcoming_rows, {
                  emptyMessage: "No live recommendations currently involve this team.",
                  variant: "qualified",
                })}
              </div>
            </article>

            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Schedule</p>
                  <h3>Current and upcoming games</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderScheduleRows(teamDetailPayload.page.scheduled_games, {
                  emptyMessage:
                    "No scheduled games are in the current local window.",
                })}
              </div>
            </article>
          </section>

          <section className="react-board-grid">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Recent results</p>
                  <h3>Completed games</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderTeamResultRows(teamDetailPayload.page.recent_results, {
                  emptyMessage: "No recent results are stored for this team.",
                })}
              </div>
            </article>

            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">History</p>
                  <h3>Backtest picks involving this team</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderPickRows(teamDetailPayload.page.history_rows, {
                  emptyMessage:
                    "No report-window picks currently involve this team.",
                  variant: "history",
                })}
              </div>
            </article>
          </section>
        </>
      ) : null}

      {route === "teams" && teamsPayload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Current query</p>
              <strong>
                {teamsPayload.page.query !== ""
                  ? `Search: ${teamsPayload.page.query}`
                  : "Featured teams only"}
              </strong>
              <p>
                Search by school or alias, then jump straight into the team
                detail route.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Matched results</p>
              <strong>{teamsPayload.page.results.length} teams</strong>
              <p>Query-driven matches stay inside the React workspace.</p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Featured board teams</p>
              <strong>{teamsPayload.page.featured.length} teams</strong>
              <p>
                The landing route still exposes the current board-driven
                shortlist when no query is active.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Route ownership</p>
              <strong>React-only team flow</strong>
              <p>
                Team search and team detail now share one frontend path against
                the existing middleware JSON contracts.
              </p>
            </article>
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Search</p>
                <h3>Find a team</h3>
              </div>
            </div>
            <form
              key={teamsPayload.page.query || "featured"}
              className="react-filter-grid"
              onSubmit={handleTeamsSearchSubmit}
            >
              <label>
                <span>Search teams</span>
                <input
                  defaultValue={teamsPayload.page.query}
                  name="q"
                  placeholder="Kansas, UConn, San Diego State"
                  type="search"
                />
              </label>
              <div className="react-filter-actions">
                <button type="submit">Search</button>
                <button onClick={handleTeamsReset} type="button">
                  Reset
                </button>
              </div>
            </form>
          </section>

          <section className="react-board-grid">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Results</p>
                  <h3>
                    {teamsPayload.page.query !== ""
                      ? `Matches for "${teamsPayload.page.query}"`
                      : "Search to start"}
                  </h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderTeamLinks(teamsPayload.page.results, {
                  basePath: "/teams",
                  emptyMessage:
                    "No explicit search results yet. Try a team name or school alias.",
                })}
              </div>
            </article>

            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Current board</p>
                  <h3>Featured teams</h3>
                </div>
              </div>
              <div className="react-row-list">
                {renderTeamLinks(teamsPayload.page.featured, {
                  basePath: "/teams",
                  emptyMessage:
                    "No featured teams are available until the prediction board has games.",
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
                Review the exact stored artifacts behind the current board
                before trusting a slate.
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
                Filter the settled log by season, team, market, and book
                without leaving the main betting workspace.
              </p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Current card</p>
              <strong>
                {picksPayload.page.cached_generated_at_label ?? "No cached card yet"}
              </strong>
              <p>
                Use the live cached recommendations below to compare the active
                board against settled history.
              </p>
            </article>
          </section>

          <section className="react-board-panel">
            {picksPayload.page.cached_rows.length > 0 ? (
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Latest cached picks</p>
                  <h3>Current job-backed recommendations</h3>
                </div>
                {picksPayload.page.cached_generated_at_label ? (
                  <span className="tone-flat">
                    {picksPayload.page.cached_generated_at_label}
                  </span>
                ) : null}
              </div>
            ) : null}
            {picksPayload.page.cached_rows.length > 0 ? (
              <div className="react-row-list">
                {renderPickRows(picksPayload.page.cached_rows, {
                  emptyMessage: "No cached picks are available yet.",
                  variant: "qualified",
                })}
              </div>
            ) : null}
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
          <section className="react-day-board-strip">
            <article className="react-day-board-summary">
              <p className="react-sidecar-label">Slate focus</p>
              <h3>
                {upcomingQualifiedCount > 0
                  ? `${upcomingQualifiedCount} bet${
                      upcomingQualifiedCount === 1 ? "" : "s"
                    } are ready right now`
                  : "No bet is cleared yet on the active slate"}
              </h3>
              <p className="react-hero-copy">
                {upcomingQualifiedCount > 0
                  ? "Start with the qualified card, then scan the watch queue and the remaining active board before you place anything."
                  : "Use the watch queue and the remaining active board to decide whether this is a waiting slate or whether the next refresh is likely to matter."}
              </p>
              <p className="react-summary-note">{upcomingPayload.page.policy_note}</p>
              <div className="react-day-board-actions">
                <a className="react-day-link is-primary" href={picksHref}>
                  Compare with history
                </a>
                <a className="react-day-link" href={performanceHref}>
                  Check recent form
                </a>
                <a className="react-day-link" href={teamsHref}>
                  Jump to a team
                </a>
              </div>
            </article>

            <div className="react-day-board-stats">
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Refresh window</p>
                <strong>{upcomingPayload.page.generated_at_label}</strong>
                <p>Expires {upcomingPayload.page.expires_at_label}</p>
              </article>
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Qualified card</p>
                <strong>
                  {upcomingQualifiedCount}{" "}
                  {upcomingQualifiedCount === 1 ? "bet" : "bets"}
                </strong>
                <p>
                  {upcomingWatchCount} close-watch{" "}
                  {upcomingWatchCount === 1 ? "row" : "rows"} behind the card.
                </p>
              </article>
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Active queue</p>
                <strong>
                  {upcomingBoardQueueCount}{" "}
                  {upcomingBoardQueueCount === 1 ? "board row" : "board rows"}
                </strong>
                <p>
                  Additional non-pass opportunities stay visible below the
                  current card.
                </p>
              </article>
              <article className="react-day-board-stat">
                <p className="react-sidecar-label">Availability note</p>
                <strong>
                  {upcomingPayload.page.availability_usage?.label ??
                    "No availability note"}
                </strong>
                <p>
                  {upcomingPayload.page.availability_summary?.label ??
                    upcomingPayload.page.availability_usage?.note ??
                    "No stored availability coverage is attached to the active slate."}
                </p>
              </article>
            </div>
          </section>

          <section className="react-board-grid react-board-grid-priority">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Qualified card</p>
                  <h3>Best bets right now</h3>
                </div>
                <span className="tone-flat">
                  {upcomingQualifiedCount}{" "}
                  {upcomingQualifiedCount === 1 ? "bet" : "bets"}
                </span>
              </div>
              <p className="react-summary-note">
                These are the current qualified recommendations from the latest
                cached job output.
              </p>
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
                  <p className="react-sidecar-label">Close watch</p>
                  <h3>Rows worth rechecking next</h3>
                </div>
                <span className="tone-warn">
                  {upcomingWatchCount}{" "}
                  {upcomingWatchCount === 1 ? "watch row" : "watch rows"}
                </span>
              </div>
              <p className="react-summary-note">
                These rows are close enough to matter if the price, line, or
                market depth moves.
              </p>
              <div className="react-row-list">
                {renderPickRows(upcomingPayload.page.watch_rows, {
                  emptyMessage: "No timing-layer watch candidates right now.",
                  variant: "watch",
                })}
              </div>
            </article>
          </section>

          <section className="react-board-grid">
            <article className="react-board-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Rest of slate</p>
                  <h3>Still-active board rows</h3>
                </div>
              </div>
              <p className="react-summary-note">
                These are the remaining non-pass board rows that are not already
                on the qualified card or the close-watch queue.
              </p>
              <div className="react-row-list">
                {renderPickRows(upcomingBoardQueueRows, {
                  emptyMessage:
                    "No additional active board rows are left after the current card and watch queue.",
                  variant: "overview",
                })}
              </div>
            </article>

            <article className="react-board-panel">
              {upcomingPayload.page.availability_summary ? (
                <>
                  <div className="react-panel-heading">
                    <div>
                      <p className="react-sidecar-label">Availability coverage</p>
                      <h3>What the slate says about player reports</h3>
                    </div>
                    {upcomingPayload.page.availability_usage ? (
                      <span className="tone-flat">
                        {upcomingPayload.page.availability_usage.label}
                      </span>
                    ) : null}
                  </div>
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
                </>
              ) : (
                <>
                  <div className="react-panel-heading">
                    <div>
                      <p className="react-sidecar-label">Availability coverage</p>
                      <h3>No stored report context on this slate</h3>
                    </div>
                  </div>
                  <p className="react-summary-note">
                    {upcomingPayload.page.availability_usage?.note ??
                      "The current slate does not carry stored availability context yet."}
                  </p>
                </>
              )}
            </article>
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Recent board context</p>
                <h3>In-progress and final state</h3>
              </div>
            </div>
            <p className="react-summary-note">
              Drop here after you work the active slate. This keeps the pregame
              decision visible once games go live or final.
            </p>
            <div className="react-row-list">
              {renderLiveBoardRows(upcomingPayload.page.live_board_rows)}
            </div>
          </section>

          <section className="react-board-panel">
            <div className="react-panel-heading">
              <div>
                <p className="react-sidecar-label">Policy framing</p>
                <h3>How to read this slate</h3>
              </div>
            </div>
            <div className="react-callout-stack">
              <p>{upcomingPayload.page.policy_note}</p>
              {upcomingPayload.page.availability_usage ? (
                <p>{upcomingPayload.page.availability_usage.note}</p>
              ) : null}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
