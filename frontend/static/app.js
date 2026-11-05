/* ==========================================================================
   Cisco TRex Network Test Studio — Core Telemetry, Routing & Overview Charts
   ========================================================================== */

const WORKLOAD_COLORS = {
  video_streaming: { label: 'Video Streaming', color: '#1769D2' },
  m365_productivity: { label: 'Microsoft 365-like', color: '#2585E6' },
  teams_collab: { label: 'Teams Voice/Video', color: '#0EA5E9' },
  social_browsing: { label: 'Social Media-like', color: '#6366F1' },
  messaging_chat: { label: 'Messaging (WhatsApp-like)', color: '#14B8A6' },
  cloud_files: { label: 'Cloud File Sync', color: '#3B82F6' },
  web_browsing: { label: 'Web Browsing', color: '#10B981' },
  dns_queries: { label: 'DNS Queries', color: '#F59E0B' },
  voip_sip: { label: 'VoIP (SIP/RTP)', color: '#0D9488' },
  gaming_realtime: { label: 'Low-Latency Gaming', color: '#8B5CF6' },
  backups_storage: { label: 'Backups & Storage', color: '#64748B' },
  bulk_downloads: { label: 'Bulk Downloads', color: '#0284C7' },
};

// The sidebar has 6 sections. Each section groups related pages as tabs.
const SECTIONS = {
  home: { title: 'Home', sub: 'Status at a glance and one-click tests', routes: ['dashboard'] },
  run: { title: 'Run a Test', sub: 'Pick a test type, set it up and start it', routes: ['quick-test', 'application-simulation', 'traffic-mix-builder', 'stress-soak', 'rfc2544-benchmark', 'traffic-profiles', 'test-scheduler'] },
  live: { title: 'Live View', sub: 'Watch the running test in real time', routes: ['live-monitoring'] },
  results: { title: 'Results & Reports', sub: 'Past tests, side-by-side comparison and PDF reports', routes: ['test-history', 'compare-tests', 'reports-exports'] },
  network: { title: 'My Network', sub: 'UniFi devices, topology and server ports', routes: ['unifi-monitoring', 'network-topology', 'nics-ports'] },
  system: { title: 'System & Settings', sub: 'Server health, TRex engine, integrations and settings', routes: ['server-health', 'trex-engine', 'api-integrations', 'configuration', 'user-access', 'audit-logs'] },
};

// Short tab labels for each page
const ROUTE_LABELS = {
  'dashboard': 'Home',
  'live-monitoring': 'Live View',
  'quick-test': 'Custom Test',
  'application-simulation': 'App Simulation',
  'traffic-mix-builder': 'Traffic Mix',
  'stress-soak': 'Stress & Soak',
  'rfc2544-benchmark': 'Benchmark (RFC 2544)',
  'traffic-profiles': 'Saved Profiles',
  'test-scheduler': 'Schedule',
  'test-history': 'History',
  'compare-tests': 'Compare',
  'reports-exports': 'Reports',
  'unifi-monitoring': 'UniFi',
  'network-topology': 'Topology',
  'nics-ports': 'Ports',
  'server-health': 'Server Health',
  'trex-engine': 'TRex Engine',
  'api-integrations': 'Integrations',
  'configuration': 'Settings',
  'user-access': 'Users',
  'audit-logs': 'Audit Log',
};

const sectionForRoute = (route) => Object.keys(SECTIONS).find((k) => SECTIONS[k].routes.includes(route));

// One-click tests shown on the Home page
const HOME_PRESETS = [
  {
    id: 'selftest',
    title: 'Engine self-test',
    desc: '30 s, 1 Gbps on the internal loopback. Checks TRex works.',
    payload: { name: 'Engine self-test (loopback)', profile_id: 'bw_1518b', traffic_engine: 'trex_stl', test_mode: 'timed', duration_sec: 30, steady_sec: 30, target_gbps: 1.0, simulated_users: 500, simulated_devices: 1000 },
  },
  {
    id: 'efg10k',
    title: 'Firewall load test',
    desc: '2 min realistic office traffic for the number of users above.',
    usesUserBox: true,
    payload: { scenario_id: 'scenario_10000_users', name: '10,000 users — gateway acceptance test', profile_id: 'imix', traffic_engine: 'trex_astf', test_mode: 'phased', simulated_users: 10000, simulated_devices: 20000, target_gbps: 5.0, ramp_up_sec: 20, steady_sec: 90, ramp_down_sec: 10 },
  },
  {
    id: 'internet',
    title: 'Internet speed & quality',
    desc: '1 min of real downloads, DNS and latency through your WAN.',
    payload: { name: 'Internet speed & quality', profile_id: 'internet_wan_mix', traffic_engine: 'internet_wan', test_mode: 'timed', duration_sec: 60, steady_sec: 60, target_gbps: 0.1, simulated_users: 500, simulated_devices: 1000 },
  },
  {
    id: 'bench',
    title: 'Frame-size benchmark',
    desc: 'RFC 2544-style sweep, 64 B to 1518 B.',
    route: 'rfc2544-benchmark',
  },
];

const App = {
  currentRoute: 'dashboard',
  liveMonTab: 'performance',
  ws: null,
  latest: null,
  profiles: [],
  workloads: [],
  scenarios: [],
  stagedSteps: [],
  runs: [],
  charts: {},

  history: {
    maxLen: 150,
    labels: [],
    txGbps: [],
    rxGbps: [],
    targetGbps: [],
    latAvg: [],
    latP95: [],
    latP99: [],
    jitter: [],
    activeFlows: [],
    estSessions: [],
    cps: [],
    drops: [],
    tcpRexmt: [],
    unifiCpu: [],
    r640Cpu: [],
  },

  async init() {
    this.bindNavigation();
    this.initDashboardCharts();
    await this.loadInitialCatalog();
    this.connectWebSocket();
    window.addEventListener('resize', () => {
      Object.values(this.charts).forEach((ch) => ch && ch.resize && ch.resize());
    });
    // Refresh recent runs periodically
    setInterval(() => {
      if (this.currentRoute === 'dashboard') this.refreshRunsSilent();
    }, 8000);
  },

  bindNavigation() {
    // Remember the last tab used in each section so clicking the section returns there
    this.lastRouteBySection = {};
    document.querySelectorAll('.nav-item[data-section]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sec = btn.getAttribute('data-section');
        this.navigate(this.lastRouteBySection[sec] || SECTIONS[sec].routes[0]);
      });
    });
    window.addEventListener('hashchange', () => {
      const r = location.hash.slice(1);
      if (r && r !== this.currentRoute) this.navigate(r);
    });
    const startRoute = location.hash.slice(1);
    if (startRoute && ROUTE_LABELS[startRoute]) setTimeout(() => this.navigate(startRoute), 0);
  },

  // Shared "number of users" field: free number entry (1 – MAX_USERS) plus quick-pick chips.
  MAX_USERS: 100000,
  usersField(id, value = 10000, onchange = '') {
    const chips = [1000, 10000, 25000, 50000, 100000]
      .map((n) => `<button type="button" class="chip-btn" onclick="App.setUsers('${id}', ${n})">${n >= 1000 ? n / 1000 + 'K' : n}</button>`)
      .join('');
    return `
      <input type="number" class="form-control" id="${id}" min="1" max="${this.MAX_USERS}" step="1" value="${value}"
        onchange="App.setUsers('${id}', this.value)${onchange ? ';' + onchange : ''}" />
      <div class="chip-row">${chips}</div>`;
  },

  setUsers(id, n) {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = this.clampUsers(n);
    el.dispatchEvent(new Event('input'));
  },

  clampUsers(n) {
    const v = Math.round(Number(String(n).replace(/[^\d.]/g, '')));
    if (!Number.isFinite(v) || v < 1) return 1;
    return Math.min(this.MAX_USERS, v);
  },

  readUsers(id, fallback = 10000) {
    const el = document.getElementById(id);
    if (!el || el.value === '') return fallback;
    return this.clampUsers(el.value);
  },

  esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },

  renderSectionTabs(sectionKey, route) {
    const bar = document.getElementById('sectionTabs');
    if (!bar) return;
    const routes = SECTIONS[sectionKey].routes;
    if (routes.length < 2) {
      bar.style.display = 'none';
      return;
    }
    bar.style.display = 'flex';
    bar.innerHTML = routes
      .map((r) => `<button class="subtab-btn ${r === route ? 'active' : ''}" onclick="App.navigate('${r}')">${ROUTE_LABELS[r]}</button>`)
      .join('');
  },

  navigate(route) {
    if (!ROUTE_LABELS[route]) route = 'dashboard';
    this.currentRoute = route;
    const sectionKey = sectionForRoute(route) || 'home';
    if (this.lastRouteBySection) this.lastRouteBySection[sectionKey] = route;
    if (location.hash.slice(1) !== route) history.replaceState(null, '', `#${route}`);

    document.querySelectorAll('.nav-item[data-section]').forEach((b) => {
      b.classList.toggle('active', b.getAttribute('data-section') === sectionKey);
    });
    document.querySelectorAll('.page-section').forEach((sec) => {
      sec.classList.toggle('active', sec.id === `page-${route}`);
    });
    this.renderSectionTabs(sectionKey, route);

    document.getElementById('topbarTitle').textContent = SECTIONS[sectionKey].title;
    document.getElementById('topbarSubtitle').textContent = SECTIONS[sectionKey].sub;
    document.getElementById('pageViewport')?.scrollTo?.(0, 0);

    // Render route content
    if (route === 'dashboard') {
      this.refreshRunsSilent();
      setTimeout(() => {
        if (this.charts.dashTp) this.charts.dashTp.resize();
      }, 60);
    } else if (route === 'live-monitoring') {
      this.ensureLiveMonChart();
      this.updateLiveMonitoringView();
    } else if (window.StudioPages && StudioPages.canHandle(route)) {
      StudioPages.render(route);
    } else if (window.InfraPages && InfraPages.canHandle(route)) {
      InfraPages.render(route);
    }
  },

  async api(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const res = await fetch(path, { ...opts, headers });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        msg = err.detail || err.message || msg;
      } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  },

  toast(msg, type = 'info') {
    const c = document.getElementById('toastContainer');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  },

  openModal(title, html) {
    document.getElementById('appModalTitle').textContent = title;
    document.getElementById('appModalBody').innerHTML = html;
    document.getElementById('appModalBackdrop').classList.add('open');
  },

  closeModal() {
    document.getElementById('appModalBackdrop').classList.remove('open');
  },

  fmtBpsParts(bps) {
    const v = Number(bps || 0);
    if (v >= 1e9) return { val: (v / 1e9).toFixed(2), unit: 'Gbps' };
    if (v >= 1e6) return { val: (v / 1e6).toFixed(2), unit: 'Mbps' };
    if (v >= 1e3) return { val: (v / 1e3).toFixed(1), unit: 'Kbps' };
    return { val: v.toFixed(0), unit: 'bps' };
  },

  fmtBps(bps) {
    if (bps === null || bps === undefined) return 'Unavailable';
    const p = this.fmtBpsParts(bps);
    return `${p.val} ${p.unit}`;
  },

  fmtPpsParts(pps) {
    const v = Number(pps || 0);
    if (v >= 1e6) return { val: (v / 1e6).toFixed(2), unit: 'Mpps' };
    if (v >= 1e3) return { val: (v / 1e3).toFixed(1), unit: 'Kpps' };
    return { val: v.toFixed(0), unit: 'pps' };
  },

  fmtDurationClock(sec) {
    const s = Math.max(0, Math.floor(Number(sec || 0)));
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const rem = s % 60;
    return [hrs, mins, rem].map((x) => String(x).padStart(2, '0')).join(':');
  },

  verdictBadge(verdict, thresholdsConfigured) {
    const v = String(verdict || 'COMPLETED').toUpperCase();
    if (v === 'RUNNING') return `<span class="badge badge-info">&#9679; Running</span>`;
    if (thresholdsConfigured === false && v === 'PASS') {
      return `<span class="badge badge-neutral">Completed</span>`;
    }
    if (v === 'PASS') return `<span class="badge badge-success">&#10003; Pass</span>`;
    if (v === 'FAIL') return `<span class="badge badge-critical">&#10005; Fail</span>`;
    return `<span class="badge badge-neutral">${v.charAt(0) + v.slice(1).toLowerCase()}</span>`;
  },

  async loadInitialCatalog() {
    try {
      const [profData, runsData, statusData] = await Promise.all([
        this.api('/api/profiles'),
        this.api('/api/runs?limit=25'),
        this.api('/api/status'),
      ]);
      this.profiles = profData.profiles || [];
      this.workloads = profData.application_workloads || [];
      this.scenarios = profData.efg_scenarios || [];
      this.stagedSteps = profData.staged_load_steps || [];
      this.runs = runsData.runs || [];

      this.populateDashQuickTest();
      this.renderDashRecentRuns();
      if (statusData) this.ingestTelemetry(statusData);
    } catch (e) {
      console.error('Initial load warning:', e);
    }
  },

  async refreshRunsSilent() {
    try {
      const d = await this.api('/api/runs?limit=25');
      this.runs = d.runs || [];
      this.renderDashRecentRuns();
    } catch (_) {}
  },

  populateDashQuickTest() {
    const list = document.getElementById('homePresetList');
    if (list) {
      list.innerHTML = HOME_PRESETS.map((p) => `
        <button class="preset-btn" onclick="App.runPreset('${p.id}')">
          <span class="preset-title">${p.title}</span>
          <span class="preset-desc">${p.desc}</span>
          <span class="preset-go">${p.route ? 'Open &rarr;' : '&#9654; Start'}</span>
        </button>`).join('');
    }
    const ub = document.getElementById('homeUsersBox');
    if (ub && !document.getElementById('homeUsers')) ub.innerHTML = this.usersField('homeUsers', 10000);
    const host = document.getElementById('sbHostIp');
    if (host) host.textContent = `Host: ${location.hostname}`;
  },

  async runPreset(id) {
    const p = HOME_PRESETS.find((x) => x.id === id);
    if (!p) return;
    if (p.route) return this.navigate(p.route);
    if (this.latest && this.latest.running) {
      this.toast('A test is already running. Stop it first.', 'error');
      return this.navigate('live-monitoring');
    }
    const payload = { ...p.payload };
    if (p.usesUserBox) {
      const users = this.readUsers('homeUsers', payload.simulated_users);
      payload.simulated_users = users;
      payload.simulated_devices = users * 2;
      payload.name = `${users.toLocaleString()} users — gateway load test`;
      delete payload.scenario_id;
      // Larger populations get a longer ramp so the gateway isn't hit with every new session at once
      payload.ramp_up_sec = users > 50000 ? 120 : users > 20000 ? 60 : 20;
    }
    try {
      await this.startTestRequest(payload);
      this.navigate('live-monitoring');
    } catch (_) {}
  },

  connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${location.host}/ws/telemetry`;
    const sbWs = document.getElementById('sbWsStatus');

    const ws = new WebSocket(wsUrl);
    this.ws = ws;

    ws.onopen = () => {
      if (sbWs) sbWs.innerHTML = `<span style="color:#4ADE80;">&#9679;</span> Live`;
    };
    ws.onmessage = (ev) => {
      try {
        const frame = JSON.parse(ev.data);
        this.ingestTelemetry(frame);
      } catch (_) {}
    };
    ws.onclose = () => {
      if (sbWs) sbWs.innerHTML = `<span style="color:#FBBF24;">&#9679;</span> Reconnecting...`;
      setTimeout(() => this.connectWebSocket(), 2000);
    };
  },

  ingestTelemetry(f) {
    const wasRunning = this.latest && this.latest.running;
    this.latest = f;

    // Push sample once per ~1 second or while running every 500ms
    const nowLabel = f.running ? this.fmtDurationClock(f.elapsed_sec || 0).slice(3) : new Date(f.ts * 1000).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' });
    const h = this.history;
    if (h.labels.length === 0 || h.labels[h.labels.length - 1] !== nowLabel || f.running) {
      // Avoid 4x/sec duplicate points when idle
      if (f.running || h.labels[h.labels.length - 1] !== nowLabel) {
        h.labels.push(nowLabel);
        h.txGbps.push(Number(((f.tx_bps || 0) / 1e9).toFixed(4)));
        h.rxGbps.push(Number(((f.rx_bps || 0) / 1e9).toFixed(4)));
        h.targetGbps.push(Number(((f.target_bps || 0) / 1e9).toFixed(4)));
        h.latAvg.push(Number((f.lat_avg_us || 0).toFixed(2)));
        h.latP95.push(Number((f.p95_lat_us || 0).toFixed(2)));
        h.latP99.push(Number((f.p99_lat_us || 0).toFixed(2)));
        h.jitter.push(Number((f.jitter_us || 0).toFixed(2)));
        h.activeFlows.push(Number(f.active_flows || 0));
        h.estSessions.push(Number(f.established_sessions || 0));
        h.cps.push(Number((f.cps || 0).toFixed(1)));
        h.drops.push(Number(f.dropped_packets || 0));
        h.tcpRexmt.push(Number(f.tcp_retransmits || 0));
        h.unifiCpu.push(f.unifi_gw_cpu !== null && f.unifi_gw_cpu !== undefined ? Number(f.unifi_gw_cpu) : null);
        h.r640Cpu.push(Number(f.cpu_pct || 0));

        if (h.labels.length > h.maxLen) {
          Object.keys(h).forEach((k) => {
            if (Array.isArray(h[k])) h[k].shift();
          });
        }
      }
    }

    if (wasRunning && !f.running) {
      this.refreshRunsSilent();
    }

    this.updateHeaderBar(f);
    if (this.currentRoute === 'dashboard') {
      this.updateDashboardView(f);
    } else if (this.currentRoute === 'live-monitoring') {
      this.updateLiveMonitoringView();
    }
  },

  updateHeaderBar(f) {
    const dot = document.getElementById('hdrTrexDot');
    const sub = document.getElementById('hdrTrexSub');
    if (dot && sub) {
      dot.className = `status-chip-dot ${f.trex_connected ? '' : 'offline'}`;
      const modeTxt = f.trex_daemon_mode || 'ASTF';
      sub.textContent = f.trex_connected ? `Running • ${modeTxt} DPDK` : 'Offline';
    }

    const stopBtn = document.getElementById('hdrEmergencyStop');
    if (stopBtn) stopBtn.style.display = f.running ? 'inline-flex' : 'none';
    const liveDot = document.getElementById('navLiveDot');
    if (liveDot) liveDot.classList.toggle('on', !!f.running);

    const alerts = f.alerts || [];
    const alertBadge = document.getElementById('hdrAlertCount');
    if (alertBadge) {
      if (alerts.length > 0) {
        alertBadge.style.display = 'flex';
        alertBadge.textContent = String(alerts.length);
      } else {
        alertBadge.style.display = 'none';
      }
    }
  },

  initDashboardCharts() {
    const tpEl = document.getElementById('dashThroughputChart');
    if (tpEl && window.echarts) {
      this.charts.dashTp = echarts.init(tpEl);
      this.charts.dashTp.setOption({
        animation: false,
        grid: { top: 28, right: 16, bottom: 26, left: 48 },
        tooltip: { trigger: 'axis' },
        legend: { top: 0, right: 6, textStyle: { color: '#475569', fontSize: 11.5 } },
        xAxis: { type: 'category', boundaryGap: false, data: [], axisLabel: { color: '#64748B', fontSize: 11 }, axisLine: { lineStyle: { color: '#DFE5ED' } } },
        yAxis: { type: 'value', name: 'Gbps', min: 0, nameTextStyle: { color: '#64748B', fontSize: 11 }, axisLabel: { color: '#64748B', fontSize: 11 }, splitLine: { lineStyle: { color: '#EEF2F6' } } },
        series: [
          { name: 'TX (Gbps)', type: 'line', smooth: true, showSymbol: false, lineStyle: { width: 2.3, color: '#1769D2' }, itemStyle: { color: '#1769D2' }, areaStyle: { color: 'rgba(23,105,210,0.12)' }, data: [] },
          { name: 'RX (Gbps)', type: 'line', smooth: true, showSymbol: false, lineStyle: { width: 2.0, color: '#10B981' }, itemStyle: { color: '#10B981' }, areaStyle: { color: 'rgba(16,185,129,0.06)' }, data: [] },
        ],
      });
    }
  },

  fmtLatency(us) {
    const v = Number(us || 0);
    if (!v) return { val: '—', unit: '' };
    if (v >= 1000) return { val: (v / 1000).toFixed(2), unit: 'ms' };
    return { val: v.toFixed(1), unit: 'μs' };
  },

  updateDashboardView(f) {
    // --- Status hero ---
    const hero = document.getElementById('homeHero');
    const heroTitle = document.getElementById('homeHeroTitle');
    const heroSub = document.getElementById('homeHeroSub');
    const heroAct = document.getElementById('homeHeroActions');
    const runningKey = f.running ? `run-${f.run_id || f.test_name}` : (f.trex_connected ? 'idle-ok' : 'idle-off');
    if (f.running) {
      hero.className = 'hero-card running';
      heroTitle.textContent = `Running: ${f.test_name || 'test'}`;
      const remaining = f.duration_sec ? ` of ${this.fmtDurationClock(f.duration_sec)}` : '';
      heroSub.textContent = `${(f.phase_name || 'steady').replace(/_/g, ' ')} • ${this.fmtDurationClock(f.elapsed_sec)}${remaining} • ${Number(f.simulated_users || 0).toLocaleString()} users`;
    } else if (f.trex_connected) {
      hero.className = 'hero-card idle';
      heroTitle.textContent = 'Ready to test';
      heroSub.innerHTML = 'Pick a one-click test below, or build your own under <strong>Run a Test</strong>.';
    } else {
      hero.className = 'hero-card warn';
      heroTitle.textContent = 'TRex engine is offline';
      heroSub.innerHTML = 'Lab tests need the TRex engine. The <strong>Internet speed</strong> test still works. Open <strong>System &amp; Settings &rarr; TRex Engine</strong> to fix.';
    }
    if (this._heroKey !== runningKey) {
      this._heroKey = runningKey;
      heroAct.innerHTML = f.running
        ? `<button class="btn btn-outline" onclick="App.navigate('live-monitoring')">Open Live View</button>
           <button class="btn btn-danger" onclick="App.stopActiveTest('completed')">&#9632; Stop</button>`
        : (f.trex_connected
          ? `<button class="btn btn-primary" onclick="App.runPreset('efg10k')">&#9654; Run load test</button>`
          : `<button class="btn btn-outline" onclick="App.navigate('trex-engine')">Check TRex engine</button>`);
    }

    // --- KPIs ---
    const tgtBps = Number(f.target_bps || 0);
    const txParts = this.fmtBpsParts(f.tx_bps || 0);
    const txPct = tgtBps > 0 ? Math.min(100, ((f.tx_bps || 0) / tgtBps) * 100) : 0;
    document.getElementById('kpiTxVal').textContent = txParts.val;
    document.getElementById('kpiTxUnit').textContent = txParts.unit;
    document.getElementById('kpiTxBar').style.width = `${txPct.toFixed(1)}%`;
    document.getElementById('kpiTxFoot').textContent = f.running
      ? `Received ${this.fmtBps(f.rx_bps || 0)} • target ${tgtBps ? this.fmtBps(tgtBps) : '—'}`
      : 'No test running';

    const lat = this.fmtLatency(f.lat_avg_us);
    document.getElementById('kpiLatVal').textContent = lat.val;
    document.getElementById('kpiLatUnit').textContent = lat.unit;
    const jit = this.fmtLatency(f.jitter_us);
    document.getElementById('kpiLatFoot').textContent = f.lat_avg_us
      ? `Jitter ${jit.val} ${jit.unit}${f.mos_score ? ` • call quality (MOS) ${Number(f.mos_score).toFixed(2)}` : ''}`
      : 'Measured during a test';

    const loss = Number(f.drop_pct || 0);
    document.getElementById('kpiLossVal').textContent = loss.toFixed(3);
    document.getElementById('kpiLossFoot').textContent = `${Number(f.dropped_packets || 0).toLocaleString()} packets dropped`;

    document.getElementById('kpiUsersVal').textContent = f.running ? Number(f.simulated_users || 0).toLocaleString() : '0';
    document.getElementById('kpiFlowsFoot').textContent = f.running
      ? `${Number(f.active_flows || 0).toLocaleString()} active flows • ${Number(f.cps || 0).toFixed(0)} new/s`
      : 'Simulated users during a test';

    // --- Throughput chart (auto-scale Mbps vs Gbps) ---
    if (this.charts.dashTp) {
      const maxG = Math.max(...this.history.txGbps, ...this.history.rxGbps, 0);
      const useMbps = maxG < 0.8;
      const unit = useMbps ? 'Mbps' : 'Gbps';
      const factor = useMbps ? 1000 : 1;
      this.charts.dashTp.setOption({
        xAxis: { data: this.history.labels },
        yAxis: { name: unit },
        series: [
          { name: `Sent (${unit})`, data: this.history.txGbps.map((v) => Number((v * factor).toFixed(3))) },
          { name: `Received (${unit})`, data: this.history.rxGbps.map((v) => Number((v * factor).toFixed(3))) },
        ],
      });
    }
    const engineNames = { trex_astf: 'TRex stateful', trex_stl: 'TRex stateless', internet_wan: 'Internet / WAN', hybrid: 'Hybrid' };
    document.getElementById('dashChartEngineLabel').textContent = f.running ? (engineNames[f.traffic_engine] || f.traffic_engine || '') : '';

    // --- UniFi card ---
    this.renderDashUniFiStack(f);

    // --- Server health card ---
    const setBar = (id, pct) => { const el = document.getElementById(id); if (el) el.style.width = `${Math.min(100, Math.max(0, pct))}%`; };
    const cpu = Number(f.cpu_pct || 0);
    const ram = Number(f.ram_pct || 0);
    document.getElementById('hlthCpuTxt').textContent = `${cpu.toFixed(0)}%`;
    setBar('hlthCpuBar', cpu);
    document.getElementById('hlthRamTxt').textContent = f.ram_total_gb ? `${ram.toFixed(0)}% of ${Math.round(f.ram_total_gb)} GB` : `${ram.toFixed(0)}%`;
    setBar('hlthRamBar', ram);
    if (f.storage && f.storage.total_gb) {
      document.getElementById('hlthDiskTxt').textContent = `${Number(f.storage.percent || 0).toFixed(0)}% of ${Math.round(f.storage.total_gb)} GB`;
      setBar('hlthDiskBar', Number(f.storage.percent || 0));
    }

    const alerts = f.alerts || [];
    const hb = document.getElementById('hlthBadge');
    const sumDot = document.getElementById('hlthSummaryDot');
    const sumTitle = document.getElementById('hlthSummaryTitle');
    const sumSub = document.getElementById('hlthSummarySub');
    if (alerts.length > 0) {
      sumDot.className = 'status-chip-dot warn';
      sumTitle.textContent = `${alerts.length} notice${alerts.length > 1 ? 's' : ''} — click to view`;
      sumSub.textContent = String(alerts[0].message || '').slice(0, 80);
      hb.className = 'badge badge-warning';
      hb.textContent = 'Check';
    } else {
      sumDot.className = 'status-chip-dot';
      sumTitle.textContent = 'All good';
      sumSub.textContent = f.trex_connected ? 'TRex engine connected.' : 'No alerts.';
      hb.className = 'badge badge-success';
      hb.textContent = 'OK';
    }
  },

  renderDashUniFiStack(f) {
    const badge = document.getElementById('dashUnifiBadge');
    const body = document.getElementById('dashUnifiStackBody');
    if (!badge || !body) return;

    const u = f.unifi_summary || {};
    const has = (v) => v !== null && v !== undefined;
    if (f.unifi_connected) {
      badge.className = 'badge badge-success';
      badge.textContent = 'Connected';
      const gwCpu = has(u.gw_cpu_pct) ? `${Number(u.gw_cpu_pct).toFixed(0)}%` : '—';
      const gwMem = has(u.gw_mem_pct) ? `${Number(u.gw_mem_pct).toFixed(0)}%` : '—';
      body.innerHTML = `
        <div class="unifi-stack-row" onclick="App.navigate('unifi-monitoring')">
          <div>
            <div style="font-weight:700;font-size:13px;">${this.esc(u.gw_name || 'Gateway')}</div>
            <div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;">CPU <strong>${gwCpu}</strong> • RAM <strong>${gwMem}</strong></div>
          </div>
          <span style="color:var(--text-secondary);">&rsaquo;</span>
        </div>
        <div class="unifi-stack-row" onclick="App.navigate('unifi-monitoring')">
          <div style="font-weight:600;">Switches</div>
          <div><strong>${u.switches_online ?? 0} / ${u.switches_total ?? 0}</strong> online</div>
        </div>
        <div class="unifi-stack-row" onclick="App.navigate('unifi-monitoring')">
          <div style="font-weight:600;">Access points</div>
          <div><strong>${u.aps_online ?? 0} / ${u.aps_total ?? 0}</strong> online</div>
        </div>
        <div class="unifi-stack-row" style="margin-bottom:0;" onclick="App.navigate('unifi-monitoring')">
          <div style="font-weight:600;">Clients</div>
          <div><strong>${has(u.active_clients) ? Number(u.active_clients).toLocaleString() : '—'}</strong></div>
        </div>
      `;
    } else {
      badge.className = 'badge badge-neutral';
      badge.textContent = f.unifi_status && f.unifi_status !== 'not_configured' ? String(f.unifi_status) : 'Not set up';
      body.innerHTML = `
        <div style="font-size:12.5px;color:var(--text-secondary);margin-bottom:10px;">
          Connect your UniFi controller to see gateway CPU, switches, access points and clients next to your test results.
        </div>
        <button class="btn btn-outline btn-sm btn-block" onclick="App.navigate('api-integrations')">Connect UniFi &rarr;</button>
      `;
    }
  },

  renderDashRecentRuns() {
    const tbody = document.getElementById('dashRecentRunsBody');
    if (!tbody) return;
    if (!this.runs || this.runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-secondary);padding:18px;">No tests yet — try a one-click test.</td></tr>`;
      return;
    }
    tbody.innerHTML = this.runs.slice(0, 5).map((r) => {
      const s = r.summary || {};
      const avgRx = this.fmtBps(s.avg_rx_bps || s.max_rx_bps || 0);
      const loss = s.drop_pct !== undefined && s.drop_pct !== null ? `${Number(s.drop_pct).toFixed(3)}%` : '—';
      const name = String(r.name || `Run #${r.id}`);
      return `
        <tr>
          <td><a href="javascript:void(0)" style="color:var(--primary);font-weight:600;text-decoration:none;" title="${this.esc(name)}" onclick="StudioPages.showRunDetailModal(${Number(r.id)})">${this.esc(name.length > 34 ? name.slice(0, 33) + '…' : name)}</a></td>
          <td style="font-weight:600;">${avgRx}</td>
          <td>${loss}</td>
          <td>${this.verdictBadge(s.verdict || r.verdict, s.thresholds_configured)}</td>
          <td><a class="btn btn-outline btn-sm" href="/api/runs/${Number(r.id)}/export/pdf?report_type=executive&inline=1" target="_blank">PDF</a></td>
        </tr>
      `;
    }).join('');
  },

  // =========================================================================
  // LIVE MONITORING (5 TABS)
  // =========================================================================
  ensureLiveMonChart() {
    const el = document.getElementById('liveMonMainChart');
    if (el && !this.charts.liveMon && window.echarts) {
      this.charts.liveMon = echarts.init(el);
    } else if (this.charts.liveMon) {
      setTimeout(() => this.charts.liveMon.resize(), 50);
    }
  },

  setLiveMonTab(tab) {
    this.liveMonTab = tab;
    document.querySelectorAll('#lmTabBar .subtab-btn').forEach((b) => {
      b.classList.toggle('active', b.getAttribute('data-lmtab') === tab);
    });
    this.updateLiveMonitoringView();
  },

  updateLiveMonitoringView() {
    this.ensureLiveMonChart();
    const f = this.latest || {};
    const h = this.history;

    document.getElementById('lmHeaderTitle').textContent = f.running
      ? `${f.test_name || 'Test'} — ${(f.phase_name || 'steady').replace(/_/g, ' ')}`
      : 'No test running';
    document.getElementById('lmHeaderSub').textContent = f.running
      ? `${this.fmtDurationClock(f.elapsed_sec)} elapsed • ${Number(f.simulated_users || 0).toLocaleString()} users • ${Number(f.emulated_client_ips || 0).toLocaleString()} client IPs • source: ${f.telemetry_source || f.traffic_engine || '—'}`
      : 'Start a test from Home or Run a Test. The last results stay on the chart below.';
    const ctrls = document.getElementById('lmControls');
    if (ctrls) ctrls.style.display = f.running ? 'flex' : 'none';

    const ch = this.charts.liveMon;
    const titleEl = document.getElementById('lmChartTitle');
    if (ch) {
      if (this.liveMonTab === 'performance') {
        titleEl.textContent = 'Real-Time Throughput (TX vs RX vs Target)';
        const useMbps = Math.max(...h.txGbps, 0) < 0.8 && (f.tx_bps || 0) > 0;
        const unit = useMbps ? 'Mbps' : 'Gbps';
        const mult = useMbps ? 1000 : 1;
        ch.setOption({
          animation: false,
          tooltip: { trigger: 'axis' },
          legend: { top: 0, right: 10 },
          grid: { top: 32, right: 24, bottom: 28, left: 56 },
          xAxis: { type: 'category', data: h.labels },
          yAxis: [{ type: 'value', name: unit, min: 0 }],
          series: [
            { name: `TX (${unit})`, type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#1769D2' }, areaStyle: { color: 'rgba(23,105,210,0.12)' }, data: h.txGbps.map((v) => +(v * mult).toFixed(3)) },
            { name: `RX (${unit})`, type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#10B981' }, data: h.rxGbps.map((v) => +(v * mult).toFixed(3)) },
            { name: `Target (${unit})`, type: 'line', showSymbol: false, lineStyle: { type: 'dashed', color: '#94A3B8' }, itemStyle: { color: '#94A3B8' }, data: h.targetGbps.map((v) => +(v * mult).toFixed(3)) },
          ],
        }, true);
      } else if (this.liveMonTab === 'flows') {
        titleEl.textContent = 'Stateful Concurrency: Active L4 Flows vs Established TCP Sessions vs CPS';
        ch.setOption({
          animation: false,
          tooltip: { trigger: 'axis' },
          legend: { top: 0, right: 10 },
          grid: { top: 32, right: 60, bottom: 28, left: 60 },
          xAxis: { type: 'category', data: h.labels },
          yAxis: [
            { type: 'value', name: 'Flows / Sessions', min: 0 },
            { type: 'value', name: 'CPS', min: 0 },
          ],
          series: [
            { name: 'Active L4 Flows', type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#1769D2' }, areaStyle: { color: 'rgba(23,105,210,0.1)' }, data: h.activeFlows },
            { name: 'Established TCP Sessions', type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#15803D' }, data: h.estSessions },
            { name: 'Connections/sec (CPS)', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, itemStyle: { color: '#D97706' }, data: h.cps },
          ],
        }, true);
      } else if (this.liveMonTab === 'latency') {
        titleEl.textContent = 'End-to-End Forwarding Latency (Avg, P95, P99) & Jitter (μs)';
        ch.setOption({
          animation: false,
          tooltip: { trigger: 'axis' },
          legend: { top: 0, right: 10 },
          grid: { top: 32, right: 24, bottom: 28, left: 56 },
          xAxis: { type: 'category', data: h.labels },
          yAxis: [{ type: 'value', name: 'Microseconds (μs)', min: 0 }],
          series: [
            { name: 'Avg Latency (μs)', type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#1769D2' }, data: h.latAvg },
            { name: 'P95 Latency (μs)', type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#0EA5E9' }, data: h.latP95 },
            { name: 'P99 Latency (μs)', type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#D97706' }, data: h.latP99 },
            { name: 'Jitter (μs)', type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#0D9488' }, data: h.jitter },
          ],
        }, true);
      } else if (this.liveMonTab === 'errors') {
        titleEl.textContent = 'Counter-Derived Dropped Packets & TCP Retransmissions';
        ch.setOption({
          animation: false,
          tooltip: { trigger: 'axis' },
          legend: { top: 0, right: 10 },
          grid: { top: 32, right: 24, bottom: 28, left: 60 },
          xAxis: { type: 'category', data: h.labels },
          yAxis: [{ type: 'value', name: 'Packets', min: 0 }],
          series: [
            { name: 'Dropped Packets', type: 'line', showSymbol: false, itemStyle: { color: '#DC2626' }, areaStyle: { color: 'rgba(220,38,38,0.1)' }, data: h.drops },
            { name: 'TCP Retransmissions', type: 'line', showSymbol: false, itemStyle: { color: '#D97706' }, data: h.tcpRexmt },
          ],
        }, true);
      } else if (this.liveMonTab === 'correlation') {
        titleEl.textContent = 'Synchronized TRex Load (Gbps) vs UniFi EFG / System CPU (%)';
        const hasUnifiCpu = h.unifiCpu.some((v) => v !== null);
        ch.setOption({
          animation: false,
          tooltip: { trigger: 'axis' },
          legend: { top: 0, right: 10 },
          grid: { top: 32, right: 56, bottom: 28, left: 56 },
          xAxis: { type: 'category', data: h.labels },
          yAxis: [
            { type: 'value', name: 'Gbps', min: 0 },
            { type: 'value', name: 'CPU %', min: 0, max: 100 },
          ],
          series: [
            { name: 'TRex TX (Gbps)', type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#1769D2' }, areaStyle: { color: 'rgba(23,105,210,0.1)' }, data: h.txGbps },
            hasUnifiCpu
              ? { name: 'UniFi EFG CPU (%)', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, itemStyle: { color: '#D97706' }, data: h.unifiCpu }
              : { name: 'R640 Generator CPU (%)', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, itemStyle: { color: '#64748B' }, data: h.r640Cpu },
          ],
        }, true);
      }
    }

    // Render 8 distinct non-conflated metric cards below chart
    const grid = document.getElementById('lmMetricsGrid');
    if (grid) {
      grid.innerHTML = `
        <div class="card"><div class="card-subtitle">Simulated Users</div><div class="kpi-value">${Number(f.simulated_users || 0).toLocaleString()}</div><div class="kpi-foot">Configured user personas</div></div>
        <div class="card"><div class="card-subtitle">Emulated Client IPs</div><div class="kpi-value">${Number(f.emulated_client_ips || 0).toLocaleString()}</div><div class="kpi-foot">Distinct L3 IPv4 sources</div></div>
        <div class="card"><div class="card-subtitle">Active L4 Flows</div><div class="kpi-value">${Number(f.active_flows || 0).toLocaleString()}</div><div class="kpi-foot">Open TCP + UDP flow table entries</div></div>
        <div class="card"><div class="card-subtitle">Established TCP Sessions</div><div class="kpi-value">${Number(f.established_sessions || 0).toLocaleString()}</div><div class="kpi-foot">Completed 3-way handshakes: ${Number(f.tcp_connects || 0).toLocaleString()}</div></div>
        <div class="card"><div class="card-subtitle">Connections / sec (CPS)</div><div class="kpi-value">${Number(f.cps || 0).toFixed(1)}</div><div class="kpi-foot">New session establishment rate</div></div>
        <div class="card"><div class="card-subtitle">P99 Tail Latency</div><div class="kpi-value">${Number(f.p99_lat_us || 0).toFixed(2)} <span class="kpi-unit">μs</span></div><div class="kpi-foot">Avg: ${Number(f.lat_avg_us || 0).toFixed(2)} μs | Jitter: ${Number(f.jitter_us || 0).toFixed(2)} μs</div></div>
        <div class="card"><div class="card-subtitle">Packet Loss &amp; TCP Drops</div><div class="kpi-value">${Number(f.drop_pct || 0).toFixed(4)} <span class="kpi-unit">%</span></div><div class="kpi-foot">TCP Drops: ${Number(f.tcp_drops || 0)} | Rexmits: ${Number(f.tcp_retransmits || 0)}</div></div>
        <div class="card"><div class="card-subtitle">UniFi Gateway CPU / RAM</div><div class="kpi-value">${f.unifi_gw_cpu != null ? f.unifi_gw_cpu.toFixed(0) + '%' : 'Unavailable'}</div><div class="kpi-foot">${f.unifi_connected ? 'Live UniFi API' : 'Connect UniFi API in Settings'}</div></div>
      `;
    }
  },

  // =========================================================================
  // TEST CONTROL ACTIONS
  // =========================================================================
  async startTestRequest(payload) {
    try {
      const res = await this.api('/api/test/start', { method: 'POST', body: JSON.stringify(payload) });
      if (!res || !res.run_id) {
        throw new Error((res && (res.error || res.detail || res.message)) || 'the server did not start a run');
      }
      this.toast(`Started test #${res.run_id}: ${res.name || payload.name || ''}`, 'success');
      return res;
    } catch (e) {
      this.toast(`Failed to start test: ${e.message}`, 'error');
      throw e;
    }
  },

  async quickStart10K() {
    return this.runPreset('efg10k');
  },

  async stopActiveTest(reason = 'completed') {
    try {
      await this.api('/api/test/stop', { method: 'POST', body: JSON.stringify({ status: reason }) });
      this.toast(reason === 'emergency_stopped' ? 'Emergency Stop executed immediately.' : 'Test stopped and saved.', 'info');
      this.refreshRunsSilent();
    } catch (e) {
      this.toast(`Stop error: ${e.message}`, 'error');
    }
  },

  async adjustLiveRate(pct) {
    try {
      await this.api('/api/test/rate', { method: 'POST', body: JSON.stringify({ rate_pct: Number(pct) }) });
    } catch (_) {}
  },

  showAlertsModal() {
    const f = this.latest || {};
    const alerts = f.alerts || [];
    const topo = f.topology_assessment || {};
    let html = '';
    if (alerts.length === 0) {
      html += `<div class="alert-banner success"><div><strong>No Active Hardware or Engine Alerts</strong><br/>Cisco TRex ZMQ RPC and R640 interfaces are operating normally.</div></div>`;
    } else {
      html += alerts.map((a) => `
        <div class="alert-banner ${a.level === 'critical' ? 'critical' : 'warning'}">
          <div><strong>[${a.source}]</strong> ${a.message}</div>
        </div>
      `).join('');
    }
    if (topo.honest_10g_explanation) {
      html += `<div class="alert-banner info"><div><strong>LAN-to-WAN EFG Topology Assessment</strong><br/>${topo.honest_10g_explanation}</div></div>`;
    }
    this.openModal('System & Topology Notifications', html);
  },
};

window.addEventListener('DOMContentLoaded', () => App.init());
