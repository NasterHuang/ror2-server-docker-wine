#!/bin/sh
set -eu
cd "$(dirname "$0")"
. ./common.sh
exec 9>/opt/ror2/deployment/.rains-companions.lock
flock -n 9
target
case "$(state)" in running/healthy\ *) ;; *) echo "container not healthy" >&2; exit 1 ;; esac
[ ! -e "$plugin_dir" ]
[ "$(digest "$manifest")" = "$manifest_before" ]
[ "$(digest "$runtime/Risk of Rain 2_Data/Managed/RoR2.dll")" = "$game_hash" ]
[ "$(digest "$runtime/BepInEx/plugins/Rains.CompanionSystem/Rains.CompanionSystem.dll")" = "$companion_hash" ]
[ "$(digest candidate.dll)" = "$new_hash" ]

mkdir previous
cp -p "$manifest" previous/release.json
sha256sum previous/release.json > previous.sha256
sha256sum -c previous.sha256
docker exec -i "$container" python3 - "$new_hash" "$PWD" > release.next.json <<'PY'
import json, sys
from pathlib import Path
new, backup = sys.argv[1:]
release = json.loads(Path("/data/runtime/release.json").read_text(encoding="utf-8"))
rel = "BepInEx/plugins/Rains.TrialHeadlessFix/Rains.TrialHeadlessFix.dll"
assert rel not in release["modsInventory"]
release["modsInventory"][rel] = new
release["rainsTrialHeadlessFixDeployment"] = {
    "version": "0.1.0", "pluginSha256": new, "backup": backup,
    "purpose": "Run RoR2.TrialController SyncVar hooks on dedicated server; prune destroyed inventories from ContagiousItemManager.pendingChanges",
    "gameplayVerified": False}
print(json.dumps(release, indent=2, ensure_ascii=False))
PY
[ "$(digest "$manifest")" = "$manifest_before" ]
sha256sum candidate.dll release.next.json > next.sha256
empty_lobby

changing=0
recover() {
    status=$?
    trap - EXIT
    if [ "$status" != 0 ] && [ "$changing" = 1 ]; then
        printf 'Apply failed, rolling back from %s.\n' "$PWD" >&2
        /bin/sh ./rollback.sh --held-lock || printf 'Inspect rollback and game startup at %s.\n' "$PWD" >&2
    fi
    exit "$status"
}
trap recover EXIT
changing=1
docker stop -t 25 "$container"
sha256sum -c next.sha256
mkdir -p "$plugin_dir"
chown 1000:1000 "$plugin_dir"; chmod 755 "$plugin_dir"
replace candidate.dll "$plugin"
chown 1000:1000 "$plugin"; chmod 644 "$plugin"
replace release.next.json "$manifest"
[ "$(digest "$plugin")" = "$new_hash" ]
[ "$(digest "$manifest")" = "$(digest release.next.json)" ]
epoch="$(date '+%s')"
date -u '+%FT%TZ' > applied-at
docker start "$container"
verify_loaded 1 "$(digest release.next.json)" "$epoch"
changing=0
printf 'backup=%s\n' "$PWD"
