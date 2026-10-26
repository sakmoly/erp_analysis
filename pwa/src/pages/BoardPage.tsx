import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { KpiCard } from "../components/KpiCard";
import { ChartWidget } from "../components/ChartWidget";
import { RankingWidget } from "../components/RankingWidget";
import { fetchWidgetData, WidgetPayload } from "../lib/dashboard";
import { loadBoardWithLocalCache } from "../lib/boardLoad";
import { CHART_TYPES, LIST_TYPES } from "../lib/widgetTypes";
import { ApiError, callMethod } from "../lib/frappe";
import { DrillPanel, DrillCrumb } from "../components/DrillPanel";
import { CustomerSheet } from "../components/CustomerSheet";
import { SheetOverlay } from "../components/SheetOverlay";
import { AttentionListWidget } from "../components/AttentionListWidget";
import { getSessionUser } from "../lib/auth";
import { useMyAccess } from "../hooks/useMyAccess";
import { canViewObject, PWA_BOARD_MENU_KEYS } from "../lib/access";

const BOARD_LABELS: Record<string, string> = {
  sales_overview: "Sales Dashboard",
  receivables_overview: "Receivables",
  inventory_overview: "Inventory",
  home: "Home",
};

type WidgetEntry = { key: string } & WidgetPayload;

function normalizeDrillDimension(dim: string): string {
  const k = dim.trim().toLowerCase();
  if (k === "item_group" || k === "group") return "sub_group";
  if (k === "channel") return "division";
  return k;
}

function filtersFromCrumbs(crumbs: DrillCrumb[]): Record<string, string[]> {
  const filters: Record<string, string[]> = {};
  for (const c of crumbs) {
    const key = normalizeDrillDimension(c.dimension);
    const value = (c.value || c.label || "").trim();
    if (value) filters[key] = [value];
  }
  return filters;
}

function isCanonicalWidget(entry: WidgetEntry): boolean {
  const canonical = (entry.widget_key || entry.key).trim();
  return entry.key.trim() === canonical;
}

function sortWidgets(entries: WidgetEntry[]): WidgetEntry[] {
  return [...entries].sort((a, b) => {
    const ao = Number(a.meta?.sort_order ?? 999);
    const bo = Number(b.meta?.sort_order ?? 999);
    if (ao !== bo) return ao - bo;
    return (a.label || a.key).localeCompare(b.label || b.key);
  });
}

/** Hide territory breakdown KPIs when filtered; drop duplicate labels from alias keys. */
function filterKpiEntries(entries: WidgetEntry[], territoryNames: string[]): WidgetEntry[] {
  const terrSet = new Set(territoryNames.map((t) => t.toLowerCase()));
  const seenLabels = new Set<string>();
  return entries.filter((w) => {
    if ((w.widget_type || "").toUpperCase() !== "KPI") return false;
    const label = (w.label || w.key || "").trim();
    const key = (w.key || "").trim();
    if (terrSet.has(label.toLowerCase()) || terrSet.has(key.toLowerCase())) {
      return false;
    }
    const dedupe = label.toLowerCase();
    if (seenLabels.has(dedupe)) return false;
    seenLabels.add(dedupe);
    return true;
  });
}

export function BoardPage() {
  const { boardId = "sales_overview" } = useParams();
  const sessionEmail = getSessionUser()?.email;
  const { profiles, ready: accessReady } = useMyAccess(Boolean(sessionEmail));
  const menuKey = PWA_BOARD_MENU_KEYS[boardId];
  const boardAllowed = !menuKey || canViewObject(profiles, menuKey);
  const showSales = canViewObject(profiles, PWA_BOARD_MENU_KEYS.sales_overview);
  const showReceivables = canViewObject(profiles, PWA_BOARD_MENU_KEYS.receivables_overview);
  const showInventory = canViewObject(profiles, PWA_BOARD_MENU_KEYS.inventory_overview);
  const [company, setCompany] = useState("");
  const [territories, setTerritories] = useState<string[]>([]);
  const [territory, setTerritory] = useState("all");
  const [period, setPeriod] = useState("ytd");
  const [widgets, setWidgets] = useState<Record<string, WidgetPayload>>({});
  const [errors, setErrors] = useState<Record<string, string> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [orderKeys, setOrderKeys] = useState<string[]>([]);
  const [cacheLabel, setCacheLabel] = useState<string | null>(null);
  const [drillOpen, setDrillOpen] = useState(false);
  const [drillWidgetKey, setDrillWidgetKey] = useState("");
  const [drillTitle, setDrillTitle] = useState("");
  const [drillCrumbs, setDrillCrumbs] = useState<DrillCrumb[]>([]);
  const [drillFilters, setDrillFilters] = useState<Record<string, string[]>>({});
  const [drillPayload, setDrillPayload] = useState<WidgetPayload | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [customerPayload, setCustomerPayload] = useState<Record<string, unknown> | null>(null);
  const [customerLoading, setCustomerLoading] = useState(false);

  const loadDrill = useCallback(
    async (
      widgetKey: string,
      title: string,
      crumbs: DrillCrumb[],
      filters: Record<string, string[]>,
      drillDepth: number,
      dimension?: string,
    ) => {
      if (!company) return;
      setDrillLoading(true);
      setDrillOpen(true);
      setDrillWidgetKey(widgetKey);
      setDrillTitle(title);
      setDrillCrumbs(crumbs);
      setDrillFilters(filters);
      try {
        const payload = await fetchWidgetData(widgetKey, company, {
          period,
          territory,
          drillDepth,
          dimension,
          filters,
          drillCrumbs: crumbs,
        });
        setDrillPayload(payload);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Drill-down failed");
        setDrillOpen(false);
      } finally {
        setDrillLoading(false);
      }
    },
    [company, period, territory],
  );

  const onCustomerTap = useCallback(
    async (id: string, _label: string) => {
      if (!company) return;
      setDrillOpen(false);
      setDrillPayload(null);
      setCustomerId(id);
      setCustomerLoading(true);
      try {
        const data = await callMethod<Record<string, unknown>>("erp_analysis.customer.get_customer_360", {
          company,
          customer: id,
        });
        setCustomerPayload(data);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load customer");
        setCustomerId(null);
      } finally {
        setCustomerLoading(false);
      }
    },
    [company],
  );

  const openReceivablesTerritoryDetail = useCallback(
    (terr: string) => {
      if (territory === "all") {
        setTerritory(terr);
        return;
      }
      const crumbs: DrillCrumb[] = [{ dimension: "territory", label: terr, value: terr }];
      void loadDrill(
        "receivables_overdue_customers_table",
        `${terr} — overdue customers`,
        crumbs,
        { territory: [terr] },
        1,
      );
    },
    [loadDrill, territory],
  );

  const onChartPoint = useCallback(
    (widget: WidgetEntry, point: { label: string; dimension_value?: string }) => {
      const dim = String(
        widget.chart?.dimension ||
          widget.table?.dimension ||
          widget.meta?.dimension ||
          "",
      ).toLowerCase();
      const value = (point.dimension_value || point.label).trim();
      if (!value) return;

      if (boardId === "receivables_overview" && dim === "territory") {
        openReceivablesTerritoryDetail(value);
        return;
      }

      if (dim === "customer") {
        void onCustomerTap(value, point.label);
        return;
      }

      if (widget.meta?.drillable) {
        const widgetKey = widget.widget_key || widget.key;
        const drillPath = (widget.meta?.drill_path as string[] | undefined) || [];
        const dimKey = normalizeDrillDimension(
          String(
            drillPath[0] ||
              widget.table?.dimension ||
              widget.meta?.dimension ||
              widget.chart?.dimension ||
              "territory",
          ),
        );
        const crumbs: DrillCrumb[] = [{ dimension: dimKey, label: point.label, value }];
        void loadDrill(
          widgetKey,
          widget.label || widgetKey,
          crumbs,
          filtersFromCrumbs(crumbs),
          crumbs.length,
        );
      }
    },
    [boardId, loadDrill, onCustomerTap, openReceivablesTerritoryDetail],
  );

  const onDrillSlice = useCallback(
    (point: { label: string; dimension_value?: string }) => {
      if (!drillPayload || !drillWidgetKey) return;
      if (!drillPayload.meta?.drillable) return;
      const drillPath = (drillPayload.meta?.drill_path as string[] | undefined) || [];
      const dimKey = normalizeDrillDimension(
        String(
          drillPath[drillCrumbs.length] ||
            drillPayload.table?.dimension ||
            drillPayload.meta?.dimension ||
            drillPayload.chart?.dimension ||
            "",
        ),
      );
      if (!dimKey) return;
      const value = (point.dimension_value || point.label).trim();
      if (!value) return;
      const crumbs: DrillCrumb[] = [
        ...drillCrumbs,
        { dimension: dimKey, label: point.label, value },
      ];
      void loadDrill(
        drillWidgetKey,
        drillTitle,
        crumbs,
        filtersFromCrumbs(crumbs),
        crumbs.length,
      );
    },
    [drillCrumbs, drillFilters, drillPayload, drillTitle, drillWidgetKey, loadDrill],
  );

  const load = useCallback(
    async (refresh = false) => {
      if (!sessionEmail) return;
      setError(null);
      if (refresh) setLoading(true);
      try {
        const result = await loadBoardWithLocalCache({
          email: sessionEmail,
          dashboardId: boardId,
          period,
          territory,
          refresh,
          onCached: (cached) => {
            setCompany(cached.company);
            setTerritories(cached.territories);
            setWidgets(cached.board.widgets || {});
            setOrderKeys(Object.keys(cached.board.widgets || {}));
            setErrors(cached.board.errors || null);
            setCacheLabel(cached.cacheLabel);
            setLoading(false);
          },
        });
        setCompany(result.company);
        setTerritories(result.territories);
        setWidgets(result.board.widgets || {});
        setOrderKeys(Object.keys(result.board.widgets || {}));
        setErrors(result.board.errors || null);
        setCacheLabel(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load board");
      } finally {
        setLoading(false);
      }
    },
    [boardId, period, sessionEmail, territory],
  );

  useEffect(() => {
    if (!accessReady || !boardAllowed) return;
    void load(false);
  }, [accessReady, boardAllowed, load]);

  const entries = useMemo(() => {
    const list = Object.entries(widgets).map(([key, w]) => ({
      key,
      ...w,
      widget_key: w.widget_key || key,
    }));
    if (orderKeys.length) {
      list.sort((a, b) => {
        const ai = orderKeys.indexOf(a.key);
        const bi = orderKeys.indexOf(b.key);
        if (ai === -1 && bi === -1) return 0;
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      });
      return list;
    }
    return sortWidgets(list);
  }, [orderKeys, widgets]);

  if (accessReady && !boardAllowed) {
    return <Navigate to="/board/sales_overview" replace />;
  }

  const kpis = filterKpiEntries(entries, territories);
  const charts = entries.filter(
    (w) => isCanonicalWidget(w) && CHART_TYPES.has((w.widget_type || "").toUpperCase()),
  );
  const lists = entries.filter(
    (w) => isCanonicalWidget(w) && LIST_TYPES.has((w.widget_type || "").toUpperCase()),
  );
  const attentionLists = lists.filter((w) => (w.widget_type || "").toUpperCase() === "LIST");
  const rankingLists = lists.filter((w) => (w.widget_type || "").toUpperCase() !== "LIST");

  return (
    <Layout title={BOARD_LABELS[boardId] || boardId} subtitle={company}>
      <p style={{ margin: "0 0 12px", fontSize: "0.85rem" }}>
        <Link to="/">← Home</Link>
        {" · "}
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

      <div className="filters">
        <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period">
          <option value="ytd">YTD</option>
          <option value="mtd">MTD</option>
          <option value="qtd">QTD</option>
        </select>
        <select value={territory} onChange={(e) => setTerritory(e.target.value)} aria-label="Territory">
          <option value="all">All territories</option>
          {territories.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn-primary btn-sm"
          onClick={() => void load(true)}
        >
          Refresh
        </button>
      </div>

      {territory !== "all" ? (
        <div className="cache-banner">Territory filter: {territory}</div>
      ) : null}

      {cacheLabel ? (
        <div className="cache-banner">Showing saved data ({cacheLabel}).</div>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}
      {loading ? <div className="loading">Loading…</div> : null}

      {!loading && kpis.length > 0 ? (
        <>
          <div className="section-title">Key indicators</div>
          <div className="kpi-grid">
            {kpis.map((w) => (
              <KpiCard key={w.key} widget={w} />
            ))}
          </div>
        </>
      ) : null}

      {!loading &&
        charts.map((w) => {
          const chartInteractive =
            boardId === "receivables_overview" ||
            Boolean(w.meta?.drillable) ||
            Boolean(w.chart?.dimension || w.meta?.dimension);
          return (
            <ChartWidget
              key={w.key}
              widget={w}
              onSliceDrill={
                chartInteractive ? (point) => onChartPoint(w, point) : undefined
              }
            />
          );
        })}

      {!loading && attentionLists.map((w) => (
        <AttentionListWidget key={w.key} widget={w} />
      ))}

      {!loading && rankingLists.length > 0 ? (
        <>
          <div className="section-title">Customer / invoice detail</div>
          {rankingLists.map((w) => (
            <RankingWidget
              key={w.key}
              widget={w}
              onRowTap={onCustomerTap}
              onRowDrill={w.meta?.drillable ? (point) => onChartPoint(w, point) : undefined}
            />
          ))}
        </>
      ) : null}

      <SheetOverlay
        open={drillOpen}
        onClose={() => {
          setDrillOpen(false);
          setDrillPayload(null);
        }}
      >
        {drillOpen ? (
          <DrillPanel
            title={drillTitle}
            crumbs={drillCrumbs}
            widget={drillPayload}
            loading={drillLoading}
            onClose={() => {
              setDrillOpen(false);
              setDrillPayload(null);
            }}
            onBack={() => {
              if (drillCrumbs.length <= 1) {
                setDrillOpen(false);
                setDrillPayload(null);
                return;
              }
              const prev = drillCrumbs.slice(0, -1);
              void loadDrill(
                drillWidgetKey,
                drillTitle,
                prev,
                filtersFromCrumbs(prev),
                prev.length,
              );
            }}
            onSliceDrill={onDrillSlice}
            onCustomerTap={onCustomerTap}
          />
        ) : null}
      </SheetOverlay>

      <SheetOverlay
        open={Boolean(customerId)}
        onClose={() => {
          setCustomerId(null);
          setCustomerPayload(null);
        }}
      >
        {customerId ? (
          <CustomerSheet
            name={customerId}
            payload={customerPayload}
            loading={customerLoading}
            onClose={() => {
              setCustomerId(null);
              setCustomerPayload(null);
            }}
          />
        ) : null}
      </SheetOverlay>

      {errors && Object.keys(errors).length > 0 ? (
        <div className="error-banner" style={{ marginTop: 16 }}>
          Widget errors: {Object.entries(errors).map(([k, v]) => `${k}: ${v}`).join("; ")}
        </div>
      ) : null}
    </Layout>
  );
}
