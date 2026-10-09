"""Repeated failure/recovery verification with isolated, retained evidence."""
import argparse
import asyncio
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from experiments.runner import run_scenario, write_json

REPEATS = {'stale-generation':10, 'gateway-failover':3, 'gateway-recovery':3,
           'split-brain':1, 'controller-unavailable':1, 'server-offline':1, 'queue-replay':1}

def source_manifest():
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],text=True).splitlines()
    files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(set(paths))
           if Path(p).is_file() and p.split('/')[0] in
           ('common','controller_node','gateway','sensor_node','server','firmware','experiments','config','simulation','ai','tests','third_party','scripts','.github')}
    return {'revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True)),
            'python':platform.python_version(),'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
            'source_sha256':files}

async def run(output, seed=42):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    write_json(output/'source_manifest.json',source_manifest())
    summaries=[]
    for name,count in REPEATS.items():
        for i in range(count):
            result=await run_scenario(name,output/f'{name}-{i:02}',seed)
            print(f'{name} {i+1}/{count}: {result["status"]}',flush=True)
            summaries.append(result)
    write_json(output/'suite_summary.json',{'passed':sum(r['status']=='PASS' for r in summaries),
                                          'total':len(summaries),'scenarios':summaries})
    hashes={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob('*')) if p.is_file() and p.suffix not in ('.db','-wal','-shm') and not '.db' in p.name}
    write_json(output/'evidence_sha256.json',hashes)
    return 0 if all(r['status']=='PASS' for r in summaries) else 1

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='.research-runs/stabilization-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    raise SystemExit(asyncio.run(run(args.output,args.seed)))
if __name__=='__main__':main()
