"""Symmetric INT8 weight-storage experiment; host dequantized inference only.

Bias/activations remain floating point. This is not an integer MCU kernel.
"""
from copy import deepcopy
import json
from pathlib import Path
from ai.engines import create_engine
from ai.dataset import generate
from ai.engines.base import LABELS


def quantize_matrix(weights):
    maximum=max(abs(v) for row in weights for v in row)
    scale=maximum/127 if maximum else 1.0
    return [[max(-127,min(127,round(v/scale))) for v in row] for row in weights],scale


def export(output,seed=42):
    out=Path(output);out.mkdir(parents=True,exist_ok=True);report={}
    rows=generate(seed,1200)[960:]
    for name in ('logistic','mlp'):
        source=create_engine(name);model=deepcopy(source.model)
        matrices=[model] if name=='logistic' else model['layers']
        for matrix in matrices:
            values,scale=quantize_matrix(matrix.pop('weights'))
            matrix.update(weights_int8=values,weight_scale=scale)
        model['quantization']={'scheme':'symmetric-per-tensor-int8-weights','activations':'float','bias':'float',
                               'inference':'host dequantized reference, not integer kernel'}
        path=out/(name+'-int8.json');path.write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
        quantized=create_engine(name,path)
        original=[source.predict_label(x) for x,y in rows];actual=[quantized.predict_label(x) for x,y in rows]
        report[name]={'sample_count':len(rows),'fp32_int8_disagreements':sum(a!=b for a,b in zip(original,actual)),
            'synthetic_policy_agreement':sum(LABELS[y]==a for (x,y),a in zip(rows,actual)),
            'serialized_json_bytes':path.stat().st_size,'device_latency':None,'integer_kernel_parity':None}
    (out/'quantization_report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='ai/artifacts/int8');a=p.parse_args()
    print(json.dumps(export(a.output),indent=2))
