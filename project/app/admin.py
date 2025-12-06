from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, Response
from flask import stream_with_context
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from .db import query_all, execute_update, query_one
from .menu_service import list_menus, update_menu as menu_update, move_menu, ensure_table as ensure_menu_table, reorder_group
from .crawler import fetch_items_for_keyword, save_items_for_keyword
import requests
import json
import urllib.parse
import time
import re

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
        flash('参数不全', 'error')
        return redirect(url_for('admin.user_list'))
        
    existing = query_one("select id from users where username = ?", [username])
    if existing:
        flash('用户已存在', 'error')
        return redirect(url_for('admin.user_list'))
        
    pwd_hash = generate_password_hash(password)
    execute_update(
        "insert into users(username, password_hash, role_id) values(?, ?, ?)",
        [username, pwd_hash, role_id]
    )
    flash('添加成功', 'success')
    return redirect(url_for('admin.user_list'))

@bp.route('/users/update/<int:user_id>', methods=['POST'])
def update_user(user_id):
    role_id = request.form.get('role_id')
    password = request.form.get('password')
    if not role_id and not password:
        flash('无更新内容', 'error')
        return redirect(url_for('admin.user_list'))
    if role_id:
        execute_update("update users set role_id = ? where id = ?", [role_id, user_id])
    if password:
        pwd_hash = generate_password_hash(password)
        execute_update("update users set password_hash = ? where id = ?", [pwd_hash, user_id])
    flash('更新成功', 'success')
    return redirect(url_for('admin.user_list'))

@bp.route('/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    execute_update("delete from users where id = ?", [user_id])
    flash('删除成功', 'success')
    return redirect(url_for('admin.user_list'))

@bp.route('/users/toggle_status/<int:user_id>', methods=['POST'])
def toggle_user_status(user_id):
    row = query_one("select status from users where id = ?", [user_id])
    if not row:
        flash('用户不存在', 'error')
        return redirect(url_for('admin.user_list'))
    cur = row.get('status')
    cur = 1 if cur is None else int(cur)
    new_val = 0 if cur == 1 else 1
    execute_update("update users set status = ? where id = ?", [new_val, user_id])
    flash('已冻结' if new_val == 0 else '已解冻', 'success')
    return redirect(url_for('admin.user_list'))

@bp.route('/roles')
def role_list():
    roles = query_all("select * from roles")
    return render_template('admin/role_list.html', roles=roles)

@bp.route('/roles/add', methods=['POST'])
def add_role():
    name = request.form.get('name')
    description = request.form.get('description')
    if not name:
        flash('名称必填', 'error')
        return redirect(url_for('admin.role_list'))
    existing = query_one("select id from roles where name = ?", [name])
    if existing:
        flash('角色已存在', 'error')
        return redirect(url_for('admin.role_list'))
    execute_update("insert into roles(name, description) values(?, ?)", [name, description])
    flash('添加成功', 'success')
    return redirect(url_for('admin.role_list'))

@bp.route('/roles/delete/<int:role_id>', methods=['POST'])
def delete_role(role_id):
    in_use = query_one("select 1 from users where role_id = ?", [role_id])
    if in_use:
        flash('角色正在使用，无法删除', 'error')
        return redirect(url_for('admin.role_list'))
    execute_update("delete from roles where id = ?", [role_id])
    flash('删除成功', 'success')
    return redirect(url_for('admin.role_list'))

# 系统设置功能已移除

@bp.route('/crawls')
def crawl_list():
    rows = query_all("select id, keyword, title, source, url, created_at from crawl_records order by id desc limit 100")
    return render_template('admin/crawl_list.html', rows=rows)

@bp.route('/sources')
def source_list():
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(sources)")]
    except Exception:
        cols = []
    if 'industry' not in cols:
        try:
            execute_update("alter table sources add column industry text")
        except Exception:
            pass
    sources = query_all("select * from sources order by id desc")
    crawlers = query_all("select * from crawlers order by id desc")
    return render_template('admin/source_list.html', sources=sources, crawlers=crawlers)

@bp.route('/sources/add', methods=['POST'])
def add_source():
    keyword = request.form.get('keyword')
    interval = request.form.get('interval_minutes', type=int)
    enabled = request.form.get('enabled', type=int)
    crawler_name = (request.form.get('crawler_name') or '').strip()
    industry_raw = (request.form.get('industry') or '').strip()
    industry_custom = (request.form.get('industry_custom') or '').strip()
    industry = industry_custom or industry_raw
    if not keyword:
        return jsonify({'code': 1, 'msg': '关键字必填'})
    if not interval:
        interval = 60
    if enabled not in (0,1):
        enabled = 1
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(sources)")]
    except Exception:
        cols = []
    if 'industry' in cols:
        execute_update("insert into sources(keyword, interval_minutes, enabled, crawler_name, industry) values(?, ?, ?, ?, ?)", [keyword, interval, enabled, crawler_name, industry])
    else:
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
    industry_raw = request.form.get('industry')
    industry_custom = request.form.get('industry_custom')
    industry = (industry_custom if (industry_custom is not None and industry_custom.strip()) else industry_raw)
    sets = []
    params = []
    if crawler_name is not None:
        sets.append('crawler_name = ?')
        params.append(crawler_name)
    if interval is not None:
        sets.append('interval_minutes = ?')
        params.append(interval)
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(sources)")]
    except Exception:
        cols = []
    if ('industry' in cols) and (industry is not None):
        sets.append('industry = ?')
        params.append((industry or '').strip())
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
    execute_update("create table if not exists crawlers(\n        id integer primary key autoincrement,\n        name text unique not null,\n        module text,\n        callable text,\n        config text,\n        domain text,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n     )")
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawlers)")]
        if 'domain' not in cols:
            execute_update("alter table crawlers add column domain text")
    except Exception:
        pass
    crawlers = query_all("select * from crawlers where enabled = 1 order by id asc")
    return render_template('admin/crawl_manage.html', crawlers=crawlers)

@bp.post('/crawlers/test/<int:crawler_id>')
def crawlers_test(crawler_id: int):
    row = query_one("select * from crawlers where id = ?", [crawler_id])
    if not row:
        return jsonify({'code': 1, 'msg': '未找到爬虫'})
    keyword = (request.form.get('keyword') or '').strip()
    count = request.form.get('count', type=int) or 10
    if not keyword:
        return jsonify({'code': 1, 'msg': '请输入测试关键字'})
    try:
        from .crawler import run_crawler
        name = (row.get('name') or row.get('domain') or '').strip()
        items = run_crawler(name, keyword, count)
        return jsonify({'code': 0, 'items': items})
    except Exception as e:
        return jsonify({'code': 1, 'msg': str(e)})

@bp.route('/data_board')
def data_board():
    from flask import url_for
    latest_url = url_for('admin.data_board_latest')
    heatmap_url = url_for('admin.data_board_heatmap')
    return render_template('admin/data_board.html', latest_url=latest_url, heatmap_url=heatmap_url)

@bp.get('/data_board/latest')
def data_board_latest():
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    try:
        if 'user_id' in cols:
            rows = query_all(
                "select id, title, source, keyword, url, created_at from crawl_records where user_id is null or user_id = ? order by datetime(created_at) desc limit 20",
                [current_user.id]
            )
        else:
            rows = query_all("select id, title, source, keyword, url, created_at from crawl_records order by datetime(created_at) desc limit 20")
    except Exception:
        rows = []
    return jsonify({'code': 0, 'rows': rows})

@bp.get('/data_board/heatmap')
def data_board_heatmap():
    def simple_heat(rows):
        provinces = [
            '北京','上海','天津','重庆','河北','山西','内蒙古','辽宁','吉林','黑龙江','江苏','浙江','安徽','福建','江西','山东','河南','湖北','湖南','广东','广西','海南','四川','贵州','云南','西藏','陕西','甘肃','青海','宁夏','新疆'
        ]
        p_counts = {p: 0 for p in provinces}
        p_words = {p: {} for p in provinces}
        s_counts = {}
        for r in rows or []:
            text = ((r.get('title') or '') + ' ' + (r.get('summary') or '')).strip()
            kw = (r.get('keyword') or '').strip()
            src = (r.get('source') or '未知').strip()
            s_counts[src] = s_counts.get(src, 0) + 1
            hit = []
            for p in provinces:
                if p and (p in text):
                    hit.append(p)
            if not hit:
                continue
            for p in set(hit):
                p_counts[p] = p_counts.get(p, 0) + 1
                if kw:
                    d = p_words.get(p) or {}
                    d[kw] = (d.get(kw) or 0) + 1
                    p_words[p] = d
        map_data = []
        for p in provinces:
            v = p_counts.get(p) or 0
            if v > 0:
                map_data.append({'name': p, 'value': int(v)})
        top_words = []
        for p in provinces:
            wmap = p_words.get(p) or {}
            if not wmap:
                continue
            arr = sorted([{'word': k, 'count': int(v)} for k, v in wmap.items()], key=lambda x: x['count'], reverse=True)[:5]
            top_words.append({'region': p, 'words': arr})
        sources = [{'name': k, 'value': v} for k, v in s_counts.items()]
        sources.sort(key=lambda x: x['value'], reverse=True)
        return {'map': map_data, 'topWords': top_words, 'sources': sources[:10]}
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    try:
        if 'user_id' in cols:
            rows = query_all(
                "select id, title, summary, source, keyword, url, created_at from crawl_records where user_id is null or user_id = ? order by datetime(created_at) desc limit 500",
                [current_user.id]
            )
        else:
            rows = query_all("select id, title, summary, source, keyword, url, created_at from crawl_records order by datetime(created_at) desc limit 500")
    except Exception:
        rows = []
    
    # Calculate sources using Python logic always, to ensure data availability
    base_stats = simple_heat(rows)
    final_map = base_stats.get('map') or []
    final_words = base_stats.get('topWords') or []
    final_sources = base_stats.get('sources') or []

    eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if eng:
        # AI logic for map/words ONLY if we want AI to refine it. 
        # But for now, let's stick to the Python implementation for reliability unless user specifically asks AI to *generate* data.
        # The existing code tried to use AI. I will keep it but make it optional/fallback or merge.
        # Actually, the user wants AI analysis. The map data is better off being exact from DB.
        # So I will prioritize the Python calculation for map/sources, and use AI for the "analysis" text route.
        # However, to preserve existing AI logic if it was working:
        pass 
        # (I will skip the AI map generation part to make the dashboard faster and more accurate based on actual data)

    return jsonify({'code': 0, 'map': final_map, 'topWords': final_words, 'sources': final_sources})

@bp.post('/data_board/analyze')
def data_board_analyze():
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    try:
        if 'user_id' in cols:
            rows = query_all(
                "select title, summary, source, keyword, created_at from crawl_records where user_id is null or user_id = ? order by datetime(created_at) desc limit 50",
                [current_user.id]
            )
        else:
            rows = query_all("select title, summary, source, keyword, created_at from crawl_records order by datetime(created_at) desc limit 50")
    except Exception:
        rows = []
    if not rows:
        return jsonify({'code': 1, 'msg': '无数据'})
    
    eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if not eng:
        return jsonify({'code': 1, 'msg': '请先配置AI引擎'})
        
    api_url = (eng.get('api_url') or '').strip().rstrip('/')
    model = eng.get('model_name') or ''
    headers = {'Authorization': f"Bearer {(eng.get('api_key') or '').strip()}", 'Content-Type': 'application/json'}
    chat_url = api_url + ('/chat/completions' if api_url.endswith('/v1') else '/v1/chat/completions')
    
    txt = "\n".join([f"{r['created_at']} [{r['source']}] {r['title']}" for r in rows])
    sys_msg = "你是政务数据分析师。请根据以下最近采集的新闻数据，生成一份简短的分析报告（300字以内），涵盖热点话题、舆情趋势和重点关注区域。"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": txt}
        ],
        "temperature": 0.7
    }
    
    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            d = resp.json()
            content = d.get('choices', [{}])[0].get('message', {}).get('content') or ''
            return jsonify({'code': 0, 'data': content})
        return jsonify({'code': 1, 'msg': f'AI请求失败: {resp.status_code}'})
    except Exception as e:
        return jsonify({'code': 1, 'msg': str(e)})

@bp.route('/crawlers')
def crawlers():
    execute_update("create table if not exists crawlers(\n        id integer primary key autoincrement,\n        name text unique not null,\n        module text,\n        callable text,\n        config text,\n        domain text,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n     )")
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawlers)")]
        if 'domain' not in cols:
            execute_update("alter table crawlers add column domain text")
    except Exception:
        pass
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        rows = query_all("select * from crawlers where name like ? or domain like ? or config like ? order by id asc", [f"%{q}%", f"%{q}%", f"%{q}%"]) 
    else:
        rows = query_all("select * from crawlers order by id asc")
    return render_template('admin/crawlers.html', rows=rows, q=q)

@bp.post('/crawlers/add')
def crawlers_add():
    name = (request.form.get('name') or '').strip()
    module = (request.form.get('module') or '').strip()
    callable_name = (request.form.get('callable') or '').strip()
    config = request.form.get('config') or ''
    domain = (request.form.get('domain') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    if not name:
        return jsonify({'code': 1, 'msg': '名称必填'})
    execute_update("insert into crawlers(name, module, callable, config, domain, enabled) values(?, ?, ?, ?, ?, ?)", [name, module, callable_name, config, domain, en])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.post('/crawlers/update/<int:crawler_id>')
def crawlers_update(crawler_id: int):
    name = (request.form.get('name') or '').strip()
    module = (request.form.get('module') or '').strip()
    callable_name = (request.form.get('callable') or '').strip()
    config = request.form.get('config') or ''
    domain = (request.form.get('domain') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 1
    execute_update("update crawlers set name=?, module=?, callable=?, config=?, domain=?, enabled=? where id=?", [name, module, callable_name, config, domain, en, crawler_id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/crawlers/delete/<int:crawler_id>')
def crawlers_delete(crawler_id: int):
    execute_update("delete from crawlers where id = ?", [crawler_id])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.post('/crawlers/toggle/<int:crawler_id>')
def crawlers_toggle(crawler_id: int):
    row = query_one("select enabled from crawlers where id = ?", [crawler_id])
    if not row:
        return jsonify({'code': 1, 'msg': '未找到'})
    new_val = 0 if row['enabled'] == 1 else 1
    execute_update("update crawlers set enabled = ? where id = ?", [new_val, crawler_id])
    return jsonify({'code': 0, 'msg': '已更新', 'enabled': new_val})

@bp.post('/crawlers/auto_rule')
def crawlers_auto_rule():
    test_url = (request.form.get('test_url') or '').strip()
    request_headers = (request.form.get('request_headers') or '').strip()
    if not test_url:
        return jsonify({'code': 1, 'msg': '缺少测试URL'})
    site = ''
    try:
        pu = urllib.parse.urlparse(test_url)
        site = (pu.netloc or '').lower()
    except Exception:
        site = ''
    if not site:
        return jsonify({'code': 1, 'msg': 'URL无效'})
    hdrs = {}
    if request_headers:
        try:
            obj = json.loads(request_headers)
            if isinstance(obj, dict):
                hdrs = {str(k): str(v) for k, v in obj.items() if v is not None}
        except Exception:
            lines = request_headers.splitlines()
            i = 0
            while i < len(lines):
                k = (lines[i] or '').strip()
                i += 1
                if not k:
                    continue
                if ':' in k:
                    parts = k.split(':', 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    hdrs[key] = val
                else:
                    # next non-empty line as value
                    j = i
                    val2 = ''
                    while j < len(lines):
                        t = (lines[j] or '').strip()
                        j += 1
                        if t:
                            val2 = t
                            break
                    hdrs[k] = val2
                    i = j
    try:
        settings = {s['key']: s['value'] for s in query_all("select * from settings")}
        proxies = {}
        if settings.get('http_proxy'):
            proxies['http'] = settings['http_proxy']
        if settings.get('https_proxy'):
            proxies['https'] = settings['https_proxy']
        ua = settings.get('user_agent') or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
        headers = {'user-agent': ua, 'accept-language': 'zh-CN,zh;q=0.9'}
        for k, v in hdrs.items():
            headers[str(k)] = str(v)
        r = requests.get(test_url, headers=headers, timeout=10, proxies=proxies or None, allow_redirects=True)
        raw = r.content
        enc = r.encoding or r.apparent_encoding or 'utf-8'
        html = None
        for candidate in [enc, 'utf-8', 'gbk', 'gb2312', 'big5']:
            try:
                html = raw.decode(candidate, errors='ignore')
                break
            except Exception:
                continue
        if html is None:
            html = raw.decode('utf-8', errors='ignore')
        title_xpath = ''
        content_xpath = ''
        try:
            from lxml import html as lhtml
            import lxml.html
            doc = lhtml.fromstring(html)
            # title detect
            tn2 = doc.xpath('//h1')
            if tn2:
                title_xpath = '//h1'
            # content detect candidates
            candidates = [
                "//article",
                "//div[@id='content']",
                "//div[contains(@class,'content')]",
                "//div[contains(@class,'article')]",
                "//div[contains(@class,'news')]",
                "//div[contains(@class,'main')]"
            ]
            for xp in candidates:
                cn2 = doc.xpath(xp)
                if not cn2:
                    continue
                txt2 = '\n'.join([c if isinstance(c, str) else (getattr(c, 'text_content', lambda: '')() or '').strip() for c in cn2 if c is not None])
                if len(txt2) >= 200:
                    content_xpath = xp
                    break
        except Exception:
            pass
        # only upsert into crawlers for management visibility; do NOT write into crawl_rules
        req_hdrs_json = json.dumps(hdrs, ensure_ascii=False) if hdrs else json.dumps({}, ensure_ascii=False)
        # derive friendly name from domain (2nd-level), excluding common subdomains
        parts = (site or '').split('.')
        friendly = ''
        if len(parts) >= 2:
            token = parts[-2]
            if token.lower() in ('www','news') and len(parts) >= 3:
                token = parts[-3]
            friendly = token.lower()
        else:
            friendly = site
        execute_update(
            "insert into crawlers(name, module, callable, config, domain, enabled) values(?, '', '', ?, ?, 1) on conflict(name) do update set config=excluded.config, domain=excluded.domain, enabled=excluded.enabled",
            [friendly or site, req_hdrs_json, site]
        )
        return jsonify({'code': 0, 'msg': '爬虫已更新', 'crawler': {'name': friendly or site, 'domain': site}})
    except Exception as e:
        return jsonify({'code': 1, 'msg': str(e)})

@bp.route('/warehouse')
def warehouse():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', type=int) or 1
    page_size = request.args.get('page_size', type=int) or 10
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 200:
        page_size = 200
    params = []
    where = ''
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    if q:
        where = " where title like ? or summary like ? or keyword like ?"
        params = [f"%{q}%", f"%{q}%", f"%{q}%"]
    if 'user_id' in cols:
        where = ((' where ' in where) and (where + " and user_id is null")) or " where user_id is null"
    total_row = query_one(f"select count(*) as cnt from crawl_records{where}", params)
    total = (total_row and total_row.get('cnt')) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    if page > pages:
        page = pages
    offset = (page - 1) * page_size
    rows = query_all(f"select id, keyword, title, summary, cover, url, source, created_at from crawl_records{where} order by id asc limit ? offset ?", params + [page_size, offset])
    return render_template('admin/warehouse.html', rows=rows, q=q, page=page, page_size=page_size, total=total, pages=pages)

@bp.post('/warehouse/update/<int:rid>')
def warehouse_update(rid: int):
    title = request.form.get('title')
    summary = request.form.get('summary')
    cover = request.form.get('cover')
    url = request.form.get('url')
    source = request.form.get('source')
    keyword = request.form.get('keyword')
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    if 'user_id' in cols:
        row = query_one("select user_id from crawl_records where id = ?", [rid])
        if row and (row.get('user_id') is not None):
            return jsonify({'code': 1, 'msg': '仅能编辑系统仓库数据'})
    execute_update("update crawl_records set title=?, summary=?, cover=?, url=?, source=?, keyword=? where id=?", [title or '', summary or '', cover or '', url or '', source or '', keyword or '', rid])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/warehouse/delete/<int:rid>')
def warehouse_delete(rid: int):
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    if 'user_id' in cols:
        row = query_one("select user_id from crawl_records where id = ?", [rid])
        if row and (row.get('user_id') is not None):
            return jsonify({'code': 1, 'msg': '仅能删除系统仓库数据'})
    execute_update("delete from crawl_details where record_id = ?", [rid])
    execute_update("delete from crawl_records where id = ?", [rid])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.post('/warehouse/batch_delete')
def warehouse_batch_delete():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 1, 'msg': '缺少ID列表'})
    cnt = 0
    for rid in ids:
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
        except Exception:
            cols = []
        try:
            if 'user_id' in cols:
                row = query_one("select user_id from crawl_records where id = ?", [rid])
                if row and (row.get('user_id') is not None):
                    continue
            execute_update("delete from crawl_details where record_id = ?", [rid])
            execute_update("delete from crawl_records where id = ?", [rid])
            cnt += 1
        except Exception:
            pass
    return jsonify({'code': 0, 'msg': '已批量删除', 'count': cnt})

@bp.post('/warehouse/batch_collect')
def warehouse_batch_collect():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 1, 'msg': '缺少ID列表'})
    import requests as _req
    cnt = 0
    for rid in ids:
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
        except Exception:
            cols = []
        try:
            qsql = "select url, source from crawl_records where id = ?"
            if 'user_id' in cols:
                qsql = qsql + " and user_id is null"
            rec = query_one(qsql, [rid])
            if not rec or not rec.get('url'):
                continue
            payload = {'url': rec.get('url'), 'source': rec.get('source') or ''}
            try:
                r = _req.post('http://127.0.0.1:5000/api/deep_crawl', json=payload, timeout=20)
                j = r.json()
            except Exception:
                j = {'code': 1, 'msg': '采集失败'}
            if isinstance(j, dict) and j.get('code') == 0:
                content_text = j.get('content_text') or ''
                content_html = j.get('content_html') or ''
                title = j.get('title') or ''
                if title:
                    try:
                        execute_update("update crawl_records set title=? where id=?", [title, rid])
                    except Exception:
                        pass
                if content_text or content_html:
                    sql_ins = "insert into crawl_details(record_id, url, content_text, content_html) select id, url, ?, ? from crawl_records where id=?"
                    if 'user_id' in cols:
                        sql_ins = sql_ins + " and user_id is null"
                    execute_update(sql_ins, [content_text, content_html, rid])
                    cnt += 1
        except Exception:
            pass
    return jsonify({'code': 0, 'msg': '已批量采集', 'count': cnt})

@bp.get('/warehouse/detail/<int:rid>')
def warehouse_detail(rid: int):
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    if 'user_id' in cols:
        row = query_one("select user_id from crawl_records where id = ?", [rid])
        if row and (row.get('user_id') is not None):
            return jsonify({'code': 1, 'msg': '仅能查看系统仓库数据'})
    detail = query_one("select content_text, content_html from crawl_details where record_id = ? order by id desc limit 1", [rid])
    return jsonify({'code': 0, 'detail': detail or {}})

@bp.post('/warehouse/analyze/<int:rid>')
def warehouse_analyze(rid: int):
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    qsql = "select content_text from crawl_details where record_id = ? order by id desc limit 1"
    rsql = "select title, summary from crawl_records where id = ?"
    if 'user_id' in cols:
        row = query_one("select user_id from crawl_records where id = ?", [rid])
        if row and (row.get('user_id') is not None):
            return jsonify({'code': 1, 'msg': '仅能解析系统仓库数据'})
    detail = query_one(qsql, [rid])
    rec = query_one(rsql, [rid])
    content_text = (detail and detail.get('content_text')) or (rec and rec.get('summary')) or ''
    if not content_text:
        return jsonify({'code': 1, 'msg': '暂无可解析内容，请先进行详细采集'})
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
    except Exception:
        cols = []
    if 'user_id' in cols:
        eng = query_one("select * from ai_engines where enabled = 1 and user_id is null order by id desc limit 1")
        if not eng:
            eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    else:
        eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if not eng:
        return jsonify({'code': 1, 'msg': '请先在AI引擎管理中配置并启用引擎'})
    api_url = (eng.get('api_url') or '').strip().rstrip('/')
    model = (eng.get('model_name') or '').strip()
    headers = {
        'Authorization': f"Bearer {(eng.get('api_key') or '').strip()}",
        'Content-Type': 'application/json'
    }
    chat_url = api_url + ('/chat/completions' if api_url.endswith('/v1') else '/v1/chat/completions')
    messages = [
        {"role": "system", "content": "你是政府信息审查系统的AI助手。请用中文在200字以内概括要点，提取关键信息，输出纯文本摘要。"},
        {"role": "user", "content": content_text[:12000]}
    ]
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=20)
        data = resp.json()
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                summary = data['choices'][0]['message']['content']
            except Exception:
                summary = ''
        else:
            summary = ''
    except Exception as e:
        summary = ''
    if not summary:
        return jsonify({'code': 1, 'msg': '解析失败或无结果', 'status': resp.status_code if 'resp' in locals() else None, 'err': (data.get('error') if isinstance(data, dict) else str(e) if 'e' in locals() else '')})
    return jsonify({'code': 0, 'summary': summary})

@bp.post('/warehouse/save_detail/<int:rid>')
def warehouse_save_detail(rid: int):
    title = request.form.get('title')
    content_text = request.form.get('content_text') or ''
    content_html = request.form.get('content_html') or ''
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    if 'user_id' in cols:
        row = query_one("select user_id from crawl_records where id = ?", [rid])
        if row and (row.get('user_id') is not None):
            return jsonify({'code': 1, 'msg': '仅能保存系统仓库数据'})
    if title:
        execute_update("update crawl_records set title=? where id=?", [title, rid])
    sql_ins = "insert into crawl_details(record_id, url, content_text, content_html) select id, url, ?, ? from crawl_records where id=?"
    if 'user_id' in cols:
        sql_ins = sql_ins + " and user_id is null"
    execute_update(sql_ins, [content_text, content_html, rid])
    return jsonify({'code': 0, 'msg': 'ok'})

@bp.post('/warehouse/update_summary/<int:rid>')
def warehouse_update_summary(rid: int):
    summary = request.form.get('summary') or ''
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    if 'user_id' in cols:
        row = query_one("select user_id from crawl_records where id = ?", [rid])
        if row and (row.get('user_id') is not None):
            return jsonify({'code': 1, 'msg': '仅能更新系统仓库数据'})
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

@bp.post('/rules/parse_site')
def rules_parse_site():
    url = (request.form.get('url') or '').strip()
    if not url:
        return jsonify({'code': 1, 'msg': 'URL不能为空'})
    try:
        if not url.startswith('http'):
            url = 'http://' + url
        pu = urllib.parse.urlparse(url)
        domain = (pu.netloc or '').lower()
        # Intelligent mapping for common sites
        site_name = domain
        if 'baidu.com' in domain:
            site_name = 'baidu'
        elif 'thepaper.cn' in domain:
            site_name = 'thepaper'
        elif 'news.cn' in domain or 'xinhuanet.com' in domain:
            site_name = 'xinhua'
        elif 'qq.com' in domain:
            site_name = 'qq'
        elif 'sina.com.cn' in domain:
            site_name = 'sina'
        elif '163.com' in domain:
            site_name = '163'
        elif 'people.com.cn' in domain:
            site_name = 'people'
        return jsonify({'code': 0, 'site': site_name})
    except Exception as e:
        return jsonify({'code': 1, 'msg': str(e)})

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

@bp.post('/rules/toggle/<int:rule_id>')
def rules_toggle(rule_id: int):
    row = query_one("select enabled from crawl_rules where id = ?", [rule_id])
    if not row:
        return jsonify({'code': 1, 'msg': '未找到'})
    new_val = 0 if row['enabled'] == 1 else 1
    execute_update("update crawl_rules set enabled = ? where id = ?", [new_val, rule_id])
    return jsonify({'code': 0, 'msg': '已更新', 'enabled': new_val})

@bp.route('/menus')
def menus():
    ensure_menu_table()
    general, admin = list_menus()
    return render_template('admin/menus.html', general=general, admin=admin)

@bp.post('/menus/update/<int:menu_id>')
def menus_update(menu_id: int):
    display_name = (request.form.get('display_name') or '').strip()
    order_no = request.form.get('order_no', type=int)
    ok = menu_update(menu_id, display_name if display_name else None, order_no)
    if not ok:
        return jsonify({'code': 1, 'msg': '无更新内容'})
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/menus/move_up/<int:menu_id>')
def menus_move_up(menu_id: int):
    ensure_menu_table()
    ok = move_menu(menu_id, 'up')
    return jsonify({'code': 0 if ok else 1, 'msg': '已上移' if ok else '无法上移'})

@bp.post('/menus/move_down/<int:menu_id>')
def menus_move_down(menu_id: int):
    ensure_menu_table()
    ok = move_menu(menu_id, 'down')
    return jsonify({'code': 0 if ok else 1, 'msg': '已下移' if ok else '无法下移'})

@bp.post('/menus/reorder')
def menus_reorder():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    group = data.get('admin_only')
    if not isinstance(ids, list) or group not in (0, 1):
        return jsonify({'code': 1, 'msg': '参数不全'})
    ok = reorder_group(group, ids)
    return jsonify({'code': 0 if ok else 1, 'msg': '已更新' if ok else '更新失败'})

@bp.route('/ai_engines')
def ai_engines():
    execute_update("create table if not exists ai_engines(\n        id integer primary key autoincrement,\n        provider_name text not null,\n        api_url text not null,\n        api_key text not null,\n        model_name text not null,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n    )")
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
        if 'user_id' not in cols:
            execute_update("alter table ai_engines add column user_id integer")
    except Exception:
        pass
    q = (request.args.get('q') or '').strip()
    if q:
        rows = query_all("select * from ai_engines where (provider_name like ? or model_name like ?) and (user_id is null) order by id desc", [f"%{q}%", f"%{q}%"])
    else:
        rows = query_all("select * from ai_engines where user_id is null order by id desc")
    return render_template('admin/ai_engines.html', rows=rows, q=q)

@bp.post('/ai_engines/add')
def ai_engines_add():
    provider_name = (request.form.get('provider_name') or '').strip()
    api_url = (request.form.get('api_url') or '').strip()
    api_key = (request.form.get('api_key') or '').strip()
    model_name = (request.form.get('model_name') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 0
    if not provider_name or not api_url or not api_key or not model_name:
        return jsonify({'code': 1, 'msg': '参数不全'})
    execute_update("insert into ai_engines(provider_name, api_url, api_key, model_name, enabled, user_id) values(?, ?, ?, ?, ?, NULL)", [provider_name, api_url, api_key, model_name, en])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.post('/ai_engines/update/<int:engine_id>')
def ai_engines_update(engine_id: int):
    provider_name = (request.form.get('provider_name') or '').strip()
    api_url = (request.form.get('api_url') or '').strip()
    api_key = (request.form.get('api_key') or '').strip()
    model_name = (request.form.get('model_name') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 0
    execute_update("update ai_engines set provider_name=?, api_url=?, api_key=?, model_name=?, enabled=? where id=?", [provider_name, api_url, api_key, model_name, en, engine_id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/ai_engines/delete/<int:engine_id>')
def ai_engines_delete(engine_id: int):
    execute_update("delete from ai_engines where id = ?", [engine_id])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.post('/ai_chat')
def ai_chat():
    engine_id = request.form.get('engine_id', type=int)
    prompt = (request.form.get('prompt') or '').strip()
    msgs_raw = request.form.get('messages')
    if not prompt:
        return jsonify({'code': 1, 'msg': '请输入对话内容'})
    eng = None
    if engine_id:
        eng = query_one("select * from ai_engines where id = ? and user_id is null", [engine_id])
    if not eng:
        eng = query_one("select * from ai_engines where enabled = 1 and user_id is null order by id desc limit 1")
    if not eng:
        eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if not eng:
        return jsonify({'code': 1, 'msg': '请先配置并启用AI引擎'})
    api_url = (eng.get('api_url') or '').strip().rstrip('/')
    model = (eng.get('model_name') or '').strip()
    headers = {
        'Authorization': f"Bearer {(eng.get('api_key') or '').strip()}",
        'Content-Type': 'application/json'
    }
    chat_url = api_url + ('/chat/completions' if api_url.endswith('/v1') else '/v1/chat/completions')
    messages = None
    if msgs_raw:
        try:
            obj = json.loads(msgs_raw)
            if isinstance(obj, list) and obj:
                messages = obj
        except Exception:
            messages = None
    if not messages:
        messages = [
            {"role": "system", "content": "你是政务信息采集与合规审查系统的AI助手。你的职责包含数据清洗、去重归并、结构化提取、合规审阅与摘要生成。回答使用简洁中文，必要时给出结构化列表。"},
            {"role": "user", "content": prompt}
        ]
    payload = {"model": model, "messages": messages, "temperature": 0.3}
    content = ''
    data = None
    error_msg = ''
    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=30)
        try:
            data = resp.json()
        except Exception:
            data = {}
        
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                content = data['choices'][0]['message']['content']
            except Exception:
                content = ''
            if not content:
                try:
                    content = data['choices'][0].get('text') or ''
                except Exception:
                    content = ''
            if not content:
                content = (data.get('output_text') or data.get('result') or '')
        else:
            err_info = (data.get('error') or data.get('msg') or resp.text[:200]) if isinstance(data, dict) else resp.text[:200]
            error_msg = f"上游错误({resp.status_code}): {err_info}"
    except Exception as e:
        content = ''
        error_msg = f"请求失败: {str(e)}"
    # fallback to completions if chat returns empty
    if not content:
        comp_url = api_url + ('/completions' if api_url.endswith('/v1') else '/v1/completions')
        comp_prompt = "系统: 你是政务数据清洗与分析助手。\n用户: " + prompt + "\n助手:"
        comp_payload = {"model": model, "prompt": comp_prompt, "temperature": 0.3}
        try:
            r2 = requests.post(comp_url, headers=headers, json=comp_payload, timeout=30)
            d2 = r2.json()
            if r2.status_code == 200 and isinstance(d2, dict):
                try:
                    content = d2['choices'][0].get('text') or ''
                except Exception:
                    content = ''
                if not content:
                    content = d2.get('output_text') or ''
        except Exception:
            pass
    if not content:
        return jsonify({'code': 1, 'msg': error_msg or '对话失败或无结果', 'err': error_msg})
    return jsonify({'code': 0, 'reply': content})



@bp.post('/ai_sql_demo')
def ai_sql_demo():
    engine_id = request.form.get('engine_id', type=int)
    prompt = (request.form.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'code': 1, 'msg': '请输入指令'})
    eng = None
    if engine_id:
        eng = query_one("select * from ai_engines where id = ?", [engine_id])
    if not eng:
        eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if not eng:
        return jsonify({'code': 1, 'msg': '请先配置并启用AI引擎'})
    api_url = (eng.get('api_url') or '').strip().rstrip('/')
    model = (eng.get('model_name') or '').strip()
    headers = {'Authorization': f"Bearer {(eng.get('api_key') or '').strip()}", 'Content-Type': 'application/json'}
    chat_url = api_url + ('/chat/completions' if api_url.endswith('/v1') else '/v1/chat/completions')
    cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
    schema = {
        'ai_engines': cols
    }
    sensitive = ['api_key']
    allow_cols = [c for c in cols if c not in sensitive]
    sys_msg = (
        "你是政务数据清洗与分析助手。根据提供的SQLite表结构，返回一个JSON对象，仅包含一个键sql，"
        "对应一条只读的SELECT语句。满足以下约束：\n"
        "1) 只查询 ai_engines 表；\n"
        "2) 明确列名，禁止使用 * ；\n"
        "3) 禁止包含敏感列 api_key；\n"
        "4) 如未说明，默认添加条件 enabled=1；\n"
        "5) 如未说明，默认 LIMIT 100；\n"
        "6) 禁止 UPDATE/DELETE/INSERT/DROP/ALTER。"
    )
    messages = [
        {"role": "system", "content": sys_msg + " 表结构:" + json.dumps(schema, ensure_ascii=False)},
        {"role": "user", "content": prompt}
    ]
    payload = {"model": model, "messages": messages, "temperature": 0}
    sql_out = ''
    reply_content = ''
    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=20)
        data = resp.json()
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                content = data['choices'][0]['message']['content']
            except Exception:
                content = ''
            reply_content = content or ''
            try:
                obj = json.loads(content)
                sql_out = obj.get('sql') or ''
            except Exception:
                sql_out = ''
    except Exception:
        sql_out = ''
    if not sql_out:
        return jsonify({'code': 1, 'msg': '未生成SQL'})
    low = sql_out.strip().lower()
    if not low.startswith('select') or any(x in low for x in ['update ', 'delete ', 'insert ', 'drop ', 'alter ']):
        return jsonify({'code': 1, 'msg': '仅允许只读SELECT语句'})
    # 仅允许查询 ai_engines
    if ' from ' not in low or 'ai_engines' not in low:
        return jsonify({'code': 1, 'msg': '仅允许查询 ai_engines 表'})
    # 去除 * 并强制列白名单
    import re
    m = re.match(r"\s*select\s+(.*?)\s+from\s+ai_engines(.*)$", sql_out, flags=re.IGNORECASE | re.DOTALL)
    if m:
        sel = m.group(1).strip()
        tail = m.group(2)
        if '*' in sel or sel == '' or sel.lower() == 'all':
            sel = ', '.join(allow_cols)
        else:
            # 过滤敏感列
            parts = [p.strip() for p in sel.split(',') if p.strip()]
            parts = [p for p in parts if p.lower() not in [s.lower() for s in sensitive]]
            if not parts:
                parts = allow_cols
            sel = ', '.join(parts)
        sql_out = 'SELECT ' + sel + ' FROM ai_engines' + tail
        low = sql_out.strip().lower()
    # 默认添加 enabled=1
    if ' where ' in low:
        if ' enabled' not in low:
            sql_out = sql_out.rstrip(';') + ' AND enabled = 1'
    else:
        sql_out = sql_out.rstrip(';') + ' WHERE enabled = 1'
    # 默认 LIMIT 100
    if ' limit ' not in low:
        sql_out = sql_out.rstrip(';') + ' LIMIT 100'
    try:
        rows = query_all(sql_out)
        # 过滤返回中的敏感列
        for r in rows:
            if 'api_key' in r:
                r.pop('api_key', None)
        return jsonify({'code': 0, 'reply': reply_content, 'sql': sql_out, 'rows': rows})
    except Exception as e:
        return jsonify({'code': 1, 'msg': str(e), 'sql': sql_out})
