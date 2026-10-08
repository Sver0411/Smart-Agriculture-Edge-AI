import argparse
from datetime import datetime,timezone
import collections,hashlib,json,pathlib,re,subprocess
parser=argparse.ArgumentParser()
parser.add_argument('--output',default='.research-runs/inventory-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
args=parser.parse_args()
root=pathlib.Path.cwd()
files=[p for p in subprocess.check_output(['git','ls-files','results'],text=True).splitlines() if (root/p).is_file()]
refs=set()
for p in (root/'docs').rglob('*.md'):
 refs.update(re.findall(r'results/[\w./-]+',p.read_text()))
failed=[]
for p in files:
 if p.endswith('summary.json'):
  try:
   if json.loads((root/p).read_text()).get('status')=='FAIL':failed.append(str(pathlib.PurePosixPath(p).parent.parent))
  except (ValueError,TypeError):pass
seen={};rows=[];groups=collections.defaultdict(list)
for p in files:
 h=hashlib.sha256((root/p).read_bytes()).hexdigest();groups[h].append(p)
 if any(p.startswith(prefix+'/') for prefix in failed) or 'failure' in p.lower() or 'failed' in p.lower() or '/reproductions/' in p:kind='C'
 elif any(p.startswith(r.rstrip('/')+'/') or p==r for r in refs):kind='B'
 elif p.endswith(('.elf','.bin','.o','.a')) or '/build/' in p:kind='F'
 elif '/ci-' in p:kind='E'
 elif h in seen:kind='D'
 else:kind='A'
 rows.append({'path':p,'class':kind,'sha256':h,'bytes':(root/p).stat().st_size,'action':'RETAIN'})
 seen[h]=p
value={'classification':'conservative; exact-byte duplicates retain experiment context; no deletion',
 'counts':dict(collections.Counter(r['class'] for r in rows)),
 'revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 'report_references':sorted(refs), 'files':rows,'exact_byte_duplicate_groups':[v for v in groups.values() if len(v)>1]}
out=pathlib.Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
if out.exists():raise FileExistsError('inventory evidence must not be overwritten')
out.write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({'counts':value['counts'],'files':len(rows),'duplicates':len(value['exact_byte_duplicate_groups']),
 'inventory_sha256':hashlib.sha256(out.read_bytes()).hexdigest()},indent=2))
