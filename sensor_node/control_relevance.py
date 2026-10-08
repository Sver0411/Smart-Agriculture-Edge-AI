"""Communication gate only; actuator decisions remain at the gateway."""
from common.protocol import number
from common.settings import SETTINGS

THRESHOLDS = {'soil_moisture': 'soil_moisture_threshold', 'temperature': 'temperature_threshold'}

class ControlRelevanceGate:
    def __init__(self, margins, policy=None):
        self.margins = dict(margins)
        self.set_policy(SETTINGS['policy'] if policy is None else policy)
        self.reported = {}

    def set_policy(self, policy):
        thresholds = {field: policy[key] for field, key in THRESHOLDS.items()}
        if any(not number(v) for v in thresholds.values()):
            raise ValueError('invalid local relevance thresholds')
        if any(not number(v) or v < 0 for v in self.margins.values()):
            raise ValueError('invalid threshold margin')
        self.thresholds = thresholds

    @staticmethod
    def trusted_channels(trust):
        channels = trust.get('channels')
        if channels:
            return {name for name, evidence in channels.items()
                    if evidence.get('state') == 'HEALTHY' and evidence.get('valid', True)}
        return set(THRESHOLDS) if trust.get('state') == 'HEALTHY' and trust.get('usable_for_control') else set()

    def evaluate(self, sample, trusted_channels):
        reasons = []
        for field, threshold in self.thresholds.items():
            current, previous = sample.get(field), self.reported.get(field)
            if field not in trusted_channels or not number(current) or previous is None:
                continue
            crossed = ((previous < threshold) != (current < threshold) if field == 'soil_moisture'
                       else (previous > threshold) != (current > threshold))
            if crossed and 'CONTROL_THRESHOLD_CROSSING' not in reasons:
                reasons.append('CONTROL_THRESHOLD_CROSSING')
            margin = self.margins.get(field, 0)
            if margin > 0 and abs(previous-threshold) > margin and abs(current-threshold) <= margin:
                if 'CONTROL_MARGIN_ENTRY' not in reasons:reasons.append('CONTROL_MARGIN_ENTRY')
        return {'control_relevant_change': bool(reasons), 'reasons': reasons}

    def mark_reported(self, sample, trusted_channels):
        # Only a successful transport admission/report advances this baseline.
        self.reported = {field: float(sample[field]) for field in THRESHOLDS
                         if field in trusted_channels and number(sample.get(field))}
