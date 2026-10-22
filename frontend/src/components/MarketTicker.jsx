import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

export default function MarketTicker({ marketQuotes, selectedSymbol, onSelectSymbol }) {
  // Enhanced list including market indices simulation
  const indices = [
    { symbol: 'NIFTY 50', price: 25482.35, change: 114.20, change_pct: 0.45, isIndex: true },
    { symbol: 'SENSEX', price: 83240.10, change: 382.40, change_pct: 0.46, isIndex: true }
  ];

  const fullQuotes = [...indices, ...(marketQuotes || [])];
  // Duplicate for seamless infinite loop marquee
  const loopList = [...fullQuotes, ...fullQuotes];

  return (
    <div style={{
      background: 'rgba(11, 16, 28, 0.95)',
      borderBottom: '1px solid var(--border-subtle)',
      padding: '8px 0',
      overflow: 'hidden'
    }}>
      <div className="ticker-marquee">
        <div className="ticker-track">
          {loopList.map((item, idx) => {
            const isSelected = item.symbol === selectedSymbol;
            const isPos = item.change >= 0;

            return (
              <div
                key={`${item.symbol}-${idx}`}
                onClick={() => !item.isIndex && onSelectSymbol(item.symbol)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '4px 12px',
                  borderRadius: '6px',
                  background: isSelected ? 'rgba(56, 189, 248, 0.12)' : 'transparent',
                  border: isSelected ? '1px solid rgba(56, 189, 248, 0.3)' : '1px solid transparent',
                  cursor: item.isIndex ? 'default' : 'pointer',
                  transition: 'background 0.15s ease'
                }}
              >
                <span style={{
                  fontSize: '12px',
                  fontWeight: '700',
                  color: isSelected ? '#38bdf8' : '#e2e8f0'
                }}>
                  {item.symbol.replace('.NS', '')}
                </span>

                <span className="mono-num" style={{ fontSize: '12px', color: '#f8fafc', fontWeight: '600' }}>
                  ₹{item.price.toFixed(2)}
                </span>

                <span style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '3px',
                  fontSize: '11px',
                  fontWeight: '700',
                  color: isPos ? 'var(--emerald-400)' : 'var(--rose-400)'
                }}>
                  {isPos ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                  <span>{isPos ? '+' : ''}{item.change_pct.toFixed(2)}%</span>
                </span>

                {item.signal && (
                  <span className={`badge ${
                    item.signal === 'BUY' ? 'badge-emerald' : 
                    item.signal === 'EXIT' ? 'badge-rose' : 'badge-cyan'
                  }`} style={{ fontSize: '9px', padding: '1px 6px' }}>
                    {item.signal}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
