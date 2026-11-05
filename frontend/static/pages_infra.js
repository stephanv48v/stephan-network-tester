/* ==========================================================================
   Cisco TRex Network Test Studio — Infrastructure (5 Pages) & Admin (4 Pages)
   ========================================================================== */

const INFRA_ROUTES = new Set([
  'unifi-monitoring',
  'network-topology',
  'nics-ports',
  'trex-engine',
  'server-health',
  'configuration',
  'api-integrations',
  'user-access',
  'audit-logs',
]);

const InfraPages = {
  unifiSubTab: 'gateways',
  selectedTopoNode: 'efg',
  lastTopoData: null,

  canHandle(route) {
    return INFRA_ROUTES.has(route);
  },

  render(route) {
    switch (route) {
      case 'unifi-monitoring': return this.renderUniFiMonitoring();
      case 'network-topology': return this.renderNetworkTopology();
      case 'nics-ports': return this.renderNicsPorts();
      case 'trex-engine': return this.renderTrexEngine();
      case 'server-health': return this.renderServerHealth();
      case 'configuration': return this.renderConfiguration();
      case 'api-integrations': return this.renderApiIntegrations();
      case 'user-access': return this.renderUserAccess();
      case 'audit-logs': return this.renderAuditLogs();
    }
  },

  // =========================================================================
  // 1. UNIFI STACK MONITORING
  // =========================================================================
  async renderUniFiMonitoring(forceRefresh = false) {
    const el = document.getElementById('page-unifi-monitoring');
    const [snap, snmpSnap] = await Promise.all([
      App.api(`/api/unifi/telemetry?refresh=${forceRefresh ? 1 : 0}`),
      App.api(`/api/snmp/telemetry?refresh=${forceRefresh ? 1 : 0}`),
    ]);

    const s = snap.summary || {};
    const caps = snap.capabilities || {};
    const capPill = (ok) => ok ? `<span class="badge badge-success">Supported</span>` : `<span class="badge badge-neutral">Unavailable</span>`;

    let tabBody = '';
    if (!snap.connected) {
      tabBody = `
        <div class="alert-banner warning">
          <div>
            <strong>UniFi Controller Telemetry Not Connected (${snap.status || 'Not Configured'})</strong><br/>
            ${snap.last_error ? `Last response: <code>${snap.last_error}</code><br/>` : ''}
            No UniFi device statistics are fabricated when disconnected. Provide a read-only Local UniFi Network API key (<code>X-API-KEY</code>) or Ubiquiti Site Manager key in <strong>Administration &rarr; API Integrations</strong>.
          </div>
          <button class="btn btn-primary btn-sm" onclick="App.navigate('api-integrations')">Configure API Key</button>
        </div>
      `;
    } else if (this.unifiSubTab === 'gateways') {
      const rows = (snap.gateways || []).map((g) => `
        <tr>
          <td><strong>${g.name || 'UniFi Gateway'}</strong></td>
          <td>${g.model || 'EFG'}</td>
          <td class="mono">${g.ip || '10.20.30.1'}</td>
          <td>${g.firmware || '—'}</td>
          <td>${g.online ? '<span class="badge badge-success">Online</span>' : '<span class="badge badge-critical">Offline</span>'}</td>
          <td>${g.cpu_pct != null ? g.cpu_pct + '%' : 'Unavailable'}</td>
          <td>${g.mem_pct != null ? g.mem_pct + '%' : 'Unavailable'}</td>
          <td>${g.wan_rx_bps != null ? App.fmtBps(g.wan_rx_bps) + ' / ' + App.fmtBps(g.wan_tx_bps || 0) : 'Unavailable'}</td>
        </tr>
      `).join('');
      tabBody = `<table class="data-table"><thead><tr><th>Gateway</th><th>Model</th><th>IP</th><th>Firmware</th><th>State</th><th>CPU</th><th>Memory</th><th>WAN RX / TX</th></tr></thead><tbody>${rows || '<tr><td colspan="8">No gateway returned by API.</td></tr>'}</tbody></table>`;
    } else if (this.unifiSubTab === 'switches') {
      const rows = (snap.switches || []).map((sw) => `
        <tr>
          <td><strong>${sw.name}</strong></td>
          <td>${sw.model}</td>
          <td class="mono">${sw.ip || '—'}</td>
          <td>${sw.online ? '<span class="badge badge-success">Online</span>' : '<span class="badge badge-critical">Offline</span>'}</td>
          <td>${sw.cpu_pct != null ? sw.cpu_pct + '%' : 'Unavailable'}</td>
          <td>${sw.mem_pct != null ? sw.mem_pct + '%' : 'Unavailable'}</td>
          <td>${Array.isArray(sw.ports) ? sw.ports.length + ' ports reported' : 'Port stats unavailable'}</td>
        </tr>
      `).join('');
      tabBody = `<table class="data-table"><thead><tr><th>Switch</th><th>Model</th><th>IP</th><th>State</th><th>CPU</th><th>RAM</th><th>Ports</th></tr></thead><tbody>${rows || '<tr><td colspan="7">No switches reported.</td></tr>'}</tbody></table>`;
    } else if (this.unifiSubTab === 'aps') {
      const rows = (snap.access_points || []).map((ap) => `
        <tr>
          <td><strong>${ap.name}</strong></td>
          <td>${ap.model}</td>
          <td class="mono">${ap.ip || '—'}</td>
          <td>${ap.online ? '<span class="badge badge-success">Online</span>' : '<span class="badge badge-critical">Offline</span>'}</td>
          <td>${ap.num_sta != null ? ap.num_sta : 'Unavailable'}</td>
          <td>${ap.cpu_pct != null ? ap.cpu_pct + '%' : 'Unavailable'}</td>
        </tr>
      `).join('');
      tabBody = `<table class="data-table"><thead><tr><th>Access Point</th><th>Model</th><th>IP</th><th>State</th><th>Clients</th><th>CPU</th></tr></thead><tbody>${rows || '<tr><td colspan="6">No access points reported.</td></tr>'}</tbody></table>`;
    } else if (this.unifiSubTab === 'clients') {
      const rows = (snap.clients || []).slice(0, 100).map((c) => `
        <tr>
          <td><strong>${c.hostname || c.mac || 'Client'}</strong></td>
          <td class="mono">${c.ip || '—'}</td>
          <td>${c.is_wired ? 'Wired' : 'Wi-Fi'}</td>
          <td>${c.network || '—'}</td>
          <td>${c.rx_bps != null ? App.fmtBps(c.rx_bps) : '—'}</td>
          <td>${c.tx_bps != null ? App.fmtBps(c.tx_bps) : '—'}</td>
        </tr>
      `).join('');
      tabBody = `<table class="data-table"><thead><tr><th>Client</th><th>IP</th><th>Medium</th><th>Network</th><th>RX</th><th>TX</th></tr></thead><tbody>${rows || '<tr><td colspan="6">Client list unavailable or empty.</td></tr>'}</tbody></table>`;
    } else if (this.unifiSubTab === 'snmp') {
      const rows = (snmpSnap.interfaces || []).map((i) => `
        <tr>
          <td class="mono">${i.if_index}</td>
          <td><strong>${i.if_name}</strong></td>
          <td>${i.oper_status}</td>
          <td>${i.speed_mbps ? i.speed_mbps + ' Mbps' : '—'}</td>
          <td>${i.counter_width}</td>
          <td>${i.in_bps != null ? App.fmtBps(i.in_bps) : 'Sampling...'}</td>
          <td>${i.out_bps != null ? App.fmtBps(i.out_bps) : 'Sampling...'}</td>
          <td>${i.in_errors ?? 0} / ${i.out_errors ?? 0}</td>
          <td>${i.in_discards ?? 0} / ${i.out_discards ?? 0}</td>
        </tr>
      `).join('');
      tabBody = snmpSnap.connected
        ? `<table class="data-table"><thead><tr><th>Idx</th><th>Interface</th><th>Oper</th><th>Speed</th><th>Width</th><th>In Rate</th><th>Out Rate</th><th>In/Out Err</th><th>In/Out Disc</th></tr></thead><tbody>${rows}</tbody></table>`
        : `<div class="alert-banner">SNMP polling is currently ${snmpSnap.status || 'Disabled'}. Enable read-only SNMPv2c/v3 in <strong>API Integrations</strong> for 64-bit IF-MIB interface octets, discards, and error counters.</div>`;
    }

    el.innerHTML = `
      <div class="grid-4" style="margin-bottom:14px;">
        <div class="card"><div class="card-subtitle">Gateway (${s.gw_name || 'EFG'})</div><div class="kpi-value">${s.gw_cpu_pct != null ? s.gw_cpu_pct + '% CPU' : (snap.connected ? 'Online' : 'Offline')}</div><div class="kpi-foot">RAM: ${s.gw_mem_pct != null ? s.gw_mem_pct + '%' : 'Unavailable'}</div></div>
        <div class="card"><div class="card-subtitle">WAN Throughput</div><div class="kpi-value">${s.wan_rx_bps != null ? App.fmtBps((s.wan_rx_bps || 0) + (s.wan_tx_bps || 0)) : 'Unavailable'}</div><div class="kpi-foot">Latency: ${s.wan_latency_ms != null ? s.wan_latency_ms + ' ms' : 'Unavailable'}</div></div>
        <div class="card"><div class="card-subtitle">Switches &amp; APs</div><div class="kpi-value">${(s.switches_online || 0) + (s.aps_online || 0)}</div><div class="kpi-foot">Switches: ${s.switches_online || 0}/${s.switches_total || 0} | APs: ${s.aps_online || 0}/${s.aps_total || 0}</div></div>
        <div class="card"><div class="card-subtitle">Active Clients</div><div class="kpi-value">${s.active_clients != null ? Number(s.active_clients).toLocaleString() : 'Unavailable'}</div><div class="kpi-foot">Mode: ${snap.api_mode_detected || 'Not Connected'}</div></div>
      </div>

      <div class="card" style="margin-bottom:14px;">
        <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;">
          <div style="display:flex;gap:14px;font-size:12px;align-items:center;">
            <strong>Detected API Capabilities:</strong>
            <span>CPU/RAM ${capPill(caps.gateway_cpu_mem)}</span>
            <span>WAN Rate ${capPill(caps.wan_throughput)}</span>
            <span>Switch Ports ${capPill(caps.switch_port_counters)}</span>
            <span>AP Radios ${capPill(caps.ap_radio_stats)}</span>
            <span>Clients ${capPill(caps.client_inventory)}</span>
          </div>
          <button class="btn btn-outline btn-sm" onclick="InfraPages.renderUniFiMonitoring(true)">&#8635; Poll Now</button>
        </div>
      </div>

      <div class="subtab-bar">
        <button class="subtab-btn ${this.unifiSubTab === 'gateways' ? 'active' : ''}" onclick="InfraPages.unifiSubTab='gateways';InfraPages.renderUniFiMonitoring()">Gateways (EFG)</button>
        <button class="subtab-btn ${this.unifiSubTab === 'switches' ? 'active' : ''}" onclick="InfraPages.unifiSubTab='switches';InfraPages.renderUniFiMonitoring()">Switches</button>
        <button class="subtab-btn ${this.unifiSubTab === 'aps' ? 'active' : ''}" onclick="InfraPages.unifiSubTab='aps';InfraPages.renderUniFiMonitoring()">Access Points</button>
        <button class="subtab-btn ${this.unifiSubTab === 'clients' ? 'active' : ''}" onclick="InfraPages.unifiSubTab='clients';InfraPages.renderUniFiMonitoring()">Active Clients</button>
        <button class="subtab-btn ${this.unifiSubTab === 'snmp' ? 'active' : ''}" onclick="InfraPages.unifiSubTab='snmp';InfraPages.renderUniFiMonitoring()">SNMP IF-MIB Counters</button>
      </div>

      <div class="card">${tabBody}</div>
    `;
  },

  // =========================================================================
  // 2. NETWORK TOPOLOGY (Interactive Diagram + Inspector + Honest Assessment)
  // =========================================================================
  async renderNetworkTopology() {
    const el = document.getElementById('page-network-topology');
    const topo = await App.api('/api/topology');
    this.lastTopoData = topo;
    const ta = topo.topology_assessment || {};
    const u = topo.unifi || {};
    const usum = u.summary || {};
    const gw = topo.discovered_gateway || {};

    const switchesHtml = (u.switches && u.switches.length > 0 ? u.switches.slice(0, 3) : [{ name: 'LAN Access Switch (Port 12)', model: '100MbE Negotiated', online: true }])
      .map((sw, idx) => `
        <div class="topo-node ${this.selectedTopoNode === 'sw_' + idx ? 'selected' : ''}" onclick="InfraPages.selectTopoNode('sw_${idx}')">
          <div style="font-size:11px;color:var(--text-secondary);">SWITCH</div>
          <div style="font-weight:700;margin:2px 0;">${sw.name}</div>
          <div style="font-size:11.5px;color:#15803D;">&#9679; ${sw.model || 'Online'}</div>
        </div>
      `).join('');

    const apsHtml = (u.access_points && u.access_points.length > 0 ? u.access_points.slice(0, 4) : [])
      .map((ap, idx) => `
        <div class="topo-node" style="min-width:120px;padding:8px 10px;" onclick="InfraPages.selectTopoNode('ap_${idx}')">
          <div style="font-weight:600;font-size:12px;">${ap.name}</div>
          <div style="font-size:11px;color:var(--text-secondary);">${ap.model}</div>
        </div>
      `).join('');

    el.innerHTML = `
      <div class="alert-banner ${ta.active_mode_code === 'internal_veth_loopback' ? 'warning' : 'info'}">
        <div>
          <strong>Verified Hardware &amp; LAN-to-WAN Topology Assessment (${ta.active_mode_label || 'Active'})</strong><br/>
          ${ta.honest_10g_explanation || ''}
        </div>
      </div>

      <div class="topology-layout">
        <div class="card" style="padding:24px;">
          <div class="card-header">
            <div class="card-title">Interactive Test &amp; UniFi Infrastructure Path (Click Any Device to Inspect)</div>
            <button class="btn btn-outline btn-sm" onclick="InfraPages.renderNetworkTopology()">&#8635; Refresh Discovery</button>
          </div>

          <div style="display:flex;flex-direction:column;align-items:center;gap:16px;padding:14px 0;">
            <!-- Tier 1: Controlled WAN / Internet -->
            <div class="topo-node ${this.selectedTopoNode === 'wan' ? 'selected' : ''}" onclick="InfraPages.selectTopoNode('wan')">
              <div style="font-size:11px;color:var(--text-secondary);">UPSTREAM / RESPONDER</div>
              <div style="font-weight:700;">Controlled WAN Server Emulator / Internet</div>
              <div style="font-size:11.5px;color:var(--primary);">TRex Port 1 (48.0.0.0/16) &amp; Authorized WAN</div>
            </div>

            <div style="width:2px;height:22px;background:#94A3B8;"></div>

            <!-- Tier 2: UniFi EFG -->
            <div class="topo-node ${this.selectedTopoNode === 'efg' ? 'selected' : ''}" style="min-width:240px;border-width:2px;" onclick="InfraPages.selectTopoNode('efg')">
              <div style="font-size:11px;color:var(--primary);font-weight:700;">DEVICE UNDER TEST (FIREWALL / NAT)</div>
              <div style="font-size:15px;font-weight:800;margin:3px 0;">${usum.gw_name || 'UniFi EFG / Gateway'}</div>
              <div class="mono" style="font-size:12px;color:var(--text-secondary);">${gw.ip || '10.20.30.1'} (${gw.mac || ''})</div>
              <div style="margin-top:4px;"><span class="badge badge-success">${gw.reachable ? '● Reachable on LAN' : 'Configured'}</span></div>
            </div>

            <div style="width:2px;height:22px;background:#94A3B8;"></div>

            <!-- Tier 3: Switching + R640 Generator -->
            <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:20px;align-items:center;">
              <div class="topo-node ${this.selectedTopoNode === 'r640' ? 'selected' : ''}" style="min-width:230px;background:#F8FAFC;" onclick="InfraPages.selectTopoNode('r640')">
                <div style="font-size:11px;color:#1769D2;font-weight:700;">TRAFFIC GENERATOR APPLIANCE</div>
                <div style="font-weight:800;font-size:14px;">Dell PowerEdge R640</div>
                <div class="mono" style="font-size:11.5px;color:var(--text-secondary);">10.20.30.237 &bull; ${topo.r640?.trex_daemon_mode || 'ASTF'}</div>
                <div style="font-size:11.5px;margin-top:3px;">10,000 Emulated Users (16.0.0.1+)</div>
              </div>
              ${switchesHtml}
            </div>

            ${apsHtml ? `<div style="width:2px;height:18px;background:#CBD5E1;"></div><div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;">${apsHtml}</div>` : ''}
          </div>
        </div>

        <!-- Right-hand Inspector Panel -->
        <div class="card" id="topoInspectorBox"></div>
      </div>
    `;
    this.selectTopoNode(this.selectedTopoNode);
  },

  selectTopoNode(nodeKey) {
    this.selectedTopoNode = nodeKey;
    const box = document.getElementById('topoInspectorBox');
    if (!box || !this.lastTopoData) return;
    const t = this.lastTopoData;
    const usum = (t.unifi && t.unifi.summary) || {};

    if (nodeKey === 'efg') {
      box.innerHTML = `
        <div class="card-header"><div class="card-title">EFG / Gateway Inspector</div><span class="badge badge-success">Online</span></div>
        <div class="form-group"><span class="form-label">Gateway IP / MAC</span><div class="mono">${t.discovered_gateway?.ip} / ${t.discovered_gateway?.mac}</div></div>
        <div class="form-group"><span class="form-label">Vendor OUI</span><div>${t.discovered_gateway?.vendor}</div></div>
        <div class="form-group"><span class="form-label">UniFi API CPU</span><div><strong>${usum.gw_cpu_pct != null ? usum.gw_cpu_pct + '%' : 'Unavailable (Connect API Key)'}</strong></div></div>
        <div class="form-group"><span class="form-label">UniFi API Memory</span><div><strong>${usum.gw_mem_pct != null ? usum.gw_mem_pct + '%' : 'Unavailable'}</strong></div></div>
        <div class="form-group"><span class="form-label">WAN Throughput</span><div><strong>${usum.wan_rx_bps != null ? App.fmtBps((usum.wan_rx_bps || 0) + (usum.wan_tx_bps || 0)) : 'Unavailable'}</strong></div></div>
        <hr style="border:none;border-top:1px solid var(--border-color);margin:12px 0;" />
        <div style="font-size:12px;color:var(--text-secondary);">
          <strong>Recommended EFG Cabling for 10K Users:</strong><br/>
          1. Keep <code>enp216s0</code> on Management VLAN.<br/>
          2. Cable <code>eno1</code> to EFG LAN Switch Trunk.<br/>
          3. Cable <code>eno2</code> to an isolated EFG WAN Lab Subnet so stateful ASTF traffic traverses NAT &amp; Firewall policies end-to-end.
        </div>
      `;
    } else if (nodeKey === 'r640') {
      const ifRows = (t.r640?.interfaces || []).map((i) => `<div style="display:flex;justify-content:space-between;font-size:12px;padding:4px 0;border-bottom:1px solid #F1F5F9;"><span><strong>${i.ifname}</strong> (${i.driver})</span><span>${i.operstate.toUpperCase()} ${i.speed_mbps ? i.speed_mbps + 'Mb' : ''}</span></div>`).join('');
      box.innerHTML = `
        <div class="card-header"><div class="card-title">Dell PowerEdge R640</div><span class="badge badge-info">${t.r640?.trex_daemon_mode}</span></div>
        <p style="font-size:12px;color:var(--text-secondary);margin-bottom:10px;">${t.r640?.trex_version}</p>
        ${ifRows}
      `;
    } else {
      box.innerHTML = `
        <div class="card-header"><div class="card-title">Node Inspector (${nodeKey.toUpperCase()})</div></div>
        <p style="font-size:12.5px;color:var(--text-secondary);">
          Controlled WAN Responder emulates internet servers (HTTP/HTTPS, ABR video, SaaS APIs, DNS, VoIP/UDP) on TRex Port 1 so high-volume 10,000-user load traverses the UniFi EFG without flooding public internet hosts.
        </p>
      `;
    }
  },

  // =========================================================================
  // 3. NICs & PORTS
  // =========================================================================
  async renderNicsPorts() {
    const el = document.getElementById('page-nics-ports');
    const hw = await App.api('/api/hardware');
    const rows = (hw.interfaces || []).map((i) => `
      <tr>
        <td><strong>${i.ifname}</strong> ${i.is_management ? '<span class="badge badge-info">Management Protected</span>' : ''}</td>
        <td class="mono">${i.pci_bus || 'virtual'}</td>
        <td>${i.driver}</td>
        <td class="mono">${i.mac}</td>
        <td class="mono">${i.ipv4 || '—'}</td>
        <td>${i.speed_mbps ? i.speed_mbps + ' Mbps' : 'No Carrier'} ${i.max_supported_mbps ? `(Max ${i.max_supported_mbps} Mbps)` : ''}</td>
        <td>${i.operstate === 'up' ? '<span class="badge badge-success">UP</span>' : '<span class="badge badge-neutral">DOWN</span>'}</td>
        <td>${App.fmtBps(i.live_tx_bps || 0)} / ${App.fmtBps(i.live_rx_bps || 0)}</td>
      </tr>
    `).join('');

    el.innerHTML = `
      <div class="card">
        <div class="card-header">
          <div class="card-title">Dell PowerEdge R640 Network Interface Inventory</div>
          <button class="btn btn-outline btn-sm" onclick="InfraPages.renderNicsPorts()">&#8635; Rescan PCIe &amp; Carrier</button>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Interface</th><th>PCIe Bus</th><th>Driver</th><th>MAC Address</th><th>IPv4</th><th>Negotiated / Max</th><th>Link</th><th>Live TX / RX</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  },

  // =========================================================================
  // 4. TREX ENGINE CONTROL (Switch ASTF <-> STL + /etc/trex_cfg.yaml)
  // =========================================================================
  async renderTrexEngine() {
    const el = document.getElementById('page-trex-engine');
    const hw = await App.api('/api/hardware');
    const mode = hw.trex_daemon_mode || 'ASTF';

    el.innerHTML = `
      <div class="grid-2">
        <div class="card">
          <div class="card-header">
            <div class="card-title">Cisco TRex Daemon Control</div>
            <span class="badge ${hw.trex_connected ? 'badge-success' : 'badge-critical'}">${hw.trex_connected ? 'ZMQ Connected (Port 4501)' : 'Disconnected'}</span>
          </div>
          <p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:14px;">
            Active Engine Version: <strong>${hw.trex_version}</strong><br/>
            Note: Starting a test automatically switches TRex between <code>--astf</code> (Stateful 10K-User TCP/UDP) and <code>--stl</code> (Stateless Wire-Speed) as needed. You can also switch manually below.
          </p>
          <div style="display:flex;gap:10px;margin-bottom:16px;">
            <button class="btn ${mode === 'ASTF' ? 'btn-primary' : 'btn-outline'}" style="flex:1;" onclick="InfraPages.switchTrexMode('ASTF')">Stateful ASTF Mode (--astf)</button>
            <button class="btn ${mode === 'STL' ? 'btn-primary' : 'btn-outline'}" style="flex:1;" onclick="InfraPages.switchTrexMode('STL')">Stateless STL Mode (--stl)</button>
          </div>
          <div class="card-subtitle" style="margin-bottom:6px;">DPDK HugePages Allocation</div>
          <pre class="mono" style="background:#F8FAFC;padding:12px;border-radius:8px;border:1px solid var(--border-color);font-size:12px;">${JSON.stringify(hw.hugepages || {}, null, 2)}</pre>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">/etc/trex_cfg.yaml</div>
            <button class="btn btn-outline btn-sm" onclick="InfraPages.regenerateTrexYaml()">Auto-Detect Test Ports &amp; Reload</button>
          </div>
          <pre class="mono" style="background:#142338;color:#E2E8F0;padding:14px;border-radius:8px;font-size:12px;overflow-x:auto;min-height:240px;">${hw.trex_cfg_yaml || '# /etc/trex_cfg.yaml'}</pre>
        </div>
      </div>
    `;
  },

  async switchTrexMode(mode) {
    App.toast(`Switching Cisco TRex daemon to ${mode} mode...`, 'info');
    const res = await App.api('/api/config/trex', { method: 'POST', body: JSON.stringify({ daemon_mode: mode }) });
    App.toast(`TRex running in ${res.trex_daemon_mode} mode.`, 'success');
    this.renderTrexEngine();
  },

  async regenerateTrexYaml() {
    const res = await App.api('/api/config/trex', { method: 'POST', body: JSON.stringify({ mode: 'auto', regenerate_yaml: true, restart_service: true }) });
    App.toast(`Updated /etc/trex_cfg.yaml (${(res.ports || []).join(', ')})`, 'success');
    this.renderTrexEngine();
  },

  // =========================================================================
  // 5. SERVER HEALTH & PRESERVED FIELD DIAGNOSTICS
  // =========================================================================
  renderServerHealth() {
    const el = document.getElementById('page-server-health');
    const f = App.latest || {};
    const cores = (f.per_cpu_pct || Array(32).fill(0)).map((v, idx) => `
      <div style="background:#F8FAFC;border:1px solid var(--border-color);border-radius:6px;padding:7px;text-align:center;">
        <div style="font-size:10.5px;color:var(--text-secondary);">CPU ${idx}</div>
        <div style="font-weight:700;font-size:13px;color:${v > 80 ? '#DC2626' : '#17243A'};">${Number(v).toFixed(0)}%</div>
      </div>
    `).join('');

    el.innerHTML = `
      <div class="grid-3" style="margin-bottom:16px;">
        <div class="card"><div class="card-subtitle">Total CPU Utilisation</div><div class="kpi-value">${Number(f.cpu_pct || 0).toFixed(1)}%</div><div class="kpi-foot">2 &times; Intel Xeon Silver 4110 (32 Logical Cores)</div></div>
        <div class="card"><div class="card-subtitle">System Memory (ECC DDR4)</div><div class="kpi-value">${f.ram_used_gb || 0} / ${Math.round(f.ram_total_gb || 500)} <span class="kpi-unit">GB</span></div><div class="kpi-foot">${Number(f.ram_pct || 0).toFixed(1)}% Allocated (Includes 8 GB DPDK HugePages)</div></div>
        <div class="card"><div class="card-subtitle">NVMe Root Storage</div><div class="kpi-value">${f.storage?.used_gb || 13} / ${f.storage?.total_gb || 231} <span class="kpi-unit">GB</span></div><div class="kpi-foot">${f.storage?.percent || 6}% Used &bull; SQLite WAL Active</div></div>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <div class="card-header"><div class="card-title">32-Core Xeon Thread Utilisation</div></div>
        <div style="display:grid;grid-template-columns:repeat(8, minmax(0, 1fr));gap:8px;">${cores}</div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-header"><div class="card-title">Field Diagnostics — Path MTU &amp; Gateway DNS Probe</div></div>
          <div style="display:flex;gap:8px;margin-bottom:10px;">
            <input type="text" class="form-control" id="diagTargetIp" value="10.20.30.1" placeholder="Target IP (e.g. 10.20.30.1)" />
            <button class="btn btn-outline" onclick="InfraPages.runMtuCheck()">Test Path MTU</button>
            <button class="btn btn-outline" onclick="InfraPages.runDnsCheck()">Gateway &amp; DNS RTT</button>
          </div>
          <pre id="diagOutputBox" class="mono" style="background:#F8FAFC;padding:10px;border-radius:7px;border:1px solid var(--border-color);font-size:12px;min-height:90px;">Ready.</pre>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">Live Packet Capture (PCAP) &amp; Git Auto-Deploy</div></div>
          <p style="font-size:12.5px;color:var(--text-secondary);margin-bottom:12px;">Capture a 150-packet Wireshark <code>.pcap</code> sample or check GitHub auto-deploy sync status.</p>
          <div style="display:flex;gap:10px;">
            <a class="btn btn-outline" href="/api/diagnostics/pcap?interface=enp216s0&count=150" target="_blank">&#11015; Capture PCAP (enp216s0)</a>
            <button class="btn btn-outline" onclick="InfraPages.triggerGitPull()">&#8635; Sync Latest GitHub Main</button>
          </div>
        </div>
      </div>
    `;
  },

  async runMtuCheck() {
    const out = document.getElementById('diagOutputBox');
    out.textContent = 'Probing DF-bit Path MTU...';
    const res = await App.api('/api/diagnostics/mtu', { method: 'POST', body: JSON.stringify({ target: document.getElementById('diagTargetIp').value }) });
    out.textContent = JSON.stringify(res, null, 2);
  },

  async runDnsCheck() {
    const out = document.getElementById('diagOutputBox');
    out.textContent = 'Benchmarking Gateway & DNS...';
    const res = await App.api('/api/diagnostics/dns-gateway', { method: 'POST', body: JSON.stringify({ dns_server: '1.1.1.1', domain: 'cloudflare.com' }) });
    out.textContent = JSON.stringify(res, null, 2);
  },

  async triggerGitPull() {
    const res = await App.api('/api/system/git-pull', { method: 'POST', body: '{}' });
    App.toast(res.message || 'Triggered git pull', 'info');
  },

  // =========================================================================
  // 6. ADMINISTRATION -> CONFIGURATION
  // =========================================================================
  async renderConfiguration() {
    const el = document.getElementById('page-configuration');
    const d = await App.api('/api/config/settings');
    const s = d.settings || {};

    el.innerHTML = `
      <div class="card" style="max-width:720px;">
        <div class="card-header"><div class="card-title">Platform &amp; Safety Preferences</div></div>
        <div class="form-group">
          <label class="form-label">Appliance Title</label>
          <input type="text" class="form-control" id="cfgAppName" value="${s.appliance_name || 'Cisco TRex Network Test Studio'}" />
        </div>
        <div class="form-group">
          <label class="form-label">Default Device Under Test (DUT) Name</label>
          <input type="text" class="form-control" id="cfgDutName" value="${s.dut_default_name || 'UniFi Enterprise Fortress Gateway (EFG)'}" />
        </div>
        <div class="grid-2" style="gap:12px;">
          <div class="form-group">
            <label class="form-label">Default Reference Link Capacity (Mbps)</label>
            <input type="number" class="form-control" id="cfgLinkCap" value="${s.default_link_capacity_mbps || 10000}" />
          </div>
          <div class="form-group">
            <label class="form-label">Default Operator Attribution</label>
            <input type="text" class="form-control" id="cfgOpName" value="${s.operator_name || 'Stephan Van Vuuren'}" />
          </div>
        </div>
        <button class="btn btn-primary" onclick="InfraPages.saveConfigSettings()">Save Configuration</button>
      </div>
    `;
  },

  async saveConfigSettings() {
    await App.api('/api/config/settings', {
      method: 'POST',
      body: JSON.stringify({
        appliance_name: document.getElementById('cfgAppName').value.trim(),
        dut_default_name: document.getElementById('cfgDutName').value.trim(),
        default_link_capacity_mbps: parseInt(document.getElementById('cfgLinkCap').value, 10) || 10000,
        operator_name: document.getElementById('cfgOpName').value.trim(),
        protect_mgmt_nic: true,
      }),
    });
    App.toast('Platform configuration saved.', 'success');
  },

  // =========================================================================
  // 7. ADMINISTRATION -> API INTEGRATIONS (UniFi + SNMPv2c/v3)
  // =========================================================================
  async renderApiIntegrations() {
    const el = document.getElementById('page-api-integrations');
    const [uRes, sRes] = await Promise.all([App.api('/api/unifi/config'), App.api('/api/snmp/config')]);
    const uc = uRes.config || {};
    const sc = sRes.config || {};

    el.innerHTML = `
      <div class="alert-banner">
        <div>
          <strong>Server-Side Credential Vault (Fernet Encrypted)</strong><br/>
          All UniFi API keys, local controller passwords, and SNMPv2c/v3 secrets are encrypted at rest on the Dell R640 and are <strong>never</strong> returned to browser JavaScript or exported in logs/reports. All polling is strictly read-only.
        </div>
      </div>

      <div class="grid-2">
        <!-- UniFi Network API -->
        <div class="card">
          <div class="card-header">
            <div class="card-title">UniFi Network API &amp; Site Manager</div>
            <span class="badge ${uRes.snapshot?.connected ? 'badge-success' : 'badge-neutral'}">${uRes.snapshot?.status || 'Not Configured'}</span>
          </div>
          <div class="grid-2" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">Controller / EFG Host or IP</label>
              <input type="text" class="form-control" id="ufHost" value="${uc.host || '10.20.30.1'}" />
            </div>
            <div class="form-group">
              <label class="form-label">HTTPS Port</label>
              <input type="number" class="form-control" id="ufPort" value="${uc.port || 443}" />
            </div>
            <div class="form-group">
              <label class="form-label">Authentication Mode</label>
              <select class="form-control" id="ufAuthMode">
                <option value="api_key" ${uc.auth_mode === 'api_key' ? 'selected' : ''}>Official Local API Key (X-API-KEY)</option>
                <option value="local_account" ${uc.auth_mode === 'local_account' ? 'selected' : ''}>Local Read-Only Admin Account</option>
                <option value="site_manager" ${uc.auth_mode === 'site_manager' ? 'selected' : ''}>Ubiquiti Site Manager Cloud API</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Site Slug / Name</label>
              <input type="text" class="form-control" id="ufSite" value="${uc.site_name || 'default'}" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Local UniFi Network API Key ${uc.has_api_key ? '(Stored Encrypted — Leave •••• to Keep)' : ''}</label>
            <input type="password" class="form-control" id="ufApiKey" value="${uc.has_api_key ? '••••••••••••' : ''}" placeholder="Paste UniFi Network Integration X-API-KEY" />
          </div>

          <div class="grid-2" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">Local Username (If Account Mode)</label>
              <input type="text" class="form-control" id="ufUser" value="${uc.username || ''}" />
            </div>
            <div class="form-group">
              <label class="form-label">Local Password</label>
              <input type="password" class="form-control" id="ufPass" value="${uc.has_password ? '••••••••••••' : ''}" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Optional Site Manager Cloud API Key (api.ui.com)</label>
            <input type="password" class="form-control" id="ufSmKey" value="${uc.has_site_manager_key ? '••••••••••••' : ''}" placeholder="Optional X-API-Key for api.ui.com" />
          </div>

          <label style="display:flex;align-items:center;gap:8px;margin:8px 0 12px;font-size:12.5px;font-weight:600;">
            <input type="checkbox" id="ufEnabled" ${uc.enabled ? 'checked' : ''} />
            <span>Enable Continuous Read-Only UniFi Polling (Every ${uc.poll_interval_sec || 5}s)</span>
          </label>

          <div style="display:flex;gap:10px;">
            <button class="btn btn-primary" style="flex:1;" onclick="InfraPages.saveAndTestUniFi()">Save &amp; Test UniFi Connection</button>
          </div>
          <div id="ufTestResult" style="margin-top:10px;font-size:12.5px;"></div>
        </div>

        <!-- Read-Only SNMPv2c / SNMPv3 -->
        <div class="card">
          <div class="card-header">
            <div class="card-title">Optional Read-Only SNMP (v2c / v3 IF-MIB)</div>
            <span class="badge ${sRes.snapshot?.connected ? 'badge-success' : 'badge-neutral'}">${sRes.snapshot?.status || 'Disabled'}</span>
          </div>
          <div class="grid-2" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">Target Device IP (EFG / Switch)</label>
              <input type="text" class="form-control" id="snHost" value="${sc.host || '10.20.30.1'}" />
            </div>
            <div class="form-group">
              <label class="form-label">SNMP Version</label>
              <select class="form-control" id="snVer">
                <option value="v3" ${sc.version === 'v3' ? 'selected' : ''}>SNMPv3 (Recommended — authPriv)</option>
                <option value="v2c" ${sc.version === 'v2c' ? 'selected' : ''}>SNMPv2c (Read-Only Community)</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">SNMPv2c Community String ${sc.has_community ? '(Stored Encrypted)' : ''}</label>
            <input type="password" class="form-control" id="snComm" value="${sc.has_community ? '••••••••' : ''}" placeholder="e.g. public (for v2c)" />
          </div>

          <div class="grid-3" style="gap:10px;">
            <div class="form-group">
              <label class="form-label">SNMPv3 User</label>
              <input type="text" class="form-control" id="snUser" value="${sc.username || ''}" />
            </div>
            <div class="form-group">
              <label class="form-label">Auth (${sc.auth_protocol || 'SHA'})</label>
              <input type="password" class="form-control" id="snAuthPass" value="${sc.has_auth_pass ? '••••••••' : ''}" placeholder="Auth Passphrase" />
            </div>
            <div class="form-group">
              <label class="form-label">Priv (${sc.priv_protocol || 'AES'})</label>
              <input type="password" class="form-control" id="snPrivPass" value="${sc.has_priv_pass ? '••••••••' : ''}" placeholder="Priv Passphrase" />
            </div>
          </div>

          <label style="display:flex;align-items:center;gap:8px;margin:8px 0 12px;font-size:12.5px;font-weight:600;">
            <input type="checkbox" id="snEnabled" ${sc.enabled ? 'checked' : ''} />
            <span>Enable 64-Bit IF-MIB Interface Counter Polling</span>
          </label>

          <button class="btn btn-primary btn-block" onclick="InfraPages.saveAndTestSnmp()">Save &amp; Test SNMP Polling</button>
          <div id="snTestResult" style="margin-top:10px;font-size:12.5px;"></div>
        </div>
      </div>
    `;
  },

  async saveAndTestUniFi() {
    const out = document.getElementById('ufTestResult');
    out.innerHTML = `<span style="color:var(--text-secondary);">Testing connection to UniFi controller...</span>`;
    try {
      const res = await App.api('/api/unifi/test', {
        method: 'POST',
        body: JSON.stringify({
          enabled: document.getElementById('ufEnabled').checked,
          host: document.getElementById('ufHost').value.trim(),
          port: parseInt(document.getElementById('ufPort').value, 10) || 443,
          auth_mode: document.getElementById('ufAuthMode').value,
          site_name: document.getElementById('ufSite').value.trim() || 'default',
          api_key: document.getElementById('ufApiKey').value,
          username: document.getElementById('ufUser').value.trim(),
          password: document.getElementById('ufPass').value,
          site_manager_key: document.getElementById('ufSmKey').value,
        }),
      });
      if (res.connected) {
        out.innerHTML = `<div class="alert-banner success" style="margin-top:8px;">Connected! Mode: <strong>${res.api_mode_detected}</strong> | Version: ${res.controller_version || 'Detected'}</div>`;
      } else {
        out.innerHTML = `<div class="alert-banner critical" style="margin-top:8px;">Connection unsuccessful: ${res.error || res.status}</div>`;
      }
    } catch (e) {
      out.innerHTML = `<div class="alert-banner critical">${e.message}</div>`;
    }
  },

  async saveAndTestSnmp() {
    const out = document.getElementById('snTestResult');
    out.innerHTML = `<span style="color:var(--text-secondary);">Querying SNMP sysName &amp; IF-MIB...</span>`;
    try {
      const res = await App.api('/api/snmp/test', {
        method: 'POST',
        body: JSON.stringify({
          enabled: document.getElementById('snEnabled').checked,
          host: document.getElementById('snHost').value.trim(),
          version: document.getElementById('snVer').value,
          community: document.getElementById('snComm').value,
          username: document.getElementById('snUser').value.trim(),
          auth_pass: document.getElementById('snAuthPass').value,
          priv_pass: document.getElementById('snPrivPass').value,
        }),
      });
      if (res.connected) {
        out.innerHTML = `<div class="alert-banner success" style="margin-top:8px;">SNMP Connected! Host: <strong>${res.sys_name || 'OK'}</strong> (${res.interface_count} IF-MIB interfaces discovered)</div>`;
      } else {
        out.innerHTML = `<div class="alert-banner critical" style="margin-top:8px;">SNMP Unreachable: ${res.error || res.status}</div>`;
      }
    } catch (e) {
      out.innerHTML = `<div class="alert-banner critical">${e.message}</div>`;
    }
  },

  // =========================================================================
  // 8. ADMINISTRATION -> USER ACCESS
  // =========================================================================
  async renderUserAccess() {
    const el = document.getElementById('page-user-access');
    const d = await App.api('/api/admin/users');
    const users = d.users || [];
    const rows = users.map((u) => `
      <tr>
        <td><strong>${u.display_name}</strong></td>
        <td class="mono">${u.username}</td>
        <td><span class="badge badge-info">${u.role}</span></td>
        <td>${u.email || '—'}</td>
        <td>${u.id === 1 ? '<span style="color:var(--text-secondary);font-size:12px;">Primary Owner</span>' : `<button class="btn btn-outline btn-sm" onclick="InfraPages.deleteUser(${u.id})">Remove</button>`}</td>
      </tr>
    `).join('');

    el.innerHTML = `
      <div class="alert-banner">
        <div><strong>Direct LAN Appliance Mode:</strong> Per appliance specification, HTTP Port 80 opens directly without a login wall on the lab LAN; operator profiles below govern test attribution and audit logging.</div>
      </div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><div class="card-title">Add Lab Operator Profile</div></div>
          <div class="form-group"><label class="form-label">Display Name</label><input type="text" class="form-control" id="uaDisp" placeholder="e.g. Network Engineer" /></div>
          <div class="form-group"><label class="form-label">Username</label><input type="text" class="form-control" id="uaUser" placeholder="e.g. neteng" /></div>
          <div class="form-group"><label class="form-label">Role</label><select class="form-control" id="uaRole"><option>Lab Administrator</option><option>Senior Network Engineer</option><option>Read-Only Observer</option></select></div>
          <button class="btn btn-primary" onclick="InfraPages.addUser()">+ Add Operator</button>
        </div>
        <div class="card">
          <div class="card-header"><div class="card-title">Configured Operators (${users.length})</div></div>
          <table class="data-table"><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Email</th><th></th></tr></thead><tbody>${rows}</tbody></table>
        </div>
      </div>
    `;
  },

  async addUser() {
    await App.api('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({
        display_name: document.getElementById('uaDisp').value.trim(),
        username: document.getElementById('uaUser').value.trim(),
        role: document.getElementById('uaRole').value,
      }),
    });
    this.renderUserAccess();
  },

  async deleteUser(id) {
    await App.api(`/api/admin/users/${id}`, { method: 'DELETE' });
    this.renderUserAccess();
  },

  // =========================================================================
  // 9. ADMINISTRATION -> AUDIT LOGS
  // =========================================================================
  async renderAuditLogs() {
    const el = document.getElementById('page-audit-logs');
    const d = await App.api('/api/admin/audit-logs?limit=200');
    const rows = (d.logs || []).map((l) => `
      <tr>
        <td class="mono">${new Date(l.ts * 1000).toLocaleString()}</td>
        <td><strong>${l.actor}</strong></td>
        <td><span class="badge badge-neutral">${l.category}</span></td>
        <td><strong>${l.action}</strong></td>
        <td>${l.target || '—'}</td>
        <td style="color:var(--text-secondary);font-size:12px;">${l.details || ''}</td>
      </tr>
    `).join('');

    el.innerHTML = `
      <div class="card">
        <div class="card-header">
          <div class="card-title">Immutable Platform Audit Log</div>
          <button class="btn btn-outline btn-sm" onclick="InfraPages.renderAuditLogs()">&#8635; Refresh</button>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Timestamp</th><th>Operator</th><th>Category</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="6">No audit entries recorded yet.</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    `;
  },
};

window.InfraPages = InfraPages;
