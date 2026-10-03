"""Host inference latency and serialized model size; no flash/energy estimate."""
import argparse
import json
import math
from pathlib import Path
import time
from ai.engines import create_engine
from ai.dataset import generate


def benchmark(seed=42,count=240):
    rows=generate(seed,count);result={}
    for name in ('rule','logistic','tree','mlp'):
        engine=create_engine(name);elapsed=[];correct=0
        for x,label in rows:
            sample={'soil_moisture':25+x[0]*25,'temperature':32+x[1]*10,'humidity':x[2]*100,'light':math.expm1(x[3]*12)}
            start=time.perf_counter_ns();decision=engine.predict(sample);elapsed.append(time.perf_counter_ns()-start)
            predicted=0 if decision is None else 1 if decision['type']=='IRRIGATION' else 2
            correct+=int(label==predicted)
        path=Path(__file__).parent/'artifacts'/(name+'.json')
        result[name]={'samples':count,'synthetic_policy_agreement':correct,'host_latency_mean_us':sum(elapsed)/len(elapsed)/1000,
                      'serialized_model_bytes':path.stat().st_size if path.exists() else None,
                      'flash_bytes':None,'energy_joules':None,'device_latency_us':None,'int8_result':None}
    return {'dataset_kind':'synthetic-software-validation','seed':seed,'scope':'host software comparison only','engines':result}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    Path(a.output).write_text(json.dumps(benchmark(),indent=2)+'\n')
if __name__=='__main__':main()
