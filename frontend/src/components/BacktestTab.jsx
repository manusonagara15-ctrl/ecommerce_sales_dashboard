import React, { useState, useEffect } from 'react';
import { 
  BarChart2, 
  ShieldCheck, 
  CheckCircle2, 
  Percent, 
  Activity, 
  Award,
  Layers,
  ArrowRight
} from 'lucide-react';

export default function BacktestTab({ selectedSymbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/backtest?symbol=${selectedSymbol}`)
      .then((res) => res.json())
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Backtest error:', err);
        setLoading(false);
      });
  }, [selectedSymbol]);

  if (loading) {
    return (
      <div className="glass-panel" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <div className="pulse-dot pulse-emerald" style={{ margin: '0 auto 12px' }} />
        <div>Running 3-Phase Chronological Backtesting Engine on <strong>{selectedSymbol}</strong>...</div>
      </div>
    );
  }

  if (!data || data.error) {
    return (
      <div className="glass-panel" style={{ padding: '30px', textAlign: 'center', color: 'var(--rose-400)' }}>
        Unable to calculate backtest metrics for {selectedSymbol}.
      </div>
    );
  }

  const { train, validation, test } = data;

  const phases = [
    { title: 'Phase 1: In-Sample Train (60%)', badge: 'IN-SAMPLE', color: '#06b6d4', metrics: train },
    { title: 'Phase 2: Out-of-Sample Validation (20%)', badge: 'VERIFIED', color: '#8b5cf6', metrics: validation },
    { title: 'Phase 3: Blind Holdout Test (20%)', badge: 'BLIND TEST', color: '#10b981', metrics: test }
  ];

  return (
    <div className="glass-panel" style={{ padding: '24px' }}>
      {/* Tab Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '20px',
        flexWrap: 'wrap',
        gap: '12px',
        borderBottom: '1px solid var(--border-subtle)',
        paddingBottom: '14px'
      }}>
        <div>
          <div style={{ fontSize: '16px', fontWeight: '800', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart2 size={18} color="#06b6d4" />
            <span>3-Phase Chronological Backtesting Audit: {selectedSymbol}</span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Strategy: <strong>20/50 Day SMA Crossover</strong> with Full Indian Cost Model (Brokerage ₹20, STT 0.1%, Stamp Duty & 18% GST)
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="badge badge-emerald">
            <ShieldCheck size={12} /> ZERO LOOK-AHEAD BIAS
          </span>
          <span className="badge badge-cyan">
            HOLDOUT VERIFIED
          </span>
        </div>
      </div>

      {/* 3-Phase Cards Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '16px',
        marginBottom: '24px'
      }}>
        {phases.map((p, idx) => {
          const m = p.metrics || {};
          const isPos = m.total_return_pct >= 0;

          return (
            <div
              key={p.title}
              style={{
                background: 'rgba(11, 16, 28, 0.7)',
                borderRadius: '12px',
                padding: '18px',
                border: `1px solid ${idx === 2 ? 'rgba(16, 185, 129, 0.35)' : 'var(--border-subtle)'}`,
                boxShadow: idx === 2 ? '0 0 20px rgba(16, 185, 129, 0.1)' : 'none'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <span style={{ fontSize: '13px', fontWeight: '700', color: '#f8fafc' }}>
                  {p.title}
                </span>
                <span className="badge" style={{
                  background: `${p.color}20`,
                  color: p.color,
                  border: `1px solid ${p.color}40`,
                  fontSize: '10px'
                }}>
                  {p.badge}
                </span>
              </div>

              {/* Net Return */}
              <div style={{ marginBottom: '14px' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Net Strategy Return</div>
                <div className="mono-num" style={{
                  fontSize: '26px',
                  fontWeight: '800',
                  color: isPos ? 'var(--emerald-400)' : 'var(--rose-400)'
                }}>
                  {isPos ? '+' : ''}{m.total_return_pct?.toFixed(2)}%
                </div>
              </div>

              {/* Metrics Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '11px' }}>
                <div>
                  <div style={{ color: 'var(--text-muted)' }}>Win Rate</div>
                  <div className="mono-num" style={{ fontWeight: '700', color: '#f8fafc', fontSize: '13px' }}>
                    {m.win_rate_pct?.toFixed(1)}%
                  </div>
                </div>

                <div>
                  <div style={{ color: 'var(--text-muted)' }}>Max Drawdown</div>
                  <div className="mono-num" style={{ fontWeight: '700', color: 'var(--rose-400)', fontSize: '13px' }}>
                    -{m.max_drawdown_pct?.toFixed(1)}%
                  </div>
                </div>

                <div>
                  <div style={{ color: 'var(--text-muted)' }}>Sharpe Ratio</div>
                  <div className="mono-num" style={{ fontWeight: '700', color: '#38bdf8', fontSize: '13px' }}>
                    {m.sharpe_ratio?.toFixed(2)}
                  </div>
                </div>

                <div>
                  <div style={{ color: 'var(--text-muted)' }}>Profit Factor</div>
                  <div className="mono-num" style={{ fontWeight: '700', color: '#f8fafc', fontSize: '13px' }}>
                    {m.profit_factor?.toFixed(2)}
                  </div>
                </div>

                <div>
                  <div style={{ color: 'var(--text-muted)' }}>Total Trades</div>
                  <div className="mono-num" style={{ fontWeight: '700', color: '#94a3b8', fontSize: '13px' }}>
                    {m.total_trades}
                  </div>
                </div>

                <div>
                  <div style={{ color: 'var(--text-muted)' }}>Fees Deducted</div>
                  <div className="mono-num" style={{ fontWeight: '700', color: 'var(--amber-500)', fontSize: '13px' }}>
                    ₹{m.cost_deductions_inr?.toFixed(2)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Regulatory Cost Model Notice */}
      <div style={{
        background: 'rgba(56, 189, 248, 0.05)',
        border: '1px solid rgba(56, 189, 248, 0.2)',
        borderRadius: '8px',
        padding: '12px 16px',
        fontSize: '12px',
        color: 'var(--text-secondary)',
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }}>
        <Award size={18} color="#38bdf8" />
        <div>
          <strong style={{ color: '#f8fafc' }}>Realistic Indian Equity Cash Model:</strong> Every trade deducts flat ₹20 brokerage, 0.1% STT on Buy & Sell, 0.00345% NSE turnover fee, ₹10/Cr SEBI turnover charge, 0.015% State Stamp Duty, 18% GST on brokerage + turnover fees, and 0.05% realistic market entry/exit slippage.
        </div>
      </div>
    </div>
  );
}
