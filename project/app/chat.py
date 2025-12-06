from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from flask_socketio import emit, join_room, leave_room
from . import socketio
from .ai.chart import parse_chart_command, get_chart_data
from datetime import datetime
import requests
import json

bp = Blueprint('chat', __name__)

# Global storage for online users: {user_id: {'username': name, 'sid': sid, 'id': id}}
online_users = {}

@bp.route('/chat')
@login_required
def index():
    return render_template('chat/room.html')

@socketio.on('connect')
def on_connect():
    if current_user.is_authenticated:
        uid = current_user.id
        # Update connection info
        online_users[uid] = {
            'id': uid,
            'username': current_user.username,
            'sid': request.sid
        }
        join_room('public')
        join_room(f"user_{uid}")
        
        # Broadcast updated user list
        emit('update_user_list', list(online_users.values()), to='public')

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated:
        uid = current_user.id
        if uid in online_users:
            del online_users[uid]
        emit('update_user_list', list(online_users.values()), to='public')

@socketio.on('send_message')
def on_send_message(data):
    """
    data: {
        'content': str,
        'to_user_id': int (optional, if private)
    }
    """
    if not current_user.is_authenticated:
        return

    content = data.get('content', '').strip()
    to_uid = data.get('to_user_id')
    
    if not content:
        return

    timestamp = datetime.now().strftime('%H:%M')
    
    # Construct message payload
    msg_payload = {
        'sender': current_user.username,
        'sender_id': current_user.id,
        'time': timestamp,
        'content': content,
        'is_private': bool(to_uid),
        'recipient_id': to_uid  # Add recipient ID
    }

    # 1. Handle @AI Command
    # Trigger: Starts with "@AI" (case insensitive check for trigger, but command is case sensitive or natural)
    # Requirement: "Only support @AI + natural language command"
    # Note: If it's a private message to someone else starting with @AI, do we intercept?
    # Usually @AI is a bot interaction. If sent in private chat, it's ambiguous.
    # Assuming @AI is treated as a command regardless of context, OR only in public.
    # Given the requirements don't specify, I will allow it in both.
    
    is_ai_command = content.upper().startswith('@AI')
    
    if is_ai_command:
        # Echo the user's message first
        if to_uid:
            # Private echo
            emit('receive_message', msg_payload, room=f"user_{to_uid}")
            emit('receive_message', msg_payload, room=f"user_{current_user.id}")
        else:
            # Public echo
            emit('receive_message', msg_payload, to='public')
            
        # Generate AI Response
        cmd_content = content[3:].strip()
        ai_reply = ""
        
        if not cmd_content:
            ai_reply = "🤖 AI：未识别到有效指令，请输入如‘播放音乐’‘查询报表’等需求"
        else:
            # Flexible command parsing
            if cmd_content.startswith("电影"):
                # Movie Parsing Logic
                # Format: @AI 电影 [url] or @AI电影[url]
                url = cmd_content[2:].strip()
                if url:
                    # Construct iframe HTML
                    parse_server = "https://jx.m3u8.tv/jiexi?url="
                    full_url = f"{parse_server}{url}"
                    ai_reply = (
                        f"🤖 AI：为您解析电影资源<br>"
                        f"<iframe src='{full_url}' width='400' height='400' "
                        f"frameborder='0' allowfullscreen></iframe>"
                    )
                else:
                    ai_reply = "🤖 AI：请提供有效的视频链接，格式：@AI 电影 [URL]"
            elif cmd_content.startswith("天气"):
                # Weather Logic
                # Format: @AI 天气 [city]
                city = cmd_content[2:].strip()
                if city:
                    try:
                        # API: https://api.yaohud.cn/api/v6/weather?key=qbvOGz9XSuLh7MF3rP7=[city]
                        api_key = "qbvOGz9XSuLh7MF3rP7"
                        
                        # Strategy: Use GET request with 'location' query parameter.
                        # Tests confirmed that GET works with 'location' parameter (not 'city').
                        weather_url = "https://api.yaohud.cn/api/v6/weather"
                        params = {
                            'key': api_key,
                            'location': city
                        }
                        
                        resp = requests.get(weather_url, params=params)
                        
                        if resp.status_code == 200:
                            try:
                                data = resp.json()
                            except ValueError:
                                # JSON Parse Error
                                ai_reply = f"🤖 AI：接口返回数据异常 (非JSON格式)<br>响应内容: {resp.text[:100]}..."
                                data = None
                            
                            if data:
                                if data.get('code') == 200:
                                    w_data = data.get('data', {}).get('weather_data', {})
                                    location = data.get('data', {}).get('location_info', {})
                                    forecast = w_data.get('forecast', [])
                                    today_weather = forecast[0] if forecast else {}
                                    
                                    # Construct Weather Card HTML
                                    ai_reply = f"""
                                    <div class="weather-card">
                                        <div class="wc-header">
                                            <div class="wc-city">{location.get('city', city)}</div>
                                            <div class="wc-time">{data.get('data', {}).get('current_time', '')}</div>
                                        </div>
                                        <div class="wc-main">
                                            <div class="wc-temp">{w_data.get('wendu', 'N/A')}°C</div>
                                            <div class="wc-desc">{w_data.get('type', '')} | 空气 {w_data.get('quality', '')}</div>
                                        </div>
                                        <div class="wc-detail">
                                            <div>湿度：{w_data.get('shidu', '')}</div>
                                            <div>PM2.5：{w_data.get('pm25', '')}</div>
                                            <div>提示：{w_data.get('ganmao', '')}</div>
                                        </div>
                                        <div class="wc-grid">
                                            <div class="wc-item">
                                                <span class="wc-label">今天 ({today_weather.get('week', '')})</span>
                                                <span class="wc-val">{today_weather.get('type', '')}</span>
                                                <span class="wc-label">{today_weather.get('low', '')} ~ {today_weather.get('high', '')}</span>
                                            </div>
                                            <div class="wc-item">
                                                <span class="wc-label">风向</span>
                                                <span class="wc-val">{today_weather.get('fx', '')}</span>
                                                <span class="wc-label">{today_weather.get('fl', '')}</span>
                                            </div>
                                        </div>
                                    </div>
                                    """
                                else:
                                    ai_reply = f"🤖 AI：查询失败，{data.get('msg', '未知错误')}"
                        else:
                            ai_reply = f"🤖 AI：天气服务暂时不可用 (Status: {resp.status_code})<br>响应: {resp.text[:50]}"
                    except Exception as e:
                        ai_reply = f"🤖 AI：查询出错，{str(e)}"
                else:
                    ai_reply = "🤖 AI：请提供城市名称，格式：@AI 天气 [城市]"
            elif cmd_content.startswith("音乐"):
                # Music Logic
                # Format: @AI 音乐 [song]
                song_name = cmd_content[2:].strip()
                if song_name:
                    try:
                        # API: https://api.yaohud.cn/api/music/kuwo?key=qbvOGz9XSuLh7MF3rP7=[song]
                        # Tested: GET with msg=[song]&n=1 works best to get single song detail.
                        api_key = "qbvOGz9XSuLh7MF3rP7"
                        music_url = "https://api.yaohud.cn/api/music/kuwo"
                        params = {
                            'key': api_key,
                            'msg': song_name,
                            'n': 1
                        }
                        
                        resp = requests.get(music_url, params=params)
                        
                        if resp.status_code == 200:
                            try:
                                data = resp.json()
                            except ValueError:
                                ai_reply = f"🤖 AI：接口返回数据异常 (非JSON格式)"
                                data = None
                            
                            if data:
                                if data.get('code') == 200:
                                    song_data = data.get('data', {})
                                    # Note: API response structure varies.
                                    # Based on latest test:
                                    # name: Song Title ("稻香")
                                    # songname: Artist Name ("周杰伦") - confusing naming
                                    # vipmusic.url: Audio URL
                                    # music: Audio URL (sometimes)
                                    
                                    s_title = song_data.get('name', song_name)
                                    s_artist = song_data.get('songname', '') # Actually artist
                                    s_album = song_data.get('album', '')
                                    s_pic = song_data.get('picture', '')
                                    
                                    # Try to find URL
                                    s_url = song_data.get('music')
                                    if not s_url:
                                        s_url = song_data.get('vipmusic', {}).get('url')
                                    
                                    if s_url:
                                        # Construct Music Card HTML
                                        ai_reply = f"""
                                        <div class="music-card">
                                            <div class="mc-cover">
                                                <img src="{s_pic}" alt="Cover" onerror="this.src='https://via.placeholder.com/100?text=Music'">
                                            </div>
                                            <div class="mc-info">
                                                <div class="mc-title">{s_title}</div>
                                                <div class="mc-album">{s_artist} - {s_album}</div>
                                                <div class="mc-player">
                                                    <audio controls src="{s_url}">
                                                        您的浏览器不支持音频播放。
                                                    </audio>
                                                </div>
                                            </div>
                                        </div>
                                        """
                                    else:
                                        ai_reply = "🤖 AI：未找到可播放的音乐资源"
                                else:
                                    ai_reply = f"🤖 AI：搜索失败，{data.get('msg', '未知错误')}"
                        else:
                            ai_reply = f"🤖 AI：音乐服务暂时不可用 (Status: {resp.status_code})"
                    except Exception as e:
                        ai_reply = f"🤖 AI：查询出错，{str(e)}"
                else:
                    ai_reply = "🤖 AI：请提供歌曲名称，格式：@AI 音乐 [歌名]"
            elif cmd_content.startswith("舆情数据报表"):
                # Report Logic
                # 1. Send Loading Message (Intermediate status)
                # Since we are in a synchronous event handler, we can emit a message immediately
                # But 'ai_reply' is sent at the end of the function.
                # To support the "Loading -> Success" flow, we might need to emit the loading message first.
                
                loading_payload = {
                    'sender': 'AI',
                    'sender_id': 0,
                    'time': datetime.now().strftime('%H:%M'),
                    'content': '<div class="ai-loading">🤖 AI：已接收舆情数据报表请求，正在生成可视化图表...</div>',
                    'is_private': bool(to_uid),
                    'recipient_id': to_uid
                }
                
                if to_uid:
                    emit('receive_message', loading_payload, room=f"user_{to_uid}")
                    emit('receive_message', loading_payload, room=f"user_{current_user.id}")
                else:
                    emit('receive_message', loading_payload, to='public')

                # 2. Parse and Generate
                is_valid, err_msg, time_range, dimensions = parse_chart_command(cmd_content)
                
                if not is_valid:
                    ai_reply = f"🤖 AI：{err_msg}"
                else:
                    # 3. Fetch Data
                    try:
                        chart_data = get_chart_data(time_range, dimensions)
                        
                        # 4. Construct Card HTML
                        # Embed data in a hidden attribute or script
                        import json
                        import html
                        data_json = json.dumps(chart_data)
                        
                        # Escape JSON for HTML attribute
                        data_attr = html.escape(data_json)
                        
                        # Dimensions Preview Images (Placeholders or Icons)
                        # Requirement: "核心维度缩略图" -> We can use static icons or a placeholder div
                        
                        report_title = f"{time_range}舆情{('全维度' if len(dimensions)==4 else '多维度')}报表"
                        
                        ai_reply = f"""
                        <div class="report-card">
                            <div class="rc-header">
                                <div class="rc-title">{report_title}</div>
                                <div class="rc-time">{chart_data['generated_at']}</div>
                            </div>
                            <div class="rc-preview">
                                <!-- Placeholder for preview, maybe a static chart icon -->
                                <div class="rc-chart-icon">📊</div>
                                <div class="rc-dims">
                                    {' '.join([f'<span class="rc-tag">{d}</span>' for d in dimensions])}
                                </div>
                            </div>
                            <div class="rc-footer">
                                <button class="btn-view-report" onclick="showChartModal(this)" data-chart="{data_attr}">
                                    查看完整报表
                                </button>
                            </div>
                        </div>
                        <div class="ai-success-tip">🤖 AI：舆情数据报表生成成功</div>
                        """
                        
                    except Exception as e:
                        ai_reply = f"🤖 AI：报表生成失败，系统接口异常，请稍后重试 ({str(e)})"

            else:
                ai_reply = f"🤖 AI：已接收指令“{cmd_content}”，功能预留开发中"
            
        ai_payload = {
            'sender': 'AI',
            'sender_id': 0,
            'time': datetime.now().strftime('%H:%M'),
            'content': ai_reply,
            'is_private': bool(to_uid),
            'recipient_id': to_uid
        }
        
        if to_uid:
            # Private reply from AI (visible to both parties of the private chat?)
            # Or just to the sender? 
            # If I am chatting with Bob and say "@AI hello", Bob sees it. AI replies. Bob should see AI reply too.
            emit('receive_message', ai_payload, room=f"user_{to_uid}")
            emit('receive_message', ai_payload, room=f"user_{current_user.id}")
        else:
            emit('receive_message', ai_payload, to='public')
            
        return

    # 2. Normal Message
    if to_uid:
        # Private
        emit('receive_message', msg_payload, room=f"user_{to_uid}")
        # Also send to sender so it shows up in their view
        emit('receive_message', msg_payload, room=f"user_{current_user.id}")
    else:
        # Public
        emit('receive_message', msg_payload, to='public')

# Placeholder for future API
@bp.route('/ai/command', methods=['POST'])
@login_required
def ai_command_api():
    # user_id = request.json.get('user_id')
    # command_content = request.json.get('command_content')
    return {'code': 0, 'msg': 'Reserved'}
