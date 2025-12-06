from flask import Blueprint, render_template, jsonify, current_app, request, Response, stream_with_context
from flask_login import login_required, current_user
from .db import query_all, query_one, execute_update
from .crawler import run_crawler, fetch_items_for_keyword, save_items_for_keyword
import requests
import json
import time
import re

bp = Blueprint("main", __name__)

@bp.get("/")
@login_required
def index():
    return render_template("index.html", user=current_user)

@bp.get("/health")
def health():
    return jsonify({"status": "ok"})

@bp.get('/favicon.ico')
def favicon():
    try:
        return current_app.send_static_file('images/logo.png')
    except Exception:
        return jsonify({"status":"no-favicon"}), 204

@bp.get("/api/users")
@login_required
def api_users():
    if not current_user.is_admin:
        return jsonify({'code': 1, 'msg': '无权'}), 403
    data = query_all("select id, username, role_id, created_at from users order by id")
    return jsonify(data)

@bp.get("/data_board")
@login_required
def data_board():
    from flask import url_for
    if getattr(current_user, 'is_admin', False):
        latest_url = url_for('admin.data_board_latest')
        heatmap_url = url_for('admin.data_board_heatmap')
    else:
        latest_url = url_for('main.data_board_latest')
        heatmap_url = url_for('main.data_board_heatmap')
    return render_template('admin/data_board.html', latest_url=latest_url, heatmap_url=heatmap_url)

@bp.get('/data_board/latest')
@login_required
def data_board_latest():
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    try:
        if 'user_id' in cols:
            rows = query_all(
                "select id, title, source, keyword, url, created_at from crawl_records where user_id = ? order by datetime(created_at) desc limit 20",
                [current_user.id]
            )
        else:
            rows = query_all("select id, title, source, keyword, url, created_at from crawl_records order by datetime(created_at) desc limit 20")
    except Exception:
        rows = []
    return jsonify({'code': 0, 'rows': rows})

@bp.get('/data_board/heatmap')
@login_required
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
                "select id, title, summary, source, keyword, url, created_at from crawl_records where user_id = ? order by datetime(created_at) desc limit 500",
                [current_user.id]
            )
        else:
            rows = query_all("select id, title, summary, source, keyword, url, created_at from crawl_records order by datetime(created_at) desc limit 500")
    except Exception:
        rows = []
    
    return jsonify({'code': 0, 'data': simple_heat(rows)})

@bp.route('/crawls')
@login_required
def crawl_list():
    rows = query_all("select id, keyword, title, source, url, created_at from crawl_records order by id desc limit 100")
    return render_template('admin/crawl_list.html', rows=rows)

@bp.route('/ai_tools')
@login_required
def ai_tools():
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
    except Exception:
        cols = []
    if 'user_id' in cols:
        try:
            if getattr(current_user, 'is_admin', False):
                rows = query_all("select * from ai_engines where enabled = 1 and (user_id = ? or user_id is null) order by id desc", [current_user.id])
            else:
                rows = query_all("select * from ai_engines where enabled = 1 and user_id = ? order by id desc", [current_user.id])
        except Exception:
            rows = []
    else:
        rows = query_all("select * from ai_engines where enabled = 1 order by id desc")
    return render_template('admin/ai_tools.html', engines=rows)

@bp.post('/ai_analyze_demo')
@login_required
def ai_analyze_demo():
    engine_id = request.form.get('engine_id', type=int)
    prompt = (request.form.get('prompt') or '').strip()
    eng = None
    if engine_id:
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
        except Exception:
            cols = []
        if 'user_id' in cols:
            eng = query_one("select * from ai_engines where id = ? and user_id = ?", [engine_id, current_user.id])
            if not eng:
                eng = query_one("select * from ai_engines where id = ? and user_id is null", [engine_id])
        else:
            eng = query_one("select * from ai_engines where id = ?", [engine_id])
    if not eng:
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
        except Exception:
            cols = []
        if 'user_id' in cols:
            eng = query_one("select * from ai_engines where enabled = 1 and user_id = ? order by id desc limit 1", [current_user.id])
            if not eng:
                eng = query_one("select * from ai_engines where enabled = 1 and user_id is null order by id desc limit 1")
        else:
            eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if not eng:
        return jsonify({'code': 1, 'msg': '请先配置并启用AI引擎'})
    api_url = (eng.get('api_url') or '').strip().rstrip('/')
    model = (eng.get('model_name') or '').strip()
    headers = {'Authorization': f"Bearer {(eng.get('api_key') or '').strip()}", 'Content-Type': 'application/json'}
    chat_url = api_url + ('/chat/completions' if api_url.endswith('/v1') else '/v1/chat/completions')
    if prompt and prompt != '帮我分析数据仓库前两天信息':
        # Normal chat mode
        sys_msg = "你是政务数据清洗与分析助手。请根据用户输入进行回答。"
        user_msg = prompt
    else:
        # Analysis mode
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
        except Exception:
            cols = []
        try:
            if 'user_id' in cols:
                rows = query_all("select id, title, source, keyword, url, created_at from crawl_records where datetime(created_at) >= datetime('now','-2 day') and user_id = ? order by created_at desc limit 200", [current_user.id])
            else:
                rows = query_all("select id, title, source, keyword, url, created_at from crawl_records where datetime(created_at) >= datetime('now','-2 day') order by created_at desc limit 200")
        except Exception:
            rows = []
        sys_msg = (
            "你是政务数据清洗与分析助手。请针对数据仓库最近两天的信息进行简洁分析，"
            "仅使用Markdown的二级/三级标题与短列表，不输出一级标题，不包含日期或‘报告’字样，不使用表格。"
            "结构为：概览要点、数据特征、异常与风险、处理建议；总字数不超过300。"
        )
        user_msg = (prompt or '帮我分析数据仓库前两天信息') + "\n数据: " + json.dumps(rows, ensure_ascii=False)
    messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]
    content = ''
    data = None
    error_msg = ''
    try:
        resp = requests.post(chat_url, headers=headers, json={"model": model, "messages": messages, "temperature": 0.5}, timeout=60)
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
    if not content:
        return jsonify({'code': 1, 'msg': error_msg or '分析失败或无结果'})
    try:
        content = re.sub(r"(?m)^\s*#\s+.*$", "", content)
        content = re.sub(r"(?m)^\s*-{3,}\s*$", "", content)
        content = re.sub(r"报告[（(][^）)]+[）)]", "", content)
    except Exception:
        pass
    return jsonify({'code': 0, 'reply': content})

@bp.get('/ai_analyze_stream')
@login_required
def ai_analyze_stream():
    engine_id = request.args.get('engine_id', type=int)
    prompt = (request.args.get('prompt') or '').strip()
    
    eng = None
    if engine_id:
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
        except Exception:
            cols = []
        if 'user_id' in cols:
            eng = query_one("select * from ai_engines where id = ? and user_id = ?", [engine_id, current_user.id])
            if not eng:
                eng = query_one("select * from ai_engines where id = ? and user_id is null", [engine_id])
        else:
            eng = query_one("select * from ai_engines where id = ?", [engine_id])
    if not eng:
        try:
            cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
        except Exception:
            cols = []
        if 'user_id' in cols:
            eng = query_one("select * from ai_engines where enabled = 1 and user_id = ? order by id desc limit 1", [current_user.id])
            if not eng:
                eng = query_one("select * from ai_engines where enabled = 1 and user_id is null order by id desc limit 1")
        else:
            eng = query_one("select * from ai_engines where enabled = 1 order by id desc limit 1")
    if not eng:
        def gen_err():
            yield "data: 请先配置并启用AI引擎\n\n"
        return Response(stream_with_context(gen_err()), mimetype='text/event-stream')
    api_url = (eng.get('api_url') or '').strip().rstrip('/')
    model = (eng.get('model_name') or '').strip()
    headers = {'Authorization': f"Bearer {(eng.get('api_key') or '').strip()}", 'Content-Type': 'application/json'}
    chat_url = api_url + ('/chat/completions' if api_url.endswith('/v1') else '/v1/chat/completions')
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    try:
        # Always fetch recent data context (limit fields and count to save tokens)
        if 'user_id' in cols:
            rows = query_all("select id, title, source, keyword, url, created_at from crawl_records where user_id = ? order by created_at desc limit 50", [current_user.id])
        else:
            rows = query_all("select id, title, source, keyword, url, created_at from crawl_records order by created_at desc limit 50")
    except Exception:
        rows = []
    
    data_context = json.dumps(rows, ensure_ascii=False)
    
    if prompt and prompt != '帮我分析数据仓库前两天信息':
        # Custom Chat Mode with Data Context
        sys_msg = (
            "你是政务数据清洗与分析助手。你拥有对本地数据仓库的访问权限。"
            "请根据用户的问题，结合下方提供的【参考数据】进行回答。"
            "要求：\n"
            "1. 严格使用标准的Markdown格式输出。\n"
            "2. 回答风格需专业、美观、直观，类似ChatGPT的输出风格。\n"
            "3. 必须使用分段（双换行）来组织内容，确保段落清晰。\n"
            "4. 使用无序列表（- ）或有序列表（1. ）来展示要点。\n"
            "5. 关键信息（如数字、实体名）请使用**加粗**标注。\n"
            "6. 如果用户只是闲聊，可忽略参考数据，但仍需保持良好的Markdown格式。"
        )
        user_msg = f"{prompt}\n\n【参考数据】:\n{data_context}"
    else:
        # Default Analysis Mode
        sys_msg = (
            "你是政务数据清洗与分析助手。请针对数据仓库最近两天的信息进行简洁分析。\n"
            "要求：\n"
            "1. 严格使用标准的Markdown格式，包含清晰的标题、列表和段落。\n"
            "2. 结构为：## 概览要点、## 数据特征、## 异常与风险、## 处理建议。\n"
            "3. 不要包含日期或‘报告’字样，不使用表格。\n"
            "4. 必须使用分段（双换行）分隔不同部分。\n"
            "5. 总字数不超过500字。"
        )
        user_msg = (prompt or '帮我分析数据仓库前两天信息') + "\n数据: " + data_context
        
    payload = {"model": model, "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}], "temperature": 0.5, "stream": True}

    def generate():
        sent_any = False
        # Remove clean_chunk function as it interferes with stream formatting
        
        try:
            with requests.post(chat_url, headers=headers, json=payload, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    try:
                        data = resp.json()
                        err = data.get('error') if isinstance(data, dict) else ''
                    except Exception:
                        err = ''
                    yield f"data: 上游错误({resp.status_code}) {err}\n\n"
                    return
                for raw in resp.iter_lines(decode_unicode=False):
                    if not raw:
                        continue
                    try:
                        line = raw.decode('utf-8', 'replace')
                    except Exception:
                        line = ''
                    if not line:
                        continue
                    if line.startswith('data:'):
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        if data_str == '[DONE]':
                            break
                        out = ''
                        try:
                            obj = json.loads(data_str)
                            ch = obj.get('choices') or []
                            if ch:
                                c0 = ch[0] or {}
                                delta = c0.get('delta') or {}
                                out = (delta.get('content') or c0.get('text') or obj.get('output_text') or obj.get('result') or '')
                        except Exception:
                            out = ''
                        if out:
                            # Do NOT strip or clean chunk in stream mode to preserve formatting
                            out = out.replace('\r', '') 
                            if out:
                                # Properly format multi-line data for SSE
                                lines = out.split('\n')
                                for line in lines:
                                    yield f"data: {line}\n"
                                yield "\n"
                            sent_any = True
        except Exception as e:
            yield f"data: 流式传输失败: {str(e)}\n\n"
        if not sent_any:
            text = ''
            try:
                payload2 = {"model": model, "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}], "temperature": 0}
                r2 = requests.post(chat_url, headers=headers, json=payload2, timeout=30)
                d2 = r2.json() if r2.status_code == 200 else {}
                if isinstance(d2, dict):
                    try:
                        text = d2.get('choices', [{}])[0].get('message', {}).get('content') or ''
                    except Exception:
                        text = ''
                    if not text:
                        try:
                            text = d2.get('choices', [{}])[0].get('text') or ''
                        except Exception:
                            text = ''
                    if not text:
                        text = d2.get('output_text') or d2.get('result') or ''
            except Exception:
                pass
            if not text:
                try:
                    comp_url = api_url + ('/completions' if api_url.endswith('/v1') else '/v1/completions')
                    comp_prompt = sys_msg + "\n" + user_msg
                    r3 = requests.post(comp_url, headers=headers, json={"model": model, "prompt": comp_prompt, "temperature": 0}, timeout=30)
                    d3 = r3.json() if r3.status_code == 200 else {}
                    if isinstance(d3, dict):
                        try:
                            text = d3.get('choices', [{}])[0].get('text') or ''
                        except Exception:
                            text = ''
                        if not text:
                            text = d3.get('output_text') or d3.get('result') or ''
                except Exception:
                    pass
            if text:
                text = text.replace('\r', '')
                # Do NOT clean chunk
                # Split large text into smaller chunks for smoother streaming
                chunk_size = 100
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i+chunk_size]
                    lines = chunk.split('\n')
                    for line in lines:
                        yield f"data: {line}\n"
                    yield "\n"
                    time.sleep(0.02)
                sent_any = True
        
        if not sent_any:
             yield "data: 生成失败，未能获取到有效回复。请检查AI引擎配置。\n\n"
        
        yield "data: [DONE]\n\n"

    resp = Response(stream_with_context(generate()), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Connection'] = 'keep-alive'
    resp.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp

@bp.get('/my/sources')
@login_required
def user_sources():
    execute_update("create table if not exists crawlers(\n        id integer primary key autoincrement,\n        name text unique not null,\n        module text,\n        callable text,\n        config text,\n        domain text,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n     )")
    try:
        cols2 = [c['name'] for c in query_all("PRAGMA table_info(crawlers)")]
        if 'domain' not in cols2:
            execute_update("alter table crawlers add column domain text")
    except Exception:
        pass
    crawlers = query_all("select * from crawlers where enabled = 1 order by id asc")
    return render_template('admin/crawl_manage.html', crawlers=crawlers)

@bp.post('/my/sources/add')
@login_required
def user_sources_add():
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
    execute_update("insert into sources(keyword, interval_minutes, enabled, crawler_name, user_id) values(?, ?, ?, ?, ?)", [keyword, interval, enabled, crawler_name, current_user.id])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.route('/my/sources/toggle/<int:source_id>', methods=['POST'])
@login_required
def user_sources_toggle(source_id):
    row = query_one("select enabled from sources where id = ? and user_id = ?", [source_id, current_user.id])
    if not row:
        return jsonify({'code': 1, 'msg': '未找到'})
    new_val = 0 if row['enabled'] == 1 else 1
    execute_update("update sources set enabled = ? where id = ? and user_id = ?", [new_val, source_id, current_user.id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.route('/my/sources/delete/<int:source_id>', methods=['POST'])
@login_required
def user_sources_delete(source_id):
    execute_update("delete from sources where id = ? and user_id = ?", [source_id, current_user.id])
    return jsonify({'code': 0, 'msg': '删除成功'})

@bp.route('/my/sources/update/<int:source_id>', methods=['POST'])
@login_required
def user_sources_update(source_id):
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
    params.append(current_user.id)
    params.append(source_id)
    execute_update(f"update sources set {', '.join(sets)} where user_id = ? and id = ?", params)
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.route('/my/sources/run/<int:source_id>', methods=['POST'])
@login_required
def user_sources_run(source_id):
    src = query_one("select * from sources where id = ? and user_id = ?", [source_id, current_user.id])
    if not src:
        return jsonify({'code': 1, 'msg': '未找到'})
    cname = (src.get('crawler_name') or '').strip()
    items = []
    if cname:
        items = run_crawler(cname, src['keyword'], 10)
    else:
        items = fetch_items_for_keyword(src['keyword'])
    save_items_for_keyword(src['keyword'], items, current_user.id)
    execute_update("update sources set last_run = current_timestamp where id = ?", [source_id])
    return jsonify({'code': 0, 'msg': '采集完成', 'count': len(items)})

@bp.route('/my/ai_engines')
@login_required
def user_ai_engines():
    execute_update("create table if not exists ai_engines(\n        id integer primary key autoincrement,\n        provider_name text not null,\n        api_url text not null,\n        api_key text not null,\n        model_name text not null,\n        enabled integer default 1,\n        created_at datetime default current_timestamp\n    )")
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(ai_engines)")]
    except Exception:
        cols = []
    if 'user_id' not in cols:
        try:
            execute_update("alter table ai_engines add column user_id integer")
        except Exception:
            pass
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        rows = query_all("select * from ai_engines where user_id = ? and (provider_name like ? or model_name like ?) order by id desc", [current_user.id, f"%{q}%", f"%{q}%"])
    else:
        rows = query_all("select * from ai_engines where user_id = ? order by id desc", [current_user.id])
        try:
            if not rows:
                admin_user = query_one("select id from users where username = ?", ['admin'])
                admin_id = admin_user and admin_user.get('id')
                copied = False
                if admin_id:
                    srcs = query_all("select provider_name, api_url, api_key, model_name, enabled from ai_engines where user_id = ? order by id asc limit 2", [admin_id])
                    for r in (srcs or []):
                        try:
                            execute_update("insert into ai_engines(provider_name, api_url, api_key, model_name, enabled, user_id) values(?, ?, ?, ?, ?, ?)", [r.get('provider_name') or '', r.get('api_url') or '', r.get('api_key') or '', r.get('model_name') or '', int(r.get('enabled') or 0), current_user.id])
                            copied = True
                        except Exception:
                            pass
                if not copied:
                    defaults = [
                        ("OpenAI", "https://api.openai.com/v1", "", "gpt-4o-mini", 0),
                        ("阿里云DashScope", "https://dashscope.aliyuncs.com/api/v1", "", "qwen-plus", 0)
                    ]
                    for (pn, url, key, mn, en) in defaults:
                        try:
                            execute_update("insert into ai_engines(provider_name, api_url, api_key, model_name, enabled, user_id) values(?, ?, ?, ?, ?, ?)", [pn, url, key, mn, en, current_user.id])
                        except Exception:
                            pass
                rows = query_all("select * from ai_engines where user_id = ? order by id desc", [current_user.id])
        except Exception:
            pass
    return render_template('admin/ai_engines.html', rows=rows, q=q, base_prefix='/my')

@bp.post('/my/ai_engines/add')
@login_required
def user_ai_engines_add():
    provider_name = (request.form.get('provider_name') or '').strip()
    api_url = (request.form.get('api_url') or '').strip()
    api_key = (request.form.get('api_key') or '').strip()
    model_name = (request.form.get('model_name') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 0
    if not provider_name or not api_url or not api_key or not model_name:
        return jsonify({'code': 1, 'msg': '参数不全'})
    execute_update("insert into ai_engines(provider_name, api_url, api_key, model_name, enabled, user_id) values(?, ?, ?, ?, ?, ?)", [provider_name, api_url, api_key, model_name, en, current_user.id])
    return jsonify({'code': 0, 'msg': '添加成功'})

@bp.post('/my/ai_engines/update/<int:engine_id>')
@login_required
def user_ai_engines_update(engine_id: int):
    provider_name = (request.form.get('provider_name') or '').strip()
    api_url = (request.form.get('api_url') or '').strip()
    api_key = (request.form.get('api_key') or '').strip()
    model_name = (request.form.get('model_name') or '').strip()
    enabled = request.form.get('enabled')
    en = 1 if (enabled in ('1','true','on')) else 0
    execute_update("update ai_engines set provider_name=?, api_url=?, api_key=?, model_name=?, enabled=? where id=? and user_id = ?", [provider_name, api_url, api_key, model_name, en, engine_id, current_user.id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/my/ai_engines/delete/<int:engine_id>')
@login_required
def user_ai_engines_delete(engine_id: int):
    execute_update("delete from ai_engines where id = ? and user_id = ?", [engine_id, current_user.id])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.post('/my/ai_chat')
@login_required
def user_ai_chat():
    engine_id = request.form.get('engine_id', type=int)
    prompt = (request.form.get('prompt') or '').strip()
    msgs_raw = request.form.get('messages')
    if not prompt:
        return jsonify({'code': 1, 'msg': '请输入对话内容'})
    eng = None
    if engine_id:
        eng = query_one("select * from ai_engines where id = ? and user_id = ?", [engine_id, current_user.id])
    if not eng:
        eng = query_one("select * from ai_engines where enabled = 1 and user_id = ? order by id desc limit 1", [current_user.id])
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

@bp.get('/my/warehouse')
@login_required
def user_warehouse():
    try:
        cols = [c['name'] for c in query_all("PRAGMA table_info(crawl_records)")]
    except Exception:
        cols = []
    if 'user_id' not in cols:
        try:
            execute_update("alter table crawl_records add column user_id integer")
        except Exception:
            pass
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
    if q:
        where = " where title like ? or summary like ? or keyword like ?"
        params = [f"%{q}%", f"%{q}%", f"%{q}%"]
    where = ((' where ' in where) and (where + " and user_id = ?")) or (" where user_id = ?")
    params = params + [current_user.id]
    total_row = query_one(f"select count(*) as cnt from crawl_records{where}", params)
    total = (total_row and total_row.get('cnt')) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    if page > pages:
        page = pages
    offset = (page - 1) * page_size
    rows = query_all(f"select id, keyword, title, summary, cover, url, source, created_at from crawl_records{where} order by id asc limit ? offset ?", params + [page_size, offset])
    return render_template('admin/warehouse.html', rows=rows, q=q, page=page, page_size=page_size, total=total, pages=pages, base_prefix='/my')

@bp.post('/my/warehouse/update/<int:rid>')
@login_required
def user_warehouse_update(rid: int):
    own = query_one("select 1 from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
    if not own:
        return jsonify({'code': 1, 'msg': '无权'})
    title = request.form.get('title')
    summary = request.form.get('summary')
    cover = request.form.get('cover')
    url = request.form.get('url')
    source = request.form.get('source')
    keyword = request.form.get('keyword')
    execute_update("update crawl_records set title=?, summary=?, cover=?, url=?, source=?, keyword=? where id=? and user_id=?", [title or '', summary or '', cover or '', url or '', source or '', keyword or '', rid, current_user.id])
    return jsonify({'code': 0, 'msg': '已更新'})

@bp.post('/my/warehouse/delete/<int:rid>')
@login_required
def user_warehouse_delete(rid: int):
    own = query_one("select 1 from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
    if not own:
        return jsonify({'code': 1, 'msg': '无权'})
    execute_update("delete from crawl_details where record_id = ?", [rid])
    execute_update("delete from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
    return jsonify({'code': 0, 'msg': '已删除'})

@bp.post('/my/warehouse/batch_delete')
@login_required
def user_warehouse_batch_delete():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 1, 'msg': '缺少ID列表'})
    cnt = 0
    for rid in ids:
        try:
            own = query_one("select 1 from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
            if not own:
                continue
            execute_update("delete from crawl_details where record_id = ?", [rid])
            execute_update("delete from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
            cnt += 1
        except Exception:
            pass
    return jsonify({'code': 0, 'msg': '已批量删除', 'count': cnt})

@bp.post('/my/warehouse/batch_collect')
@login_required
def user_warehouse_batch_collect():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 1, 'msg': '缺少ID列表'})
    import requests as _req
    cnt = 0
    for rid in ids:
        try:
            rec = query_one("select url, source from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
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
                        execute_update("update crawl_records set title=? where id=? and user_id = ?", [title, rid, current_user.id])
                    except Exception:
                        pass
                if content_text or content_html:
                    execute_update("insert into crawl_details(record_id, url, content_text, content_html) select id, url, ?, ? from crawl_records where id=? and user_id = ?", [content_text, content_html, rid, current_user.id])
                    cnt += 1
        except Exception:
            pass
    return jsonify({'code': 0, 'msg': '已批量采集', 'count': cnt})

@bp.get('/my/warehouse/detail/<int:rid>')
@login_required
def user_warehouse_detail(rid: int):
    own = query_one("select 1 from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
    if not own:
        return jsonify({'code': 1, 'msg': '无权'})
    detail = query_one("select content_text, content_html from crawl_details where record_id = ? order by id desc limit 1", [rid])
    return jsonify({'code': 0, 'detail': detail or {}})

@bp.post('/my/warehouse/analyze/<int:rid>')
@login_required
def user_warehouse_analyze(rid: int):
    own = query_one("select 1 from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
    if not own:
        return jsonify({'code': 1, 'msg': '无权'})
    detail = query_one("select content_text from crawl_details where record_id = ? order by id desc limit 1", [rid])
    rec = query_one("select title, summary from crawl_records where id = ? and user_id = ?", [rid, current_user.id])
    content_text = (detail and detail.get('content_text')) or (rec and rec.get('summary')) or ''
    if not content_text:
        return jsonify({'code': 1, 'msg': '暂无可解析内容，请先进行详细采集'})
    try:
        eng = query_one("select * from ai_engines where enabled = 1 and user_id = ? order by id desc limit 1", [current_user.id])
    except Exception:
        eng = None
    if not eng:
        return jsonify({'code': 1, 'msg': '请先在AI引擎管理中配置并启用引擎'})
    api_url = (eng.get('api_url') or '').strip().rstrip('/')
    model = (eng.get('model_name') or '').strip()
    headers = {'Authorization': f"Bearer {(eng.get('api_key') or '').strip()}", 'Content-Type': 'application/json'}
    chat_url = api_url + ('/chat/completions' if api_url.endswith('/v1') else '/v1/chat/completions')
    messages = [
        {"role": "system", "content": "你是政府信息审查系统的AI助手。请用中文在200字以内概括要点，提取关键信息，输出纯文本摘要。"},
        {"role": "user", "content": content_text}
    ]
    payload = {"model": model, "messages": messages, "temperature": 0.3}
    content = ''
    data = None
    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=30)
        data = resp.json() if resp.status_code == 200 else {}
        if isinstance(data, dict):
            content = data.get('choices', [{}])[0].get('message', {}).get('content') or ''
    except Exception:
        content = ''
    if not content:
        return jsonify({'code': 1, 'msg': '解析失败或无结果'})
    return jsonify({'code': 0, 'summary': content})
