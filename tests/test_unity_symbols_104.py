"""FPTS 1.0.4 cache-zero semantics stay distinct from the unsafe older reader."""
import hashlib
import struct
import unittest
from unittest import mock

from test_unity_symbols import fixture, symbols


def fixture104(include_optional=False):
    pe, original = fixture()
    pdb = bytearray(original)
    pdb[2048:] = bytes(len(pdb) - 2048)
    cursor = 2048
    for index, (key, name) in enumerate(symbols.SYMBOLS104.items()):
        if key == 'MonoManagerIsAssemblyCreatedOffset' and not include_optional:
            continue
        section = 2 if key == 'ScriptingAssembliesOffset' else 1
        record = struct.pack('<IH', 24 * (index + 1), section) + b'\0' + name.encode() + b'\0'
        pdb[cursor:cursor + len(record)] = record
        cursor += len(record)
    return pe, bytes(pdb), cursor


class Symbols104Tests(unittest.TestCase):
    def modern(self, pe, pdb):
        with mock.patch.object(symbols, 'FPTS104_SHA256', hashlib.sha256(b'104-fixture').hexdigest()):
            return symbols.derive_cache(pe, pdb, b'104-fixture')

    def test_absent_inline_function_uses_audited_zero_and_real_fallback(self):
        pe, pdb, _ = fixture104()
        config, report = self.modern(pe, pdb)
        self.assertIn('FunctionOffsetLookupType = PreferPdb', config)
        self.assertIn('MonoManagerIsAssemblyCreatedOffset = 00', config)
        self.assertTrue(report['offsets']['MonoManagerIsAssemblyCreatedOffset']['absent'])
        self.assertEqual(report['offsets']['IsFileCreatedOffset']['rva'], 0x1048)
        self.assertEqual(report['offsets']['ScriptingAssembliesOffset']['rva'], 0x20c0)
        self.assertEqual(report['serializationPatcherVersion'], '1.0.4')
        self.assertFalse(report['runtimeVerified'])

    def test_real_optional_function_never_replaced_with_zero(self):
        pe, pdb, _ = fixture104(True)
        _, report = self.modern(pe, pdb)
        self.assertEqual(report['offsets']['MonoManagerIsAssemblyCreatedOffset']['rva'], 0x1030)
        self.assertNotIn('absent', report['offsets']['MonoManagerIsAssemblyCreatedOffset'])

    def test_duplicate_records_allowed_only_when_the_target_rva_agrees(self):
        pe, original, cursor = fixture104()
        name = symbols.SYMBOLS104['IsFileCreatedOffset']
        for relative, success in ((72, True), (88, False)):
            pdb = bytearray(original)
            record = struct.pack('<IH', relative, 1) + b'\0' + name.encode() + b'\0'
            pdb[cursor:cursor + len(record)] = record
            if success:
                self.modern(pe, bytes(pdb))
            else:
                with self.assertRaisesRegex(ValueError, 'ambiguous/missing'):
                    self.modern(pe, bytes(pdb))

    def test_old_reader_still_rejects_missing_function(self):
        pe, original = fixture()
        pdb = original.replace(b'MonoManager::IsAssemblyCreated', b'X' * len(b'MonoManager::IsAssemblyCreated'))
        with mock.patch.object(symbols, 'FPTS_SHA256', hashlib.sha256(b'old-fixture').hexdigest()):
            with self.assertRaisesRegex(ValueError, 'ambiguous/missing'):
                symbols.derive_cache(pe, pdb, b'old-fixture')


if __name__ == '__main__':
    unittest.main()
