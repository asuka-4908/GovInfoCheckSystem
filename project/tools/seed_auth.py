import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from werkzeug.security import generate_password_hash
from project.app.db import execute_update, query_one, get_connection

def seed():
    print("Seeding Auth Data...")
    
    # 1. Roles
    roles = {
        'admin': 'Administrator with full access',
        'user': 'Ordinary user with read-only access to reports'
    }
    
    for role_name, desc in roles.items():
        existing = query_one("select id from roles where name = ?", [role_name])
        if not existing:
            execute_update("insert into roles(name, description) values(?, ?)", [role_name, desc])
            print(f"Role '{role_name}' created.")
        else:
            print(f"Role '{role_name}' already exists.")
            
    # 2. Admin User
    admin_role = query_one("select id from roles where name = 'admin'")
    if not admin_role:
        print("Error: Admin role not found!")
        return
        
    admin_user = query_one("select id from users where username = 'admin'")
    if not admin_user:
        pwd_hash = generate_password_hash("123456")
        execute_update(
            "insert into users(username, password_hash, role_id) values(?, ?, ?)",
            ["admin", pwd_hash, admin_role['id']]
        )
        print("User 'admin' created with password '123456'.")
    else:
        print("User 'admin' already exists.")

if __name__ == "__main__":
    seed()
