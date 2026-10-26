import { formatCompact, WidgetPayload } from "./dashboard";

export type ChartPoint = {
  label?: string;
  value?: number;
  dimension_value?: string;
  value_ly?: number;
  change_pct?: number;
};

export function chartSeries(w: WidgetPayload): ChartPoint[] {
  const chart = w.chart as { series?: ChartPoint[] } | undefined;
  if (chart?.series?.length) return chart.series;
  if (Array.isArray(w.series)) return w.series as ChartPoint[];
  const data = w.data as { series?: ChartPoint[] } | undefined;
  if (data?.series?.length) return data.series;
  return [];
}

export type TableRow = Record<string, unknown>;

export function tableRows(w: WidgetPayload): TableRow[] {
  const table = w.table as { rows?: TableRow[] } | undefined;
  if (table?.rows?.length) return table.rows;
  if (Array.isArray(w.rows)) return w.rows as TableRow[];
  const data = w.data as { rows?: TableRow[] } | undefined;
  if (data?.rows?.length) return data.rows;
  return [];
}

export function rowLabel(row: TableRow): string {
  const v =
    row.dimension ??
    row.label ??
    row.customer ??
    row.territory ??
    row.name ??
    row.itemName;
  return v != null ? String(v) : "—";
}

export function rowMetric(row: TableRow): number | null {
  const v = row.metric ?? row.value ?? row.net_sales ?? row.outstanding ?? row.amount;
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

export function formatSeriesValue(value: number, w: WidgetPayload): string {
  const fmt =
    (w.chart as { metric?: string } | undefined)?.metric === "net_sales"
      ? "currency_compact"
      : w.meta?.format || "currency_compact";
  return formatCompact(value, fmt);
}

export const CHART_TYPES = new Set(["LINE", "BAR", "PIE", "DONUT"]);
export const LIST_TYPES = new Set(["RANKING", "TABLE", "LIST"]);
