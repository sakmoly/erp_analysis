import { formatCompact, widgetDisplayValue, widgetFormat, WidgetPayload } from "../lib/dashboard";

type Props = {
  widget: WidgetPayload;
};

export function KpiCard({ widget }: Props) {
  const value = widgetDisplayValue(widget);
  const fmt = widgetFormat(widget);
  const label = widget.label || widget.kpi?.label || widget.widget_key || "KPI";

  return (
    <div className="kpi-card">
      <div className="label">{label}</div>
      <div className="value">
        {value === null || Number.isNaN(value) ? "—" : formatCompact(value, fmt)}
      </div>
    </div>
  );
}
