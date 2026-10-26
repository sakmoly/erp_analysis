import type { WidgetPayload as WP } from "../lib/dashboard";

type Props = {
  widget: WP;
};

export function AttentionListWidget({ widget }: Props) {
  const data = widget.data as { items?: Array<Record<string, unknown>> } | undefined;
  const items = data?.items || [];
  const title = widget.label || widget.widget_key || "Attention";

  if (!items.length) {
    return (
      <div className="chart-card">
        <div className="chart-title">{title}</div>
        <div className="chart-empty">No alerts</div>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <div className="chart-title">{title}</div>
      <ul className="rank-list">
        {items.map((item, i) => (
          <li key={String(item.key ?? i)} className="rank-row">
            <span className="rank-label">{String(item.label ?? item.key ?? "—")}</span>
            <span className="rank-value">{String(item.count ?? "—")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
