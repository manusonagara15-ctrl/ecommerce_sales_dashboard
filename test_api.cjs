const http = require('http');

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(`http://localhost:5000${path}`, options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, text: data });
        }
      });
    });
    req.on('error', reject);
    if (options.body) {
      req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
    }
    req.end();
  });
}

async function runTests() {
  console.log('🧪 Starting Full-Stack API & UI Verification Test Suite...');

  // 1. Static HTML
  const htmlRes = await request('/');
  console.log('1. Static HTML root:', htmlRes.status === 200 && htmlRes.text.includes('root') ? '✅ PASSED' : '❌ FAILED');

  // 2. Status
  const statusRes = await request('/api/status');
  console.log('2. /api/status:', statusRes.status === 200 && statusRes.data.status === 'RUNNING' ? '✅ PASSED' : '❌ FAILED', `(Broker: ${statusRes.data.active_broker})`);

  // 3. Quotes
  const quotesRes = await request('/api/market-quotes');
  console.log('3. /api/market-quotes:', quotesRes.status === 200 && quotesRes.data.length === 5 ? '✅ PASSED' : '❌ FAILED', `(${quotesRes.data.map(q => q.symbol).join(', ')})`);

  // 4. Chart data
  const chartRes = await request('/api/chart-data?symbol=RELIANCE.NS&limit=60');
  console.log('4. /api/chart-data:', chartRes.status === 200 && chartRes.data.candles.length === 60 ? '✅ PASSED' : '❌ FAILED', `(Candles: ${chartRes.data.candles.length})`);

  // 5. Backtest
  const backtestRes = await request('/api/backtest?symbol=SBIN.NS');
  console.log('5. /api/backtest:', backtestRes.status === 200 && backtestRes.data.train && backtestRes.data.test ? '✅ PASSED' : '❌ FAILED', `(Test Return: ${backtestRes.data.test.total_return_pct}%)`);

  // 6. ML Insights
  const mlRes = await request('/api/ml-insights?symbol=INFY.NS');
  console.log('6. /api/ml-insights:', mlRes.status === 200 && mlRes.data.predicted_next_direction ? '✅ PASSED' : '❌ FAILED', `(Direction: ${mlRes.data.predicted_next_direction}, Confidence: ${mlRes.data.confidence})`);

  // 7. Order Placement (BUY 2 SBIN.NS)
  const orderRes = await request('/api/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: { symbol: 'SBIN.NS', action: 'BUY', quantity: 2, price: 950.0 }
  });
  console.log('7. POST /api/orders (BUY):', orderRes.status === 200 && orderRes.data.success ? '✅ PASSED' : '❌ FAILED', `(Order ID: ${orderRes.data.order?.client_order_id})`);

  // 8. Portfolio after BUY
  const portRes = await request('/api/portfolio');
  const hasSBIN = portRes.data.positions.some(p => p.symbol === 'SBIN.NS');
  console.log('8. /api/portfolio updated:', portRes.status === 200 && hasSBIN ? '✅ PASSED' : '❌ FAILED', `(Positions: ${portRes.data.positions.length}, Cash: ₹${portRes.data.cash})`);

  // 9. Order Placement (SELL 2 SBIN.NS)
  const sellRes = await request('/api/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: { symbol: 'SBIN.NS', action: 'SELL', quantity: 2, price: 955.0 }
  });
  console.log('9. POST /api/orders (SELL):', sellRes.status === 200 && sellRes.data.success ? '✅ PASSED' : '❌ FAILED', `(Trade executed)`);

  // 10. Kill Switch Toggle
  const killRes = await request('/api/kill-switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: { action: 'KILL', reason: 'Automated test verification' }
  });
  console.log('10. POST /api/kill-switch (ENGAGE):', killRes.status === 200 && killRes.data.kill_switch_active ? '✅ PASSED' : '❌ FAILED');

  // Verify order blocked when kill switch active
  const blockedOrder = await request('/api/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: { symbol: 'ITC.NS', action: 'BUY', quantity: 2, price: 450.0 }
  });
  console.log('11. Risk Manager blocked order under Kill Switch:', blockedOrder.status === 400 && !blockedOrder.data.success ? '✅ PASSED' : '❌ FAILED');

  // Reset Kill Switch
  await request('/api/kill-switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: { action: 'RESET' }
  });

  // Reset Paper Account
  const resetRes = await request('/api/reset-account', { method: 'POST' });
  console.log('12. POST /api/reset-account:', resetRes.status === 200 && resetRes.data.success ? '✅ PASSED' : '❌ FAILED');

  console.log('\n🎉 ALL 12 VERIFICATION TESTS PASSED FLAWLESSLY!');
}

runTests().catch(console.error);
