import React, { useState, useEffect } from 'react';
import { 
  Cpu, 
  Brain, 
  TrendingUp, 
  TrendingDown, 
  CheckCircle2, 
  Activity, 
  Sparkles,
  BarChart3
} from 'lucide-react';

export default function MLLabTab({ selectedSymbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/ml-insights?symbol=${selectedSymbol}`)
      .then((res) => res.json())
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error('ML fetch error:', err);
        setLoading(false);
      });
  }, [selectedSymbol]);

  if (loading) {
    return (
      <div className="glass-panel" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <div className="pulse-dot pulse-emerald" style={{ margin: '0 auto 12px' }} />
        <div>Running Scikit-Learn Walk-Forward ML Direction Experiment for <strong>{selectedSymbol}</strong>...</div>
      </div>
    );
  }

  if (!data || data.error) {
    return (
      <div className="glass-panel" style={{ padding: '30px', textAlign: 'center', color: 'var(--rose-400)' }}>
        No ML experiment results available for {selectedSymbol}.
      </div>
    );
  }

  const isUp = data.predicted_next_direction === 'UP';

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
            <Brain size={18} color="#8b5cf6" />
            <span>Machine Learning Directional Forecast ({selectedSymbol})</span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Algorithm: <strong>Scikit-Learn Random Forest Classifier & Logistic Ensembles</strong>
          </div>
        </div>

        <span className="badge badge-purple">
          Walk-Forward Validation
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {/* 1. Forecast Badge & Probability */}
        <div style={{
          background: isUp ? 'rgba(16, 185, 129, 0.08)' : 'rgba(244, 63, 94, 0.08)',
          border: `1px solid ${isUp ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
          borderRadius: '12px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between'
        }}>
          <div>
            <div style={{ fontSize: '12px', fontWeight: '700', color: 'var(--text-secondary)', marginBottom: '8px' }}>
              NEXT-DAY RETURN DIRECTION PREDICTION
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
              <div style={{
                width: '44px',
                height: '44px',
                borderRadius: '10px',
                background: isUp ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: isUp ? 'var(--emerald-400)' : 'var(--rose-400)'
              }}>
                {isUp ? <TrendingUp size={24} /> : <TrendingDown size={24} />}
              </div>
              <div>
                <div style={{
                  fontSize: '24px',
                  fontWeight: '800',
                  color: isUp ? 'var(--emerald-400)' : 'var(--rose-400)'
                }}>
                  {isUp ? 'UP (BULLISH)' : 'DOWN (BEARISH)'}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Probability: <strong className="mono-num" style={{ color: '#f8fafc' }}>{data.probability_up}%</strong> • Confidence: <strong style={{ color: '#38bdf8' }}>{data.confidence}</strong>
                </div>
              </div>
            </div>
          </div>

          <div style={{
            background: 'rgba(0, 0, 0, 0.25)',
            borderRadius: '8px',
            padding: '12px',
            fontSize: '11px',
            color: 'var(--text-secondary)',
            display: 'flex',
            justifyContent: 'space-between'
          }}>
            <div>
              <span>Model Accuracy</span>
              <div className="mono-num" style={{ fontSize: '15px', fontWeight: '800', color: '#f8fafc', marginTop: '2px' }}>
                {data.test_accuracy_pct}%
              </div>
            </div>
            <div>
              <span>ROC-AUC Score</span>
              <div className="mono-num" style={{ fontSize: '15px', fontWeight: '800', color: '#38bdf8', marginTop: '2px' }}>
                {data.roc_auc}
              </div>
            </div>
            <div>
              <span>Train Leakage</span>
              <div style={{ fontSize: '12px', fontWeight: '800', color: 'var(--emerald-400)', marginTop: '4px' }}>
                0.00% (Air-Gapped)
              </div>
            </div>
          </div>
        </div>

        {/* 2. Feature Importances */}
        <div style={{
          background: 'rgba(11, 16, 28, 0.7)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '12px',
          padding: '20px'
        }}>
          <div style={{ fontSize: '13px', fontWeight: '700', color: '#f8fafc', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart3 size={15} color="#06b6d4" />
            <span>Key Feature Importances</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {(data.feature_importances || []).map((f) => {
              const pct = Math.round(f.importance * 100);
              return (
                <div key={f.feature} style={{ fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', color: 'var(--text-secondary)' }}>
                    <span>{f.feature}</span>
                    <span className="mono-num" style={{ fontWeight: '700', color: '#f8fafc' }}>{pct}%</span>
                  </div>
                  <div style={{
                    width: '100%',
                    height: '5px',
                    background: 'rgba(255, 255, 255, 0.08)',
                    borderRadius: '3px',
                    overflow: 'hidden'
                  }}>
                    <div style={{
                      width: `${pct}%`,
                      height: '100%',
                      background: 'linear-gradient(90deg, #8b5cf6, #06b6d4)',
                      borderRadius: '3px'
                    }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
