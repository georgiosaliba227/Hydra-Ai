"""Explicit software scenarios, not manufactured human physiology.

Bootstraps only the real TRAIN partition's mass-proxy rates. Mapping those proxy
rates to a simulated mass-balance loss is an explicit scenario assumption.
Environmental and supplement context has no numerical effect.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random

from .train import canonical, split_participants


def generate_scenarios(real_records: list[dict], *, seed: int = 8317,
                       participants: int = 120) -> list[dict]:
    if type(participants) is not int or participants < 10 or participants > 10000:
        raise ValueError("invalid_participant_count")
    if any(r["synthetic"] for r in real_records):
        raise ValueError("real_inventory_required")
    # Real validation/calibration/test subjects cannot inform the augmentation.
    anchors = split_participants(real_records)["train"]
    if any(r["target_name"] != "corrected_mass_loss_proxy_ml" for r in anchors):
        raise ValueError("corrected_mass_proxy_anchor_required")
    rng = random.Random(seed)
    digest = hashlib.sha256(canonical(anchors).encode()).hexdigest()
    records = []
    for participant in range(participants):
        anchor = rng.choice(anchors)
        # Anchor rate stays within the observed training range. No invented
        # environmental, caffeine, creatine, HR or HRV physiological multiplier.
        rate = anchor["target_value_ml"] / anchor["duration_minutes"]
        for workout in range(4):
            duration = rng.choice([30.0, 45.0, 60.0, 90.0, 120.0])
            latent_loss = rate*duration
            # Scenario sensor noise, NOT measured instrument accuracy. Keep an
            # explicit interval so tests can separate latent and noisy labels.
            noise_ml = rng.uniform(-40.0, 40.0)
            measured_loss = max(0.0, latent_loss+noise_ml)
            consumed_ml = rng.choice([0.0, 150.0, 300.0])
            pre_mass = anchor["pre_mass_kg"]
            post_mass = pre_mass + (consumed_ml-measured_loss)/1000
            row = {"record_id":f"synthetic:{participant:03d}:{workout}",
                   "participant_id":f"synthetic:{anchor["participant_id"]}",
                   "scenario_user_id":f"synthetic-user:{participant:03d}", "study_id":"synthetic-scenarios-v1",
                   "synthetic":True, "target_name":"simulated_sweat_loss_ml",
                   "target_value_ml": measured_loss, "target_method":"synthetic_mass_balance_scenario",
                   "duration_minutes":duration, "pre_mass_kg":pre_mass if rng.random() >= .1 else None,
                   "age_years":anchor["age_years"] if rng.random() >= .1 else None,
                   "temperature_c":rng.choice([None,18.0,24.0,30.0]),
                   "humidity_percent":rng.choice([None,35.0,50.0,75.0]),
                   "intensity":rng.choice(["low","moderate","high"]),
                   "context_only":{"creatine_reported":rng.choice([True,False,None]),
                                   "caffeine_mg":rng.choice([0,80,160,None]),
                                   "thirst_reported":rng.choice([True,False,None]),
                                   "heart_rate_bpm":None,"hrv_ms":None,"sleep_hours":None},
                   "simulated_measurement":{"pre_mass_kg":pre_mass,"post_mass_kg":post_mass,
                                            "consumed_ml":consumed_ml,"urine_ml":0.0,
                                            "latent_loss_ml":latent_loss,"noise_bound_ml":40.0},
                   "source_train_sha256":digest,
                   "source_license":"Hydra synthetic scenarios; empirical source attribution retained in artifact"}
            records.append(row)
    return records


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("real_records",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    records=generate_scenarios(json.loads(args.real_records.read_text()))
    args.output.write_text(json.dumps(records,indent=2,sort_keys=True,allow_nan=False)+"\n")

if __name__=="__main__":
    main()
