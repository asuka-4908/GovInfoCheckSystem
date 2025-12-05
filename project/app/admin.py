from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from .db import query_all, execute_update, query_one
from .crawler import fetch_items_for_keyword, save_items_for_keyword
import requests
import json

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
    http_proxy = request.form.get('http_proxy')
    https_proxy = request.form.get('https_proxy')
    user_agent = request.form.get('user_agent')
    referer = request.form.get('referer')
    sec_ch_ua = request.form.get('sec_ch_ua')
    sec_ch_ua_platform = request.form.get('sec_ch_ua_platform')
    sec_ch_ua_mobile = request.form.get('sec_ch_ua_mobile')
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
    if http_proxy is not None:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['http_proxy', http_proxy]
        )
    if https_proxy is not None:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['https_proxy', https_proxy]
        )
    if user_agent is not None:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['user_agent', user_agent]
        )
    if referer is not None:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['referer', referer]
        )
    if sec_ch_ua is not None:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['sec_ch_ua', sec_ch_ua]
        )
    if sec_ch_ua_platform is not None:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['sec_ch_ua_platform', sec_ch_ua_platform]
        )
    if sec_ch_ua_mobile is not None:
        execute_update(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            ['sec_ch_ua_mobile', sec_ch_ua_mobile]
        )
    flash('设置已更新', 'success')
    return redirect(url_for('admin.settings'))

@bp.route('/crawls')
def crawl_list():
    rows = query_all("select id, keyword, title, source, url, created_at from crawl_records order by id desc limit 100")
    return render_template('admin/crawl_list.html', rows=rows)

@bp.route('/sources')
def source_list():
    sources = query_all("select * from sources order by id desc")
    crawlers = query_all("select * from crawlers order by id desc")
    return render_template('admin/source_list.html', sources=sources, crawlers=crawlers)

@bp.route('/sources/add', methods=['POST'])
def add_source():
    keyword = request.form.get('keyword')
    interval = request.form.get('interval_minutes', type=int)
    enabled = request.form.get('enabled', type=int)
    crawler_name = (request.form.get('crawler_name') or '').strip()
    if not keyword:
        return jsonify({'code': 1, 'msg': '关键字必填'})
    if not interval:
        interval = 60
    if enabled not in (0,1):
        enabled = 1
    execute_update("insert into sources(keyword, interval_minutes, enabled, crawler_name) values(?, ?, ?, ?)", [keyword, interval, enabled, crawler_name])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.route('/sources/toggle/<int:source_id>', methods=['POST'])
def toggle_source(source_id):
    row = query_one("select enabled from sources where id = ?", [source_id])
    if not row:
        return jsonify({'code': 1, 'msg': '未找到'})
    new_val = 0 if row['enabled'] == 1 else 1
    execute_update("update sources set enabled = ? where id = ?", [new_val, source_id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.route('/sources/delete/<int:source_id>', methods=['POST'])
def delete_source(source_id):
    execute_update("delete from sources where id = ?", [source_id])
    return jsonify({'code': 0, 'msg': '删除成功'})

@bp.route('/sources/update/<int:source_id>', methods=['POST'])
def update_source(source_id):
    crawler_name = (request.form.get('crawler_name') or '').strip()
    interval = request.form.get('interval_minutes', type=int)
    sets = []
    params = []
    if crawler_name is not None:
        sets.append('crawler_name = ?')
        params.append(crawler_name)
    if interval is not None:
        sets.append('interval_minutes = ?')
        params.append(interval)
    if not sets:
        return jsonify({'code': 1, 'msg': '无更新内容'})
    params.append(source_id)
    execute_update(f"update sources set {', '.join(sets)} where id = ?", params)
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.route('/sources/run/<int:source_id>', methods=['POST'])
def run_source(source_id):
    src = query_one("select * from sources where id = ?", [source_id])
    if not src:
        return jsonify({'code': 1, 'msg': '未找到'})
    from .crawler import run_crawler
    cname = (src.get('crawler_name') or '').strip()
    items = []
    if cname:
        items = run_crawler(cname, src['keyword'], 10)
    else:
        items = fetch_items_for_keyword(src['keyword'])
    save_items_for_keyword(src['keyword'], items)
    execute_update("update sources set last_run = current_timestamp where id = ?", [source_id])
    return jsonify({'code': 0, 'msg': '采集完成', 'count': len(items)})

@bp.route('/crawl/manage')
def crawl_manage():
    execute_update("create table if not exists crawlers(\n        id integer primary key autoincrement,\n        name text unique not null,\n        module text,\n        callable text,\n        config text,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n    )")
    crawlers = query_all("select * from crawlers where enabled = 1 order by id desc")
    return render_template('admin/crawl_manage.html', crawlers=crawlers)

@bp.route('/crawlers')
def crawlers():
    execute_update("create table if not exists crawlers(\n        id integer primary key autoincrement,\n        name text unique not null,\n        module text,\n        callable text,\n        config text,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n    )")
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        rows = query_all("select * from crawlers where name like ? or module like ? or callable like ? order by id desc", [f"%{q}%", f"%{q}%", f"%{q}%"]) 
    else:
        rows = query_all("select * from crawlers order by id desc")
    return render_template('admin/crawlers.html', rows=rows, q=q)

@bp.post('/crawlers/add')
def crawlers_add():
    name = (request.form.get('name') or '').strip()
    module = (request.form.get('module') or '').strip()
    callable_name = (request.form.get('callable') or '').strip()
    config = request.form.get('config') or ''
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    if not name:
        return jsonify({'code': 1, 'msg': '名称必填'})
    execute_update("insert into crawlers(name, module, callable, config, enabled) values(?, ?, ?, ?, ?)", [name, module, callable_name, config, en])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.post('/crawlers/update/<int:crawler_id>')
def crawlers_update(crawler_id: int):
    name = (request.form.get('name') or '').strip()
    module = (request.form.get('module') or '').strip()
    callable_name = (request.form.get('callable') or '').strip()
    config = request.form.get('config') or ''
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    execute_update("update crawlers set name=?, module=?, callable=?, config=?, enabled=? where id=?", [name, module, callable_name, config, en, crawler_id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/crawlers/delete/<int:crawler_id>')
def crawlers_delete(crawler_id: int):
    execute_update("delete from crawlers where id = ?", [crawler_id])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.route('/warehouse')
def warehouse():
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        rows = query_all("select id, keyword, title, summary, cover, url, source, created_at from crawl_records where title like ? or summary like ? or keyword like ? order by id asc limit 200", [f"%{q}%", f"%{q}%", f"%{q}%"])
    else:
        rows = query_all("select id, keyword, title, summary, cover, url, source, created_at from crawl_records order by id asc limit 200")
    return render_template('admin/warehouse.html', rows=rows, q=q)

@bp.post('/warehouse/update/<int:rid>')
def warehouse_update(rid: int):
    title = request.form.get('title')
    summary = request.form.get('summary')
    cover = request.form.get('cover')
    url = request.form.get('url')
    source = request.form.get('source')
    keyword = request.form.get('keyword')
    execute_update("update crawl_records set title=?, summary=?, cover=?, url=?, source=?, keyword=? where id=?", [title or '', summary or '', cover or '', url or '', source or '', keyword or '', rid])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/warehouse/delete/<int:rid>')
def warehouse_delete(rid: int):
    execute_update("delete from crawl_details where record_id = ?", [rid])
    execute_update("delete from crawl_records where id = ?", [rid])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.get('/warehouse/detail/<int:rid>')
def warehouse_detail(rid: int):
    detail = query_one("select content_text, content_html from crawl_details where record_id = ? order by id desc limit 1", [rid])
    return jsonify({'code': 0, 'detail': detail or {}})

@bp.post('/warehouse/analyze/<int:rid>')
def warehouse_analyze(rid: int):
    detail = query_one("select content_text from crawl_details where record_id = ? order by id desc limit 1", [rid])
    rec = query_one("select title, summary from crawl_records where id = ?", [rid])
    content_text = (detail and detail.get('content_text')) or (rec and rec.get('summary')) or ''
    if not content_text:
        return jsonify({'code': 1, 'msg': '暂无可解析内容，请先进行详细采集'})
    eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if not eng:
        return jsonify({'code': 1, 'msg': '请先在AI引擎管理中配置并启用引擎'})
    api_url = (eng.get('api_url') or '').rstrip('/')
    model = eng.get('model_name') or ''
    headers = {
        'Authorization': f"Bearer {eng.get('api_key')}",
        'Content-Type': 'application/json'
    }
    messages = [
        {"role": "system", "content": "你是政府信息审查系统的AI助手。请用中文在200字以内概括要点，提取关键信息，输出纯文本摘要。"},
        {"role": "user", "content": content_text[:12000]}
    ]
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    try:
        resp = requests.post(f"{api_url}/v1/chat/completions", headers=headers, json=payload, timeout=20)
        data = resp.json()
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                summary = data['choices'][0]['message']['content']
            except Exception:
                summary = ''
        else:
            summary = ''
    except Exception:
        summary = ''
    if not summary:
        return jsonify({'code': 1, 'msg': '解析失败或无结果'})
    return jsonify({'code': 0, 'summary': summary})

@bp.post('/warehouse/save_detail/<int:rid>')
def warehouse_save_detail(rid: int):
    title = request.form.get('title')
    content_text = request.form.get('content_text') or ''
    content_html = request.form.get('content_html') or ''
    if title:
        execute_update("update crawl_records set title=? where id=?", [title, rid])
    execute_update("insert into crawl_details(record_id, url, content_text, content_html) select id, url, ?, ? from crawl_records where id=?", [content_text, content_html, rid])
    return jsonify({'code': 0, 'msg': 'ok'})

@bp.post('/warehouse/update_summary/<int:rid>')
def warehouse_update_summary(rid: int):
    summary = request.form.get('summary') or ''
    execute_update("update crawl_records set summary=? where id=?", [summary, rid])
    return jsonify({'code': 0, 'msg': '已更新摘要'})

# 采集规则库
@bp.route('/rules')
def rules():
    execute_update("create table if not exists crawl_rules(\n        id integer primary key autoincrement,\n        site text not null,\n        title_xpath text,\n        content_xpath text,\n        request_headers text,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n    )")
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        rows = query_all("select * from crawl_rules where site like ? order by id asc", [f"%{q}%"])
    else:
        rows = query_all("select * from crawl_rules order by id asc")
    return render_template('admin/rules.html', rows=rows, q=q)

@bp.post('/rules/add')
def rules_add():
    site = (request.form.get('site') or '').strip()
    title_xpath = request.form.get('title_xpath') or ''
    content_xpath = request.form.get('content_xpath') or ''
    request_headers = request.form.get('request_headers') or ''
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    if not site:
        return jsonify({'code': 1, 'msg': '站点必填'})
    if request_headers:
        try:
            obj = json.loads(request_headers)
            if isinstance(obj, dict):
                request_headers = json.dumps(obj, ensure_ascii=False)
            else:
                request_headers = json.dumps({}, ensure_ascii=False)
        except Exception:
            lines = request_headers.splitlines()
            hdrs = {}
            i = 0
            while i < len(lines):
                k = (lines[i] or '').strip()
                if not k:
                    i += 1
                    continue
                v = ''
                if ':' in k:
                    parts = k.split(':', 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if not val and i + 1 < len(lines):
                        i += 1
                        val = (lines[i] or '').strip()
                    v = val.strip().strip('"\'`')
                    hdrs[key] = v
                    i += 1
                    continue
                key = k
                j = i + 1
                val2 = ''
                while j < len(lines):
                    t = (lines[j] or '').strip()
                    j += 1
                    if t:
                        val2 = t
                        break
                v = val2.strip().strip('"\'`')
                hdrs[key] = v
                i = j
            request_headers = json.dumps(hdrs, ensure_ascii=False)
    execute_update("insert into crawl_rules(site, title_xpath, content_xpath, request_headers, enabled) values(?, ?, ?, ?, ?)", [site, title_xpath, content_xpath, request_headers, en])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.post('/rules/update/<int:rule_id>')
def rules_update(rule_id: int):
    site = (request.form.get('site') or '').strip()
    title_xpath = request.form.get('title_xpath') or ''
    content_xpath = request.form.get('content_xpath') or ''
    request_headers = request.form.get('request_headers') or ''
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    if request_headers:
        try:
            obj = json.loads(request_headers)
            if isinstance(obj, dict):
                request_headers = json.dumps(obj, ensure_ascii=False)
            else:
                request_headers = json.dumps({}, ensure_ascii=False)
        except Exception:
            lines = request_headers.splitlines()
            hdrs = {}
            i = 0
            while i < len(lines):
                k = (lines[i] or '').strip()
                if not k:
                    i += 1
                    continue
                v = ''
                if ':' in k:
                    parts = k.split(':', 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if not val and i + 1 < len(lines):
                        i += 1
                        val = (lines[i] or '').strip()
                    v = val.strip().strip('"\'`')
                    hdrs[key] = v
                    i += 1
                    continue
                key = k
                j = i + 1
                val2 = ''
                while j < len(lines):
                    t = (lines[j] or '').strip()
                    j += 1
                    if t:
                        val2 = t
                        break
                v = val2.strip().strip('"\'`')
                hdrs[key] = v
                i = j
            request_headers = json.dumps(hdrs, ensure_ascii=False)
    execute_update("update crawl_rules set site=?, title_xpath=?, content_xpath=?, request_headers=?, enabled=? where id=?", [site, title_xpath, content_xpath, request_headers, en, rule_id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/rules/delete/<int:rule_id>')
def rules_delete(rule_id: int):
    execute_update("delete from crawl_rules where id = ?", [rule_id])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.route('/ai_engines')
def ai_engines():
    execute_update("create table if not exists ai_engines(\n        id integer primary key autoincrement,\n        provider_name text not null,\n        api_url text not null,\n        api_key text not null,\n        model_name text not null,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n    )")
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        rows = query_all("select * from ai_engines where provider_name like ? or model_name like ? order by id desc", [f"%{q}%", f"%{q}%"])
    else:
        rows = query_all("select * from ai_engines order by id desc")
    return render_template('admin/ai_engines.html', rows=rows, q=q)

@bp.post('/ai_engines/add')
def ai_engines_add():
    provider_name = (request.form.get('provider_name') or '').strip()
    api_url = (request.form.get('api_url') or '').strip()
    api_key = request.form.get('api_key') or ''
    model_name = (request.form.get('model_name') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    if not provider_name or not api_url or not api_key or not model_name:
        return jsonify({'code': 1, 'msg': '参数不全'})
    execute_update("insert into ai_engines(provider_name, api_url, api_key, model_name, enabled) values(?, ?, ?, ?, ?)", [provider_name, api_url, api_key, model_name, en])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.post('/ai_engines/update/<int:engine_id>')
def ai_engines_update(engine_id: int):
    provider_name = (request.form.get('provider_name') or '').strip()
    api_url = (request.form.get('api_url') or '').strip()
    api_key = request.form.get('api_key') or ''
    model_name = (request.form.get('model_name') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    execute_update("update ai_engines set provider_name=?, api_url=?, api_key=?, model_name=?, enabled=? where id=?", [provider_name, api_url, api_key, model_name, en, engine_id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/ai_engines/delete/<int:engine_id>')
def ai_engines_delete(engine_id: int):
    execute_update("delete from ai_engines where id = ?", [engine_id])
    return jsonify({'code': 0, 'msg': '已删除'})
