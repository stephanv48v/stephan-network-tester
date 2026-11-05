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
          <td><a href="javascript:void(0)" style="color:var(--primary);font-weight:600;text-decoration:none;" onclick="StudioPages.showRunDetailModal(${r.id})">${r.name}</a></td>
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
            <button class="btn btn-outline btn-sm" onclick="StudioPages.deleteHistoryRun(${r.id})">&times;</button>
          </td>
        </tr>
      `;
    }).join('');

    el.innerHTML = `
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
  },

  async deleteHistoryRun(id) {
    if (!confirm(`Delete Test Run #${id} permanently?`)) return;
    await App.api(`/api/runs/${id}`, { method: 'DELETE' });
    this.renderTestHistory();
  },

  async showRunDetailModal(runId) {
    try {
      const r = await App.api(`/api/runs/${runId}`);
      const s = r.summary || {};
      const html = `
        <div class="grid-3" style="gap:10px;margin-bottom:14px;">
          <div class="card"><div class="card-subtitle">Avg / Peak RX</div><div style="font-size:17px;font-weight:800;">${App.fmtBps(s.avg_rx_bps || 0)}</div><div class="kpi-foot">Peak: ${App.fmtBps(s.max_rx_bps || 0)}</div></div>
          <div class="card"><div class="card-subtitle">Avg / P99 Latency</div><div style="font-size:17px;font-weight:800;">${Number(s.lat_avg_us || 0).toFixed(2)} μs</div><div class="kpi-foot">P99: ${Number(s.p99_lat_us || 0).toFixed(2)} μs</div></div>
          <div class="card"><div class="card-subtitle">Flows / TCP Sessions</div><div style="font-size:17px;font-weight:800;">${Number(s.peak_active_flows || 0).toLocaleString()}</div><div class="kpi-foot">Est TCP: ${Number(s.peak_established_sessions || 0).toLocaleString()}</div></div>
        </div>
        <div style="font-size:12.5px;color:var(--text-secondary);margin-bottom:12px;">
          <strong>Source:</strong> ${s.telemetry_source || r.traffic_engine} &bull;
          <strong>Samples:</strong> ${(r.samples || []).length}s &bull;
          <strong>UniFi Polls:</strong> ${(r.unifi_samples || []).length} &bull;
          <strong>Packet Loss:</strong> ${Number(s.drop_pct || 0).toFixed(4)}%
        </div>
        <div style="display:flex;gap:8px;">
          <a class="btn btn-primary btn-sm" href="/api/runs/${r.id}/export/pdf?report_type=technical" target="_blank">Download 9-Page Technical PDF</a>
          <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/pdf?report_type=executive" target="_blank">Download 3-Page Executive PDF</a>
          <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/csv">Download CSV</a>
          <a class="btn btn-outline btn-sm" href="/api/runs/${r.id}/export/json">Download JSON</a>
        </div>
      `;
      App.openModal(`Run #${r.id} — ${r.name}`, html);
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
              <button class="btn btn-outline" onclick="StudioPages.downloadSelectedReport('csv')">Download CSV</button>
              <button class="btn btn-outline" onclick="StudioPages.downloadSelectedReport('json')">Download JSON</button>
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
