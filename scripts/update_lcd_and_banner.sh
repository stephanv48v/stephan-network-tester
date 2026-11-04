#!/usr/bin/env bash
# Updates Dell PowerEdge R640 Front Physical LCD Panel (via ipmitool) and Console /etc/issue with live DHCP IP
PRIMARY_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -n1)
if [ -z "$PRIMARY_IP" ]; then
    PRIMARY_IP=$(hostname -I | awk '{print $1}')
fi
PRIMARY_IF=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -n1)

# Update Dell PowerEdge R640 Front Bezel LCD if ipmitool works
if command -v ipmitool >/dev/null 2>&1; then
    ipmitool delloem lcd set mode userdefined "SVV NET TESTER  http://${PRIMARY_IP}" >/dev/null 2>&1 || true
fi

# Update Console /etc/issue Banner for VGA / iDRAC Virtual Console
cat <<EOF > /etc/issue
========================================================================
   STEPHAN VAN VUUREN'S NETWORK TESTER (Dell PowerEdge R640 Appliance)
========================================================================
   Web Dashboard (Port 80) : http://${PRIMARY_IP}
   mDNS Zero-Config URL    : http://stephan-tester.local
   Active DHCP Interface   : ${PRIMARY_IF:-enp216s0} (\4)
   NIC Inventory           : 1x 10GbE (enp216s0) + 4x 1GbE (eno1-eno4)
========================================================================

EOF
