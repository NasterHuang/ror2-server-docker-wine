#!/bin/sh
# Pre-change snapshot of everything this fix could touch (not the 4GB game runtime).
set -eu
cd "$(dirname "$0")"
umask 077
mkdir -p snapshot
docker inspect rains-ror2-server-1 > snapshot/container-inspect.json
docker image inspect ror2-local:experimental > snapshot/image-inspect.json
docker inspect -f '{{.Image}}' rains-ror2-server-1 > snapshot/image-id.txt
cp -p /opt/ror2/deployment/docker-compose.yml /opt/ror2/deployment/compose.router.yml snapshot/
cd /opt/ror2/data
tar czf "$OLDPWD/snapshot/runtime-bepinex-and-metadata.tgz" \
    runtime/BepInEx/plugins runtime/BepInEx/config runtime/BepInEx/core runtime/BepInEx/patchers \
    runtime/release.json runtime/patch-manifest.json runtime/mods-lock.json runtime/doorstop_config.ini \
    "runtime/Risk of Rain 2_Data/Managed/RoR2.dll" bepinex-config
cd "$OLDPWD"
sha256sum snapshot/* > snapshot.sha256
ls -la snapshot
