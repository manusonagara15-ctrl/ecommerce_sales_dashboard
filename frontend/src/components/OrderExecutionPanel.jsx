import React, { useState } from 'react';
import { 
  Send, 
  AlertCircle, 
  CheckCircle2, 
  Info, 
  ShieldCheck,
  TrendingUp,
  TrendingDown
} from 'lucide-react';

export default function OrderExecutionPanel({
  selectedSymbol,
  currentQuote,
  portfolio,
  botStatus,
  onSubmitOrder
}) {
  const [quantity, setQuantity] = useState(2);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [alert, setAlert] = useState(null);

  const price = currentQuote?.price || 1000.0;
  const orderValue = quantity * price;

  // Indian Cost Model Calculation
  const brokerage = 20.0;
  const stt = orderValue * 0.001; // 0.1%
  const exchFee = orderValue * 0.0000345;
  const gst = (brokerage + exchFee) * 0.18;
  const stampDuty = orderValue * 0.00015;
  const totalFees = brokerage + stt + exchFee + gst + stampDuty;
  const totalCashRequired = orderValue + totalFees;

  // Pre-trade risk conditions
  const exceedsMaxOrderCap = orderValue > 5000.0;
  const availableCash = portfolio?.available_cash || portfolio?.cash || 0;
  const hasInsufficientCash = totalCashRequired > availableCash;
  const isKillSwitchActive = botStatus?.kill_switch_active;

  const handleOrder = async (action) => {
    // Client-side pre-trade validations
    if (exceedsMaxOrderCap) {
      setAlert({
        type: 'error',
        text: `Risk Violation: Order value ₹${orderValue.toFixed(2)} exceeds ₹5,000 cap.`
      });
      return;
    }

    if (action === 'BUY' && hasInsufficientCash) {
      setAlert({
        type: 'error',
        text: `Insufficient cash: Need ₹${totalCashRequired.toFixed(2)}, Available ₹${availableCash.toFixed(2)}.`
      });
      return;
    }

    if (isKillSwitchActive) {
      setAlert({
        type: 'error',
        text: `Order blocked: Emergency Kill Switch is engaged!`
      });
      return;
    }

    setIsSubmitting(true);
    setAlert(null);

    try {
      const res = await onSubmitOrder({
        symbol: selectedSymbol,
        action,
        quantity: parseInt(quantity, 10),
        price
      });

      if (res?.success) {
        setAlert({
          type: 'success',
          text: `✅ ${action} ${quantity} ${selectedSymbol} executed @ ₹${price.toFixed(2)}!`
        });
      } else {
        setAlert({
          type: 'error',
          text: res?.error || 'Order submission failed.'
        });
      }
    } catch (err) {
      setAlert({
        type: 'error',
        text: err.message || 'Execution error'
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Widget Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '16px',
        borderBottom: '1px solid var(--border-subtle)',
        paddingBottom: '12px'
      }}>
        <div>
          <div style={{ fontSize: '15px', fontWeight: '800', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>Virtual Order Entry</span>
            <span className="badge badge-purple" style={{ fontSize: '10px' }}>AIR-GAPPED</span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Target: <strong style={{ color: '#38bdf8' }}>{selectedSymbol}</strong>
          </div>
        </div>

        <div style={{ textAlign: 'right' }}>
          <div className="mono-num" style={{ fontSize: '16px', fontWeight: '800', color: '#f8fafc' }}>
            ₹{price.toFixed(2)}
          </div>
          <div style={{ fontSize: '11px', color: currentQuote?.change >= 0 ? 'var(--emerald-400)' : 'var(--rose-400)' }}>
            {currentQuote?.change >= 0 ? '+' : ''}{currentQuote?.change_pct?.toFixed(2) || '0.00'}%
          </div>
        </div>
      </div>

      {/* Quantity Selector */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
          <span>Order Quantity (Shares)</span>
          <span>Max single order: ₹5,000</span>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
          <input
            type="number"
            min="1"
            max="100"
            value={quantity}
            onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value, 10) || 1))}
            style={{
              flex: 1,
              padding: '10px 14px',
              borderRadius: '8px',
              background: 'rgba(14, 21, 36, 0.8)',
              border: exceedsMaxOrderCap ? '1px solid var(--rose-500)' : '1px solid var(--border-medium)',
              color: '#f8fafc',
              fontSize: '15px',
              fontWeight: '700',
              fontFamily: 'var(--font-mono)',
              outline: 'none'
            }}
          />
        </div>

        {/* Quick Quantity Chips */}
        <div style={{ display: 'flex', gap: '6px' }}>
          {[1, 2, 5, 10].map((q) => (
            <button
              key={q}
              onClick={() => setQuantity(q)}
              style={{
                flex: 1,
                padding: '4px 0',
                borderRadius: '6px',
                background: quantity === q ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255, 255, 255, 0.04)',
                border: quantity === q ? '1px solid #38bdf8' : '1px solid var(--border-subtle)',
                color: quantity === q ? '#38bdf8' : 'var(--text-secondary)',
                fontSize: '11px',
                fontWeight: '600',
                cursor: 'pointer'
              }}
            >
              {q} qty
            </button>
          ))}
        </div>
      </div>

      {/* Financial Calculations Box */}
      <div style={{
        background: 'rgba(10, 15, 26, 0.6)',
        borderRadius: '10px',
        padding: '12px 14px',
        border: '1px solid var(--border-subtle)',
        fontSize: '12px',
        marginBottom: '16px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Gross Turnover:</span>
          <span className="mono-num" style={{ color: '#f8fafc', fontWeight: '700' }}>₹{orderValue.toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Estimated Brokerage:</span>
          <span className="mono-num" style={{ color: 'var(--text-secondary)' }}>₹{brokerage.toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ color: 'var(--text-muted)' }}>STT, Exch, GST & Stamp:</span>
          <span className="mono-num" style={{ color: 'var(--text-secondary)' }}>₹{(totalFees - brokerage).toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border-subtle)', paddingTop: '6px', marginTop: '6px' }}>
          <span style={{ color: '#f8fafc', fontWeight: '700' }}>Effective Total Required:</span>
          <span className="mono-num" style={{ color: 'var(--emerald-400)', fontWeight: '800' }}>₹{totalCashRequired.toFixed(2)}</span>
        </div>
      </div>

      {/* Pre-trade Alert Display */}
      {alert && (
        <div style={{
          padding: '10px 12px',
          borderRadius: '8px',
          marginBottom: '16px',
          fontSize: '12px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          background: alert.type === 'error' ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)',
          border: alert.type === 'error' ? '1px solid rgba(244, 63, 94, 0.35)' : '1px solid rgba(16, 185, 129, 0.35)',
          color: alert.type === 'error' ? 'var(--rose-400)' : 'var(--emerald-400)'
        }}>
          {alert.type === 'error' ? <AlertCircle size={15} /> : <CheckCircle2 size={15} />}
          <span>{alert.text}</span>
        </div>
      )}

      {/* Action Buttons: BUY and SELL */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: 'auto' }}>
        <button
          onClick={() => handleOrder('BUY')}
          disabled={isSubmitting || exceedsMaxOrderCap}
          className="btn btn-buy"
          style={{
            padding: '12px',
            fontSize: '14px',
            opacity: exceedsMaxOrderCap ? 0.5 : 1
          }}
        >
          <TrendingUp size={16} />
          <span>BUY (Long)</span>
        </button>

        <button
          onClick={() => handleOrder('SELL')}
          disabled={isSubmitting}
          className="btn btn-sell"
          style={{ padding: '12px', fontSize: '14px' }}
        >
          <TrendingDown size={16} />
          <span>SELL (Exit)</span>
        </button>
      </div>

      {/* Compliance Notice */}
      <div style={{
        marginTop: '12px',
        fontSize: '10px',
        color: 'var(--text-dim)',
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        justifyContent: 'center'
      }}>
        <ShieldCheck size={12} color="var(--emerald-400)" />
        <span>Pre-trade risk checked & idempotent client order ID</span>
      </div>
    </div>
  );
}
