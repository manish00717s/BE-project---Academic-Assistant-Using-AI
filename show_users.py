import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database/database/evaluation_system.db')
conn.row_factory = sqlite3.Row

users = conn.execute('SELECT id, full_name, email, role FROM users ORDER BY role, id').fetchall()

print(f"{'Role':<10} | {'Email':<28} | {'Name'}")
print("-" * 75)
for u in users:
    print(f"{u['role']:<10} | {u['email']:<28} | {u['full_name']}")

# Reset all passwords to role-based defaults
print("\n--- Resetting all passwords ---")
for u in users:
    if u['role'] == 'Admin':
        pwd = 'admin123'
    elif u['role'] == 'Teacher':
        pwd = 'teacher123'
    else:
        pwd = 'student123'
    
    hashed = generate_password_hash(pwd)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, u['id']))

conn.commit()
conn.close()

print("\nAll passwords reset!")
print(f"{'Role':<10} | Password")
print("-" * 30)
print(f"{'Admin':<10} | admin123")
print(f"{'Teacher':<10} | teacher123")
print(f"{'Student':<10} | student123")
