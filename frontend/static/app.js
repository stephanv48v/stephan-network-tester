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

const ROUTE_TITLES = {
  'dashboard': ['Cisco TRex Network Test Studio', 'Traffic Generation • 10,000-User EFG Performance Testing • UniFi Stack Monitoring'],
  'live-monitoring': ['Live Real-Time Monitoring', '250ms Stateful Flow, Session, Latency & UniFi Infrastructure Correlation'],
  'quick-test': ['Quick Test Launcher', 'Configure & Launch Enterprise User Traffic Against UniFi EFG'],
  'traffic-mix-builder': ['Traffic Mix Builder', 'Create Realistic Enterprise Profiles with Normalized 100% Application Allocations'],
  'application-simulation': ['Application Simulation (10,000 Users)', 'Stateful ASTF User Behaviours, Separate Flow/Session Accounting & Live WAN Mode'],
  'traffic-profiles': ['Traffic Profiles Library', 'Pre-Built Enterprise, Benchmark & Custom Saved Workload Profiles'],
  'rfc2544-benchmark': ['RFC 2544-Style Frame-Size Benchmarking', 'Automated Cisco TRex STL Multi-Frame-Size Throughput & Latency Sweeps'],
  'stress-soak': ['10,000-User EFG Stress & Soak Testing', 'Phased User Ramp-Up, Staged Load Steps (10%–100%) & Long-Duration Stability Runs'],
  'test-scheduler': ['Automated Test Scheduler', 'Recurring Cron & One-Shot Scheduled Validation Jobs'],
  'test-history': ['Recorded Test History', 'Immutable SQLite Run Archives, Telemetry Summaries & Threshold Verdicts'],
  'compare-tests': ['Compare Test Runs', 'Side-by-Side Throughput, Latency, Flow & Gateway Utilisation Delta Analysis'],
  'reports-exports': ['Client Reports & Exports', 'Multi-Page Light-Mode Executive & Technical PDF Reports, CSV & JSON Archives'],
  'unifi-monitoring': ['UniFi Stack Monitoring', 'Read-Only Local UniFi Network API & Site Manager Gateway, Switch, AP & Client Telemetry'],
  'network-topology': ['Interactive Network Topology', 'Live R640 <-> UniFi EFG <-> Switches <-> APs <-> WAN Path & Hardware Verification'],
  'nics-ports': ['NICs & Physical Ports', 'Dell PowerEdge R640 PCIe Inventory, Link Speeds & Management Safety'],
  'trex-engine': ['Cisco TRex Engine Control', 'Switch Between Stateful ASTF (--astf) & Stateless STL (--stl) Modes & Inspect /etc/trex_cfg.yaml'],
  'server-health': ['Dell PowerEdge R640 Server Health', '32-Thread Xeon Utilisation, HugePages, NVMe Storage & Live Field Diagnostics'],
  'configuration': ['Platform Configuration', 'Default Appliance Preferences, Safety Watchdogs & Operator Defaults'],
  'api-integrations': ['API & Telemetry Integrations', 'Configure Encrypted Local UniFi API Key, Site Manager Cloud Key & Read-Only SNMPv2c/v3'],
  'user-access': ['Operator & User Access', 'Manage Authorized Lab Administrators & Report Attribution Identities'],
  'audit-logs': ['System Audit Logs', 'Chronological Trail of Test Executions, Configuration Changes & Exports'],
};

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
    document.querySelectorAll('.nav-item[data-route]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.navigate(btn.getAttribute('data-route'));
      });
    });
  },

  navigate(route) {
    if (!ROUTE_TITLES[route]) route = 'dashboard';
    this.currentRoute = route;

    document.querySelectorAll('.nav-item[data-route]').forEach((b) => {
      b.classList.toggle('active', b.getAttribute('data-route') === route);
    });
    document.querySelectorAll('.page-section').forEach((sec) => {
      sec.classList.toggle('active', sec.id === `page-${route}`);
    });

    const [t, s] = ROUTE_TITLES[route];
    document.getElementById('topbarTitle').textContent = t;
    document.getElementById('topbarSubtitle').textContent = s;

    // Render route content
    if (route === 'dashboard') {
      this.refreshRunsSilent();
      setTimeout(() => {
        if (this.charts.dashTp) this.charts.dashTp.resize();
        if (this.charts.dashMix) this.charts.dashMix.resize();
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
    const sel = document.getElementById('qtDashProfile');
    if (!sel) return;
    sel.innerHTML = this.profiles
      .map((p) => `<option value="${p.id}" ${p.id === 'imix' ? 'selected' : ''}>${p.short_name || p.name}</option>`)
      .join('');
  },

  connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${location.host}/ws/telemetry`;
    const sbWs = document.getElementById('sbWsStatus');

    const ws = new WebSocket(wsUrl);
    this.ws = ws;

    ws.onopen = () => {
      if (sbWs) sbWs.innerHTML = `<span style="color:#4ADE80;">&#9679;</span> Live 250ms Stream`;
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

    const hwSub = document.getElementById('hdrHwSub');
    if (hwSub && f.ram_total_gb) {
      hwSub.textContent = `2 × Xeon | ${Math.round(f.ram_total_gb)} GB RAM`;
    }

    const stopBtn = document.getElementById('hdrEmergencyStop');
    if (stopBtn) stopBtn.style.display = f.running ? 'inline-flex' : 'none';

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
    const mixEl = document.getElementById('dashMixChart');
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
          { name: 'RX (Gbps)', type: 'line', smooth: true, showSymbol: false, lineStyle: { width: 2.0, color: '#2585E6' }, itemStyle: { color: '#2585E6' }, areaStyle: { color: 'rgba(37,133,230,0.06)' }, data: [] },
        ],
      });
    }

    if (mixEl && window.echarts) {
      this.charts.dashMix = echarts.init(mixEl);
    }
  },

  updateDashboardView(f) {
    const tgtBps = Math.max(1, Number(f.target_bps || 5e9));
    const txParts = this.fmtBpsParts(f.tx_bps || 0);
    const rxParts = this.fmtBpsParts(f.rx_bps || 0);
    const ppsParts = this.fmtPpsParts(f.tx_pps || 0);
    const tgtStr = this.fmtBps(tgtBps);
    const txPct = Math.min(100, ((f.tx_bps || 0) / tgtBps) * 100);
    const rxPct = Math.min(100, ((f.rx_bps || 0) / tgtBps) * 100);

    document.getElementById('kpiTxVal').textContent = txParts.val;
    document.getElementById('kpiTxUnit').textContent = txParts.unit;
    document.getElementById('kpiTxBar').style.width = `${txPct.toFixed(1)}%`;
    document.getElementById('kpiTxFoot').textContent = `Target: ${tgtStr} (${txPct.toFixed(1)}%)`;

    document.getElementById('kpiRxVal').textContent = rxParts.val;
    document.getElementById('kpiRxUnit').textContent = rxParts.unit;
    document.getElementById('kpiRxBar').style.width = `${rxPct.toFixed(1)}%`;
    document.getElementById('kpiRxFoot').textContent = `Target: ${tgtStr} (${rxPct.toFixed(1)}%)`;

    document.getElementById('kpiPpsVal').textContent = ppsParts.val;
    document.getElementById('kpiPpsUnit').textContent = ppsParts.unit;
    document.getElementById('kpiFlowsFoot').textContent = `Flows: ${Number(f.active_flows || 0).toLocaleString()} | TCP Est: ${Number(f.established_sessions || 0).toLocaleString()}`;

    document.getElementById('kpiLatVal').textContent = Number(f.lat_avg_us || 0).toFixed(2);
    document.getElementById('kpiLatFoot').textContent = `P95: ${Number(f.p95_lat_us || 0).toFixed(1)} μs | P99: ${Number(f.p99_lat_us || 0).toFixed(1)} μs`;

    document.getElementById('kpiJitVal').textContent = Number(f.jitter_us || 0).toFixed(2);
    document.getElementById('kpiJitFoot').textContent = `CPS: ${Number(f.cps || 0).toFixed(0)}/s | MOS: ${f.mos_score ? f.mos_score.toFixed(2) : '—'}`;

    document.getElementById('kpiLossVal').textContent = Number(f.drop_pct || 0).toFixed(4);
    document.getElementById('kpiLossFoot').textContent = `Dropped: ${Number(f.dropped_packets || 0).toLocaleString()} pkts`;

    // Active Test Status Card
    const runCard = document.getElementById('kpiRunCard');
    const runDot = document.getElementById('kpiRunBadgeDot');
    const runTitle = document.getElementById('kpiRunStatusTitle');
    const runSub = document.getElementById('kpiRunSubInfo');
    const runAct = document.getElementById('kpiRunActionArea');
    if (f.running) {
      runCard.className = 'kpi-card active-run-card running';
      runDot.style.background = '#15803D';
      runTitle.textContent = `Test Running (${(f.phase_name || 'steady').replace('_', ' ')})`;
      runSub.innerHTML = `<strong>${f.simulated_users.toLocaleString()} Users</strong> &bull; ${this.fmtDurationClock(f.elapsed_sec)}`;
      runAct.innerHTML = `<button class="btn btn-primary btn-sm btn-block" onclick="App.stopActiveTest('completed')">&#9632; Stop Test</button>`;
    } else {
      runCard.className = 'kpi-card active-run-card idle';
      runDot.style.background = '#64748B';
      runTitle.textContent = 'Idle — Ready';
      runSub.textContent = `${Number(f.simulated_users || 10000).toLocaleString()} Emulated Users Configured`;
      runAct.innerHTML = `<button class="btn btn-primary btn-sm btn-block" onclick="App.quickStart10K()">&#9654; Run 10K EFG Test</button>`;
    }

    // Update Throughput Chart (auto-scale Mbps vs Gbps)
    if (this.charts.dashTp) {
      const maxG = Math.max(...this.history.txGbps, 0.001);
      const useMbps = maxG < 0.8 && (f.running && f.tx_bps > 0);
      const unit = useMbps ? 'Mbps' : 'Gbps';
      const factor = useMbps ? 1000 : 1;
      this.charts.dashTp.setOption({
        xAxis: { data: this.history.labels },
        yAxis: { name: unit },
        series: [
          { name: `TX (${unit})`, data: this.history.txGbps.map((v) => Number((v * factor).toFixed(3))) },
          { name: `RX (${unit})`, data: this.history.rxGbps.map((v) => Number((v * factor).toFixed(3))) },
        ],
      });
    }
    document.getElementById('dashChartEngineLabel').textContent = `Engine: ${f.traffic_engine || 'trex_astf'} (${f.trex_daemon_mode || 'ASTF'})`;

    // Update Traffic Mix Donut
    if (this.charts.dashMix) {
      const mix = f.protocol_mix || {};
      const entries = Object.entries(mix).filter(([, v]) => Number(v) > 0).sort((a, b) => b[1] - a[1]);
      const top = entries.slice(0, 5);
      if (entries.length > 5) {
        const rest = entries.slice(5).reduce((acc, [, v]) => acc + Number(v), 0);
        if (rest > 0) top.push(['other', Number(rest.toFixed(1))]);
      }
      const pieData = top.map(([k, v]) => {
        const meta = WORKLOAD_COLORS[k] || { label: 'Other (VoIP, DNS, etc.)', color: '#94A3B8' };
        return { name: `${meta.label}  ${Number(v).toFixed(0)}%`, value: Number(v), itemStyle: { color: meta.color } };
      });
      const centerVal = f.running ? `${txParts.val} ${txParts.unit}` : '100% Mix';
      this.charts.dashMix.setOption({
        animation: false,
        tooltip: { trigger: 'item', formatter: '{b}' },
        legend: { orient: 'vertical', right: 0, top: 'middle', icon: 'circle', itemWidth: 9, itemHeight: 9, textStyle: { color: '#17243A', fontSize: 11.5 } },
        title: {
          text: centerVal,
          subtext: f.running ? 'Live Total' : `${Number(f.simulated_users || 10000).toLocaleString()} Users`,
          left: '25%',
          top: '39%',
          textAlign: 'center',
          textStyle: { fontSize: 14.5, fontWeight: 800, color: '#17243A' },
          subtextStyle: { fontSize: 11, color: '#64748B' },
        },
        series: [{
          type: 'pie',
          radius: ['52%', '76%'],
          center: ['26%', '50%'],
          avoidLabelOverlap: false,
          label: { show: false },
          itemStyle: { borderColor: '#FFFFFF', borderWidth: 2 },
          data: pieData,
        }],
      });
    }

    // Update UniFi Stack Card
    this.renderDashUniFiStack(f);

    // Update NICs Table
    this.renderDashNicTable(f.interfaces || []);

    // Update System Health Strip
    const cpu = Number(f.cpu_pct || 0);
    const ram = Number(f.ram_pct || 0);
    const disk = (f.storage && f.storage.percent) || 6;
    document.getElementById('hlthCpuTxt').textContent = `${cpu.toFixed(0)}%`;
    document.getElementById('hlthCpuBar').style.width = `${Math.min(100, cpu)}%`;
    document.getElementById('hlthRamTxt').textContent = `${ram.toFixed(0)}% (${f.ram_used_gb || 0} / ${Math.round(f.ram_total_gb || 500)} GB)`;
    document.getElementById('hlthRamBar').style.width = `${Math.min(100, ram)}%`;
    if (f.storage) {
      document.getElementById('hlthDiskTxt').textContent = `${disk.toFixed(0)}% (${f.storage.used_gb} / ${f.storage.total_gb} GB)`;
      document.getElementById('hlthDiskBar').style.width = `${Math.min(100, disk)}%`;
    }

    const alerts = f.alerts || [];
    const sumDot = document.getElementById('hlthSummaryDot');
    const sumTitle = document.getElementById('hlthSummaryTitle');
    const sumSub = document.getElementById('hlthSummarySub');
    if (alerts.length > 0) {
      sumDot.className = 'status-chip-dot warn';
      sumTitle.textContent = `${alerts.length} Hardware / Link Notice`;
      sumSub.textContent = alerts[0].message.slice(0, 72) + '...';
    } else {
      sumDot.className = 'status-chip-dot';
      sumTitle.textContent = 'All Systems Operational';
      sumSub.textContent = 'TRex Engine, NICs & Monitoring running normally.';
    }
  },

  renderDashUniFiStack(f) {
    const badge = document.getElementById('dashUnifiBadge');
    const body = document.getElementById('dashUnifiStackBody');
    if (!badge || !body) return;

    const u = f.unifi_summary || {};
    if (f.unifi_connected) {
      badge.className = 'badge badge-success';
      badge.textContent = '● Connected';
      const gwCpu = u.gw_cpu_pct !== null && u.gw_cpu_pct !== undefined ? `${Number(u.gw_cpu_pct).toFixed(0)}%` : 'Unavailable';
      const gwMem = u.gw_mem_pct !== null && u.gw_mem_pct !== undefined ? `${Number(u.gw_mem_pct).toFixed(0)}%` : 'Unavailable';
      const wanRate = u.wan_rx_bps !== null && u.wan_rx_bps !== undefined ? this.fmtBps((u.wan_rx_bps || 0) + (u.wan_tx_bps || 0)) : 'Unavailable';
      body.innerHTML = `
        <div class="unifi-stack-row" onclick="App.navigate('unifi-monitoring')">
          <div>
            <div style="font-weight:700;font-size:13px;"><span style="color:#15803D;">&#9679;</span> ${u.gw_name || 'Enterprise Fortress Gateway (EFG)'}</div>
            <div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;">CPU <strong>${gwCpu}</strong> | RAM <strong>${gwMem}</strong> | WAN <strong>${wanRate}</strong></div>
          </div>
          <span style="color:var(--text-secondary);">&rsaquo;</span>
        </div>
        <div class="unifi-stack-row" onclick="App.navigate('unifi-monitoring')">
          <div style="font-weight:600;">Switches</div>
          <div><strong style="color:#15803D;">${u.switches_online ?? 0} / ${u.switches_total ?? 0}</strong> Online &rsaquo;</div>
        </div>
        <div class="unifi-stack-row" onclick="App.navigate('unifi-monitoring')">
          <div style="font-weight:600;">Access Points</div>
          <div><strong style="color:#15803D;">${u.aps_online ?? 0} / ${u.aps_total ?? 0}</strong> Online &rsaquo;</div>
        </div>
        <div class="unifi-stack-row" style="margin-bottom:0;" onclick="App.navigate('unifi-monitoring')">
          <div style="font-weight:600;">Clients (Active)</div>
          <div><strong>${u.active_clients !== null && u.active_clients !== undefined ? Number(u.active_clients).toLocaleString() : 'Unavailable'}</strong> &rsaquo;</div>
        </div>
      `;
    } else {
      badge.className = 'badge badge-neutral';
      badge.textContent = f.unifi_status || 'Not Configured';
      body.innerHTML = `
        <div class="unifi-stack-row" onclick="App.navigate('network-topology')">
          <div>
            <div style="font-weight:700;font-size:13px;"><span style="color:#15803D;">&#9679;</span> Gateway Reachable (10.20.30.1)</div>
            <div style="font-size:11.5px;color:var(--text-secondary);">Ubiquiti OUI detected on LAN &bull; Connect API Key for EFG CPU/RAM</div>
          </div>
          <span style="color:var(--text-secondary);">&rsaquo;</span>
        </div>
        <div style="padding:10px 12px;background:#F8FAFC;border:1px dashed var(--border-color);border-radius:8px;margin-top:8px;">
          <div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px;">
            Connect a read-only Local UniFi Network API key (<code>X-API-KEY</code>) to stream live EFG CPU, memory, switch port utilisation, APs, and active client telemetry.
          </div>
          <button class="btn btn-outline btn-sm btn-block" onclick="App.navigate('api-integrations')">Configure UniFi API &amp; SNMP &rarr;</button>
        </div>
      `;
    }
  },

  renderDashNicTable(ifaces) {
    const tbody = document.getElementById('dashNicTableBody');
    const badge = document.getElementById('dashNicCountBadge');
    if (!tbody) return;
    const upCount = ifaces.filter((i) => i.operstate === 'up').length;
    if (badge) badge.textContent = `${upCount} / ${ifaces.length} Up`;

    tbody.innerHTML = ifaces.slice(0, 6).map((nic, idx) => {
      const isUp = nic.operstate === 'up';
      const spd = nic.speed_mbps ? (nic.speed_mbps >= 1000 ? `${nic.speed_mbps / 1000} Gbps` : `${nic.speed_mbps} Mbps`) : 'Unplugged';
      return `
        <tr>
          <td><span class="port-pill ${isUp ? '' : 'down'}">P${idx + 1}</span></td>
          <td><strong>${nic.ifname}</strong> ${nic.is_management ? '<span class="badge badge-info" style="font-size:10px;padding:1px 5px;">MGMT</span>' : ''}</td>
          <td>${spd}</td>
          <td>${isUp ? '<span style="color:#15803D;font-weight:600;">&#9679; Up</span>' : '<span style="color:#64748B;">&#9679; Down</span>'}</td>
          <td>${this.fmtBps(nic.live_tx_bps || 0)}</td>
          <td>${this.fmtBps(nic.live_rx_bps || 0)}</td>
        </tr>
      `;
    }).join('');
  },

  renderDashRecentRuns() {
    const tbody = document.getElementById('dashRecentRunsBody');
    if (!tbody) return;
    if (!this.runs || this.runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-secondary);padding:18px;">No recorded test runs yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = this.runs.slice(0, 5).map((r) => {
      const s = r.summary || {};
      const avgRx = this.fmtBps(s.avg_rx_bps || s.max_rx_bps || 0);
      const lat = s.lat_avg_us ? `${Number(s.lat_avg_us).toFixed(1)} μs` : '—';
      const loss = s.drop_pct !== undefined ? `${Number(s.drop_pct).toFixed(4)}%` : '0.0000%';
      return `
        <tr>
          <td><a href="javascript:void(0)" style="color:var(--primary);font-weight:600;text-decoration:none;" onclick="StudioPages.showRunDetailModal(${r.id})">${r.name.slice(0, 30)}</a></td>
          <td>${Number(r.simulated_users || 0).toLocaleString()}</td>
          <td style="color:var(--primary);font-weight:600;">${avgRx}</td>
          <td>${lat}</td>
          <td>${loss}</td>
          <td>${this.verdictBadge(s.verdict || r.verdict, s.thresholds_configured)}</td>
          <td><a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/pdf?report_type=technical" target="_blank">PDF</a></td>
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
      ? `Live Test: ${f.test_name} (${(f.phase_name || 'steady').toUpperCase()})`
      : 'Live Monitoring — Ready';
    document.getElementById('lmHeaderSub').textContent = f.running
      ? `Engine: ${f.traffic_engine} | Simulated Users: ${Number(f.simulated_users || 0).toLocaleString()} | Client IPs: ${Number(f.emulated_client_ips || 0).toLocaleString()} | Elapsed: ${this.fmtDurationClock(f.elapsed_sec)}`
      : `Telemetry Source: ${f.telemetry_source || 'Cisco TRex Ready'}`;

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
      this.toast(`Started Run #${res.run_id}: ${res.name}`, 'success');
      return res;
    } catch (e) {
      this.toast(`Failed to start test: ${e.message}`, 'error');
      throw e;
    }
  },

  async quickStart10K() {
    await this.startTestRequest({
      scenario_id: 'scenario_10000_users',
      name: '10,000 Users — Primary EFG Acceptance Test',
      profile_id: 'imix',
      traffic_engine: 'trex_astf',
      test_mode: 'phased',
      simulated_users: 10000,
      simulated_devices: 20000,
      target_gbps: 5.0,
      ramp_up_sec: 20,
      steady_sec: 90,
      ramp_down_sec: 10,
    });
  },

  async startFromDashboardQuickTest() {
    const profile_id = document.getElementById('qtDashProfile').value;
    const simulated_users = parseInt(document.getElementById('qtDashUsers').value, 10) || 10000;
    const target_gbps = parseFloat(document.getElementById('qtDashTargetGbps').value) || 5.0;
    const duration_sec = parseInt(document.getElementById('qtDashDuration').value, 10) || 60;
    const traffic_engine = document.getElementById('qtDashEngine').value;

    await this.startTestRequest({
      profile_id,
      simulated_users,
      simulated_devices: simulated_users * 2,
      target_gbps,
      duration_sec,
      traffic_engine,
      test_mode: traffic_engine === 'trex_astf' ? 'phased' : 'timed',
      ramp_up_sec: traffic_engine === 'trex_astf' ? Math.min(15, Math.floor(duration_sec / 4)) : 0,
      steady_sec: traffic_engine === 'trex_astf' ? Math.max(10, duration_sec - 20) : duration_sec,
      ramp_down_sec: traffic_engine === 'trex_astf' ? 5 : 0,
    });
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
