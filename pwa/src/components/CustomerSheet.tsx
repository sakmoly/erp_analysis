type Props = {
  name: string;
  payload: Record<string, unknown> | null;
  loading: boolean;
  onClose: () => void;
};

export function CustomerSheet({ name, payload, loading, onClose }: Props) {
  const recv = payload?.receivables as Record<string, unknown> | undefined;
  const customer = payload?.customer as Record<string, unknown> | undefined;
  const invoices = (payload?.recent_invoices as Array<Record<string, unknown>> | undefined) || [];

  return (
    <div className="drill-panel customer-sheet" role="dialog" aria-label="Customer detail">
      <div className="drill-header">
        <button type="button" className="btn-ghost-inline" onClick={onClose}>
          Close
        </button>
        <div className="drill-title">{String(customer?.customer_name || customer?.id || name)}</div>
      </div>
      {loading ? <div className="loading">Loading…</div> : null}
      {!loading && recv ? (
        <>
          <div className="customer-blocks">
            <div className="customer-block">
              <div className="label">Outstanding</div>
              <div className="value">{formatNum(recv.outstanding ?? recv.total_outstanding)}</div>
            </div>
            <div className="customer-block">
              <div className="label">Overdue</div>
              <div className="value">{formatNum(recv.overdue)}</div>
            </div>
            {recv.current != null ? (
              <div className="customer-block">
                <div className="label">Not yet due</div>
                <div className="value">{formatNum(recv.current)}</div>
              </div>
            ) : null}
            {recv.avg_monthly_sales != null ? (
              <div className="customer-block">
                <div className="label">Avg monthly sales</div>
                <div className="value">{formatNum(recv.avg_monthly_sales)}</div>
              </div>
            ) : null}
            {customer?.territory ? (
              <div className="customer-meta">Territory: {String(customer.territory)}</div>
            ) : null}
            {recv.oldest_invoice ? (
              <div className="customer-meta">Oldest open invoice: {String(recv.oldest_invoice)}</div>
            ) : null}
          </div>
          {invoices.length > 0 ? (
            <>
              <div className="section-title">Recent invoices</div>
              <ul className="rank-list customer-invoices">
                {invoices.slice(0, 8).map((inv) => (
                  <li key={String(inv.name)} className="rank-row">
                    <span className="rank-label">
                      {String(inv.name)}
                      {inv.due_date ? (
                        <span className="invoice-due"> due {String(inv.due_date)}</span>
                      ) : null}
                    </span>
                    <span className="rank-value">{formatNum(inv.outstanding ?? inv.amount)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </>
      ) : null}
      {!loading && !recv ? <div className="chart-empty">No customer detail returned.</div> : null}
    </div>
  );
}

function formatNum(v: unknown): string {
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1_000_000) return `SAR ${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `SAR ${(n / 1_000).toFixed(1)}K`;
  return `SAR ${n.toFixed(0)}`;
}
