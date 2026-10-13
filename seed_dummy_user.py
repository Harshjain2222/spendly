import sys
import os
import random
from datetime import datetime
from werkzeug.security import generate_password_hash

# Make the project root importable so `database.db` resolves correctly
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from database.db import get_db

# ── Indian name pool (regional variety) ───────────────────────────────────────
first_names = [
    # North Indian
    "Aarav", "Rohan", "Rahul", "Aditya", "Vikram",
    "Kabir", "Nikhil", "Rajesh", "Suresh", "Deepak",
    # South Indian
    "Kiran", "Harish", "Prasad", "Venkat", "Arjun",
    "Lakshmi", "Savitha", "Kavya", "Divya", "Meera",
    # West Indian
    "Rajan", "Mihir", "Jignesh", "Pooja", "Sneha",
    # East Indian
    "Sanjay", "Subhash", "Priya", "Ananya", "Ranjit",
]

last_names = [
    # Pan-India
    "Sharma", "Verma", "Singh", "Patel", "Nair",
    "Reddy", "Iyer", "Pillai", "Rao", "Joshi",
    "Mishra", "Gupta", "Mehta", "Agarwal", "Bose",
    "Chatterjee", "Kulkarni", "Desai", "Menon", "Hegde",
    "Patil", "Kumar", "Dubey", "Pandey", "Shukla",
]

# ── Connect and generate a unique email ───────────────────────────────────────
conn = get_db()


def make_candidate():
    first = random.choice(first_names)
    last  = random.choice(last_names)
    suffix = random.randint(10, 999)
    email  = f"{first.lower()}.{last.lower()}{suffix}@gmail.com"
    return first, last, email


MAX_ATTEMPTS = 20
for attempt in range(MAX_ATTEMPTS):
    first, last, email = make_candidate()
    already_exists = conn.execute(
        "SELECT 1 FROM users WHERE email = ?", (email,)
    ).fetchone()
    if not already_exists:
        break
else:
    print(f"ERROR: Could not find a unique email after {MAX_ATTEMPTS} attempts.")
    conn.close()
    sys.exit(1)

# ── Insert ────────────────────────────────────────────────────────────────────
name          = f"{first} {last}"
password_hash = generate_password_hash("password123")
created_at    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

cursor = conn.execute(
    "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
    (name, email, password_hash, created_at),
)
conn.commit()
user_id = cursor.lastrowid
conn.close()

# ── Confirmation ──────────────────────────────────────────────────────────────
print("[OK] Dummy user created successfully!")
print(f"   ID    : {user_id}")
print(f"   Name  : {name}")
print(f"   Email : {email}")
