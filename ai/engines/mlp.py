import math
from .base import ModelEngine, LABELS
class MLPEngine(ModelEngine):
    name="mlp"
    def predict_label(self,features):
        x=self.normalize(features)
        layers=self.model['layers']
        for i,layer in enumerate(layers):
            x=[b+sum(w*v for w,v in zip(row,x)) for row,b in zip(layer['weights'],layer['bias'])]
            if i<len(layers)-1:x=[max(0,v) for v in x]
        return LABELS[max(range(len(x)),key=x.__getitem__)]
