#!/usr/bin/env python3
"""Verify pinned upstream blobs and build one offline-test candidate; never deploy."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--dotnet',default='dotnet')
 parser.add_argument('--output',required=True,type=Path)
 args=parser.parse_args()
 provenance=json.loads((BASE/'upstream-provenance.json').read_text(encoding='utf-8'))
 for name,digest in provenance['sourceFilesSha256'].items():
  if sha(BASE/'upstream'/name)!=digest:raise RuntimeError('Pinned upstream file differs: '+name)
 overlay=json.loads((BASE/'local-patches.json').read_text(encoding='utf-8'))
 if overlay['upstreamCommit']!=provenance['commit']:raise RuntimeError('Patch upstream commit differs')
 dependency_lock=BASE/'upstream/src/FixPluginTypesSerialization/packages.lock.json'
 if sha(dependency_lock)!=overlay['dependencyLockSha256']:raise RuntimeError('Dependency lock differs')
 target=args.output.resolve()
 if target.exists():raise RuntimeError('Refuse overwrite existing candidate directory')
 target.mkdir(parents=True)
 source=target/'build-source'
 shutil.copytree(BASE/'upstream',source,ignore=shutil.ignore_patterns('bin','obj'))
 for patch in overlay['patches']:
  path=(source/patch['path']).resolve()
  if not path.is_relative_to(source):raise RuntimeError('Patch path escapes build source')
  if sha(path)!=patch['beforeSha256']:raise RuntimeError('Patch input differs: '+patch['path'])
  text=path.read_text(encoding='utf-8')
  for edit in patch['edits']:
   if text.count(edit['old'])!=1:raise RuntimeError('Patch context is not unique: '+patch['path'])
   text=text.replace(edit['old'],edit['new'])
  path.write_text(text,encoding='utf-8',newline='\n')
  if sha(path)!=patch['afterSha256']:raise RuntimeError('Patch output differs: '+patch['path'])
 project=source/'src/FixPluginTypesSerialization/FixPluginTypesSerialization.csproj'
 command=[args.dotnet,'build',str(project),'-c','Release','-p:TargetFrameworks=netstandard2.1','-p:RestoreLockedMode=true','-p:NuGetAudit=false','-p:ContinuousIntegrationBuild=true','-p:PathMap='+str(source) +'=/_/fpts']
 log=target/'build.log'
 with log.open('w',encoding='utf-8') as out:
  result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,text=True)
 if result.returncode:raise RuntimeError('Build failed; read '+str(log))
 dll=project.parent/'bin/Release/netstandard2.1/FixPluginTypesSerialization.dll'
 shutil.copy2(dll,target/dll.name)
 shutil.copy2(BASE/'upstream/LICENSE',target/'LICENSE')
 shutil.copy2(BASE/'upstream-provenance.json',target/'upstream-provenance.json')
 shutil.copy2(BASE/'local-patches.json',target/'local-patches.json')
 report=dict(provenance,assemblySha256=sha(dll),sdkVersion=subprocess.check_output([args.dotnet,'--version'],text=True).strip(),targetFramework='netstandard2.1',dependencyLockSha256=sha(project.parent/'packages.lock.json'),buildCommand=command,sourceModifications=overlay['patches'],localPatchesSha256=sha(BASE/'local-patches.json'),runtimeVerified=False)
 (target/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'candidate':str(target),'sha256':sha(dll),'runtimeVerified':False}))
if __name__=='__main__':main()
