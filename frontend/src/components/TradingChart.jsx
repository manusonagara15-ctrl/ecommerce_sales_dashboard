import React, { useState, useMemo } from 'react';
import { BarChart3, LineChart, Layers, Calendar, Zap } from 'lucide-react';

export default function TradingChart({ chartData, selectedSymbol, onSelectSymbol }) {
  const [timeframe, setTimeframe] = useState(60); // 30, 60, 90, 180 days
  const [hoverCandle, setHoverCandle] = useState(null);

  const symbols = ['SBIN.NS', 'ITC.NS', 'INFY.NS', 'ICICIBANK.NS', 'RELIANCE.NS'];

  const visibleCandles = useMemo(() => {
    if (!chartData?.candles) return [];
    return chartData.candles.slice(-timeframe);
  }, [chartData, timeframe]);

  // Dimensions & Scale Calculations
  const { minPrice, maxPrice, maxVolume, pointsSMA20, pointsSMA50 } = useMemo(() => {
    if (visibleCandles.length === 0) {
      return { minPrice: 0, maxPrice: 100, maxVolume: 100, pointsSMA20: '', pointsSMA50: '' };
    }

    let min = Infinity;
    let max = -Infinity;
    let maxVol = 0;

    visibleCandles.forEach(c => {
      if (c.low < min) min = c.low;
      if (c.high > max) max = c.high;
      if (c.volume > maxVol) maxVol = c.volume;
    });

    // Add 5% padding
    const pad = (max - min) * 0.05 || 10;
    min = Math.max(0, min - pad);
    max = max + pad;

    const width = 860;
    const height = 240;
    const step = width / (visibleCandles.length || 1);

    const pts20 = [];
    const pts50 = [];

    visibleCandles.forEach((c, i) => {
      const x = i * step + step / 2;
      if (c.sma20) {
        const y = height - ((c.sma20 - min) / (max - min)) * height;
        pts20.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
      if (c.sma50) {
        const y = height - ((c.sma50 - min) / (max - min)) * height;
        pts50.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
    });

    return {
      minPrice: min,
      maxPrice: max,
      maxVolume: maxVol,
      pointsSMA20: pts20.join(' '),
      pointsSMA50: pts50.join(' ')
    };
  }, [visibleCandles]);

  const width = 860;
  const height = 240;
  const step = width / (visibleCandles.length || 1);
  const activeCandle = hoverCandle || (visibleCandles.length > 0 ? visibleCandles[visibleCandles.length - 1] : null);

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top Header: Symbols & Timeframes */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        marginBottom: '16px',
        borderBottom: '1px solid var(--border-subtle)',
        paddingBottom: '14px'
      }}>
        {/* Symbol Tabs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          {symbols.map(sym => {
            const isSelected = sym === selectedSymbol;
            return (
              <button
                key={sym}
                onClick={() => onSelectSymbol(sym)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: isSelected ? '1px solid #38bdf8' : '1px solid var(--border-subtle)',
                  background: isSelected ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  color: isSelected ? '#38bdf8' : 'var(--text-secondary)',
                  fontSize: '12px',
                  fontWeight: '700',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
              >
                {sym.replace('.NS', '')}
              </button>
            );
          })}
        </div>

        {/* Timeframe Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          {[
            { label: '1M', days: 30 },
            { label: '3M', days: 60 },
            { label: '6M', days: 90 },
            { label: '1Y', days: 180 }
          ].map(tf => (
            <button
              key={tf.label}
              onClick={() => setTimeframe(tf.days)}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                border: 'none',
                background: timeframe === tf.days ? 'rgba(255, 255, 255, 0.12)' : 'transparent',
                color: timeframe === tf.days ? '#f8fafc' : 'var(--text-muted)',
                fontSize: '11px',
                fontWeight: '600',
                cursor: 'pointer'
              }}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {/* Dynamic Candle Stats Bar */}
      {activeCandle && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          fontSize: '12px',
          color: 'var(--text-secondary)',
          marginBottom: '14px',
          flexWrap: 'wrap'
        }}>
          <span style={{ color: '#f8fafc', fontWeight: '700' }}>
            {activeCandle.date}
          </span>
          <span>O: <strong className="mono-num" style={{ color: '#e2e8f0' }}>₹{activeCandle.open?.toFixed(2)}</strong></span>
          <span>H: <strong className="mono-num" style={{ color: 'var(--emerald-400)' }}>₹{activeCandle.high?.toFixed(2)}</strong></span>
          <span>L: <strong className="mono-num" style={{ color: 'var(--rose-400)' }}>₹{activeCandle.low?.toFixed(2)}</strong></span>
          <span>C: <strong className="mono-num" style={{ color: activeCandle.close >= activeCandle.open ? 'var(--emerald-400)' : 'var(--rose-400)' }}>
            ₹{activeCandle.close?.toFixed(2)}
          </strong></span>

          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#06b6d4' }} />
            SMA 20: <strong className="mono-num" style={{ color: '#06b6d4' }}>₹{activeCandle.sma20?.toFixed(2) || '—'}</strong>
          </span>

          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#8b5cf6' }} />
            SMA 50: <strong className="mono-num" style={{ color: '#8b5cf6' }}>₹{activeCandle.sma50?.toFixed(2) || '—'}</strong>
          </span>

          {activeCandle.signal && (
            <span className={`badge ${
              activeCandle.signal === 'BUY' ? 'badge-emerald' : 
              activeCandle.signal === 'EXIT' ? 'badge-rose' : 'badge-cyan'
            }`} style={{ marginLeft: 'auto', fontSize: '10px' }}>
              <Zap size={11} /> {activeCandle.signal} SIGNAL
            </span>
          )}
        </div>
      )}

      {/* SVG Candlestick & Volume Chart */}
      <div style={{ position: 'relative', width: '100%', flex: 1, minHeight: '300px' }}>
        <svg
          viewBox={`0 0 ${width} 310`}
          style={{ width: '100%', height: '100%', overflow: 'visible', userSelect: 'none' }}
          onMouseLeave={() => setHoverCandle(null)}
        >
          {/* Horizontal Gridlines */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((frac, idx) => {
            const y = height * (1 - frac);
            const val = minPrice + (maxPrice - minPrice) * frac;
            return (
              <g key={idx}>
                <line x1="0" y1={y} x2={width} y2={y} stroke="rgba(255, 255, 255, 0.05)" strokeDasharray="3 3" />
                <text x={width - 5} y={y - 4} textAnchor="end" fill="var(--text-dim)" fontSize="10" fontFamily="var(--font-mono)">
                  ₹{val.toFixed(1)}
                </text>
              </g>
            );
          })}

          {/* Volume Separator */}
          <line x1="0" y1="245" x2={width} y2="245" stroke="rgba(255, 255, 255, 0.08)" />

          {/* Candlesticks & Volume Bars */}
          {visibleCandles.map((c, i) => {
            const isGreen = c.close >= c.open;
            const color = isGreen ? '#10b981' : '#f43f5e';
            const x = i * step + step / 2;
            const barWidth = Math.max(2, step * 0.7);

            // Price Y coords
            const yHigh = height - ((c.high - minPrice) / (maxPrice - minPrice)) * height;
            const yLow = height - ((c.low - minPrice) / (maxPrice - minPrice)) * height;
            const yOpen = height - ((c.open - minPrice) / (maxPrice - minPrice)) * height;
            const yClose = height - ((c.close - minPrice) / (maxPrice - minPrice)) * height;
            const bodyTop = Math.min(yOpen, yClose);
            const bodyHeight = Math.max(2, Math.abs(yOpen - yClose));

            // Volume bar Y coords (height 55px from 250 to 305)
            const volHeight = maxVolume > 0 ? (c.volume / maxVolume) * 50 : 0;
            const volY = 305 - volHeight;

            return (
              <g 
                key={c.date || i} 
                onMouseEnter={() => setHoverCandle(c)}
                style={{ cursor: 'crosshair' }}
              >
                {/* Wick */}
                <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth="1.2" opacity="0.8" />
                {/* Body */}
                <rect
                  x={x - barWidth / 2}
                  y={bodyTop}
                  width={barWidth}
                  height={bodyHeight}
                  fill={color}
                  rx="1"
                />
                {/* Volume bar */}
                <rect
                  x={x - barWidth / 2}
                  y={volY}
                  width={barWidth}
                  height={volHeight}
                  fill={color}
                  opacity="0.35"
                />
              </g>
            );
          })}

          {/* SMA 20 Overlay Line */}
          {pointsSMA20 && (
            <polyline
              points={pointsSMA20}
              fill="none"
              stroke="#06b6d4"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.9"
            />
          )}

          {/* SMA 50 Overlay Line */}
          {pointsSMA50 && (
            <polyline
              points={pointsSMA50}
              fill="none"
              stroke="#8b5cf6"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.9"
            />
          )}
        </svg>
      </div>

      {/* Chart Footer Legend */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginTop: '10px',
        fontSize: '11px',
        color: 'var(--text-dim)',
        borderTop: '1px solid var(--border-subtle)',
        paddingTop: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '12px', height: '2px', background: '#06b6d4' }} /> 20-Day SMA
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '12px', height: '2px', background: '#8b5cf6' }} /> 50-Day SMA
          </span>
          <span>Volume (Daily)</span>
        </div>
        <span>Look-ahead bias free closed daily bars</span>
      </div>
    </div>
  );
}
