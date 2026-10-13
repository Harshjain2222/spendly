description: Seed realistic dummy expenses for a specific user
argument-hint: "<user_id> <count> <months>"
allowed-tools: Read, Bash(python :*)

User input: $ARGUMENTS

## Task
Create <count> realistic dummy expenses for <user_id>, distributed randomly across the past <months> months.

## 1. Parse & validate
Arguments must be exactly:
- user_id: integer
- count: integer
- months: integer

If invalid/missing, stop with:
Usage: /seed-expenses <user_id> <count> <months>
Example: /seed-expenses 1 50 6

## 2. Verify user
Read `database/db.py` first to understand:
- expenses table schema
- DB connection pattern
- database filename

Do NOT hardcode the DB filename.

Verify `user_id` exists in `users`. If not:
No user found with id <user_id>.

## 3. Generate & insert
Write and run a Python script that:
- Randomly spreads expenses across the past <months> months.
- Uses these categories, realistic Indian descriptions, and ₹ amounts:
  - Food: ₹50–800
  - Transport: ₹20–500
  - Bills: ₹200–3000
  - Health: ₹100–2000
  - Entertainment: ₹100–1500
  - Shopping: ₹200–5000
  - Other: ₹50–1000
- Uses roughly proportional category frequency:
  Food most common; Health and Entertainment least common.
- Uses the DB connection pattern from `database/db.py`.
- Uses parameterized SQL queries only; never interpolate/format values into SQL.
- Inserts ALL expenses inside one transaction. Roll back everything if any insert fails.

## 4. Confirm
After success, print:
- Number of expenses inserted
- Date range covered
- Sample of 5 inserted records
