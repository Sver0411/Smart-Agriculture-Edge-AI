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
        if m.get("provenance",{}).get("dataset_kind") not in ("synthetic-software-validation","user-provided-unvalidated"):
            raise ValueError("model requires explicit dataset provenance")
        def finite(obj):
            if isinstance(obj,dict): return all(finite(v) for v in obj.values())
            if isinstance(obj,list): return all(finite(v) for v in obj)
            return not isinstance(obj,float) or math.isfinite(obj)
        if not finite(m):raise ValueError("nonfinite model")
        matrices=[m] if self.name=="logistic" else m.get("layers",[])
        for matrix in matrices:
            if "weights_int8" in matrix:
                scale=matrix.get("weight_scale")
                if type(scale) not in (int,float) or scale<=0:raise ValueError("invalid weight scale")
                if any(type(v) is not int or not -127<=v<=127 for row in matrix["weights_int8"] for v in row):raise ValueError("invalid INT8 weight")
                matrix["weights"]=[[v*scale for v in row] for row in matrix["weights_int8"]]

        self.validate_shapes()

    def validate_shapes(self):
        m=self.model
        def matrix(weights,bias,inputs,outputs):
            if not isinstance(weights,list) or len(weights)!=outputs or len(bias)!=outputs or any(not isinstance(row,list) or len(row)!=inputs for row in weights):
                raise ValueError("model matrix shape mismatch")
            if any(type(v) not in (int,float) for row in weights for v in row) or any(type(v) not in (int,float) for v in bias):
                raise ValueError("invalid model weights")
        if self.name in ("logistic","mlp"):
            if len(m.get('mean',[]))!=4 or len(m.get('scale',[]))!=4 or any(type(v) not in (int,float) or v<=0 for v in m['scale']):
                raise ValueError("model normalization shape mismatch")
        if self.name=='logistic':matrix(m.get('weights',[]),m.get('bias',[]),4,3)
        if self.name=='mlp':
            layers=m.get('layers',[])
            if not 1<=len(layers)<=3:raise ValueError("invalid MLP depth")
            inputs=4
            for layer in layers:
                outputs=len(layer.get('bias',[]))
                if not 1<=outputs<=32:raise ValueError("invalid MLP width")
                matrix(layer.get('weights',[]),layer.get('bias',[]),inputs,outputs);inputs=outputs
            if inputs!=3:raise ValueError("MLP output shape mismatch")
        if self.name=='tree':
            nodes=m.get('nodes',[])
            if not 1<=len(nodes)<=63:raise ValueError("invalid bounded tree")
            def visit(index,trail):
                if type(index) is not int or not 0<=index<len(nodes) or index in trail:raise ValueError("invalid tree edge")
                node=nodes[index]
                if 'class_id' in node:
                    if type(node['class_id']) is not int or not 0<=node['class_id']<3:raise ValueError("invalid tree class")
                    return
                if type(node.get('feature')) is not int or not 0<=node['feature']<4 or type(node.get('threshold')) not in (int,float):raise ValueError("invalid tree feature")
                visit(node.get('left'),trail|{index});visit(node.get('right'),trail|{index})
            visit(0,set())

    def normalize(self,x):
        return [(v-mean)/scale for v,mean,scale in zip(x,self.model['mean'],self.model['scale'])]

    def predict(self,sample,policy=None):
        policy={**config.DEFAULT_POLICY,**(policy or {})}
        label=self.predict_label(extract_features(sample,policy))
        if label=='NONE':return None
        return {'type':label,'duration':policy['irrigation_duration' if label=='IRRIGATION' else 'ventilation_duration'],
                'reason':f'{self.name} synthetic reference prediction','engine':self.name}
