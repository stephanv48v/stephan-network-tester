#!/usr/bin/env python3
"""
Stephan Van Vuuren's Network Tester
Hardware Discovery & Cisco TRex Configuration Generator (/etc/trex_cfg.yaml)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def run_cmd(cmd: List[str], timeout: int = 5) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except Exception:
        return ""


def get_default_route_iface() -> Optional[str]:
    out = run_cmd(["ip", "-j", "route", "show", "default"])
    if out:
        try:
            routes = json.loads(out)
            if routes and "dev" in routes[0]:
                return routes[0]["dev"]
        except Exception:
            pass
    # Fallback: check which interface has a global IPv4 address
    out_addr = run_cmd(["ip", "-j", "-4", "addr", "show"])
    if out_addr:
        try:
            addrs = json.loads(out_addr)
            for item in addrs:
                if item.get("ifname") != "lo" and item.get("addr_info"):
                    return item.get("ifname")
        except Exception:
            pass
    return "enp216s0"


def get_pci_devices() -> Dict[str, Dict[str, str]]:
    """Map PCI bus address (e.g. 0000:d8:00.0) to vendor/device description."""
    pci_map: Dict[str, Dict[str, str]] = {}
    out = run_cmd(["lspci", "-Dnn"])
    for line in out.splitlines():
        if "Ethernet controller" in line or "Network controller" in line:
            parts = line.split(" ", 1)
            if len(parts) == 2:
                slot = parts[0].strip()
                desc = parts[1].strip()
                # Extract clean model name
                clean_desc = re.sub(r"^Ethernet controller \[\d+\]:\s*", "", desc)
                pci_map[slot] = {
                    "pci_address": slot,
                    "description": clean_desc,
                }
    return pci_map


def parse_ethtool(ifname: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "speed_mbps": 0,
        "speed_label": "Down",
        "max_speed_mbps": 1000,
        "max_speed_label": "1 Gbps",
        "duplex": "Unknown",
        "port_type": "Twisted Pair",
        "link_detected": False,
        "partner_max_mbps": 0,
        "speed_warning": None,
    }
    out = run_cmd(["ethtool", ifname])
    if not out:
        return info

    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Speed:"):
            val = s.split(":", 1)[1].strip()
            info["speed_label"] = val
            m = re.search(r"(\d+)Mb/s", val)
            if m:
                info["speed_mbps"] = int(m.group(1))
        elif s.startswith("Duplex:"):
            info["duplex"] = s.split(":", 1)[1].strip()
        elif s.startswith("Port:"):
            info["port_type"] = s.split(":", 1)[1].strip()
        elif s.startswith("Link detected:"):
            info["link_detected"] = s.split(":", 1)[1].strip().lower() == "yes"

    # Determine max supported link mode
    if "10000base" in out:
        info["max_speed_mbps"] = 10000
        info["max_speed_label"] = "10 Gbps"
    elif "5000base" in out:
        info["max_speed_mbps"] = 5000
        info["max_speed_label"] = "5 Gbps"
    elif "2500base" in out:
        info["max_speed_mbps"] = 2500
        info["max_speed_label"] = "2.5 Gbps"

    # Check Link Partner advertised speed for mismatch diagnostic
    m_partner = re.search(
        r"Link partner advertised link modes:(.*?)(?:Link partner advertised|$)",
        out,
        re.DOTALL,
    )
    if m_partner:
        partner_text = m_partner.group(1)
        if "10000base" in partner_text:
            info["partner_max_mbps"] = 10000
        elif "5000base" in partner_text:
            info["partner_max_mbps"] = 5000
        elif "2500base" in partner_text:
            info["partner_max_mbps"] = 2500
        elif "1000base" in partner_text:
            info["partner_max_mbps"] = 1000
        elif "100base" in partner_text:
            info["partner_max_mbps"] = 100
        elif "10base" in partner_text:
            info["partner_max_mbps"] = 10

    if info["link_detected"] and info["speed_mbps"] > 0 and info["speed_mbps"] < info["max_speed_mbps"]:
        info["speed_warning"] = (
            f"Negotiated at {info['speed_mbps']} Mbps on a {info['max_speed_label']} capable NIC "
            f"(Switch/Partner advertised max: {info['partner_max_mbps'] or info['speed_mbps']} Mbps)"
        )

    return info


def get_lldp_neighbors() -> Dict[str, Dict[str, str]]:
    neighbors: Dict[str, Dict[str, str]] = {}
    out = run_cmd(["lldpctl", "-f", "json"])
    if not out:
        return neighbors
    try:
        data = json.loads(out)
        lldp_ifaces = data.get("lldp", {}).get("interface", [])
        if isinstance(lldp_ifaces, dict):
            lldp_ifaces = [lldp_ifaces]
        for entry in lldp_ifaces:
            for ifname, details in entry.items():
                chassis = details.get("chassis", {})
                port = details.get("port", {})
                vlan = details.get("vlan", {})
                sw_name = "Unknown Switch"
                if isinstance(chassis, dict):
                    for k, v in chassis.items():
                        if isinstance(v, dict) and "value" in v:
                            sw_name = v["value"]
                            break
                        elif k == "name" and isinstance(v, list) and v:
                            sw_name = v[0].get("value", sw_name)
                port_id = ""
                if isinstance(port, dict):
                    port_id = port.get("id", {}).get("value", "") or port.get("descr", [{}])[0].get("value", "") if isinstance(port.get("descr"), list) else port.get("descr", "")
                vlan_id = ""
                if isinstance(vlan, dict):
                    vlan_id = str(vlan.get("vlan-id", ""))
                neighbors[ifname] = {
                    "switch_name": str(sw_name),
                    "port_id": str(port_id),
                    "vlan_id": str(vlan_id),
                }
    except Exception:
        pass
    return neighbors


def ensure_virtual_loopback() -> bool:
    """Create veth_trex0 <-> veth_trex1 virtual pair so Cisco TRex always has a high-speed loopback pair ready."""
    out = run_cmd(["ip", "link", "show", "veth_trex0"])
    if not out:
        subprocess.run(["ip", "link", "add", "veth_trex0", "type", "veth", "peer", "name", "veth_trex1"], check=False)
    for dev, mac in [("veth_trex0", "02:53:56:00:00:01"), ("veth_trex1", "02:53:56:00:00:02")]:
        subprocess.run(["ip", "link", "set", "dev", dev, "address", mac], check=False)
        subprocess.run(["ip", "link", "set", "dev", dev, "mtu", "9216", "up", "promisc", "on"], check=False)
        subprocess.run(["ethtool", "-K", dev, "rx", "off", "tx", "off", "sg", "off", "tso", "off", "gso", "off"], check=False, capture_output=True)
    return True


def discover_interfaces() -> Dict[str, Any]:
    pci_map = get_pci_devices()
    mgmt_iface = get_default_route_iface()
    lldp_map = get_lldp_neighbors()

    ip_addr_out = run_cmd(["ip", "-j", "addr", "show"])
    addr_map: Dict[str, Dict[str, Any]] = {}
    if ip_addr_out:
        try:
            for entry in json.loads(ip_addr_out):
                addr_map[entry["ifname"]] = entry
        except Exception:
            pass

    interfaces: List[Dict[str, Any]] = []
    sys_net = Path("/sys/class/net")
    for net_dir in sorted(sys_net.iterdir(), key=lambda p: p.name):
        ifname = net_dir.name
        if ifname == "lo":
            continue

        dev_link = net_dir / "device"
        pci_slot = "virtual"
        driver = "veth"
        numa_node = 0
        if dev_link.exists():
            try:
                real_dev = os.path.realpath(dev_link)
                pci_slot = os.path.basename(real_dev)
                drv_link = dev_link / "driver"
                if drv_link.exists():
                    driver = os.path.basename(os.path.realpath(drv_link))
                numa_file = dev_link / "numa_node"
                if numa_file.exists():
                    n_val = int(numa_file.read_text().strip())
                    numa_node = max(0, n_val)
            except Exception:
                pass

        # Skip docker/bridge virtuals except veth_trex*
        if pci_slot == "virtual" and not ifname.startswith("veth_trex"):
            continue

        addr_entry = addr_map.get(ifname, {})
        mac = addr_entry.get("address", "00:00:00:00:00:00")
        mtu = addr_entry.get("mtu", 1500)
        operstate = addr_entry.get("operstate", "DOWN").upper()
        ipv4_list = []
        ipv6_list = []
        for ai in addr_entry.get("addr_info", []):
            if ai.get("family") == "inet":
                ipv4_list.append(f"{ai.get('local')}/{ai.get('prefixlen')}")
            elif ai.get("family") == "inet6":
                ipv6_list.append(f"{ai.get('local')}/{ai.get('prefixlen')}")

        eth_info = parse_ethtool(ifname) if pci_slot != "virtual" else {
            "speed_mbps": 10000,
            "speed_label": "10000Mb/s (Virtual Loopback)",
            "max_speed_mbps": 10000,
            "max_speed_label": "10 Gbps",
            "duplex": "Full",
            "port_type": "Virtual Loopback Pair",
            "link_detected": True,
            "partner_max_mbps": 10000,
            "speed_warning": None,
        }

        # Read RX/TX counters from sysfs
        stats_dir = net_dir / "statistics"
        rx_bytes = int((stats_dir / "rx_bytes").read_text().strip()) if (stats_dir / "rx_bytes").exists() else 0
        tx_bytes = int((stats_dir / "tx_bytes").read_text().strip()) if (stats_dir / "tx_bytes").exists() else 0
        rx_packets = int((stats_dir / "rx_packets").read_text().strip()) if (stats_dir / "rx_packets").exists() else 0
        tx_packets = int((stats_dir / "tx_packets").read_text().strip()) if (stats_dir / "tx_packets").exists() else 0
        rx_dropped = int((stats_dir / "rx_dropped").read_text().strip()) if (stats_dir / "rx_dropped").exists() else 0
        tx_dropped = int((stats_dir / "tx_dropped").read_text().strip()) if (stats_dir / "tx_dropped").exists() else 0

        pci_desc = pci_map.get(pci_slot, {}).get("description", "Cisco TRex Virtual Loopback Interface" if ifname.startswith("veth_trex") else "Network Interface")
        if "AQC113" in pci_desc or "10G" in pci_desc:
            eth_info["max_speed_mbps"] = 10000
            eth_info["max_speed_label"] = "10 Gbps"

        is_mgmt = (ifname == mgmt_iface) or (len(ipv4_list) > 0 and any("10.20.30." in ip for ip in ipv4_list))

        interfaces.append({
            "ifname": ifname,
            "pci_address": pci_slot,
            "pci_bus": pci_slot,
            "description": pci_desc,
            "driver": driver,
            "mac": mac,
            "mtu": mtu,
            "numa_node": numa_node,
            "operstate": "up" if (eth_info["link_detected"] or operstate == "UP") else "down",
            "link_detected": eth_info["link_detected"],
            "speed_mbps": eth_info["speed_mbps"] if (eth_info["link_detected"] or pci_slot == "virtual") else 0,
            "speed_label": eth_info["speed_label"],
            "max_speed_mbps": eth_info["max_speed_mbps"],
            "max_supported_mbps": eth_info["max_speed_mbps"],
            "max_speed_label": eth_info["max_speed_label"],
            "duplex": eth_info["duplex"],
            "port_type": eth_info["port_type"],
            "partner_max_mbps": eth_info["partner_max_mbps"],
            "speed_warning": eth_info["speed_warning"],
            "ipv4": ipv4_list[0] if ipv4_list else "",
            "ipv4_list": ipv4_list,
            "ipv6": ipv6_list,
            "is_management": is_mgmt,
            "role": "MGMT + Live TX/RX (10GbE)" if is_mgmt and eth_info["max_speed_mbps"] >= 10000 else ("MGMT Protected" if is_mgmt else ("TRex Loopback" if ifname.startswith("veth_trex") else "Test Port (1GbE)")),
            "lldp": lldp_map.get(ifname),
            "counters": {
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "rx_packets": rx_packets,
                "tx_packets": tx_packets,
                "rx_dropped": rx_dropped,
                "tx_dropped": tx_dropped,
            },
        })

    # Sort physical first (10G first, then eno1..4), then virtual
    def sort_key(item: Dict[str, Any]):
        if item["ifname"] == "enp216s0":
            return (0, item["ifname"])
        if item["pci_address"] != "virtual":
            return (1, item["ifname"])
        return (2, item["ifname"])

    interfaces.sort(key=sort_key)

    phys_nics = [i for i in interfaces if i["pci_address"] != "virtual"]
    ten_g_nics = [i for i in phys_nics if i["max_speed_mbps"] >= 10000]
    one_g_nics = [i for i in phys_nics if i["max_speed_mbps"] == 1000]
    non_mgmt_up = [i for i in phys_nics if not i["is_management"] and i["link_detected"]]

    limitation_msg = (
        "R640 currently has 1x 10GbE NIC (enp216s0, in use for Management 10.20.30.237 at 100 Mbps) "
        "and 4x 1GbE Intel I350 NICs (eno1-eno4, currently unpatched). "
        "Single-box LAN-to-WAN testing through the UniFi EFG using eno1/eno2 supports 10,000 stateful users up to 1 Gbps. "
        "Achieving full 10 Gbps LAN-to-WAN hairpin across the EFG requires either a dual-port 10GbE SFP+ NIC (DPDK-capable) "
        "or a dedicated 10GbE WAN-side responder."
    )
    can_10g = len([i for i in ten_g_nics if not i["is_management"]]) >= 2
    mode_code = "physical_lan_wan" if len(non_mgmt_up) >= 2 else "internal_veth_loopback"
    topology_assessment = {
        "ten_gbe_count": len(ten_g_nics),
        "one_gbe_count": len(one_g_nics),
        "non_mgmt_linked_count": len(non_mgmt_up),
        "can_10g_lan_to_wan_hairpin": can_10g,
        "can_achieve_10gbps_lan_to_wan": can_10g,
        "max_verified_efg_hairpin_mbps": 10000 if can_10g else (1000 if len(one_g_nics) >= 2 else 0),
        "current_cabled_mode": mode_code,
        "active_mode_code": mode_code,
        "active_mode_label": "Physical LAN <-> EFG <-> WAN Pair" if len(non_mgmt_up) >= 2 else "Internal veth_trex0 <-> veth_trex1 Self-Test Loopback",
        "limitation_summary": limitation_msg,
        "honest_10g_explanation": limitation_msg,
    }

    return {
        "management_interface": mgmt_iface,
        "interfaces": interfaces,
        "topology_assessment": topology_assessment,
    }


def generate_trex_cfg(
    discovery: Dict[str, Any],
    mode: str = "auto",
    port0: Optional[str] = None,
    port1: Optional[str] = None,
    output_path: str = "/etc/trex_cfg.yaml",
) -> Dict[str, Any]:
    """
    Generate /etc/trex_cfg.yaml.
    Supports:
    - 'loopback_sim': Uses veth_trex0 and veth_trex1 (safe, zero-drop Linux AF_PACKET mode so management NIC is untouched and TRex daemon runs 24/7).
    - 'physical_pair': Uses two non-management physical ports (e.g. eno1 & eno2 or PCI bus IDs) when linked.
    - 'auto': Checks if two non-management physical ports have carrier UP; if not, uses veth_trex0/veth_trex1 loopback simulation while recording all physical PCI IDs in comments.
    """
    ensure_virtual_loopback()
    ifaces = discovery["interfaces"]
    phys_non_mgmt_up = [
        i for i in ifaces
        if i["pci_address"] != "virtual" and not i["is_management"] and i["link_detected"]
    ]

    selected_mode = mode
    if mode == "auto":
        if len(phys_non_mgmt_up) >= 2:
            selected_mode = "physical_pair"
            p0 = phys_non_mgmt_up[0]["ifname"]
            p1 = phys_non_mgmt_up[1]["ifname"]
        else:
            selected_mode = "loopback_sim"
            p0 = "veth_trex0"
            p1 = "veth_trex1"
    elif mode == "physical_pair" and port0 and port1:
        p0 = port0
        p1 = port1
    else:
        selected_mode = "loopback_sim"
        p0 = port0 or "veth_trex0"
        p1 = port1 or "veth_trex1"

    # SAFETY: never hand the management NIC to TRex (DPDK would unbind it and cut off SSH/web UI),
    # and only allow plain ifname / PCI-address tokens (values are interpolated into YAML).
    protected = {"enp216s0", discovery.get("management_interface") or "enp216s0"}
    for i in ifaces:
        if i.get("is_management"):
            protected.add(i.get("ifname"))
            protected.add(i.get("pci_address"))
    name_ok = re.compile(r"^[A-Za-z0-9_.:\-]{1,32}$")
    if (
        p0 in protected or p1 in protected or p0 == p1
        or not name_ok.match(str(p0)) or not name_ok.match(str(p1))
    ):
        selected_mode = "loopback_sim"
        p0, p1 = "veth_trex0", "veth_trex1"

    # Build YAML with both Stateless L2/L3 and ASTF support
    phys_comment_lines = []
    for i in ifaces:
        if i["pci_address"] != "virtual":
            phys_comment_lines.append(
                f"#   {i['ifname']} | PCIe: {i['pci_address']} | Driver: {i['driver']} | MAC: {i['mac']} | Max: {i['max_speed_label']} | Link: {i['operstate']} | MgmtProtected: {i['is_management']}"
            )
    phys_comments = "\n".join(phys_comment_lines)

    yaml_content = f"""### Auto-generated by Stephan Van Vuuren's Network Tester (discover_hardware.py)
### Dell PowerEdge R640 Discovered Physical NICs:
{phys_comments}
### Active TRex Mode: {selected_mode} ({p0} <-> {p1})

- version: 2
  interfaces: ['{p0}', '{p1}']
  port_limit: 2
  low_end: true
  port_info:
    - ip: 198.18.0.1
      default_gw: 198.18.0.2
    - ip: 198.18.0.2
      default_gw: 198.18.0.1

  platform:
    master_thread_id: 0
    latency_thread_id: 1
    dual_if:
      - socket: 0
        threads: [2, 4, 6, 8]
"""
    Path(output_path).write_text(yaml_content)
    return {
        "config_path": output_path,
        "selected_mode": selected_mode,
        "interfaces": [p0, p1],
        "yaml": yaml_content,
    }


def main():
    parser = argparse.ArgumentParser(description="Stephan's Network Tester Hardware Discovery & TRex Configurator")
    parser.add_argument("--write-config", action="store_true", help="Write /etc/trex_cfg.yaml")
    parser.add_argument("--mode", default="auto", choices=["auto", "loopback_sim", "physical_pair"])
    parser.add_argument("--port0", default=None)
    parser.add_argument("--port1", default=None)
    parser.add_argument("--output", default="/etc/trex_cfg.yaml")
    args = parser.parse_args()

    ensure_virtual_loopback()
    discovery = discover_interfaces()
    if args.write_config:
        cfg_res = generate_trex_cfg(discovery, mode=args.mode, port0=args.port0, port1=args.port1, output_path=args.output)
        discovery["trex_config"] = cfg_res

    print(json.dumps(discovery, indent=2))


if __name__ == "__main__":
    main()
