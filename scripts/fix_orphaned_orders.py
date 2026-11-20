import sqlite3

conn = sqlite3.connect("database/aifoodie.db")
c = conn.cursor()
c.execute("SELECT id, order_number, status, delivery_partner_id FROM orders WHERE status = 'out_for_delivery' AND delivery_partner_id IS NULL")
unassigned = c.fetchall()
print("Unassigned out_for_delivery orders:", unassigned)
if unassigned:
    c.execute("UPDATE orders SET delivery_partner_id = 4 WHERE status = 'out_for_delivery' AND delivery_partner_id IS NULL")
    conn.commit()
    print("Updated unassigned orders to delivery partner 4 (Vikram Singh)")

# Also create delivery_assignments records if missing
for o_id, o_num, status, _ in unassigned:
    c.execute("SELECT id FROM delivery_assignments WHERE order_id = ?", (o_id,))
    if not c.fetchone():
        c.execute("INSERT INTO delivery_assignments (order_id, delivery_partner_id, assigned_at, picked_up_at, delivery_fee_earned, distance_km) VALUES (?, 4, datetime('now'), datetime('now'), 40.0, 3.2)", (o_id,))
conn.commit()
conn.close()
print("Cleaned up orphaned orders.")
