import sys
import os
import random
from datetime import datetime, timedelta

# Make project root importable
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from database.db import get_db

# ── Category configurations ──────────────────────────────────────────────────
CATEGORIES = {
    "Food": {
        "weight": 35,
        "min_amount": 50,
        "max_amount": 800,
        "descriptions": [
            "Chai & samosa break",
            "Swiggy order - Biryani",
            "Zomato dinner with friends",
            "Dosa & filter coffee breakfast",
            "Groceries from Blinkit",
            "Milk and daily essentials from Zepto",
            "Street food - Chaat & pani puri",
            "Lunch thali at local mess",
            "Dominos pizza delivery",
            "Evening snacks & sweets from Mithai shop",
            "Office cafeteria lunch",
            "Pav bhaji at street stall",
            "South Indian breakfast at Udupi restaurant",
            "McDonald's burger meal",
            "Fresh fruits and vegetables from mandi",
        ],
    },
    "Transport": {
        "weight": 20,
        "min_amount": 20,
        "max_amount": 500,
        "descriptions": [
            "Auto rickshaw to metro station",
            "Uber ride to office",
            "Ola cab return trip",
            "Metro smart card recharge",
            "Rapido bike taxi ride",
            "Petrol refill for two-wheeler",
            "Bus ticket fare",
            "Local train pass renewal",
            "Mall parking charges",
            "Fastag / Toll gate charge",
        ],
    },
    "Bills": {
        "weight": 12,
        "min_amount": 200,
        "max_amount": 3000,
        "descriptions": [
            "Electricity bill payment",
            "Broadband WiFi bill - Airtel Fiber",
            "Jio mobile prepaid quarterly recharge",
            "Piped natural gas bill (PNG)",
            "Apartment society maintenance fee",
            "Water utility bill",
            "Postpaid mobile bill",
            "LPG cylinder refill booking",
        ],
    },
    "Shopping": {
        "weight": 15,
        "min_amount": 200,
        "max_amount": 5000,
        "descriptions": [
            "Amazon order - Home essentials",
            "Myntra clothing purchase",
            "Flipkart electronics accessory",
            "Decathlon sports gear",
            "Zudio casual wear",
            "Footwear purchase from Bata",
            "Monthly groceries & utensils at D-Mart",
            "Books and stationery purchase",
            "Bed linen from local market",
        ],
    },
    "Other": {
        "weight": 8,
        "min_amount": 50,
        "max_amount": 1000,
        "descriptions": [
            "Laundry & dry cleaning services",
            "Haircut & grooming at salon",
            "Pooja items and flower garland",
            "Photocopy & document printing",
            "Tailor alteration charges",
            "Indoor plants from local nursery",
            "Courier speed post fee",
            "Key duplication & lock repair",
        ],
    },
    "Entertainment": {
        "weight": 5,
        "min_amount": 100,
        "max_amount": 1500,
        "descriptions": [
            "PVR Cinemas movie tickets & popcorn",
            "Netflix monthly subscription",
            "Spotify Premium annual renewal",
            "BookMyShow stand-up comedy show",
            "Hotstar annual subscription",
            "Weekend bowling and arcade",
        ],
    },
    "Health": {
        "weight": 5,
        "min_amount": 100,
        "max_amount": 2000,
        "descriptions": [
            "Apollo Pharmacy - Prescribed medicines",
            "Doctor clinic consultation fee",
            "Blood test & diagnostic lab tests",
            "Dental cleaning & checkup",
            "Multivitamins and protein - Tata 1mg",
            "First-aid kit and pain relief spray",
            "Ayurvedic health supplements",
        ],
    },
}


def seed_expenses(user_id: int, count: int, months: int):
    conn = get_db()
    try:
        # Step 2: Verify user exists
        user = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            print(f"No user found with id {user_id}.")
            sys.exit(1)

        print(f"Generating {count} expenses for User #{user['id']} ({user['name']} - {user['email']}) across the past {months} months...")

        # Prepare weighted categories
        cat_names = list(CATEGORIES.keys())
        cat_weights = [CATEGORIES[c]["weight"] for c in cat_names]

        # Calculate time window
        now = datetime.now()
        total_days = max(1, months * 30)

        records = []
        for _ in range(count):
            chosen_cat = random.choices(cat_names, weights=cat_weights, k=1)[0]
            cfg = CATEGORIES[chosen_cat]
            
            # Amount with 2 decimal places or clean round number
            amount = round(random.uniform(cfg["min_amount"], cfg["max_amount"]), 2)
            desc = random.choice(cfg["descriptions"])
            
            # Random date within the last `months`
            days_ago = random.randint(0, total_days)
            expense_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            
            records.append((user_id, amount, chosen_cat, expense_date, desc))

        # Sort chronologically for clean insertion
        records.sort(key=lambda r: r[3])

        # Step 3: Insert inside a single transaction
        with conn:
            conn.executemany(
                """
                INSERT INTO expenses (user_id, amount, category, date, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                records,
            )

        # Step 4: Confirmation
        dates = [r[3] for r in records]
        min_date = min(dates)
        max_date = max(dates)

        print("\n" + "=" * 60)
        print("[SUCCESS] Expenses successfully inserted!")
        print(f"  - Expenses inserted : {count}")
        print(f"  - Date range        : {min_date} to {max_date} ({months} months)")
        print("\nSample of 5 inserted records:")
        print("-" * 60)
        print(f"{'ID / Date':<12} | {'Category':<14} | {'Amount (INR)':<12} | {'Description'}")
        print("-" * 60)
        
        sample_rows = conn.execute(
            """
            SELECT id, date, category, amount, description 
            FROM expenses 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT 5
            """,
            (user_id,)
        ).fetchall()

        for row in reversed(sample_rows):
            print(f"{row['date']:<12} | {row['category']:<14} | Rs. {row['amount']:>9.2f} | {row['description']}")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Failed to insert expenses. Transaction rolled back. Details: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    if len(sys.argv) != 4:
        print("Usage: /seed-expenses <user_id> <count> <months>")
        print("Example: /seed-expenses 1 50 6")
        sys.exit(1)

    try:
        user_id = int(sys.argv[1])
        count = int(sys.argv[2])
        months = int(sys.argv[3])
    except ValueError:
        print("Usage: /seed-expenses <user_id> <count> <months>")
        print("Example: /seed-expenses 1 50 6")
        sys.exit(1)

    if user_id <= 0 or count <= 0 or months <= 0:
        print("Error: user_id, count, and months must be positive integers.")
        sys.exit(1)

    seed_expenses(user_id, count, months)


if __name__ == "__main__":
    main()
