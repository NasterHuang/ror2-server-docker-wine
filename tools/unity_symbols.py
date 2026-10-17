#!/usr/bin/env python3
"""Build an offline, SHA-pinned FPTS 1.0.3/1.0.4 exact-PDB offset cache.

No network access, game modification, or native hook execution occurs here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import uuid

FPTS_SHA256 = 'f0ff47d9c25fdf76140f0de00e31c9eb77b246710ca1e10e4b86b49ecc82a0d8'
FPTS104_SHA256 = 'ea955d050d4c5977451e109a82ba52134c388707100e71a6626fd0a2c4521949'
SYMBOLS = {
    'MonoManagerAwakeFromLoadOffset': 'MonoManager::AwakeFromLoad',
    'MonoManagerIsAssemblyCreatedOffset': 'MonoManager::IsAssemblyCreated',
    'ReadStringFromFileOffset': 'ReadStringFromFile',
    'ScriptingManagerDeconstructorOffset': 'ScriptingManager::~ScriptingManager',
}
SYMBOLS104 = {
    'MonoManagerAwakeFromLoadOffset': 'AwakeFromLoad@MonoManager',
    'MonoManagerIsAssemblyCreatedOffset': 'IsAssemblyCreated@MonoManager',
    'IsFileCreatedOffset': 'IsFileCreated',
    'ScriptingManagerDeconstructorOffset': '?1ScriptingManager@',
    'ConvertSeparatorsToPlatformOffset': 'ConvertSeparatorsToPlatform',
    'MallocInternalOffset': 'malloc_internal',
    'FreeAllocInternalOffset': 'free_alloc_internal',
    'ScriptingAssembliesOffset': 'm_ScriptingAssemblies@',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_pe(pe):
    require(pe[:2] == b'MZ' and len(pe) >= 64, 'Not a DOS/PE image')
    offset = struct.unpack_from('<I', pe, 0x3c)[0]
    require(pe[offset:offset + 4] == b'PE\0\0', 'Invalid PE signature')
    machine, count = struct.unpack_from('<HH', pe, offset + 4)
    require(machine == 0x8664, 'Only reviewed Windows x64 UnityPlayer is supported')
    optional_size = struct.unpack_from('<H', pe, offset + 20)[0]
    optional = offset + 24
    require(struct.unpack_from('<H', pe, optional)[0] == 0x20b, 'Expected PE32+ optional header')
    require(optional_size >= 168, 'Missing PE debug directory entry')
    sections = []
    for index in range(count):
        start = optional + optional_size + 40 * index
        name, virtual_size, rva, raw_size, raw_offset = struct.unpack_from('<8sIIII', pe, start)
        flags = struct.unpack_from('<I', pe, start + 36)[0]
        require(raw_offset + raw_size <= len(pe), 'Truncated PE section')
        sections.append(dict(name=name.rstrip(b'\0').decode('ascii'), rva=rva,
                             virtualSize=virtual_size, rawSize=raw_size, rawOffset=raw_offset, flags=flags))
    debug_rva, debug_size = struct.unpack_from('<II', pe, optional + 112 + 6 * 8)
    debug_offsets = [s['rawOffset'] + debug_rva - s['rva'] for s in sections
                     if s['rva'] <= debug_rva and debug_rva + debug_size <= s['rva'] + s['rawSize']]
    require(len(debug_offsets) == 1 and debug_size % 28 == 0, 'Invalid PE debug directory')
    identities = []
    for start in range(debug_offsets[0], debug_offsets[0] + debug_size, 28):
        kind, size, _, pointer = struct.unpack_from('<IIII', pe, start + 12)
        if kind != 2:
            continue
        require(pointer + size <= len(pe) and size >= 25, 'Truncated CodeView debug record')
        record = pe[pointer:pointer + size]
        require(record[:4] == b'RSDS', 'Unsupported CodeView format')
        guid = uuid.UUID(bytes_le=record[4:20])
        age = struct.unpack_from('<I', record, 20)[0]
        name = record[24:].split(b'\0', 1)[0].decode('ascii')
        require(name.lower().endswith('.pdb'), 'Invalid CodeView PDB path')
        identities.append((guid, age, name))
    require(len(identities) == 1, 'Missing or ambiguous CodeView PDB identity')
    return sections, identities[0]


def pdb_identity(pdb):
    require(pdb.startswith(b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0'), 'Expected native MSF 7 PDB')
    block, _, count, directory_size, _, block_map = struct.unpack_from('<6I', pdb, 32)
    require(block in (512, 1024, 2048, 4096, 8192, 16384), 'Invalid MSF block size')
    require(len(pdb) == block * count, f'Incomplete PDB: {len(pdb)} != {block * count}')
    directory_blocks = (directory_size + block - 1) // block
    require(directory_blocks * 4 <= block and block_map < count, 'Unsupported/invalid MSF block map')
    pages = struct.unpack_from('<' + 'I' * directory_blocks, pdb, block_map * block)
    require(all(p < count for p in pages), 'MSF directory page outside file')
    directory = b''.join(pdb[p * block:(p + 1) * block] for p in pages)[:directory_size]
    streams = struct.unpack_from('<I', directory)[0]
    require(2 <= streams <= directory_size // 4 - 1, 'Invalid MSF stream count')
    sizes = struct.unpack_from('<' + 'I' * streams, directory, 4)
    pointer = 4 + 4 * streams
    info = None
    for index, size in enumerate(sizes):
        num_pages = 0 if size == 0xffffffff else (size + block - 1) // block
        require(pointer + num_pages * 4 <= len(directory), 'Truncated MSF stream directory')
        pages = struct.unpack_from('<' + 'I' * num_pages, directory, pointer)
        pointer += 4 * num_pages
        require(all(p < count for p in pages), 'MSF stream page outside file')
        if index == 1:
            require(28 <= size <= 1024 * 1024, 'Invalid PDB identity stream size')
            info = b''.join(pdb[p * block:(p + 1) * block] for p in pages)[:size]
    return uuid.UUID(bytes_le=info[12:28]), struct.unpack_from('<I', info, 8)[0]


def derive_cache(pe, pdb, patcher):
    digest = sha256(patcher)
    require(digest in (FPTS_SHA256, FPTS104_SHA256), 'FPTS DLL differs from reviewed Thunderstore 1.0.3/1.0.4; re-audit its cache/symbol algorithm')
    modern = digest == FPTS104_SHA256
    symbols = SYMBOLS104 if modern else SYMBOLS
    sections, (guid, age, pdb_name) = parse_pe(pe)
    require((guid, age) == pdb_identity(pdb), 'UnityPlayer/PDB GUID or age mismatch')
    records = {}
    for key, symbol in symbols.items():
        candidates = []
        matches = list(re.finditer(re.escape(symbol.encode('ascii')), pdb))
        if modern and not matches and key == 'MonoManagerIsAssemblyCreatedOffset':
            # Reviewed 1.0.4 returns IntPtr.Zero BEFORE adding module base,
            # then selects IsFileCreated when IsAssemblyCreated.IsApplied=false.
            # 1.0.3 does not have this safe cache-zero branch: never allow it there.
            records[key] = dict(symbol=symbol, rva=0, rvaHex='00', absent=True,
                                reason='No exact PDB function; FPTS 1.0.4 safely skips this hook and uses IsFileCreated')
            continue
        for match in matches:
            position = match.start()
            if position < 7:
                continue
            # Exact reviewed MiniPdbReader algorithm, not a cross-version offset.
            relative = struct.unpack_from('<I', pdb, position - 7)[0]
            section = struct.unpack_from('<H', pdb, position - 3)[0] - 1
            if not 0 <= section < len(sections):
                continue
            entry = sections[section]
            executable = key != 'ScriptingAssembliesOffset'
            if bool(entry['flags'] & 0x20000000) != executable or relative >= min(entry['virtualSize'], entry['rawSize']):
                continue
            rva = entry['rva'] + relative
            raw = entry['rawOffset'] + relative
            candidates.append(dict(pdbPosition=position, section=section, rva=rva,
                                   rvaHex=f'{rva:X}', first16Bytes=pe[raw:raw + 16].hex()))
        if modern:
            require(candidates and len({c['rva'] for c in candidates}) == 1,
                    f'Refuse ambiguous/missing symbol {symbol}: {candidates}')
            require(candidates[0]['pdbPosition'] == matches[0].start(),
                    f'Refuse invalid first PDB pattern match for {symbol}')
        else:
            require(len(candidates) == 1, f'Refuse ambiguous/missing executable symbol {symbol}: {candidates}')
        records[key] = dict(symbol=symbol, **candidates[0])
        if modern:
            records[key]['matchingRecords'] = candidates
    identity = guid.hex.upper() + str(age)
    config = (['[Overrides]', '', 'FunctionOffsetLookupType = PreferPdb', ''] if modern else [])
    config.extend(['[Cache]', '', 'LastDownloadedGUID = ' + identity, ''])
    for key, record in records.items():
        config.extend([key + ' = ' + record['rvaHex'], ''])
    config_text = '\n'.join(config)
    report = dict(unityPlayerSha256=sha256(pe), pdbSha256=sha256(pdb), pdbBytes=len(pdb),
                  serializationPatcherVersion='1.0.4' if modern else '1.0.3',
                  serializationPatcherSha256=sha256(patcher), configSha256=sha256(config_text.encode('utf-8')),
                  guidAge=identity, pdbName=pdb_name, pdbGuidAgeMatched=True, offsets=records,
                  installedReaderAlgorithm='uint32 @ symbol-7 + ImageSectionHeaders[uint16 @ symbol-3 - 1].VirtualAddress',
                  runtimeVerified=False)
    report['source'] = ('https://symbolserver.unity3d.com/' + Path(pdb_name.replace('\\', '/')).name +
                        '/' + identity + '/' + Path(pdb_name.replace('\\', '/')).name)
    if modern:
        report['compatibilityWarning'] = 'Use only with the audited FPTS 1.0.4 DLL; 1.0.3 cached zero would target module base. Replace DLL and config together.'
    return config_text, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unity-player', required=True, type=Path)
    parser.add_argument('--pdb', required=True, type=Path)
    parser.add_argument('--fpts-dll', required=True, type=Path)
    parser.add_argument('--config-out', required=True, type=Path)
    parser.add_argument('--audit-out', required=True, type=Path)
    args = parser.parse_args()
    try:
        inputs = {p.resolve() for p in (args.unity_player, args.pdb, args.fpts_dll)}
        outputs = [args.config_out.resolve(), args.audit_out.resolve()]
        require(not inputs.intersection(outputs) and outputs[0] != outputs[1], 'Output paths must not overwrite inputs or each other')
        config, report = derive_cache(args.unity_player.read_bytes(), args.pdb.read_bytes(), args.fpts_dll.read_bytes())
        for destination, content in ((args.config_out, config), (args.audit_out, json.dumps(report, indent=2) + '\n')):
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_text(content, encoding='utf-8', newline='\n')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, struct.error, UnicodeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
