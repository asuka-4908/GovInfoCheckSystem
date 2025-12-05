from flask import Blueprint, request, jsonify
import requests
from bs4 import BeautifulSoup
from .db import execute_update, query_all, query_one
import json
import time
import random
import urllib.parse
import re
from urllib.parse import urljoin

bp = Blueprint('crawler', __name__, url_prefix='/api')

def parse_items(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    def pick_cover(container):
        img = container.select_one('img') or container.select_one('.c-img img') or container.select_one('.c-img')
        url = ''
        if img:
            for key in ('src','data-src','data-original'):
                if img.has_attr(key) and img.get(key):
                    url = img.get(key)
                    break
        if not url:
            styled = container.select_one('[style*="background"]')
            if styled and styled.has_attr('style'):
                m = re.search(r'url\(([^)]+)\)', styled['style'])
                if m:
                    url = m.group(1).strip('"\'')
        if url.startswith('//'):
            url = 'https:' + url
        return url
    for res in soup.select('div.result'):
        title_tag = res.select_one('h3 a') or res.select_one('a')
        title = title_tag.get_text(strip=True) if title_tag else ''
        href = title_tag['href'] if title_tag and title_tag.has_attr('href') else ''
        summary_tag = res.select_one('.c-line-clamp3') or res.select_one('.c-abstract') or res.select_one('div')
        summary = summary_tag.get_text(strip=True) if summary_tag else ''
        source_tag = res.select_one('.c-author') or res.select_one('.news-source') or res.select_one('span')
        source = source_tag.get_text(strip=True) if source_tag else ''
        cover = pick_cover(res)
        if title or href:
            items.append({'标题': title, '概要': summary, '封面': cover, '原始URL': href, '来源': source})
    if not items:
        for a in soup.select('h3 a'):
            title = a.get_text(strip=True)
            href = a.get('href', '')
            items.append({'标题': title, '概要': '', '封面': '', '原始URL': href, '来源': ''})
    return items

def parse_news_items(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    def pick_cover(container):
        img = container.select_one('img') or container.select_one('.c-img img') or container.select_one('.c-img')
        url = ''
        if img:
            for key in ('src','data-src','data-original'):
                if img.has_attr(key) and img.get(key):
                    url = img.get(key)
                    break
        if not url:
            styled = container.select_one('[style*="background"]')
            if styled and styled.has_attr('style'):
                m = re.search(r'url\(([^)]+)\)', styled['style'])
                if m:
                    url = m.group(1).strip('"\'')
        if url.startswith('//'):
            url = 'https:' + url
        return url
    containers = soup.select('div.result') or soup.select('.result')
    for res in containers:
        title_tag = res.select_one('h3 a') or res.select_one('a')
        title = title_tag.get_text(strip=True) if title_tag else ''
        href = title_tag['href'] if title_tag and title_tag.has_attr('href') else ''
        summary_tag = res.select_one('.c-summary') or res.select_one('.c-row') or res.select_one('p')
        summary = summary_tag.get_text(strip=True) if summary_tag else ''
        source_tag = res.select_one('.c-author') or res.select_one('.source')
        source = source_tag.get_text(strip=True) if source_tag else ''
        cover = pick_cover(res)
        if title or href:
            items.append({'标题': title, '概要': summary, '封面': cover, '原始URL': href, '来源': source})
    if not items:
        for a in soup.select('h3 a'):
            title = a.get_text(strip=True)
            href = a.get('href', '')
            items.append({'标题': title, '概要': '', '封面': '', '原始URL': href, '来源': ''})
    return items

def collect_baidu_items(keyword, count):
    if not keyword:
        return []
    url = 'https://www.baidu.com/s'
    params = {
        'rtt': '1', 'bsst': '1', 'cl': '2', 'tn': 'news', 'rsv_dl': 'ns_pc', 'word': keyword
    }
    headers = {
        'cache-control': 'max-age=0',
        'referer': 'https://www.baidu.com/',
        'sec-ch-ua': '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
    }
    count = count or 10
    out = []
    seen = set()
    current_pn = 0
    max_attempts = max(5, count // 2)
    for i in range(max_attempts):
        if len(out) >= count:
            break
        params_p = dict(params)
        params_p['pn'] = current_pn * 10
        try:
            resp = requests.get(url, params=params_p, headers=headers, timeout=10)
            page_items = parse_items(resp.text)
        except Exception:
            page_items = []
        if not page_items:
            url2 = 'https://news.baidu.com/ns'
            params2 = {'word': keyword, 'tn': 'news', 'from': 'news', 'pn': current_pn * 20}
            try:
                resp2 = requests.get(url2, params=params2, headers=headers, timeout=10)
                page_items = parse_news_items(resp2.text)
            except Exception:
                page_items = []
        added_in_page = 0
        for it in page_items:
            u = it.get('原始URL','')
            t = it.get('标题','')
            key = u or t
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(it)
            added_in_page += 1
            if len(out) >= count:
                break
        current_pn += 1
        if i > 1 and added_in_page == 0:
            pass
    out = out[:count]
    if not out:
        out = []
    try:
        def find_meta_image(html, base_url):
            s = BeautifulSoup(html, 'html.parser')
            for sel in [
                'meta[property="og:image"]',
                'meta[name="og:image"]',
                'meta[name="twitter:image"]',
                'meta[property="twitter:image"]'
            ]:
                m = s.select_one(sel)
                if m and m.has_attr('content') and m['content']:
                    return m['content']
            for sel in [
                'link[rel="icon"]',
                'link[rel="shortcut icon"]',
                'link[rel="apple-touch-icon"]'
            ]:
                l = s.select_one(sel)
                if l and l.has_attr('href') and l['href']:
                    return l['href']
            img = s.select_one('img')
            if img and img.has_attr('src'):
                return img['src']
            try:
                from urllib.parse import urlparse
                pu = urlparse(base_url)
                return f"{pu.scheme}://{pu.netloc}/favicon.ico"
            except Exception:
                return ''
        for i in range(min(6, len(out))):
            it = out[i]
            if not it.get('封面') and it.get('原始URL','').startswith('http'):
                try:
                    r2 = requests.get(it['原始URL'], headers=headers, timeout=5)
                    cover2 = find_meta_image(r2.text, it['原始URL'])
                    if cover2:
                        if cover2.startswith('//'):
                            cover2 = 'https:' + cover2
                        it['封面'] = cover2
                except Exception:
                    pass
    except Exception:
        pass
    return out

@bp.get('/crawl')
def crawl():
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify([])
    count = request.args.get('count', type=int) or 10
    out = collect_baidu_items(keyword, count)
    if request.args.get('save') == '1':
        for it in out:
            execute_update(
                "insert into crawl_records(keyword, title, summary, cover, url, source) values(?, ?, ?, ?, ?, ?)",
                [keyword, it.get('标题',''), it.get('概要',''), it.get('封面',''), it.get('原始URL',''), it.get('来源','')]
            )
    # 本地库兜底：若外部采集为空，尝试从数据库返回历史记录
    if not out:
        try:
            rows = query_all(
                "select title as 标题, summary as 概要, cover as 封面, url as 原始URL, source as 来源 from crawl_records where (keyword like ? or title like ? or summary like ?) order by id desc limit ?",
                [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", count]
            )
            out = rows or []
        except Exception:
            pass
    return jsonify(out)

def fetch_items_for_keyword(keyword):
    settings_map = {s['key']: s['value'] for s in query_all("select * from settings")}
    proxies = {}
    if settings_map.get('http_proxy'):
        proxies['http'] = settings_map['http_proxy']
    if settings_map.get('https_proxy'):
        proxies['https'] = settings_map['https_proxy']
    ua = settings_map.get('user_agent') or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
    referer = settings_map.get('referer') or 'https://www.baidu.com/'
    ch_ua = settings_map.get('sec_ch_ua') or '"Chromium";v="142", "Not_A Brand";v="99", "Google Chrome";v="142"'
    ch_ua_platform = settings_map.get('sec_ch_ua_platform') or '"Windows"'
    ch_ua_mobile = settings_map.get('sec_ch_ua_mobile') or '?0'
    try:
        call_ztbox(keyword, proxies, ua, referer)
    except Exception:
        pass
    url = 'https://www.baidu.com/s'
    params = {'rtt': '1', 'bsst': '1', 'cl': '2', 'tn': 'news', 'rsv_dl': 'ns_pc', 'word': keyword}
    headers = {
        'cache-control': 'max-age=0',
        'referer': referer,
        'sec-ch-ua': ch_ua,
        'sec-ch-ua-mobile': ch_ua_mobile,
        'sec-ch-ua-platform': ch_ua_platform,
        'accept-language': 'zh-CN,zh;q=0.9',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'user-agent': ua
    }
    resp = requests.get(url, params=params, headers=headers, timeout=10, proxies=proxies or None, allow_redirects=True)
    items = parse_items(resp.text)
    if not items:
        url2 = 'https://news.baidu.com/ns'
        params2 = {'word': keyword, 'tn': 'news', 'from': 'news'}
        resp2 = requests.get(url2, params=params2, headers=headers, timeout=10, proxies=proxies or None, allow_redirects=True)
        items = parse_news_items(resp2.text)
    return items

def save_items_for_keyword(keyword, items):
    for it in items:
        execute_update(
            "insert into crawl_records(keyword, title, summary, cover, url, source) values(?, ?, ?, ?, ?, ?)",
            [keyword, it.get('标题',''), it.get('概要',''), it.get('封面',''), it.get('原始URL',''), it.get('来源','')]
        )

def call_ztbox(keyword: str, proxies: dict, ua: str, referer: str):
    payload = {
        "cateid": "99",
        "actiondata": {
            "id": 19083,
            "type": "0",
            "timestamp": int(time.time() * 1000),
            "content": {
                "page": "a",
                "source": "",
                "from": "search",
                "type": "show",
                "value": "cardresult",
                "ext": {
                    "qid": f"{random.randint(0, 1<<64):x}",
                    "rsv_dl": "tb",
                    "query": keyword,
                    "card_type": "ala",
                    "valueInfo": []
                }
            }
        }
    }
    data_param = urllib.parse.quote(json.dumps(payload, ensure_ascii=True))
    url = "https://mbd.baidu.com/ztbox"
    params = {"action": "zpblog", "appname": "pcsearch", "v": "2.0", "data": data_param}
    headers = {
        'referer': referer,
        'origin': 'https://www.baidu.com',
        'user-agent': ua,
        'cache-control': 'max-age=0'
    }
    requests.get(url, params=params, headers=headers, timeout=5, proxies=proxies or None, allow_redirects=True)

@bp.post('/deep_crawl')
def deep_crawl():
    data = request.get_json(silent=True) or {}
    url = data.get('url') or ''
    if not url:
        return jsonify({'code': 1, 'msg': '缺少URL'})
    settings_map = {s['key']: s['value'] for s in query_all("select * from settings")}
    proxies = {}
    if settings_map.get('http_proxy'):
        proxies['http'] = settings_map['http_proxy']
    if settings_map.get('https_proxy'):
        proxies['https'] = settings_map['https_proxy']
    ua = settings_map.get('user_agent') or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
    headers = {
        'user-agent': ua,
        'referer': settings_map.get('referer') or 'https://www.baidu.com/',
        'accept-language': 'zh-CN,zh;q=0.9'
    }
    # 读取采集规则，匹配站点并合并自定义请求头
    rule = None
    try:
        rules = query_all("select * from crawl_rules where enabled = 1 order by id desc")
        for r in rules:
            s = r.get('site') or ''
            src = (data.get('source') or '').strip()
            if s and (s in url or (src and s in src)):
                rule = r
                break
        if rule and (rule.get('request_headers')):
            try:
                hdrs = json.loads(rule['request_headers'])
                if isinstance(hdrs, dict):
                    for k, v in hdrs.items():
                        if v is not None:
                            headers[str(k)] = str(v)
            except Exception:
                pass
    except Exception:
        rule = None
    try:
        r = requests.get(url, headers=headers, timeout=10, proxies=proxies or None, allow_redirects=True)
        raw = r.content
        enc = None
        try:
            m1 = re.search(br'<meta[^>]*charset\s*=\s*[\"\']?([a-zA-Z0-9_-]+)', raw, re.IGNORECASE)
            if m1:
                enc = m1.group(1).decode('ascii', errors='ignore')
            else:
                m2 = re.search(br'charset\s*=\s*([a-zA-Z0-9_-]+)', raw, re.IGNORECASE)
                if m2:
                    enc = m2.group(1).decode('ascii', errors='ignore')
        except Exception:
            enc = None
        if not enc:
            enc = r.encoding or r.apparent_encoding or 'utf-8'
        html = None
        for candidate in [enc, 'utf-8', 'gbk', 'gb2312', 'big5']:
            if not candidate:
                continue
            try:
                html = raw.decode(candidate, errors='ignore')
                break
            except Exception:
                continue
        if html is None:
            html = raw.decode('utf-8', errors='ignore')
        # 若存在规则且提供了XPath，尝试按规则提取
        if rule and (rule.get('title_xpath') or rule.get('content_xpath')):
            try:
                from lxml import html as lhtml
                import lxml.html
                doc = lhtml.fromstring(html)
                title_val = ''
                if rule.get('title_xpath'):
                    tn = doc.xpath(rule['title_xpath'])
                    if tn:
                        t0 = tn[0]
                        title_val = t0 if isinstance(t0, str) else (t0.text_content() or '').strip()
                content_text = ''
                content_html = ''
                if rule.get('content_xpath'):
                    cn = doc.xpath(rule['content_xpath'])
                    if cn:
                        content_text = '\n'.join([c if isinstance(c, str) else (c.text_content() or '').strip() for c in cn if c is not None])
                        try:
                            content_html = ''.join([c if isinstance(c, str) else lxml.html.tostring(c, encoding='unicode') for c in cn if c is not None])
                        except Exception:
                            content_html = ''
                # 如果规则命中却未解析到有效内容，尝试自动探测内容容器并更新规则
                if not (content_text or content_html):
                    try:
                        candidates = [
                            "//article",
                            "//div[@id='content']",
                            "//div[contains(@class,'content')]",
                            "//div[contains(@class,'article')]",
                            "//div[contains(@class,'news')]",
                            "//div[contains(@class,'main')]"
                        ]
                        best_xpath = None
                        best_text = ''
                        best_html = ''
                        for xp in candidates:
                            cn2 = doc.xpath(xp)
                            if not cn2:
                                continue
                            txt2 = '\n'.join([c if isinstance(c, str) else (c.text_content() or '').strip() for c in cn2 if c is not None])
                            if len(txt2) >= 200:  # 文本足够长认为有效
                                best_xpath = xp
                                try:
                                    best_html = ''.join([c if isinstance(c, str) else lxml.html.tostring(c, encoding='unicode') for c in cn2 if c is not None])
                                except Exception:
                                    best_html = ''
                                best_text = txt2
                                break
                        if best_xpath:
                            content_text = best_text
                            content_html = best_html
                            # 自动更新规则库的内容XPath
                            try:
                                execute_update("update crawl_rules set content_xpath=? where id=?", [best_xpath, rule['id']])
                            except Exception:
                                pass
                    except Exception:
                        pass
                if not title_val:
                    try:
                        tn2 = doc.xpath('//h1')
                        if tn2:
                            t0 = tn2[0]
                            title_val = t0 if isinstance(t0, str) else (t0.text_content() or '').strip()
                            try:
                                execute_update("update crawl_rules set title_xpath=? where id=?", ['//h1', rule['id']])
                            except Exception:
                                pass
                    except Exception:
                        pass
                if content_text or content_html or title_val:
                    if not content_text:
                        soup2 = BeautifulSoup(html, 'html.parser')
                        content_text = soup2.get_text(separator='\n', strip=True)
                    if not content_html:
                        content_html = html
                    return jsonify({'code': 0, 'msg': 'ok', 'title': title_val, 'content_text': content_text, 'content_html': content_html})
            except Exception:
                pass
        # 默认提取：无规则或规则失败
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator='\n', strip=True)
        ttag = soup.find('h1') or (soup.find('title') if soup.find('title') else None)
        tval = ''
        try:
            if ttag:
                tval = ttag.get_text(strip=True)
        except Exception:
            tval = ''
        return jsonify({'code': 0, 'msg': 'ok', 'title': tval, 'content_text': text, 'content_html': html})
    except Exception as e:
        return jsonify({'code': 1, 'msg': str(e)})

def collect_xinhua_items(keyword, count):
    keyword = (keyword or '').strip()
    count = count or 10
    base_url = 'http://sc.news.cn/scyw.htm'
    settings_map = {s['key']: s['value'] for s in query_all("select * from settings")}
    proxies = {}
    if settings_map.get('http_proxy'):
        proxies['http'] = settings_map['http_proxy']
    if settings_map.get('https_proxy'):
        proxies['https'] = settings_map['https_proxy']
    ua = settings_map.get('user_agent') or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
    headers = {
        'user-agent': ua,
        'referer': 'http://sc.news.cn/',
        'accept-language': 'zh-CN,zh;q=0.9'
    }
    try:
        resp = requests.get(base_url, headers=headers, timeout=10, proxies=proxies or None, allow_redirects=True)
        raw = resp.content
        enc = resp.encoding or resp.apparent_encoding or 'utf-8'
        html = None
        for candidate in [enc, 'utf-8', 'gbk', 'gb2312']:
            try:
                html = raw.decode(candidate, errors='ignore')
                break
            except Exception:
                continue
        if html is None:
            html = raw.decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        items = []
        seen = set()
        ids = re.findall(r'datasource:([0-9a-fA-F]{32})', html)
        if ids:
            nid = ids[0]
            for pg in range(1, 6):
                api = f"https://qc.wa.news.cn/nodeart/list?nid={nid}&pgnum={pg}&cnt={max(10,count)}&tp=1&orderby=1"
                try:
                    jr = requests.get(api, headers=headers, timeout=10, proxies=proxies or None, verify=False)
                    j = jr.json()
                    lst = j.get('data', {}).get('list') or j.get('list') or []
                    for it in lst:
                        title = it.get('Title') or it.get('title') or ''
                        href = it.get('LinkUrl') or it.get('Url') or it.get('url') or ''
                        cover = it.get('ImgUrl') or it.get('Image') or it.get('image') or ''
                        summary = it.get('Intro') or it.get('Digest') or it.get('intro') or ''
                        if href and not href.startswith('http'):
                            href = urljoin(base_url, href)
                        k = href or title
                        if not k or k in seen:
                            continue
                        seen.add(k)
                        items.append({'标题': title, '概要': summary, '封面': cover or '', '原始URL': href, '来源': '新华网'})
                        if len(items) >= count:
                            break
                except Exception:
                    pass
                if len(items) >= count:
                    break
        containers = soup.select('#newslist li') or soup.select('.news_list li') or soup.select('li')
        for li in containers:
            a = li.select_one('a')
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get('href', '')
            if href and not href.startswith('http'):
                href = urljoin(base_url, href)
            img = li.select_one('img')
            cover = ''
            if img:
                for key in ('src','data-src','data-original'):
                    if img.has_attr(key) and img.get(key):
                        cover = img.get(key)
                        break
            p = li.select_one('p')
            summary = p.get_text(strip=True) if p else ''
            source = '新华网'
            if not title or not href:
                continue
            k = href or title
            if k in seen:
                continue
            seen.add(k)
            items.append({'标题': title, '概要': summary, '封面': cover, '原始URL': href, '来源': source})
            if len(items) >= count:
                break
        if keyword:
            kw = keyword.strip()
            filt = [it for it in items if (kw in (it.get('标题') or '')) or (kw in (it.get('概要') or ''))]
            if len(filt) >= count:
                items = filt[:count]
            else:
                extras = [it for it in items if it not in filt]
                items = (filt + extras)[:count]
        # try fill cover via meta
        try:
            def find_meta_image(html, base):
                s = BeautifulSoup(html, 'html.parser')
                m = s.select_one('meta[property="og:image"], meta[name="og:image"], meta[name="twitter:image"], meta[property="twitter:image"]')
                if m and m.has_attr('content') and m['content']:
                    return m['content']
                img = s.select_one('img')
                if img and img.has_attr('src'):
                    return img['src']
                return ''
            for i in range(min(6, len(items))):
                it = items[i]
                if not it.get('封面') and it.get('原始URL','').startswith('http'):
                    try:
                        r2 = requests.get(it['原始URL'], headers=headers, timeout=5, proxies=proxies or None)
                        html2 = r2.content.decode(r2.encoding or 'utf-8', errors='ignore')
                        cover2 = find_meta_image(html2, it['原始URL'])
                        if cover2:
                            it['封面'] = cover2
                    except Exception:
                        pass
        except Exception:
            pass
        if len(items) < count:
            try:
                urlb = 'https://www.baidu.com/s'
                query_word = ('site:sc.news.cn ' + (keyword or '四川'))
                paramsb = {'rtt':'1','bsst':'1','cl':'2','tn':'news','rsv_dl':'ns_pc','word': query_word}
                rb = requests.get(urlb, params=paramsb, headers=headers, timeout=10, proxies=proxies or None, allow_redirects=True)
                alt = parse_items(rb.text)
                if not alt:
                    # 尝试新闻页解析
                    rb2 = requests.get('https://news.baidu.com/ns', params={'word': query_word, 'tn':'news', 'from':'news'}, headers=headers, timeout=10, proxies=proxies or None, allow_redirects=True)
                    alt = parse_news_items(rb2.text)
                # 过滤和限制数量
                for it in alt:
                    k = it.get('原始URL') or it.get('标题')
                    if not k or k in seen:
                        continue
                    if keyword:
                        kw = keyword.strip()
                        if kw not in (it.get('标题') or '') and kw not in (it.get('概要') or ''):
                            continue
                    it['来源'] = it.get('来源') or '新华网'
                    items.append(it)
                    seen.add(k)
                    if len(items) >= count:
                        break
            except Exception:
                pass
        # 本地库兜底：返回历史记录
        if len(items) < count and keyword:
            try:
                rows = query_all(
                    "select title as 标题, summary as 概要, cover as 封面, url as 原始URL, '新华网' as 来源 from crawl_records where (keyword like ? or title like ? or summary like ?) order by id desc limit ?",
                    [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", count - len(items)]
                )
                rows = rows or []
                for it in rows:
                    k = it.get('原始URL') or it.get('标题')
                    if not k or k in seen:
                        continue
                    items.append(it)
                    seen.add(k)
                    if len(items) >= count:
                        break
            except Exception:
                pass
        return items
    except Exception as e:
        return []

@bp.get('/crawl_xinhua')
def crawl_xinhua():
    keyword = request.args.get('keyword', '').strip()
    count = request.args.get('count', type=int) or 10
    items = collect_xinhua_items(keyword, count)
    return jsonify(items)

def run_crawler(name: str, keyword: str, count: int, config: dict = None):
    name = (name or '').strip()
    count = count or 10
    if not keyword:
        return []
    reg = {
        'baidu': collect_baidu_items,
        'xinhua': collect_xinhua_items
    }
    if name in reg:
        return reg[name](keyword, count)
    try:
        row = query_one("select * from crawlers where name = ? and enabled = 1", [name])
        if not row:
            return collect_baidu_items(keyword, count)
        module = (row.get('module') or '').strip()
        call = (row.get('callable') or 'run').strip()
        cfg_raw = config if isinstance(config, dict) else None
        if not cfg_raw:
            try:
                cfg_raw = json.loads(row.get('config') or '{}')
                if not isinstance(cfg_raw, dict):
                    cfg_raw = {}
            except Exception:
                cfg_raw = {}
        if module:
            import importlib
            m = importlib.import_module(module)
            func = getattr(m, call)
            return func(keyword, count, cfg_raw)
    except Exception:
        return collect_baidu_items(keyword, count)
    return collect_baidu_items(keyword, count)

@bp.get('/crawl_dynamic')
def crawl_dynamic():
    keyword = request.args.get('keyword', '').strip()
    count = request.args.get('count', type=int) or 10
    source = request.args.get('source', '').strip()
    items = run_crawler(source or 'baidu', keyword, count)
    return jsonify(items)

@bp.post('/save_selection')
def save_selection():
    data = request.get_json(silent=True) or {}
    keyword = data.get('keyword') or ''
    items = data.get('items') or []
    saved = []
    for it in items:
        title = it.get('标题') or it.get('title') or ''
        summary = it.get('概要') or it.get('summary') or ''
        cover = it.get('封面') or it.get('cover') or ''
        url = it.get('原始URL') or it.get('url') or ''
        source = it.get('来源') or it.get('source') or ''
        rid = execute_update(
            "insert into crawl_records(keyword, title, summary, cover, url, source) values(?, ?, ?, ?, ?, ?)",
            [keyword, title, summary, cover, url, source]
        )
        deep_text = it.get('deep_content_text')
        deep_html = it.get('deep_content_html')
        if deep_text or deep_html:
            execute_update(
                "insert into crawl_details(record_id, url, content_text, content_html) values(?, ?, ?, ?)",
                [rid, url, deep_text or '', deep_html or '']
            )
        saved.append(rid)
    return jsonify({'code': 0, 'msg': 'ok', 'ids': saved})
