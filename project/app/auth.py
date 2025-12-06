from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from .db import query_one, execute_update
from .models import User

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not username or not password:
            flash('用户名和密码不能为空', 'error')
            return render_template('register.html')
            
        if password != confirm_password:
            flash('两次密码输入不一致', 'error')
            return render_template('register.html')

        existing = query_one("select id from users where username = ?", [username])
        if existing:
            flash('用户名已存在', 'error')
            return render_template('register.html')

        # Default role 'user'
        user_role = query_one("select id from roles where name = 'user'")
        if not user_role:
            # Fallback if 'user' role doesn't exist, try 'admin' or create 'user'
            # For now assume 'user' role exists as per seed logic
            flash('系统错误：无法分配角色', 'error')
            return render_template('register.html')
            
        pwd_hash = generate_password_hash(password)
        execute_update(
            "insert into users(username, password_hash, role_id) values(?, ?, ?)",
            [username, pwd_hash, user_role['id']]
        )
        new_user = query_one("select id from users where username = ?", [username])
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
        except Exception:
            cols = []
        if 'user_id' not in cols:
            try:
                execute_update("alter table ai_engines add column user_id integer")
            except Exception:
                pass
        admin_user = query_one("select id from users where username = ?", ['admin'])
        admin_id = admin_user and admin_user.get('id')
        if new_user and admin_id:
            try:
                rows = query_all("select provider_name, api_url, api_key, model_name, enabled from ai_engines where user_id = ? order by id asc", [admin_id])
                if not rows:
                    rows = query_all("select provider_name, api_url, api_key, model_name, enabled from ai_engines where user_id is null order by id asc")
            except Exception:
                rows = []
            for r in rows or []:
                try:
                    execute_update("insert into ai_engines(provider_name, api_url, api_key, model_name, enabled, user_id) values(?, ?, ?, ?, ?, ?)", [r.get('provider_name') or '', r.get('api_url') or '', r.get('api_key') or '', r.get('model_name') or '', int(r.get('enabled') or 1), new_user['id']])
                except Exception:
                    pass
        flash('注册成功，请登录', 'success') # success category might not be styled in login.html but that's fine for now, we can check login.html
        return redirect(url_for('auth.login'))

    return render_template('register.html')

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        updates = []
        params = []
        
        if new_username and new_username != current_user.username:
            existing = query_one("select id from users where username = ?", [new_username])
            if existing:
                flash('用户名已存在', 'error')
                return redirect(url_for('auth.profile'))
            updates.append("username = ?")
            params.append(new_username)
            current_user.username = new_username # Update session user object
            
        if password:
            if password != confirm_password:
                flash('两次密码不一致', 'error')
                return redirect(url_for('auth.profile'))
            pwd_hash = generate_password_hash(password)
            updates.append("password_hash = ?")
            params.append(pwd_hash)
            
        if updates:
            params.append(current_user.id)
            execute_update(f"update users set {', '.join(updates)} where id = ?", params)
            flash('个人信息修改成功', 'success')
        else:
            flash('未做任何修改', 'info')
            
    return render_template('profile.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = query_one(
            "select u.*, r.name as role_name from users u join roles r on u.role_id = r.id where username = ?", 
            [username]
        )
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            if user_data.get('status') == 0:
                flash('账号已被冻结，请联系管理员', 'error')
                return render_template('login.html')
                
            user = User(
                user_data['id'], 
                user_data['username'], 
                user_data['role_id'], 
                user_data['role_name']
            )
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('用户名或密码错误', 'error')
            
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
