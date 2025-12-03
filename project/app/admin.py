from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from .db import query_all, execute_update, query_one

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.before_request
@login_required
def require_admin():
    if not current_user.is_admin:
        flash("无权访问", "error")
        return redirect(url_for('main.index'))

@bp.route('/users')
def user_list():
    users = query_all("select u.*, r.name as role_name from users u join roles r on u.role_id = r.id")
    roles = query_all("select * from roles")
    return render_template('admin/user_list.html', users=users, roles=roles)

@bp.route('/users/add', methods=['POST'])
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role_id = request.form.get('role_id')
    
    if not all([username, password, role_id]):
        return jsonify({'code': 1, 'msg': '参数不全'})
        
    existing = query_one("select id from users where username = ?", [username])
    if existing:
        return jsonify({'code': 1, 'msg': '用户已存在'})
        
    pwd_hash = generate_password_hash(password)
    execute_update(
        "insert into users(username, password_hash, role_id) values(?, ?, ?)",
        [username, pwd_hash, role_id]
    )
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.route('/users/update/<int:user_id>', methods=['POST'])
def update_user(user_id):
    role_id = request.form.get('role_id')
    password = request.form.get('password')
    if not role_id and not password:
        return jsonify({'code': 1, 'msg': '无更新内容'})
    if role_id:
        execute_update("update users set role_id = ? where id = ?", [role_id, user_id])
    if password:
        pwd_hash = generate_password_hash(password)
        execute_update("update users set password_hash = ? where id = ?", [pwd_hash, user_id])
    return jsonify({'code': 0, 'msg': '更新成功'})

@bp.route('/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    execute_update("delete from users where id = ?", [user_id])
    return jsonify({'code': 0, 'msg': '删除成功'})

@bp.route('/roles')
def role_list():
    roles = query_all("select * from roles")
    return render_template('admin/role_list.html', roles=roles)

@bp.route('/roles/add', methods=['POST'])
def add_role():
    name = request.form.get('name')
    description = request.form.get('description')
    if not name:
        return jsonify({'code': 1, 'msg': '名称必填'})
    existing = query_one("select id from roles where name = ?", [name])
    if existing:
        return jsonify({'code': 1, 'msg': '角色已存在'})
    execute_update("insert into roles(name, description) values(?, ?)", [name, description])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.route('/roles/delete/<int:role_id>', methods=['POST'])
def delete_role(role_id):
    in_use = query_one("select 1 from users where role_id = ?", [role_id])
    if in_use:
        return jsonify({'code': 1, 'msg': '角色正在使用，无法删除'})
    execute_update("delete from roles where id = ?", [role_id])
    return jsonify({'code': 0, 'msg': '删除成功'})

@bp.route('/settings')
def settings():
    settings_list = query_all("select * from settings")
    settings_dict = {item['key']: item['value'] for item in settings_list}
    return render_template('admin/settings.html', settings=settings_dict)

@bp.route('/settings/update', methods=['POST'])
def update_settings():
    app_name = request.form.get('app_name')
    app_logo = request.form.get('app_logo')
    if app_name:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['app_name', app_name]
        )
    if app_logo:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['app_logo', app_logo]
        )
    flash('设置已更新', 'success')
    return redirect(url_for('admin.settings'))
