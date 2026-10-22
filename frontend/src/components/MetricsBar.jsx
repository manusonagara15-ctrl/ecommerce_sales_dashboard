import React from 'react';
import { 
  Wallet, 
  TrendingUp, 
  TrendingDown, 
  ShieldAlert, 
  PieChart, 
  RotateCcw 
} from 'lucide-react';

export default function MetricsBar({ portfolio, onResetAccount }) {
  if (!portfolio) return null;

  const initialCash = portfolio.initial_margin || 50000.0;
  const equity = portfolio.equity || 50000.0;
  const availableCash = portfolio.available_cash || portfolio.cash || 50000.0;
  const grossExposure = portfolio.gross_exposure || 0.0;
  const realizedPnl = portfolio.realized_pnl || 0.0;
  const unrealizedPnl = portfolio.unrealized_pnl || 0.0;
  const totalPnl = portfolio.total_pnl || (realizedPnl + unrealizedPnl);
  const returnPct = portfolio.return_pct || 0.0;

  const isProfitable = totalPnl >= 0;
  const maxExposureLimit = 15000.0;
  const exposurePct = Math.min(100, Math.round((grossExposure / maxExposureLimit) * 100));

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
      gap: '16px',
      marginBottom: '24px'
    }}>
      {/* 1. Total Portfolio Equity */}
      <div className="glass-panel" style={{ padding: '20px', position: 'relative', overflow: 'hidden' }}>
        <div style={{
          position: 'absolute',
          top: '-20px',
          right: '-20px',
          width: '80px',
          height: '80px',
          borderRadius: '50%',
          background: isProfitable ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
          filter: 'blur(20px)',
          zIndex: 0
        }} />

        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)' }}>
              PORTFOLIO EQUITY
            </span>
            <div style={{
              width: '28px',
              height: '28px',
              borderRadius: '6px',
              background: 'rgba(56, 189, 248, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#38bdf8'
            }}>
              <Wallet size={16} />
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }}>
            <span className="mono-num" style={{ fontSize: '24px', fontWeight: '800', color: '#f8fafc' }}>
              ₹{equity.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
            <span className={`badge ${isProfitable ? 'badge-emerald' : 'badge-rose'}`} style={{ padding: '2px 6px', fontSize: '10px' }}>
              {isProfitable ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
              {isProfitable ? '+' : ''}{totalPnl.toFixed(2)} ({returnPct >= 0 ? '+' : ''}{returnPct.toFixed(2)}%)
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>vs ₹50k base</span>
          </div>
        </div>
      </div>

      {/* 2. Available Cash & Margin */}
      <div className="glass-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)' }}>
            AVAILABLE MARGIN (CASH)
          </span>
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: 'rgba(16, 185, 129, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--emerald-400)'
          }}>
            <PieChart size={16} />
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }}>
          <span className="mono-num" style={{ fontSize: '24px', fontWeight: '800', color: 'var(--emerald-400)' }}>
            ₹{availableCash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)' }}>
          <span>Free Trading Balance</span>
          <button 
            onClick={onResetAccount}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#38bdf8',
              fontSize: '11px',
              fontWeight: '600',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 6px',
              borderRadius: '4px'
            }}
            title="Reset paper simulation balance back to ₹50,000"
          >
            <RotateCcw size={11} /> Reset Margin
          </button>
        </div>
      </div>

      {/* 3. Gross Exposure vs Risk Limit */}
      <div className="glass-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)' }}>
            PORTFOLIO EXPOSURE
          </span>
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: exposurePct > 80 ? 'rgba(244, 63, 94, 0.1)' : 'rgba(245, 158, 11, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: exposurePct > 80 ? 'var(--rose-400)' : 'var(--amber-500)'
          }}>
            <ShieldAlert size={16} />
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '8px' }}>
          <span className="mono-num" style={{ fontSize: '24px', fontWeight: '800', color: '#f8fafc' }}>
            ₹{grossExposure.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
            / ₹15,000 max
          </span>
        </div>

        {/* Progress Bar */}
        <div style={{
          width: '100%',
          height: '6px',
          background: 'rgba(255, 255, 255, 0.08)',
          borderRadius: '3px',
          overflow: 'hidden',
          marginBottom: '6px'
        }}>
          <div style={{
            width: `${exposurePct}%`,
            height: '100%',
            background: exposurePct > 80 
              ? 'linear-gradient(90deg, #f59e0b, #f43f5e)' 
              : 'linear-gradient(90deg, #06b6d4, #10b981)',
            borderRadius: '3px',
            transition: 'width 0.4s ease'
          }} />
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)' }}>
          <span>{exposurePct}% Allocated</span>
          <span>{Object.keys(portfolio.positions || {}).length} / 3 Positions</span>
        </div>
      </div>

      {/* 4. Realized vs Unrealized P&L */}
      <div className="glass-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)' }}>
            P&L BREAKDOWN
          </span>
          <span className="badge badge-cyan" style={{ fontSize: '10px' }}>
            INTRADAY
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '4px' }}>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '2px' }}>Unrealized</div>
            <div className="mono-num" style={{
              fontSize: '17px',
              fontWeight: '700',
              color: unrealizedPnl >= 0 ? 'var(--emerald-400)' : 'var(--rose-400)'
            }}>
              {unrealizedPnl >= 0 ? '+' : ''}₹{unrealizedPnl.toFixed(2)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '2px' }}>Realized (Closed)</div>
            <div className="mono-num" style={{
              fontSize: '17px',
              fontWeight: '700',
              color: realizedPnl >= 0 ? 'var(--emerald-400)' : 'var(--rose-400)'
            }}>
              {realizedPnl >= 0 ? '+' : ''}₹{realizedPnl.toFixed(2)}
            </div>
          </div>
        </div>

        <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-dim)', borderTop: '1px solid var(--border-subtle)', paddingTop: '6px' }}>
          All STT, Exchange & GST fees deducted
        </div>
      </div>
    </div>
  );
}
