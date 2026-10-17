#!/bin/sh
# Managed by rains boot service v1; starts only this project's existing container.
set -eu
name=rains-ror2-server-1
# Minimal ImmortalWrt need not ship a timeout applet. Bound only our Docker
# client subprocess; the daemon and unrelated containers are never signalled.
bounded() {
    "$@" & client=$!
    (sleep 5; kill -TERM "$client" 2>/dev/null || :; sleep 1; kill -KILL "$client" 2>/dev/null || :) >/dev/null 2>&1 & watchdog=$!
    result=0
    wait "$client" || result=$?
    kill -TERM "$watchdog" 2>/dev/null || :
    wait "$watchdog" 2>/dev/null || :
    return "$result"
}
attempt=0
until owner=$(bounded docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$name" 2>/dev/null); do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 24 ]; then echo 'rains: Docker did not become available'; exit 1; fi
    sleep 2
done
if [ "$owner" != rains ]; then echo 'rains: container ownership check failed'; exit 1; fi
running=$(bounded docker inspect --format '{{.State.Running}}' "$name")
if [ "${1:-}" = --status ]; then
    health=$(bounded docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name")
    echo "rains: running=$running health=$health"
    [ "$running" = true ]
    exit $?
fi
if [ "${1:-}" = --check ]; then echo "rains: ownership checked; running=$running"; exit 0; fi
if [ "$running" = true ]; then echo 'rains: project container is already running'; exit 0; fi
bounded docker start "$name" >/dev/null
echo 'rains: started project container; game readiness must be checked separately'
