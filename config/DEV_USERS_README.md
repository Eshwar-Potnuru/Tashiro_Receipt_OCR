# Phase 5D-4: Dev User Seed File Generator

## DO NOT COMMIT THIS FILE TO GIT
This file contains test passwords and must remain local only.

## How to generate config/users_seed_dev.json

Run this Python script to create 30 test users:

```python
import json

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
hq_names = ["HQ1", "HQ2", "HQ3", "HQ4", "HQ5"]
for i, name in enumerate(hq_names, 1):
    users.append({
        "user_id": f"h{i:02d}_hq{i}",
        "email": f"h{i:02d}_hq{i}@example.com",
        "password": "password123",
        "role": "HQ",
        "display_name": name
    })

# Write to config/users_seed_dev.json
with open('config/users_seed_dev.json', 'w') as f:
    json.dump(users, f, indent=2)

print(f"✅ Created {len(users)} users (workers:{len([u for u in users if u['role']=='WORKER'])} admins:{len([u for u in users if u['role']=='ADMIN'])} hq:{len([u for u in users if u['role']=='HQ'])})")
print("File: config/users_seed_dev.json")
```

## Quick generate (one-liner)

From project root:
```bash
python -c "import json; users = [{'user_id': f'w{i:02d}_{n.lower()}', 'email': f'w{i:02d}_{n.lower()}@example.com', 'password': 'password123', 'role': 'WORKER', 'display_name': n} for i, n in enumerate(['Sam', 'Mark', 'Lisa', 'Tom', 'Nina', 'Jake', 'Emma', 'Ryan', 'Maya', 'Alex', 'Zoe', 'Leo', 'Mia', 'Owen', 'Eva', 'Ian', 'Ava', 'Luke', 'Isla', 'Max'], 1)] + [{'user_id': f'a{i:02d}_{n.lower()}', 'email': f'a{i:02d}_{n.lower()}@example.com', 'password': 'password123', 'role': 'ADMIN', 'display_name': f'Admin {n}'} for i, n in enumerate(['Pau', 'Raj', 'Sofia', 'Chen', 'Amir'], 1)] + [{'user_id': f'h{i:02d}_hq{i}', 'email': f'h{i:02d}_hq{i}@example.com', 'password': 'password123', 'role': 'HQ', 'display_name': f'HQ{i}'} for i in range(1, 6)]; open('config/users_seed_dev.json', 'w').write(json.dumps(users, indent=2)); print(f'Created {len(users)} users')"
```

## Login Examples

After seeding, you can login with:
- **Workers:** `w01_sam` / `password123`, `w02_mark` / `password123`, ... `w20_max` / `password123`
- **Admins:** `a01_pau` / `password123`, `a02_raj` / `password123`, ... `a05_amir` / `password123`
- **HQ:** `h01_hq1` / `password123`, `h02_hq2` / `password123`, ... `h05_hq5` / `password123`

## Security Notes

- ⚠️ **This file is for DEV ONLY**
- ✅ Automatically gitignored via `.gitignore`
- ✅ Passwords hashed with bcrypt before storage
- ✅ Plain passwords never stored in database
- 🚫 Never use these passwords in production
