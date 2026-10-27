import { callMethod } from "./frappe";

export type BootstrapPayload = {
  schema_version?: number;
  user?: { email?: string; full_name?: string };
  context?: { company?: string; profile?: string };
  branding?: { app_title?: string; app_subtitle?: string };
  dashboards?: Array<{ dashboard_key?: string; label?: string; enabled?: number | boolean }>;
  board_data?: Record<string, { widgets?: Record<string, WidgetPayload> }>;
};

export type BoardDataPayload = {
  dashboard_id: string;
  widgets: Record<string, WidgetPayload>;
  errors?: Record<string, string> | null;
};

export type WidgetPayload = {
  widget_key?: string;
  widget_type?: string;
  label?: string;
  value?: number | null;
  kpi?: {
    value?: number | null;
    value_ly?: number | null;
    change_pct?: number | null;
    format?: string;
    metric?: string;
    label?: string;
  };
  chart?: {
    series?: Array<{ label?: string; value?: number; dimension_value?: string }>;
    metric?: string;
    dimension?: string;
  };
  series?: Array<{ label?: string; value?: number; dimension_value?: string }>;
  table?: { rows?: Array<Record<string, unknown>> };
  rows?: Array<Record<string, unknown>>;
  data?: Record<string, unknown>;
  meta?: {
    format?: string;
    section_title?: string;
    sort_order?: number;
    drillable?: boolean;
    next_dimension?: string;
    drill_path?: string[];
    drill_depth?: number;
    dimension?: string;
  };
  section_title?: string;
};

const ACCESS_TIMEOUT_MS = 90_000;
const BOARD_TIMEOUT_MS = 120_000;

export async function fetchBootstrap(company?: string): Promise<BootstrapPayload> {
  return callMethod<BootstrapPayload>(
    "erp_analysis.api.get_mobile_bootstrap",
    { company: company || undefined, hydrate: 0 },
    { timeoutMs: BOARD_TIMEOUT_MS },
  );
}

export async function fetchMyAccess(company?: string): Promise<{
  scope?: { company?: string; view_territories?: string[]; territories?: string[] };
  profiles?: Array<{ object_key?: string; can_view?: boolean; active?: boolean }>;
}> {
  return callMethod(
    "erp_analysis.api.get_my_access",
    { company: company || undefined },
    { timeoutMs: ACCESS_TIMEOUT_MS },
  );
}

export async function fetchWidgetData(
  widgetKey: string,
  company: string,
  options?: {
    period?: string;
    territory?: string;
    drillDepth?: number;
    dimension?: string;
    filters?: Record<string, string[]>;
    drillCrumbs?: Array<{ dimension: string; label: string; value: string }>;
    limit?: number;
  },
): Promise<WidgetPayload> {
  const boardTerritory =
    options?.territory && options.territory !== "all" ? options.territory : undefined;
  let filters = options?.filters ? { ...options.filters } : undefined;
  if (boardTerritory) {
    filters = { ...(filters || {}), territory: [boardTerritory] };
  }
  return callMethod<WidgetPayload>(
    "erp_analysis.api.get_dashboard_widget_data",
    {
      widget_key: widgetKey,
      company,
      period: options?.period || "ytd",
      drill_depth: options?.drillDepth,
      dimension: options?.dimension,
      filters: filters ? JSON.stringify(filters) : undefined,
      drill_crumbs: options?.drillCrumbs ? JSON.stringify(options.drillCrumbs) : undefined,
      territory: boardTerritory,
      limit: options?.limit ?? 15,
    },
    { timeoutMs: BOARD_TIMEOUT_MS },
  );
}

export async function fetchBoardData(
  dashboardId: string,
  company: string,
  options?: { refresh?: boolean; period?: string; territory?: string },
): Promise<BoardDataPayload> {
  const filters =
    options?.territory && options.territory !== "all"
      ? JSON.stringify({ territory: [options.territory] })
      : undefined;
  return callMethod<BoardDataPayload>(
    "erp_analysis.api.get_dashboard_board_data",
    {
      dashboard_id: dashboardId,
      company,
      period: options?.period || "ytd",
      refresh: options?.refresh ? 1 : 0,
      use_cache: options?.refresh ? 0 : 1,
      filters,
      territory: options?.territory && options.territory !== "all" ? options.territory : undefined,
    },
    { timeoutMs: BOARD_TIMEOUT_MS },
  );
}

export function widgetDisplayValue(w: WidgetPayload): number | null {
  const v = w.kpi?.value ?? w.value;
  if (v === null || v === undefined) return null;
  return typeof v === "number" ? v : Number(v);
}

export function widgetFormat(w: WidgetPayload): string {
  return w.kpi?.format || w.meta?.format || "number";
}

export function formatCompact(value: number, fmt: string): string {
  if (fmt === "currency_integer") {
    const n = Math.round(value);
    return `SAR ${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  if (fmt === "currency_compact") {
    const abs = Math.abs(value);
    if (abs >= 1_000_000) return `SAR ${(value / 1_000_000).toFixed(2)}M`;
    if (abs >= 1_000) return `SAR ${(value / 1_000).toFixed(1)}K`;
    return `SAR ${value.toFixed(0)}`;
  }
  if (fmt === "integer") return Math.round(value).toLocaleString();
  if (fmt === "decimal") return value.toFixed(2);
  if (fmt === "percent") return `${value.toFixed(1)}%`;
  return value.toLocaleString();
}
