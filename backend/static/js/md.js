/* 极简 Markdown → HTML 渲染器（约百行，无依赖）
 * 支持：标题 / 加粗 / 斜体 / 列表 / 引用块 / 分割线 / 代码块 / 行内代码 / 链接
 * 安全：先转义 HTML，再套 Markdown 语法，避免注入原始标签。
 */
(function (global) {
  'use strict';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // 行内语法：行内代码 → 加粗 → 斜体 → 链接（在 HTML 已转义之后执行）
  function inline(text) {
    let t = escapeHtml(text);
    t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
    t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    return t;
  }

  function renderMarkdown(md) {
    if (md == null) return '';
    const lines = String(md).replace(/\r\n?/g, '\n').split('\n');
    let html = '';
    let para = [];           // 普通段落缓冲
    let inCode = false;      // 是否在代码块内
    let codeBuf = [];
    let listOpen = null;     // 'ul' | 'ol' | null

    const flushPara = () => {
      if (para.length) {
        html += '<p>' + inline(para.join(' ')) + '</p>';
        para = [];
      }
    };
    const closeList = () => {
      if (listOpen) { html += '</' + listOpen + '>'; listOpen = null; }
    };

    for (const line of lines) {
      // 代码块
      if (/^\s*```/.test(line)) {
        if (inCode) {
          html += '<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>';
          codeBuf = []; inCode = false;
        } else {
          flushPara(); closeList(); inCode = true;
        }
        continue;
      }
      if (inCode) { codeBuf.push(line); continue; }

      // 空行：段落与列表收尾
      if (/^\s*$/.test(line)) { flushPara(); closeList(); continue; }

      // 标题
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) { flushPara(); closeList(); const n = h[1].length; html += '<h' + n + '>' + inline(h[2]) + '</h' + n + '>'; continue; }

      // 分割线
      if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) { flushPara(); closeList(); html += '<hr>'; continue; }

      // 引用块
      const q = line.match(/^\s*>\s?(.*)$/);
      if (q) { flushPara(); closeList(); html += '<blockquote>' + inline(q[1]) + '</blockquote>'; continue; }

      // 无序列表
      const ul = line.match(/^\s*[-*+]\s+(.*)$/);
      if (ul) {
        flushPara();
        if (listOpen !== 'ul') { closeList(); html += '<ul>'; listOpen = 'ul'; }
        html += '<li>' + inline(ul[1]) + '</li>';
        continue;
      }

      // 有序列表
      const ol = line.match(/^\s*\d+\.\s+(.*)$/);
      if (ol) {
        flushPara();
        if (listOpen !== 'ol') { closeList(); html += '<ol>'; listOpen = 'ol'; }
        html += '<li>' + inline(ol[1]) + '</li>';
        continue;
      }

      // 普通段落
      closeList();
      para.push(line.trim());
    }

    if (inCode) html += '<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>';
    flushPara();
    closeList();
    return html;
  }

  global.renderMarkdown = renderMarkdown;
})(window);
