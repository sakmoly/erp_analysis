import type { KeyboardEvent } from "react";
import type { WidgetPayload as WP } from "../lib/dashboard";
import { chartSeries, formatSeriesValue } from "../lib/widgetTypes";

type Props = {
  widget: WP;
  onSliceDrill?: (point: { label: string; dimension_value?: string }) => void;
};

export function ChartWidget({ widget, onSliceDrill }: Props) {
  const series = chartSeries(widget);
  const title = widget.label || widget.widget_key || "Chart";
  const max = Math.max(...series.map((p) => Number(p.value) || 0), 1);
  const drillable = Boolean(
    onSliceDrill &&
      (widget.meta?.drillable ||
        widget.chart?.dimension ||
        widget.meta?.dimension),
  );

  if (!series.length) {
    return (
      <div className="chart-card">
        <div className="chart-title">{title}</div>
        <div className="chart-empty">No data</div>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <div className="chart-title">{title}</div>
      {drillable ? (
        <div className="drill-hint">
          {String(widget.chart?.dimension || widget.meta?.dimension || "").toLowerCase() === "territory"
            ? "Tap a territory for customer detail"
            : "Tap a row to drill down"}
        </div>
      ) : null}
      <ul className="bar-list">
        {series.slice(0, 12).map((point, i) => {
          const val = Number(point.value) || 0;
          const pct = Math.round((val / max) * 100);
          const label = point.label || "";
          return (
            <li
              key={`${point.label}-${i}`}
              className={`bar-row${drillable ? " bar-row-drill" : ""}`}
              {...(drillable && onSliceDrill
                ? {
                    role: "button",
                    tabIndex: 0,
                    onClick: () =>
                      onSliceDrill({
                        label,
                        dimension_value: point.dimension_value || label,
                      }),
                    onKeyDown: (e: KeyboardEvent) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSliceDrill({ label, dimension_value: point.dimension_value || label });
                      }
                    },
                  }
                : {})}
            >
              <div className="bar-label">{point.label}</div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${pct}%` }} />
              </div>
              <div className="bar-value">{formatSeriesValue(val, widget)}</div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
