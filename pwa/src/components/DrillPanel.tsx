import { WidgetPayload } from "../lib/dashboard";
import { ChartWidget } from "./ChartWidget";
import { RankingWidget } from "./RankingWidget";
import { LIST_TYPES, CHART_TYPES } from "../lib/widgetTypes";

export type DrillCrumb = { dimension: string; label: string; value: string };

type Props = {
  title: string;
  crumbs: DrillCrumb[];
  widget: WidgetPayload | null;
  loading: boolean;
  onBack: () => void;
  onClose: () => void;
  onSliceDrill?: (point: { label: string; dimension_value?: string }) => void;
  onCustomerTap?: (customerId: string, label: string) => void;
};

export function DrillPanel({
  title,
  crumbs,
  widget,
  loading,
  onBack,
  onClose,
  onSliceDrill,
  onCustomerTap,
}: Props) {
  const wType = (widget?.widget_type || "").toUpperCase();
  const renderHint = (widget?.meta?.render_hint || "").toLowerCase();
  const tableFirst =
    renderHint === "table" ||
    renderHint === "ranking" ||
    Boolean(widget?.table?.rows?.length);
  const isChart = !tableFirst && CHART_TYPES.has(wType);
  const isList = tableFirst || LIST_TYPES.has(wType) || wType === "TABLE";

  return (
    <div className="drill-panel" role="dialog" aria-label="Drill down">
      <div className="drill-header">
        <button type="button" className="btn-ghost-inline" onClick={crumbs.length ? onBack : onClose}>
          {crumbs.length ? "← Back" : "Close"}
        </button>
        <div className="drill-title">{title}</div>
      </div>
      {crumbs.length > 0 ? (
        <div className="drill-crumbs">
          {crumbs.map((c, i) => (
            <span key={`${c.dimension}-${c.value}-${i}`}>
              {i > 0 ? " › " : ""}
              {c.label}
            </span>
          ))}
        </div>
      ) : null}
      {loading ? <div className="loading">Loading…</div> : null}
      {!loading && widget && isChart ? (
        <ChartWidget widget={widget} onSliceDrill={onSliceDrill} />
      ) : null}
      {!loading && widget && isList ? (
        <RankingWidget widget={widget} onRowTap={onCustomerTap} onRowDrill={onSliceDrill} />
      ) : null}
      {!loading && widget && !isChart && !isList ? (
        <RankingWidget widget={widget} onRowTap={onCustomerTap} onRowDrill={onSliceDrill} />
      ) : null}
    </div>
  );
}
