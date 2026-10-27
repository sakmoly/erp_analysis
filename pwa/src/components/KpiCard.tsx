import { formatCompact, widgetDisplayValue, widgetFormat, WidgetPayload } from "../lib/dashboard";

type Props = {
  widget: WidgetPayload;
};

export function KpiCard({ widget }: Props) {
  const value = widgetDisplayValue(widget);
  const fmt = widgetFormat(widget);
  const label = widget.label || widget.kpi?.label || widget.widget_key || "KPI";

  const valueDisplay =
    (widget.kpi as { value_display?: string } | undefined)?.value_display ||
    (widget.data as { value_display?: string } | undefined)?.value_display;

  return (
    <div className="kpi-card">
      <div className="label">{label}</div>
      <div className="value">
        {typeof valueDisplay === "string" && valueDisplay.trim()
          ? valueDisplay
          : value === null || Number.isNaN(value)
            ? "—"
            : formatCompact(value, fmt)}
      </div>
    </div>
  );
}
