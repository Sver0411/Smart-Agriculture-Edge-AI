"""Synthetic control-policy fixtures, not measured agriculture observations."""
import random
from common import config
from ai.features import extract_features

def generate(seed=42,count=1200):
    rng=random.Random(seed);rows=[]
    for _ in range(count):
        sample={'soil_moisture':rng.uniform(0,100),'temperature':rng.uniform(-10,60),
                'humidity':rng.uniform(0,100),'light':rng.uniform(0,2000)}
        p=config.DEFAULT_POLICY
        label=1 if sample['soil_moisture']<p['soil_moisture_threshold'] else 2 if sample['temperature']>p['temperature_threshold'] else 0
        rows.append((extract_features(sample),label))
    return rows
