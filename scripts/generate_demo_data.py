from pathlib import Path

import pandas as pd

rows = [
    {"asset_id": "BUS-001", "failure_code": "BRAKE", "downtime_hours": 8, "repair_cost": 650},
    {"asset_id": "BUS-001", "failure_code": "BRAKE", "downtime_hours": 10, "repair_cost": 720},
    {"asset_id": "BUS-001", "failure_code": "BRAKE", "downtime_hours": 12, "repair_cost": 810},
    {"asset_id": "BUS-002", "failure_code": "ENGINE", "downtime_hours": 3, "repair_cost": 300},
]
path = Path(__file__).resolve().parents[1] / "demo_maintenance.csv"
pd.DataFrame(rows).to_csv(path, index=False)
print(path)
