# Build without proprietary game files. Pin the resulting image digest after validation.
FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim AS patcher
WORKDIR /build
COPY RoR2Patcher/ ./
RUN dotnet publish RoR2Patcher.csproj -c Release -r linux-x64 --self-contained true -o /publish /p:PublishSingleFile=true

FROM debian:bookworm-slim
ARG DEBIAN_FRONTEND=noninteractive
RUN test "$(dpkg --print-architecture)" = amd64 \
    && apt-get update \
    && apt-get install -y --no-install-recommends wine64 wine xvfb xauth python3 ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 ror2 \
    && useradd --uid 1000 --gid 1000 --create-home ror2 \
    && mkdir -p /data /config /source /mods \
    && chown ror2:ror2 /data
COPY --from=patcher /publish/ /opt/patcher/
COPY tools/ /opt/ror2/tools/
COPY entrypoint.sh /opt/ror2/entrypoint.sh
RUN chmod 755 /opt/ror2/entrypoint.sh /opt/patcher/RoR2Patcher
ENV HOME=/home/ror2 WINEPREFIX=/data/wine WINEARCH=win64 \
    WINEDEBUG=-all WINEDLLOVERRIDES="winhttp=n,b;mscoree,mshtml=" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
WORKDIR /data
EXPOSE 27015/udp 27016/udp 27017/udp
STOPSIGNAL SIGTERM
ENTRYPOINT ["/opt/ror2/entrypoint.sh"]
