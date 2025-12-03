from flask_login import UserMixin
from .db import query_one

class User(UserMixin):
    def __init__(self, id, username, role_id, role_name):
        self.id = id
        self.username = username
        self.role_id = role_id
        self.role_name = role_name

    @staticmethod
    def get(user_id):
        sql = """
            select u.id, u.username, u.role_id, r.name as role_name 
            from users u 
            join roles r on u.role_id = r.id 
            where u.id = ?
        """
        row = query_one(sql, [user_id])
        if not row:
            return None
        return User(row['id'], row['username'], row['role_id'], row['role_name'])

    @property
    def is_admin(self):
        return self.role_name == 'admin'
