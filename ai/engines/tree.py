from .base import ModelEngine, LABELS
class TreeEngine(ModelEngine):
    name="tree"
    def predict_label(self,features):
        nodes=self.model['nodes'];index=0
        for _ in range(len(nodes)):
            node=nodes[index]
            if 'class_id' in node:return LABELS[node['class_id']]
            index=node['left'] if features[node['feature']]<=node['threshold'] else node['right']
        raise ValueError("cyclic tree artifact")
