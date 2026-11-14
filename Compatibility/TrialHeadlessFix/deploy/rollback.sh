#!/bin/sh
# Restores the exact pre-fix state: removes Rains.TrialHeadlessFix and restores release.json.
set -eu
cd "$(dirname "$0")"
. ./common.sh
if [ "${1:-}" != --held-lock ]; then
    exec 9>/opt/ror2/deployment/.rains-companions.lock
    flock -n 9
fi
target
sha256sum -c previous.sha256
case "$(digest "$manifest")" in
    "$manifest_before") ;;
    *) [ -f release.next.json ] && [ "$(digest "$manifest")" = "$(digest release.next.json)" ] ||
       { printf '%s\n' 'Release manifest differs from both deployment snapshots.' >&2; exit 1; } ;;
esac
if [ -e "$plugin" ] && [ "$(digest "$plugin")" != "$new_hash" ]; then
    printf '%s\n' 'Plugin differs from deployed hash; refusing.' >&2; exit 1
fi
if [ "$(docker inspect -f '{{.State.Running}}' "$container")" = true ]; then
    if [ "${1:-}" != --held-lock ] && [ "${2:-}" != --force-busy ]; then empty_lobby; fi
    docker stop -t 25 "$container"
fi
rm -f "$plugin"
rmdir "$plugin_dir" 2>/dev/null || :
replace previous/release.json "$manifest"
[ "$(digest "$manifest")" = "$manifest_before" ]
epoch="$(date '+%s')"
docker start "$container"
verify_loaded 0 "$manifest_before" "$epoch"
