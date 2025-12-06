from flask import Blueprint, render_template, jsonify, current_app, request, Response, stream_with_context
from flask_login import login_required, current_user
from .db import query_all, query_one
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
    data = query_all("select id, username, role_id, created_at from users order by id")
    return jsonify(data)

@bp.get("/data_board")
@login_required
def data_board():
    return render_template('admin/data_board.html')

@bp.get('/data_board/latest')
@login_required
def data_board_latest():
    try:
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
    rows = query_all("select * from ai_engines where enabled = 1 order by id desc")
    return render_template('admin/ai_tools.html', engines=rows)

@bp.post('/ai_analyze_demo')
@login_required
def ai_analyze_demo():
    engine_id = request.form.get('engine_id', type=int)
    prompt = (request.form.get('prompt') or '').strip()
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
    if prompt and prompt != '帮我分析数据仓库前两天信息':
        # Normal chat mode
        sys_msg = "你是政务数据清洗与分析助手。请根据用户输入进行回答。"
        user_msg = prompt
    else:
        # Analysis mode
        try:
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
        eng = query_one("select * from ai_engines where id = ?", [engine_id])
    if not eng:
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
        # Always fetch recent data context (limit fields and count to save tokens)
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
