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
  run: { title: 'Run a Test', sub: 'Pick what you want to find out, then start the test', routes: ['test-picker', 'quick-test', 'stress-soak', 'rfc2544-benchmark', 'traffic-mix-builder', 'test-scheduler'], hidden: ['application-simulation', 'traffic-profiles'] },
  live: { title: 'Live View', sub: 'Watch the running test in real time', routes: ['live-monitoring'] },
  results: { title: 'Results & Reports', sub: 'Past tests, side-by-side comparison and PDF reports', routes: ['test-history', 'compare-tests', 'trends', 'reports-exports'] },
  network: { title: 'My Network', sub: 'UniFi devices, topology and server ports', routes: ['unifi-monitoring', 'network-topology', 'nics-ports'] },
  system: { title: 'System & Settings', sub: 'Server health, TRex engine, integrations and settings', routes: ['server-health', 'trex-engine', 'api-integrations', 'configuration', 'user-access', 'audit-logs'] },
};

// Short tab labels for each page
const ROUTE_LABELS = {
  'dashboard': 'Home',
  'live-monitoring': 'Live View',
  'test-picker': 'Choose a test',
  'quick-test': 'Custom test',
  'application-simulation': 'App simulation',
  'traffic-mix-builder': 'Traffic mix',
  'stress-soak': 'Load & breaking point',
  'rfc2544-benchmark': 'Speed benchmark',
  'traffic-profiles': 'Saved profiles',
  'test-scheduler': 'Schedule',
  'test-history': 'History',
  'compare-tests': 'Compare (before/after)',
  'trends': 'Internet Trends',
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

const sectionForRoute = (route) => Object.keys(SECTIONS).find((k) => SECTIONS[k].routes.includes(route) || (SECTIONS[k].hidden || []).includes(route));

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
    // Asks for 1 Gbps; the server caps it at 85% of the management link so SSH/UI stay usable
    payload: { name: 'Internet speed & quality', profile_id: 'internet_wan_mix', traffic_engine: 'internet_wan', test_mode: 'timed', duration_sec: 60, steady_sec: 60, target_gbps: 1.0, simulated_users: 500, simulated_devices: 1000 },
  },
  {
    id: 'voice',
    title: 'Voice quality under load',
    desc: '1 min: phone-call packets while the link is ~95% full. Checks QoS.',
    payload: { name: 'Voice quality under load', profile_id: 'voice_under_load', traffic_engine: 'trex_stl', test_mode: 'timed', duration_sec: 60, steady_sec: 60, target_gbps: 0.95, simulated_users: 500, simulated_devices: 1000 },
  },
  {
    id: 'breakit',
    title: 'Test my network until it breaks',
    desc: 'One click: adds users and bandwidth until quality drops, then a detailed report. About 15–25 min.',
    action: 'runBreakIt',
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
    cpuTemp: [],
    mos: [],
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

  // ---- Plain-English quality ratings --------------------------------------
  // Returns { label, cls } for a measured value. Limits are typical enterprise/voice targets.
  rate(metric, v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return null;
    const n = Number(v);
    const scale = {
      latency_ms: [[10, 'Excellent'], [50, 'Good'], [150, 'Fair']],    // ITU-T G.114: keep voice under 150 ms
      jitter_ms: [[2, 'Excellent'], [10, 'Good'], [30, 'Fair']],
      loss_pct: [[0.0001, 'Excellent'], [0.1, 'Good'], [1, 'Fair']],
    }[metric];
    if (metric === 'mos') {
      if (n <= 0) return null;
      if (n >= 4.3) return { label: 'Excellent', cls: 'badge-success' };
      if (n >= 4.0) return { label: 'Good', cls: 'badge-success' };
      if (n >= 3.6) return { label: 'Fair', cls: 'badge-warning' };
      return { label: 'Poor', cls: 'badge-critical' };
    }
    if (!scale) return null;
    for (const [limit, label] of scale) {
      if (n <= limit) return { label, cls: label === 'Fair' ? 'badge-warning' : 'badge-success' };
    }
    return { label: 'Poor', cls: 'badge-critical' };
  },

  rateBadge(metric, v) {
    const r = this.rate(metric, v);
    return r ? `<span class="badge ${r.cls} rate-badge">${r.label}</span>` : '';
  },

  // One-sentence verdict for a finished run, in plain words
  plainSummary(run) {
    const s = run.summary || {};
    if (!s.sample_count) return 'No measurements were recorded for this test.';
    const parts = [];
    parts.push(`Delivered ${this.fmtBps(s.avg_rx_bps)} on average (peak ${this.fmtBps(s.max_rx_bps)})`);
    const loss = Number(s.drop_pct || 0);
    parts.push(loss === 0 ? 'with no packet loss' : `with ${loss.toFixed(3)}% packet loss (${(this.rate('loss_pct', loss) || {}).label || ''})`.trim());
    const lat = Number(s.lat_avg_us || 0) / 1000;
    if (lat > 0) parts.push(`latency ${lat < 1 ? lat.toFixed(2) : lat.toFixed(1)} ms (${this.rate('latency_ms', lat).label.toLowerCase()})`);
    if (Number(s.mos_avg) > 0) parts.push(`estimated call quality ${Number(s.mos_avg).toFixed(2)}/5 (${this.rate('mos', s.mos_avg).label.toLowerCase()})`);
    if (Number(s.peak_active_flows) > 0) parts.push(`${Number(s.peak_active_flows).toLocaleString()} connections open at the peak`);
    return `${parts.join(', ')}.`;
  },

  // Where does test traffic actually go right now?
  trafficPath(f, engine) {
    const eng = engine || (f && f.traffic_engine);
    if (eng === 'internet_wan') return { cls: 'path-real', text: 'Through your gateway to the internet', tip: 'Real downloads, DNS and pings leave via the management port and your gateway.' };
    const mode = ((f && f.topology_assessment) || {}).active_mode_code;
    if (mode === 'physical_lan_wan') return { cls: 'path-real', text: 'Through your gateway (test ports cabled)', tip: 'TRex sends traffic out one test port and receives it on the other, through the gateway.' };
    return { cls: 'path-internal', text: 'Inside this server only — not through your gateway', tip: 'Test ports eno1–eno4 have no cable, so TRex uses an internal loopback. Results show what the server can generate, not what your firewall can handle. Cable eno1/eno2 to the gateway to test it.' };
  },

  pathBadge(f, engine) {
    const p = this.trafficPath(f, engine);
    return `<span class="path-badge ${p.cls}" title="${this.esc(p.tip)}">${p.cls === 'path-real' ? '&#9679;' : '&#9888;'} ${p.text}</span>`;
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
        ['dashTp', 'dashLat', 'dashFlow', 'dashLoad', 'dashRecent'].forEach((k) => this.charts[k] && this.charts[k].resize());
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
    if (res.status === 401) {
      // Session missing/expired (or password changed elsewhere): back to the login screen
      location.href = '/login';
      throw new Error('Not logged in');
    }
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
    document.querySelector('#appModalBackdrop .modal-box')?.classList.remove('wide');
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
      // The one-click breaking-point test goes first
      const ordered = [...HOME_PRESETS].sort((a, b) => (b.id === 'breakit') - (a.id === 'breakit'));
      list.innerHTML = ordered.map((p) => `
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
    if (p.action) return this[p.action]();
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

  // ---- One-click "test my network until it breaks" -------------------------
  async runBreakIt() {
    const f = this.latest || {};
    if (f.running || (f.capacity || {}).running) {
      this.toast('A test is already running. Stop it first.', 'error');
      return;
    }
    const path = this.trafficPath(f, 'trex_astf');
    const msg = [
      'Test my network until it breaks?',
      '',
      '• Starts at 10,000 users and adds 10,000 per step (up to 100,000).',
      '• Bandwidth grows with the users (20 kbps each: 0.2 Gbps at 10K, 2 Gbps at 100K).',
      '• Stops as soon as packet loss goes over 0.5%, latency over 50 ms, or less than 95% of traffic gets through — then narrows down the exact limit.',
      '• Takes about 15–25 minutes. You get a detailed report at the end.',
      path.cls === 'path-internal' ? '\nNote: the test ports are not cabled, so this will find the limit of the test server, not your gateway.' : '',
    ].join('\n');
    if (!confirm(msg)) return;
    try {
      await this.api('/api/capacity/start', {
        method: 'POST',
        body: JSON.stringify({
          start_users: 10000, step_users: 10000, max_users: 100000, step_sec: 45, per_user_kbps: 20,
          max_loss_pct: 0.5, max_latency_ms: 50, min_rx_ratio: 0.95, refine_steps: 2, label: 'One-click breaking-point test',
        }),
      });
      this.toast('Started. Watch the progress here on Home or in Live View.', 'success');
    } catch (e) {
      this.toast(`Could not start: ${e.message}`, 'error');
    }
  },

  openBreakItReport(id) {
    window.open(`/api/capacity/report.pdf${id ? `?id=${encodeURIComponent(id)}` : ''}`, '_blank');
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
    ws.onclose = (ev) => {
      if (ev && ev.code === 4401) {
        location.href = '/login';
        return;
      }
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
        const gwCpu = f.unifi_gw_cpu ?? (f.unifi_connected ? (f.unifi_summary || {}).gw_cpu_pct : null);
        h.unifiCpu.push(gwCpu !== null && gwCpu !== undefined ? Number(gwCpu) : null);
        h.cpuTemp.push(f.sensors && f.sensors.cpu_max_c != null ? Number(f.sensors.cpu_max_c) : null);
        h.mos.push(f.mos_score ? Number(Number(f.mos_score).toFixed(2)) : null);
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

  // Colour a temperature: green / amber / red. Limits differ per sensor.
  tempSpan(c, warn = 70, hot = 85) {
    if (c === null || c === undefined || Number.isNaN(Number(c))) return '';
    const v = Number(c);
    const cls = v >= hot ? 'hot' : v >= warn ? 'warm' : 'ok';
    return `<span class="temp ${cls}">${v.toFixed(0)}°C</span>`;
  },

  pctSpan(label, v, warn = 75, hot = 90) {
    if (v === null || v === undefined) return '';
    const n = Number(v);
    const cls = n >= hot ? 'hot' : n >= warn ? 'warm' : '';
    return `${label} <strong class="${cls}">${n.toFixed(0)}%</strong>`;
  },

  updateHealthChips(f) {
    // --- R640 server ---
    const s = f.sensors || {};
    const srv = document.getElementById('hdrServerSub');
    if (srv) {
      const parts = [this.pctSpan('CPU', f.cpu_pct), this.pctSpan('RAM', f.ram_pct)];
      if (s.cpu_max_c != null) parts.push(this.tempSpan(s.cpu_max_c, 70, 85));
      srv.innerHTML = parts.filter(Boolean).join(' · ') || '—';
      const tip = [
        `CPU ${Number(f.cpu_pct || 0).toFixed(0)}% · RAM ${Number(f.ram_pct || 0).toFixed(0)}%${f.ram_total_gb ? ` of ${Math.round(f.ram_total_gb)} GB` : ''}`,
        f.storage && f.storage.percent != null ? `Disk ${f.storage.percent}% used` : '',
        ...(s.cpu_packages || []).map((c) => `${c.label} temp ${c.c}°C`),
        s.inlet_c != null ? `Inlet (room) ${s.inlet_c}°C` : '',
        s.exhaust_c != null ? `Exhaust ${s.exhaust_c}°C` : '',
        s.nvme_c != null ? `NVMe drive ${s.nvme_c}°C` : '',
        ...(s.nics || []).map((n) => `NIC ${n.name} ${n.c}°C`),
        s.fan_avg_rpm != null ? `Fans avg ${s.fan_avg_rpm.toLocaleString()} RPM` : '',
        s.power_w != null ? `Power ${s.power_w} W` : '',
      ].filter(Boolean);
      document.getElementById('hdrServerChip').title = `${tip.join('\n')}\n\nClick for full server health`;
      const hot = (s.cpu_max_c != null && s.cpu_max_c >= 85) || (s.inlet_c != null && s.inlet_c >= 35);
      document.getElementById('hdrServerChip').classList.toggle('chip-alert', !!hot);
    }

    // --- UniFi gateway (EFG): only when the UniFi API is connected ---
    const efg = document.getElementById('hdrEfgChip');
    if (efg) {
      const u = f.unifi_summary || {};
      const show = !!f.unifi_connected && (u.gw_name || u.gw_cpu_pct != null);
      efg.style.display = show ? '' : 'none';
      if (show) {
        document.getElementById('hdrEfgName').textContent = u.gw_model ? `${u.gw_model}` : (u.gw_name || 'Gateway');
        const parts = [this.pctSpan('CPU', u.gw_cpu_pct), this.pctSpan('RAM', u.gw_mem_pct)];
        if (u.gw_temp_c != null) parts.push(this.tempSpan(u.gw_temp_c, 75, 90));
        if (!u.gw_online) parts.unshift('<strong class="hot">offline</strong>');
        document.getElementById('hdrEfgSub').innerHTML = parts.filter(Boolean).join(' · ') || 'connected';
        const up = u.gw_uptime_sec ? `${Math.floor(u.gw_uptime_sec / 86400)}d ${Math.floor((u.gw_uptime_sec % 86400) / 3600)}h` : null;
        efg.title = [
          u.gw_name, u.gw_model, u.gw_ip, u.gw_firmware ? `Firmware ${u.gw_firmware}` : '',
          u.gw_cpu_pct != null ? `CPU ${Number(u.gw_cpu_pct).toFixed(0)}%` : '', u.gw_mem_pct != null ? `RAM ${Number(u.gw_mem_pct).toFixed(0)}%` : '',
          ...(u.gw_temperatures || []).map((t) => `${t.name} ${t.c}°C`),
          u.wan_rx_bps != null ? `WAN ↓ ${this.fmtBps(u.wan_rx_bps)} ↑ ${this.fmtBps(u.wan_tx_bps || 0)}` : '',
          u.wan_latency_ms != null ? `WAN latency ${u.wan_latency_ms} ms` : '',
          u.active_sessions != null ? `${Number(u.active_sessions).toLocaleString()} firewall sessions` : '',
          up ? `Up ${up}` : '',
        ].filter(Boolean).join('\n') + '\n\nClick for UniFi details';
        efg.classList.toggle('chip-alert', !u.gw_online || (u.gw_cpu_pct != null && u.gw_cpu_pct >= 90) || (u.gw_temp_c != null && u.gw_temp_c >= 90));
      }
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
    this.updateHealthChips(f);

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
      this.charts.dashTp = this.trackHover(echarts.init(tpEl));
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
    for (const [key, id] of [['dashLat', 'dashLatChart'], ['dashFlow', 'dashFlowChart'], ['dashLoad', 'dashLoadChart'], ['dashRecent', 'dashRecentChart']]) {
      const el = document.getElementById(id);
      if (el && window.echarts) this.charts[key] = this.trackHover(echarts.init(el));
    }
  },

  // Shared look for the small Home charts
  miniChartBase(yAxis, labels) {
    const axisLabel = { color: '#64748B', fontSize: 10.5 };
    return {
      animation: false,
      grid: { top: 26, right: Array.isArray(yAxis) && yAxis.length > 1 ? 42 : 12, bottom: 22, left: 44 },
      tooltip: { trigger: 'axis', confine: true },
      legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 7, textStyle: { color: '#475569', fontSize: 10.5 } },
      xAxis: { type: 'category', boundaryGap: false, data: labels || this.history.labels, axisLabel: { ...axisLabel, hideOverlap: true }, axisLine: { lineStyle: { color: '#DFE5ED' } } },
      yAxis: (Array.isArray(yAxis) ? yAxis : [yAxis]).map((y, i) => ({
        type: 'value', min: 0, splitLine: { show: i === 0, lineStyle: { color: '#EEF2F6' } },
        nameTextStyle: { color: '#64748B', fontSize: 10 }, axisLabel, ...y,
      })),
    };
  },

  // When nothing is running, show the latest finished test instead of flat zero lines
  async loadLastRunForHome() {
    const last = (this.runs || []).find((r) => (r.summary || {}).sample_count > 1 && r.status !== 'running');
    if (!last || (this._lastRun && this._lastRun.id === last.id)) return;
    try {
      const run = await this.api(`/api/runs/${last.id}`);
      const ss = run.samples || [];
      this._lastRun = {
        id: run.id, name: run.name,
        labels: ss.map((s) => `${s.elapsed_sec}s`),
        latAvg: ss.map((s) => Number(s.lat_avg_us || 0)), latP99: ss.map((s) => Number(s.p99_lat_us || 0)), jitter: ss.map((s) => Number(s.jitter_us || 0)),
        activeFlows: ss.map((s) => Number(s.active_flows || 0)), estSessions: ss.map((s) => Number(s.established_sessions || 0)), cps: ss.map((s) => Number(s.cps || 0)),
      };
      if (this.latest && !this.latest.running) this.updateDashMiniCharts(this.latest);
    } catch (_) {}
  },

  updateDashMiniCharts(f) {
    const live = this.history;
    // Idle and no live measurements in the buffer -> chart the latest finished test
    const liveHasData = live.latAvg.some((v) => v > 0) || live.activeFlows.some((v) => v > 0);
    const useLast = !f.running && !liveHasData && this._lastRun;
    const h = useLast ? { ...live, ...this._lastRun } : live;
    const lastNote = useLast ? `last test #${this._lastRun.id}` : '';
    const line = (name, data, color, extra = {}) => ({ name, type: 'line', smooth: true, showSymbol: false, connectNulls: true, lineStyle: { width: 1.8, color }, itemStyle: { color }, data, ...extra });

    // Latency & jitter (ms when large, μs otherwise)
    if (this.charts.dashLat && !this.charts.dashLat.__hover) {
      const maxLat = Math.max(0, ...h.latAvg, ...h.latP99);
      const ms = maxLat >= 2000;
      const k = ms ? 1 / 1000 : 1;
      const u = ms ? 'ms' : 'μs';
      const sc = (arr) => arr.map((v) => +(v * k).toFixed(ms ? 2 : 1));
      this.charts.dashLat.setOption({
        ...this.miniChartBase({ name: u }, h.labels),
        series: [
          line('Avg', sc(h.latAvg), '#1769D2', { areaStyle: { color: 'rgba(23,105,210,0.08)' } }),
          line('P99', sc(h.latP99), '#D97706'),
          line('Jitter', sc(h.jitter), '#0D9488', { lineStyle: { width: 1.5, color: '#0D9488', type: 'dashed' } }),
        ],
      }, true);
      const last = h.latAvg[h.latAvg.length - 1] || 0;
      document.getElementById('dashLatSub').textContent = useLast ? lastNote : f.running && last ? `${(last * k).toFixed(ms ? 2 : 1)} ${u} avg${f.mos_score ? ` · MOS ${Number(f.mos_score).toFixed(2)}` : ''}` : '';
    }

    // Connections: active flows + established sessions, new connections/sec on the right
    if (this.charts.dashFlow && !this.charts.dashFlow.__hover) {
      this.charts.dashFlow.setOption({
        ...this.miniChartBase([{ name: 'flows' }, { name: '/s' }], h.labels),
        series: [
          line('Active flows', h.activeFlows, '#1769D2', { areaStyle: { color: 'rgba(23,105,210,0.08)' } }),
          line('TCP sessions', h.estSessions, '#15803D'),
          line('New/s', h.cps, '#D97706', { yAxisIndex: 1, lineStyle: { width: 1.5, color: '#D97706', type: 'dashed' } }),
        ],
      }, true);
      document.getElementById('dashFlowSub').textContent = useLast ? lastNote : f.running ? `${Number(f.active_flows || 0).toLocaleString()} flows · ${Number(f.cps || 0).toFixed(0)}/s` : '';
    }

    // Server CPU % (+ gateway CPU when UniFi is connected) and CPU temperature on the right
    if (this.charts.dashLoad && !this.charts.dashLoad.__hover) {
      const hg = live;
      const hasGw = hg.unifiCpu.some((v) => v !== null && v !== undefined);
      const hasTemp = hg.cpuTemp.some((v) => v !== null && v !== undefined);
      this.charts.dashLoad.setOption({
        ...this.miniChartBase([{ name: '%', max: 100 }, { name: '°C', min: 20, max: 90, show: hasTemp }], live.labels),
        series: [
          line('R640 CPU', hg.r640Cpu, '#64748B', { areaStyle: { color: 'rgba(100,116,139,0.08)' } }),
          ...(hasGw ? [line('Gateway CPU', hg.unifiCpu, '#7C3AED')] : []),
          ...(hasTemp ? [line('CPU temp', hg.cpuTemp, '#DC2626', { yAxisIndex: 1, lineStyle: { width: 1.5, color: '#DC2626', type: 'dashed' } })] : []),
        ],
      }, true);
      const s = f.sensors || {};
      document.getElementById('dashLoadSub').textContent = [
        `${Number(f.cpu_pct || 0).toFixed(0)}% CPU`,
        s.cpu_max_c != null ? `${Number(s.cpu_max_c).toFixed(0)}°C` : '',
        s.inlet_c != null ? `inlet ${Number(s.inlet_c).toFixed(0)}°C` : '',
      ].filter(Boolean).join(' · ');
    }
  },

  // Bar chart of the last tests: received throughput (bars) and loss (line) — click a bar to open the test
  renderDashRecentChart() {
    const ch = this.charts.dashRecent;
    if (!ch) return;
    const runs = (this.runs || []).filter((r) => (r.summary || {}).sample_count).slice(0, 12).reverse();
    if (!runs.length) {
      ch.clear();
      return;
    }
    const maxBps = Math.max(...runs.map((r) => Number(r.summary.avg_rx_bps || 0)));
    const gbps = maxBps >= 1e9;
    const k = gbps ? 1e9 : 1e6;
    const engineColor = { trex_astf: '#1769D2', trex_stl: '#0EA5E9', internet_wan: '#10B981', hybrid: '#7C3AED' };
    ch.setOption({
      animation: false,
      grid: { top: 22, right: 40, bottom: 20, left: 44 },
      tooltip: {
        trigger: 'axis', confine: true,
        formatter: (ps) => {
          const r = runs[ps[0].dataIndex];
          const s = r.summary || {};
          return `<strong>#${r.id} ${this.esc(r.name)}</strong><br/>Received ${this.fmtBps(s.avg_rx_bps)}<br/>Loss ${Number(s.drop_pct || 0).toFixed(3)}%<br/>Latency ${this.fmtLatency(s.lat_avg_us).val} ${this.fmtLatency(s.lat_avg_us).unit}`;
        },
      },
      xAxis: { type: 'category', data: runs.map((r) => `#${r.id}`), axisLabel: { color: '#64748B', fontSize: 10 }, axisLine: { lineStyle: { color: '#DFE5ED' } } },
      yAxis: [
        { type: 'value', name: gbps ? 'Gbps' : 'Mbps', min: 0, nameTextStyle: { color: '#64748B', fontSize: 10 }, axisLabel: { color: '#64748B', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEF2F6' } } },
        { type: 'value', name: 'loss %', min: 0, nameTextStyle: { color: '#64748B', fontSize: 10 }, axisLabel: { color: '#64748B', fontSize: 10 }, splitLine: { show: false } },
      ],
      series: [
        { name: 'Received', type: 'bar', barMaxWidth: 22, data: runs.map((r) => ({ value: +(Number(r.summary.avg_rx_bps || 0) / k).toFixed(2), itemStyle: { color: engineColor[r.traffic_engine] || '#94A3B8', borderRadius: [3, 3, 0, 0] } })) },
        { name: 'Loss %', type: 'line', yAxisIndex: 1, symbolSize: 5, lineStyle: { color: '#DC2626', width: 1.5 }, itemStyle: { color: '#DC2626' }, data: runs.map((r) => +Number(r.summary.drop_pct || 0).toFixed(3)) },
      ],
    }, true);
    ch.off('click');
    ch.on('click', (p) => { const r = runs[p.dataIndex]; if (r) StudioPages.showRunDetailModal(r.id); });
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
    const cap = f.capacity || {};
    const capDone = !cap.running && ['limit_found', 'no_limit_found'].includes(cap.outcome) && cap.ended_at && (Date.now() / 1000 - cap.ended_at) < 7 * 86400;
    const runningKey = cap.running ? `cap-${cap.id}` : f.running ? `run-${f.run_id || f.test_name}` : `${f.trex_connected ? 'idle-ok' : 'idle-off'}-${capDone ? cap.id : ''}`;
    if (cap.running) {
      hero.className = 'hero-card running';
      heroTitle.textContent = 'Testing your network until it breaks…';
      const users = cap.current_users ? `${Number(cap.current_users).toLocaleString()} users` : 'starting';
      heroSub.innerHTML = `Step ${cap.current_step || 1} of up to ${cap.plan_len || '?'} — ${users}${cap.max_good_users ? ` · handled ${Number(cap.max_good_users).toLocaleString()} cleanly so far` : ''}. It stops by itself when quality drops, then builds the report.<div style="margin-top:6px;">${this.pathBadge(f, 'trex_astf')}</div>`;
    } else if (f.running) {
      hero.className = 'hero-card running';
      heroTitle.textContent = `Running: ${f.test_name || 'test'}`;
      const remaining = f.duration_sec ? ` of ${this.fmtDurationClock(f.duration_sec)}` : '';
      heroSub.innerHTML = `${this.esc((f.phase_name || 'steady').replace(/_/g, ' '))} • ${this.fmtDurationClock(f.elapsed_sec)}${remaining} • ${Number(f.simulated_users || 0).toLocaleString()} users<div style="margin-top:6px;">${this.pathBadge(f)}</div>`;
    } else if (f.trex_connected) {
      hero.className = 'hero-card idle';
      heroTitle.textContent = 'Ready to test';
      heroSub.innerHTML = (capDone
        ? `<strong>Last breaking-point test:</strong> ${this.esc(cap.message || '')} `
        : 'Pick a one-click test below, or choose one under <strong>Run a Test</strong>. ')
        + `<div style="margin-top:6px;">Lab tests right now: ${this.pathBadge(f, 'trex_astf')}</div>`;
    } else {
      hero.className = 'hero-card warn';
      heroTitle.textContent = 'TRex engine is offline';
      heroSub.innerHTML = 'Lab tests need the TRex engine. The <strong>Internet speed</strong> test still works. Open <strong>System &amp; Settings &rarr; TRex Engine</strong> to fix.';
    }
    if (this._heroKey !== runningKey) {
      this._heroKey = runningKey;
      heroAct.innerHTML = (cap.running || f.running)
        ? `<button class="btn btn-outline" onclick="App.navigate('live-monitoring')">Open Live View</button>
           <button class="btn btn-danger" onclick="App.stopActiveTest('completed')">&#9632; Stop</button>`
        : (f.trex_connected
          ? `${capDone ? `<button class="btn btn-outline" onclick="App.openBreakItReport(${Number(cap.id) || ''})">Open report</button>` : ''}
             <button class="btn btn-primary btn-breakit" onclick="App.runBreakIt()">&#9889; Test my network until it breaks</button>`
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
    document.getElementById('kpiLatFoot').innerHTML = f.lat_avg_us
      ? `${this.rateBadge('latency_ms', Number(f.lat_avg_us) / 1000)} Jitter ${jit.val} ${jit.unit}${f.mos_score ? ` • call quality ${Number(f.mos_score).toFixed(2)}/5` : ''}`
      : 'Measured during a test';

    const loss = Number(f.drop_pct || 0);
    document.getElementById('kpiLossVal').textContent = loss.toFixed(3);
    document.getElementById('kpiLossFoot').innerHTML = `${f.running ? this.rateBadge('loss_pct', loss) : ''} ${Number(f.dropped_packets || 0).toLocaleString()} packets dropped`;

    document.getElementById('kpiUsersVal').textContent = f.running ? Number(f.simulated_users || 0).toLocaleString() : '0';
    document.getElementById('kpiFlowsFoot').textContent = f.running
      ? `${Number(f.active_flows || 0).toLocaleString()} active flows • ${Number(f.cps || 0).toFixed(0)} new/s`
      : 'Simulated users during a test';

    // --- Throughput chart (auto-scale Mbps vs Gbps) ---
    if (this.charts.dashTp && !this.charts.dashTp.__hover) {
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

    // --- Live mini charts (throttled to ~1/s when idle) ---
    const nowMs = Date.now();
    if (f.running || !this._miniTs || nowMs - this._miniTs > 1000) {
      this._miniTs = nowMs;
      this.updateDashMiniCharts(f);
    }

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
    this.renderDashRecentChart();
    this.loadLastRunForHome();
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
  // Pause live redraws while the mouse is over a chart; otherwise the tooltip vanishes on every update
  trackHover(ch) {
    if (!ch || ch.__hoverTracked) return ch;
    ch.__hoverTracked = true;
    const zr = ch.getZr();
    zr.on('mousemove', () => { ch.__hover = true; });
    zr.on('globalout', () => { ch.__hover = false; });
    return ch;
  },

  ensureLiveMonChart() {
    const el = document.getElementById('liveMonMainChart');
    if (el && !this.charts.liveMon && window.echarts) {
      this.charts.liveMon = this.trackHover(echarts.init(el));
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
    const remain = f.running && f.duration_sec ? Math.max(0, f.duration_sec - (f.elapsed_sec || 0)) : null;
    document.getElementById('lmHeaderSub').innerHTML = f.running
      ? `${this.fmtDurationClock(f.elapsed_sec)} elapsed${remain !== null ? ` • ${this.fmtDurationClock(remain)} left` : ''} • ${Number(f.simulated_users || 0).toLocaleString()} users <span style="margin-left:8px;">${this.pathBadge(f)}</span>`
      : `Start a test from <a href="javascript:void(0)" onclick="App.navigate('dashboard')">Home</a> or <a href="javascript:void(0)" onclick="App.navigate('test-picker')">Run a Test</a>. The chart keeps the last few minutes of data.`;
    const ctrls = document.getElementById('lmControls');
    if (ctrls) ctrls.style.display = f.running ? 'flex' : 'none';

    // Big live numbers + progress for the running test
    const liveBlock = document.getElementById('lmLiveBlock');
    if (liveBlock) {
      liveBlock.style.display = f.running ? '' : 'none';
      if (f.running) {
        const pct = f.duration_sec ? Math.min(100, (Number(f.elapsed_sec || 0) / f.duration_sec) * 100) : 0;
        document.getElementById('lmProgress').style.width = `${pct.toFixed(1)}%`;
        const tx = this.fmtBpsParts(f.tx_bps || 0);
        const rx = this.fmtBpsParts(f.rx_bps || 0);
        const lat = this.fmtLatency(f.lat_avg_us);
        const jit = this.fmtLatency(f.jitter_us);
        const delivered = f.tx_bps > 0 ? (Number(f.rx_bps || 0) / Number(f.tx_bps)) * 100 : null;
        const big = (label, val, unit, sub) => `<div class="score"><div class="score-label">${label}</div><div class="score-val">${val}<span class="score-unit">${unit}</span></div><div class="score-sub">${sub || ''}</div></div>`;
        document.getElementById('lmScoreboard').innerHTML = [
          big('Sending', tx.val, tx.unit, f.target_bps ? `target ${this.fmtBps(f.target_bps)}` : ''),
          big('Receiving', rx.val, rx.unit, delivered !== null ? `${Math.min(100, delivered).toFixed(1)}% delivered` : ''),
          big('Latency', lat.val, lat.unit, f.lat_avg_us ? this.rateBadge('latency_ms', Number(f.lat_avg_us) / 1000) : ''),
          big('Jitter', jit.val, jit.unit, f.mos_score ? `call quality ${Number(f.mos_score).toFixed(2)}/5` : (f.jitter_us ? this.rateBadge('jitter_ms', Number(f.jitter_us) / 1000) : '')),
          big('Packet loss', Number(f.drop_pct || 0).toFixed(3), '%', this.rateBadge('loss_pct', f.drop_pct || 0)),
          big('Open connections', Number(f.active_flows || 0).toLocaleString(), '', `${Number(f.cps || 0).toFixed(0)} new/s · ${Number(f.simulated_users || 0).toLocaleString()} users`),
        ].join('');
      }
    }

    const ch = this.charts.liveMon;
    const titleEl = document.getElementById('lmChartTitle');
    if (ch && !ch.__hover) {
      if (this.liveMonTab === 'performance') {
        titleEl.textContent = 'Speed: sent vs received vs target';
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
        titleEl.textContent = 'Connections: open now, established, and new per second';
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
        titleEl.textContent = 'Delay (latency) and jitter — lower is better';
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
        titleEl.textContent = 'Errors: lost packets and TCP retransmissions';
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
        titleEl.textContent = 'Test load vs gateway CPU (or server CPU if UniFi is not connected)';
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
      const lat = this.fmtLatency(f.lat_avg_us);
      const p99 = this.fmtLatency(f.p99_lat_us);
      const jit = this.fmtLatency(f.jitter_us);
      const u = f.unifi_summary || {};
      const gwCpu = f.unifi_gw_cpu ?? u.gw_cpu_pct;
      const tile = (title, value, foot, help) => `<div class="card" title="${this.esc(help)}"><div class="card-subtitle">${title} <span class="help-dot">?</span></div><div class="kpi-value">${value}</div><div class="kpi-foot">${foot}</div></div>`;
      grid.innerHTML = [
        tile('Received speed', `${this.fmtBpsParts(f.rx_bps).val} <span class="kpi-unit">${this.fmtBpsParts(f.rx_bps).unit}</span>`, `Sent ${this.fmtBps(f.tx_bps || 0)}`,
          'How much test traffic made it back. If it is much lower than what was sent, something in the path is dropping or slowing traffic.'),
        tile('Latency', `${lat.val} <span class="kpi-unit">${lat.unit}</span>`, `${f.running && f.lat_avg_us ? this.rateBadge('latency_ms', Number(f.lat_avg_us) / 1000) : ''} slowest 1%: ${p99.val} ${p99.unit}`,
          'Delay for a packet to cross the path. Lower is better. Under 10 ms is excellent on a local network; voice calls need under 150 ms.'),
        tile('Jitter', `${jit.val} <span class="kpi-unit">${jit.unit}</span>`, `${f.running && f.jitter_us ? this.rateBadge('jitter_ms', Number(f.jitter_us) / 1000) : ''} ${f.mos_score ? `call quality ${Number(f.mos_score).toFixed(2)}/5 ${this.rateBadge('mos', f.mos_score)}` : 'variation in delay'}`,
          'How much the delay changes from packet to packet. High jitter makes calls and video choppy. Call quality (MOS) is an estimate from 1 (bad) to 5 (perfect).'),
        tile('Packet loss', `${Number(f.drop_pct || 0).toFixed(3)} <span class="kpi-unit">%</span>`, `${f.running ? this.rateBadge('loss_pct', f.drop_pct || 0) : ''} ${Number(f.dropped_packets || 0).toLocaleString()} packets lost`,
          'Share of packets that never arrived. Anything above 0.1% is noticeable; above 1% hurts calls and downloads.'),
        tile('Users', Number(f.simulated_users || 0).toLocaleString(), `${Number(f.emulated_client_ips || 0).toLocaleString()} client IP addresses`,
          'Each simulated user gets its own IP address. This is not the same as open connections — see the next card.'),
        tile('Open connections', Number(f.active_flows || 0).toLocaleString(), `${Number(f.established_sessions || 0).toLocaleString()} TCP sessions established`,
          'Connections open right now. This is what fills a firewall\'s connection table.'),
        tile('New connections / sec', Number(f.cps || 0).toFixed(0), `${Number(f.tcp_retransmits || 0).toLocaleString()} TCP retransmissions`,
          'How fast new connections are being opened. Firewalls often struggle with a high rate of new connections before they struggle with bandwidth.'),
        tile('Gateway CPU', gwCpu != null ? `${Number(gwCpu).toFixed(0)}<span class="kpi-unit">%</span>` : '—', f.unifi_connected ? `RAM ${u.gw_mem_pct != null ? Number(u.gw_mem_pct).toFixed(0) + '%' : '—'}${u.gw_temp_c != null ? ` · ${Number(u.gw_temp_c).toFixed(0)}°C` : ''}` : `<a href="javascript:void(0)" onclick="App.navigate('api-integrations')">Connect UniFi</a> to see this`,
          'Load on your UniFi gateway during the test, read from the UniFi controller.'),
      ].join('');
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
