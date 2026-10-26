import { useCallback, useEffect, useMemo, useState } from "react";
import { Layout } from "../components/Layout";
import { KpiCard } from "../components/KpiCard";
import { WidgetPayload } from "../lib/dashboard";
import { loadBoardWithLocalCache } from "../lib/boardLoad";
import { ApiError } from "../lib/frappe";
import { getSessionUser } from "../lib/auth";
import { isPilotUser } from "../lib/config";
import { Link } from "react-router-dom";
import { useMyAccess } from "../hooks/useMyAccess";
import { canViewObject, PWA_BOARD_MENU_KEYS } from "../lib/access";

export function HomePage() {
  const sessionEmail = getSessionUser()?.email;
  const { profiles } = useMyAccess(Boolean(sessionEmail && isPilotUser(sessionEmail)));
  const showSales = canViewObject(profiles, PWA_BOARD_MENU_KEYS.sales_overview);
  const showReceivables = canViewObject(profiles, PWA_BOARD_MENU_KEYS.receivables_overview);
  const showInventory = canViewObject(profiles, PWA_BOARD_MENU_KEYS.inventory_overview);
  const [company, setCompany] = useState<string>("");
  const [territories, setTerritories] = useState<string[]>([]);
  const [territory, setTerritory] = useState("all");
  const [period, setPeriod] = useState("ytd");
  const [widgets, setWidgets] = useState<Record<string, WidgetPayload>>({});
  const [errors, setErrors] = useState<Record<string, string> | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [cacheLabel, setCacheLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyBoardResult = useCallback(
    (companyName: string, terr: string[], boardWidgets: Record<string, WidgetPayload>, boardErrors: Record<string, string> | null) => {
      setCompany(companyName);
      setTerritories(terr);
      setWidgets(boardWidgets);
      setErrors(boardErrors);
    },
    [],
  );

  const load = useCallback(
    async (refresh = false) => {
      if (!sessionEmail) return;
      setError(null);
      if (refresh) {
        setLoading(true);
        setCacheLabel(null);
      } else {
        setSyncing(true);
      }
      try {
        const result = await loadBoardWithLocalCache({
          email: sessionEmail,
          dashboardId: "home",
          period,
          territory,
          refresh,
          onCached: (cached) => {
            applyBoardResult(
              cached.company,
              cached.territories,
              cached.board.widgets || {},
              cached.board.errors || null,
            );
            setCacheLabel(cached.cacheLabel);
            setLoading(false);
            setSyncing(true);
          },
        });
        applyBoardResult(
          result.company,
          result.territories,
          result.board.widgets || {},
          result.board.errors || null,
        );
        setCacheLabel(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load dashboard");
      } finally {
        setLoading(false);
        setSyncing(false);
      }
    },
    [applyBoardResult, period, sessionEmail, territory],
  );

  useEffect(() => {
    if (!sessionEmail || !isPilotUser(sessionEmail)) return;
    void load(false);
  }, [load, sessionEmail]);

  const kpiWidgets = useMemo(() => {
    return Object.entries(widgets)
      .map(([key, w]) => ({ key, ...w, widget_key: w.widget_key || key }))
      .filter((w) => (w.widget_type || "").toUpperCase() === "KPI")
      .sort((a, b) => (a.label || "").localeCompare(b.label || ""));
  }, [widgets]);

  const sections = useMemo(() => {
    const bySection: Record<string, typeof kpiWidgets> = {};
    for (const w of kpiWidgets) {
      const sec = w.section_title || w.meta?.section_title || "Overview";
      if (!bySection[sec]) bySection[sec] = [];
      bySection[sec].push(w);
    }
    return bySection;
  }, [kpiWidgets]);

  if (!sessionEmail || !isPilotUser(sessionEmail)) {
    return (
      <Layout title="Printechs" subtitle="Pilot">
        <div className="pilot-block">This account is not enabled for the web pilot.</div>
      </Layout>
    );
  }

  return (
    <Layout title="Business Insight" subtitle={company}>
      <div className="filters">
        <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period">
          <option value="ytd">YTD</option>
          <option value="mtd">MTD</option>
          <option value="qtd">QTD</option>
        </select>
        <select
          value={territory}
          onChange={(e) => setTerritory(e.target.value)}
          aria-label="Territory"
        >
          <option value="all">All territories</option>
          {territories.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn-primary"
          style={{ width: "auto", padding: "8px 14px" }}
          onClick={() => void load(true)}
          disabled={loading && syncing}
        >
          Refresh
        </button>
      </div>

      <p className="nav-links">
        {showSales ? (
          <>
            <Link to="/board/sales_overview">Sales</Link>
            {showReceivables || showInventory ? " · " : null}
          </>
        ) : null}
        {showReceivables ? (
          <>
            <Link to="/board/receivables_overview">Receivables</Link>
            {showInventory ? " · " : null}
          </>
        ) : null}
        {showInventory ? <Link to="/board/inventory_overview">Inventory</Link> : null}
      </p>

      {cacheLabel ? (
        <div className="cache-banner">
          Showing saved data ({cacheLabel}).{syncing ? " Updating…" : ""}
        </div>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}
      {loading && !kpiWidgets.length ? (
        <div className="loading">
          Loading…
          <div className="loading-hint">
            First load can take 1–2 minutes. Later visits use saved data on this device.
          </div>
        </div>
      ) : null}

      {!loading &&
        kpiWidgets.length === 0 &&
        !error && (
          <div className="pilot-block">No KPI widgets returned for Home. Try Refresh or open Sales.</div>
        )}

      {kpiWidgets.length > 0 &&
        Object.entries(sections).map(([section, items]) => (
          <div key={section}>
            <div className="section-title">{section}</div>
            <div className="kpi-grid">
              {items.map((w) => (
                <KpiCard key={w.key} widget={w} />
              ))}
            </div>
          </div>
        ))}

      {errors && Object.keys(errors).length > 0 ? (
        <div className="error-banner" style={{ marginTop: 16 }}>
          Some widgets failed: {Object.keys(errors).join(", ")}
        </div>
      ) : null}
    </Layout>
  );
}
