#!/usr/bin/env python3
"""Build, audit and record exact provenance for the optional headless ping hook."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    workspace = source.parents[1]
    output = args.output.resolve()
    if output == source or source in output.parents or output in source.parents:
        parser.error('Build output must not overlap the source directory')
    project = source / 'PillarReviveHeadless.csproj'
    audit_project = source / 'audit/Audit.csproj'
    subprocess.run([args.dotnet, 'build', str(project), '--configuration', 'Release',
                    '--output', str(output)], check=True, cwd=workspace)
    subprocess.run([args.dotnet, 'build', str(audit_project), '--configuration', 'Release'],
                   check=True, cwd=workspace)
    result = subprocess.run([args.dotnet, 'run', '--project', str(audit_project),
                             '--configuration', 'Release', '--no-build', '--',
                             str(workspace), str(output / 'Rains.PillarReviveHeadless.dll')],
                            check=True, cwd=workspace, capture_output=True, text=True)
    audit = json.loads(result.stdout)
    (output / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    sources = {
        path.relative_to(workspace).as_posix(): sha256(path)
        for path in sorted(source.rglob('*'))
        if path.is_file() and not any(part in ('bin', 'obj', '__pycache__')
                                      for part in path.relative_to(source).parts)
    }
    report = {
        'schema': 1,
        'assembly': 'Rains.PillarReviveHeadless.dll',
        'version': '0.1.0',
        'builtUtc': datetime.now(timezone.utc).isoformat(),
        'assemblySha256': sha256(output / 'Rains.PillarReviveHeadless.dll'),
        'sourceFilesSha256': sources,
        'acceptedHashes': {
            'game': ['73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07',
                     '48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c'],
            'pillar': ['801805422fadcba1877de4c22411c2debeb3a54fb58054ddfb3836916d3b2051'],
            'networkRuntime': ['76d55b3e90e5fe6c0f8738302b01d54141e5a07931fa4cfa370f6a20832d37cf'],
        },
        'build': {'targetFramework': 'netstandard2.1', 'configuration': 'Release'},
        'staticChecksPassed': audit['checksPassed'],
        'resolvedApiReferences': audit['resolvedApiReferences'],
        'auditReportSha256': sha256(output / 'audit.json'),
        'runtimeVerified': False,
        'clientMarkerDisplayVerified': False,
    }
    if report['assemblySha256'] != audit['assemblySha256']:
        raise RuntimeError('Assembly changed after the static audit')
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'assemblySha256': report['assemblySha256'],
                      'staticChecksPassed': report['staticChecksPassed'],
                      'runtimeVerified': False}, indent=2))


if __name__ == '__main__':
    main()
