import React from 'react';
import { Briefcase, ListOrdered, History, LogOut } from 'lucide-react';

export default function HoldingsOrdersTab({ portfolio, onSquareOff }) {
  const positions = portfolio?.positions || [];
  const orders = portfolio?.orders || [];
  const history = portfolio?.trade_history || [];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '20px' }}>
      {/* 1. Active Holdings Table */}
      <div className="glass-panel" style={{ padding: '20px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '14px',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '10px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '15px', fontWeight: '800', color: '#f8fafc' }}>
            <Briefcase size={16} color="#10b981" />
            <span>Active Portfolio Holdings ({positions.length})</span>
          </div>
          <span className="badge badge-emerald" style={{ fontSize: '10px' }}>
            CONSERVATIVE MARGIN
          </span>
        </div>

        {positions.length === 0 ? (
          <div style={{ padding: '36px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No open stock positions currently held. Use the Order Widget to simulate a position.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <th style={{ padding: '8px 6px' }}>Symbol</th>
                  <th style={{ padding: '8px 6px' }}>Qty</th>
                  <th style={{ padding: '8px 6px' }}>Avg Price</th>
                  <th style={{ padding: '8px 6px' }}>Current Price</th>
                  <th style={{ padding: '8px 6px' }}>Unrealized P&L</th>
                  <th style={{ padding: '8px 6px', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const isPos = p.unrealized_pnl >= 0;
                  return (
                    <tr key={p.symbol} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                      <td style={{ padding: '10px 6px', fontWeight: '700', color: '#f8fafc' }}>
                        {p.symbol.replace('.NS', '')}
                      </td>
                      <td className="mono-num" style={{ padding: '10px 6px', color: '#94a3b8' }}>
                        {p.quantity}
                      </td>
                      <td className="mono-num" style={{ padding: '10px 6px', color: '#94a3b8' }}>
                        ₹{p.entry_price.toFixed(2)}
                      </td>
                      <td className="mono-num" style={{ padding: '10px 6px', color: '#f8fafc', fontWeight: '600' }}>
                        ₹{p.current_price.toFixed(2)}
                      </td>
                      <td className="mono-num" style={{
                        padding: '10px 6px',
                        fontWeight: '700',
                        color: isPos ? 'var(--emerald-400)' : 'var(--rose-400)'
                      }}>
                        {isPos ? '+' : ''}₹{p.unrealized_pnl.toFixed(2)} ({isPos ? '+' : ''}{p.unrealized_pnl_pct.toFixed(1)}%)
                      </td>
                      <td style={{ padding: '10px 6px', textAlign: 'right' }}>
                        <button
                          onClick={() => onSquareOff(p.symbol, p.quantity)}
                          className="btn btn-sell"
                          style={{ padding: '4px 8px', fontSize: '10px', height: '24px' }}
                          title="Instant auto-square off this position"
                        >
                          <LogOut size={12} />
                          <span>Square Off</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 2. Order Audit Book */}
      <div className="glass-panel" style={{ padding: '20px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '14px',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '10px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '15px', fontWeight: '800', color: '#f8fafc' }}>
            <ListOrdered size={16} color="#06b6d4" />
            <span>SEBI Order Audit Book ({orders.length})</span>
          </div>
          <span className="badge badge-cyan" style={{ fontSize: '10px' }}>
            IDEMPOTENT AUDIT
          </span>
        </div>

        {orders.length === 0 ? (
          <div style={{ padding: '36px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No simulated orders recorded in this session.
          </div>
        ) : (
          <div style={{ overflowX: 'auto', maxHeight: '280px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <th style={{ padding: '6px' }}>Order ID</th>
                  <th style={{ padding: '6px' }}>Side</th>
                  <th style={{ padding: '6px' }}>Symbol</th>
                  <th style={{ padding: '6px' }}>Qty</th>
                  <th style={{ padding: '6px' }}>Price</th>
                  <th style={{ padding: '6px' }}>Status</th>
                  <th style={{ padding: '6px', textAlign: 'right' }}>Time</th>
                </tr>
              </thead>
              <tbody>
                {orders.slice(0, 15).map((o) => (
                  <tr key={o.client_order_id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.03)' }}>
                    <td className="mono-num" style={{ padding: '8px 6px', color: 'var(--text-dim)' }}>
                      {o.client_order_id}
                    </td>
                    <td style={{ padding: '8px 6px' }}>
                      <span className={`badge ${o.action === 'BUY' ? 'badge-emerald' : 'badge-rose'}`} style={{ padding: '1px 5px', fontSize: '9px' }}>
                        {o.action}
                      </span>
                    </td>
                    <td style={{ padding: '8px 6px', fontWeight: '700', color: '#f8fafc' }}>
                      {o.symbol.replace('.NS', '')}
                    </td>
                    <td className="mono-num" style={{ padding: '8px 6px', color: '#94a3b8' }}>
                      {o.quantity}
                    </td>
                    <td className="mono-num" style={{ padding: '8px 6px', color: '#f8fafc' }}>
                      ₹{o.price?.toFixed(2)}
                    </td>
                    <td style={{ padding: '8px 6px' }}>
                      <span style={{ color: 'var(--emerald-400)', fontWeight: '700', fontSize: '10px' }}>
                        {o.status}
                      </span>
                    </td>
                    <td className="mono-num" style={{ padding: '8px 6px', textAlign: 'right', color: 'var(--text-dim)' }}>
                      {new Date(o.timestamp).toLocaleTimeString('en-IN', { hour12: false })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
