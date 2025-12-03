from flask import Flask
from flask_login import LoginManager
from .models import User
from .db import query_all

def create_app():
    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.config['SECRET_KEY'] = 'dev-secret-key' # Change this in production

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    from .views import bp as main_bp
    from .auth import bp as auth_bp
    from .admin import bp as admin_bp
    from .crawler import bp as crawler_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(crawler_bp)

    @app.context_processor
    def inject_settings():
        settings_list = query_all("select * from settings")
        settings_dict = {item['key']: item['value'] for item in settings_list}
        return dict(settings=settings_dict)

    return app
