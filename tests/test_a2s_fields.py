"""Wire fixtures for the extended A2S_INFO fields; no network or credentials."""
import importlib.util
from pathlib import Path
import struct
import unittest


spec = importlib.util.spec_from_file_location('a2s_fields', Path(__file__).resolve().parents[1] / 'tools/a2s_fields.py')
a2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2s)


def mandatory(app_id=0, version=b'1.5.0', ship=b''):
    return (b'\xff\xff\xff\xffI\x11Server\0Lobby\0riskofrain2\0Risk of Rain 2\0'
            + struct.pack('<HBBBccBB', app_id, 2, 4, 0, b'd', b'w', 1, 0)
            + ship + version + b'\0')


class A2SFieldsTests(unittest.TestCase):
    def test_full_edf_preserves_zero_short_and_uses_game_id_low_24_bits(self):
        game_id = (0x80000003 << 32) | (1 << 24) | 632360
        extra = (b'\xf1' + struct.pack('<HQH', 27015, 12345678901234567, 27020)
                 + b'Spectator\0modded,1.5.0\0' + struct.pack('<Q', game_id))
        result = a2s.parse_info(mandatory() + extra)
        self.assertEqual((result['appId16'], result['appId'], result['gameId64']), (0, 632360, game_id))
        self.assertEqual(result['appIdSource'], 'gameId64')
        self.assertEqual((result['gamePort'], result['spectatorPort'], result['spectatorName']),
                         (27015, 27020, 'Spectator'))
        self.assertEqual(result['keywords'], 'modded,1.5.0')
        self.assertTrue(result['hasSteamId'])
        self.assertNotIn('steamId64', result)
        self.assertEqual(a2s.parse_info(mandatory() + extra, include_steam_id=True)['steamId64'],
                         12345678901234567)

    def test_legacy_response_without_edf_and_zero_do_not_invent_app_id(self):
        for app_id in (0, 440, 632360 % 65536):
            with self.subTest(app_id=app_id):
                result = a2s.parse_info(mandatory(app_id))
                self.assertEqual(result['appId'], app_id)
                self.assertEqual(result['appIdSource'], 'appId16')
                self.assertEqual(result['edf'], 0)
                self.assertNotIn('gameId64', result)

    def test_every_truncated_edf_field_is_rejected(self):
        prefix = mandatory() + b'\xf1'
        fields = (struct.pack('<HQH', 27015, 12345678901234567, 27020)
                  + b'Spectator\0modded\0' + struct.pack('<Q', 632360))
        for end in range(len(fields)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                a2s.parse_info(prefix + fields[:end])
        self.assertEqual(a2s.parse_info(prefix + fields)['appId'], 632360)

    def test_malformed_mandatory_and_non_info_packets_are_rejected(self):
        wire = mandatory()
        for end in range(len(wire)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                a2s.parse_info(wire[:end])
        for packet in (b'\xff\xff\xff\xffA1234', b'\xfe\xff\xff\xffI' + wire[5:],
                       b'\xff\xff\xff\xffm' + wire[5:]):
            with self.subTest(packet=packet[:5]), self.assertRaises(ValueError):
                a2s.parse_info(packet)

    def test_unknown_edf_and_trailing_data_fail_closed(self):
        for extra in (b'\x02', b'\x00extra', b'\x01' + struct.pack('<Q', 632360) + b'\0'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                a2s.parse_info(mandatory() + extra)

    def test_ship_fields_precede_version_and_strings_are_bounded(self):
        result = a2s.parse_info(mandatory(2400, b'1.0', b'\x02\x03\x04') + b'\x00')
        self.assertEqual((result['shipMode'], result['shipWitnesses'], result['shipDuration'], result['version']),
                         (2, 3, 4, '1.0'))
        self.assertEqual(a2s.parse_info(mandatory(version=b'\xff'))['version'], '\ufffd')
        with self.assertRaises(ValueError):
            a2s.parse_info(mandatory() + b'\x20unterminated')


if __name__ == '__main__':
    unittest.main()
