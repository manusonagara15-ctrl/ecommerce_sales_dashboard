import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  AlertTriangle, 
  Clock, 
  Activity, 
  Settings, 
  User, 
  RefreshCw,
  Power
} from 'lucide-react';

export default function Navbar({ 
  botStatus, 
  userProfile, 
  onToggleKillSwitch, 
  onOpenBrokerModal,
  onRefresh
}) {
  const [istTime, setIstTime] = useState('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setIstTime(now.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }));
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const isKillSwitchActive = botStatus?.kill_switch_active;
  const activeBroker = botStatus?.active_broker || 'GROWW';

  return (
    <header style={{
      background: 'rgba(10, 15, 26, 0.85)',
      backdropFilter: 'blur(16px)',
      borderBottom: '1px solid var(--border-subtle)',
      padding: '12px 24px',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      <div style={{
        maxWidth: '1440px',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        {/* Brand & Mode */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '38px',
            height: '38px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #06b6d4, #3b82f6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 14px rgba(6, 182, 212, 0.35)',
            fontSize: '20px'
          }}>
            📈
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '17px', fontWeight: '800', letterSpacing: '-0.02em', color: '#f8fafc' }}>
                AlgoTrader <span style={{ color: '#38bdf8' }}>India</span>
              </span>
              <span className="badge badge-cyan" style={{ fontSize: '10px' }}>
                TERMINAL v2.5
              </span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span className={`pulse-dot ${isKillSwitchActive ? 'pulse-rose' : 'pulse-emerald'}`} />
                {isKillSwitchActive ? 'SAFETY LOCK ENGAGED' : 'LIVE PAPER ENGINE'}
              </span>
              <span>•</span>
              <span>NSE / NIFTY 50</span>
              <span>•</span>
              <span style={{ color: 'var(--emerald-400)', display: 'flex', alignItems: 'center', gap: '3px' }}>
                <ShieldCheck size={12} /> SEBI RISK LOCK ACTIVE
              </span>
            </div>
          </div>
        </div>

        {/* Right Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          {/* Market Clock */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid var(--border-subtle)',
            fontSize: '12px',
            color: 'var(--text-secondary)'
          }}>
            <Clock size={14} color="#06b6d4" />
            <span className="mono-num" style={{ fontWeight: '600', color: '#f8fafc' }}>{istTime}</span>
            <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>IST</span>
          </div>

          {/* Broker Badge */}
          <div 
            onClick={onOpenBrokerModal}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '8px',
              background: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.25)',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: '600',
              color: '#60a5fa'
            }}
            title="Click to configure broker & SEBI credentials"
          >
            <Activity size={14} />
            <span>{activeBroker}</span>
            <Settings size={12} style={{ opacity: 0.6 }} />
          </div>

          {/* Kill Switch Toggle */}
          <button
            onClick={onToggleKillSwitch}
            className={`btn ${isKillSwitchActive ? 'btn-primary' : 'btn-danger'}`}
            style={{ padding: '6px 14px', fontSize: '12px' }}
          >
            <Power size={14} />
            <span>{isKillSwitchActive ? 'Reset Safety Lock' : 'Kill Switch'}</span>
          </button>

          {/* Refresh Data */}
          <button
            onClick={onRefresh}
            className="btn btn-outline"
            style={{ padding: '6px 10px' }}
            title="Refresh Quotes & Portfolio Data"
          >
            <RefreshCw size={14} />
          </button>

          {/* User Profile */}
          <div 
            onClick={onOpenBrokerModal}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '5px 10px',
              borderRadius: '8px',
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px solid var(--border-subtle)',
              cursor: 'pointer'
            }}
          >
            <div style={{
              width: '26px',
              height: '26px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: '700'
            }}>
              {(userProfile?.name || 'M')[0]}
            </div>
            <span style={{ fontSize: '12px', fontWeight: '600', color: '#e2e8f0' }}>
              {(userProfile?.name || 'Trader').split(' ')[0]}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
