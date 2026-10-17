"""Small synthetic PE/PDBs test identity and offset boundaries, not Unity compatibility."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import uuid

spec = importlib.util.spec_from_file_location('unity_symbols', Path(__file__).resolve().parents[1] / 'tools/unity_symbols.py')
symbols = importlib.util.module_from_spec(spec)
spec.loader.exec_module(symbols)
GUID = uuid.UUID('12345678-1234-5678-abcd-123456789abc')


def fixture():
    pe = bytearray(2048)
    pe[:2] = b'MZ'
    struct.pack_into('<I', pe, 0x3c, 0x80)
    pe[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', pe, 0x84, 0x8664, 2)
    struct.pack_into('<H', pe, 0x94, 240)
    optional = 0x98
    struct.pack_into('<H', pe, optional, 0x20b)
    struct.pack_into('<II', pe, optional + 112 + 48, 0x2100, 28)
    for index, (name, rva, raw, flags) in enumerate(((b'.text', 0x1000, 0x200, 0x60000020),
                                                   (b'.rdata', 0x2000, 0x400, 0x40000040))):
        start = optional + 240 + index * 40
        struct.pack_into('<8sIIII', pe, start, name, 512, rva, 512, raw)
        struct.pack_into('<I', pe, start + 36, flags)
    identity = b'RSDS' + GUID.bytes_le + struct.pack('<I', 1) + b'UnityPlayer.pdb\0'
    struct.pack_into('<IIII', pe, 0x500 + 12, 2, len(identity), 0x2140, 0x540)
    pe[0x540:0x540 + len(identity)] = identity
    pdb = bytearray(512 * 5)
    magic = b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0'
    pdb[:len(magic)] = magic
    struct.pack_into('<6I', pdb, 32, 512, 0, 5, 16, 0, 1)
    struct.pack_into('<I', pdb, 512, 2)
    struct.pack_into('<4I', pdb, 1024, 2, 0, 28, 3)
    struct.pack_into('<III', pdb, 1536, 20000404, 0, 1)
    pdb[1548:1564] = GUID.bytes_le
    cursor = 2048
    for index, name in enumerate(symbols.SYMBOLS.values()):
        record = struct.pack('<IH', 32 * (index + 1), 1) + b'\0' + name.encode() + b'\0'
        pdb[cursor:cursor + len(record)] = record
        cursor += len(record)
    return bytes(pe), bytes(pdb)


class SymbolTests(unittest.TestCase):
    def test_matching_identity_produces_section_relative_offsets(self):
        pe, pdb = fixture()
        with mock.patch.object(symbols, 'FPTS_SHA256', hashlib.sha256(b'fixture-patcher').hexdigest()):
            config, report = symbols.derive_cache(pe, pdb, b'fixture-patcher')
        self.assertTrue(report['pdbGuidAgeMatched'])
        self.assertIn(GUID.hex.upper() + '1', config)
        self.assertEqual([r['rva'] for r in report['offsets'].values()], [0x1020, 0x1040, 0x1060, 0x1080])
        self.assertFalse(report['runtimeVerified'])

    def test_truncated_or_different_build_pdb_is_rejected(self):
        pe, pdb = fixture()
        with self.assertRaisesRegex(ValueError, 'Incomplete PDB'):
            symbols.pdb_identity(pdb[:-1])
        wrong = bytearray(pdb)
        struct.pack_into('<I', wrong, 1544, 2)
        with mock.patch.object(symbols, 'FPTS_SHA256', hashlib.sha256(b'fixture-patcher').hexdigest()):
            with self.assertRaisesRegex(ValueError, 'GUID or age mismatch'):
                symbols.derive_cache(pe, bytes(wrong), b'fixture-patcher')

    def test_different_patcher_and_duplicate_executable_symbol_are_rejected(self):
        pe, pdb = fixture()
        with self.assertRaisesRegex(ValueError, 'FPTS DLL differs'):
            symbols.derive_cache(pe, pdb, b'unreviewed-patcher')
        duplicate = bytearray(pdb)
        record = struct.pack('<IH', 32, 1) + b'\0' + next(iter(symbols.SYMBOLS.values())).encode() + b'\0'
        duplicate[2400:2400 + len(record)] = record
        with mock.patch.object(symbols, 'FPTS_SHA256', hashlib.sha256(b'fixture-patcher').hexdigest()):
            with self.assertRaisesRegex(ValueError, 'ambiguous/missing'):
                symbols.derive_cache(pe, bytes(duplicate), b'fixture-patcher')

    def test_cli_refuses_to_overwrite_input_before_reading_binaries(self):
        with tempfile.TemporaryDirectory() as root:
            original = Path(root) / 'player.dll'
            original.write_bytes(b'preserve-me')
            audit = Path(root) / 'audit.json'
            args = ['unity_symbols.py', '--unity-player', str(original), '--pdb', str(original),
                    '--fpts-dll', str(original), '--config-out', str(original), '--audit-out', str(audit)]
            with mock.patch.object(sys, 'argv', args), mock.patch('builtins.print'):
                self.assertEqual(symbols.main(), 1)
            self.assertEqual(original.read_bytes(), b'preserve-me')
            self.assertFalse(audit.exists())


if __name__ == '__main__':
    unittest.main()
