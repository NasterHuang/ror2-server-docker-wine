#!/bin/sh
# Project-scoped fw4 integration. Never changes the Docker daemon or other zones.
set -eu
action=${1:-status}
case "$action" in status|apply|remove) ;; *) echo 'Usage: immortalwrt-firewall.sh status|apply|remove' >&2; exit 2;; esac
test "$(id -u)" = 0 || { echo 'Run on the router as root.' >&2; exit 1; }
command -v uci >/dev/null
command -v fw4 >/dev/null
bridge=${ROR2_BRIDGE_NAME:-br-ror2}
case "$bridge" in ''|*[!a-zA-Z0-9_-]*) echo 'Invalid bridge name' >&2; exit 1;; esac
test "${#bridge}" -le 15
port=${PORT:-27015}
query=${STEAM_QUERY_PORT:-27016}
steam=${STEAM_SERVER_PORT:-27017}
for value in "$port" "$query" "$steam"; do
    case "$value" in ''|*[!0-9]*) echo 'Invalid port' >&2; exit 1;; esac
    test "$value" -ge 1024 && test "$value" -le 65535
done
test "$port" != "$query" && test "$port" != "$steam" && test "$query" != "$steam"
sections='ror2_zone ror2_lan ror2_wan ror2_egress ror2_dns'
if test "$action" = status; then
    for section in $sections; do uci -q show "firewall.$section" || true; done
    exit 0
fi
test -z "$(uci changes firewall)" || { echo 'Existing uncommitted firewall changes; preserving them.' >&2; exit 1; }
state=/opt/ror2/deployment
mkdir -p "$state"
marker="$state/firewall-managed.version"
if test ! -f "$marker"; then
    for section in $sections; do
        if uci -q get "firewall.$section" >/dev/null; then
            echo 'A project section already exists without an ownership marker; preserving it.' >&2
            exit 1
        fi
    done
fi
umask 077
if test "$action" = apply; then
    test -d "/sys/class/net/$bridge" || { echo 'Create the project Docker network first.' >&2; exit 1; }
    if test ! -f "$state/firewall-before.uci"; then uci export firewall > "$state/firewall-before.uci"; fi
    for section in $sections; do uci -q delete "firewall.$section" || true; done
    uci batch <<EOF
set firewall.ror2_zone=zone
set firewall.ror2_zone.name='ror2'
add_list firewall.ror2_zone.device='$bridge'
set firewall.ror2_zone.input='REJECT'
set firewall.ror2_zone.output='ACCEPT'
set firewall.ror2_zone.forward='REJECT'
set firewall.ror2_lan=rule
set firewall.ror2_lan.name='RoR2 LAN UDP'
set firewall.ror2_lan.src='lan'
set firewall.ror2_lan.dest='ror2'
set firewall.ror2_lan.proto='udp'
set firewall.ror2_lan.dest_port='$port $query $steam'
set firewall.ror2_lan.target='ACCEPT'
set firewall.ror2_wan=rule
set firewall.ror2_wan.name='RoR2 WAN UDP'
set firewall.ror2_wan.src='wan'
set firewall.ror2_wan.dest='ror2'
set firewall.ror2_wan.proto='udp'
set firewall.ror2_wan.dest_port='$port $query $steam'
set firewall.ror2_wan.target='ACCEPT'
set firewall.ror2_egress=rule
set firewall.ror2_egress.name='RoR2 Steam egress'
set firewall.ror2_egress.src='ror2'
set firewall.ror2_egress.dest='wan'
set firewall.ror2_egress.proto='tcp udp'
set firewall.ror2_egress.target='ACCEPT'
set firewall.ror2_dns=rule
set firewall.ror2_dns.name='RoR2 router DNS'
set firewall.ror2_dns.src='ror2'
set firewall.ror2_dns.proto='tcp udp'
set firewall.ror2_dns.dest_port='53'
set firewall.ror2_dns.target='ACCEPT'
EOF
else
    test -f "$marker" || { echo 'No managed project sections to remove.'; exit 0; }
    for section in $sections; do uci -q delete "firewall.$section" || true; done
fi
if ! fw4 check; then
    for section in $sections; do uci -q revert "firewall.$section" || true; done
    echo 'fw4 check failed; project staged changes reverted.' >&2
    exit 1
fi
if test "$action" = apply; then printf '%s\n' 1 > "$marker"; fi
uci commit firewall
if ! fw4 reload; then
    echo 'Firewall reload failed. Configuration backup is in the project deployment directory.' >&2
    exit 1
fi
if test "$action" = remove; then
    rm -f "$marker"
fi
echo "RoR2 firewall action completed: $action"
