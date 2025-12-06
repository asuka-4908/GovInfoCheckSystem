from .db import query_all, query_one, execute_update

def ensure_table():
    execute_update("create table if not exists menus( id integer primary key autoincrement, endpoint text unique not null, display_name text not null, order_no integer default 0, admin_only integer default 0 )")

def list_menus():
    ensure_table()
    general = query_all("select * from menus where admin_only = 0 order by order_no asc, id asc")
    admin = query_all("select * from menus where admin_only = 1 order by order_no asc, id asc")
    return general, admin

def update_menu(menu_id: int, display_name: str = None, order_no: int = None):
    sets = []
    params = []
    if display_name:
        sets.append('display_name = ?')
        params.append(display_name)
    if order_no is not None:
        sets.append('order_no = ?')
        params.append(order_no)
    if not sets:
        return False
    params.append(menu_id)
    execute_update(f"update menus set {', '.join(sets)} where id = ?", params)
    return True

def move_menu(menu_id: int, direction: str):
    row = query_one("select id, order_no, admin_only from menus where id = ?", [menu_id])
    if not row:
        return False
    group = row.get('admin_only')
    cur = row.get('order_no') or 0
    if direction == 'up':
        target = query_one("select id, order_no from menus where admin_only = ? and order_no < ? order by order_no desc, id desc limit 1", [group, cur])
    else:
        target = query_one("select id, order_no from menus where admin_only = ? and order_no > ? order by order_no asc, id asc limit 1", [group, cur])
    if not target:
        return False
    tid = target.get('id')
    to = target.get('order_no') or 0
    execute_update("update menus set order_no = ? where id = ?", [to, row.get('id')])
    execute_update("update menus set order_no = ? where id = ?", [cur, tid])
    return True

def reorder_group(admin_only: int, ids: list):
    if admin_only not in (0, 1):
        return False
    if not isinstance(ids, list) or not ids:
        return False
    # 规范化顺序为从1开始的连续数字
    order_val = 1
    for mid in ids:
        try:
            execute_update("update menus set order_no = ? where id = ? and admin_only = ?", [order_val, mid, admin_only])
            order_val += 1
        except Exception:
            continue
    return True
