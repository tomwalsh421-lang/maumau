import { startTransition, useEffect, useState } from "react";
import type { JSX } from "react";

type AppRoute = "overview" | "upcoming";
type WindowKey = "7" | "14" | "30" | "90" | "season";

type OverviewCard = {
  label: string;
  value: string;
  detail: string;
  why_it_matters: string;
};

type AvailabilityUsageView = {
  state: string;
  label: string;
  note: string;
};

type PerformanceWindowSummary = {
  key: WindowKey;
  label: string;
  bets: number;
  profit_label: string;
  roi_label: string;
  drawdown_label: string;
  explanation: string;
};

type PickTableRow = {
  matchup_label: string;
  commence_label: string;
  side_label: string;
  sportsbook_label: string;
  status_label: string;
  status_tone: string;
  stake_label: string;
  edge_label: string;
  expected_value_label: string;
  coverage_label: string;
  profit_label: string;
};

type SeasonChartBar = {
  season: number;
  profit_label: string;
  roi_label: string;
  height_pct: number;
  tone: string;
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

function readAppPath(rootElement: HTMLDivElement): string {
  return rootElement.dataset.appPath ?? window.location.pathname;
}

function readAppRoute(rootElement: HTMLDivElement): AppRoute {
  const rawPath = readAppPath(rootElement);
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
    variant: "qualified" | "watch" | "overview";
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
          key={`${variant}-${row.matchup_label}-${row.commence_label}`}
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
    (route === "overview" ? "/" : "/classic/upcoming");
  const classicLabel =
    rootElement.dataset.classicLabel ??
    (route === "overview"
      ? "Open the server-rendered dashboard"
      : "Open the server-rendered recommendations fallback");
  const upcomingHref = isBetaRoute ? "/app/upcoming" : "/upcoming";
  const [windowKey, setWindowKey] = useState<WindowKey>(() =>
    readInitialWindow(rootElement),
  );
  const [dashboardPayload, setDashboardPayload] = useState<DashboardPayload | null>(
    null,
  );
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
            ? buildDashboardApiUrl(rootElement, windowKey)
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
            setUpcomingPayload(null);
          } else {
            setUpcomingPayload(data as UpcomingPayload);
            setDashboardPayload(null);
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
  }, [rootElement, route, windowKey]);

  function handleWindowChange(nextWindow: WindowKey): void {
    const url = new URL(window.location.href);
    url.searchParams.set("window", nextWindow);
    window.history.replaceState({}, "", url);
    setWindowKey(nextWindow);
  }

  const heroTitle =
    route === "overview"
      ? "Best-path posture without leaving the dashboard contract"
      : isBetaRoute
        ? "Recommendations without leaving the React beta"
        : "Recommendations on the primary route";
  const heroCopy =
    route === "overview"
      ? "This surface reads the same middleware payload as the classic overview. It is the first migration slice, not a separate product."
      : isBetaRoute
        ? "This recommendations view reuses the existing upcoming-page contract, including live picks, the timing watchlist, and the recent board state."
        : "This route now serves the React recommendations client by default while the classic server-rendered page remains available as a documented fallback.";

  return (
    <div className="react-overview-shell">
      <section className="react-beta-hero">
        <div>
          <p className="react-kicker">
            {route === "overview"
              ? "React beta overview"
              : isBetaRoute
                ? "React beta recommendations"
                : "React recommendations"}
          </p>
          <h2>{heroTitle}</h2>
          <p className="react-hero-copy">{heroCopy}</p>
        </div>
        <div className="react-beta-sidecar">
          <p className="react-sidecar-label">React routes</p>
          <nav className="react-beta-nav" aria-label="React routes">
            <a
              className={route === "overview" ? "is-active" : undefined}
              href={`/app?window=${windowKey}`}
            >
              Overview
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

      {loading &&
      ((route === "overview" && dashboardPayload === null) ||
        (route === "upcoming" && upcomingPayload === null)) ? (
        <section className="react-loading-state">
          <p>
            {route === "overview"
              ? "Loading the dashboard snapshot and current board."
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
