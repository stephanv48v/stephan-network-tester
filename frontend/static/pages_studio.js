/* ==========================================================================
   Cisco TRex Network Test Studio — Test Studio (7 Pages) & Results (3 Pages)
   ========================================================================== */

const STUDIO_ROUTES = new Set([
  'quick-test',
  'traffic-mix-builder',
  'application-simulation',
  'traffic-profiles',
  'rfc2544-benchmark',
  'stress-soak',
  'test-scheduler',
  'test-history',
  'compare-tests',
  'reports-exports',
  'trends',
]);

const StudioPages = {
  mixDraft: {
    video_streaming: 25,
    m365_productivity: 15,
    teams_collab: 10,
    social_browsing: 15,
    messaging_chat: 10,
    web_browsing: 15,
    cloud_files: 3,
    voip_sip: 3,
    dns_queries: 2,
    gaming_realtime: 2,
    backups_storage: 0,
    bulk_downloads: 0,
  },
  mixChart: null,
  compareChart: null,
  rfcRunning: false,

  canHandle(route) {
    return STUDIO_ROUTES.has(route);
  },

  render(route) {
    switch (route) {
      case 'quick-test': return this.renderQuickTest();
      case 'traffic-mix-builder': return this.renderTrafficMixBuilder();
      case 'application-simulation': return this.renderApplicationSimulation();
      case 'traffic-profiles': return this.renderTrafficProfiles();
      case 'rfc2544-benchmark': return this.renderRfc2544();
      case 'stress-soak': return this.renderStressSoak();
      case 'test-scheduler': return this.renderScheduler();
      case 'test-history': return this.renderTestHistory();
      case 'compare-tests': return this.renderCompareTests();
      case 'reports-exports': return this.renderReportsExports();
      case 'trends': return this.renderTrends();
    }
  },

  // =========================================================================
  // 1. QUICK TEST (Full Studio Launcher + Pre-Check + Optional Thresholds)
  // =========================================================================
  renderQuickTest() {
    const el = document.getElementById('page-quick-test');
    const profOpts = App.profiles.map((p) => `<option value="${p.id}" ${p.id === 'imix' ? 'selected' : ''}>${p.name} (${p.traffic_engine})</option>`).join('');
    el.innerHTML = `
      <div class="grid-2">
        <div class="card">
          <div class="card-header">
            <div class="card-title">&#9654; Configure &amp; Launch Enterprise Test</div>
            <span class="badge badge-info">Independent Users &amp; Bandwidth</span>
          </div>

          <div class="form-group">
            <label class="form-label">Test Run Name</label>
            <input type="text" class="form-control" id="qtFullRunName" value="UniFi EFG — 10,000-User Enterprise Validation" />
          </div>

          <div class="grid-2" style="gap:12px;">
            <div class="form-group">
              <label class="form-label">Traffic Profile</label>
              <select class="form-control" id="qtFullProfile" onchange="StudioPages.onQuickTestProfileChange()">${profOpts}</select>
            </div>
            <div class="form-group">
              <label class="form-label">Traffic Engine</label>
              <select class="form-control" id="qtFullEngine" onchange="StudioPages.runPrecheckFromQuickTest()">
                <option value="trex_astf" selected>Cisco TRex ASTF (Stateful TCP/UDP Sessions)</option>
                <option value="trex_stl">Cisco TRex STL (Stateless Wire-Speed)</option>
                <option value="internet_wan">Live Internet / WAN Traffic (via 10.20.30.1)</option>
                <option value="hybrid">Hybrid (TRex + Live Internet/WAN)</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Simulated Concurrent Users</label>
              ${App.usersField('qtFullUsers', 10000)}
            </div>
            <div class="form-group">
              <label class="form-label">Target Throughput (Gbps)</label>
              <input type="number" class="form-control" id="qtFullGbps" min="0.01" max="20" step="0.05" value="5.00" />
            </div>
            <div class="form-group">
              <label class="form-label">Execution Mode</label>
              <select class="form-control" id="qtFullMode">
                <option value="phased" selected>Phased (Ramp-Up &rarr; Steady &rarr; Ramp-Down)</option>
                <option value="timed">Fixed Timed Duration</option>
                <option value="step_ramp">Staged Load Steps (10% &rarr; 100%)</option>
                <option value="continuous">Continuous Until Stopped</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Steady-State Duration (Seconds)</label>
              <input type="number" class="form-control" id="qtFullDuration" min="5" max="86400" value="90" />
            </div>
            <div class="form-group">
              <label class="form-label">Emulated Client IP Base (LAN Port 0)</label>
              <input type="text" class="form-control mono" id="qtFullSrcIp" value="16.0.0.1" />
            </div>
            <div class="form-group">
              <label class="form-label">802.1Q VLAN Tag (0 = Untagged) / DSCP</label>
              <div style="display:flex;gap:8px;">
                <input type="number" class="form-control" id="qtFullVlan" min="0" max="4094" value="0" placeholder="VLAN" />
                <input type="number" class="form-control" id="qtFullDscp" min="0" max="63" value="0" placeholder="DSCP" />
              </div>
            </div>
          </div>

          <div style="border-top:1px solid var(--border-color);padding-top:12px;margin-top:6px;">
            <label style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:12.5px;cursor:pointer;margin-bottom:10px;">
              <input type="checkbox" id="qtEnableThresholds" onchange="document.getElementById('qtThreshBox').style.display=this.checked?'grid':'none'" />
              <span>Enable Explicit Pass / Fail Acceptance Thresholds (Recommended for Client Reports)</span>
            </label>
            <div id="qtThreshBox" class="grid-3" style="display:none;gap:10px;">
              <div class="form-group">
                <label class="form-label">Min Avg RX (Mbps)</label>
                <input type="number" class="form-control" id="qtThrMinRx" value="500" />
              </div>
              <div class="form-group">
                <label class="form-label">Max Packet Loss (%)</label>
                <input type="number" class="form-control" id="qtThrMaxLoss" step="0.01" value="0.10" />
              </div>
              <div class="form-group">
                <label class="form-label">Max Avg Latency (μs)</label>
                <input type="number" class="form-control" id="qtThrMaxLat" value="2000" />
              </div>
            </div>
          </div>

          <div style="display:flex;gap:10px;margin-top:10px;">
            <button class="btn btn-outline" onclick="StudioPages.runPrecheckFromQuickTest()">&#10003; Run Pre-Test Check</button>
            <button class="btn btn-primary" style="flex:1;" onclick="StudioPages.launchFromQuickTest()">&#9654; Launch Test &amp; Open Live Monitor</button>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">&#128269; Pre-Flight Readiness &amp; EFG Path Verification</div>
          </div>
          <div id="qtPrecheckOutput">
            <div class="alert-banner">
              <div>
                <strong>Independent User &amp; Bandwidth Architecture</strong><br/>
                Simulated Users control the exact IPv4 endpoint pool (e.g. <code>16.0.0.1 – 16.0.39.16</code> for 10,000 users) and concurrent TCP/UDP flows, while Target Throughput independently paces CPS / stream rates. Click <strong>Run Pre-Test Check</strong> to verify hardware links and TRex status before execution.
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    this.runPrecheckFromQuickTest();
  },

  onQuickTestProfileChange() {
    const pid = document.getElementById('qtFullProfile')?.value;
    const prof = (App.profiles || []).find((p) => p.id === pid);
    if (prof) {
      const engEl = document.getElementById('qtFullEngine');
      const gbpsEl = document.getElementById('qtFullGbps');
      const usrEl = document.getElementById('qtFullUsers');
      const nameEl = document.getElementById('qtFullRunName');
      if (engEl && prof.traffic_engine) engEl.value = prof.traffic_engine;
      if (gbpsEl && prof.target_gbps) gbpsEl.value = Number(prof.target_gbps).toFixed(2);
      if (usrEl && prof.default_users) usrEl.value = prof.default_users;
      if (nameEl) nameEl.value = `${prof.short_name || prof.name} — EFG Validation`;
    }
    this.runPrecheckFromQuickTest();
  },

  _collectQuickTestPayload() {
    const thresholdsEnabled = document.getElementById('qtEnableThresholds')?.checked;
    const dur = parseInt(document.getElementById('qtFullDuration').value, 10) || 90;
    const mode = document.getElementById('qtFullMode').value;
    return {
      name: document.getElementById('qtFullRunName').value.trim(),
      profile_id: document.getElementById('qtFullProfile').value,
      traffic_engine: document.getElementById('qtFullEngine').value,
      simulated_users: App.readUsers('qtFullUsers'),
      target_gbps: parseFloat(document.getElementById('qtFullGbps').value) || 5.0,
      test_mode: mode,
      duration_sec: dur,
      steady_sec: dur,
      ramp_up_sec: mode === 'phased' ? Math.min(25, Math.max(5, Math.floor(dur * 0.2))) : 0,
      ramp_down_sec: mode === 'phased' ? 10 : 0,
      src_ip_start: document.getElementById('qtFullSrcIp').value.trim() || '16.0.0.1',
      vlan_id: parseInt(document.getElementById('qtFullVlan').value, 10) || 0,
      dscp: parseInt(document.getElementById('qtFullDscp').value, 10) || 0,
      thresholds: thresholdsEnabled
        ? {
            enabled: true,
            min_rx_mbps: parseFloat(document.getElementById('qtThrMinRx').value) || 100,
            max_loss_pct: parseFloat(document.getElementById('qtThrMaxLoss').value) ?? 0.1,
            max_avg_latency_us: parseFloat(document.getElementById('qtThrMaxLat').value) || 2000,
          }
        : null,
    };
  },

  async runPrecheckFromQuickTest() {
    const out = document.getElementById('qtPrecheckOutput');
    if (!out) return;
    try {
      const payload = this._collectQuickTestPayload();
      const res = await App.api('/api/test/precheck', { method: 'POST', body: JSON.stringify(payload) });
      const rows = (res.checks || []).map((c) => {
        const badgeCls = c.status === 'ok' ? 'badge-success' : (c.status === 'warning' ? 'badge-warning' : (c.status === 'error' ? 'badge-critical' : 'badge-info'));
        return `<tr><td><strong>${c.check}</strong></td><td><span class="badge ${badgeCls}">${c.status.toUpperCase()}</span></td><td>${c.detail}</td></tr>`;
      }).join('');
      const warns = (res.warnings || []).map((w) => `<div class="alert-banner warning" style="margin-top:10px;"><div><strong>Topology / Capacity Notice:</strong> ${w}</div></div>`).join('');
      out.innerHTML = `
        <table class="data-table"><thead><tr><th>Subsystem</th><th>Status</th><th>Verification Detail</th></tr></thead><tbody>${rows}</tbody></table>
        ${warns}
      `;
    } catch (e) {
      out.innerHTML = `<div class="alert-banner critical">Pre-check error: ${e.message}</div>`;
    }
  },

  async launchFromQuickTest() {
    const payload = this._collectQuickTestPayload();
    await App.startTestRequest(payload);
    App.navigate('live-monitoring');
  },

  // =========================================================================
  // 2. TRAFFIC MIX BUILDER (Matches Bottom-Left Reference Panel!)
  // =========================================================================
  renderTrafficMixBuilder() {
    const el = document.getElementById('page-traffic-mix-builder');
    const workloads = App.workloads.length ? App.workloads : Object.entries(WORKLOAD_COLORS).map(([k, v]) => ({ key: k, name: v.label, short_name: v.label, color: v.color, protocol: 'TCP/UDP', avg_frame_bytes: 576 }));

    const slidersHtml = workloads.map((w) => {
      const val = Number(this.mixDraft[w.key] ?? 0);
      return `
        <div style="display:grid;grid-template-columns:210px 1fr 56px;align-items:center;gap:12px;padding:7px 0;border-bottom:1px solid #F1F5F9;">
          <div>
            <div style="display:flex;align-items:center;gap:7px;font-weight:600;font-size:12.5px;">
              <span style="width:10px;height:10px;border-radius:50%;background:${w.color};display:inline-block;"></span>
              <span>${w.short_name || w.name}</span>
            </div>
            <div style="font-size:11px;color:var(--text-secondary);padding-left:17px;">${w.protocol} &bull; ~${w.avg_frame_bytes}B</div>
          </div>
          <input type="range" min="0" max="100" step="1" value="${val}" data-mixkey="${w.key}" oninput="StudioPages.onMixSliderChange('${w.key}', this.value)" />
          <strong style="text-align:right;" id="mixVal_${w.key}">${val}%</strong>
        </div>
      `;
    }).join('');

    el.innerHTML = `
      <div style="display:grid;grid-template-columns:360px 1fr;gap:16px;">
        <div class="card">
          <div class="card-header">
            <div class="card-title">Profile Settings</div>
          </div>
          <div class="form-group">
            <label class="form-label">Profile Name</label>
            <input type="text" class="form-control" id="tmbName" value="10K Enterprise Mix" />
          </div>
          <div class="form-group">
            <label class="form-label">Simulated Users</label>
            ${App.usersField('tmbUsers', 10000)}
          </div>
          <div class="form-group">
            <label class="form-label">Target Throughput (Gbps)</label>
            <select class="form-control" id="tmbGbps" onchange="StudioPages.refreshMixChart()">
              <option value="0.5">0.50 Gbps</option>
              <option value="1.0">1.00 Gbps</option>
              <option value="2.5">2.50 Gbps</option>
              <option value="5.0" selected>5.00 Gbps</option>
              <option value="10.0">10.00 Gbps</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Duration</label>
            <select class="form-control" id="tmbDuration">
              <option value="60">00:01:00</option>
              <option value="300">00:05:00</option>
              <option value="1800" selected>00:30:00</option>
              <option value="3600">01:00:00</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Engine Classification</label>
            <select class="form-control" id="tmbEngine">
              <option value="trex_astf" selected>Stateful ASTF (TCP/UDP Client-Server)</option>
              <option value="trex_stl">Stateless STL (Stream Mix)</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;margin-top:12px;">
            <button class="btn btn-primary btn-block" onclick="StudioPages.saveCustomMixProfile()">&#128190; Save Profile</button>
            <button class="btn btn-outline btn-block" onclick="StudioPages.launchCustomMixNow()">&#9654; Launch Mix Immediately</button>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">Traffic Allocation (Must Equal 100%)</div>
            <div style="display:flex;align-items:center;gap:10px;">
              <span class="badge badge-success" id="tmbTotalBadge">Total: 100%</span>
              <button class="btn btn-outline btn-sm" onclick="StudioPages.normalizeMixSliders()">Auto-Normalize to 100%</button>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 270px;gap:18px;align-items:center;">
            <div>${slidersHtml}</div>
            <div>
              <div id="tmbDonutChart" style="width:260px;height:260px;margin:0 auto;"></div>
              <div style="font-size:11.5px;color:var(--text-secondary);text-align:center;margin-top:8px;">
                Synthetic workload templates model packet sizes, burst intervals &amp; L4 state transitions (not commercial logins).
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    setTimeout(() => {
      const dom = document.getElementById('tmbDonutChart');
      if (dom && window.echarts) {
        this.mixChart = echarts.init(dom);
        this.refreshMixChart();
      }
    }, 40);
  },

  onMixSliderChange(key, val) {
    this.mixDraft[key] = Number(val);
    const lbl = document.getElementById(`mixVal_${key}`);
    if (lbl) lbl.textContent = `${val}%`;
    this.refreshMixChart();
  },

  normalizeMixSliders() {
    const sum = Object.values(this.mixDraft).reduce((a, b) => a + Number(b || 0), 0);
    if (sum <= 0) {
      this.mixDraft.video_streaming = 100;
    } else {
      let running = 0;
      const keys = Object.keys(this.mixDraft);
      keys.forEach((k) => {
        const scaled = Math.round((this.mixDraft[k] / sum) * 100);
        this.mixDraft[k] = scaled;
        running += scaled;
      });
      const diff = 100 - running;
      if (diff !== 0) {
        const largest = keys.reduce((a, b) => (this.mixDraft[a] >= this.mixDraft[b] ? a : b));
        this.mixDraft[largest] = Math.max(0, this.mixDraft[largest] + diff);
      }
    }
    Object.entries(this.mixDraft).forEach(([k, v]) => {
      const inp = document.querySelector(`input[data-mixkey="${k}"]`);
      const lbl = document.getElementById(`mixVal_${k}`);
      if (inp) inp.value = v;
      if (lbl) lbl.textContent = `${v}%`;
    });
    this.refreshMixChart();
  },

  refreshMixChart() {
    const sum = Object.values(this.mixDraft).reduce((a, b) => a + Number(b || 0), 0);
    const badge = document.getElementById('tmbTotalBadge');
    if (badge) {
      badge.textContent = `Total: ${sum}%`;
      badge.className = sum === 100 ? 'badge badge-success' : 'badge badge-warning';
    }
    if (!this.mixChart) return;
    const gbps = document.getElementById('tmbGbps')?.value || '5.0';
    const data = Object.entries(this.mixDraft)
      .filter(([, v]) => v > 0)
      .map(([k, v]) => ({
        name: (WORKLOAD_COLORS[k]?.label || k),
        value: v,
        itemStyle: { color: WORKLOAD_COLORS[k]?.color || '#64748B' },
      }));
    this.mixChart.setOption({
      animation: false,
      tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
      title: {
        text: `${Number(gbps).toFixed(2)}`,
        subtext: 'Gbps Target',
        left: 'center',
        top: '40%',
        textStyle: { fontSize: 18, fontWeight: 800, color: '#17243A' },
        subtextStyle: { fontSize: 11.5, color: '#64748B' },
      },
      series: [{
        type: 'pie',
        radius: ['54%', '82%'],
        label: { show: false },
        itemStyle: { borderColor: '#FFF', borderWidth: 2 },
        data,
      }],
    });
  },

  async saveCustomMixProfile() {
    this.normalizeMixSliders();
    const name = document.getElementById('tmbName').value.trim() || 'Custom Enterprise Mix';
    const users = App.readUsers('tmbUsers');
    const gbps = parseFloat(document.getElementById('tmbGbps').value) || 5.0;
    const engine = document.getElementById('tmbEngine').value;
    try {
      await App.api('/api/profiles/custom', {
        method: 'POST',
        body: JSON.stringify({
          name,
          short_name: name.slice(0, 22),
          default_users: users,
          default_devices: users * 2,
          target_gbps: gbps,
          default_rate_pct: Math.min(100, gbps * 10),
          traffic_engine: engine,
          protocol_mix: { ...this.mixDraft },
        }),
      });
      await App.loadInitialCatalog();
      App.toast(`Saved custom profile "${name}"`, 'success');
    } catch (e) {
      App.toast(`Save failed: ${e.message}`, 'error');
    }
  },

  async launchCustomMixNow() {
    this.normalizeMixSliders();
    const name = document.getElementById('tmbName').value.trim() || 'Custom Enterprise Mix';
    const simulated_users = App.readUsers('tmbUsers');
    const target_gbps = parseFloat(document.getElementById('tmbGbps').value) || 5.0;
    const duration_sec = parseInt(document.getElementById('tmbDuration').value, 10) || 300;
    const traffic_engine = document.getElementById('tmbEngine').value;

    await App.startTestRequest({
      name,
      profile_id: 'custom',
      traffic_engine,
      simulated_users,
      target_gbps,
      duration_sec,
      steady_sec: duration_sec,
      test_mode: 'phased',
      protocol_mix: { ...this.mixDraft },
    });
    App.navigate('live-monitoring');
  },

  // =========================================================================
  // 3. APPLICATION SIMULATION (10,000-User ASTF Catalog + Live Internet Mode)
  // =========================================================================
  renderApplicationSimulation() {
    const el = document.getElementById('page-application-simulation');
    const rows = (App.workloads || []).map((w) => `
      <tr>
        <td><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${w.color};margin-right:7px;"></span><strong>${w.name}</strong></td>
        <td><span class="badge badge-info">${w.protocol}</span></td>
        <td class="mono">${(w.ports || []).join(', ')}</td>
        <td>${w.avg_frame_bytes} B</td>
        <td>DSCP ${w.dscp}</td>
        <td style="font-size:12px;color:var(--text-secondary);">${w.burst_pattern} — <em>${w.disclaimer}</em></td>
      </tr>
    `).join('');

    el.innerHTML = `
      <div class="alert-banner">
        <div>
          <strong>Engineering Methodology — Synthetic ASTF User Behaviours vs Live Internet WAN</strong><br/>
          In <strong>Cisco TRex ASTF mode</strong>, up to 10,000 distinct LAN client IPs establish stateful TCP 3-way handshakes and bidirectional UDP sessions across 12 realistic application templates (with think-time delays, chunked ABR video transfers, SaaS API bursts, uploads/downloads, and DNS). In <strong>Live Internet / WAN mode</strong>, the R640 opens genuine outbound HTTP/HTTPS/DNS connections routed through your UniFi Gateway (<code>10.20.30.1</code>) to authorized public CDN/DNS endpoints.
        </div>
      </div>

      <div class="grid-2" style="margin-bottom:16px;">
        <div class="card">
          <div class="card-header">
            <div class="card-title">&#127760; Live Internet / WAN Gateway Traffic Generator</div>
            <span class="badge badge-warning">Explicit Opt-In</span>
          </div>
          <p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:12px;">
            Generates real outbound &amp; inbound Internet traffic (HTTPS CDN object downloads, web page loads, UDP/53 DNS queries, and WAN RTT/jitter probes) routed via <code>10.20.30.1</code> so you can observe live WAN throughput on the UniFi EFG immediately.
          </p>
          <div class="grid-3" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">Target WAN Rate (Mbps)</label>
              <input type="number" class="form-control" id="inetWanMbps" min="1" max="1000" value="80" />
            </div>
            <div class="form-group">
              <label class="form-label">Concurrent Workers</label>
              <input type="number" class="form-control" id="inetWorkers" min="1" max="32" value="10" />
            </div>
            <div class="form-group">
              <label class="form-label">Duration (sec)</label>
              <input type="number" class="form-control" id="inetDuration" min="10" max="3600" value="60" />
            </div>
          </div>
          <button class="btn btn-primary btn-block" onclick="StudioPages.launchInternetWanTest()">&#9654; Start Live Internet / WAN Test Through 10.20.30.1</button>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">&#128101; 10,000-User Stateful ASTF Simulation</div>
            <span class="badge badge-success">Primary EFG Mode</span>
          </div>
          <p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:12px;">
            Launches 10,000 emulated enterprise user IPs (<code>16.0.0.1 – 16.0.39.16</code>) executing all 12 stateful TCP/UDP behaviours simultaneously, reporting Users, Client IPs, Active Flows, Established TCP Sessions, and CPS separately.
          </p>
          <div class="grid-2" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">Simulated Users</label>
              ${App.usersField('astfSimUsers', 10000)}
            </div>
            <div class="form-group">
              <label class="form-label">Target Load (Gbps)</label>
              <input type="number" class="form-control" id="astfSimGbps" step="0.25" value="5.0" />
            </div>
          </div>
          <button class="btn btn-primary btn-block" onclick="StudioPages.launchAstfAppSim()">&#9654; Launch 10K Stateful Application Workload</button>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">12 Enterprise Application Workload Templates</div>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Application Category</th><th>L4 Protocol</th><th>Ports</th><th>Avg Frame</th><th>QoS</th><th>Behaviour &amp; Classification</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  },

  async launchInternetWanTest() {
    const mbps = parseFloat(document.getElementById('inetWanMbps').value) || 80;
    const workers = parseInt(document.getElementById('inetWorkers').value, 10) || 10;
    const dur = parseInt(document.getElementById('inetDuration').value, 10) || 60;
    await App.startTestRequest({
      name: `Live Internet / WAN Gateway Test (${mbps} Mbps)`,
      profile_id: 'internet_wan_mix',
      traffic_engine: 'internet_wan',
      test_mode: 'timed',
      duration_sec: dur,
      simulated_users: workers * 25,
      target_gbps: mbps / 1000.0,
      internet_options: { wan_target_mbps: mbps, workers, enable_download: true, enable_web: true, enable_dns: true },
    });
    App.navigate('live-monitoring');
  },

  async launchAstfAppSim() {
    const users = App.readUsers('astfSimUsers');
    const gbps = parseFloat(document.getElementById('astfSimGbps').value) || 5.0;
    await App.startTestRequest({
      name: `Stateful Enterprise App Simulation (${users.toLocaleString()} Users)`,
      profile_id: 'imix',
      traffic_engine: 'trex_astf',
      test_mode: 'phased',
      simulated_users: users,
      target_gbps: gbps,
      ramp_up_sec: 15,
      steady_sec: 90,
      ramp_down_sec: 10,
    });
    App.navigate('live-monitoring');
  },

  // =========================================================================
  // 4. TRAFFIC PROFILES LIBRARY
  // =========================================================================
  renderTrafficProfiles() {
    const el = document.getElementById('page-traffic-profiles');
    const cards = App.profiles.map((p) => `
      <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
            <strong style="font-size:14px;">${p.name}</strong>
            <span class="badge ${p.traffic_engine === 'trex_astf' ? 'badge-info' : (p.traffic_engine === 'internet_wan' ? 'badge-warning' : 'badge-neutral')}">${p.traffic_engine}</span>
          </div>
          <p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:12px;">${p.description || ''}</p>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-secondary);padding:8px 0;border-top:1px solid #EEF2F6;">
            <span>Avg Frame: <strong>${p.avg_frame_size}B</strong></span>
            <span>Default Users: <strong>${Number(p.default_users || 1000).toLocaleString()}</strong></span>
            <span>Target: <strong>${p.target_gbps || 5} Gbps</strong></span>
          </div>
          <div style="display:flex;gap:8px;margin-top:6px;">
            <button class="btn btn-primary btn-sm" style="flex:1;" onclick="StudioPages.quickRunProfile('${p.id}')">&#9654; Run Profile</button>
            ${p.is_custom_saved ? `<button class="btn btn-outline btn-sm" onclick="StudioPages.deleteCustomProf('${p.id}')">Delete</button>` : ''}
          </div>
        </div>
      </div>
    `).join('');

    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <div style="color:var(--text-secondary);">Showing ${App.profiles.length} pre-built and saved custom enterprise traffic profiles.</div>
        <button class="btn btn-primary btn-sm" onclick="App.navigate('traffic-mix-builder')">+ Create New Custom Mix</button>
      </div>
      <div class="grid-3">${cards}</div>
    `;
  },

  async quickRunProfile(pid) {
    const p = App.profiles.find((x) => x.id === pid) || App.profiles[0];
    await App.startTestRequest({
      profile_id: p.id,
      traffic_engine: p.traffic_engine || 'trex_astf',
      simulated_users: p.default_users || 5000,
      target_gbps: p.target_gbps || 2.5,
      duration_sec: 60,
      steady_sec: 60,
      test_mode: p.traffic_engine === 'trex_astf' ? 'phased' : 'timed',
    });
    App.navigate('live-monitoring');
  },

  async deleteCustomProf(pid) {
    await App.api(`/api/profiles/custom/${pid}`, { method: 'DELETE' });
    await App.loadInitialCatalog();
    this.renderTrafficProfiles();
    App.toast('Custom profile deleted.', 'info');
  },

  // =========================================================================
  // 5. RFC 2544 / FRAME-SIZE BENCHMARKING
  // =========================================================================
  renderRfc2544() {
    const el = document.getElementById('page-rfc2544-benchmark');
    el.innerHTML = `
      <div class="alert-banner">
        <div>
          <strong>Methodology Note — Automated STL Frame-Size Sweep</strong><br/>
          Executes genuine Cisco TRex STL hardware/DPDK trials sequentially across standard IEEE/RFC 2544 Ethernet frame sizes (<code>64B, 128B, 256B, 512B, 1024B, 1280B, 1518B</code> + optional <code>9000B</code> Jumbo) and records real TX/RX throughput, packet rate (Kpps/Mpps), PG_ID latency, jitter, and counter-derived frame loss.
        </div>
      </div>

      <div class="grid-2" style="margin-bottom:16px;">
        <div class="card">
          <div class="card-header"><div class="card-title">Sweep Configuration</div></div>
          <div class="form-group">
            <label class="form-label">Benchmark Title / Site Label</label>
            <input type="text" class="form-control" id="rfcSiteName" value="UniFi EFG Forwarding Matrix" />
          </div>
          <div class="grid-3" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">Offered Rate (Gbps)</label>
              <input type="number" class="form-control" id="rfcTargetGbps" step="0.1" min="0.05" max="10" value="1.0" />
            </div>
            <div class="form-group">
              <label class="form-label">Seconds / Frame Size</label>
              <input type="number" class="form-control" id="rfcTrialSec" min="2" max="20" value="3" />
            </div>
            <div class="form-group">
              <label class="form-label">Jumbo 9000B</label>
              <select class="form-control" id="rfcJumbo">
                <option value="0" selected>Standard (64–1518B)</option>
                <option value="1">Include 9000B Jumbo</option>
              </select>
            </div>
          </div>
          <button class="btn btn-primary btn-block" id="rfcRunBtn" onclick="StudioPages.executeRfcSweep()">&#9654; Execute Live Cisco TRex STL Frame-Size Sweep</button>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">Sweep Results Matrix</div></div>
          <div id="rfcResultsArea" style="color:var(--text-secondary);font-size:13px;">
            Configure parameters on the left and click <strong>Execute Live Cisco TRex STL Frame-Size Sweep</strong> to run real per-frame-size hardware measurements.
          </div>
        </div>
      </div>
    `;
  },

  async executeRfcSweep() {
    const btn = document.getElementById('rfcRunBtn');
    const out = document.getElementById('rfcResultsArea');
    if (!btn || !out) return;
    btn.disabled = true;
    btn.textContent = 'Running Real STL Trials Across Frame Sizes...';
    out.innerHTML = `<div class="alert-banner">Executing sequential Cisco TRex STL trials (switching daemon to STL if needed and sampling each frame size)...</div>`;
    try {
      const res = await App.api('/api/certification/rfc2544', {
        method: 'POST',
        body: JSON.stringify({
          site_name: document.getElementById('rfcSiteName').value.trim(),
          target_gbps: parseFloat(document.getElementById('rfcTargetGbps').value) || 1.0,
          trial_duration_sec: parseInt(document.getElementById('rfcTrialSec').value, 10) || 3,
          include_jumbo: document.getElementById('rfcJumbo').value === '1',
        }),
      });
      await App.refreshRunsSilent();
      const rows = (res.frame_matrix || []).map((r) => `
        <tr>
          <td><strong>${r.frame_size_bytes} B</strong></td>
          <td>${r.tx_mbps} Mbps</td>
          <td style="color:var(--primary);font-weight:700;">${r.throughput_mbps} Mbps</td>
          <td>${r.packet_rate_kpps} Kpps</td>
          <td>${r.lat_avg_us} μs</td>
          <td>${r.p99_lat_us} μs</td>
          <td>${r.drop_pct}%</td>
        </tr>
      `).join('');
      out.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <span class="badge badge-success">Completed Run #${res.run_id}</span>
          <a class="btn btn-outline btn-sm" href="/api/runs/${res.run_id}/export/pdf?report_type=technical" target="_blank">Download PDF Report</a>
        </div>
        <table class="data-table">
          <thead><tr><th>Frame</th><th>TX Rate</th><th>RX Rate</th><th>Packet Rate</th><th>Avg Lat</th><th>P99 Lat</th><th>Loss</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    } catch (e) {
      out.innerHTML = `<div class="alert-banner critical">Sweep error: ${e.message}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = '▶ Execute Live Cisco TRex STL Frame-Size Sweep';
    }
  },

  // =========================================================================
  // 6. STRESS & SOAK TESTING (500 -> 10,000 EFG Scenarios + Staged Steps)
  // =========================================================================
  renderStressSoak() {
    const el = document.getElementById('page-stress-soak');
    const scenCards = (App.scenarios || []).map((sc) => `
      <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <strong style="font-size:14px;">${sc.name}</strong>
            <span class="badge ${sc.users >= 10000 ? 'badge-info' : 'badge-neutral'}">${sc.users.toLocaleString()} Users</span>
          </div>
          <p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:10px;">${sc.description}</p>
        </div>
        <div>
          <div style="font-size:12px;color:var(--text-secondary);padding:7px 0;border-top:1px solid #EEF2F6;display:flex;justify-content:space-between;">
            <span>Target: <strong>${sc.target_gbps} Gbps</strong></span>
            <span>Ramp: <strong>${sc.ramp_up_sec}s</strong> | Steady: <strong>${sc.steady_sec}s</strong></span>
          </div>
          <button class="btn btn-primary btn-sm btn-block" onclick="StudioPages.runScenario('${sc.id}')">&#9654; Launch Scenario</button>
        </div>
      </div>
    `).join('');

    el.innerHTML = `
      <div class="card" style="margin-bottom:16px;border-left:4px solid var(--primary);">
        <div class="card-header">
          <div class="card-title">&#128269; Find the breaking point</div>
          <span class="badge badge-info" id="bpBadge">Idle</span>
        </div>
        <p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:10px;">
          Runs back-to-back tests with more and more users until loss, latency or delivered traffic go outside the limits below.
          The result is the highest user count your gateway handled cleanly. Each step is saved in History with its own PDF.
        </p>
        <div class="grid-4" style="gap:12px;">
          <div class="form-group"><label class="form-label">Start at (users)</label><input type="number" class="form-control" id="bpStart" min="1" max="100000" value="10000" /></div>
          <div class="form-group"><label class="form-label">Step size (users)</label><input type="number" class="form-control" id="bpStep" min="1" max="100000" value="10000" /></div>
          <div class="form-group"><label class="form-label">Stop at (users)</label><input type="number" class="form-control" id="bpMax" min="1" max="100000" value="100000" /></div>
          <div class="form-group"><label class="form-label">Seconds per step</label><input type="number" class="form-control" id="bpSec" min="15" max="3600" value="60" /></div>
          <div class="form-group"><label class="form-label">Target throughput (Gbps)</label><input type="number" class="form-control" id="bpGbps" min="0.01" step="0.1" value="1.0" /></div>
          <div class="form-group"><label class="form-label">Max packet loss (%)</label><input type="number" class="form-control" id="bpLoss" min="0" step="0.1" value="0.5" /></div>
          <div class="form-group"><label class="form-label">Max avg latency (ms)</label><input type="number" class="form-control" id="bpLat" min="0.01" step="1" value="50" /></div>
          <div class="form-group"><label class="form-label">&nbsp;</label>
            <div style="display:flex;gap:6px;">
              <button class="btn btn-primary" style="flex:1;" id="bpStartBtn" onclick="StudioPages.startBreakingPoint()">&#9654; Start</button>
              <button class="btn btn-danger" id="bpStopBtn" style="display:none;" onclick="StudioPages.stopBreakingPoint()">&#9632; Stop</button>
            </div>
          </div>
        </div>
        <div id="bpResult"></div>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <div class="card-header">
          <div class="card-title">&#128101; Custom user-scale test (up to 100,000 users)</div>
        </div>
        <div class="grid-4" style="gap:12px;align-items:start;">
          <div class="form-group">
            <label class="form-label">Users</label>
            ${App.usersField('ssUsers', 25000)}
          </div>
          <div class="form-group">
            <label class="form-label">Target throughput (Gbps)</label>
            <input type="number" class="form-control" id="ssGbps" min="0.01" max="100" step="0.1" value="1.0" />
          </div>
          <div class="form-group">
            <label class="form-label">Steady time (minutes)</label>
            <input type="number" class="form-control" id="ssMinutes" min="1" max="1440" step="1" value="5" />
          </div>
          <div class="form-group">
            <label class="form-label">&nbsp;</label>
            <button class="btn btn-primary btn-block" onclick="StudioPages.runCustomScaleTest()">&#9654; Start scale test</button>
          </div>
        </div>
        <p style="font-size:12px;color:var(--text-secondary);margin-top:4px;">
          Each user gets its own client IP. Ramp-up is longer for big numbers so the gateway is loaded gradually.
        </p>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <div class="card-header">
          <div class="card-title">&#128200; Staged Load-Step Saturation Finder (10% &rarr; 25% &rarr; 50% &rarr; 75% &rarr; 90% &rarr; 100%)</div>
          <button class="btn btn-primary btn-sm" onclick="StudioPages.runStagedStepTest()">&#9654; Start 6-Stage Saturation Ramp</button>
        </div>
        <p style="font-size:12.5px;color:var(--text-secondary);">
          Automatically steps load across <strong>10%, 25%, 50%, 75%, 90%, and 100%</strong> while recording UniFi EFG CPU, memory, latency percentiles, and packet loss at every plateau to identify exact firewall saturation knees.
        </p>
      </div>

      <h3 style="font-size:14.5px;font-weight:700;margin-bottom:12px;">Pre-Engineered UniFi EFG User-Scale &amp; Extended Soak Scenarios</h3>
      <div class="grid-3">${scenCards}</div>
    `;
    this.refreshBreakingPoint();
  },

  // ---- Breaking-point finder ----------------------------------------------
  async startBreakingPoint() {
    const num = (id, d) => { const v = parseFloat(document.getElementById(id).value); return Number.isFinite(v) ? v : d; };
    const body = {
      start_users: App.clampUsers(num('bpStart', 10000)),
      step_users: App.clampUsers(num('bpStep', 10000)),
      max_users: App.clampUsers(num('bpMax', 100000)),
      step_sec: num('bpSec', 60),
      target_gbps: num('bpGbps', 1.0),
      max_loss_pct: num('bpLoss', 0.5),
      max_latency_ms: num('bpLat', 50),
    };
    try {
      const res = await App.api('/api/capacity/start', { method: 'POST', body: JSON.stringify(body) });
      App.toast(`Breaking-point finder started: ${res.steps} steps, about ${res.estimated_minutes} min.`, 'success');
      this.refreshBreakingPoint();
    } catch (e) {
      App.toast(`Could not start: ${e.message}`, 'error');
    }
  },

  async stopBreakingPoint() {
    try {
      await App.api('/api/capacity/stop', { method: 'POST' });
      App.toast('Stopping the breaking-point finder…', 'info');
    } catch (e) {
      App.toast(e.message, 'error');
    }
  },

  async refreshBreakingPoint() {
    clearTimeout(this._bpTimer);
    const box = document.getElementById('bpResult');
    if (!box) return;
    let st;
    try {
      st = await App.api('/api/capacity/status');
    } catch (_) {
      return;
    }
    const badge = document.getElementById('bpBadge');
    const startBtn = document.getElementById('bpStartBtn');
    const stopBtn = document.getElementById('bpStopBtn');
    if (startBtn) startBtn.disabled = !!st.running;
    if (stopBtn) stopBtn.style.display = st.running ? '' : 'none';
    const outcomeBadge = {
      running: ['badge-info', 'Running'], limit_found: ['badge-warning', 'Limit found'], no_limit_found: ['badge-success', 'No limit hit'],
      cancelled: ['badge-neutral', 'Stopped'], error: ['badge-critical', 'Error'],
    }[st.running ? 'running' : st.outcome] || ['badge-neutral', 'Idle'];
    if (badge) { badge.className = `badge ${outcomeBadge[0]}`; badge.textContent = outcomeBadge[1]; }

    const steps = st.steps || [];
    if (!st.running && !steps.length) {
      box.innerHTML = '';
      return;
    }
    const lat = (us) => (us ? (us >= 1000 ? `${(us / 1000).toFixed(2)} ms` : `${Number(us).toFixed(1)} μs`) : '—');
    const rows = steps.map((s) => `
      <tr>
        <td>${s.step}</td>
        <td><strong>${Number(s.users).toLocaleString()}</strong></td>
        <td>${App.fmtBps(s.avg_rx_bps || 0)}</td>
        <td>${s.drop_pct != null ? Number(s.drop_pct).toFixed(3) + '%' : '—'}</td>
        <td>${lat(s.lat_avg_us)}</td>
        <td>${Number(s.peak_active_flows || 0).toLocaleString()}</td>
        <td>${s.peak_gw_cpu_pct != null ? s.peak_gw_cpu_pct + '%' : '—'}</td>
        <td>${s.ok ? '<span class="badge badge-success">OK</span>' : `<span class="badge badge-critical" title="${App.esc(s.reason)}">Broke</span> <span style="font-size:11px;color:var(--text-secondary);">${App.esc(s.reason)}</span>`}</td>
        <td>${s.run_id ? `<a href="javascript:void(0)" onclick="StudioPages.showRunDetailModal(${Number(s.run_id)})">#${s.run_id}</a>` : ''}</td>
      </tr>`).join('');
    const running = st.running
      ? `<tr><td>${st.current_step}</td><td><strong>${Number(st.current_users || 0).toLocaleString()}</strong></td><td colspan="7" style="color:var(--text-secondary);">Running now… (step ${st.current_step} of ${(st.plan || []).length})</td></tr>`
      : '';
    const headline = st.running
      ? `<div class="alert-banner info" style="margin-top:12px;"><div><strong>Running.</strong> ${App.esc(st.message || '')} — watch it live in <a href="javascript:void(0)" onclick="App.navigate('live-monitoring')">Live View</a>.</div></div>`
      : `<div class="alert-banner ${st.outcome === 'limit_found' ? 'warning' : st.outcome === 'no_limit_found' ? 'success' : 'info'}" style="margin-top:12px;"><div>
           ${st.max_good_users ? `<div style="font-size:20px;font-weight:800;">${Number(st.max_good_users).toLocaleString()} users handled cleanly</div>` : ''}
           ${App.esc(st.message || '')}
           ${st.ended_at ? `<div style="font-size:11.5px;color:var(--text-secondary);margin-top:3px;">Finished ${new Date(st.ended_at * 1000).toLocaleString()}</div>` : ''}
         </div></div>`;
    box.innerHTML = `
      ${headline}
      <div class="table-wrap" style="margin-top:10px;">
        <table class="data-table">
          <thead><tr><th>Step</th><th>Users</th><th>Avg received</th><th>Loss</th><th>Avg latency</th><th>Peak flows</th><th>Gateway CPU</th><th>Result</th><th>Run</th></tr></thead>
          <tbody>${rows}${running}</tbody>
        </table>
      </div>`;
    if (st.running && App.currentRoute === 'stress-soak') {
      this._bpTimer = setTimeout(() => this.refreshBreakingPoint(), 3000);
    }
  },

  // =========================================================================
  // TRENDS (internet quality over time + nightly check)
  // =========================================================================
  async renderTrends() {
    const el = document.getElementById('page-trends');
    const days = this._trendDays || 30;
    let data;
    let schedules = [];
    try {
      [data, { schedules }] = await Promise.all([
        App.api(`/api/trends?engine_type=internet_wan&days=${days}`),
        App.api('/api/schedules'),
      ]);
    } catch (e) {
      el.innerHTML = `<div class="alert-banner critical">Could not load trends: ${App.esc(e.message)}</div>`;
      return;
    }
    const nightly = (schedules || []).find((j) => j.name === 'Nightly internet check');
    const pts = data.points || [];
    const avg = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);
    const dl = pts.map((p) => Number(p.avg_rx_bps || 0));
    const lats = pts.map((p) => Number(p.lat_avg_us || 0)).filter((v) => v > 0);
    el.innerHTML = `
      <div class="card" style="margin-bottom:16px;">
        <div class="card-header">
          <div class="card-title">&#127760; Internet speed &amp; quality over time</div>
          <div style="display:flex;gap:6px;">
            ${[7, 30, 90].map((d) => `<button class="btn btn-sm ${d === days ? 'btn-primary' : 'btn-outline'}" onclick="StudioPages._trendDays=${d};StudioPages.renderTrends()">${d} days</button>`).join('')}
          </div>
        </div>
        <div class="grid-4" style="gap:12px;margin-bottom:12px;">
          <div class="card"><div class="card-subtitle">Tests</div><div class="kpi-value">${pts.length}</div></div>
          <div class="card"><div class="card-subtitle">Average download</div><div class="kpi-value">${dl.length ? App.fmtBps(avg(dl)) : '—'}</div></div>
          <div class="card"><div class="card-subtitle">Slowest test</div><div class="kpi-value">${dl.length ? App.fmtBps(Math.min(...dl)) : '—'}</div></div>
          <div class="card"><div class="card-subtitle">Average latency</div><div class="kpi-value">${lats.length ? (avg(lats) / 1000).toFixed(1) + ' <span class="kpi-unit">ms</span>' : '—'}</div></div>
        </div>
        ${pts.length ? '<div id="trendChart" style="width:100%;height:320px;"></div>' : '<div class="alert-banner info"><div>No internet tests in this period yet. Run <strong>Internet speed &amp; quality</strong> from Home, or schedule the nightly check below.</div></div>'}
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title">&#127769; Nightly internet check</div>
          ${nightly ? '<span class="badge badge-success">Scheduled</span>' : '<span class="badge badge-neutral">Off</span>'}</div>
        ${nightly
          ? `<p style="font-size:12.5px;">Runs every night (cron <code>${App.esc(nightly.cron_expr)}</code>) — a 60-second download/upload, DNS and latency test through your WAN.
             Last run: ${nightly.last_run_at ? new Date(nightly.last_run_at * 1000).toLocaleString() : 'not yet'}.
             Manage or delete it under <a href="javascript:void(0)" onclick="App.navigate('test-scheduler')">Run a Test → Schedule</a>.</p>`
          : `<p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:10px;">Runs a 60-second internet speed &amp; quality test every night so you can prove (or disprove) what your ISP promises.</p>
             <div style="display:flex;gap:8px;align-items:center;">
               <label class="form-label" style="margin:0;">Time</label>
               <input type="time" class="form-control" id="nightlyTime" value="02:00" style="max-width:130px;" />
               <button class="btn btn-primary" onclick="StudioPages.enableNightlyCheck()">Turn on nightly check</button>
             </div>`}
      </div>`;
    if (pts.length && window.echarts) {
      const ch = echarts.init(document.getElementById('trendChart'));
      this.trendChart = ch;
      const labels = pts.map((p) => new Date(p.started_at * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }));
      ch.setOption({
        animation: false,
        tooltip: { trigger: 'axis' },
        legend: { top: 0, right: 10 },
        grid: { top: 34, right: 60, bottom: 30, left: 60 },
        xAxis: { type: 'category', data: labels },
        yAxis: [{ type: 'value', name: 'Mbps', min: 0 }, { type: 'value', name: 'ms', min: 0 }],
        series: [
          { name: 'Download (Mbps)', type: 'line', smooth: true, itemStyle: { color: '#1769D2' }, areaStyle: { color: 'rgba(23,105,210,0.1)' }, data: pts.map((p) => +((p.avg_rx_bps || 0) / 1e6).toFixed(2)) },
          { name: 'Upload (Mbps)', type: 'line', smooth: true, itemStyle: { color: '#10B981' }, data: pts.map((p) => +((p.avg_tx_bps || 0) / 1e6).toFixed(2)) },
          { name: 'Latency (ms)', type: 'line', yAxisIndex: 1, smooth: true, itemStyle: { color: '#D97706' }, data: pts.map((p) => +((p.lat_avg_us || 0) / 1000).toFixed(2)) },
          { name: 'Jitter (ms)', type: 'line', yAxisIndex: 1, smooth: true, itemStyle: { color: '#8B5CF6' }, data: pts.map((p) => +((p.jitter_avg_us || 0) / 1000).toFixed(2)) },
        ],
      });
      ch.on('click', (params) => { const p = pts[params.dataIndex]; if (p) this.showRunDetailModal(p.run_id); });
    }
  },

  async enableNightlyCheck() {
    const [h, m] = (document.getElementById('nightlyTime')?.value || '02:00').split(':').map((x) => parseInt(x, 10));
    try {
      await App.api('/api/schedules/nightly-internet', { method: 'POST', body: JSON.stringify({ hour: h || 0, minute: m || 0 }) });
      App.toast('Nightly internet check is on.', 'success');
      this.renderTrends();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  },

  async runScenario(scenId) {
    await App.startTestRequest({ scenario_id: scenId });
    App.navigate('live-monitoring');
  },

  async runCustomScaleTest() {
    const users = App.readUsers('ssUsers', 25000);
    const gbps = Math.max(0.01, parseFloat(document.getElementById('ssGbps').value) || 1.0);
    const steady = Math.max(1, parseInt(document.getElementById('ssMinutes').value, 10) || 5) * 60;
    await App.startTestRequest({
      name: `${users.toLocaleString()} users — scale test @ ${gbps} Gbps`,
      profile_id: 'imix',
      traffic_engine: 'trex_astf',
      test_mode: 'phased',
      simulated_users: users,
      simulated_devices: users * 2,
      target_gbps: gbps,
      ramp_up_sec: users > 50000 ? 120 : users > 20000 ? 60 : 30,
      steady_sec: steady,
      ramp_down_sec: users > 50000 ? 60 : 20,
    });
    App.navigate('live-monitoring');
  },

  async runStagedStepTest() {
    await App.startTestRequest({
      name: 'EFG 6-Stage Saturation Ramp (10% -> 100%)',
      profile_id: 'imix',
      traffic_engine: 'trex_stl',
      test_mode: 'step_ramp',
      simulated_users: App.readUsers('ssUsers', 10000),
      ramp_steps_pct: [10, 25, 50, 75, 90, 100],
      ramp_step_sec: 15,
    });
    App.navigate('live-monitoring');
  },

  // =========================================================================
  // 7. TEST SCHEDULER
  // =========================================================================
  async renderScheduler() {
    const el = document.getElementById('page-test-scheduler');
    const data = await App.api('/api/schedules');
    const jobs = data.schedules || [];
    const profOpts = App.profiles.map((p) => `<option value="${p.id}">${p.name}</option>`).join('');

    const rows = jobs.map((j) => `
      <tr>
        <td><strong>${j.name}</strong></td>
        <td class="mono">${j.run_at_iso || j.cron_expr}</td>
        <td>${j.profile_id}</td>
        <td>${Number(j.simulated_users).toLocaleString()}</td>
        <td>${j.duration_sec}s</td>
        <td>${j.last_run_id ? `<a href="javascript:void(0)" onclick="StudioPages.showRunDetailModal(${j.last_run_id})">Run #${j.last_run_id}</a>` : 'Never'}</td>
        <td><button class="btn btn-outline btn-sm" onclick="StudioPages.deleteSchedule(${j.id})">Delete</button></td>
      </tr>
    `).join('');

    el.innerHTML = `
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><div class="card-title">Schedule Automated Benchmark</div></div>
          <div class="form-group">
            <label class="form-label">Job Name</label>
            <input type="text" class="form-control" id="schName" value="Nightly 2:00 AM 10K-User EFG Soak" />
          </div>
          <div class="grid-2" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">5-Field Cron Expression</label>
              <input type="text" class="form-control mono" id="schCron" value="0 2 * * *" />
            </div>
            <div class="form-group">
              <label class="form-label">Profile</label>
              <select class="form-control" id="schProf">${profOpts}</select>
            </div>
            <div class="form-group">
              <label class="form-label">Simulated Users</label>
              ${App.usersField('schUsers', 10000)}
            </div>
            <div class="form-group">
              <label class="form-label">Duration (sec)</label>
              <input type="number" class="form-control" id="schDur" value="300" />
            </div>
          </div>
          <button class="btn btn-primary btn-block" onclick="StudioPages.createSchedule()">+ Save Scheduled Job</button>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">Configured Schedules (${jobs.length})</div></div>
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>Job</th><th>Schedule</th><th>Profile</th><th>Users</th><th>Dur</th><th>Last Run</th><th></th></tr></thead>
              <tbody>${rows || '<tr><td colspan="7">No schedules configured.</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  },

  async createSchedule() {
    await App.api('/api/schedules', {
      method: 'POST',
      body: JSON.stringify({
        name: document.getElementById('schName').value.trim(),
        cron_expr: document.getElementById('schCron').value.trim(),
        profile_id: document.getElementById('schProf').value,
        simulated_users: App.readUsers('schUsers'),
        duration_sec: parseInt(document.getElementById('schDur').value, 10) || 300,
        test_mode: 'phased',
      }),
    });
    App.toast('Scheduled job created.', 'success');
    this.renderScheduler();
  },

  async deleteSchedule(id) {
    await App.api(`/api/schedules/${id}`, { method: 'DELETE' });
    this.renderScheduler();
  },

  // =========================================================================
  // 8. TEST HISTORY (Preserves Existing SQLite Runs + Full Inspection Modal)
  // =========================================================================
  async renderTestHistory() {
    const el = document.getElementById('page-test-history');
    const d = await App.api('/api/runs?limit=100');
    App.runs = d.runs || [];

    const rows = App.runs.map((r) => {
      const s = r.summary || {};
      const dt = new Date((r.started_at || 0) * 1000).toLocaleString();
      return `
        <tr>
          <td class="mono">#${r.id}</td>
          <td><a href="javascript:void(0)" style="color:var(--primary);font-weight:600;text-decoration:none;" onclick="StudioPages.showRunDetailModal(${r.id})">${App.esc(r.name)}</a></td>
          <td>${dt}</td>
          <td><span class="badge badge-neutral">${r.traffic_engine || 'trex_stl'}</span></td>
          <td>${Number(r.simulated_users || 0).toLocaleString()}</td>
          <td>${App.fmtBps(s.avg_rx_bps || 0)}</td>
          <td>${s.lat_avg_us ? Number(s.lat_avg_us).toFixed(2) + ' μs' : '—'}</td>
          <td>${s.drop_pct !== undefined ? Number(s.drop_pct).toFixed(4) + '%' : '0.0000%'}</td>
          <td>${App.verdictBadge(s.verdict || r.verdict, s.thresholds_configured)}</td>
          <td style="display:flex;gap:5px;">
            <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/pdf?report_type=technical" target="_blank">PDF</a>
            <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/csv">CSV</a>
            <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/json">JSON</a>
            ${r.test_mode !== 'rfc2544_sweep' ? `<button class="btn btn-outline btn-sm" title="Run the exact same test again (e.g. after a firmware upgrade)" onclick="StudioPages.rerunTest(${r.id})">&#8635; Re-run</button>` : ''}
            <button class="btn btn-outline btn-sm" title="Compare with the previous run of the same test" onclick="StudioPages.compareWithPrevious(${r.id})">Before/after</button>
            <button class="btn btn-outline btn-sm" onclick="StudioPages.deleteHistoryRun(${r.id})">&times;</button>
          </td>
        </tr>
      `;
    }).join('');

    el.innerHTML = `
      <div class="card" style="margin-bottom:14px;">
        <div class="card-header">
          <div class="card-title">Results over time</div>
          <span class="card-subtitle">Bars: average received throughput (colour = test type) · line: average latency · click a bar to open the test</span>
        </div>
        <div id="histChart" style="width:100%;height:240px;"></div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title">Recorded Test Runs (${App.runs.length} Stored in SQLite)</div>
          <button class="btn btn-outline btn-sm" onclick="StudioPages.renderTestHistory()">&#8635; Refresh</button>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>Test Name</th><th>Started</th><th>Engine</th><th>Users</th><th>Avg RX</th><th>Avg Lat</th><th>Loss</th><th>Outcome</th><th>Exports</th></tr>
            </thead>
            <tbody>${rows || '<tr><td colspan="10">No runs stored.</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    `;
    this.renderHistoryChart();
  },

  async rerunTest(id) {
    if (App.latest && App.latest.running) {
      App.toast('A test is already running. Stop it first.', 'error');
      return;
    }
    if (!confirm(`Run test #${id} again with exactly the same settings?`)) return;
    try {
      const res = await App.api(`/api/runs/${id}/rerun`, { method: 'POST' });
      App.toast(`Started test #${res.run_id}: ${res.name}. When it finishes, use "Before/after" to compare.`, 'success');
      App.closeModal();
      App.navigate('live-monitoring');
    } catch (e) {
      App.toast(`Re-run failed: ${e.message}`, 'error');
    }
  },

  async compareWithPrevious(id) {
    try {
      const prev = await App.api(`/api/runs/${id}/previous`);
      App.closeModal();
      App.navigate('compare-tests');
      // renderCompareTests is async; wait for the selects to exist, then pick before (A) and after (B)
      for (let i = 0; i < 30 && !document.getElementById('cmpRunA'); i++) await new Promise((r) => setTimeout(r, 100));
      await new Promise((r) => setTimeout(r, 150));
      const a = document.getElementById('cmpRunA');
      const b = document.getElementById('cmpRunB');
      if (a && b) {
        a.value = String(prev.run_id);
        b.value = String(id);
        this.executeCompare();
      }
    } catch (e) {
      App.toast(`${e.message}. Re-run this test first (e.g. after a firmware upgrade), then compare.`, 'error');
    }
  },

  renderHistoryChart() {
    const el = document.getElementById('histChart');
    if (!el || !window.echarts) return;
    if (this.histChart) this.histChart.dispose();
    const runs = (App.runs || []).filter((r) => (r.summary || {}).sample_count).slice(0, 60).reverse();
    if (!runs.length) { el.innerHTML = '<div style="color:var(--text-secondary);font-size:12.5px;padding:20px;">No finished tests yet.</div>'; return; }
    const ch = echarts.init(el);
    this.histChart = ch;
    const maxBps = Math.max(...runs.map((r) => Number(r.summary.avg_rx_bps || 0)));
    const k = maxBps >= 1e9 ? 1e9 : 1e6;
    const unit = maxBps >= 1e9 ? 'Gbps' : 'Mbps';
    const colors = { trex_astf: '#1769D2', trex_stl: '#0EA5E9', internet_wan: '#10B981', hybrid: '#7C3AED' };
    const names = { trex_astf: 'Stateful (users)', trex_stl: 'Stateless', internet_wan: 'Internet', hybrid: 'Hybrid' };
    const axisLabel = { color: '#64748B', fontSize: 10.5 };
    ch.setOption({
      animation: false,
      grid: { top: 34, right: 54, bottom: 28, left: 56 },
      legend: { top: 0, left: 'center', data: Object.keys(names).filter((e) => runs.some((r) => r.traffic_engine === e)).map((e) => names[e]).concat(['Avg latency (ms)']), textStyle: { color: '#475569', fontSize: 11 } },
      tooltip: {
        trigger: 'axis', confine: true,
        formatter: (ps) => {
          const r = runs[ps[0].dataIndex];
          const s = r.summary || {};
          return `<strong>#${r.id} ${App.esc(r.name)}</strong><br/>${new Date(r.started_at * 1000).toLocaleString()}<br/>Received ${App.fmtBps(s.avg_rx_bps)} · loss ${Number(s.drop_pct || 0).toFixed(3)}%<br/>Latency ${(Number(s.lat_avg_us || 0) / 1000).toFixed(2)} ms · ${Number(r.simulated_users || 0).toLocaleString()} users`;
        },
      },
      xAxis: { type: 'category', data: runs.map((r) => `#${r.id}`), axisLabel, axisLine: { lineStyle: { color: '#DFE5ED' } } },
      yAxis: [
        { type: 'value', name: unit, min: 0, axisLabel, nameTextStyle: axisLabel, splitLine: { lineStyle: { color: '#EEF2F6' } } },
        { type: 'value', name: 'ms', min: 0, axisLabel, nameTextStyle: axisLabel, splitLine: { show: false } },
      ],
      series: [
        ...Object.keys(names).filter((e) => runs.some((r) => r.traffic_engine === e)).map((e) => ({
          name: names[e], type: 'bar', stack: 'rx', barMaxWidth: 26, itemStyle: { color: colors[e], borderRadius: [3, 3, 0, 0] },
          data: runs.map((r) => (r.traffic_engine === e ? +(Number(r.summary.avg_rx_bps || 0) / k).toFixed(2) : null)),
        })),
        { name: 'Avg latency (ms)', type: 'line', yAxisIndex: 1, symbolSize: 5, connectNulls: true, lineStyle: { color: '#D97706', width: 1.6 }, itemStyle: { color: '#D97706' },
          data: runs.map((r) => (r.summary.lat_avg_us ? +(Number(r.summary.lat_avg_us) / 1000).toFixed(2) : null)) },
      ],
    });
    ch.on('click', (p) => { const r = runs[p.dataIndex]; if (r) this.showRunDetailModal(r.id); });
  },

  async deleteHistoryRun(id) {
    if (!confirm(`Delete Test Run #${id} permanently?`)) return;
    await App.api(`/api/runs/${id}`, { method: 'DELETE' });
    this.renderTestHistory();
  },

  // ---- Charts for one recorded run (used by the run detail window) ----------
  _runChartDefs(run) {
    const ss = run.samples || [];
    const x = ss.map((s) => `${s.elapsed_sec}s`);
    const n = (v) => (v === null || v === undefined ? null : Number(v));
    const maxBps = Math.max(0, ...ss.map((s) => Math.max(n(s.tx_bps) || 0, n(s.rx_bps) || 0)));
    const gb = maxBps >= 1e9;
    const bk = gb ? 1e9 : 1e6;
    const maxLat = Math.max(0, ...ss.map((s) => n(s.p99_lat_us) || n(s.lat_avg_us) || 0));
    const ms = maxLat >= 2000;
    const lk = ms ? 1000 : 1;

    // Shade ramp-up / steady / ramp-down / step phases
    const bands = [];
    let start = 0;
    for (let i = 1; i <= ss.length; i++) {
      if (i === ss.length || ss[i].phase_name !== ss[start].phase_name) {
        const ph = String(ss[start].phase_name || '');
        if (ph && ph !== 'steady' && ph !== 'idle') {
          bands.push([{ name: ph.replace(/_/g, ' '), xAxis: x[start], itemStyle: { color: ph.startsWith('ramp') ? 'rgba(148,163,184,0.12)' : 'rgba(23,105,210,0.05)' } }, { xAxis: x[i - 1] }]);
        }
        start = i;
      }
    }
    const markArea = bands.length ? { silent: true, label: { color: '#94A3B8', fontSize: 10, position: 'insideTop' }, data: bands } : undefined;
    const line = (name, data, color, extra = {}) => ({ name, type: 'line', smooth: true, showSymbol: false, connectNulls: true, lineStyle: { width: 1.8, color }, itemStyle: { color }, data, ...extra });
    const hasFlows = ss.some((s) => n(s.active_flows) > 0);
    const hasMos = ss.some((s) => n(s.mos_score) > 0);

    return [
      {
        title: `Throughput (${gb ? 'Gbps' : 'Mbps'})`,
        y: [{ name: gb ? 'Gbps' : 'Mbps' }],
        series: [
          line('Sent', ss.map((s) => +((n(s.tx_bps) || 0) / bk).toFixed(3)), '#1769D2', { areaStyle: { color: 'rgba(23,105,210,0.10)' }, markArea }),
          line('Received', ss.map((s) => +((n(s.rx_bps) || 0) / bk).toFixed(3)), '#10B981'),
        ],
      },
      {
        title: `Latency & jitter (${ms ? 'ms' : 'μs'})`,
        y: [{ name: ms ? 'ms' : 'μs' }],
        series: [
          line('Avg', ss.map((s) => (n(s.lat_avg_us) ? +(n(s.lat_avg_us) / lk).toFixed(2) : null)), '#1769D2', { markArea }),
          line('P99', ss.map((s) => (n(s.p99_lat_us) ? +(n(s.p99_lat_us) / lk).toFixed(2) : null)), '#D97706'),
          line('Jitter', ss.map((s) => (n(s.jitter_us) ? +(n(s.jitter_us) / lk).toFixed(2) : null)), '#0D9488', { lineStyle: { width: 1.5, color: '#0D9488', type: 'dashed' } }),
        ],
      },
      hasFlows
        ? {
            title: 'Connections',
            y: [{ name: 'flows' }, { name: 'new/s' }],
            series: [
              line('Active flows', ss.map((s) => n(s.active_flows) || 0), '#1769D2', { areaStyle: { color: 'rgba(23,105,210,0.08)' }, markArea }),
              line('TCP sessions', ss.map((s) => n(s.established_sessions) || 0), '#15803D'),
              line('New/s', ss.map((s) => +(n(s.cps) || 0).toFixed(1)), '#D97706', { yAxisIndex: 1, lineStyle: { width: 1.5, color: '#D97706', type: 'dashed' } }),
            ],
          }
        : {
            title: 'Packet rate (kpps)',
            y: [{ name: 'kpps' }],
            series: [
              line('Sent', ss.map((s) => +((n(s.tx_pps) || 0) / 1e3).toFixed(1)), '#1769D2', { areaStyle: { color: 'rgba(23,105,210,0.08)' }, markArea }),
              line('Received', ss.map((s) => +((n(s.rx_pps) || 0) / 1e3).toFixed(1)), '#10B981'),
            ],
          },
      {
        title: hasMos ? 'Packet loss & call quality (MOS estimate)' : 'Packet loss',
        y: hasMos ? [{ name: 'loss %' }, { name: 'MOS', min: 1, max: 5 }] : [{ name: 'loss %' }],
        series: [
          line('Loss %', ss.map((s) => +(n(s.drop_pct) || 0).toFixed(4)), '#DC2626', { areaStyle: { color: 'rgba(220,38,38,0.08)' }, markArea }),
          ...(hasMos ? [line('MOS', ss.map((s) => (n(s.mos_score) ? +n(s.mos_score).toFixed(2) : null)), '#7C3AED', { yAxisIndex: 1 })] : []),
        ],
      },
    ].map((d) => ({ ...d, x }));
  },

  _renderRunCharts(run, idPrefix) {
    (this._modalCharts || []).forEach((c) => c.dispose());
    this._modalCharts = [];
    if (!window.echarts || !(run.samples || []).length) return;
    const axisLabel = { color: '#64748B', fontSize: 10 };
    this._runChartDefs(run).forEach((d, i) => {
      const el = document.getElementById(`${idPrefix}${i}`);
      if (!el) return;
      const ch = echarts.init(el);
      ch.setOption({
        animation: false,
        grid: { top: 26, right: d.y.length > 1 ? 44 : 14, bottom: 22, left: 48 },
        tooltip: { trigger: 'axis', confine: true },
        legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 7, textStyle: { color: '#475569', fontSize: 10.5 } },
        xAxis: { type: 'category', boundaryGap: false, data: d.x, axisLabel: { ...axisLabel, hideOverlap: true }, axisLine: { lineStyle: { color: '#DFE5ED' } } },
        yAxis: d.y.map((y, j) => ({ type: 'value', min: 0, splitLine: { show: j === 0, lineStyle: { color: '#EEF2F6' } }, nameTextStyle: { color: '#64748B', fontSize: 10 }, axisLabel, ...y })),
        series: d.series,
      });
      this._modalCharts.push(ch);
    });
  },

  async showRunDetailModal(runId) {
    try {
      const r = await App.api(`/api/runs/${runId}`);
      const s = r.summary || {};
      const html = `
        <div class="grid-4" style="gap:10px;margin-bottom:14px;">
          <div class="card"><div class="card-subtitle">Packet loss</div><div style="font-size:17px;font-weight:800;">${Number(s.drop_pct || 0).toFixed(3)}%</div><div class="kpi-foot">${Number(s.total_dropped_packets || 0).toLocaleString()} packets dropped</div></div>
          <div class="card"><div class="card-subtitle">Avg / Peak RX</div><div style="font-size:17px;font-weight:800;">${App.fmtBps(s.avg_rx_bps || 0)}</div><div class="kpi-foot">Peak: ${App.fmtBps(s.max_rx_bps || 0)}</div></div>
          <div class="card"><div class="card-subtitle">Avg / P99 Latency</div><div style="font-size:17px;font-weight:800;">${Number(s.lat_avg_us || 0).toFixed(2)} μs</div><div class="kpi-foot">P99: ${Number(s.p99_lat_us || 0).toFixed(2)} μs</div></div>
          <div class="card"><div class="card-subtitle">Flows / TCP Sessions</div><div style="font-size:17px;font-weight:800;">${Number(s.peak_active_flows || 0).toLocaleString()}</div><div class="kpi-foot">Est TCP: ${Number(s.peak_established_sessions || 0).toLocaleString()}</div></div>
        </div>
        <div style="font-size:12.5px;color:var(--text-secondary);margin-bottom:12px;">
          <strong>Source:</strong> ${s.telemetry_source || r.traffic_engine} &bull;
          <strong>Samples:</strong> ${(r.samples || []).length}s &bull;
          <strong>UniFi Polls:</strong> ${(r.unifi_samples || []).length} &bull;
          <strong>Users:</strong> ${Number(r.simulated_users || 0).toLocaleString()}
        </div>
        <div class="run-charts">
          ${[0, 1, 2, 3].map((i) => `<div class="rc"><div class="rc-title" id="rcTitle${i}"></div><div class="rc-chart" id="rcChart${i}"></div></div>`).join('')}
        </div>
        <div style="display:flex;gap:8px;">
          <a class="btn btn-primary btn-sm" href="/api/runs/${r.id}/export/pdf?report_type=technical" target="_blank">Technical PDF</a>
          <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/pdf?report_type=executive" target="_blank">Executive PDF</a>
          <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/csv">CSV</a>
          <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/json">JSON</a>
        </div>
        <div style="display:flex;gap:8px;margin-top:10px;">
          ${r.test_mode !== 'rfc2544_sweep' ? `<button class="btn btn-outline btn-sm" onclick="StudioPages.rerunTest(${r.id})">&#8635; Re-run this test</button>` : ''}
          <button class="btn btn-outline btn-sm" onclick="StudioPages.compareWithPrevious(${r.id})">Compare with previous run (before/after)</button>
        </div>
      `;
      App.openModal(`Run #${r.id} — ${r.name}`, html);
      document.querySelector('#appModalBackdrop .modal-box')?.classList.add('wide');
      if ((r.samples || []).length) {
        this._runChartDefs(r).forEach((d, i) => { const el = document.getElementById(`rcTitle${i}`); if (el) el.textContent = d.title; });
        setTimeout(() => this._renderRunCharts(r, 'rcChart'), 30);
      } else {
        document.querySelector('.run-charts')?.remove();
      }
    } catch (e) {
      App.toast(e.message, 'error');
    }
  },

  // =========================================================================
  // 9. COMPARE TESTS (Side-by-Side Overlaid Chart + Delta Table + PDF)
  // =========================================================================
  async renderCompareTests() {
    const el = document.getElementById('page-compare-tests');
    const d = await App.api('/api/runs?limit=100');
    App.runs = d.runs || [];
    const optsA = App.runs.map((r, i) => `<option value="${r.id}" ${i === Math.min(1, App.runs.length - 1) ? 'selected' : ''}>#${r.id} — ${r.name} (${r.simulated_users} users)</option>`).join('');
    const optsB = App.runs.map((r, i) => `<option value="${r.id}" ${i === 0 ? 'selected' : ''}>#${r.id} — ${r.name} (${r.simulated_users} users)</option>`).join('');

    el.innerHTML = `
      <div class="card" style="margin-bottom:16px;">
        <div style="display:grid;grid-template-columns:1fr 1fr auto auto;gap:12px;align-items:end;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Baseline Test (Run A)</label>
            <select class="form-control" id="cmpRunA">${optsA}</select>
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Candidate Test (Run B)</label>
            <select class="form-control" id="cmpRunB">${optsB}</select>
          </div>
          <button class="btn btn-primary" onclick="StudioPages.executeCompare()">Compare Runs</button>
          <button class="btn btn-outline" onclick="StudioPages.downloadComparePdf()">Export Comparison PDF</button>
        </div>
      </div>
      <div id="cmpResultContainer"></div>
    `;
    if (App.runs.length >= 1) this.executeCompare();
  },

  async executeCompare() {
    const a = document.getElementById('cmpRunA')?.value;
    const b = document.getElementById('cmpRunB')?.value;
    const out = document.getElementById('cmpResultContainer');
    if (!a || !b || !out) return;
    try {
      const comp = await App.api(`/api/runs/compare?run_a=${a}&run_b=${b}`);
      const dl = comp.deltas || {};
      const fmtRow = (label, key, unit = '') => {
        const obj = dl[key] || {};
        const sign = (obj.delta || 0) > 0 ? '+' : '';
        const pct = obj.delta_pct !== null && obj.delta_pct !== undefined ? ` (${sign}${obj.delta_pct}%)` : '';
        return `<tr><td><strong>${label}</strong></td><td>${obj.run_a ?? 0}${unit}</td><td>${obj.run_b ?? 0}${unit}</td><td style="font-weight:700;color:${(obj.delta || 0) >= 0 ? '#1769D2' : '#D97706'};">${sign}${obj.delta ?? 0}${unit}${pct}</td></tr>`;
      };

      out.innerHTML = `
        <div class="grid-2">
          <div class="card">
            <div class="card-header"><div class="card-title">Side-by-Side Metric Deltas</div></div>
            <table class="data-table">
              <thead><tr><th>Metric</th><th>Run #${a}</th><th>Run #${b}</th><th>Delta (B - A)</th></tr></thead>
              <tbody>
                ${fmtRow('Average TX Throughput', 'avg_tx_mbps', ' Mbps')}
                ${fmtRow('Average RX Throughput', 'avg_rx_mbps', ' Mbps')}
                ${fmtRow('Peak RX Throughput', 'max_rx_mbps', ' Mbps')}
                ${fmtRow('Packet Loss', 'drop_pct', '%')}
                ${fmtRow('Average Latency', 'lat_avg_us', ' μs')}
                ${fmtRow('P99 Latency', 'p99_lat_us', ' μs')}
                ${fmtRow('Peak Active Flows', 'peak_active_flows', '')}
                ${fmtRow('Peak Established TCP', 'peak_established_sessions', '')}
              </tbody>
            </table>
          </div>
          <div class="card">
            <div class="card-header"><div class="card-title">Overlaid RX Throughput Timeline</div></div>
            <div id="cmpEchart" style="width:100%;height:300px;"></div>
          </div>
        </div>
      `;

      setTimeout(() => {
        const dom = document.getElementById('cmpEchart');
        if (dom && window.echarts) {
          const ch = echarts.init(dom);
          const sa = comp.run_a.samples || [];
          const sb = comp.run_b.samples || [];
          const maxLen = Math.max(sa.length, sb.length);
          const xs = Array.from({ length: maxLen }, (_, i) => `${i + 1}s`);
          ch.setOption({
            tooltip: { trigger: 'axis' },
            legend: { top: 0 },
            grid: { top: 32, right: 18, bottom: 28, left: 56 },
            xAxis: { type: 'category', data: xs },
            yAxis: { type: 'value', name: 'Mbps', min: 0 },
            series: [
              { name: `Run #${a} RX (Mbps)`, type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#1769D2' }, data: sa.map((x) => +((x.rx_bps || 0) / 1e6).toFixed(2)) },
              { name: `Run #${b} RX (Mbps)`, type: 'line', smooth: true, showSymbol: false, itemStyle: { color: '#15803D' }, data: sb.map((x) => +((x.rx_bps || 0) / 1e6).toFixed(2)) },
            ],
          });
        }
      }, 40);
    } catch (e) {
      out.innerHTML = `<div class="alert-banner critical">${e.message}</div>`;
    }
  },

  downloadComparePdf() {
    const a = document.getElementById('cmpRunA')?.value;
    const b = document.getElementById('cmpRunB')?.value;
    if (a && b) window.open(`/api/runs/compare/export/pdf?run_a=${a}&run_b=${b}`, '_blank');
  },

  // =========================================================================
  // 10. REPORTS & EXPORTS (Client Customization + Live Inline PDF Preview)
  // =========================================================================
  async renderReportsExports() {
    const el = document.getElementById('page-reports-exports');
    const d = await App.api('/api/runs?limit=100');
    App.runs = d.runs || [];
    const runOpts = App.runs.map((r) => `<option value="${r.id}">Run #${r.id} — ${r.name} (${Number(r.simulated_users).toLocaleString()} Users)</option>`).join('');
    const firstId = App.runs[0]?.id || '';

    el.innerHTML = `
      <div style="display:grid;grid-template-columns:390px 1fr;gap:16px;">
        <div class="card">
          <div class="card-header"><div class="card-title">Client Report Builder</div></div>
          <div class="form-group">
            <label class="form-label">Select Recorded Test Run</label>
            <select class="form-control" id="repRunId" onchange="StudioPages.refreshReportPreview()">${runOpts}</select>
          </div>
          <div class="form-group">
            <label class="form-label">Report Variant</label>
            <select class="form-control" id="repVariant" onchange="StudioPages.refreshReportPreview()">
              <option value="technical" selected>Full 9-Page Engineering &amp; UniFi Report</option>
              <option value="executive">3-Page Executive Summary Report</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Custom Cover Headline (Optional)</label>
            <input type="text" class="form-control" id="repTitle" placeholder="Cisco TRex + UniFi Enterprise Fortress Gateway" />
          </div>
          <div class="form-group">
            <label class="form-label">Client / Project Name</label>
            <input type="text" class="form-control" id="repClient" value="Enterprise Network Performance Validation" />
          </div>

          <div style="display:flex;flex-direction:column;gap:8px;margin-top:14px;">
            <button class="btn btn-outline btn-block" onclick="StudioPages.refreshReportPreview()">&#128065; Refresh Live PDF Preview</button>
            <button class="btn btn-primary btn-block" onclick="StudioPages.downloadSelectedReport('pdf')">&#11015; Download Styled PDF Report</button>
            <div class="grid-2" style="gap:8px;">
              <button class="btn btn-outline" onclick="StudioPages.downloadSelectedReport('csv')">CSV</button>
              <button class="btn btn-outline" onclick="StudioPages.downloadSelectedReport('json')">JSON</button>
            </div>
          </div>
        </div>

        <div class="card" style="display:flex;flex-direction:column;min-height:680px;">
          <div class="card-header">
            <div class="card-title">Client-Ready Light-Mode PDF Preview</div>
            <span class="badge badge-info">A4 Vector Report</span>
          </div>
          <iframe id="repPdfFrame" style="flex:1;width:100%;border:1px solid var(--border-color);border-radius:8px;background:#F8FAFC;" src="${firstId ? `/api/runs/${firstId}/export/pdf?report_type=technical&inline=1` : 'about:blank'}"></iframe>
        </div>
      </div>
    `;
  },

  _buildReportQuery(inline = false) {
    const id = document.getElementById('repRunId')?.value;
    const type = document.getElementById('repVariant')?.value || 'technical';
    const title = encodeURIComponent(document.getElementById('repTitle')?.value.trim() || '');
    const client = encodeURIComponent(document.getElementById('repClient')?.value.trim() || '');
    if (!id) return null;
    let url = `/api/runs/${id}/export/pdf?report_type=${type}&inline=${inline ? 1 : 0}`;
    if (title) url += `&title=${title}`;
    if (client) url += `&client=${client}`;
    return { id, url };
  },

  refreshReportPreview() {
    const q = this._buildReportQuery(true);
    const frame = document.getElementById('repPdfFrame');
    if (q && frame) frame.src = q.url;
  },

  downloadSelectedReport(fmt) {
    const id = document.getElementById('repRunId')?.value;
    if (!id) return;
    if (fmt === 'csv') window.open(`/api/runs/${id}/export/csv`, '_blank');
    else if (fmt === 'json') window.open(`/api/runs/${id}/export/json`, '_blank');
    else {
      const q = this._buildReportQuery(false);
      if (q) window.open(q.url, '_blank');
    }
  },
};

window.StudioPages = StudioPages;
