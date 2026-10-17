#!/usr/bin/env python3
"""Parse an unsplit Source A2S_INFO datagram, without making a health claim.

Wire format: https://developer.valvesoftware.com/wiki/Server_queries#A2S_INFO
GameID layout: ValveSoftware/source-sdk-2013, src/public/steam/
steamclientpublic.h (CGameID::GameID_t and CGameID::AppID).
The legacy ID field is only 16 bits. EDF bit 0x01 adds a 64-bit GameID,
whose low 24 bits hold the AppID; it is not a server SteamID.
"""
import struct


class _Reader:
    def __init__(self, data):
        self.data = data
        self.position = 5

    def number(self, format, field):
        size = struct.calcsize(format)
        if len(self.data) - self.position < size:
            raise ValueError('Truncated A2S_INFO field: ' + field)
        result = struct.unpack_from(format, self.data, self.position)[0]
        self.position += size
        return result

    def byte(self, field):
        return self.number('<B', field)

    def string(self, field):
        end = self.data.find(b'\0', self.position)
        if end == -1:
            raise ValueError('Unterminated A2S_INFO field: ' + field)
        result = self.data[self.position:end].decode('utf-8', errors='replace')
        self.position = end + 1
        return result


def parse_info(reply, *, include_steam_id=False):
    """Return protocol fields from one complete, unsplit 0x49 response.

    Challenges, split packets, unknown EDF flags and trailing bytes are rejected.
    An old response may end immediately after its version, without an EDF byte.
    ``appId`` uses GameID's low 24 bits when present, otherwise the legacy short;
    ``appId16`` always retains the actual wire short, including zero. Neither
    field proves Steam login, client compatibility, or multiplayer readiness.
    The server SteamID is consumed and bounds checked, but omitted by default.
    """
    if not isinstance(reply, (bytes, bytearray, memoryview)):
        raise TypeError('A2S_INFO reply must be bytes-like')
    reply = bytes(reply)
    if reply[:5] != b'\xff\xff\xff\xffI':
        raise ValueError('Expected one unsplit Source A2S_INFO response')
    read = _Reader(reply)
    result = {'protocol': read.byte('protocol')}
    for field in ('name', 'map', 'folder', 'game'):
        result[field] = read.string(field)
    result['appId16'] = read.number('<H', 'appId16')
    for field in ('players', 'maxPlayers', 'bots'):
        result[field] = read.byte(field)
    result['serverType'] = chr(read.byte('serverType'))
    result['environment'] = chr(read.byte('environment'))
    result['visibility'] = read.byte('visibility')
    result['vac'] = read.byte('vac')
    # The Ship inserts these three bytes before Version in this same format.
    if result['appId16'] == 2400:
        for field in ('shipMode', 'shipWitnesses', 'shipDuration'):
            result[field] = read.byte(field)
    result['version'] = read.string('version')
    result['appId'] = result['appId16']
    result['appIdSource'] = 'appId16'
    result['edf'] = read.byte('edf') if read.position < len(reply) else 0
    edf = result['edf']
    if edf & ~0xf1:
        raise ValueError('Unsupported A2S_INFO EDF flags')
    if edf & 0x80:
        result['gamePort'] = read.number('<H', 'gamePort')
    if edf & 0x10:
        steam_id = read.number('<Q', 'steamId64')
        result['hasSteamId'] = True
        if include_steam_id:
            result['steamId64'] = steam_id
    if edf & 0x40:
        result['spectatorPort'] = read.number('<H', 'spectatorPort')
        result['spectatorName'] = read.string('spectatorName')
    if edf & 0x20:
        result['keywords'] = read.string('keywords')
    if edf & 0x01:
        game_id = read.number('<Q', 'gameId64')
        result['gameId64'] = game_id
        result['appId'] = game_id & 0xffffff
        result['appIdSource'] = 'gameId64'
    if read.position != len(reply):
        raise ValueError('Unexpected trailing A2S_INFO bytes')
    return result
