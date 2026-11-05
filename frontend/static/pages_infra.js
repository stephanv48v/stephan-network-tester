/* ==========================================================================
   Codeblue Network Test Studio — "My Network" (UniFi, Topology, Ports) and
   "System & Settings" (Server Health, Traffic engine, Integrations, Settings,
   Users, Activity log) pages.
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

// ---------------------------------------------------------------------------
// Small presentation helpers (plain-English wording lives here so every page
// says the same thing the same way)
// ---------------------------------------------------------------------------
const IX = {
  esc(s) { return App.esc(s); },

  // Card header: title + one-line "what is this for", optional right-hand HTML
  head(title, desc, right = '') {
    return `<div class="card-header" style="align-items:flex-start;">
      <div>
        <div class="card-title">${title}</div>
        ${desc ? `<div class="card-subtitle" style="margin-top:3px;max-width:760px;line-height:1.45;">${desc}</div>` : ''}
      </div>
      ${right ? `<div style="display:flex;gap:8px;align-items:center;flex-shrink:0;">${right}</div>` : ''}
    </div>`;
  },

  // Status banner: kind = info | warning | critical | success
  banner(kind, title, body = '', actions = '') {
    return `<div class="alert-banner ${kind}">
      <div style="line-height:1.5;"><strong style="font-size:13px;">${title}</strong>${body ? `<br/>${body}` : ''}</div>
      ${actions ? `<div style="display:flex;gap:8px;flex-shrink:0;">${actions}</div>` : ''}
    </div>`;
  },

  // Muted "not reported" in place of a bare "Unavailable"
  na(tip = 'Your UniFi API does not report this value. It will appear here when it does.') {
    return `<span style="color:var(--text-secondary);font-weight:500;" title="${App.esc(tip)}">not reported</span>`;
  },

  muted(text) { return `<span style="color:var(--text-secondary);">${text}</span>`; },

  small(text) { return `<div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;line-height:1.4;">${text}</div>`; },

  plural(n, one, many) { return `${n} ${Number(n) === 1 ? one : (many || one + 's')}`; },

  pct(v) { return v != null ? `${Number(v).toFixed(0)}%` : null; },

  fmtMbps(m) {
    const v = Number(m || 0);
    if (!v) return '—';
    return v >= 1000 ? `${+(v / 1000).toFixed(1)} Gbps` : `${v} Mbps`;
  },

  modeWords(mode) {
    const m = String(mode || '').toUpperCase();
    if (m === 'ASTF') return 'realistic-user mode (stateful)';
    if (m === 'STL') return 'raw-speed mode (stateless)';
    return 'an unknown mode';
  },

  online(ok) {
    return ok ? '<span class="badge badge-success">Online</span>' : '<span class="badge badge-critical">Offline</span>';
  },

  details(summary, inner, open = false, extra = '') {
    return `<details ${open ? 'open' : ''} ${extra} style="margin-top:12px;">
      <summary style="cursor:pointer;font-size:12.5px;font-weight:600;color:var(--text-secondary);user-select:none;">${summary}</summary>
      <div style="margin-top:10px;">${inner}</div>
    </details>`;
  },

  // What each server network port is for, in words
  portRole(i) {
    const name = String(i.ifname || '');
    const virtual = name.startsWith('veth') || i.pci_bus === 'virtual' || i.pci_address === 'virtual';
    const linked = !!(i.link_detected || (i.operstate === 'up' && Number(i.speed_mbps) > 0));
    if (virtual) {
      return { label: 'Internal loopback', badge: 'neutral', linked,
        hint: 'A virtual cable inside this server. The traffic engine uses it for self-tests when the test ports are not cabled. Traffic on it never leaves the server.' };
    }
    if (i.is_management) {
      return { label: 'Management — don\'t touch', badge: 'info', linked,
        hint: 'Carries this web page and remote access to the server. It is never used for test traffic, so a test can\'t cut you off.' };
    }
    const where = name === 'eno1' ? 'an EFG LAN port' : name === 'eno2' ? 'a second EFG port or VLAN' : null;
    if (linked) {
      return { label: 'Test port — connected', badge: 'success', linked,
        hint: `Linked at ${IX.fmtMbps(i.speed_mbps)}.${where ? ` This one should go to ${where}.` : ' Spare test port.'}` };
    }
    return { label: where ? 'Test port — unplugged' : 'Spare port — unplugged', badge: where ? 'warning' : 'neutral', linked,
      hint: where ? `Cable it to ${where}.` : 'Not needed for normal tests.' };
  },

  topoAssessment(fromApi) {
    const ta = (fromApi && Object.keys(fromApi).length) ? fromApi : ((App.latest || {}).topology_assessment || {});
    return ta;
  },

  // Honest "where does test traffic actually go?" banner (Ports + Topology pages)
  cablingBanner(ta, linkToPorts = true) {
    const code = ta && ta.active_mode_code;
    if (code === 'physical_lan_wan') {
      return IX.banner('success', 'Test ports are cabled — test traffic goes out through your gateway.',
        IX.muted(IX.esc(ta.active_mode_label || '')));
    }
    if (!code) {
      return IX.banner('warning', 'Can\'t tell yet how the test ports are cabled.',
        'The server hasn\'t reported its network ports. Until two test ports show a link, assume test traffic stays inside this server. To test your gateway, cable <strong>eno1</strong> to an EFG LAN port and <strong>eno2</strong> to a second EFG port/VLAN.',
        linkToPorts ? `<button class="btn btn-outline btn-sm" onclick="App.navigate('nics-ports')">Check ports</button>` : '');
    }
    return IX.banner('warning', 'Test traffic currently stays inside this server (internal loopback).',
      'To test your gateway, cable <strong>eno1</strong> to an EFG LAN port and <strong>eno2</strong> to a second EFG port/VLAN. Until then, results show what this server can generate — not what your gateway can handle.',
      linkToPorts ? `<button class="btn btn-outline btn-sm" onclick="App.navigate('nics-ports')">See ports</button>` : '');
  },
};

const InfraPages = {
  unifiSubTab: 'gateways',
  selectedTopoNode: 'efg',
  lastTopoData: null,
  coresOpen: false,

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
  // 1. UNIFI
  // =========================================================================
  async renderUniFiMonitoring(forceRefresh = false) {
    const el = document.getElementById('page-unifi-monitoring');
    const E = IX.esc;
    const [snap, snmpSnap] = await Promise.all([
      App.api(`/api/unifi/telemetry?refresh=${forceRefresh ? 1 : 0}`).catch((e) => ({ connected: false, status: 'Could not reach this server', last_error: e.message })),
      App.api(`/api/snmp/telemetry?refresh=${forceRefresh ? 1 : 0}`).catch(() => ({ connected: false, status: 'Unknown' })),
    ]);
    if (forceRefresh) App.toast(snap.connected ? 'UniFi data refreshed.' : 'Still not connected to UniFi.', snap.connected ? 'success' : 'error');

    const s = snap.summary || {};
    const caps = snap.capabilities || {};
    const capPill = (ok) => ok ? `<span class="badge badge-success">Yes</span>` : `<span class="badge badge-neutral">No</span>`;
    const setupBtn = `<button class="btn btn-primary btn-sm" onclick="App.navigate('api-integrations')">Set up UniFi</button>`;

    // ---- Status first ----
    let statusHtml;
    if (snap.connected) {
      const parts = [
        IX.plural(s.switches_total || 0, 'switch', 'switches'),
        IX.plural(s.aps_total || 0, 'access point'),
        s.active_clients != null ? IX.plural(Number(s.active_clients).toLocaleString(), 'client') : null,
      ].filter(Boolean).join(', ');
      statusHtml = IX.banner('success', `Connected to ${E(s.gw_name || 'your UniFi controller')} — ${parts}`,
        IX.muted(`Read-only. Refreshed automatically every few seconds${snap.api_mode_detected ? ` via ${E(snap.api_mode_detected)}` : ''}.`),
        `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderUniFiMonitoring(true)">Refresh now</button>`);
    } else {
      statusHtml = IX.banner('warning', 'Not connected to UniFi yet',
        `Enter your controller address and an API key in <strong>Integrations</strong>. To create a key, open UniFi Network and go to <strong>Settings &rarr; Control Plane &rarr; Integrations</strong>.
         ${snap.last_error ? `<div style="margin-top:4px;font-size:11.5px;">Last error: <code>${E(snap.last_error)}</code></div>` : ''}
         ${snap.status && snap.status !== 'Not Configured' ? `<div style="font-size:11.5px;">Status: ${E(snap.status)}</div>` : ''}`,
        `${setupBtn}<button class="btn btn-outline btn-sm" onclick="InfraPages.renderUniFiMonitoring(true)">Try again</button>`);
    }

    // ---- Tab bodies ----
    const notConnectedBody = (what) => `
      <div style="padding:22px 6px;text-align:center;">
        <div style="font-weight:700;font-size:13.5px;margin-bottom:4px;">No ${what} to show yet</div>
        <div class="card-subtitle" style="margin-bottom:12px;">They appear here once this app is connected to your UniFi controller.</div>
        ${setupBtn}
      </div>`;
    const table = (head, rows, emptyText, cols) => `<div class="table-wrap"><table class="data-table"><thead><tr>${head}</tr></thead><tbody>${rows || `<tr><td colspan="${cols}" style="color:var(--text-secondary);">${emptyText}</td></tr>`}</tbody></table></div>`;
    const p = (v) => v != null ? `${v}%` : IX.na();

    let tabIntro = '';
    let tabBody = '';
    if (this.unifiSubTab === 'snmp') {
      tabIntro = 'Exact per-port counters read straight from the device over SNMP: traffic rates, errors and dropped packets. Optional — useful when you need to prove a port is dropping packets.';
      const rows = (snmpSnap.interfaces || []).map((i) => `
        <tr>
          <td class="mono" title="Interface index">${E(i.if_index)}</td>
          <td><strong>${E(i.if_name)}</strong></td>
          <td>${String(i.oper_status).toLowerCase() === 'up' ? '<span class="badge badge-success">Up</span>' : `<span class="badge badge-neutral">${E(i.oper_status || 'Down')}</span>`}</td>
          <td>${i.speed_mbps ? IX.fmtMbps(i.speed_mbps) : '—'}</td>
          <td>${i.in_bps != null ? App.fmtBps(i.in_bps) : IX.muted('measuring…')}</td>
          <td>${i.out_bps != null ? App.fmtBps(i.out_bps) : IX.muted('measuring…')}</td>
          <td>${E(i.in_errors ?? 0)} / ${E(i.out_errors ?? 0)}</td>
          <td>${E(i.in_discards ?? 0)} / ${E(i.out_discards ?? 0)}</td>
          <td class="mono" style="color:var(--text-secondary);">${E(i.counter_width)}</td>
        </tr>`).join('');
      tabBody = snmpSnap.connected
        ? table('<th>#</th><th>Port</th><th>State</th><th>Speed</th><th>In</th><th>Out</th><th title="In / out">Errors</th><th title="In / out — packets the device threw away">Dropped</th><th title="Counter size in bits">Counter</th>', rows, 'The device answered but reported no interfaces.', 9)
        : `<div style="padding:22px 6px;text-align:center;">
            <div style="font-weight:700;font-size:13.5px;margin-bottom:4px;">SNMP is off${snmpSnap.status && snmpSnap.status !== 'Disabled' ? ` (${E(snmpSnap.status)})` : ''}</div>
            <div class="card-subtitle" style="margin-bottom:12px;">Turn it on in Integrations if you need per-port error and drop counters. Most people can skip this.</div>
            <button class="btn btn-outline btn-sm" onclick="App.navigate('api-integrations')">Open Integrations</button>
          </div>`;
    } else if (!snap.connected) {
      const what = { gateways: 'gateways', switches: 'switches', aps: 'access points', clients: 'clients' }[this.unifiSubTab] || 'devices';
      tabBody = notConnectedBody(what);
    } else if (this.unifiSubTab === 'gateways') {
      tabIntro = 'Your gateway is the device being tested. Watch its CPU and memory while a test runs — if they hit 100%, the gateway is the bottleneck.';
      const rows = (snap.gateways || []).map((g) => `
        <tr>
          <td><strong>${E(g.name || 'UniFi gateway')}</strong></td>
          <td>${E(g.model || '—')}</td>
          <td class="mono">${E(g.ip || '—')}</td>
          <td>${E(g.firmware || '—')}</td>
          <td>${IX.online(g.online)}</td>
          <td>${p(g.cpu_pct)}</td>
          <td>${p(g.mem_pct)}</td>
          <td>${g.wan_rx_bps != null ? App.fmtBps(g.wan_rx_bps) + ' / ' + App.fmtBps(g.wan_tx_bps || 0) : IX.na()}</td>
        </tr>`).join('');
      tabBody = table('<th>Gateway</th><th>Model</th><th>IP address</th><th>Firmware</th><th>State</th><th>CPU</th><th>Memory</th><th title="Download / upload on the internet link">Internet down / up</th>', rows, 'Connected, but the controller didn\'t return a gateway. Check the site name in Integrations &rarr; Advanced.', 8);
    } else if (this.unifiSubTab === 'switches') {
      tabIntro = 'UniFi switches on this site. An offline switch between this server and the gateway will break tests.';
      const rows = (snap.switches || []).map((sw) => `
        <tr>
          <td><strong>${E(sw.name || 'Switch')}</strong></td>
          <td>${E(sw.model || '—')}</td>
          <td class="mono">${E(sw.ip || '—')}</td>
          <td>${IX.online(sw.online)}</td>
          <td>${p(sw.cpu_pct)}</td>
          <td>${p(sw.mem_pct)}</td>
          <td>${Array.isArray(sw.ports) ? IX.plural(sw.ports.length, 'port') : IX.na('This UniFi API version does not report per-port details.')}</td>
        </tr>`).join('');
      tabBody = table('<th>Switch</th><th>Model</th><th>IP address</th><th>State</th><th>CPU</th><th>Memory</th><th>Ports</th>', rows, 'No switches on this site.', 7);
    } else if (this.unifiSubTab === 'aps') {
      tabIntro = 'Wi-Fi access points on this site and how many devices are connected to each.';
      const rows = (snap.access_points || []).map((ap) => `
        <tr>
          <td><strong>${E(ap.name || 'Access point')}</strong></td>
          <td>${E(ap.model || '—')}</td>
          <td class="mono">${E(ap.ip || '—')}</td>
          <td>${IX.online(ap.online)}</td>
          <td>${ap.num_sta != null ? E(ap.num_sta) : IX.na()}</td>
          <td>${p(ap.cpu_pct)}</td>
        </tr>`).join('');
      tabBody = table('<th>Access point</th><th>Model</th><th>IP address</th><th>State</th><th>Clients</th><th>CPU</th>', rows, 'No access points on this site.', 6);
    } else if (this.unifiSubTab === 'clients') {
      tabIntro = 'Devices currently connected to your network (first 100). Useful to check real users aren\'t affected while a test runs.';
      const rows = (snap.clients || []).slice(0, 100).map((c) => `
        <tr>
          <td><strong>${E(c.hostname || c.mac || 'Client')}</strong></td>
          <td class="mono">${E(c.ip || '—')}</td>
          <td>${c.is_wired ? 'Wired' : 'Wi-Fi'}</td>
          <td>${E(c.network || '—')}</td>
          <td>${c.rx_bps != null ? App.fmtBps(c.rx_bps) : '—'}</td>
          <td>${c.tx_bps != null ? App.fmtBps(c.tx_bps) : '—'}</td>
        </tr>`).join('');
      tabBody = table('<th>Device</th><th>IP address</th><th>Connection</th><th>Network</th><th>Download</th><th>Upload</th>', rows, 'No client list was returned — your UniFi API version may not report clients.', 6);
    }

    // ---- KPIs (only when there is something real to show) ----
    const kpis = snap.connected ? `
      <div class="grid-4" style="margin-bottom:14px;">
        <div class="card"><div class="card-subtitle">Gateway CPU${s.gw_name ? ` — ${E(s.gw_name)}` : ''}</div>
          <div class="kpi-value">${s.gw_cpu_pct != null ? `${s.gw_cpu_pct}%` : IX.na()}</div>
          <div class="kpi-foot">Memory ${s.gw_mem_pct != null ? `${s.gw_mem_pct}%` : 'not reported'}${s.gw_temp_c != null ? ` · ${App.tempSpan(s.gw_temp_c, 75, 90)}` : ''}</div></div>
        <div class="card"><div class="card-subtitle">Internet traffic right now</div>
          <div class="kpi-value">${s.wan_rx_bps != null ? App.fmtBps((s.wan_rx_bps || 0) + (s.wan_tx_bps || 0)) : IX.na()}</div>
          <div class="kpi-foot">${s.wan_rx_bps != null ? `Down ${App.fmtBps(s.wan_rx_bps || 0)} · Up ${App.fmtBps(s.wan_tx_bps || 0)}` : ''}${s.wan_latency_ms != null ? ` · ${s.wan_latency_ms} ms latency` : ''}</div></div>
        <div class="card"><div class="card-subtitle">Switches &amp; access points online</div>
          <div class="kpi-value">${(s.switches_online || 0) + (s.aps_online || 0)} <span class="kpi-unit">of ${(s.switches_total || 0) + (s.aps_total || 0)}</span></div>
          <div class="kpi-foot">Switches ${s.switches_online || 0}/${s.switches_total || 0} · APs ${s.aps_online || 0}/${s.aps_total || 0}</div></div>
        <div class="card"><div class="card-subtitle">Connected devices</div>
          <div class="kpi-value">${s.active_clients != null ? Number(s.active_clients).toLocaleString() : IX.na()}</div>
          <div class="kpi-foot">Phones, laptops and other clients</div></div>
      </div>` : '';

    const capsHtml = snap.connected ? `<div class="card" style="margin-bottom:14px;padding:10px 18px;">${IX.details('What your UniFi API reports',
      `<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;align-items:center;">
        <span>Gateway CPU &amp; memory ${capPill(caps.gateway_cpu_mem)}</span>
        <span>Internet traffic rate ${capPill(caps.wan_throughput)}</span>
        <span>Switch port counters ${capPill(caps.switch_port_counters)}</span>
        <span>Wi-Fi radio stats ${capPill(caps.ap_radio_stats)}</span>
        <span>Client list ${capPill(caps.client_inventory)}</span>
      </div>
      ${IX.small('Different UniFi versions and API types expose different data. Anything marked "No" shows as "not reported" on this page.')}`)}</div>` : '';

    const tabBtn = (key, label) => `<button class="subtab-btn ${this.unifiSubTab === key ? 'active' : ''}" onclick="InfraPages.unifiSubTab='${key}';InfraPages.renderUniFiMonitoring()">${label}</button>`;

    el.innerHTML = `
      ${statusHtml}
      ${kpis}
      ${capsHtml}
      <div class="subtab-bar">
        ${tabBtn('gateways', 'Gateway')}
        ${tabBtn('switches', 'Switches')}
        ${tabBtn('aps', 'Access points')}
        ${tabBtn('clients', 'Clients')}
        ${tabBtn('snmp', 'SNMP counters')}
      </div>
      <div class="card">
        ${tabIntro ? `<div class="card-subtitle" style="margin-bottom:10px;">${tabIntro}</div>` : ''}
        ${tabBody}
      </div>
    `;
  },

  // =========================================================================
  // 2. NETWORK TOPOLOGY (diagram + inspector + honest cabling assessment)
  // =========================================================================
  async renderNetworkTopology() {
    const el = document.getElementById('page-network-topology');
    const E = IX.esc;
    let topo;
    try {
      topo = await App.api('/api/topology');
    } catch (e) {
      el.innerHTML = IX.banner('critical', 'Couldn\'t load the network map', E(e.message),
        `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderNetworkTopology()">Try again</button>`);
      return;
    }
    this.lastTopoData = topo;
    const ta = IX.topoAssessment(topo.topology_assessment);
    const u = topo.unifi || {};
    const usum = u.summary || {};
    const gw = topo.discovered_gateway || {};
    const r = topo.r640 || {};

    const sel = (k) => (this.selectedTopoNode === k ? 'selected' : '');
    const tag = (text, color = 'var(--text-secondary)') => `<div style="font-size:10.5px;letter-spacing:.04em;color:${color};font-weight:700;">${text}</div>`;
    const line = (c = '#94A3B8') => `<div style="width:2px;height:22px;background:${c};"></div>`;

    let switchesHtml;
    if (u.switches && u.switches.length > 0) {
      switchesHtml = u.switches.slice(0, 3).map((sw, idx) => `
        <div class="topo-node ${sel('sw_' + idx)}" onclick="InfraPages.selectTopoNode('sw_${idx}')">
          ${tag('SWITCH')}
          <div style="font-weight:700;margin:2px 0;">${E(sw.name || 'Switch')}</div>
          <div style="font-size:11.5px;color:${sw.online ? '#15803D' : '#DC2626'};">${sw.online ? 'Online' : 'Offline'}${sw.model ? ` · ${E(sw.model)}` : ''}</div>
        </div>`).join('');
    } else {
      switchesHtml = `
        <div class="topo-node" style="border-style:dashed;max-width:220px;cursor:default;">
          ${tag('SWITCHES')}
          <div style="font-size:12px;margin-top:3px;">${u.connected ? 'No UniFi switches reported on this site.' : 'Connect UniFi to show your switches and access points here.'}</div>
          ${u.connected ? '' : `<button class="btn btn-outline btn-sm" style="margin-top:6px;" onclick="event.stopPropagation();App.navigate('api-integrations')">Set up UniFi</button>`}
        </div>`;
    }

    const apsHtml = (u.access_points && u.access_points.length > 0 ? u.access_points.slice(0, 4) : [])
      .map((ap, idx) => `
        <div class="topo-node ${sel('ap_' + idx)}" style="min-width:120px;padding:8px 10px;" onclick="InfraPages.selectTopoNode('ap_${idx}')">
          ${tag('ACCESS POINT')}
          <div style="font-weight:600;font-size:12px;">${E(ap.name || 'Access point')}</div>
          <div style="font-size:11px;color:var(--text-secondary);">${E(ap.model || '')}</div>
        </div>`).join('');

    const physical = ta.active_mode_code === 'physical_lan_wan';

    el.innerHTML = `
      ${IX.cablingBanner(ta)}

      <div class="topology-layout">
        <div class="card" style="padding:20px 24px;">
          ${IX.head('Network map',
            'How test traffic flows: this server plays your users on one side of the gateway and the internet on the other, so the traffic has to pass through the gateway. Click any box for details.',
            `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderNetworkTopology()">Refresh</button>`)}

          <div style="display:flex;flex-direction:column;align-items:center;gap:14px;padding:10px 0;">
            <div class="topo-node ${sel('wan')}" onclick="InfraPages.selectTopoNode('wan')" title="TRex port 1 — responder subnet 48.0.0.0/16">
              ${tag('INTERNET SIDE')}
              <div style="font-weight:700;">Simulated internet servers</div>
              <div style="font-size:11.5px;color:var(--primary);">Websites, video and apps your test users reach</div>
            </div>

            ${line()}

            <div class="topo-node ${sel('efg')}" style="min-width:240px;border-width:2px;" onclick="InfraPages.selectTopoNode('efg')">
              ${tag('DEVICE BEING TESTED', 'var(--primary)')}
              <div style="font-size:15px;font-weight:800;margin:3px 0;">${E(usum.gw_name || 'Your UniFi gateway')}</div>
              <div class="mono" style="font-size:12px;color:var(--text-secondary);" title="${E(gw.mac || '')}">${E(gw.ip || '—')}</div>
              <div style="margin-top:4px;">${gw.reachable ? '<span class="badge badge-success">Reachable</span>' : '<span class="badge badge-neutral" title="This server has not seen the gateway on the management network recently">Not seen yet</span>'}</div>
            </div>

            ${line()}

            <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:20px;align-items:center;">
              <div class="topo-node ${sel('r640')}" style="min-width:230px;background:#F8FAFC;" onclick="InfraPages.selectTopoNode('r640')">
                ${tag('THIS SERVER — TRAFFIC GENERATOR', '#1769D2')}
                <div style="font-weight:800;font-size:14px;">${E(r.name || 'Dell PowerEdge R640')}</div>
                <div class="mono" style="font-size:11.5px;color:var(--text-secondary);">${E(r.management_ip || '')}</div>
                <div style="font-size:11.5px;margin-top:3px;">Simulates up to 10,000 users</div>
                <div style="font-size:11px;margin-top:3px;color:${physical ? '#15803D' : '#B45309'};">${physical ? 'Test ports cabled to the gateway' : 'Test ports not cabled — traffic stays inside'}</div>
              </div>
              ${switchesHtml}
            </div>

            ${apsHtml ? `${line('#CBD5E1')}<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;">${apsHtml}</div>` : ''}
          </div>

          ${ta.honest_10g_explanation ? IX.details('Why tests through the gateway are limited to about 1 Gbps', `<div style="font-size:12px;color:var(--text-secondary);line-height:1.5;">${E(ta.honest_10g_explanation)}</div>`) : ''}
        </div>

        <div class="card" id="topoInspectorBox"></div>
      </div>
    `;
    this.selectTopoNode(this.selectedTopoNode);
  },

  selectTopoNode(nodeKey) {
    this.selectedTopoNode = nodeKey;
    const box = document.getElementById('topoInspectorBox');
    if (!box || !this.lastTopoData) return;
    const E = IX.esc;
    const t = this.lastTopoData;
    const u = t.unifi || {};
    const usum = u.summary || {};
    const gw = t.discovered_gateway || {};
    const row = (label, val) => `<div class="form-group"><span class="form-label">${label}</span><div>${val}</div></div>`;
    const connectHint = u.connected ? '' : `<div class="alert-banner info" style="margin-top:6px;"><div>Connect UniFi to see live CPU, memory and traffic for this device.</div><button class="btn btn-primary btn-sm" onclick="App.navigate('api-integrations')">Set up</button></div>`;
    document.querySelectorAll('#page-network-topology .topo-node').forEach((n) => {
      const m = (n.getAttribute('onclick') || '').match(/selectTopoNode\('([^']+)'\)/);
      if (m) n.classList.toggle('selected', m[1] === nodeKey);
    });

    if (nodeKey === 'efg') {
      box.innerHTML = `
        ${IX.head('Your gateway', 'The firewall / router being tested. Test traffic must pass through it.', gw.reachable ? '<span class="badge badge-success">Reachable</span>' : '<span class="badge badge-neutral">Not seen yet</span>')}
        ${row('Address', `<span class="mono">${E(gw.ip || '—')}</span>${gw.mac ? IX.small(`MAC ${E(gw.mac)}${gw.vendor ? ` · ${E(gw.vendor)}` : ''}`) : ''}`)}
        ${u.connected ? `
          ${row('CPU', `<strong>${usum.gw_cpu_pct != null ? usum.gw_cpu_pct + '%' : IX.na()}</strong>`)}
          ${row('Memory', `<strong>${usum.gw_mem_pct != null ? usum.gw_mem_pct + '%' : IX.na()}</strong>`)}
          ${row('Internet traffic', `<strong>${usum.wan_rx_bps != null ? App.fmtBps((usum.wan_rx_bps || 0) + (usum.wan_tx_bps || 0)) : IX.na()}</strong>`)}
        ` : connectHint}
        <hr style="border:none;border-top:1px solid var(--border-color);margin:12px 0;" />
        <div style="font-size:12px;color:var(--text-secondary);line-height:1.55;">
          <strong style="color:var(--text-main);">How to cable it for a real test</strong><br/>
          1. Leave the management port (<code>${E(t.r640?.management_interface || 'enp216s0')}</code>) where it is.<br/>
          2. Cable <code>eno1</code> to an EFG LAN port.<br/>
          3. Cable <code>eno2</code> to a second EFG port/VLAN, so traffic crosses the gateway's NAT and firewall rules.
        </div>
      `;
    } else if (nodeKey === 'r640') {
      const ifs = t.r640?.interfaces || [];
      const ifRows = ifs.map((i) => {
        const role = IX.portRole(i);
        return `<div style="display:flex;justify-content:space-between;gap:8px;font-size:12px;padding:6px 0;border-bottom:1px solid #F1F5F9;" title="${E(role.hint)}">
          <span><strong>${E(i.ifname)}</strong><br/><span style="color:var(--text-secondary);font-size:11px;">${E(role.label)}</span></span>
          <span style="text-align:right;">${role.linked ? `<span class="badge badge-success">${IX.fmtMbps(i.speed_mbps)}</span>` : '<span class="badge badge-neutral">No link</span>'}</span>
        </div>`;
      }).join('');
      box.innerHTML = `
        ${IX.head('This server', 'Generates the test traffic.', `<span class="badge ${t.r640?.trex_connected ? 'badge-success' : 'badge-critical'}">${t.r640?.trex_connected ? 'Engine running' : 'Engine offline'}</span>`)}
        <p style="font-size:12px;color:var(--text-secondary);margin-bottom:10px;">Traffic engine: ${t.r640?.trex_connected ? IX.modeWords(t.r640?.trex_daemon_mode) : 'offline'}${t.r640?.trex_version ? `<br/><span style="font-size:11px;">${E(t.r640.trex_version)}</span>` : ''}</p>
        ${ifRows || `<div style="font-size:12px;color:var(--text-secondary);">No network ports reported by the server.</div>`}
        <button class="btn btn-outline btn-sm" style="margin-top:12px;" onclick="App.navigate('nics-ports')">Open ports page</button>
      `;
    } else if (nodeKey.startsWith('sw_') || nodeKey.startsWith('ap_')) {
      const isSw = nodeKey.startsWith('sw_');
      const d = ((isSw ? u.switches : u.access_points) || [])[Number(nodeKey.slice(3))] || {};
      box.innerHTML = `
        ${IX.head(E(d.name || (isSw ? 'Switch' : 'Access point')), isSw ? 'A UniFi switch on this site.' : 'A UniFi Wi-Fi access point on this site.', IX.online(d.online))}
        ${row('Model', E(d.model || '—'))}
        ${row('Address', `<span class="mono">${E(d.ip || '—')}</span>`)}
        ${row('CPU', d.cpu_pct != null ? `${d.cpu_pct}%` : IX.na())}
        ${isSw ? row('Memory', d.mem_pct != null ? `${d.mem_pct}%` : IX.na()) : row('Connected clients', d.num_sta != null ? E(d.num_sta) : IX.na())}
        <button class="btn btn-outline btn-sm" onclick="InfraPages.unifiSubTab='${isSw ? 'switches' : 'aps'}';App.navigate('unifi-monitoring')">See all in UniFi page</button>
      `;
    } else {
      box.innerHTML = `
        ${IX.head('Simulated internet servers', 'The "far side" of the test.')}
        <p style="font-size:12.5px;color:var(--text-secondary);line-height:1.55;">
          The second test port pretends to be the internet: websites, video streaming, cloud apps, DNS and voice calls.
          That way a heavy 10,000-user test goes through your gateway without flooding real internet services.
        </p>
        ${IX.small('Technical: TRex port 1, responder subnet 48.0.0.0/16.')}
      `;
    }
  },

  // =========================================================================
  // 3. SERVER NETWORK PORTS
  // =========================================================================
  async renderNicsPorts() {
    const el = document.getElementById('page-nics-ports');
    const E = IX.esc;
    let hw;
    try {
      hw = await App.api('/api/hardware');
    } catch (e) {
      el.innerHTML = IX.banner('critical', 'Couldn\'t read the server\'s network ports', E(e.message),
        `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderNicsPorts()">Try again</button>`);
      return;
    }
    const ifs = hw.interfaces || [];
    const ta = IX.topoAssessment(hw.topology_assessment);

    // ---- Status first ----
    const mgmt = ifs.find((i) => i.is_management);
    const testPorts = ifs.filter((i) => !i.is_management && !String(i.ifname).startsWith('veth') && i.pci_bus !== 'virtual');
    const testLinked = testPorts.filter((i) => IX.portRole(i).linked);
    let banners = '';
    if (ifs.length) {
      banners += IX.banner('info',
        `${IX.plural(testLinked.length, 'test port')} connected (of ${testPorts.length})${mgmt ? ` · management port ${E(mgmt.ifname)} ${IX.portRole(mgmt).linked ? `up at ${IX.fmtMbps(mgmt.speed_mbps)}` : 'has no link'}` : ''}`,
        'Each port below says what it is for. Only the test ports carry test traffic.');
    }
    banners += IX.cablingBanner(ta, false);
    if (mgmt && Number(mgmt.speed_mbps) === 100 && Number(mgmt.max_supported_mbps || mgmt.max_speed_mbps || 0) >= 10000) {
      banners += IX.banner('warning', 'Management port linked at 100 Mbps',
        `<strong>${E(mgmt.ifname)}</strong> can do 10 Gbps but linked at 100 Mbps — the switch port is likely forced to 100 Mbps; set it to Auto. This only slows the web page and file downloads, not tests.`);
    }

    const rows = ifs.map((i) => {
      const role = IX.portRole(i);
      const up = role.linked;
      const max = i.max_supported_mbps || i.max_speed_mbps;
      return `
      <tr>
        <td><strong>${E(i.ifname)}</strong>${i.description ? IX.small(E(i.description)) : ''}</td>
        <td><span class="badge badge-${role.badge}">${E(role.label)}</span>${IX.small(E(role.hint))}</td>
        <td>${up ? `<strong>${IX.fmtMbps(i.speed_mbps)}</strong>${max ? IX.small(`of ${IX.fmtMbps(max)} max`) : ''}` : IX.muted('No cable / no link')}
          ${i.speed_warning && !i.is_management ? `<div style="font-size:11px;color:#B45309;margin-top:2px;" title="${E(i.speed_warning)}">Slower than this port can do</div>` : ''}</td>
        <td class="mono">${E(i.ipv4 || '—')}</td>
        <td>${up ? `${App.fmtBps(i.live_tx_bps || 0)} / ${App.fmtBps(i.live_rx_bps || 0)}` : IX.muted('—')}</td>
      </tr>`;
    }).join('');

    const techRows = ifs.map((i) => `
      <tr>
        <td><strong>${E(i.ifname)}</strong></td>
        <td class="mono">${E(i.pci_bus || 'virtual')}</td>
        <td>${E(i.driver || '—')}</td>
        <td class="mono">${E(i.mac || '—')}</td>
        <td>${E(i.mtu || '—')}</td>
        <td>${E(i.speed_label || '—')}</td>
        <td>${E(i.operstate || '—')}</td>
        <td style="font-size:11.5px;">${E(i.speed_warning || '')}</td>
      </tr>`).join('');

    const body = ifs.length ? `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Port</th><th>What it's for</th><th>Link speed</th><th>IP address</th><th title="Traffic leaving / arriving on this port right now">Live out / in</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        ${IX.details('Technical details (PCIe address, driver, MAC, MTU)', `
          <div class="table-wrap"><table class="data-table">
            <thead><tr><th>Port</th><th>PCIe bus</th><th>Driver</th><th>MAC address</th><th>MTU</th><th>Reported speed</th><th>State</th><th>Notes</th></tr></thead>
            <tbody>${techRows}</tbody>
          </table></div>`)}`
      : `<div style="padding:22px 6px;text-align:center;">
          <div style="font-weight:700;font-size:13.5px;margin-bottom:4px;">The server didn't report any network ports</div>
          <div class="card-subtitle" style="margin-bottom:12px;">This happens when the app runs somewhere other than the R640 (for example a laptop), or the port scan failed. Try a rescan.</div>
          <button class="btn btn-primary btn-sm" onclick="InfraPages.renderNicsPorts()">Rescan ports</button>
        </div>`;

    el.innerHTML = `
      ${banners}
      <div class="card">
        ${IX.head('Server network ports',
          'The physical network sockets on the back of this server and what each one is for. Use this to check the cabling before a test.',
          `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderNicsPorts()" title="Re-scan PCIe devices and cable links">Rescan</button>`)}
        ${body}
      </div>
    `;
  },

  // =========================================================================
  // 4. TRAFFIC ENGINE (Cisco TRex: stateful ASTF <-> stateless STL + config file)
  // =========================================================================
  async renderTrexEngine() {
    const el = document.getElementById('page-trex-engine');
    const E = IX.esc;
    let hw;
    try {
      hw = await App.api('/api/hardware');
    } catch (e) {
      el.innerHTML = IX.banner('critical', 'Couldn\'t read the traffic engine status', E(e.message),
        `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderTrexEngine()">Try again</button>`);
      return;
    }
    const mode = String(hw.trex_daemon_mode || 'ASTF').toUpperCase();
    const restartBtn = (cls = 'btn-outline') => `<button class="btn ${cls} btn-sm" onclick="InfraPages.regenerateTrexYaml()" title="Re-detects the test ports, rewrites /etc/trex_cfg.yaml and restarts the trex-server service">Detect ports &amp; restart engine</button>`;

    const status = hw.trex_connected
      ? IX.banner('success', `Running in ${IX.modeWords(mode)}`,
        IX.muted(`Ready for tests.${hw.trex_version ? ` Version: ${E(hw.trex_version)}` : ''}`))
      : IX.banner('critical', 'Offline — the traffic engine isn\'t responding',
        'Click <strong>Detect ports &amp; restart engine</strong>. If it stays offline, check the <code>trex-server</code> service on the server (or that this app is running on the R640).',
        restartBtn('btn-primary'));

    const modeBtn = (key, title, desc) => `
      <button class="btn ${mode === key ? 'btn-primary' : 'btn-outline'}" style="flex:1;flex-direction:column;align-items:flex-start;text-align:left;height:auto;padding:12px 14px;white-space:normal;gap:4px;" onclick="InfraPages.switchTrexMode('${key}')" title="Engine flag: --${key.toLowerCase()}">
        <span style="font-weight:700;">${title}${mode === key ? (hw.trex_connected ? ' — active' : ' — selected') : ''}</span>
        <span style="font-size:11.5px;font-weight:500;opacity:.85;line-height:1.4;">${desc}</span>
      </button>`;

    const huge = hw.hugepages || {};
    const hugeRows = Object.keys(huge).map((k) => `<tr><td>${E(k)}</td><td class="mono">${E(huge[k])}</td></tr>`).join('');

    el.innerHTML = `
      ${status}
      <div class="card" style="margin-bottom:14px;">
        ${IX.head('Traffic engine',
          'Chooses how test traffic is made. Starting a test switches this automatically, so you rarely need to change it by hand.',
          `<span class="badge ${hw.trex_connected ? 'badge-success' : 'badge-critical'}" title="${hw.trex_connected ? 'Control connection (ZMQ port 4501) is up' : 'No control connection to TRex'}">${hw.trex_connected ? 'Running' : 'Offline'}</span>`)}
        <div style="display:flex;gap:10px;margin-bottom:10px;">
          ${modeBtn('ASTF', 'Realistic user traffic (stateful)', 'Real TCP/UDP sessions — web, video, calls. Use it to answer "how many users can my gateway handle?"')}
          ${modeBtn('STL', 'Raw speed / frame tests (stateless)', 'Fixed-size packets at a set rate. Use it for maximum throughput and packet-size tests.')}
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
          ${IX.small('Switching mode restarts the engine and stops any test that is running.')}
          ${hw.trex_connected ? restartBtn() : ''}
        </div>

        ${IX.details('Advanced: engine config file (/etc/trex_cfg.yaml)', `
          ${IX.small('Which ports the engine uses and how. Rewritten automatically by "Detect ports & restart engine".')}
          ${hw.trex_cfg_yaml
            ? `<pre class="mono" style="background:#142338;color:#E2E8F0;padding:14px;border-radius:8px;font-size:12px;overflow-x:auto;margin-top:8px;">${E(hw.trex_cfg_yaml)}</pre>`
            : `<div style="font-size:12.5px;margin-top:8px;">No config file found yet. Click <strong>Detect ports &amp; restart engine</strong> to create one.</div>`}
        `)}
        ${IX.details('Advanced: memory reserved for the engine (HugePages)', hugeRows
          ? `${IX.small('The engine reserves this memory up front so it can move packets fast. That\'s why server memory use looks high.')}<table class="data-table" style="margin-top:8px;max-width:520px;"><tbody>${hugeRows}</tbody></table>`
          : `<div style="font-size:12.5px;">Not reported — only available when the app runs on the Linux server.</div>`)}
      </div>
    `;
  },

  async switchTrexMode(mode) {
    App.toast(`Switching the traffic engine to ${IX.modeWords(mode)}…`, 'info');
    try {
      const res = await App.api('/api/config/trex', { method: 'POST', body: JSON.stringify({ daemon_mode: mode }) });
      if (res.status === 'error' || !res.trex_connected) {
        App.toast('The engine didn\'t come back after switching. Try "Detect ports & restart engine".', 'error');
      } else {
        App.toast(`Traffic engine now in ${IX.modeWords(res.trex_daemon_mode)}.`, 'success');
      }
    } catch (e) {
      App.toast(`Couldn't switch mode: ${e.message}`, 'error');
    }
    this.renderTrexEngine();
  },

  async regenerateTrexYaml() {
    App.toast('Detecting test ports and restarting the traffic engine…', 'info');
    try {
      const res = await App.api('/api/config/trex', { method: 'POST', body: JSON.stringify({ mode: 'auto', regenerate_yaml: true, restart_service: true }) });
      const ports = (res.ports || []).join(', ');
      App.toast(res.trex_connected ? `Engine restarted${ports ? ` using ${ports}` : ''}.` : `Config updated${ports ? ` (${ports})` : ''}, but the engine is still offline.`, res.trex_connected ? 'success' : 'error');
    } catch (e) {
      App.toast(`Couldn't restart the engine: ${e.message}`, 'error');
    }
    this.renderTrexEngine();
  },

  // =========================================================================
  // 5. SERVER HEALTH & FIELD DIAGNOSTICS
  // =========================================================================
  healthSummary(f) {
    const s = f.sensors || {};
    const warn = [];
    const hot = [];
    const bits = [];
    const check = (label, v, w, h, advice) => {
      if (v == null || Number.isNaN(Number(v))) return;
      bits.push(`${label} ${App.tempSpan(v, w, h)}`);
      if (v >= h) hot.push(`${label} is ${Math.round(v)} °C — ${advice}`);
      else if (v >= w) warn.push(`${label} is ${Math.round(v)} °C — ${advice}`);
    };
    if (s.available) {
      const pk = (s.cpu_packages || []).map((c) => c.c).filter((c) => c != null);
      const cpuMax = pk.length ? Math.max(...pk) : s.cpu_max_c;
      check(pk.length > 1 ? 'CPUs' : 'CPU', cpuMax, 70, 85, 'check the fans and airflow.');
      check('room air', s.inlet_c, 30, 35, 'keep the server room below about 27 °C.');
      check('exhaust', s.exhaust_c, 50, 60, 'airflow through the server may be blocked.');
      check('drive', s.nvme_c, 60, 75, 'the NVMe drive is running hot.');
      const nicMax = (s.nics || []).map((n) => n.c).filter((c) => c != null);
      if (nicMax.length) check('network cards', Math.max(...nicMax), 80, 95, 'network cards are running hot.');
      const fans = s.fans || [];
      const stopped = fans.filter((x) => Number(x.rpm) === 0);
      if (stopped.length) {
        hot.push(`${IX.plural(stopped.length, 'fan')} reporting 0 RPM (${stopped.map((x) => App.esc(x.name)).join(', ')}).`);
        bits.push('<span class="hot">fan stopped</span>');
      } else if (s.fan_avg_rpm != null) {
        bits.push('fans normal');
      }
    }
    if (f.storage?.percent != null && f.storage.percent >= 90) warn.push(`Disk is ${f.storage.percent}% full — delete old reports or captures.`);
    const level = hot.length ? 'critical' : warn.length ? 'warning' : 'success';
    const word = hot.length ? 'Needs attention' : warn.length ? 'Running warm' : (s.available ? 'Healthy' : 'Load looks fine');
    return { level, word, bits, issues: [...hot, ...warn], sensorsOk: !!s.available };
  },

  renderServerHealth() {
    const el = document.getElementById('page-server-health');
    const E = IX.esc;
    const f = App.latest || {};
    const hasFrame = Object.keys(f).length > 0;
    const nCores = (f.per_cpu_pct || []).length;
    const cores = (f.per_cpu_pct || []).map((v, idx) => `
      <div style="background:#F8FAFC;border:1px solid var(--border-color);border-radius:6px;padding:7px;text-align:center;">
        <div style="font-size:10.5px;color:var(--text-secondary);">CPU ${idx}</div>
        <div style="font-weight:700;font-size:13px;color:${v > 80 ? '#DC2626' : '#17243A'};">${Number(v).toFixed(0)}%</div>
      </div>
    `).join('');

    // ---- Status first ----
    let summary;
    if (!hasFrame) {
      summary = IX.banner('info', 'Waiting for the first reading from the server…', 'Health data updates every few seconds. If this doesn\'t change, refresh the page.',
        `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderServerHealth()">Check again</button>`);
    } else {
      const h = this.healthSummary(f);
      const load = `CPU ${Number(f.cpu_pct || 0).toFixed(0)}% busy · memory ${Number(f.ram_pct || 0).toFixed(0)}% used${f.storage?.percent != null ? ` · disk ${f.storage.percent}% full` : ''}`;
      const headline = h.bits.length ? `${h.word} — ${h.bits.join(', ')}` : h.word;
      summary = IX.banner(h.level, headline,
        `${load}${h.issues.length ? `<ul style="margin:6px 0 0 18px;padding:0;">${h.issues.map((x) => `<li>${x}</li>`).join('')}</ul>` : ''}${h.sensorsOk ? '' : '<div style="font-size:11.5px;margin-top:3px;">Temperatures aren\'t available yet (sensors refresh every 15 seconds; they need the app to be running on the server).</div>'}`,
        `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderServerHealth()">Refresh</button>`);
    }

    const tempCard = (() => {
      const s = f.sensors || {};
      const header = IX.head('Temperatures, fans &amp; power',
        'Read from the CPU sensors and the server\'s iDRAC. High room-air temperature is the most common cause of a hot server.',
        s.updated_at ? `<span class="card-subtitle">Updated ${new Date(s.updated_at * 1000).toLocaleTimeString()}</span>` : '');
      if (!s.available) {
        return `<div class="card" style="margin-bottom:16px;">${header}
          <div style="font-size:12.5px;color:var(--text-secondary);">No sensor readings yet. They refresh every 15 seconds and are only available when the app runs on the R640.</div></div>`;
      }
      const tile = (label, val, sub) => `<div class="sensor-tile"><div class="card-subtitle">${label}</div><div class="kpi-value" style="font-size:22px;">${val}</div><div class="kpi-foot">${sub || ''}</div></div>`;
      const tiles = [
        ...(s.cpu_packages || []).map((c) => tile(`${E(c.label)} temperature`, App.tempSpan(c.c, 70, 85), c.high ? `High ${c.high}°C · critical ${c.critical}°C` : '')),
        s.inlet_c != null ? tile('Room air (inlet)', App.tempSpan(s.inlet_c, 30, 35), 'Keep below about 27°C') : '',
        s.exhaust_c != null ? tile('Exhaust air', App.tempSpan(s.exhaust_c, 50, 60), 'Air leaving the server') : '',
        s.nvme_c != null ? tile('NVMe drive', App.tempSpan(s.nvme_c, 60, 75), 'System drive') : '',
        ...(s.nics || []).map((n) => tile(`Network card ${E(n.name)}`, App.tempSpan(n.c, 80, 95), '')),
        s.chipset_c != null ? tile('Chipset', App.tempSpan(s.chipset_c, 70, 85), 'Motherboard (PCH)') : '',
        s.fan_avg_rpm != null ? tile('Fans (average)', `${s.fan_avg_rpm.toLocaleString()} <span class="kpi-unit">RPM</span>`, (s.fans || []).map((x) => `${E(x.name)}: ${Number(x.rpm).toLocaleString()}`).join(' · ')) : '',
        s.power_w != null ? tile('Power draw', `${s.power_w} <span class="kpi-unit">W</span>`, 'Whole server, from iDRAC') : '',
      ].filter(Boolean).join('');
      return `<div class="card" style="margin-bottom:16px;">${header}<div class="sensor-grid">${tiles || '<div style="font-size:12.5px;color:var(--text-secondary);">Sensors answered but reported no values.</div>'}</div></div>`;
    })();

    el.innerHTML = `
      ${summary}

      <div class="grid-3" style="margin-bottom:16px;">
        <div class="card"><div class="card-subtitle">CPU load</div><div class="kpi-value">${hasFrame ? Number(f.cpu_pct || 0).toFixed(1) + '%' : '—'}</div><div class="kpi-foot">${nCores ? `Average across ${nCores} threads. High during big tests is normal.` : 'Waiting for data'}</div></div>
        <div class="card"><div class="card-subtitle">Memory</div><div class="kpi-value">${f.ram_used_gb ?? '—'} / ${f.ram_total_gb ? Math.round(f.ram_total_gb) : '—'} <span class="kpi-unit">GB</span></div><div class="kpi-foot">${hasFrame ? `${Number(f.ram_pct || 0).toFixed(0)}% used, including memory reserved for the traffic engine` : 'Waiting for data'}</div></div>
        <div class="card"><div class="card-subtitle">Disk space</div><div class="kpi-value">${f.storage?.used_gb ?? '—'} / ${f.storage?.total_gb ?? '—'} <span class="kpi-unit">GB</span></div><div class="kpi-foot">${f.storage?.percent != null ? `${f.storage.percent}% full (reports, captures, database)` : 'Not reported yet'}</div></div>
      </div>

      ${tempCard}

      <div class="card" style="margin-bottom:16px;padding:12px 18px;">
        <details ${this.coresOpen ? 'open' : ''} ontoggle="InfraPages.coresOpen=this.open">
          <summary style="cursor:pointer;font-size:13px;font-weight:700;user-select:none;">Per-core CPU load${nCores ? ` (${nCores} threads)` : ''}</summary>
          <div class="card-subtitle" style="margin:6px 0 10px;">One box per CPU thread. A few busy cores during a test is normal — the engine pins work to specific cores.</div>
          ${cores ? `<div style="display:grid;grid-template-columns:repeat(8, minmax(0, 1fr));gap:8px;">${cores}</div>` : '<div style="font-size:12.5px;color:var(--text-secondary);">No per-core data yet.</div>'}
        </details>
      </div>

      <div class="grid-2">
        <div class="card">
          ${IX.head('Network checks', 'Quick checks from this server: does a full-size packet get through (MTU), and how fast do the gateway and DNS answer?')}
          <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">
            <input type="text" class="form-control" id="diagTargetIp" value="10.20.30.1" placeholder="Address to test, e.g. 10.20.30.1" style="flex:1;min-width:160px;" title="Address used by the packet-size test" />
            <button class="btn btn-outline" onclick="InfraPages.runMtuCheck()" title="Path MTU probe with the don't-fragment bit set">Test packet size</button>
            <button class="btn btn-outline" onclick="InfraPages.runDnsCheck()">Test gateway &amp; DNS speed</button>
          </div>
          <div id="diagSummary" style="font-size:12.5px;margin-bottom:8px;color:var(--text-secondary);">Pick a check above. Results appear here.</div>
          <pre id="diagOutputBox" class="mono" style="background:#F8FAFC;padding:10px;border-radius:7px;border:1px solid var(--border-color);font-size:11.5px;min-height:60px;max-height:260px;overflow:auto;">No raw result yet.</pre>
        </div>

        <div class="card">
          ${IX.head('Packet capture &amp; updates', 'Grab a short packet sample to open in Wireshark, or pull the latest version of this app from GitHub.')}
          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <a class="btn btn-outline" href="/api/diagnostics/pcap?interface=enp216s0&count=150" target="_blank" title="150 packets from the management port enp216s0, saved as a .pcap file">Download packet capture</a>
            <button class="btn btn-outline" onclick="InfraPages.triggerGitPull()">Update app from GitHub</button>
          </div>
          ${IX.small('The capture records 150 packets on the management port (enp216s0).')}
        </div>
      </div>
    `;
  },

  async runMtuCheck() {
    const out = document.getElementById('diagOutputBox');
    const sum = document.getElementById('diagSummary');
    const target = document.getElementById('diagTargetIp').value.trim();
    if (!target) { App.toast('Enter an address to test first.', 'error'); return; }
    sum.textContent = `Testing the largest packet that reaches ${target}…`;
    out.textContent = '';
    try {
      const res = await App.api('/api/diagnostics/mtu', { method: 'POST', body: JSON.stringify({ target }) });
      if (res.status === 'error') sum.textContent = `Couldn't run the test: ${res.message || 'unknown error'}`;
      else if (res.discovered_mtu) {
        sum.textContent = `Largest packet that got through: ${res.discovered_mtu} bytes. `
          + (res.standard_1500_ok ? 'Normal 1500-byte packets work.' : 'Normal 1500-byte packets do NOT get through — check MTU settings on the path.')
          + (res.jumbo_supported ? ' Jumbo frames work too.' : '');
      } else sum.textContent = `No reply from ${target}. It may be unreachable, or blocking ping.`;
      out.textContent = JSON.stringify(res, null, 2);
    } catch (e) {
      sum.textContent = `Couldn't run the test: ${e.message}`;
    }
  },

  async runDnsCheck() {
    const out = document.getElementById('diagOutputBox');
    const sum = document.getElementById('diagSummary');
    sum.textContent = 'Timing the gateway and a DNS lookup…';
    out.textContent = '';
    try {
      const res = await App.api('/api/diagnostics/dns-gateway', { method: 'POST', body: JSON.stringify({ dns_server: '1.1.1.1', domain: 'cloudflare.com' }) });
      const gwPart = res.gateway_rtt_ms != null ? `Gateway ${res.gateway_ip || ''} answered in ${res.gateway_rtt_ms} ms.` : 'The gateway did not answer.';
      const dnsPart = res.dns_avg_ms != null ? ` Looking up ${res.domain_tested || 'a website'} took ${res.dns_avg_ms} ms on average.` : ' The DNS lookup failed.';
      sum.textContent = gwPart + dnsPart;
      out.textContent = JSON.stringify(res, null, 2);
    } catch (e) {
      sum.textContent = `Couldn't run the test: ${e.message}`;
    }
  },

  async triggerGitPull() {
    try {
      const res = await App.api('/api/system/git-pull', { method: 'POST', body: '{}' });
      App.toast(res.message || 'Update started.', 'info');
    } catch (e) {
      App.toast(`Couldn't start the update: ${e.message}`, 'error');
    }
  },

  // =========================================================================
  // 6. SETTINGS
  // =========================================================================
  async renderConfiguration() {
    const el = document.getElementById('page-configuration');
    const E = IX.esc;
    let d;
    try {
      d = await App.api('/api/config/settings');
    } catch (e) {
      el.innerHTML = IX.banner('critical', 'Couldn\'t load settings', E(e.message), `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderConfiguration()">Try again</button>`);
      return;
    }
    const s = d.settings || {};
    const hint = (t) => `<div style="font-size:11.5px;color:var(--text-secondary);margin-top:4px;">${t}</div>`;

    el.innerHTML = `
      <div class="card" style="max-width:720px;">
        ${IX.head('Settings', 'Names and defaults used across the app and in exported reports.')}
        <div class="form-group">
          <label class="form-label" for="cfgAppName">App name</label>
          <input type="text" class="form-control" id="cfgAppName" value="${E(s.appliance_name || 'Cisco TRex Network Test Studio')}" />
          ${hint('Shown on reports.')}
        </div>
        <div class="form-group">
          <label class="form-label" for="cfgDutName">Device being tested</label>
          <input type="text" class="form-control" id="cfgDutName" value="${E(s.dut_default_name || 'UniFi Enterprise Fortress Gateway (EFG)')}" />
          ${hint('Default name of the gateway or firewall you test. Each test can override it.')}
        </div>
        <div class="grid-2" style="gap:12px;">
          <div class="form-group">
            <label class="form-label" for="cfgLinkCap">Link speed for percentages (Mbps)</label>
            <input type="number" class="form-control" id="cfgLinkCap" value="${E(s.default_link_capacity_mbps || 10000)}" />
            ${hint('Results are shown as a % of this. 1000 = 1 Gbps, 10000 = 10 Gbps.')}
          </div>
          <div class="form-group">
            <label class="form-label" for="cfgOpName">Your name</label>
            <input type="text" class="form-control" id="cfgOpName" value="${E(s.operator_name || 'Stephan Van Vuuren')}" />
            ${hint('Printed on reports as the person who ran the test.')}
          </div>
        </div>
        ${hint('The management port is always protected — tests never use it.')}
        <button class="btn btn-primary" style="margin-top:12px;" onclick="InfraPages.saveConfigSettings()">Save settings</button>
      </div>
    `;
  },

  async saveConfigSettings() {
    try {
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
      App.toast('Settings saved.', 'success');
    } catch (e) {
      App.toast(`Couldn't save settings: ${e.message}`, 'error');
    }
  },

  // =========================================================================
  // 7. INTEGRATIONS (UniFi + SNMP)
  // =========================================================================
  async renderApiIntegrations() {
    const el = document.getElementById('page-api-integrations');
    const E = IX.esc;
    let uRes, sRes;
    try {
      [uRes, sRes] = await Promise.all([App.api('/api/unifi/config'), App.api('/api/snmp/config')]);
    } catch (e) {
      el.innerHTML = IX.banner('critical', 'Couldn\'t load integrations', E(e.message), `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderApiIntegrations()">Try again</button>`);
      return;
    }
    const uc = uRes.config || {};
    const sc = sRes.config || {};
    const uOk = !!uRes.snapshot?.connected;
    const sOk = !!sRes.snapshot?.connected;
    const usum = uRes.snapshot?.summary || {};
    const hint = (t) => `<div style="font-size:11.5px;color:var(--text-secondary);margin-top:4px;line-height:1.4;">${t}</div>`;
    const stored = (has) => (has ? ' <span class="badge badge-neutral" title="Saved encrypted on the server. Leave the dots to keep it.">saved</span>' : '');

    const status = uOk
      ? IX.banner('success', `UniFi connected${usum.gw_name ? ` to ${E(usum.gw_name)}` : ''} · SNMP ${sOk ? 'connected' : 'off (optional)'}`,
        IX.muted('Keys and passwords are stored encrypted on this server and never sent back to your browser. The app only reads from your devices — it never changes them.'))
      : IX.banner('warning', `UniFi not connected yet · SNMP ${sOk ? 'connected' : 'off (optional)'}`,
        'Fill in the two fields under <strong>UniFi</strong> below and click <strong>Save &amp; test</strong>. Keys and passwords are stored encrypted on this server, never sent back to your browser, and only used to read data.');

    el.innerHTML = `
      ${status}

      <div class="grid-2">
        <div class="card">
          ${IX.head('UniFi', 'Lets this app read your gateway, switches and Wi-Fi stats, so you can see how the gateway copes during a test.',
            `<span class="badge ${uOk ? 'badge-success' : 'badge-neutral'}">${E(uRes.snapshot?.status || 'Not set up')}</span>`)}

          <div class="form-group">
            <label class="form-label" for="ufHost">Gateway or controller address</label>
            <input type="text" class="form-control" id="ufHost" value="${E(uc.host || '10.20.30.1')}" placeholder="e.g. 10.20.30.1" />
          </div>
          <div class="form-group">
            <label class="form-label" for="ufApiKey">API key${stored(uc.has_api_key)}</label>
            <input type="password" class="form-control" id="ufApiKey" value="${uc.has_api_key ? '••••••••••••' : ''}" placeholder="Paste your UniFi API key" autocomplete="off" />
            ${hint('Get one in UniFi Network: <strong>Settings &rarr; Control Plane &rarr; Integrations &rarr; Create API key</strong>. A read-only key is enough.')}
          </div>

          <label style="display:flex;align-items:center;gap:8px;margin:8px 0 4px;font-size:12.5px;font-weight:600;">
            <input type="checkbox" id="ufEnabled" ${uc.enabled ? 'checked' : ''} />
            <span>Keep reading UniFi stats (every ${E(uc.poll_interval_sec || 5)} seconds)</span>
          </label>

          ${IX.details('Advanced: port, sign-in method, site, cloud key', `
            <div class="grid-2" style="gap:10px;">
              <div class="form-group">
                <label class="form-label" for="ufPort">HTTPS port</label>
                <input type="number" class="form-control" id="ufPort" value="${E(uc.port || 443)}" />
                ${hint('Almost always 443.')}
              </div>
              <div class="form-group">
                <label class="form-label" for="ufSite">Site name</label>
                <input type="text" class="form-control" id="ufSite" value="${E(uc.site_name || 'default')}" />
                ${hint('Leave as "default" unless you have several sites.')}
              </div>
            </div>
            <div class="form-group">
              <label class="form-label" for="ufAuthMode">Sign-in method</label>
              <select class="form-control" id="ufAuthMode">
                <option value="api_key" ${uc.auth_mode === 'api_key' || !uc.auth_mode ? 'selected' : ''}>API key (recommended)</option>
                <option value="local_account" ${uc.auth_mode === 'local_account' ? 'selected' : ''}>Local read-only admin account (username + password)</option>
                <option value="site_manager" ${uc.auth_mode === 'site_manager' ? 'selected' : ''}>Ubiquiti cloud (Site Manager)</option>
              </select>
            </div>
            <div class="grid-2" style="gap:10px;">
              <div class="form-group">
                <label class="form-label" for="ufUser">Username</label>
                <input type="text" class="form-control" id="ufUser" value="${E(uc.username || '')}" autocomplete="off" />
                ${hint('Only for the local account method.')}
              </div>
              <div class="form-group">
                <label class="form-label" for="ufPass">Password${stored(uc.has_password)}</label>
                <input type="password" class="form-control" id="ufPass" value="${uc.has_password ? '••••••••••••' : ''}" autocomplete="new-password" />
              </div>
            </div>
            <div class="form-group">
              <label class="form-label" for="ufSmKey">Site Manager cloud key (optional)${stored(uc.has_site_manager_key)}</label>
              <input type="password" class="form-control" id="ufSmKey" value="${uc.has_site_manager_key ? '••••••••••••' : ''}" placeholder="Key from unifi.ui.com &rarr; API" autocomplete="off" />
              ${hint('Only for the Ubiquiti cloud method (api.ui.com).')}
            </div>
          `)}

          <button class="btn btn-primary" style="width:100%;margin-top:14px;" onclick="InfraPages.saveAndTestUniFi()">Save &amp; test UniFi connection</button>
          <div id="ufTestResult" style="margin-top:10px;font-size:12.5px;"></div>
        </div>

        <div class="card">
          ${IX.head('SNMP (optional)', 'Only needed if you want exact per-port counters — traffic, errors and dropped packets — read straight from the gateway or a switch. The UniFi connection covers most needs.',
            `<span class="badge ${sOk ? 'badge-success' : 'badge-neutral'}">${E(sRes.snapshot?.status || 'Off')}</span>`)}
          <div class="grid-2" style="gap:10px;">
            <div class="form-group">
              <label class="form-label" for="snHost">Device address</label>
              <input type="text" class="form-control" id="snHost" value="${E(sc.host || '10.20.30.1')}" placeholder="Gateway or switch IP" />
            </div>
            <div class="form-group">
              <label class="form-label" for="snVer">SNMP version</label>
              <select class="form-control" id="snVer">
                <option value="v3" ${sc.version === 'v3' ? 'selected' : ''}>v3 (recommended)</option>
                <option value="v2c" ${sc.version === 'v2c' ? 'selected' : ''}>v2c (community string)</option>
              </select>
            </div>
          </div>
          ${hint('Turn SNMP on in UniFi under Settings &rarr; System (or the device\'s own settings), then copy the same details here.')}

          <div class="card-subtitle" style="margin:12px 0 6px;font-weight:700;">If you chose v2c</div>
          <div class="form-group">
            <label class="form-label" for="snComm">Community string${stored(sc.has_community)}</label>
            <input type="password" class="form-control" id="snComm" value="${sc.has_community ? '••••••••' : ''}" placeholder="e.g. public" autocomplete="off" />
          </div>

          <div class="card-subtitle" style="margin:12px 0 6px;font-weight:700;">If you chose v3</div>
          <div class="grid-3" style="gap:10px;">
            <div class="form-group">
              <label class="form-label" for="snUser">Username</label>
              <input type="text" class="form-control" id="snUser" value="${E(sc.username || '')}" autocomplete="off" />
            </div>
            <div class="form-group">
              <label class="form-label" for="snAuthPass" title="Authentication protocol: ${E(sc.auth_protocol || 'SHA')}">Auth password${stored(sc.has_auth_pass)}</label>
              <input type="password" class="form-control" id="snAuthPass" value="${sc.has_auth_pass ? '••••••••' : ''}" placeholder="${E(sc.auth_protocol || 'SHA')}" autocomplete="new-password" />
            </div>
            <div class="form-group">
              <label class="form-label" for="snPrivPass" title="Privacy (encryption) protocol: ${E(sc.priv_protocol || 'AES')}">Encryption password${stored(sc.has_priv_pass)}</label>
              <input type="password" class="form-control" id="snPrivPass" value="${sc.has_priv_pass ? '••••••••' : ''}" placeholder="${E(sc.priv_protocol || 'AES')}" autocomplete="new-password" />
            </div>
          </div>

          <label style="display:flex;align-items:center;gap:8px;margin:8px 0 12px;font-size:12.5px;font-weight:600;">
            <input type="checkbox" id="snEnabled" ${sc.enabled ? 'checked' : ''} />
            <span>Keep reading SNMP port counters</span>
          </label>

          <button class="btn btn-primary btn-block" onclick="InfraPages.saveAndTestSnmp()">Save &amp; test SNMP</button>
          <div id="snTestResult" style="margin-top:10px;font-size:12.5px;"></div>
        </div>
      </div>
    `;
  },

  async saveAndTestUniFi() {
    const out = document.getElementById('ufTestResult');
    const E = IX.esc;
    const host = document.getElementById('ufHost').value.trim();
    const authMode = document.getElementById('ufAuthMode').value;
    const apiKey = document.getElementById('ufApiKey').value;
    const fail = (msg) => {
      App.toast(msg, 'error');
      out.innerHTML = `<div class="alert-banner critical" style="margin-top:8px;">${E(msg)}</div>`;
    };
    if (!host) return fail('Enter your gateway or controller address first (for example 10.20.30.1).');
    if (authMode === 'api_key' && !apiKey) return fail('Paste a UniFi API key first (UniFi Network → Settings → Control Plane → Integrations).');
    if (authMode === 'local_account' && !document.getElementById('ufUser').value.trim()) return fail('Enter the local account username (under Advanced).');
    if (authMode === 'site_manager' && !document.getElementById('ufSmKey').value) return fail('Paste a Site Manager cloud key (under Advanced).');

    out.innerHTML = `<span style="color:var(--text-secondary);">Connecting to ${E(host)}…</span>`;
    try {
      const res = await App.api('/api/unifi/test', {
        method: 'POST',
        body: JSON.stringify({
          enabled: document.getElementById('ufEnabled').checked,
          host,
          port: parseInt(document.getElementById('ufPort').value, 10) || 443,
          auth_mode: authMode,
          site_name: document.getElementById('ufSite').value.trim() || 'default',
          api_key: apiKey,
          username: document.getElementById('ufUser').value.trim(),
          password: document.getElementById('ufPass').value,
          site_manager_key: document.getElementById('ufSmKey').value,
        }),
      });
      if (res.connected) {
        const sm = res.summary || {};
        const found = [sm.gw_name ? E(sm.gw_name) : null, sm.switches_total != null ? IX.plural(sm.switches_total, 'switch', 'switches') : null, sm.aps_total != null ? IX.plural(sm.aps_total, 'access point') : null].filter(Boolean).join(', ');
        out.innerHTML = `<div class="alert-banner success" style="margin-top:8px;"><div><strong>Connected.</strong>${found ? ` Found ${found}.` : ''}${IX.small(`${E(res.api_mode_detected || '')}${res.controller_version ? ` · version ${E(res.controller_version)}` : ''}`)}</div>
          <button class="btn btn-outline btn-sm" onclick="App.navigate('unifi-monitoring')">View UniFi</button></div>`;
        App.toast('UniFi connected.', 'success');
      } else {
        out.innerHTML = `<div class="alert-banner critical" style="margin-top:8px;"><div><strong>Couldn't connect.</strong> ${E(res.error || res.status || 'No answer')}
          ${IX.small('Check the address is reachable from this server, the key is correct and not expired, and the port (Advanced) is right.')}</div></div>`;
        App.toast('UniFi connection failed.', 'error');
      }
    } catch (e) {
      out.innerHTML = `<div class="alert-banner critical">${E(e.message)}</div>`;
      App.toast(`UniFi test failed: ${e.message}`, 'error');
    }
  },

  async saveAndTestSnmp() {
    const out = document.getElementById('snTestResult');
    const E = IX.esc;
    const host = document.getElementById('snHost').value.trim();
    if (!host) {
      App.toast('Enter the device address first.', 'error');
      out.innerHTML = `<div class="alert-banner critical" style="margin-top:8px;">Enter the device address first.</div>`;
      return;
    }
    out.innerHTML = `<span style="color:var(--text-secondary);">Asking ${E(host)} for its name and ports…</span>`;
    try {
      const res = await App.api('/api/snmp/test', {
        method: 'POST',
        body: JSON.stringify({
          enabled: document.getElementById('snEnabled').checked,
          host,
          version: document.getElementById('snVer').value,
          community: document.getElementById('snComm').value,
          username: document.getElementById('snUser').value.trim(),
          auth_pass: document.getElementById('snAuthPass').value,
          priv_pass: document.getElementById('snPrivPass').value,
        }),
      });
      if (res.connected) {
        out.innerHTML = `<div class="alert-banner success" style="margin-top:8px;"><strong>Connected to ${E(res.sys_name || host)}</strong> — ${IX.plural(res.interface_count || 0, 'port')} found.</div>`;
        App.toast('SNMP connected.', 'success');
      } else {
        out.innerHTML = `<div class="alert-banner critical" style="margin-top:8px;"><div><strong>No SNMP answer.</strong> ${E(res.error || res.status || '')}
          ${IX.small('Check SNMP is turned on for the device, the version matches, and the community string or v3 passwords are correct.')}</div></div>`;
        App.toast('SNMP test failed.', 'error');
      }
    } catch (e) {
      out.innerHTML = `<div class="alert-banner critical">${E(e.message)}</div>`;
      App.toast(`SNMP test failed: ${e.message}`, 'error');
    }
  },

  // =========================================================================
  // 8. USERS
  // =========================================================================
  async renderUserAccess() {
    const el = document.getElementById('page-user-access');
    const E = IX.esc;
    let d;
    try {
      d = await App.api('/api/admin/users');
    } catch (e) {
      el.innerHTML = IX.banner('critical', 'Couldn\'t load users', E(e.message), `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderUserAccess()">Try again</button>`);
      return;
    }
    const users = d.users || [];
    const rows = users.map((u) => `
      <tr>
        <td><strong>${E(u.display_name)}</strong></td>
        <td class="mono">${E(u.username)}</td>
        <td><span class="badge badge-info">${E(u.role)}</span></td>
        <td>${E(u.email || '—')}</td>
        <td>${u.id === 1 ? '<span style="color:var(--text-secondary);font-size:12px;">Owner</span>' : `<button class="btn btn-outline btn-sm" onclick="InfraPages.deleteUser(${Number(u.id)})">Remove</button>`}</td>
      </tr>
    `).join('');

    el.innerHTML = `
      ${IX.banner('info', 'One password protects this app',
        'Everyone signs in with the admin password below. The names under <strong>People</strong> are just labels for who ran each test — they appear on reports and in the activity log, and don\'t get their own login.')}

      <div class="card" style="margin-bottom:14px;max-width:520px;">
        ${IX.head('Admin password', 'The password used to sign in to this app.')}
        <div class="form-group"><label class="form-label" for="uaPwCur">Current password</label><input type="password" class="form-control" id="uaPwCur" autocomplete="current-password" /></div>
        <div class="form-group"><label class="form-label" for="uaPwNew">New password (at least 8 characters)</label><input type="password" class="form-control" id="uaPwNew" autocomplete="new-password" /></div>
        <div class="form-group"><label class="form-label" for="uaPwConf">Type the new password again</label><input type="password" class="form-control" id="uaPwConf" autocomplete="new-password" /></div>
        <div id="uaPwMsg" style="font-size:12.5px;margin-bottom:10px;display:none;"></div>
        <button class="btn btn-primary" id="uaPwBtn" onclick="InfraPages.changeAdminPassword()">Change password</button>
        <div style="font-size:11.5px;color:var(--text-secondary);margin-top:8px;">Changing it signs out every other browser.</div>
      </div>

      <div class="grid-2">
        <div class="card">
          ${IX.head('Add a person', 'Add someone who runs tests, so reports show their name.')}
          <div class="form-group"><label class="form-label" for="uaDisp">Name</label><input type="text" class="form-control" id="uaDisp" placeholder="e.g. Jane Smith" /></div>
          <div class="form-group"><label class="form-label" for="uaUser">Short name</label><input type="text" class="form-control" id="uaUser" placeholder="e.g. jsmith" /></div>
          <div class="form-group"><label class="form-label" for="uaRole">Role</label><select class="form-control" id="uaRole"><option>Lab Administrator</option><option>Senior Network Engineer</option><option>Read-Only Observer</option></select></div>
          <button class="btn btn-primary" onclick="InfraPages.addUser()">Add person</button>
        </div>
        <div class="card">
          ${IX.head(`People (${users.length})`, 'Names available when you start a test.')}
          ${users.length
            ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Name</th><th>Short name</th><th>Role</th><th>Email</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
            : `<div style="font-size:12.5px;color:var(--text-secondary);">Nobody added yet. Use <strong>Add a person</strong> to add the first one.</div>`}
        </div>
      </div>
    `;
  },

  async changeAdminPassword() {
    const cur = document.getElementById('uaPwCur').value;
    const nw = document.getElementById('uaPwNew').value;
    const conf = document.getElementById('uaPwConf').value;
    const msg = document.getElementById('uaPwMsg');
    const btn = document.getElementById('uaPwBtn');
    const show = (text, ok) => {
      msg.style.display = 'block';
      msg.style.color = ok ? 'var(--success)' : 'var(--critical)';
      msg.textContent = text;
    };
    if (!cur) return show('Enter your current password.', false);
    if (nw.length < 8) return show('New password must be at least 8 characters.', false);
    if (nw !== conf) return show('New passwords do not match.', false);
    btn.disabled = true;
    try {
      await App.api('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: cur, new_password: nw }),
      });
      ['uaPwCur', 'uaPwNew', 'uaPwConf'].forEach((id) => { document.getElementById(id).value = ''; });
      show('Password changed. Other sessions have been signed out.', true);
      App.toast('Admin password changed', 'success');
    } catch (e) {
      show(e.message || 'Could not change password.', false);
    } finally {
      btn.disabled = false;
    }
  },

  async addUser() {
    const display = document.getElementById('uaDisp').value.trim();
    const username = document.getElementById('uaUser').value.trim();
    if (!display || !username) { App.toast('Enter a name and a short name.', 'error'); return; }
    try {
      await App.api('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({ display_name: display, username, role: document.getElementById('uaRole').value }),
      });
      App.toast(`Added ${display}.`, 'success');
    } catch (e) {
      App.toast(`Couldn't add: ${e.message}`, 'error');
    }
    this.renderUserAccess();
  },

  async deleteUser(id) {
    try {
      await App.api(`/api/admin/users/${id}`, { method: 'DELETE' });
    } catch (e) {
      App.toast(`Couldn't remove: ${e.message}`, 'error');
    }
    this.renderUserAccess();
  },

  // =========================================================================
  // 9. ACTIVITY LOG
  // =========================================================================
  async renderAuditLogs() {
    const el = document.getElementById('page-audit-logs');
    const E = IX.esc;
    let d;
    try {
      d = await App.api('/api/admin/audit-logs?limit=200');
    } catch (e) {
      el.innerHTML = IX.banner('critical', 'Couldn\'t load the activity log', E(e.message), `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderAuditLogs()">Try again</button>`);
      return;
    }
    const logs = d.logs || [];
    const rows = logs.map((l) => `
      <tr>
        <td class="mono" style="white-space:nowrap;">${new Date(l.ts * 1000).toLocaleString()}</td>
        <td><strong>${E(l.actor)}</strong></td>
        <td><span class="badge badge-neutral">${E(l.category)}</span></td>
        <td><strong>${E(l.action)}</strong></td>
        <td>${E(l.target || '—')}</td>
        <td style="color:var(--text-secondary);font-size:12px;">${E(l.details || '')}</td>
      </tr>
    `).join('');

    el.innerHTML = `
      <div class="card">
        ${IX.head('Activity log',
          `Who did what, and when: tests started and stopped, settings changed, engine restarts. Entries can't be edited or deleted. Showing the latest ${logs.length ? Math.min(logs.length, 200) : 200}.`,
          `<button class="btn btn-outline btn-sm" onclick="InfraPages.renderAuditLogs()">Refresh</button>`)}
        ${logs.length ? `<div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>When</th><th>Who</th><th>Area</th><th>What happened</th><th>On</th><th>Details</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<div style="padding:22px 6px;text-align:center;">
          <div style="font-weight:700;font-size:13.5px;margin-bottom:4px;">Nothing recorded yet</div>
          <div class="card-subtitle">Starting a test, changing a setting or restarting the engine adds an entry here.</div>
        </div>`}
      </div>
    `;
  },
};

window.InfraPages = InfraPages;
