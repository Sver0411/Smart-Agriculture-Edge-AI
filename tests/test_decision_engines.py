import json
import pytest
from ai.features import extract_features, FeatureError, FEATURE_NAMES
from ai.engines import create_engine
from ai.dataset import generate
from gateway.edge_decision import EdgeDecider

SAMPLE={'temperature':25,'humidity':60,'soil_moisture':10,'light':800}


def test_feature_schema_and_policy_relative_values():
    f=extract_features(SAMPLE)
    assert len(f)==len(FEATURE_NAMES)==4
    assert f[0]==-0.6 and f[1]==-0.7
    assert extract_features(SAMPLE,{'soil_moisture_threshold':10})[0]==0


@pytest.mark.parametrize('bad',[{},dict(SAMPLE,light=float('nan')),dict(SAMPLE,humidity=True)])
def test_features_reject_invalid_or_incomplete(bad):
    with pytest.raises(FeatureError):extract_features(bad)


@pytest.mark.parametrize('name',['rule','logistic','tree','mlp'])
def test_engine_interface_and_determinism(name):
    engine=create_engine(name)
    first=engine.predict(SAMPLE)
    assert first['type']=='IRRIGATION'
    assert first==engine.predict(SAMPLE)
    decider=EdgeDecider(engine=name)
    assert decider.decide(SAMPLE)['type']=='IRRIGATION'


def test_dataset_replay_and_export_provenance():
    assert generate(42,10)==generate(42,10)
    assert generate(42,10)!=generate(43,10)
    for name in ('logistic','tree','mlp'):
        engine=create_engine(name)
        assert engine.model['provenance']['dataset_kind']=='synthetic-software-validation'


def test_bad_engine_and_incompatible_artifact_fail(tmp_path):
    with pytest.raises(ValueError):create_engine('huge-network')
    path=tmp_path/'bad.json';path.write_text(json.dumps({'engine':'tree','features':['wrong']}))
    with pytest.raises(ValueError):create_engine('tree',path)
