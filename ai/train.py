"""Offline reproducible training/export plus exported-inference parity checks.

python -m ai.train --seed 42 --output ai/artifacts
Requires requirements-training.txt. No claim of real-data accuracy or device cost.
"""
import argparse
import hashlib
import json
from pathlib import Path
from ai.dataset import generate
from ai.features import FEATURE_NAMES,FEATURE_VERSION
from ai.engines import create_engine
from ai.engines.base import LABELS

def train(seed=42,output="ai/artifacts",count=1200,rows=None):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.preprocessing import StandardScaler
    dataset_kind="synthetic-software-validation" if rows is None else "user-provided-unvalidated"
    rows=generate(seed,count) if rows is None else list(rows)
    count=len(rows)
    if count<20 or any(len(x)!=4 or y not in (0,1,2) for x,y in rows):raise ValueError("dataset requires at least 20 four-feature labeled rows")
    cut=int(count*0.8)
    X=np.array([x for x,y in rows]);y=np.array([y for x,y in rows])
    scaler=StandardScaler().fit(X[:cut]);Z=scaler.transform(X)
    models={'logistic':LogisticRegression(max_iter=500,random_state=seed),
            'tree':DecisionTreeClassifier(max_depth=4,random_state=seed),
            'mlp':MLPClassifier(hidden_layer_sizes=(8,),activation='relu',solver='lbfgs',max_iter=1000,random_state=seed)}
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    summary={}
    digest=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
    for name,model in models.items():
        inputs=X if name=='tree' else Z
        model.fit(inputs[:cut],y[:cut])
        artifact={'engine':name,'feature_version':FEATURE_VERSION,'features':list(FEATURE_NAMES),'labels':list(LABELS),
                  'provenance':{'dataset_kind':dataset_kind,'seed':seed,'rows':count,'train_rows':cut,
                                'test_rows':count-cut,'dataset_sha256':digest,'purpose':'policy imitation and pipeline validation'},
                  'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist()}
        if name=='logistic':artifact.update(weights=model.coef_.tolist(),bias=model.intercept_.tolist())
        if name=='tree':
            t=model.tree_;nodes=[]
            for i in range(t.node_count):
                nodes.append({'class_id':int(np.argmax(t.value[i]))} if t.children_left[i]==-1 else
                    {'feature':int(t.feature[i]),'threshold':float(t.threshold[i]),'left':int(t.children_left[i]),'right':int(t.children_right[i])})
            artifact['nodes']=nodes
        if name=='mlp':artifact['layers']=[{'weights':w.T.tolist(),'bias':b.tolist()} for w,b in zip(model.coefs_,model.intercepts_)]
        path=out/(name+'.json');path.write_text(json.dumps(artifact,sort_keys=True,indent=2)+'\n')
        engine=create_engine(name,path)
        expected=model.predict(inputs[cut:]);actual=[LABELS.index(engine.predict_label(x.tolist())) for x in X[cut:]]
        parity=sum(int(a==b) for a,b in zip(actual,expected))
        if parity!=count-cut:raise AssertionError(f'{name} export parity failure')
        summary[name]={'synthetic_test_correct':sum(int(a==b) for a,b in zip(actual,y[cut:])),
                       'synthetic_test_count':count-cut,'export_parity_count':parity,'serialized_bytes':path.stat().st_size,
                       'device_flash_bytes':None,'device_latency_ms':None,'int8_parity':None}
    (out/'training_report.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=42);p.add_argument('--output',default='ai/artifacts');a=p.parse_args()
    print(json.dumps(train(a.seed,a.output),indent=2))
if __name__=='__main__':main()
