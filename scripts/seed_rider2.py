import sqlite3
import bcrypt

pwd_bytes = "Demo@12345".encode("utf-8")[:72]
salt = bcrypt.gensalt()
password_hash = bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

conn = sqlite3.connect("a:/CDD/CDD/database/aifoodie.db")
c = conn.cursor()

c.execute("SELECT id FROM users WHERE email = 'delivery2@demo.com'")
row = c.fetchone()
if not row:
    c.execute("""
        INSERT INTO users (email, hashed_password, full_name, phone, role, is_active, loyalty_points, created_at)
        VALUES ('delivery2@demo.com', ?, 'Rahul Verma (Delivery Partner)', '+91 98450 77889', 'DELIVERY_PARTNER', 1, 0, datetime('now'))
    """, (password_hash,))
    user_id = c.lastrowid
    print(f"Created user delivery2@demo.com with id {user_id}")
else:
    user_id = row[0]
    print(f"User delivery2@demo.com already exists with id {user_id}")

c.execute("SELECT id FROM delivery_profiles WHERE user_id = ?", (user_id,))
prof = c.fetchone()
if not prof:
    c.execute("""
        INSERT INTO delivery_profiles (user_id, vehicle_type, vehicle_number, current_latitude, current_longitude, is_available, total_deliveries, total_earnings, rating, last_location_updated)
        VALUES (?, 'Motorcycle (Hero Splendor Plus)', 'KA-05-AB-4321', 12.9720, 77.5950, 1, 88, 3960.0, 4.8, datetime('now'))
    """, (user_id,))
    print(f"Created delivery profile for user {user_id}")
else:
    print(f"Delivery profile exists with id {prof[0]}")

conn.commit()

c.execute("""
    SELECT u.id, u.email, u.full_name, dp.vehicle_type, dp.vehicle_number, dp.is_available 
    FROM users u 
    JOIN delivery_profiles dp ON u.id = dp.user_id 
    WHERE u.role = 'DELIVERY_PARTNER'
""")
for r in c.fetchall():
    print("Partner:", r)
conn.close()
