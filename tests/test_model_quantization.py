from ai.quantize import quantize_matrix
from ai.engines import create_engine
from ai.features import extract_features


def test_symmetric_weight_quantization_is_bounded_and_repeatable():
    matrix=[[0,-2,1],[3,0,-1]]
    q,scale=quantize_matrix(matrix)
    assert q==quantize_matrix(matrix)[0]
    assert all(-127<=v<=127 for row in q for v in row)
    assert max(abs(v-intv*scale) for row,quant in zip(matrix,q) for v,intv in zip(row,quant))<=scale/2


def test_quantized_reference_engine_keeps_interface_and_provenance():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    sample={'temperature':25,'humidity':60,'soil_moisture':10,'light':800}
    for name in ('logistic','mlp'):
        engine=create_engine(name,root/'ai/artifacts/int8'/(name+'-int8.json'))
        assert engine.predict(sample)['type']=='IRRIGATION'
        assert engine.model['quantization']['activations']=='float'
