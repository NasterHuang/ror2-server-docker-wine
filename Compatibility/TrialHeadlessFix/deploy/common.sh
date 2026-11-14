#!/bin/sh
# Rains Trial Headless Fix 0.1.0 deployment helpers (modelled on rains-companions kit).
set -eu
umask 077

container=rains-ror2-server-1
data=/opt/ror2/data
runtime="$data/runtime"
plugin_dir_rel=BepInEx/plugins/Rains.TrialHeadlessFix
plugin_rel=$plugin_dir_rel/Rains.TrialHeadlessFix.dll
plugin_dir="$runtime/$plugin_dir_rel"
plugin="$runtime/$plugin_rel"
manifest="$runtime/release.json"
loader_log="$runtime/BepInEx/LogOutput.log"
new_hash=d43ef6f894bed5a225ebe4c12363d451f1f00ff6be46e90e5e7dd0da9c0aaba7
game_hash=73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07
companion_hash=2f576507a1d36d3755b60398598bf6c6768fdff4943b59c8c50549830a0590d9
manifest_before=a06d247cbbef91720113d4c86be79c5ea2e341784a6994b7f597834a4ea9bcce

digest() { sha256sum "$1" | cut -d ' ' -f 1; }

target() {
    [ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$container")" = rains ] &&
    [ "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$container")" = "$data" ] &&
    [ "$(docker inspect -f '{{json .Config.Cmd}}' "$container")" = '["launch"]' ]
}

state() { docker inspect -f '{{.State.Status}}/{{.State.Health.Status}} restarts={{.RestartCount}}' "$container"; }

empty_lobby() {
    docker exec -i "$container" python3 - <<'PY'
import datetime, json, sys
sys.path.insert(0, "/opt/ror2/tools")
from runtime import a2s_info
with open("/data/status/game.json") as f:
    sample = json.load(f)
ts = datetime.datetime.fromisoformat(sample["sampleUtc"].replace("Z", "+00:00"))
age = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds()
q = a2s_info("127.0.0.1", 27016)
print(json.dumps({k: sample.get(k) for k in ("scene", "networkUsers", "runActive")}), flush=True)
print(json.dumps(q), flush=True)
if not (-5 <= age <= 15 and sample["scene"] == "lobby" and sample["networkUsers"] == 0
        and not sample["runActive"] and sample["gameLoadFinished"] and sample["serverActive"]
        and sample["steamLoggedOn"] and q["map"] == "lobby" and q["players"] == 0):
    sys.exit("Game lobby is busy or has no fresh readiness sample.")
PY
}

replace() {
    [ -f "$1" ] || return 1
    swap_file=$(mktemp "$(dirname "$2")/.trial-fix-next-XXXXXX") || return 1
    if { [ -f "$2" ] && ! cp -p "$2" "$swap_file"; } || ! cat "$1" > "$swap_file" || ! mv -f "$swap_file" "$2"; then
        rm -f "$swap_file"; return 1
    fi
}

# $1 = expect plugin loaded (1) or absent (0); $2 = expected manifest digest; $3 = start epoch
verify_loaded() {
    want=$1; expected_manifest=$2; start_epoch=$3
    tries=0; last_state=
    while [ "$tries" -lt 72 ]; do
        observed="$(state)"
        if [ "$observed" != "$last_state" ]; then printf '%s %s\n' "$(date -u '+%FT%TZ')" "$observed"; last_state=$observed; fi
        case "$observed" in
            exited/*|dead/*) break ;;
            running/healthy*)
                ok=1
                [ "$(digest "$manifest")" = "$expected_manifest" ] || ok=0
                grep -q 'Rains Companion System 0.3.0 ready in batch mode' "$loader_log" || ok=0
                grep -q 'Chainloader startup complete' "$loader_log" || ok=0
                if [ "$want" = 1 ]; then
                    [ "$(digest "$plugin")" = "$new_hash" ] || ok=0
                    grep -q 'TrialController SyncVar hooks now run on the dedicated server (3 setters patched)' "$loader_log" || ok=0
                    grep -q 'ContagiousItemManager destroyed-inventory guard installed' "$loader_log" || ok=0
                    ! grep -q 'Trial headless fix refused/failed' "$loader_log" || ok=0
                else
                    [ ! -e "$plugin" ] || ok=0
                    ! grep -q 'Rains Trial Headless Fix' "$loader_log" || ok=0
                fi
                if [ "$ok" = 1 ] && result="$(docker exec -i "$container" python3 - "$start_epoch" 2>/dev/null <<'PY'
import datetime, json, sys
from pathlib import Path
sys.path.insert(0, "/opt/ror2/tools")
from runtime import a2s_info
epoch = int(sys.argv[1])
assert Path("/data/runtime/BepInEx/LogOutput.log").stat().st_mtime >= epoch
with open("/data/status/game.json") as f:
    s = json.load(f)
ts = datetime.datetime.fromisoformat(s["sampleUtc"].replace("Z", "+00:00"))
age = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds()
assert ts.timestamp() >= epoch and -5 <= age <= 20
assert s["serverActive"] and s["gameLoadFinished"] and s["steamLoggedOn"]
print(json.dumps({k: s[k] for k in ("sampleUtc", "scene", "networkUsers", "runActive", "gameLoadFinished", "serverActive", "steamLoggedOn")}))
print(json.dumps(a2s_info("127.0.0.1", 27016)))
PY
)"; then
                    printf '%s\n' "$result"
                    grep -E 'Loading \[Rains|Trial Headless Fix\]|Rains Companion System 0.3.0 ready' "$loader_log" | tail -12
                    [ -e "$plugin" ] && sha256sum "$plugin"
                    sha256sum "$manifest"
                    return 0
                fi ;;
        esac
        tries=$((tries+1)); sleep 5
    done
    printf '%s\n' 'Startup verification failed.' >&2
    grep -Ei 'Trial Headless|Companion System|Unhandled|Exception' "$loader_log" | tail -15 || :
    return 1
}
