from flask import Blueprint, request, jsonify
import requests
from bs4 import BeautifulSoup

bp = Blueprint('crawler', __name__, url_prefix='/api')

def parse_items(html):
    soup = BeautifulSoup(html, 'lxml')
    items = []
    for res in soup.select('div.result'):
        title_tag = res.select_one('h3 a') or res.select_one('a')
        title = title_tag.get_text(strip=True) if title_tag else ''
        href = title_tag['href'] if title_tag and title_tag.has_attr('href') else ''
        summary_tag = res.select_one('.c-line-clamp3') or res.select_one('.c-abstract') or res.select_one('div')
        summary = summary_tag.get_text(strip=True) if summary_tag else ''
        source_tag = res.select_one('.c-author') or res.select_one('.news-source') or res.select_one('span')
        source = source_tag.get_text(strip=True) if source_tag else ''
        img_tag = res.select_one('img')
        cover = img_tag['src'] if img_tag and img_tag.has_attr('src') else ''
        if title or href:
            items.append({'标题': title, '概要': summary, '封面': cover, '原始URL': href, '来源': source})
    if not items:
        for a in soup.select('h3 a'):
            title = a.get_text(strip=True)
            href = a.get('href', '')
            items.append({'标题': title, '概要': '', '封面': '', '原始URL': href, '来源': ''})
    return items

@bp.get('/crawl')
def crawl():
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify([])
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
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    items = parse_items(resp.text)
    return jsonify(items)

