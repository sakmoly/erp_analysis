import type { KeyboardEvent } from "react";
import { formatCompact, type WidgetPayload as WP } from "../lib/dashboard";
import { rowLabel, rowMetric, tableRows } from "../lib/widgetTypes";

type Props = {
  widget: WP;
  onRowTap?: (customerId: string, label: string) => void;
  onRowDrill?: (point: { label: string; dimension_value?: string }) => void;
};

export function RankingWidget({ widget, onRowTap, onRowDrill }: Props) {
  const dim = (
    widget.chart?.dimension ||
    widget.meta?.dimension ||
    widget.data?.dimension ||
    ""
  ).toString().toLowerCase();
  const customerRows =
    dim.includes("customer") ||
    (widget.widget_key || "").toLowerCase().includes("customer");
  const rows = tableRows(widget);
  const title = widget.label || widget.widget_key || "Ranking";
  const drillable = Boolean(
    onRowDrill && widget.meta?.drillable && widget.meta?.next_dimension,
  );

  if (!rows.length) {
    const series = (widget.series || widget.chart?.series) as Array<{ label?: string; value?: number }> | undefined;
    if (series?.length) {
      const tappable = Boolean(customerRows && onRowTap);
      return (
        <div className="chart-card">
          <div className="chart-title">{title}</div>
          {tappable ? <div className="drill-hint">Tap a customer for receivables detail</div> : null}
          <ul className="rank-list">
            {series.slice(0, 10).map((p, i) => {
              const label = p.label || "";
              const id = String((p as { dimension_value?: string }).dimension_value || label);
              return (
                <li
                  key={i}
                  className={`rank-row${tappable ? " rank-row-drill" : ""}`}
                  {...(tappable
                    ? {
                        role: "button",
                        tabIndex: 0,
                        onClick: () => onRowTap!(id, label),
                        onKeyDown: (e: KeyboardEvent) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onRowTap!(id, label);
                          }
                        },
                      }
                    : {})}
                >
                  <span className="rank-label">{label}</span>
                  <span className="rank-value">
                    {p.value != null ? formatCompact(Number(p.value), "currency_compact") : "—"}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      );
    }
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
      {customerRows && onRowTap ? (
        <div className="drill-hint">Tap a customer for receivables detail</div>
      ) : drillable ? (
        <div className="drill-hint">Tap a row to drill down</div>
      ) : null}
      <ul className="rank-list">
        {rows.slice(0, 10).map((row, i) => {
          const metric = rowMetric(row);
          const label = rowLabel(row);
          const customerId = String(
            row.customer ?? row.dimension_value ?? row.name ?? row.party ?? label,
          );
          const tappable = Boolean(customerRows && onRowTap);
          const drillTap = Boolean(
            drillable &&
              !tappable &&
              (row.dimension_value != null || label),
          );
          return (
            <li
              key={i}
              className={`rank-row${tappable || drillTap ? " rank-row-drill" : ""}`}
              {...(tappable
                ? {
                    role: "button",
                    tabIndex: 0,
                    onClick: () => onRowTap!(customerId, label),
                    onKeyDown: (e: KeyboardEvent) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onRowTap!(customerId, label);
                      }
                    },
                  }
                : drillTap
                  ? {
                      role: "button",
                      tabIndex: 0,
                      onClick: () =>
                        onRowDrill!({
                          label,
                          dimension_value: String(row.dimension_value ?? label),
                        }),
                      onKeyDown: (e: KeyboardEvent) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowDrill!({
                            label,
                            dimension_value: String(row.dimension_value ?? label),
                          });
                        }
                      },
                    }
                  : {})}
            >
              <span className="rank-label">{label}</span>
              <span className="rank-value">
                {metric != null ? formatCompact(metric, "currency_compact") : "—"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
