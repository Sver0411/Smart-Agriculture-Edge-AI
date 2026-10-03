"""Inference from portable JSON exports; no sklearn required at runtime."""
import json
import math
from pathlib import Path
from common import config
from ai.features import FEATURE_NAMES, FEATURE_VERSION, extract_features
LABELS=("NONE","IRRIGATION","VENTILATION")

class ModelEngine:
    name="model"
    def __init__(self,artifact=None):
        path=Path(artifact) if artifact else Path(__file__).resolve().parents[1]/"artifacts"/(self.name+".json")
        self.model=json.loads(path.read_text())
        m=self.model
        if m.get("engine")!=self.name or m.get("feature_version")!=FEATURE_VERSION or m.get("features")!=list(FEATURE_NAMES) or m.get("labels")!=list(LABELS):
            raise ValueError("incompatible model feature/label schema")
        if m.get("provenance",{}).get("dataset_kind")!="synthetic-software-validation":
            raise ValueError("model requires explicit dataset provenance")
        def finite(obj):
            if isinstance(obj,dict): return all(finite(v) for v in obj.values())
            if isinstance(obj,list): return all(finite(v) for v in obj)
            return not isinstance(obj,float) or math.isfinite(obj)
        if not finite(m):raise ValueError("nonfinite model")

    def normalize(self,x):
        return [(v-mean)/scale for v,mean,scale in zip(x,self.model['mean'],self.model['scale'])]

    def predict(self,sample,policy=None):
        policy={**config.DEFAULT_POLICY,**(policy or {})}
        label=self.predict_label(extract_features(sample,policy))
        if label=='NONE':return None
        return {'type':label,'duration':policy['irrigation_duration' if label=='IRRIGATION' else 'ventilation_duration'],
                'reason':f'{self.name} synthetic reference prediction','engine':self.name}
