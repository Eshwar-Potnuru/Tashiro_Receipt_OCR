"""
Phase 5D-4: Generate config/users_seed_dev.json

Creates 30 dev users (20 WORKER, 5 ADMIN, 5 HQ) for testing.
Run from project root: python scripts/generate_dev_users.py
"""

import json
from pathlib import Path

# Define users
users = []

# 20 WORKER users
worker_names = [
    "Sam", "Mark", "Lisa", "Tom", "Nina", "Jake", "Emma", "Ryan", "Maya", "Alex",
    "Zoe", "Leo", "Mia", "Owen", "Eva", "Ian", "Ava", "Luke", "Isla", "Max"
]
for i, name in enumerate(worker_names, 1):
    users.append({
        "user_id": f"w{i:02d}_{name.lower()}",
        "email": f"w{i:02d}_{name.lower()}@example.com",
        "password": "password123",
        "role": "WORKER",
        "display_name": name
    })

# 5 ADMIN users
admin_names = ["Pau", "Raj", "Sofia", "Chen", "Amir"]
for i, name in enumerate(admin_names, 1):
    users.append({
        "user_id": f"a{i:02d}_{name.lower()}",
        "email": f"a{i:02d}_{name.lower()}@example.com",
        "password": "password123",
        "role": "ADMIN",
        "display_name": f"Admin {name}"
    })

# 5 HQ users
for i in range(1, 6):
    users.append({
        "user_id": f"h{i:02d}_hq{i}",
        "email": f"h{i:02d}_hq{i}@example.com",
        "password": "password123",
        "role": "HQ",
        "display_name": f"HQ{i}"
    })

# Write to config/users_seed_dev.json
config_dir = Path(__file__).parent.parent / "config"
config_dir.mkdir(exist_ok=True)

output_file = config_dir / "users_seed_dev.json"

with open(output_file, 'w') as f:
    json.dump(users, f, indent=2)

worker_count = len([u for u in users if u['role']=='WORKER'])
admin_count = len([u for u in users if u['role']=='ADMIN'])
hq_count = len([u for u in users if u['role']=='HQ'])

print(f"✅ Created {len(users)} users (workers:{worker_count} admins:{admin_count} hq:{hq_count})")
print(f"📁 File: {output_file}")
print("\nLogin examples:")
print("  Workers: w01_sam, w02_mark, ... w20_max")
print("  Admins:  a01_pau, a02_raj, ... a05_amir")
print("  HQ:      h01_hq1, h02_hq2, ... h05_hq5")
print("\nAll passwords: password123")
