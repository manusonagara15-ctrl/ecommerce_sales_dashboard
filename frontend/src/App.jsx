import React, { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import MarketTicker from './components/MarketTicker';
import MetricsBar from './components/MetricsBar';
import TradingChart from './components/TradingChart';
import OrderExecutionPanel from './components/OrderExecutionPanel';
import HoldingsOrdersTab from './components/HoldingsOrdersTab';
import BacktestTab from './components/BacktestTab';
import MLLabTab from './components/MLLabTab';
import BrokerModal from './components/BrokerModal';

import { 
  Briefcase, 
  BarChart2, 
  Brain, 
  ShieldCheck, 
  Sliders, 
  AlertOctagon,
  RefreshCw
} from 'lucide-react';

export default function App() {
  const [selectedSymbol, setSelectedSymbol] = useState('SBIN.NS');
  const [botStatus, setBotStatus] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [marketQuotes, setMarketQuotes] = useState([]);
  const [userProfile, setUserProfile] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [activeTab, setActiveTab] = useState('HOLDINGS'); // 'HOLDINGS' | 'BACKTEST' | 'ML_LAB' | 'RISK_GATEWAY'
  const [isBrokerModalOpen, setIsBrokerModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Fetch Core System State
  const fetchState = useCallback(async () => {
    try {
      const [statusRes, portfolioRes, quotesRes, userRes] = await Promise.all([
        fetch('/api/status').then(r => r.json()).catch(() => null),
        fetch('/api/portfolio').then(r => r.json()).catch(() => null),
        fetch('/api/market-quotes').then(r => r.json()).catch(() => []),
        fetch('/api/user/profile').then(r => r.json()).catch(() => null)
      ]);

      if (statusRes) setBotStatus(statusRes);
      if (portfolioRes) setPortfolio(portfolioRes);
      if (quotesRes && quotesRes.length > 0) setMarketQuotes(quotesRes);
      if (userRes) setUserProfile(userRes);
    } catch (err) {
      console.error('Error fetching dashboard state:', err);
    }
  }, []);

  // Fetch Chart Data for Symbol
  const fetchChart = useCallback(async (symbol) => {
    try {
      const res = await fetch(`/api/chart-data?symbol=${symbol}&limit=180`);
      const data = await res.json();
      setChartData(data);
    } catch (err) {
      console.error('Error fetching chart data:', err);
    }
  }, []);

  // Initial load and periodic polling
  useEffect(() => {
    fetchState();
    fetchChart(selectedSymbol);

    const interval = setInterval(() => {
      fetchState();
    }, 5000);

    return () => clearInterval(interval);
  }, [fetchState, fetchChart, selectedSymbol]);

  // Symbol Change Handler
  const handleSelectSymbol = (symbol) => {
    setSelectedSymbol(symbol);
    fetchChart(symbol);
  };

  // Order Submission Handler
  const handleSubmitOrder = async (orderData) => {
    try {
      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderData)
      });
      const data = await res.json();
      fetchState();
      return data;
    } catch (err) {
      return { success: false, error: err.message };
    }
  };

  // Kill Switch Toggle Handler
  const handleToggleKillSwitch = async () => {
    const isEngaged = botStatus?.kill_switch_active;
    const action = isEngaged ? 'RESET' : 'KILL';
    try {
      await fetch('/api/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          reason: isEngaged ? '' : 'Emergency stop triggered via Navigation Bar'
        })
      });
      fetchState();
    } catch (err) {
      console.error('Kill switch error:', err);
    }
  };

  // Reset Virtual Margin
  const handleResetAccount = async () => {
    if (window.confirm('Reset virtual paper margin back to ₹50,000 cash balance and clear all open positions?')) {
      try {
        await fetch('/api/reset-account', { method: 'POST' });
        fetchState();
      } catch (err) {
        console.error('Reset account error:', err);
      }
    }
  };

  // Select Broker Connector
  const handleSelectBroker = async (brokerId) => {
    try {
      await fetch('/api/broker/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker: brokerId })
      });
      fetchState();
    } catch (err) {
      console.error('Broker selection error:', err);
    }
  };

  // Square Off Position
  const handleSquareOff = async (symbol, qty) => {
    if (window.confirm(`Auto square-off and exit position in ${symbol} (${qty} shares)?`)) {
      const quote = marketQuotes.find(q => q.symbol === symbol);
      const price = quote?.price || 1000.0;
      await handleSubmitOrder({
        symbol,
        action: 'SELL',
        quantity: qty,
        price
      });
    }
  };

  // Update Profile
  const handleUpdateProfile = async (email, name) => {
    try {
      await fetch('/api/user/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name })
      });
      fetchState();
    } catch (err) {
      console.error('Profile update error:', err);
    }
  };

  const currentQuote = marketQuotes.find(q => q.symbol === selectedSymbol) || {
    symbol: selectedSymbol,
    price: chartData?.current_price || 1000.0,
    change: 0,
    change_pct: 0
  };

  const tabs = [
    { id: 'HOLDINGS', label: 'Holdings & Order Book', icon: Briefcase },
    { id: 'BACKTEST', label: '3-Phase Backtesting Audit', icon: BarChart2 },
    { id: 'ML_LAB', label: 'Walk-Forward ML Lab', icon: Brain },
    { id: 'RISK_GATEWAY', label: 'SEBI Risk Matrix', icon: ShieldCheck }
  ];

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* 1. Navbar */}
      <Navbar
        botStatus={botStatus}
        userProfile={userProfile}
        onToggleKillSwitch={handleToggleKillSwitch}
        onOpenBrokerModal={() => setIsBrokerModalOpen(true)}
        onRefresh={() => { fetchState(); fetchChart(selectedSymbol); }}
      />

      {/* 2. Scrolling Ticker Marquee */}
      <MarketTicker
        marketQuotes={marketQuotes}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={handleSelectSymbol}
      />

      {/* Main Dashboard Workspace */}
      <main style={{ maxWidth: '1440px', width: '100%', margin: '0 auto', padding: '24px 24px 40px', flex: 1 }}>
        {/* Emergency Kill Switch Banner if active */}
        {botStatus?.kill_switch_active && (
          <div style={{
            background: 'rgba(244, 63, 94, 0.15)',
            border: '1px solid rgba(244, 63, 94, 0.4)',
            borderRadius: '10px',
            padding: '14px 20px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--rose-400)' }}>
              <AlertOctagon size={20} />
              <div>
                <strong>EMERGENCY KILL-SWITCH ACTIVE:</strong> All automated and manual order entries are strictly blocked.
                <span style={{ color: '#f8fafc', fontSize: '12px', marginLeft: '8px' }}>
                  Reason: {botStatus?.kill_switch_reason || 'Manual user trigger'}
                </span>
              </div>
            </div>

            <button
              onClick={handleToggleKillSwitch}
              className="btn btn-primary"
              style={{ padding: '6px 14px', fontSize: '12px' }}
            >
              Reset Safety Lock
            </button>
          </div>
        )}

        {/* 3. Top Portfolio Metric Cards */}
        <MetricsBar
          portfolio={portfolio}
          onResetAccount={handleResetAccount}
        />

        {/* 4. Chart & Order Widget Row */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 2fr) minmax(320px, 1fr)',
          gap: '24px',
          marginBottom: '24px',
          alignItems: 'stretch'
        }}>
          {/* Chart */}
          <TradingChart
            chartData={chartData}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={handleSelectSymbol}
          />

          {/* Virtual Order Widget */}
          <OrderExecutionPanel
            selectedSymbol={selectedSymbol}
            currentQuote={currentQuote}
            portfolio={portfolio}
            botStatus={botStatus}
            onSubmitOrder={handleSubmitOrder}
          />
        </div>

        {/* 5. Sub-Navigation Tabs */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          borderBottom: '1px solid var(--border-subtle)',
          marginBottom: '20px',
          overflowX: 'auto'
        }}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 18px',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: `2px solid ${isActive ? '#06b6d4' : 'transparent'}`,
                  color: isActive ? '#38bdf8' : 'var(--text-secondary)',
                  fontSize: '13px',
                  fontWeight: '700',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
              >
                <Icon size={16} />
                <span>{tab.label}</span>
              </button>
            );
          })}

          <button
            onClick={() => setIsBrokerModalOpen(true)}
            style={{
              marginLeft: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: '6px',
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              fontSize: '12px',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            <Sliders size={14} color="#06b6d4" />
            <span>Broker & Credentials Gateway</span>
          </button>
        </div>

        {/* Tab Contents */}
        {activeTab === 'HOLDINGS' && (
          <HoldingsOrdersTab
            portfolio={portfolio}
            onSquareOff={handleSquareOff}
          />
        )}

        {activeTab === 'BACKTEST' && (
          <BacktestTab
            selectedSymbol={selectedSymbol}
          />
        )}

        {activeTab === 'ML_LAB' && (
          <MLLabTab
            selectedSymbol={selectedSymbol}
          />
        )}

        {activeTab === 'RISK_GATEWAY' && (
          <div className="glass-panel" style={{ padding: '24px' }}>
            <div style={{ fontSize: '16px', fontWeight: '800', color: '#f8fafc', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShieldCheck size={18} color="var(--emerald-400)" />
              <span>Pre-Trade Risk Management & SEBI Mandate Matrix</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Single Order Limit</div>
                <div className="mono-num" style={{ fontSize: '20px', fontWeight: '800', color: 'var(--emerald-400)', marginTop: '4px' }}>
                  ₹5,000.00
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>Max capital allocated to one trade</div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Gross Exposure Cap</div>
                <div className="mono-num" style={{ fontSize: '20px', fontWeight: '800', color: '#38bdf8', marginTop: '4px' }}>
                  ₹15,000.00
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>Max total portfolio market value</div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Max Concurrent Positions</div>
                <div className="mono-num" style={{ fontSize: '20px', fontWeight: '800', color: '#f8fafc', marginTop: '4px' }}>
                  3 Stocks
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>Strict diversification constraint</div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Market Entry Cutoff</div>
                <div className="mono-num" style={{ fontSize: '20px', fontWeight: '800', color: 'var(--amber-500)', marginTop: '4px' }}>
                  02:45 PM IST
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>Square-off deadline: 03:10 PM IST</div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* 6. Footer */}
      <footer style={{
        background: '#070b14',
        borderTop: '1px solid var(--border-subtle)',
        padding: '16px 24px',
        fontSize: '11px',
        color: 'var(--text-dim)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>🇮🇳 AlgoTrader India Framework (Vite + React Edition)</span>
          <span>•</span>
          <span>Educational & Simulation Mode</span>
          <span>•</span>
          <span style={{ color: 'var(--emerald-400)' }}>SEBI Risk Lock Enforced</span>
        </div>
        <div>
          Connected to <strong>{botStatus?.active_broker || 'GROWW'}</strong> Engine • Port 5173 / 5000
        </div>
      </footer>

      {/* 7. Broker & Credentials Modal */}
      <BrokerModal
        isOpen={isBrokerModalOpen}
        onClose={() => setIsBrokerModalOpen(false)}
        botStatus={botStatus}
        userProfile={userProfile}
        onSelectBroker={handleSelectBroker}
        onUpdateProfile={handleUpdateProfile}
      />
    </div>
  );
}
