/* Agentic RAG 前端逻辑（纯原生 JS，无依赖） */
(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // ── 通用工具 ──────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d) ? '—' : d.toLocaleString('zh-CN', { hour12: false });
  }

  // 统一 fetch 封装：JSON 解析 + 错误提示
  async function api(path, opts = {}) {
    const cfg = Object.assign({ headers: {} }, opts);
    if (cfg.body && !(cfg.body instanceof FormData) && typeof cfg.body === 'object') {
      cfg.body = JSON.stringify(cfg.body);
      cfg.headers['Content-Type'] = 'application/json';
    }
    let resp;
    try {
      resp = await fetch(path, cfg);
    } catch (e) {
      throw new Error('网络错误，请确认后端已启动');
    }
    if (!resp.ok) {
      let msg = '请求失败 (' + resp.status + ')';
      try {
        const j = await resp.json();
        msg = j.detail || j.message || msg;
      } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    const ct = resp.headers.get('content-type') || '';
    return ct.includes('application/json') ? resp.json() : resp.text();
  }

  // ── 视图切换 ──────────────────────────────────────────
  const NAV_VIEWS = {
    search: null, kb: loadDocs, report: loadReports, dashboard: loadDashboard,
  };
  function switchView(name) {
    $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
    $$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + name));
    const loader = NAV_VIEWS[name];
    if (loader) loader();
  }
  $$('.nav-item').forEach((b) => b.addEventListener('click', () => switchView(b.dataset.view)));

  // ── 智能搜索（SSE 流式）───────────────────────────────
  const STAGE_LABEL = {
    planning: '规划子查询…',
    planned: '子查询规划完成',
    retrieval: '检索中…',
    retrieved: '检索完成',
    critic: '审查信息充分性…',
    critiqued: '审查完成',
    synthesizing: '生成答案中…',
  };
  // 多轮对话状态：每轮完整记录（问题/答案/引用/置信度/耗时/反馈），localStorage 持久化
  const MAX_HISTORY_TURNS = 4;   // 带给后端做指代消解的历史轮数上限
  const STORAGE_KEY = 'agentic_rag_chat_v1';
  let turns = [];                // [{id, question, answer, citations, confidence, latency, queryLogId, feedback, agentic}]
  let currentTurnId = null;      // 正在流式渲染的 turn id

  // Agent 流程节点图：stage → 节点 + 状态
  const NODE_BY_STAGE = {
    planning: 'planner', planned: 'planner',
    retrieval: 'retrieval', retrieved: 'retrieval',
    critic: 'critic', critiqued: 'critic',
    synthesizing: 'synthesizer',
  };
  const DONE_STAGES = { planned: 1, retrieved: 1, critiqued: 1 };

  function setNodeState(node, state) {
    const el = document.querySelector('.flow-node[data-node="' + node + '"]');
    if (!el) return;
    el.classList.remove('active', 'done');
    if (state) el.classList.add(state);
  }

  function resetFlow() {
    $$('.flow-node').forEach((el) => el.classList.remove('active', 'done'));
    const round = $('#critic-round');
    if (round) round.textContent = '';
  }

  function resetTrace() {
    $('#trace-stage').textContent = '等待检索';
    $('#trace-subqueries').textContent = '—';
    $('#trace-iterations').textContent = '—';
    $('#trace-latency').textContent = '—';
    $('#trace-confidence').textContent = '—';
    resetFlow();
  }

  function currentTurnWrap() {
    return document.querySelector('.chat-turn[data-turn-id="' + currentTurnId + '"]');
  }
  function currentTurnBody() {
    const wrap = currentTurnWrap();
    return wrap ? wrap.querySelector('.msg-assistant .msg-body') : null;
  }

  function handleStreamEvent(event, data) {
    const turn = turns.find((t) => t.id === currentTurnId);
    if (!turn) return;

    if (event === 'retrieval') {
      // trace 面板：展示最近一轮的 Agent 流程可视化
      const stage = data.stage || 'retrieval';
      $('#trace-stage').textContent = STAGE_LABEL[stage] || stage;
      if (Array.isArray(data.sub_queries)) {
        $('#trace-subqueries').textContent = data.sub_queries.length;
      } else if (typeof data.total_sub_queries === 'number') {
        $('#trace-subqueries').textContent = data.total_sub_queries;
      }
      if (typeof data.iterations === 'number') {
        $('#trace-iterations').textContent = data.iterations;
      }
      if (typeof data.chunks_retrieved === 'number') {
        $('#trace-stage').textContent = STAGE_LABEL[stage] + '（已取 ' + data.chunks_retrieved + ' 片段）';
      }
      const node = NODE_BY_STAGE[stage];
      if (node) setNodeState(node, DONE_STAGES[stage] ? 'done' : 'active');
      if (typeof data.iterations === 'number') {
        const round = $('#critic-round');
        if (round) round.textContent = data.iterations + '/3';
      }
    } else if (event === 'token') {
      // 流式期用纯文本追加，避免 markdown 半成品抖动
      turn.answer += String(data);
      const body = currentTurnBody();
      if (body) { body.classList.add('streaming'); body.textContent = turn.answer; }
    } else if (event === 'citations') {
      turn.citations = Array.isArray(data) ? data : [];
    } else if (event === 'done') {
      setNodeState('synthesizer', 'done');
      if (typeof data.confidence_score === 'number') turn.confidence = data.confidence_score;
      if (typeof data.latency_ms === 'number') turn.latency = data.latency_ms;
      turn.queryLogId = data.query_log_id;
      if (typeof data.confidence_score === 'number') {
        $('#trace-confidence').textContent = (data.confidence_score * 100).toFixed(0) + '%';
      }
      if (typeof data.latency_ms === 'number') {
        $('#trace-latency').textContent = (data.latency_ms / 1000).toFixed(1) + 's';
      }
      if (typeof data.trace === 'object' && data.trace) {
        if (Array.isArray(data.trace.sub_queries)) $('#trace-subqueries').textContent = data.trace.sub_queries.length;
        if (typeof data.trace.iterations === 'number') $('#trace-iterations').textContent = data.trace.iterations;
      }
      finalizeTurn(turn);
      currentTurnId = null;
      enableSearch(true);
    } else if (event === 'error') {
      const body = currentTurnBody();
      if (body) body.innerHTML = '<span class="msg-error">出错了：' + esc(data.message || '未知错误') + '</span>';
      finalizeTurn(turn);
      currentTurnId = null;
      enableSearch(true);
    }
  }

  function saveTurns() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(turns)); } catch (e) { /* 存储满时忽略 */ }
  }
  function loadTurns() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      turns = raw ? (JSON.parse(raw) || []) : [];
    } catch (e) { turns = []; }
  }

  function enableSearch(on) {
    const btn = $('#search-btn');
    btn.disabled = !on;
    btn.textContent = on ? '发送' : '生成中…';
  }

  // ── 对话消息渲染 ────────────────────────────────
  function showChatPlaceholder() {
    $('#chat-container').innerHTML =
      '<div class="chat-placeholder">' +
        '<div class="chat-placeholder-title">开始多轮对话</div>' +
        '<div class="chat-placeholder-desc">支持上下文追问与指代消解——先问「什么是 RRF 混合检索」，再追问「它和 BM25 是什么关系？」试试。</div>' +
      '</div>';
  }
  function hideChatPlaceholder() {
    const ph = $('#chat-container .chat-placeholder');
    if (ph) ph.remove();
  }
  function scrollToBottom() {
    const c = $('#chat-container');
    c.scrollTop = c.scrollHeight;
  }

  function buildCitationCard(c) {
    const card = document.createElement('div');
    card.className = 'citation-card';
    const title = document.createElement('div');
    title.className = 'cite-title';
    title.textContent = '《' + (c.document_title || '未知来源') + '》' + (c.section ? ' · ' + c.section : '');
    const snip = document.createElement('div');
    snip.className = 'cite-snippet';
    snip.textContent = c.content_snippet || '';
    card.appendChild(title);
    card.appendChild(snip);
    return card;
  }

  // 渲染一轮完整对话（骨架 + 已完成数据填充）
  function renderTurn(turn) {
    const container = $('#chat-container');
    const wrap = document.createElement('div');
    wrap.className = 'chat-turn';
    wrap.dataset.turnId = turn.id;

    // 用户气泡
    const userMsg = document.createElement('div');
    userMsg.className = 'msg msg-user';
    userMsg.textContent = turn.question;
    wrap.appendChild(userMsg);

    // 助手气泡
    const asst = document.createElement('div');
    asst.className = 'msg msg-assistant';

    const body = document.createElement('div');
    body.className = 'msg-body markdown-body';
    body.innerHTML = turn.answer
      ? renderMarkdown(turn.answer)
      : '<span class="msg-typing">思考中…</span>';
    asst.appendChild(body);

    const meta = document.createElement('div');
    meta.className = 'msg-meta';
    asst.appendChild(meta);

    const cites = document.createElement('div');
    cites.className = 'msg-citations';
    asst.appendChild(cites);

    const fb = document.createElement('div');
    fb.className = 'msg-feedback';
    asst.appendChild(fb);

    wrap.appendChild(asst);
    container.appendChild(wrap);

    updateTurnMeta(turn, wrap);
    renderTurnCitations(turn, wrap);
    attachTurnFeedback(turn, wrap);
    scrollToBottom();
    return wrap;
  }

  function updateTurnMeta(turn, wrap) {
    const meta = wrap.querySelector('.msg-meta');
    const conf = turn.confidence != null ? (turn.confidence * 100).toFixed(0) + '%' : '—';
    const lat = turn.latency != null ? (turn.latency / 1000).toFixed(1) + 's' : '';
    const mode = turn.agentic ? 'Agentic 多步检索' : '单轮混合检索';
    let html = '<span class="msg-mode">' + mode + '</span>' +
      '<span>置信度 <b>' + conf + '</b></span>';
    if (lat) html += '<span>耗时 <b>' + lat + '</b></span>';
    meta.innerHTML = html;
  }

  function renderTurnCitations(turn, wrap) {
    const cites = wrap.querySelector('.msg-citations');
    cites.innerHTML = '';
    (turn.citations || []).forEach((c) => cites.appendChild(buildCitationCard(c)));
  }

  function attachTurnFeedback(turn, wrap) {
    const fb = wrap.querySelector('.msg-feedback');
    fb.innerHTML = '';
    const hb = document.createElement('button');
    hb.className = 'btn-feedback' + (turn.feedback === 'helpful' ? ' active' : '');
    hb.textContent = '👍 有帮助';
    const nb = document.createElement('button');
    nb.className = 'btn-feedback' + (turn.feedback === 'not_helpful' ? ' active' : '');
    nb.textContent = '👎 没帮助';
    const result = document.createElement('span');
    result.className = 'feedback-result';

    if (turn.queryLogId != null) {
      hb.addEventListener('click', () => sendTurnFeedback(turn, 'helpful', hb, nb, result));
      nb.addEventListener('click', () => sendTurnFeedback(turn, 'not_helpful', hb, nb, result));
    } else {
      hb.disabled = true;
      nb.disabled = true;
    }
    fb.appendChild(hb);
    fb.appendChild(nb);
    fb.appendChild(result);
  }

  // 流式结束后：补全 meta / 引用 / 反馈交互，并持久化
  function finalizeTurn(turn) {
    const wrap = currentTurnWrap();
    if (wrap) {
      const body = wrap.querySelector('.msg-assistant .msg-body');
      if (body) {
        body.classList.remove('streaming');
        if (turn.answer) body.innerHTML = renderMarkdown(turn.answer);
      }
      updateTurnMeta(turn, wrap);
      renderTurnCitations(turn, wrap);
      attachTurnFeedback(turn, wrap);
    }
    saveTurns();
  }

  // 组装带历史的多轮检索请求（不含当前正在提问的轮次）
  function buildHistory() {
    const hist = [];
    const past = turns.slice(0, -1).slice(-MAX_HISTORY_TURNS);
    for (const t of past) {
      hist.push({ role: 'user', content: t.question });
      if (t.answer) hist.push({ role: 'assistant', content: t.answer });
    }
    return hist;
  }

  async function runSearch() {
    const question = $('#search-input').value.trim();
    if (!question) return;
    const useAgentic = $('#agentic-toggle').checked;

    hideChatPlaceholder();

    const turn = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      question: question,
      answer: '',
      citations: [],
      confidence: null,
      latency: null,
      queryLogId: null,
      feedback: null,
      agentic: useAgentic,
    };
    turns.push(turn);
    currentTurnId = turn.id;

    renderTurn(turn);
    resetTrace();
    enableSearch(false);
    $('#search-input').value = '';

    try {
      await streamSSE('/api/search/chat/stream', {
        question: question, top_k: 5, use_agentic: useAgentic, history: buildHistory(),
      }, handleStreamEvent);
    } catch (e) {
      const wrap = currentTurnWrap();
      if (wrap) {
        const body = wrap.querySelector('.msg-assistant .msg-body');
        if (body) body.innerHTML = '<span class="msg-error">请求失败：' + esc(e.message) + '</span>';
      }
      finalizeTurn(turn);
      currentTurnId = null;
      resetTrace();
      enableSearch(true);
    }
  }

  // 基于 fetch 的手写 SSE 客户端（POST 无法用 EventSource）
  async function streamSSE(url, body, onEvent) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      let msg = '请求失败 (' + resp.status + ')';
      try { const j = await resp.json(); msg = j.detail || msg; } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    if (!resp.body) throw new Error('浏览器不支持流式响应');

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, '\n');
      let idx;
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const evt = parseSSE(raw);
        if (evt) onEvent(evt.event, evt.data);
      }
    }
  }

  function parseSSE(raw) {
    let event = 'message';
    const dataLines = [];
    for (const line of raw.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    let data = dataLines.join('\n');
    try { data = JSON.parse(data); } catch (e) { /* 保留原始字符串 */ }
    return { event: event, data: data };
  }

  $('#search-btn').addEventListener('click', runSearch);
  $('#search-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runSearch(); }
  });

  // 用户反馈（按轮次）
  async function sendTurnFeedback(turn, feedback, hb, nb, result) {
    if (turn.queryLogId == null) return;
    try {
      await api('/api/search/feedback', {
        method: 'POST',
        body: { query_log_id: turn.queryLogId, feedback: feedback },
      });
      turn.feedback = feedback;
      saveTurns();
      hb.classList.toggle('active', feedback === 'helpful');
      nb.classList.toggle('active', feedback === 'not_helpful');
      result.textContent = '感谢反馈！';
    } catch (e) {
      result.textContent = e.message;
    }
  }

  // 清空对话
  $('#clear-chat-btn').addEventListener('click', () => {
    if (!turns.length) return;
    if (!confirm('确认清空当前对话记录？')) return;
    turns = [];
    currentTurnId = null;
    saveTurns();
    showChatPlaceholder();
    resetTrace();
  });

  // ── 知识库 ────────────────────────────────────────────
  const DOC_STATUS = {
    uploaded: ['已上传', 'badge-uploaded'], parsing: ['解析中', 'badge-parsing'],
    embedded: ['向量化中', 'badge-embedded'], ready: ['就绪', 'badge-ready'],
    error: ['失败', 'badge-error'],
  };

  async function loadDocs() {
    const tbody = $('#doc-tbody');
    try {
      const data = await api('/api/documents');
      if (!data.items.length) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="6">暂无文档，请上传</td></tr>';
        return;
      }
      tbody.innerHTML = data.items.map((d) => {
        const [label, cls] = DOC_STATUS[d.status] || [d.status, 'badge-uploaded'];
        return '<tr>' +
          '<td>' + esc(d.filename) + '</td>' +
          '<td>' + esc(d.file_type || '') + '</td>' +
          '<td><span class="badge ' + cls + '">' + label + '</span></td>' +
          '<td>' + d.total_chunks + '</td>' +
          '<td>' + esc(fmtTime(d.created_at)) + '</td>' +
          '<td><button class="btn btn-sm btn-danger" data-del="' + d.id + '">删除</button></td>' +
          '</tr>';
      }).join('');
    } catch (e) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="6">' + esc(e.message) + '</td></tr>';
    }
  }

  $('#upload-btn').addEventListener('click', () => $('#file-input').click());
  $('#file-input').addEventListener('change', async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const status = $('#kb-status');
    status.classList.remove('error');
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f));
    status.textContent = '上传中（共 ' + files.length + ' 个文件）…';
    try {
      const r = await api('/api/documents/upload-batch', { method: 'POST', body: fd });
      const ok = r.results.filter((x) => x.status === 'ready').length;
      const fail = r.results.filter((x) => x.status !== 'ready').length;
      status.textContent = '上传完成：成功 ' + ok + ' 个' + (fail ? '，失败 ' + fail + ' 个' : '');
      if (fail) status.classList.add('error');
      e.target.value = '';
      await loadDocs();
    } catch (err) {
      status.textContent = '上传失败：' + err.message;
      status.classList.add('error');
    }
  });

  $('#doc-tbody').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-del]');
    if (!btn) return;
    if (!confirm('确认删除该文档及其分片？')) return;
    try {
      await api('/api/documents/' + btn.dataset.del, { method: 'DELETE' });
      await loadDocs();
    } catch (err) {
      alert('删除失败：' + err.message);
    }
  });

  // ── 调研报告 ──────────────────────────────────────────
  const REPORT_STATUS = {
    generating: ['生成中', 'badge-generating'], ready: ['就绪', 'badge-ready'],
    failed: ['失败', 'badge-failed'],
  };
  let reportPolling = false;

  async function loadReports() {
    const tbody = $('#report-tbody');
    try {
      const data = await api('/api/reports');
      if (!data.items.length) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="6">暂无报告</td></tr>';
        return;
      }
      const hasGenerating = data.items.some((r) => r.status === 'generating');
      tbody.innerHTML = data.items.map((r) => {
        const [label, cls] = REPORT_STATUS[r.status] || [r.status, 'badge-uploaded'];
        const conf = r.confidence == null ? '—' : (r.confidence * 100).toFixed(0) + '%';
        const actions = r.status === 'ready'
          ? '<button class="btn btn-sm btn-secondary" data-view="' + r.id + '">查看</button> ' +
            '<a class="btn btn-sm btn-secondary" href="/api/reports/' + r.id + '/download">下载</a>'
          : '<button class="btn btn-sm btn-secondary" data-view="' + r.id + '" disabled>待生成</button>';
        return '<tr>' +
          '<td>' + esc(r.topic) + '</td>' +
          '<td><span class="badge ' + cls + '">' + label + (r.status === 'generating' ? ' <span class="spinner"></span>' : '') + '</span></td>' +
          '<td>' + r.depth + '</td>' +
          '<td>' + conf + '</td>' +
          '<td>' + esc(fmtTime(r.created_at)) + '</td>' +
          '<td>' + actions + '</td>' +
          '</tr>';
      }).join('');
      // 有生成中的报告则轮询
      if (hasGenerating && !reportPolling) {
        reportPolling = true;
        const timer = setInterval(async () => {
          const cur = await api('/api/reports');
          const still = cur.items.some((r) => r.status === 'generating');
          await loadReports();
          if (!still) { clearInterval(timer); reportPolling = false; }
        }, 2000);
      }
    } catch (e) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="6">' + esc(e.message) + '</td></tr>';
    }
  }

  $('#report-generate-btn').addEventListener('click', async () => {
    const topic = $('#report-topic').value.trim();
    if (!topic) { $('#report-status').textContent = '请输入调研主题'; return; }
    const depth = parseInt($('#report-depth').value, 10);
    const status = $('#report-status');
    status.textContent = '正在创建…';
    status.classList.remove('error');
    const btn = $('#report-generate-btn');
    btn.disabled = true;
    try {
      const r = await api('/api/reports/generate', { method: 'POST', body: { topic: topic, depth: depth } });
      status.textContent = '已提交，报告 #' + r.report_id + ' 正在后台生成';
      $('#report-topic').value = '';
      await loadReports();
    } catch (e) {
      status.textContent = '创建失败：' + e.message;
      status.classList.add('error');
    } finally {
      btn.disabled = false;
    }
  });

  $('#report-tbody').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-view]');
    if (!btn || btn.disabled) return;
    const id = btn.dataset.view;
    try {
      const md = await api('/api/reports/' + id + '/download');
      openReportModal(id, md);
    } catch (err) {
      alert('读取报告失败：' + err.message);
    }
  });

  function openReportModal(id, md) {
    $('#modal-title').textContent = '报告 #' + id;
    $('#modal-download').href = '/api/reports/' + id + '/download';
    $('#report-viewer').innerHTML = renderMarkdown(md);
    $('#report-modal').classList.remove('hidden');
  }
  function closeReportModal() { $('#report-modal').classList.add('hidden'); }
  $('#modal-close').addEventListener('click', closeReportModal);
  $('#modal-backdrop').addEventListener('click', closeReportModal);

  // ── 运营看板 ──────────────────────────────────────────
  async function loadDashboard() {
    try {
      const stats = await api('/api/dashboard/stats');
      $('#stat-docs').textContent = stats.document_count ?? 0;
      $('#stat-chunks').textContent = stats.chunk_count ?? 0;
      $('#stat-queries').textContent = stats.total_queries ?? 0;
      $('#stat-avg-conf').textContent = stats.avg_confidence != null ? (stats.avg_confidence * 100).toFixed(0) + '%' : '—';
    } catch (e) {
      $('#stat-docs').textContent = '—';
    }

    try {
      const hot = await api('/api/dashboard/hot-queries?limit=10');
      const hotUl = $('#hot-queries');
      if (!hot.length) { hotUl.innerHTML = '<li class="empty-row">暂无数据</li>'; }
      else {
        hotUl.innerHTML = hot.map((h) =>
          '<li><span class="hot-q">' + esc(h.question) + '</span>' +
          '<span class="hot-count">' + h.query_count + ' 次</span></li>'
        ).join('');
      }
    } catch (e) {
      $('#hot-queries').innerHTML = '<li class="empty-row">加载失败</li>';
    }

    try {
      const low = await api('/api/dashboard/low-confidence?limit=20');
      const lowUl = $('#low-confidence');
      if (!low.length) { lowUl.innerHTML = '<li class="empty-row">暂无数据</li>'; }
      else {
        lowUl.innerHTML = low.map((l) =>
          '<li><span class="low-conf-q">' + esc(l.question) + '</span>' +
          '<span class="low-conf-score">' + (l.confidence_score * 100).toFixed(0) + '%</span></li>'
        ).join('');
      }
    } catch (e) {
      $('#low-confidence').innerHTML = '<li class="empty-row">加载失败</li>';
    }
  }

  // 初始：恢复历史对话，再加载搜索视图（默认）
  loadTurns();
  if (turns.length) {
    turns.forEach((t) => renderTurn(t));
  } else {
    showChatPlaceholder();
  }
  switchView('search');
})();
