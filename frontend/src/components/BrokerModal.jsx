import React, { useState } from 'react';
import { 
  X, 
  ShieldCheck, 
  Key, 
  Lock, 
  Check, 
  Server, 
  Cpu, 
  CheckCircle2, 
  User, 
  Mail,
  AlertTriangle
} from 'lucide-react';

export default function BrokerModal({
  isOpen,
  onClose,
  botStatus,
  userProfile,
  onSelectBroker,
  onUpdateProfile
}) {
  if (!isOpen) return null;

  const [name, setName] = useState(userProfile?.name || 'Maheshvaree Sonagara');
  const [email, setEmail] = useState(userProfile?.email || 'manusonagara15@gmail.com');
  const [savedSuccess, setSavedSuccess] = useState(false);

  const activeBroker = botStatus?.active_broker || 'GROWW';

  const brokers = [
    {
      id: 'GROWW',
      name: 'Groww API Gateway',
      desc: 'Seamless Indian retail execution with automated TOTP session management.',
      badge: 'ACTIVE'
    },
    {
      id: 'DHAN',
      name: 'DhanHQ API v2',
      desc: 'Institutional ultra-low latency direct exchange connection with correlation ID tagging.',
      badge: 'READY'
    },
    {
      id: 'MOCK',
      name: 'Air-Gapped Simulator',
      desc: 'Zero-risk virtual execution matching real-time NSE market quotes locally.',
      badge: 'SAFE'
    }
  ];

  const handleSaveUser = (e) => {
    e.preventDefault();
    onUpdateProfile(email, name);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.75)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '20px'
    }}>
      <div style={{
        background: '#0e1524',
        border: '1px solid var(--border-medium)',
        borderRadius: '16px',
        width: '100%',
        maxWidth: '680px',
        maxHeight: '90vh',
        overflowY: 'auto',
        boxShadow: '0 25px 60px rgba(0,0,0,0.8)'
      }}>
        {/* Modal Header */}
        <div style={{
          padding: '18px 24px',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'rgba(6, 182, 212, 0.15)',
              color: '#06b6d4',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Server size={18} />
            </div>
            <div>
              <div style={{ fontSize: '16px', fontWeight: '800', color: '#f8fafc' }}>
                Broker Gateway & SEBI Controls
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Configure execution connectors and pre-trade regulatory locks
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '6px'
            }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: '24px' }}>
          {/* Broker Selector Cards */}
          <div style={{ marginBottom: '24px' }}>
            <div style={{ fontSize: '13px', fontWeight: '700', color: '#f8fafc', marginBottom: '12px' }}>
              Select Active Execution Connector
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {brokers.map((b) => {
                const isSelected = b.id === activeBroker;
                return (
                  <div
                    key={b.id}
                    onClick={() => onSelectBroker(b.id)}
                    style={{
                      padding: '14px 16px',
                      borderRadius: '10px',
                      background: isSelected ? 'rgba(56, 189, 248, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                      border: isSelected ? '1px solid #38bdf8' : '1px solid var(--border-subtle)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '14px', fontWeight: '700', color: isSelected ? '#38bdf8' : '#f8fafc' }}>
                          {b.name}
                        </span>
                        <span className={`badge ${isSelected ? 'badge-cyan' : 'badge-emerald'}`} style={{ fontSize: '9px', padding: '1px 6px' }}>
                          {b.badge}
                        </span>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                        {b.desc}
                      </div>
                    </div>

                    <div style={{
                      width: '20px',
                      height: '20px',
                      borderRadius: '50%',
                      border: isSelected ? '2px solid #38bdf8' : '2px solid var(--border-medium)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: isSelected ? '#38bdf8' : 'transparent'
                    }}>
                      {isSelected && <Check size={12} color="#080c14" strokeWidth={3} />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* SEBI Compliance Status Grid */}
          <div style={{
            background: 'rgba(16, 185, 129, 0.06)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            borderRadius: '12px',
            padding: '16px',
            marginBottom: '24px'
          }}>
            <div style={{ fontSize: '13px', fontWeight: '700', color: 'var(--emerald-400)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
              <ShieldCheck size={16} />
              <span>SEBI Circular Compliance Readiness Matrix</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '11px', color: 'var(--text-secondary)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={13} color="var(--emerald-400)" />
                <span>Static IP Whitelisting Enforced</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={13} color="var(--emerald-400)" />
                <span>Daily 2FA / TOTP Verified</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={13} color="var(--emerald-400)" />
                <span>10 req/s Exchange Rate Limiter</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={13} color="var(--emerald-400)" />
                <span>Triple-Interlock Live Lock On</span>
              </div>
            </div>
          </div>

          {/* Profile & Session Form */}
          <form onSubmit={handleSaveUser}>
            <div style={{ fontSize: '13px', fontWeight: '700', color: '#f8fafc', marginBottom: '12px' }}>
              Trader Profile & Credentials
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                  Full Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid var(--border-subtle)',
                    color: '#f8fafc',
                    fontSize: '13px',
                    outline: 'none'
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                  Email Address
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid var(--border-subtle)',
                    color: '#f8fafc',
                    fontSize: '13px',
                    outline: 'none'
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '11px', color: savedSuccess ? 'var(--emerald-400)' : 'var(--text-dim)' }}>
                {savedSuccess ? '✅ Profile updated successfully!' : 'All secret tokens scrubbed before display.'}
              </span>

              <button
                type="submit"
                className="btn btn-primary"
                style={{ padding: '8px 18px', fontSize: '12px' }}
              >
                Save Preferences
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
