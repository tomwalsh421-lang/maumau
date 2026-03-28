import { startTransition, useEffect, useState } from "react";
import type { JSX } from "react";

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
  status_label: string;
  status_tone: string;
  stake_label: string;
  edge_label: string;
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

const WINDOW_KEYS: WindowKey[] = ["7", "14", "30", "90", "season"];

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

export function App({
  rootElement,
}: {
  rootElement: HTMLDivElement;
}): JSX.Element {
  const [windowKey, setWindowKey] = useState<WindowKey>(() =>
    readInitialWindow(rootElement),
  );
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    async function loadDashboard(): Promise<void> {
      try {
        const response = await fetch(buildDashboardApiUrl(rootElement, windowKey), {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Dashboard request failed with ${response.status}.`);
        }
        const data = (await response.json()) as DashboardPayload;
        startTransition(() => {
          setPayload(data);
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

    void loadDashboard();

    return () => controller.abort();
  }, [rootElement, windowKey]);

  function handleWindowChange(nextWindow: WindowKey): void {
    const url = new URL(window.location.href);
    url.searchParams.set("window", nextWindow);
    window.history.replaceState({}, "", url);
    setWindowKey(nextWindow);
  }

  return (
    <div className="react-overview-shell">
      <section className="react-beta-hero">
        <div>
          <p className="react-kicker">React beta overview</p>
          <h2>Best-path posture without leaving the dashboard contract</h2>
          <p className="react-hero-copy">
            This surface reads the same middleware payload as the classic overview.
            It is the first migration slice, not a separate product.
          </p>
        </div>
        <div className="react-beta-sidecar">
          <p className="react-sidecar-label">Classic path</p>
          <a className="react-classic-link" href="/">
            Open the server-rendered dashboard
          </a>
        </div>
      </section>

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
        {payload ? (
          <p className="react-summary-note">{payload.page.recent_summary.explanation}</p>
        ) : null}
      </section>

      {loading && payload === null ? (
        <section className="react-loading-state">
          <p>Loading the dashboard snapshot and current board.</p>
        </section>
      ) : null}

      {error ? (
        <section className="react-error-state">
          <p className="react-sidecar-label">React beta error</p>
          <p>{error}</p>
        </section>
      ) : null}

      {payload ? (
        <>
          <section className="react-status-grid">
            <article className="react-status-card">
              <p className="react-sidecar-label">Strategy note</p>
              <p>{payload.page.strategy_note}</p>
            </article>
            <article className="react-status-card">
              <p className="react-sidecar-label">Board note</p>
              <p>{payload.page.board_note}</p>
            </article>
            {payload.page.availability_usage ? (
              <article className="react-status-card">
                <p className="react-sidecar-label">Availability usage</p>
                <strong>{payload.page.availability_usage.label}</strong>
                <p>{payload.page.availability_usage.note}</p>
              </article>
            ) : null}
            <article className="react-status-card">
              <p className="react-sidecar-label">Recent summary</p>
              <strong>
                {payload.page.recent_summary.label}: {payload.page.recent_summary.profit_label}
              </strong>
              <p>
                ROI {payload.page.recent_summary.roi_label} across{" "}
                {payload.page.recent_summary.bets} bets with drawdown{" "}
                {payload.page.recent_summary.drawdown_label}.
              </p>
            </article>
          </section>

          <section className="react-card-grid">
            {payload.page.overview_cards.map((card) => (
              <article className="react-metric-card" key={card.label}>
                <p className="react-sidecar-label">{card.label}</p>
                <h3>{card.value}</h3>
                <p>{card.detail}</p>
                <p className="react-muted-copy">{card.why_it_matters}</p>
              </article>
            ))}
          </section>

          {payload.page.season_bars.length > 0 ? (
            <section className="react-season-panel">
              <div className="react-panel-heading">
                <div>
                  <p className="react-sidecar-label">Season shape</p>
                  <h3>Per-season profit posture</h3>
                </div>
              </div>
              <div className="react-season-bars">
                {payload.page.season_bars.map((bar) => (
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
                {payload.page.recent_rows.map((row) => (
                  <article
                    className="react-row-card"
                    key={`${row.matchup_label}-${row.commence_label}`}
                  >
                    <div className="react-row-topline">
                      <strong>{row.matchup_label}</strong>
                      <span className={`tone-${row.status_tone}`}>{row.status_label}</span>
                    </div>
                    <p className="react-row-meta">
                      {row.commence_label} · {row.side_label} · {row.stake_label}
                    </p>
                    <p className="react-row-meta">
                      Edge {row.edge_label} · Profit {row.profit_label}
                    </p>
                  </article>
                ))}
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
                {payload.page.upcoming_rows.map((row) => (
                  <article
                    className="react-row-card"
                    key={`${row.matchup_label}-${row.commence_label}`}
                  >
                    <div className="react-row-topline">
                      <strong>{row.matchup_label}</strong>
                      <span className={`tone-${row.status_tone}`}>{row.status_label}</span>
                    </div>
                    <p className="react-row-meta">
                      {row.commence_label} · {row.side_label}
                    </p>
                    <p className="react-row-meta">
                      Coverage {row.coverage_label} · Edge {row.edge_label}
                    </p>
                  </article>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}
