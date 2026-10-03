from .base import ModelEngine, LABELS
class LogisticEngine(ModelEngine):
    name="logistic"
    def predict_label(self,features):
        x=self.normalize(features)
        scores=[b+sum(w*v for w,v in zip(row,x)) for row,b in zip(self.model['weights'],self.model['bias'])]
        return LABELS[max(range(len(scores)),key=scores.__getitem__)]
