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

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

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

  // Lazy load on first visit
  if (tab === 'analytics') loadAnalytics();
  if (tab === 'followers') loadFollowers();
  if (tab === 'org') loadOrg();
  if (tab === 'profile') loadProfile();
  if (tab === 'posts') loadPostsOrgInfo();
}

function switchStudio(panel) {
  document.querySelectorAll('.studio-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.studio-panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`[data-studio="${panel}"]`)?.classList.add('active');
  $(`studio-${panel}`)?.classList.add('active');
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
  const { ok, data } = await apiFetch('/api/org');
  if (!ok) return;
  const org = data.org?.data || {};
  $('org-info-display').innerHTML = `
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

async function publishPost() {
  const text       = $('post-text').value.trim();
  const visibility = $('post-visibility').value;
  const draft      = $('post-draft').checked;

  if (!text) { showToast('Escreva o conteúdo do post antes de publicar', 'error'); return; }

  const btn = $('publish-post-btn');
  btn.disabled = true;
  btn.textContent = draft ? 'A guardar...' : 'A publicar...';
  $('post-result').className = 'result-box hidden';

  const { ok, data } = await apiFetch('/api/posts', {
    method: 'POST',
    body: JSON.stringify({ text, visibility, draft }),
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

async function loadAutoTopics() {
  const chipsContainer = $('auto-topics-chips');
  if (!chipsContainer) return;
  
  const { ok, data } = await apiFetch('/api/gemini/auto-topics');
  if (ok && data.topics && data.topics.length > 0) {
    cachedAutoTopics = data.topics;
    chipsContainer.innerHTML = data.topics.map((t, idx) => `
      <div class="topic-chip" onclick="selectAutoTopic(${idx})">
        <span class="chip-badge">${t.category}</span>
        <span class="chip-text">${t.topic}</span>
      </div>
    `).join('');
  } else {
    chipsContainer.innerHTML = '<span class="chip-sub">Nenhuma sugestão carregada do site.</span>';
  }
}

function selectAutoTopic(index) {
  const item = cachedAutoTopics[index];
  if (!item) return;
  $('gen-topic').value = item.topic;
  if (item.format) $('gen-format').value = item.format;
  if (item.tone) $('gen-tone').value = item.tone;
  showToast('Tema do site selecionado!', 'info');
}

async function autoGenerate1Click() {
  if (cachedAutoTopics.length === 0) {
    await loadAutoTopics();
  }
  if (cachedAutoTopics.length > 0) {
    const randomTopic = cachedAutoTopics[Math.floor(Math.random() * cachedAutoTopics.length)];
    $('gen-topic').value = randomTopic.topic;
    if (randomTopic.format) $('gen-format').value = randomTopic.format;
    if (randomTopic.tone) $('gen-tone').value = randomTopic.tone;
    showToast('Tópico sorteado do site! Gerando criativo...', 'info');
    generatePost();
  } else {
    $('gen-topic').value = "IA Generativa no SAP S/4HANA: Como extrair ROI real em 2026";
    generatePost();
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

async function generatePost() {
  const topic  = $('gen-topic').value.trim();
  const format = $('gen-format').value;
  const tone   = $('gen-tone').value;

  if (!topic) { showToast('Insira um tema para gerar o post', 'error'); return; }

  setLoading('gen-btn-text', 'gen-spinner', true, 'A gerar com Gemini (10-15s)...');
  $('gen-actions').classList.add('hidden');
  $('gen-meta').classList.add('hidden');
  $('gen-empty-state').classList.remove('hidden');
  $('gen-empty-state').innerHTML = '<div class="empty-icon" style="animation:spin 1s linear infinite">✦</div><p>Gemini 3.5 está criando o seu texto corporativo e peça visual. Por favor, aguarde...</p>';
  $('gen-output-content').classList.add('hidden');
  $('gen-text-content').textContent = "";
  $('gen-image-container').classList.add('hidden');

  const { ok, data } = await apiFetch('/api/gemini/generate-post', {
    method: 'POST',
    body: JSON.stringify({ topic, format_type: format, tone }),
  });

  setLoading('gen-btn-text', 'gen-spinner', false, '✦ Gerar Post & Imagem');

  if (ok && data.content) {
    $('gen-empty-state').classList.add('hidden');
    $('gen-output-content').classList.remove('hidden');
    
    // Inject Text
    $('gen-text-content').textContent = data.content;
    
    // Inject Image or SVG Banner
    if (data.image_base64) {
      $('gen-image-container').classList.remove('hidden');
      const isSvg = data.image_base64.startsWith('<svg') || data.image_base64.includes('xml');
      const mime = isSvg ? 'image/svg+xml' : 'image/jpeg';
      $('gen-image').src = `data:${mime};base64,${data.image_base64}`;
    } else {
      $('gen-image-container').classList.add('hidden');
    }
    
    $('gen-chars').textContent = `${data.char_count} caracteres`;
    $('gen-meta').classList.remove('hidden');
    $('gen-actions').classList.remove('hidden');
    showToast('Criativo gerado com sucesso!', 'success');
    loadDrafts(); // refresh drafts list
  } else {
    $('gen-empty-state').classList.remove('hidden');
    $('gen-empty-state').innerHTML = '<div class="empty-icon">⚠️</div><p>Erro ao gerar post. Tente novamente.</p>';
    showToast('Erro ao gerar post', 'error');
  }
}

function copyGeneratedPost() {
  const text = $('gen-text-content').textContent;
  navigator.clipboard.writeText(text).then(() => showToast('Copiado!', 'success'));
}

function sendToPostsTab() {
  const text = $('gen-text-content').textContent;
  $('post-text').value = text;
  switchTab('posts');
  showToast('Conteúdo enviado para Gestão de Posts', 'success');
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

  // Login form
  $('login-form').addEventListener('submit', doLogin);
  $('logout-btn').addEventListener('click', doLogout);

  // Nav
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Studio tabs
  document.querySelectorAll('.studio-tab').forEach(btn => {
    btn.addEventListener('click', () => switchStudio(btn.dataset.studio));
  });

  // Dashboard refresh
  $('refresh-dashboard').addEventListener('click', loadDashboard);
  $('refresh-analytics').addEventListener('click', loadAnalytics);
  $('refresh-followers').addEventListener('click', loadFollowers);
  $('refresh-org').addEventListener('click', loadOrg);
  $('refresh-profile').addEventListener('click', loadProfile);

  // Posts
  $('publish-post-btn').addEventListener('click', publishPost);
  $('open-studio-btn').addEventListener('click', () => switchTab('studio'));
  const refreshDraftsBtn = $('refresh-drafts-btn');
  if (refreshDraftsBtn) refreshDraftsBtn.addEventListener('click', loadDrafts);

  // Studio — Generate & Auto
  $('generate-post-btn').addEventListener('click', generatePost);
  const auto1ClickBtn = $('auto-generate-1click-btn');
  if (auto1ClickBtn) auto1ClickBtn.addEventListener('click', autoGenerate1Click);
  $('copy-gen-btn').addEventListener('click', copyGeneratedPost);
  $('send-to-posts-btn').addEventListener('click', sendToPostsTab);

  // Load auto topics & drafts on start if authed
  if (authed) {
    loadAutoTopics();
    loadDrafts();
  }

  // Studio — Review
  $('review-post-btn').addEventListener('click', reviewPost);

  // Studio — Strategy
  $('generate-strategy-btn').addEventListener('click', generateStrategy);

  // Studio — Hashtags
  $('generate-hashtags-btn').addEventListener('click', generateHashtags);
}

document.addEventListener('DOMContentLoaded', init);
