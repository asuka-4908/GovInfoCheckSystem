document.addEventListener('DOMContentLoaded', function () {
  function initRipple() {
    var btns = document.querySelectorAll('.layui-btn');
    btns.forEach(function (b) {
      if (getComputedStyle(b).position === 'static') { b.style.position = 'relative' }
      var holder = b.querySelector('.ripple-holder');
      if (!holder) { holder = document.createElement('span'); holder.className = 'ripple-holder'; b.appendChild(holder) }
      b.addEventListener('click', function (e) {
        var rect = b.getBoundingClientRect();
        var x = e.clientX - rect.left;
        var y = e.clientY - rect.top;
        var r = Math.max(rect.width, rect.height);
        var el = document.createElement('span');
        el.className = 'ripple';
        el.style.width = r + 'px';
        el.style.height = r + 'px';
        el.style.left = (x - r / 2) + 'px';
        el.style.top = (y - r / 2) + 'px';
        holder.appendChild(el);
        setTimeout(function () { el.remove() }, 600);
      });
    });
  }
  function initMaskCopy() {
    var masks = document.querySelectorAll('.mask');
    masks.forEach(function (m) {
      m.style.cursor = 'copy';
      m.title = '复制隐藏值';
      m.addEventListener('click', function () {
        var t = m.textContent || '';
        try { navigator.clipboard.writeText(t) } catch (e) { }
        try { layui.layer && layui.layer.msg('已复制', { time: 800 }) } catch (e) { }
      });
    });
  }
  function initReveal() {
    var obs = new IntersectionObserver(function (es) {
      es.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('reveal') }
      });
    }, { threshold: .06 });
    document.querySelectorAll('.layui-card').forEach(function (c) { obs.observe(c) });
  }
  try { initRipple() } catch (e) { }
  try { initMaskCopy() } catch (e) { }
  try { initReveal() } catch (e) { }
});

function mdToHtml(md) {
  function esc(s) { return s.replace(/[&<>]/g, function (ch) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]) }) }
  md = (md || '').replace(/\r\n?/g, '\n');
  md = md.replace(/-{3,}\s*(##\s+)/g, '\n$1');
  md = md.replace(/-{3,}\s*(###\s+)/g, '\n$1');
  md = md.replace(/([^\n])\s*(##\s+)/g, '$1\n$2');
  md = md.replace(/([^\n])\s*(###\s+)/g, '$1\n$2');
  md = md.replace(/([^\n])\s+(-\s+)/g, '$1\n$2');
  md = md.replace(/([^\n])\s+(\d+\.\s+)/g, '$1\n$2');
  var lines = md.split(/\n/);
  var html = '';
  var inCode = false, codeBuf = []; var inUl = false, inOl = false;
  function closeLists(){ if(inUl){ html += '</ul>'; inUl = false; } if(inOl){ html += '</ol>'; inOl = false; } }
  lines.forEach(function (l) {
    if (l.trim().startsWith('```')) { if (inCode) { html += '<pre><code>' + esc(codeBuf.join('\n')) + '</code></pre>'; codeBuf = []; inCode = false; } else { closeLists(); inCode = true; } return; }
    if (inCode) { codeBuf.push(l); return; }
    if (/^\s*#\s+/.test(l)) { closeLists(); html += '<h1>' + esc(l.replace(/^\s*#\s+/, '')) + '</h1>'; return; }
    if (/^\s*##\s+/.test(l)) { closeLists(); html += '<h2>' + esc(l.replace(/^\s*##\s+/, '')) + '</h2>'; return; }
    if (/^\s*###\s+/.test(l)) { closeLists(); html += '<h3>' + esc(l.replace(/^\s*###\s+/, '')) + '</h3>'; return; }
    if (/^\s*-\s+/.test(l)) { if(!inUl){ closeLists(); html += '<ul>'; inUl = true; } html += '<li>' + esc(l.replace(/^\s*-\s+/, '')) + '</li>'; return; }
    if (/^\s*\d+\.\s+/.test(l)) { if(!inOl){ closeLists(); html += '<ol>'; inOl = true; } html += '<li>' + esc(l.replace(/^\s*\d+\.\s+/, '')) + '</li>'; return; }
    var t = esc(l).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/\*([^*]+)\*/g, '<em>$1</em>').replace(/`([^`]+)`/g, '<code>$1</code>');
    if (t.trim().length) { closeLists(); html += '<p>' + t + '</p>'; }
  });
  closeLists();
  return html;
}

function streamSSEToMarkdown(container, url) {
  if (!container || !url) return;
  container.innerHTML = '';
  try { container.style.whiteSpace = 'normal'; } catch (e) { }
  var buf = '';
  var es = new EventSource(url);
  es.onmessage = function (ev) {
    var chunk = ev.data || '';
    if (!chunk) return;
    buf += chunk;
    container.innerHTML = mdToHtml(buf);
    try { container.dataset.md = buf; } catch (e) { }
    try { container.scrollIntoView({ behavior: 'smooth', block: 'end' }); } catch (e) { }
  };
  es.onerror = function () { try { es.close(); } catch (e) { } };
  return es;
}
