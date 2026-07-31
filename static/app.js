/* app.js — VisionAI Corporate LinkedIn Manager */

const API = '';
let dashboardChart = null;
let analyticsChart = null;
let engagementChart = null;

// ═══════════════════════════════════════════════════════ UTILS

function $(id) { return document.getElementById(id); }

function showToast(msg, type = 'info', duration = 3500) {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast ${type}`;
  t.classList.remove('hidden');
  setTimeout(() => t.classList.add('hidden'), duration);
}

function setLoading(btnTextId, spinnerId, loading, text = null) {
  const btnText = $(btnTextId);
  const spinner = $(spinnerId);
  if (!btnText || !spinner) return;
  if (loading) {
    btnText.textContent = text || btnText.textContent;
    spinner.classList.remove('hidden');
    btnText.closest('button').disabled = true;
  } else {
    spinner.classList.add('hidden');
    if (text) btnText.textContent = text;
    btnText.closest('button').disabled = false;
  }
}

function formatNum(n) {
  if (n === null || n === undefined || n === '—') return '—';
  const num = Number(n);
  if (isNaN(num)) return '—';
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function formatDate(ms) {
  if (!ms) return '—';
  const d = new Date(ms);
  return d.toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' });
}

// Simple markdown-to-HTML
function mdToHtml(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hul])(.+)$/gm, (m, g) => g ? `<p>${g}</p>` : '');
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    credentials: 'include',
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

// ═══════════════════════════════════════════════════════ RADAR DE TENDÊNCIAS DA WEB & RECURSOS AVANÇADOS
let cachedWebTrends = [];
let cachedExtractedPosts = [];

async function loadWebTrends(query = '') {
  const container = $('web-trends-panel-container') || $('web-trends-container');
  const btn = $('btn-fetch-web-trends-panel') || $('btn-fetch-web-trends');
  if (!container) return;

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Escaneando Web...';
  }
  container.innerHTML = '<div class="empty-state"><p class="chip-loading">O Gemini 3.5 está varrendo as últimas notícias e artigos da internet...</p></div>';

  try {
    const url = query ? `/api/gemini/web-trends?query=${encodeURIComponent(query)}` : '/api/gemini/web-trends';
    const { ok, data } = await apiFetch(url);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '🌐 Escanear Notícias Agora';
    }

    if (ok && data.trends && Array.isArray(data.trends)) {
      cachedWebTrends = data.trends;
      container.innerHTML = data.trends.map((t, idx) => `
        <div class="card" style="border-left:4px solid #9EFF00; background: rgba(15, 23, 42, 0.85);">
          <div class="draft-header mb-2" style="display:flex; justify-content:space-between; align-items:center;">
            <span class="chip-badge" style="background:rgba(158,255,0,0.15); color:#9EFF00; padding:4px 10px; border-radius:12px; font-weight:700;">📡 ${escapeHtml(t.category || 'TENDÊNCIA')}</span>
            <button class="btn btn-primary btn-sm" onclick="generatePostFromTrend(${idx})">⚡ Gerar Post</button>
          </div>
          <h4 style="color:#ffffff; font-size:16px; margin-bottom:8px;">${escapeHtml(t.title)}</h4>
          <p style="font-size:13px; color:#94a3b8; margin-bottom:8px;">${escapeHtml(t.summary)}</p>
          <div style="font-size:12px; color:#9EFF00; font-weight:600;">💡 Impacto B2B: ${escapeHtml(t.impact_b2b || '')}</div>
        </div>
      `).join('');
      showToast('Tendências da web carregadas!', 'success');
    } else {
      container.innerHTML = '<div class="empty-state"><p>Nenhuma tendência encontrada. Tente novamente.</p></div>';
    }
  } catch (e) {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '🌐 Escanear Notícias Agora';
    }
    container.innerHTML = '<div class="empty-state"><p>Erro de conexão ao buscar notícias.</p></div>';
  }
}

function generatePostFromTrend(idx) {
  const item = cachedWebTrends[idx];
  if (!item) return;

  switchStudio('generate');
  const topicInput = $('gen-topic');
  if (topicInput) topicInput.value = item.suggested_topic || item.title;

  showToast(`Gerando post sobre tendência: ${item.title.substring(0, 30)}...`, 'info');
  generatePost();
}

async function generateCarouselPdfAction() {
  const topic = $('carousel-topic') ? $('carousel-topic').value.trim() : '';
  const count = $('carousel-slides-count') ? parseInt($('carousel-slides-count').value) : 5;
  const previewArea = $('carousel-preview-area');
  const btn = $('btn-generate-carousel');

  if (!topic) {
    showToast('Informe o tema do carrossel em PDF', 'error');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Criando slides e compondo PDF...';
  }

  try {
    const { ok, data } = await apiFetch('/api/gemini/generate-carousel', {
      method: 'POST',
      body: JSON.stringify({ topic: topic, slides_count: count })
    });

    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '📄 Gerar Carrossel em PDF';
    }

    if (ok && data.pdf_base64) {
      const pdfDataUrl = `data:application/pdf;base64,${data.pdf_base64}`;
      currentGeneratedImageBase64 = data.pdf_base64;
      currentGeneratedImageMime = 'application/pdf';

      if (previewArea) {
        previewArea.innerHTML = `
          <div class="card mb-3" style="text-align:center;">
            <h4 style="color:#9EFF00;margin-bottom:8px;">✅ Carrossel PDF Gerado (${data.slides_count} Slides)</h4>
            <p style="font-size:13px;color:#94a3b8;margin-bottom:12px;">${escapeHtml(data.title)}</p>
            <div style="display:flex;gap:8px;justify-content:center;margin-bottom:16px;">
              <a href="${pdfDataUrl}" download="carrossel-visionai.pdf" class="btn btn-primary btn-sm">📥 Baixar PDF (${data.slides_count} slides)</a>
              <button class="btn btn-secondary btn-sm" onclick="sendCarouselToCalendar()">📅 Agendar no LinkedIn</button>
            </div>
            <iframe src="${pdfDataUrl}" style="width:100%;height:450px;border:1px solid rgba(158,255,0,0.3);border-radius:12px;"></iframe>
          </div>
        `;
      }
      showToast('Carrossel PDF criado com sucesso!', 'success');
    } else {
      showToast('Erro ao gerar carrossel PDF', 'error');
    }
  } catch (e) {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '📄 Gerar Carrossel em PDF';
    }
    showToast(`Erro de conexão: ${e.message}`, 'error');
  }
}

function sendCarouselToCalendar() {
  switchTab('calendar');
  if ($('sched-topic')) $('sched-topic').value = $('carousel-topic') ? $('carousel-topic').value : 'Carrossel PDF VisionAI';
  if ($('sched-text')) $('sched-text').value = `📊 Carrossel Corporativo: ${$('carousel-topic') ? $('carousel-topic').value : ''}\n\nConfira os slides em PDF acima! #VisionAI #VisaoComputacional #EdgeAI`;
}

function useExtractedPost(idx) {
  const post = cachedExtractedPosts[idx];
  if (!post) return;

  switchStudio('generate');
  if ($('gen-topic')) $('gen-topic').value = post.topic || 'Documento Interno VisionAI';
  if ($('gen-editable-text')) $('gen-editable-text').value = post.content;
  if ($('gen-text-content')) $('gen-text-content').textContent = post.content;
  if ($('live-editor-box')) $('live-editor-box').classList.remove('hidden');
  if ($('gen-output-content')) $('gen-output-content').classList.remove('hidden');
  if ($('gen-empty-state')) $('gen-empty-state').classList.add('hidden');
  if ($('gen-actions')) $('gen-actions').classList.remove('hidden');
  showToast('Post carregado no editor principal!', 'info');
}

async function uploadDocumentFile(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);

  showToast('Processando PDF/Documento corporativo...', 'info');

  try {
    const res = await fetch(API + '/api/brand/upload-document', {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });
    const data = await res.json();
    const container = $('doc-extracted-posts-container');

    if (res.ok && data.generated_posts && data.generated_posts.length > 0) {
      cachedExtractedPosts = data.generated_posts;
      if (container) {
        container.innerHTML = data.generated_posts.map((p, idx) => `
          <div class="card mb-3" style="border-left:4px solid #0055FF; background: rgba(15, 23, 42, 0.85);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
              <span style="font-weight:700;color:#0055FF;">POST ${p.post_number || idx + 1}: ${escapeHtml(p.topic || '')}</span>
              <button class="btn btn-primary btn-sm" onclick="useExtractedPost(${idx})">⚡ Usar este Post</button>
            </div>
            <p style="font-size:12px;color:#94a3b8;margin-bottom:8px;"><strong>Ângulo:</strong> ${escapeHtml(p.angle || '')}</p>
            <div style="font-size:13px;white-space:pre-wrap;color:#f8fafc;background:rgba(0,0,0,0.3);padding:12px;border-radius:8px;">${escapeHtml(p.content || '')}</div>
          </div>
        `).join('');
      }
      showToast(`Documento extraído com sucesso! ${data.generated_posts.length} posts gerados`, 'success');
    } else {
      showToast('Erro ao processar documento', 'error');
    }
  } catch (e) {
    showToast(`Erro de conexão no upload do PDF: ${e.message}`, 'error');
  }
}

// ═══════════════════════════════════════════════════════ CALENDÁRIO & AGENDAMENTO
async function loadScheduledPosts() {
  const container = $('scheduled-posts-list');
  if (!container) return;

  const { ok, data } = await apiFetch('/api/posts/scheduled');
  if (ok && Array.isArray(data) && data.length > 0) {
    container.innerHTML = data.map(p => `
      <div class="draft-card" style="border-left: 3px solid ${p.status === 'published' ? '#9EFF00' : p.status === 'failed' ? '#ef4444' : '#3b82f6'};">
        <div class="draft-header">
          <span class="draft-topic">📅 ${escapeHtml(p.topic)}</span>
          <span class="draft-date" style="color:#9EFF00;font-weight:700;">${new Date(p.scheduled_at).toLocaleString('pt-BR')}</span>
        </div>
        <div class="draft-snippet">${escapeHtml(p.post_text ? p.post_text.substring(0, 120) + '...' : '')}</div>
        <div class="draft-actions" style="margin-top:8px;display:flex;justify-content:space-between;align-items:center;">
          <span class="badge-status ${p.status}">${p.status.toUpperCase()}</span>
          ${p.status === 'pending' ? `<button class="btn-mini danger" onclick="cancelScheduledPost(${p.id})">Cancelar Agendamento</button>` : ''}
        </div>
      </div>
    `).join('');
  } else {
    container.innerHTML = '<div class="empty-state"><p>Nenhum post agendado na fila.</p></div>';
  }
}

async function schedulePostFromCalendar() {
  const topic = $('sched-topic') ? $('sched-topic').value.trim() : '';
  const dtVal = $('sched-datetime') ? $('sched-datetime').value : '';
  const text  = $('sched-text') ? $('sched-text').value.trim() : '';

  if (!dtVal || !text) {
    showToast('Preencha a data/horário e o conteúdo do post', 'error');
    return;
  }

  const payload = {
    topic: topic || 'Post Agendado',
    text: text,
    scheduled_at: dtVal,
    image_base64: currentGeneratedImageBase64,
    image_mime: currentGeneratedImageMime,
    media_type: currentGeneratedMediaType || 'image'
  };

  const { ok, data } = await apiFetch('/api/posts/schedule', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (ok) {
    showToast('Post agendado com sucesso!', 'success');
    if ($('sched-topic')) $('sched-topic').value = '';
    if ($('sched-text')) $('sched-text').value = '';
    loadScheduledPosts();
  } else {
    showToast(`Erro ao agendar: ${data.detail || 'Falha'}`, 'error');
  }
}

async function cancelScheduledPost(id) {
  if (!confirm('Deseja cancelar este agendamento?')) return;
  const { ok } = await apiFetch(`/api/posts/scheduled/${id}`, { method: 'DELETE' });
  if (ok) {
    showToast('Agendamento cancelado', 'success');
    loadScheduledPosts();
  }
}

// Expose handlers to window scope for HTML onclick bindings
window.loadWebTrends = loadWebTrends;
window.generatePostFromTrend = generatePostFromTrend;
window.generateCarouselPdfAction = generateCarouselPdfAction;
window.sendCarouselToCalendar = sendCarouselToCalendar;
window.uploadDocumentFile = uploadDocumentFile;
window.useExtractedPost = useExtractedPost;
window.loadScheduledPosts = loadScheduledPosts;
window.schedulePostFromCalendar = schedulePostFromCalendar;
window.cancelScheduledPost = cancelScheduledPost;
window.filterTopicsByCategory = typeof filterTopicsByCategory !== 'undefined' ? filterTopicsByCategory : function(){};
window.selectAutoTopic = typeof selectAutoTopic !== 'undefined' ? selectAutoTopic : function(){};
window.autoGenerate1Click = typeof autoGenerate1Click !== 'undefined' ? autoGenerate1Click : function(){};

document.addEventListener('DOMContentLoaded', init);

// ═══════════════════════════════════════════════════════ AUTH

async function checkAuth() {
  const { data } = await apiFetch('/api/auth/status');
  return data.authenticated;
}

async function doLogin(e) {
  e.preventDefault();
  const user = $('login-user').value.trim();
  const pass = $('login-pass').value.trim();
  $('login-error').classList.add('hidden');
  setLoading('login-btn-text', null, false);
  $('login-btn').disabled = true;
  $('login-btn-text').textContent = 'A entrar...';

  const { ok } = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username: user, password: pass }),
  });

  if (ok) {
    showApp();
    loadDashboard();
    loadAutoTopics();
    loadDrafts();
  } else {
    $('login-error').classList.remove('hidden');
    $('login-btn').disabled = false;
    $('login-btn-text').textContent = 'Entrar';
  }
}

async function doLogout() {
  await apiFetch('/api/auth/logout', { method: 'POST' });
  $('app').classList.add('hidden');
  $('login-screen').classList.remove('hidden');
  $('login-pass').value = '';
}

function showApp() {
  $('login-screen').classList.add('hidden');
  $('app').classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════ NAVIGATION

function switchTab(tab) {
  document.querySelectorAll('.tab-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  $(`tab-${tab}`)?.classList.add('active');
  document.querySelector(`[data-tab="${tab}"]`)?.classList.add('active');

  // Lazy load on visit
  if (tab === 'analytics') loadAnalytics();
  if (tab === 'followers') loadFollowers();
  if (tab === 'org') loadOrg();
  if (tab === 'profile') loadProfile();
  if (tab === 'posts') { loadPostsOrgInfo(); loadDrafts(); }
  if (tab === 'studio') loadAutoTopics();
}

function switchStudio(panel) {
  document.querySelectorAll('.studio-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.studio-panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`[data-studio="${panel}"]`)?.classList.add('active');
  $(`studio-${panel}`)?.classList.add('active');

  if (panel === 'web-trends' && cachedWebTrends.length === 0) {
    loadWebTrends();
  }
}

// ═══════════════════════════════════════════════════════ DASHBOARD

async function loadDashboard() {
  $('ai-insight-text').textContent = 'A gerar insight com Gemini 3.5-flash...';
  ['kpi-followers','kpi-impressions','kpi-likes','kpi-comments','kpi-engagement']
    .forEach(id => { if($(id)) $(id).textContent = '…'; });

  const { ok, data } = await apiFetch('/api/dashboard');
  if (!ok) { showToast('Erro ao carregar dashboard', 'error'); return; }

  // KPIs
  $('kpi-followers').textContent   = formatNum(data.kpis?.followers);
  $('kpi-impressions').textContent = formatNum(data.kpis?.total_impressions_12m);
  $('kpi-likes').textContent       = formatNum(data.kpis?.total_likes_12m);
  $('kpi-comments').textContent    = formatNum(data.kpis?.total_comments_12m);
  $('kpi-engagement').textContent  = (data.kpis?.avg_engagement_pct ?? 0) + '%';

  // Sidebar
  $('sidebar-org-name').textContent   = data.org?.name || 'VisionAi';
  $('sidebar-followers').textContent  = formatNum(data.kpis?.followers);

  // AI Insight
  $('ai-insight-text').textContent = data.ai_insight || 'Sem insights disponíveis.';

  // Chart
  const monthly = data.monthly_data || [];
  const labels  = monthly.map(m => formatDate(m.period_start));
  const impressions = monthly.map(m => m.impressions);
  const likes       = monthly.map(m => m.likes);
  const comments    = monthly.map(m => m.comments);

  if (dashboardChart) dashboardChart.destroy();
  dashboardChart = new Chart($('dashboard-chart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Impressões', data: impressions, backgroundColor: 'rgba(79,126,248,0.7)', borderRadius: 4 },
        { label: 'Likes',      data: likes,       backgroundColor: 'rgba(52,211,153,0.7)', borderRadius: 4 },
        { label: 'Comentários',data: comments,    backgroundColor: 'rgba(167,139,250,0.7)', borderRadius: 4 },
      ],
    },
    options: chartOptions(),
  });
}

function chartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
    scales: {
      x: { grid: { color: '#1e2540' }, ticks: { color: '#8a95b0', font: { size: 11 } } },
      y: { grid: { color: '#1e2540' }, ticks: { color: '#8a95b0', font: { size: 11 } }, beginAtZero: true },
    },
  };
}

// ═══════════════════════════════════════════════════════ ANALYTICS

async function loadAnalytics() {
  $('analytics-ai-text').textContent = 'A gerar análise com Gemini 3.5-flash...';
  const { ok, data } = await apiFetch('/api/analytics');
  if (!ok) { showToast('Erro ao carregar analytics', 'error'); return; }

  $('analytics-ai-text').textContent = data.ai_insights || 'Sem insights disponíveis.';

  const elements = data.raw?.elements || [];
  const labels       = elements.map(e => formatDate(e.timeRange?.start));
  const impressions  = elements.map(e => e.totalShareStatistics?.impressionCount || 0);
  const engagements  = elements.map(e => parseFloat((e.totalShareStatistics?.engagement || 0) * 100).toFixed(2));

  if (analyticsChart) analyticsChart.destroy();
  analyticsChart = new Chart($('analytics-chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Impressões',
        data: impressions,
        borderColor: '#4f7ef8',
        backgroundColor: 'rgba(79,126,248,0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointBackgroundColor: '#4f7ef8',
      }],
    },
    options: chartOptions(),
  });

  if (engagementChart) engagementChart.destroy();
  engagementChart = new Chart($('engagement-chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Engagement %',
        data: engagements,
        borderColor: '#a78bfa',
        backgroundColor: 'rgba(167,139,250,0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointBackgroundColor: '#a78bfa',
      }],
    },
    options: chartOptions(),
  });
}

// ═══════════════════════════════════════════════════════ FOLLOWERS

async function loadFollowers() {
  $('total-followers-kpi').textContent = '…';
  $('followers-ai-text').textContent = 'A analisar seguidores com Gemini 3.5-flash...';
  $('followers-breakdown').innerHTML = '';

  const { ok, data } = await apiFetch('/api/followers');
  if (!ok) { showToast('Erro ao carregar seguidores', 'error'); return; }

  $('total-followers-kpi').textContent = formatNum(data.count);
  $('followers-ai-text').textContent = data.ai_analysis || 'Sem análise disponível.';

  // Render demographic breakdowns
  const stats = data.statistics?.elements?.[0] || {};
  const groups = [
    { key: 'followerCountsByIndustry',       label: 'Por Indústria',  nameKey: 'industry' },
    { key: 'followerCountsBySeniority',       label: 'Por Seniority',  nameKey: 'seniority' },
    { key: 'followerCountsByFunction',        label: 'Por Função',     nameKey: 'function' },
    { key: 'followerCountsByStaffCountRange', label: 'Por Tamanho de Empresa', nameKey: 'staffCountRange' },
  ];

  const container = $('followers-breakdown');
  groups.forEach(g => {
    const items = stats[g.key] || [];
    if (!items.length) return;
    const maxCount = Math.max(...items.map(i => (i.followerCounts?.organicFollowerCount || 0)));

    const card = document.createElement('div');
    card.className = 'followers-group-card';
    card.innerHTML = `<div class="followers-group-title">${g.label}</div>` +
      items.slice(0, 8).map(item => {
        const count = item.followerCounts?.organicFollowerCount || 0;
        const pct = maxCount > 0 ? (count / maxCount * 100) : 0;
        const nameRaw = item[g.nameKey] || '—';
        const name = nameRaw.replace('urn:li:', '').replace(/:/g, ' ').slice(0, 24);
        return `<div class="followers-group-item">
          <span class="followers-item-label">${name}</span>
          <div class="followers-bar-wrap"><div class="followers-bar" style="width:${pct}%"></div></div>
          <span class="followers-item-count">${count}</span>
        </div>`;
      }).join('');
    container.appendChild(card);
  });
}

// ═══════════════════════════════════════════════════════ ORG

async function loadOrg() {
  const { ok, data } = await apiFetch('/api/org');
  if (!ok) { showToast('Erro ao carregar organização', 'error'); return; }

  const org = data.org?.data || {};
  $('org-details').innerHTML = `
    <div class="org-info-row"><span class="org-info-label">Nome</span><span class="org-info-value">${org.localizedName || '—'}</span></div>
    <div class="org-info-row"><span class="org-info-label">Vanity URL</span><span class="org-info-value">linkedin.com/company/${org.vanityName || '—'}</span></div>
    <div class="org-info-row"><span class="org-info-label">Descrição</span><span class="org-info-value">${org.description?.localized?.pt_BR || org.description?.localized?.en_US || '—'}</span></div>
    <div class="org-info-row"><span class="org-info-label">Website</span><span class="org-info-value">${org.websiteUrl || '—'}</span></div>
    <div class="org-info-row"><span class="org-info-label">ID</span><span class="org-info-value">${org.id || '—'}</span></div>
  `;

  const admins = data.admins?.data?.elements || [];
  if (admins.length === 0) {
    $('org-admins-list').innerHTML = '<div class="text-muted" style="color:var(--text-muted);font-size:13px">Nenhum administrador encontrado</div>';
    return;
  }
  $('org-admins-list').innerHTML = admins.map(a => {
    const ra = a['roleAssignee~'] || {};
    const firstName = ra.firstName?.localized?.pt_BR || ra.firstName?.localized?.en_US || '';
    const lastName  = ra.lastName?.localized?.pt_BR  || ra.lastName?.localized?.en_US  || '';
    const initials  = (firstName[0] || '') + (lastName[0] || '') || 'A';
    return `<div class="admin-item">
      <div class="admin-avatar">${initials.toUpperCase()}</div>
      <div>
        <div class="admin-name">${firstName} ${lastName}</div>
        <div class="admin-role">Administrador</div>
      </div>
    </div>`;
  }).join('');
}

async function loadPostsOrgInfo() {
  const el = $('org-info-display');
  if (!el) return;
  const { ok, data } = await apiFetch('/api/org');
  if (!ok) return;
  const org = data.org?.data || {};
  el.innerHTML = `
    <div class="org-info-row"><span class="org-info-label">Página</span><span class="org-info-value">${org.localizedName || 'VisionAi'}</span></div>
    <div class="org-info-row"><span class="org-info-label">URL</span><span class="org-info-value">linkedin.com/company/${org.vanityName || 'visionaicombr'}</span></div>
    <div class="org-info-row"><span class="org-info-label">ID Org</span><span class="org-info-value">${org.id || '106355456'}</span></div>
  `;
}

// ═══════════════════════════════════════════════════════ PROFILE

async function loadProfile() {
  $('profile-network-size').textContent = '…';
  const { ok, data } = await apiFetch('/api/analytics/profile');
  if (!ok) { showToast('Erro ao carregar perfil', 'error'); return; }

  $('profile-network-size').textContent = formatNum(data.network_size);

  const views   = data.profile_views?.elements || [];
  const postAna = data.post_analytics?.elements || [];

  let html = '';
  if (views.length === 0 && postAna.length === 0) {
    html = '<div class="empty-state"><div class="empty-icon">📊</div><p>Sem dados de analytics disponíveis para este token</p></div>';
  } else {
    if (views.length) {
      html += '<div style="margin-bottom:16px"><div style="font-size:12px;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px;font-weight:600">Visualizações do Perfil</div>';
      html += views.slice(0, 5).map(v => `
        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">
          <span style="color:var(--text-secondary)">${formatDate(v.timeRange?.start)}</span>
          <span style="color:var(--text-primary);font-weight:600">${v.totalPageStatistics?.views?.allPageViews?.pageViews || 0} views</span>
        </div>`).join('');
      html += '</div>';
    }
    if (postAna.length) {
      html += '<div><div style="font-size:12px;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px;font-weight:600">Analytics dos Posts Pessoais</div>';
      html += JSON.stringify(postAna.slice(0, 3), null, 2);
      html += '</div>';
    }
  }
  $('profile-analytics-display').innerHTML = html;
}

// ═══════════════════════════════════════════════════════ POSTS

let currentGeneratedImageBase64 = null;
let currentGeneratedImageMime = 'image/jpeg';

async function publishPost() {
  const text       = $('post-text').value.trim();
  const visibility = $('post-visibility').value;
  const draft      = $('post-draft').checked;

  if (!text) { showToast('Escreva o conteúdo do post antes de publicar', 'error'); return; }

  const btn = $('publish-post-btn');
  btn.disabled = true;
  btn.textContent = draft ? 'A guardar...' : 'A publicar no LinkedIn...';
  $('post-result').className = 'result-box hidden';

  const payload = {
    text,
    visibility,
    draft,
    image_base64: currentGeneratedImageBase64,
    image_mime: currentGeneratedImageMime
  };

  const { ok, data } = await apiFetch('/api/posts', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  btn.disabled = false;
  btn.textContent = 'Publicar na Vizionai';

  const resultEl = $('post-result');
  resultEl.classList.remove('hidden');
  if (ok) {
    resultEl.className = 'result-box success';
    resultEl.textContent = draft
      ? '✅ Rascunho guardado com sucesso!'
      : `✅ Post publicado na página Vizionai! ${data.id ? 'ID: ' + data.id : ''}`;
    $('post-text').value = '';
    showToast('Post publicado com sucesso!', 'success');
  } else {
    resultEl.className = 'result-box error';
    resultEl.textContent = `❌ Erro: ${data.detail || data.error || 'Erro desconhecido'}`;
    showToast('Erro ao publicar post', 'error');
  }
}

// ═══════════════════════════════════════════════════════ AUTO TOPICS & DRAFTS

let cachedAutoTopics = [];
let activeCategoryFilter = '';
let topicSearchQuery = '';

async function loadAutoTopics(forceRefresh = false) {
  const chipsContainer = $('auto-topics-chips');
  const btnRefresh = $('btn-refresh-topics');
  if (!chipsContainer) return;

  if (forceRefresh) {
    if (btnRefresh) {
      btnRefresh.disabled = true;
      btnRefresh.innerHTML = '⏳ Gerando Tópicos...';
    }
    chipsContainer.innerHTML = '<span class="chip-loading">🧠 IA analisando os 6 serviços do site visionai.com.br...</span>';
  }

  let url = '/api/gemini/auto-topics';
  if (forceRefresh) url += '?refresh=true';

  const { ok, data } = await apiFetch(url);

  if (btnRefresh) {
    btnRefresh.disabled = false;
    btnRefresh.innerHTML = '🔄 Buscar Novos Tópicos';
  }

  if (ok && data.topics && data.topics.length > 0) {
    cachedAutoTopics = data.topics;
    renderAutoTopics();
    if (forceRefresh) {
      showToast('Novos tópicos gerados com sucesso!', 'success');
    }
  } else {
    chipsContainer.innerHTML = '<span class="chip-sub">Nenhuma sugestão carregada. Tente novamente.</span>';
  }
}

function renderAutoTopics() {
  const chipsContainer = $('auto-topics-chips');
  if (!chipsContainer) return;

  let filtered = cachedAutoTopics;

  if (activeCategoryFilter) {
    const catLower = activeCategoryFilter.toLowerCase();
    filtered = filtered.filter(t => (t.category || '').toLowerCase().includes(catLower));
  }

  if (topicSearchQuery) {
    const qLower = topicSearchQuery.toLowerCase();
    filtered = filtered.filter(t =>
      (t.topic || '').toLowerCase().includes(qLower) ||
      (t.category || '').toLowerCase().includes(qLower)
    );
  }

  if (filtered.length === 0) {
    chipsContainer.innerHTML = '<span class="chip-sub">Nenhum tópico encontrado para o filtro selecionado.</span>';
    return;
  }

  chipsContainer.innerHTML = filtered.map((t) => {
    const realIdx = cachedAutoTopics.indexOf(t);
    const catLabel = t.category || 'VisionAI';
    return `
      <div class="topic-chip-card" onclick="selectAutoTopic(${realIdx}, false)">
        <div class="topic-chip-header">
          <span class="chip-badge">${catLabel}</span>
          <div class="chip-actions">
            <button class="btn-chip-action btn-use" onclick="event.stopPropagation(); selectAutoTopic(${realIdx}, false)" title="Usar este tema no formulário">
              ✍️ Usar
            </button>
            <button class="btn-chip-action btn-gen" onclick="event.stopPropagation(); selectAutoTopic(${realIdx}, true)" title="Gerar post com este tema imediatamente">
              ⚡ Gerar
            </button>
          </div>
        </div>
        <div class="topic-chip-body">${t.topic}</div>
      </div>
    `;
  }).join('');
}

function filterTopicsByCategory(cat) {
  activeCategoryFilter = cat;
  const pills = document.querySelectorAll('#topics-category-filters .pill-filter');
  pills.forEach(pill => {
    const pillText = pill.innerText.trim();
    if ((!cat && pillText.startsWith('Todas')) || (cat && pillText.toLowerCase().includes(cat.toLowerCase()))) {
      pill.classList.add('active');
    } else {
      pill.classList.remove('active');
    }
  });
  renderAutoTopics();
}

function onSearchTopicsInput() {
  const input = $('topics-search-input');
  if (input) {
    topicSearchQuery = input.value.trim();
    renderAutoTopics();
  }
}

function selectAutoTopic(index, autoGenerate = false) {
  const item = cachedAutoTopics[index];
  if (!item) return;

  const topicInput = $('gen-topic');
  if (topicInput) topicInput.value = item.topic;

  if (item.format && $('gen-format')) $('gen-format').value = item.format;
  if (item.tone && $('gen-tone')) $('gen-tone').value = item.tone;

  if (autoGenerate) {
    showToast(`Gerando criativo para: ${item.category}...`, 'info');
    generatePost();
  } else {
    showToast(`Tema selecionado: ${item.category}`, 'info');
    if (topicInput) topicInput.focus();
  }
}

async function autoGenerate1Click() {
  if (cachedAutoTopics.length === 0) {
    await loadAutoTopics();
  }
  if (cachedAutoTopics.length > 0) {
    const randomIndex = Math.floor(Math.random() * cachedAutoTopics.length);
    selectAutoTopic(randomIndex, true);
  } else {
    showToast('Carregando tópicos antes de gerar...', 'info');
    await loadAutoTopics(true);
    if (cachedAutoTopics.length > 0) {
      selectAutoTopic(0, true);
    }
  }
}

async function loadDrafts() {
  const draftsContainer = $('drafts-list');
  if (!draftsContainer) return;

  const { ok, data } = await apiFetch('/api/posts/drafts');
  if (ok && Array.isArray(data) && data.length > 0) {
    draftsContainer.innerHTML = data.map(d => `
      <div class="draft-card">
        <div class="draft-header">
          <span class="draft-topic">${escapeHtml(d.topic || 'Criativo sem título')}</span>
          <span class="draft-date">${d.created_at ? new Date(d.created_at).toLocaleDateString('pt-BR') : ''}</span>
        </div>
        <div class="draft-snippet">${escapeHtml(d.post_text ? d.post_text.substring(0, 140) + '...' : '')}</div>
        <div class="draft-actions">
          <button class="btn-mini primary" onclick="useDraftText('${escapeHtml(d.post_text).replace(/'/g, "\\'")}')">Usar no Post</button>
          <button class="btn-mini danger" onclick="deleteDraftItem(${d.id})">Excluir</button>
        </div>
      </div>
    `).join('');
  } else {
    draftsContainer.innerHTML = '<div class="empty-state"><p>Nenhum rascunho guardado ainda.</p></div>';
  }
}

async function deleteDraftItem(id) {
  if (!confirm('Deseja excluir este rascunho?')) return;
  const { ok } = await apiFetch(`/api/posts/drafts/${id}`, { method: 'DELETE' });
  if (ok) {
    showToast('Rascunho excluído', 'success');
    loadDrafts();
  }
}

function useDraftText(text) {
  $('post-text').value = text;
  switchTab('posts');
  showToast('Rascunho carregado no editor!', 'success');
}

// Helper to escape HTML characters
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ═══════════════════════════════════════════════════════ GEMINI STUDIO

let currentMediaMode = 'image';
let currentGeneratedMediaType = 'image';

function updateMediaDisplay(b64, mime, mediaType = 'image') {
  const container = $('gen-image-container');
  const imgEl = $('gen-image');
  const videoEl = $('gen-video');
  const badgeEl = $('media-type-badge');

  if (!b64) {
    container.classList.add('hidden');
    imgEl.classList.add('hidden');
    videoEl.classList.add('hidden');
    currentGeneratedImageBase64 = null;
    return;
  }

  container.classList.remove('hidden');
  currentGeneratedImageBase64 = b64;
  currentGeneratedImageMime = mime;
  currentGeneratedMediaType = mediaType;

  const isVideo = mediaType === 'video' || (mime && mime.includes('video'));

  if (isVideo) {
    imgEl.classList.add('hidden');
    videoEl.classList.remove('hidden');
    videoEl.src = `data:${mime};base64,${b64}`;
    if (badgeEl) badgeEl.textContent = '🎬 Vídeo Criativo Gerado para a VisionAi';
  } else {
    videoEl.classList.add('hidden');
    imgEl.classList.remove('hidden');
    const isSvg = b64.startsWith('<svg') || b64.includes('xml');
    const actualMime = mime || (isSvg ? 'image/svg+xml' : 'image/jpeg');
    imgEl.src = `data:${actualMime};base64,${b64}`;
    if (badgeEl) badgeEl.textContent = '✨ Criativo Visual Gerado para a VisionAi';
  }
}

async function generatePost() {
  const topic  = $('gen-topic').value.trim();
  const format = $('gen-format').value;
  const tone   = $('gen-tone').value;

  if (!topic) { showToast('Insira um tema para gerar o post', 'error'); return; }

  setLoading('gen-btn-text', 'gen-spinner', true, 'A gerar com Gemini (10-15s)...');
  $('gen-actions').classList.add('hidden');
  $('gen-meta').classList.add('hidden');
  if ($('live-editor-box')) $('live-editor-box').classList.add('hidden');
  $('gen-empty-state').classList.remove('hidden');
  $('gen-empty-state').innerHTML = '<div class="empty-icon" style="animation:spin 1s linear infinite">✦</div><p>Gemini 3.5 está criando o seu texto corporativo e peça visual. Por favor, aguarde...</p>';
  $('gen-output-content').classList.add('hidden');
  $('gen-text-content').textContent = "";
  $('gen-image-container').classList.add('hidden');

  const { ok, data } = await apiFetch('/api/gemini/generate-post', {
    method: 'POST',
    body: JSON.stringify({ topic, format_type: format, tone, media_type: currentMediaMode }),
  });

  setLoading('gen-btn-text', 'gen-spinner', false, '✦ Gerar Post & Criativo Visual');

  if (ok && data.content) {
    $('gen-empty-state').classList.add('hidden');
    $('gen-output-content').classList.remove('hidden');
    
    // Inject Text
    $('gen-text-content').textContent = data.content;
    if ($('gen-editable-text')) {
      $('gen-editable-text').value = data.content;
      $('live-editor-box').classList.remove('hidden');
    }
    
    // Inject Image or Video
    updateMediaDisplay(data.image_base64, data.image_mime, data.media_type || currentMediaMode);
    
    $('gen-chars').textContent = `${data.char_count || data.content.length} caracteres`;
    $('gen-meta').classList.remove('hidden');
    $('gen-actions').classList.remove('hidden');
    showToast('Criativo gerado com sucesso!', 'success');
    loadDrafts();
  } else {
    $('gen-empty-state').classList.remove('hidden');
    $('gen-empty-state').innerHTML = '<div class="empty-icon">⚠️</div><p>Erro ao gerar post. Tente novamente.</p>';
    showToast('Erro ao gerar post', 'error');
  }
}

async function regenerateMediaFromText() {
  const revisedText = $('gen-editable-text').value.trim();
  if (!revisedText) { showToast('Escreva ou revise o texto antes de re-gerar a mídia', 'error'); return; }

  const btn = $('regenerate-media-btn');
  btn.disabled = true;
  btn.textContent = '🔄 Re-gerando mídia...';

  try {
    const { ok, data } = await apiFetch('/api/gemini/regenerate-media', {
      method: 'POST',
      body: JSON.stringify({ revised_text: revisedText, media_type: currentMediaMode }),
    });

    btn.disabled = false;
    btn.textContent = '🔄 Re-gerar Mídia com Texto Revisado';

    if (ok && data.image_base64) {
      updateMediaDisplay(data.image_base64, data.image_mime, data.media_type || currentMediaMode);
      showToast('Mídia re-gerada e sincronizada!', 'success');
    } else {
      showToast('Erro ao re-gerar mídia', 'error');
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = '🔄 Re-gerar Mídia com Texto Revisado';
    showToast('Erro ao re-gerar mídia', 'error');
  }
}

async function uploadCustomMediaFile(file) {
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  showToast('Enviando mídia...', 'info');

  try {
    const res = await fetch(API + '/api/media/upload', {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });
    const data = await res.json();
    if (res.ok && data.media_b64) {
      updateMediaDisplay(data.media_b64, data.media_mime, data.media_type);
      showToast(`Mídia carregada com sucesso (${data.filename})!`, 'success');
    } else {
      showToast('Erro no upload da mídia', 'error');
    }
  } catch (e) {
    showToast(`Erro de conexão no upload: ${e.message}`, 'error');
  }
}

function copyGeneratedPost() {
  const text = $('gen-editable-text') ? $('gen-editable-text').value : $('gen-text-content').textContent;
  if (!text) { showToast('Nenhum post gerado para copiar', 'error'); return; }
  navigator.clipboard.writeText(text).then(() => showToast('Copiado!', 'success'));
}

function sendToPostsTab() {
  const text = $('gen-editable-text') ? $('gen-editable-text').value : $('gen-text-content').textContent;
  if (!text) { showToast('Nenhum post gerado para enviar', 'error'); return; }
  if ($('post-text')) $('post-text').value = text;
  switchTab('posts');
  showToast('Conteúdo e mídia salvos na Gestão de Posts', 'success');
}

async function publishGeneratedPostDirectly() {
  const text = $('gen-editable-text') ? $('gen-editable-text').value.trim() : $('gen-text-content').textContent.trim();
  if (!text) { showToast('Gere um post primeiro antes de publicar', 'error'); return; }

  const btn = $('publish-direct-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '🚀 Publicando no LinkedIn...';
  }

  const payload = {
    text,
    visibility: 'PUBLIC',
    draft: false,
    image_base64: currentGeneratedImageBase64,
    image_mime: currentGeneratedImageMime,
    media_type: currentGeneratedMediaType
  };

  const { ok, data } = await apiFetch('/api/posts', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  if (btn) {
    btn.disabled = false;
    btn.textContent = '🚀 Publicar no LinkedIn';
  }

  if (ok && (data.id || data.ok)) {
    showToast('🎉 Post publicado na página da VisionAI no LinkedIn!', 'success');
    alert(`🎉 Sucesso!\nPost publicado na página da VisionAI no LinkedIn!\nID do Post: ${data.id || 'Confirmado'}`);
  } else {
    const err = data.detail || data.error || 'Falha ao comunicar com API LinkedIn';
    showToast(`Erro ao publicar: ${err}`, 'error');
    alert(`❌ Erro ao publicar no LinkedIn:\n${err}`);
  }
}

async function reviewPost() {
  const draft = $('review-draft').value.trim();
  if (!draft) { showToast('Cole um rascunho para analisar', 'error'); return; }

  setLoading('review-btn-text', 'review-spinner', true, 'A analisar com Gemini...');
  $('review-output').innerHTML = '<div class="empty-state"><div class="empty-icon" style="animation:spin 1s linear infinite">🔍</div><p>Gemini está a analisar...</p></div>';

  const { ok, data } = await apiFetch('/api/gemini/review-post', {
    method: 'POST',
    body: JSON.stringify({ draft }),
  });

  setLoading('review-btn-text', 'review-spinner', false, '✦ Analisar com Gemini');

  if (!ok) { showToast('Erro na análise', 'error'); return; }

  if (data.score !== undefined) {
    $('review-output').innerHTML = `
      <div class="review-card">
        <div class="review-label">Pontuação</div>
        <div class="review-score">${data.score}<span style="font-size:16px;color:var(--text-muted)">/10</span></div>
      </div>
      <div class="review-card">
        <div class="review-section-title">✅ Pontos Fortes</div>
        <ul class="review-list">${(data.strengths || []).map(s => `<li>${s}</li>`).join('')}</ul>
      </div>
      <div class="review-card">
        <div class="review-section-title">🔧 Melhorias</div>
        <ul class="review-list">${(data.improvements || []).map(i => `<li>${i}</li>`).join('')}</ul>
      </div>
      <div class="review-card">
        <div class="review-section-title">✦ Versão Melhorada pelo Gemini</div>
        <div class="review-improved">${data.improved_version || '—'}</div>
      </div>
    `;
  } else {
    $('review-output').innerHTML = `<div class="review-card"><div class="review-improved">${data.raw || '—'}</div></div>`;
  }
  showToast('Análise concluída!', 'success');
}

async function generateStrategy() {
  const period = parseInt($('strategy-period').value);
  setLoading('strategy-btn-text', 'strategy-spinner', true, 'A gerar estratégia...');
  $('strategy-output').innerHTML = '<div class="empty-state"><div class="empty-icon" style="animation:spin 1s linear infinite">📅</div><p>Gemini está a construir o seu plano editorial...</p></div>';

  const { ok, data } = await apiFetch('/api/gemini/content-strategy', {
    method: 'POST',
    body: JSON.stringify({ period_days: period }),
  });

  setLoading('strategy-btn-text', 'strategy-spinner', false, '✦ Gerar Estratégia');

  if (!ok || data.raw) {
    $('strategy-output').innerHTML = `<div class="review-card"><div class="review-improved">${data.raw || 'Erro ao gerar estratégia'}</div></div>`;
    return;
  }

  const pillarsHtml = (data.content_pillars || []).map(p => `
    <div class="strategy-pillar">
      <div class="pillar-name">${p.pillar}</div>
      <div class="pillar-bar-wrap"><div class="pillar-bar" style="width:${p.percentage}%"></div></div>
      <div class="pillar-pct">${p.percentage}%</div>
      <div class="pillar-rationale">${p.rationale}</div>
    </div>`).join('');

  const ideasHtml = (data.post_ideas || []).map(i => `
    <div class="post-idea-card">
      <div class="idea-week">Semana ${i.week}</div>
      <div class="idea-topic">${i.topic}</div>
      <div class="idea-format">${i.format}</div>
      <div class="idea-hook">"${i.hook}"</div>
    </div>`).join('');

  const hashtagsHtml = (data.hashtag_strategy || []).map(h => `<span class="hashtag-chip">${h}</span>`).join('');

  $('strategy-output').innerHTML = `
    <div class="strategy-summary">${data.strategy_summary || ''}</div>
    <div style="font-size:12px;text-transform:uppercase;color:var(--text-muted);font-weight:600;margin-bottom:12px">Pilares de Conteúdo</div>
    <div class="strategy-grid">${pillarsHtml}</div>
    <div style="font-size:12px;text-transform:uppercase;color:var(--text-muted);font-weight:600;margin:20px 0 12px">Ideias de Posts</div>
    ${ideasHtml}
    <div style="font-size:12px;text-transform:uppercase;color:var(--text-muted);font-weight:600;margin:16px 0 10px">Hashtags Recomendadas</div>
    <div class="hashtags-output" style="display:flex">${hashtagsHtml}</div>
  `;
  showToast('Estratégia gerada!', 'success');
}

async function generateHashtags() {
  const topic = $('hashtag-topic').value.trim();
  const count = parseInt($('hashtag-count').value) || 8;
  if (!topic) { showToast('Insira um tema', 'error'); return; }

  setLoading('hashtags-btn-text', 'hashtags-spinner', true, 'A gerar...');
  $('hashtags-output').classList.add('hidden');

  const { ok, data } = await apiFetch('/api/gemini/hashtags', {
    method: 'POST',
    body: JSON.stringify({ topic, count }),
  });

  setLoading('hashtags-btn-text', 'hashtags-spinner', false, '✦ Gerar Hashtags com Gemini');

  if (!ok) { showToast('Erro ao gerar hashtags', 'error'); return; }

  const hashtags = data.hashtags || [];
  $('hashtags-output').innerHTML = hashtags.map(h => `
    <span class="hashtag-chip" onclick="navigator.clipboard.writeText('${h}').then(()=>showToast('${h} copiado!','success'))">${h}</span>
  `).join('');
  $('hashtags-output').classList.remove('hidden');
  showToast(`${hashtags.length} hashtags geradas!`, 'success');
}

// ═══════════════════════════════════════════════════════ INIT

async function init() {
  // Check auth
  const authed = await checkAuth();
  if (authed) {
    showApp();
    loadDashboard();
  } else {
    $('login-screen').classList.remove('hidden');
  }

  const addEv = (id, event, fn) => {
    const el = $(id);
    if (el) el.addEventListener(event, fn);
  };

  // Login & Logout
  addEv('login-form', 'submit', doLogin);
  addEv('logout-btn', 'click', doLogout);

  // Nav
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Studio tabs
  document.querySelectorAll('.studio-tab').forEach(btn => {
    btn.addEventListener('click', () => switchStudio(btn.dataset.studio));
  });

  // Dashboard & Refresh Buttons
  addEv('refresh-dashboard', 'click', loadDashboard);
  addEv('refresh-analytics', 'click', loadAnalytics);
  addEv('refresh-followers', 'click', loadFollowers);
  addEv('refresh-org', 'click', loadOrg);
  addEv('refresh-profile', 'click', loadProfile);
  addEv('publish-post-btn', 'click', publishPost);
  addEv('open-studio-btn', 'click', () => switchTab('studio'));
  addEv('refresh-drafts-btn', 'click', loadDrafts);

  // Studio — Generate & Auto
  addEv('generate-post-btn', 'click', generatePost);
  addEv('auto-generate-1click-btn', 'click', autoGenerate1Click);
  addEv('copy-gen-btn', 'click', copyGeneratedPost);
  addEv('send-to-posts-btn', 'click', sendToPostsTab);
  addEv('publish-direct-btn', 'click', publishGeneratedPostDirectly);
  addEv('review-post-btn', 'click', reviewPost);
  addEv('generate-strategy-btn', 'click', generateStrategy);
  addEv('generate-hashtags-btn', 'click', generateHashtags);

  // Media Mode Tabs (Image / Video / Custom Upload)
  document.querySelectorAll('.media-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.media-tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentMediaMode = btn.dataset.mediaType || 'image';
      const customUploadBox = $('custom-upload-box');
      const docUploadBox = $('doc-upload-box');

      if (customUploadBox) customUploadBox.classList.add('hidden');
      if (docUploadBox) docUploadBox.classList.add('hidden');

      if (currentMediaMode === 'custom') {
        if (customUploadBox) customUploadBox.classList.remove('hidden');
      } else if (currentMediaMode === 'doc') {
        if (docUploadBox) docUploadBox.classList.remove('hidden');
      }
    });
  });

  // Custom File & Doc Upload Listeners
  const triggerFileBtn = $('trigger-file-btn');
  const customFileInput = $('custom-file-input');
  if (triggerFileBtn && customFileInput) {
    triggerFileBtn.addEventListener('click', () => customFileInput.click());
    customFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadCustomMediaFile(e.target.files[0]);
      }
    });
  }

  const triggerDocFileBtn = $('trigger-doc-file-btn');
  const docFileInput = $('doc-file-input');
  if (triggerDocFileBtn && docFileInput) {
    triggerDocFileBtn.addEventListener('click', () => docFileInput.click());
    docFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadDocumentFile(e.target.files[0]);
      }
    });
  }

  const docPanelFileInput = $('doc-panel-file-input');
  if (docPanelFileInput) {
    docPanelFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadDocumentFile(e.target.files[0]);
      }
    });
  }

  // Live Text Canvas Editor Sync & Regenerate Media Button
  const editableTextEl = $('gen-editable-text');
  if (editableTextEl) {
    editableTextEl.addEventListener('input', (e) => {
      const val = e.target.value;
      if ($('gen-text-content')) $('gen-text-content').textContent = val;
      if ($('gen-chars')) $('gen-chars').textContent = `${val.length} caracteres`;
    });
  }
  addEv('regenerate-media-btn', 'click', regenerateMediaFromText);

  // Load auto topics, web trends & drafts on start if authed
  if (authed) {
    loadAutoTopics();
    loadDrafts();
    loadScheduledPosts();
  }

  // Studio — Strategy & Hashtags
  addEv('generate-strategy-btn', 'click', generateStrategy);
  addEv('generate-hashtags-btn', 'click', generateHashtags);
}
