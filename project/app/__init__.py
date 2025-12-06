from flask import Flask
from flask_login import LoginManager
from flask_socketio import SocketIO
from .models import User
from werkzeug.security import generate_password_hash

socketio = SocketIO()
from .db import query_all, execute_update, get_connection, query_one
import os
import threading
import time
from pathlib import Path
from .crawler import fetch_items_for_keyword, save_items_for_keyword, run_crawler

def create_app():
    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.config['SECRET_KEY'] = 'dev-secret-key' # Change this in production

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    # Run migrations at startup (idempotent)
    try:
        def run_migrations():
            root = Path(__file__).resolve().parents[1]
            migrations_dir = root / "migrations"
            conn = get_connection()
            try:
                sql_files = sorted(migrations_dir.glob("*.sql"))
                for sql_file in sql_files:
                    try:
                        sql = sql_file.read_text(encoding='utf-8')
                        conn.executescript(sql)
                    except Exception:
                        pass
            finally:
                conn.close()
        run_migrations()
        # Seed roles and default admin user if not exists
        try:
            # roles
            roles = query_all("select * from roles")
            role_names = {r.get('name') for r in (roles or [])}
            if 'admin' not in (role_names or set()):
                execute_update("insert into roles(name, description) values(?, ?)", ['admin', 'Administrator'])
            if 'user' not in (role_names or set()):
                execute_update("insert into roles(name, description) values(?, ?)", ['user', 'Normal User'])
            # admin user
            admin_row = query_one("select id from users where username = ?", ['admin'])
            if not admin_row:
                admin_role = query_one("select id from roles where name = 'admin'")
                rid = admin_role and admin_role.get('id')
                pwd = generate_password_hash('123456')
                if rid:
                    execute_update("insert into users(username, password_hash, role_id) values(?, ?, ?)", ['admin', pwd, rid])
        except Exception:
            pass
    except Exception:
        pass

    from .views import bp as main_bp
    from .auth import bp as auth_bp
    from .admin import bp as admin_bp
    from .crawler import bp as crawler_bp
    from .chat import bp as chat_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(crawler_bp)
    app.register_blueprint(chat_bp)

    @app.context_processor
    def inject_settings():
        settings_list = query_all("select * from settings")
        settings_dict = {item['key']: item['value'] for item in settings_list}
        return dict(settings=settings_dict)

    def scheduler_loop():
        while True:
            try:
                rows = query_all("select * from sources where enabled = 1")
                for s in rows:
                    interval = s.get('interval_minutes') or 60
                    can_run = False
                    lr = s.get('last_run')
                    if not lr:
                        can_run = True
                    else:
                        try:
                            import datetime
                            last_dt = datetime.datetime.strptime(lr, "%Y-%m-%d %H:%M:%S")
                            diff = (datetime.datetime.utcnow() - last_dt).total_seconds()
                            if diff >= interval * 60:
                                can_run = True
                        except Exception:
                            can_run = True
                    if can_run:
                        cname = (s.get('crawler_name') or '').strip()
                        items = []
                        if cname:
                            items = run_crawler(cname, s['keyword'], 10)
                        else:
                            enabled_crawlers = query_all("select name from crawlers where enabled = 1")
                            if enabled_crawlers:
                                for c in enabled_crawlers:
                                    try:
                                        its = run_crawler(c.get('name'), s['keyword'], 10)
                                        save_items_for_keyword(s['keyword'], its)
                                    except Exception:
                                        continue
                            else:
                                items = fetch_items_for_keyword(s['keyword'])
                                save_items_for_keyword(s['keyword'], items)
                        execute_update("update sources set last_run = current_timestamp where id = ?", [s['id']])
                time.sleep(60)
            except Exception:
                time.sleep(60)

    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        t = threading.Thread(target=scheduler_loop, daemon=True)
        t.start()

    return app
