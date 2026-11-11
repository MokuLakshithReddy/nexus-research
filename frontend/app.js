const API = '/api';
const state = { projects: [], selectedProject: null, sources: [], reports: [], messages: [], activeTab: 'overview', activeFilter: 'all', currentReportId: null, allSources: [], currentUser: null, authMode: 'register', activeJobId: null };
const $ = (id) => document.getElementById(id);

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}
function displayDate(value) {
  if (!value) return 'Date not listed';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}
function toast(message, error = false) {
  const node = $('toast');
  node.textContent = message;
  node.classList.toggle('error', error);
  node.classList.remove('hidden');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.add('hidden'), 4200);
}
function readCookie(name) {
  const item = document.cookie.split('; ').find(part => part.startsWith(`${name}=`));
  return item ? decodeURIComponent(item.slice(name.length + 1)) : '';
}
async function api(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(options.headers || {}) };
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers['X-CSRF-Token']) {
    const csrf = readCookie('nexus_csrf');
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  const response = await fetch(`${API}${path}`, { ...options, method, headers, credentials: 'same-origin' });
  const type = response.headers.get('content-type') || '';
  const payload = type.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const error = new Error(payload?.detail || payload?.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}
function setButtonBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    if (!button.dataset.previousLabel) button.dataset.previousLabel = button.innerHTML;
    button.innerHTML = `<span class="spinner"></span> ${label || 'Working…'}`;
    button.classList.add('loading');
  } else {
    if (button.dataset.previousLabel) button.innerHTML = button.dataset.previousLabel;
    delete button.dataset.previousLabel;
    button.classList.remove('loading');
  }
}
function showModal(title, content) {
  $('modal-title').textContent = title;
  $('modal-content').innerHTML = content;
  $('modal-backdrop').classList.remove('hidden');
}
function closeModal() { $('modal-backdrop').classList.add('hidden'); }
function nav(view) {
  document.querySelectorAll('.side-link[data-nav]').forEach((el) => el.classList.toggle('active', el.dataset.nav === view));
  $('home-view').classList.toggle('hidden', view !== 'projects');
  $('project-view').classList.add('hidden');
  $('library-view').classList.toggle('hidden', view !== 'sources');
  $('reports-view').classList.toggle('hidden', view !== 'reports');
  $('breadcrumb-current').textContent = view === 'projects' ? 'Overview' : view === 'sources' ? 'Source library' : 'Research documents';
  if (view === 'sources') loadAllSources();
  if (view === 'reports') loadAllReports();
}
function setProjectNavActive() {
  document.querySelectorAll('.side-link[data-nav]').forEach((el) => el.classList.toggle('active', el.dataset.nav === 'projects'));
}

function setAuthMode(mode) {
  state.authMode = mode;
  const register = mode === 'register';
  $('auth-mode-register').classList.toggle('active', register);
  $('auth-mode-login').classList.toggle('active', !register);
  $('auth-name-row').classList.toggle('hidden', !register);
  $('auth-name').required = register;
  $('auth-password').autocomplete = register ? 'new-password' : 'current-password';
  $('auth-heading').innerHTML = register ? 'Your research, <em>connected.</em>' : 'Welcome <em>back.</em>';
  $('auth-submit').innerHTML = register ? 'Create secure workspace <span>↗</span>' : 'Sign in to Nexus <span>↗</span>';
  $('auth-error').classList.add('hidden');
}
function showAuth(mode = 'register') {
  setAuthMode(mode);
  $('auth-screen').classList.remove('hidden');
  document.querySelector('.app-shell').classList.add('hidden');
}
function showApp(user) {
  state.currentUser = user;
  $('auth-screen').classList.add('hidden');
  document.querySelector('.app-shell').classList.remove('hidden');
  $('profile-name').textContent = user.full_name || 'Researcher';
  $('profile-email').textContent = user.email;
}
async function submitAuth(event) {
  event.preventDefault();
  const button = $('auth-submit');
  const mode = state.authMode;
  const payload = {
    email: $('auth-email').value.trim(),
    password: $('auth-password').value,
  };
  if (mode === 'register') payload.full_name = $('auth-name').value.trim();
  setButtonBusy(button, true, mode === 'register' ? 'Creating account…' : 'Signing in…');
  $('auth-error').classList.add('hidden');
  try {
    const result = await api(mode === 'register' ? '/auth/register' : '/auth/login', {
      method: 'POST', body: JSON.stringify(payload),
    });
    showApp(result.user);
    await loadProjects();
    toast(mode === 'register' ? 'Your private research workspace is ready.' : 'Welcome back.');
  } catch (error) {
    $('auth-error').textContent = error.message;
    $('auth-error').classList.remove('hidden');
  } finally {
    setButtonBusy(button, false);
  }
}
async function signOut() {
  try { await api('/auth/logout', { method: 'POST', body: '{}' }); }
  catch (error) { toast(error.message, true); }
  state.currentUser = null;
  state.projects = [];
  state.selectedProject = null;
  state.sources = [];
  state.messages = [];
  $('auth-password').value = '';
  showAuth('login');
}


async function loadProjects() {
  const payload = await api('/projects');
  state.projects = payload.projects || [];
  renderProjects();
}
function renderProjects() {
  $('project-count').textContent = state.projects.length;
  $('stat-projects').textContent = state.projects.length;
  $('stat-sources').textContent = state.projects.reduce((sum, project) => sum + Number(project.source_count || 0), 0);
  $('stat-reports').textContent = state.projects.reduce((sum, project) => sum + Number(project.report_count || 0), 0);
  $('project-grid-count').textContent = `${state.projects.length} PROJECT${state.projects.length === 1 ? '' : 'S'}`;
  $('sidebar-projects').innerHTML = state.projects.length ? state.projects.slice(0, 12).map(project => `
    <button class="sidebar-project ${state.selectedProject?.id === project.id ? 'active' : ''}" data-project-id="${project.id}" title="${escapeHtml(project.title)}">${escapeHtml(project.title)}</button>`).join('') : '<div class="sidebar-empty">Your projects will appear here.</div>';
  $('project-grid').innerHTML = state.projects.length ? state.projects.slice(0, 6).map(project => `
    <article class="project-card" data-project-id="${project.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(project.title)}">
      <div class="project-card-top"><span class="project-type">RESEARCH PROJECT</span><span class="project-arrow">↗</span></div>
      <h3>${escapeHtml(project.title)}</h3><p>${escapeHtml(project.research_question)}</p>
      <div class="project-card-meta"><span>◫ ${Number(project.source_count || 0)} sources</span><span>▤ ${Number(project.report_count || 0)} docs</span></div>
    </article>`).join('') : `
      <div class="empty-project-card"><div class="empty-orbit">✳</div><h3>Your first research starts here.</h3><p>Ask a question above. Nexus will collect academic papers and news, then keep everything organized in one workspace.</p><button class="outline-button" id="empty-start">Create a research project <span>↗</span></button></div>`;
  $('empty-start')?.addEventListener('click', () => $('research-question').focus());
  document.querySelectorAll('[data-project-id]').forEach(el => {
    el.addEventListener('click', () => openProject(Number(el.dataset.projectId)));
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') openProject(Number(el.dataset.projectId)); });
  });
}

async function openProject(projectId) {
  try {
    const payload = await api(`/projects/${projectId}`);
    state.selectedProject = payload.project;
    state.sources = payload.sources || [];
    state.messages = payload.messages || [];
    state.reports = payload.reports || [];
    state.activeTab = 'overview';
    state.currentReportId = null;
    nav('projects');
    $('home-view').classList.add('hidden');
    $('project-view').classList.remove('hidden');
    setProjectNavActive();
    $('breadcrumb-current').textContent = state.selectedProject.title;
    $('project-title').textContent = state.selectedProject.title;
    $('project-question').textContent = state.selectedProject.research_question;
    $('project-id-label').textContent = `PROJECT #${String(projectId).padStart(3, '0')}`;
    renderProject();
    renderProjects();
  } catch (error) { toast(error.message, true); }
}
function renderProject() {
  const sources = state.sources;
  $('project-source-count').textContent = sources.length;
  $('project-paper-count').textContent = sources.filter(s => s.source_type === 'research_paper').length;
  $('project-article-count').textContent = sources.filter(s => ['news', 'article'].includes(s.source_type)).length;
  $('project-updated').textContent = displayDate(state.selectedProject.updated_at || state.selectedProject.created_at);
  $('sources-tab-count').textContent = sources.length;
  $('copilot-source-count').textContent = `${sources.length} source${sources.length === 1 ? '' : 's'}`;
  renderSourceRows($('overview-sources'), sources.slice(0, 5));
  renderSourceRows($('all-sources'), filteredSources());
  renderChat();
  document.querySelectorAll('.workspace-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.tab === state.activeTab));
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('hidden', panel.id !== `tab-${state.activeTab}`));
}
function sourceIcon(type) {
  return ({ research_paper: '◈', news: '◉', video: '▷', social_post: '◎', document: '▤', article: '◫' })[type] || '◫';
}
function sourceTypeLabel(type) {
  return ({ research_paper: 'ACADEMIC', news: 'NEWS', video: 'VIDEO', social_post: 'SOCIAL', document: 'DOCUMENT', article: 'ARTICLE' })[type] || 'SOURCE';
}
function renderSourceRows(container, sources) {
  if (!container) return;
  if (!sources.length) {
    container.innerHTML = '<div class="panel-empty">No sources here yet. Run research or import a URL/document.</div>';
    return;
  }
  container.innerHTML = sources.map(source => `
    <article class="source-row">
      <div class="source-type-icon">${sourceIcon(source.source_type)}</div>
      <div>
        <div class="source-title"><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a></div>
        <div class="source-description">${escapeHtml(source.description || 'No abstract or description was supplied by this provider.')}</div>
        <div class="source-meta"><span class="source-provider">${escapeHtml(source.provider || 'source').replaceAll('_', ' ').toUpperCase()}</span><span>${sourceTypeLabel(source.source_type)}</span><span>${displayDate(source.published_at)}</span><span>REF ${source.id}</span></div>
      </div>
      <a class="source-external" href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer" title="Open original source">↗</a>
    </article>`).join('');
}
function filteredSources() {
  const query = ($('source-search')?.value || '').toLowerCase().trim();
  return state.sources.filter(s => (state.activeFilter === 'all' || s.source_type === state.activeFilter)
    && (!query || `${s.title} ${s.description} ${s.authors} ${s.provider}`.toLowerCase().includes(query)));
}
function setTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll('.workspace-tab').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(el => el.classList.toggle('hidden', el.id !== `tab-${tab}`));
}
function renderChat() {
  const box = $('chat-messages');
  if (!state.messages.length) {
    box.innerHTML = `<div class="assistant-message"><div class="assistant-mark">✳</div><div><strong>Let's investigate.</strong><p>Ask me to summarize the collection, compare sources, identify disagreements or explore a specific claim.</p><div class="suggested-prompts"><button data-prompt="Summarize the key findings across all sources.">Summarize key findings <span>↗</span></button><button data-prompt="What themes or claims appear across multiple sources?">Find recurring themes <span>↗</span></button><button data-prompt="Where do the sources disagree or leave evidence gaps?">Find contradictions <span>↗</span></button></div></div></div>`;
  } else {
    box.innerHTML = state.messages.map(message => message.role === 'user'
      ? `<div class="user-bubble">${escapeHtml(message.content)}</div>`
      : `<div class="assistant-bubble"><div class="assistant-mark">✳</div><div class="answer-content">${escapeHtml(message.content)}</div></div>`).join('');
  }
  box.scrollTop = box.scrollHeight;
  box.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => { $('chat-input').value = button.dataset.prompt; $('chat-input').focus(); }));
}
async function createResearchProject(question) {
  const trimmed = question.trim();
  if (trimmed.length < 8) return toast('Add a more specific research question first.', true);
  const title = trimmed.length > 72 ? `${trimmed.slice(0, 69).trim()}…` : trimmed;
  const button = $('start-research-button');
  setButtonBusy(button, true, 'Creating project…');
  try {
    const created = await api('/projects', { method: 'POST', body: JSON.stringify({ title, research_question: trimmed }) });
    state.selectedProject = created.project;
    const result = await api(`/projects/${created.project.id}/research`, { method: 'POST', body: JSON.stringify({ query: trimmed }) });
    await loadProjects();
    await openProject(created.project.id);
    state.activeJobId = result.job_id;
    showJobStatus('queued', 'Research job queued. The worker is preparing your source collection.');
    toast('Research queued. You can keep working while the worker collects sources.');
    monitorResearchJob(result.job_id, created.project.id);
  } catch (error) { toast(error.message, true); }
  finally { setButtonBusy(button, false); }
}
async function researchMore() {
  if (!state.selectedProject) return;
  const button = $('project-research-again');
  const projectId = state.selectedProject.id;
  setButtonBusy(button, true, 'Queueing…');
  try {
    const result = await api(`/projects/${projectId}/research`, { method: 'POST', body: JSON.stringify({ query: state.selectedProject.research_question }) });
    state.activeJobId = result.job_id;
    showJobStatus('queued', 'Research job queued. You can keep using this workspace.');
    setTab('sources');
    toast('Research added to the background queue.');
    monitorResearchJob(result.job_id, projectId);
  } catch (error) { toast(error.message, true); }
  finally { setButtonBusy(button, false); }
}
function showJobStatus(status, message) {
  const banner = $('job-status-banner');
  banner.classList.remove('hidden', 'completed', 'failed');
  if (status === 'completed') banner.classList.add('completed');
  if (status === 'failed') banner.classList.add('failed');
  $('job-status-text').textContent = message;
}
async function monitorResearchJob(jobId, projectId) {
  for (let attempt = 0; attempt < 180; attempt++) {
    try {
      const payload = await api(`/jobs/${jobId}`);
      const job = payload.job;
      const statusMessage = job.status === 'queued' ? 'Research is queued and waiting for a worker…'
        : job.status === 'running' ? `Collecting and indexing sources · attempt ${job.attempts}`
        : job.status === 'completed' ? `Completed · ${job.discovered_count} results found, ${job.added_count} new sources added.`
        : `Research failed: ${job.error_message || 'Worker could not complete this job.'}`;
      if (state.selectedProject?.id === projectId) showJobStatus(job.status, statusMessage);
      if (job.status === 'completed') {
        await loadProjects();
        if (state.selectedProject?.id === projectId) await openProject(projectId);
        toast(statusMessage);
        return;
      }
      if (job.status === 'failed') { toast(statusMessage, true); return; }
    } catch (error) {
      if (error.status === 401) { showAuth('login'); return; }
      if (state.selectedProject?.id === projectId) showJobStatus('running', 'Checking research job status…');
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  if (state.selectedProject?.id === projectId) showJobStatus('running', 'This research job is still running. Its status is saved and will update when you reopen the project.');
}
function openAddSourceModal() {
  if (!state.selectedProject) return;
  showModal('Add research material', `
    <form id="add-url-form" class="modal-form"><label>Import a webpage URL<input name="url" type="url" placeholder="https://example.com/research-article" required></label><p class="modal-help">Nexus extracts readable text from public HTML pages. Pages that require sign-in, block access, or redirect may need a direct final URL or manual document upload.</p><button class="primary-button" type="submit">Import webpage ↗</button></form>
    <div class="modal-divider"></div>
    <form id="upload-form" class="modal-form"><label>Upload a research document<input name="file" type="file" accept=".pdf,.docx,.txt,.md" required></label><p class="modal-help">PDF, DOCX, TXT or Markdown · 15 MB maximum. Extracted text is stored in this project's source library.</p><button class="outline-button" type="submit">Upload document ↑</button></form>`);
  $('add-url-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const button = event.currentTarget.querySelector('button'); setButtonBusy(button, true, 'Importing…');
    try {
      const result = await api(`/projects/${state.selectedProject.id}/sources/url`, { method: 'POST', body: JSON.stringify({ url: form.get('url') }) });
      closeModal(); await openProject(state.selectedProject.id); toast(result.message);
    } catch (error) { toast(error.message, true); setButtonBusy(button, false); }
  });
  $('upload-form').addEventListener('submit', async event => {
    event.preventDefault();
    const file = event.currentTarget.elements.file.files[0]; if (!file) return;
    const form = new FormData(); form.append('file', file);
    const button = event.currentTarget.querySelector('button'); setButtonBusy(button, true, 'Uploading…');
    try {
      const result = await api(`/projects/${state.selectedProject.id}/sources/upload`, { method: 'POST', body: form });
      closeModal(); await openProject(state.selectedProject.id); toast(result.message);
    } catch (error) { toast(error.message, true); setButtonBusy(button, false); }
  });
}
async function sendChat(message) {
  if (!state.selectedProject || !message.trim()) return;
  const input = $('chat-input'); const button = $('chat-send');
  input.value = '';
  state.messages.push({ role: 'user', content: message.trim() });
  renderChat(); button.disabled = true; button.innerHTML = '<span class="spinner"></span>';
  try {
    const result = await api(`/projects/${state.selectedProject.id}/chat`, { method: 'POST', body: JSON.stringify({ message }) });
    state.messages = result.messages || state.messages;
    renderChat();
  } catch (error) { toast(error.message, true); state.messages.pop(); renderChat(); }
  finally { button.disabled = false; button.textContent = '↑'; }
}
async function summarizeProject(button) {
  if (!state.selectedProject) return;
  setButtonBusy(button, true, 'Synthesizing…');
  try {
    const result = await api(`/projects/${state.selectedProject.id}/summarize`, { method: 'POST' });
    $('overview-synthesis').className = 'synthesis-text'; $('overview-synthesis').textContent = result.summary;
    $('insights-output').innerHTML = `<div class="synthesis-text">${escapeHtml(result.summary)}</div><p class="panel-subtitle">${result.source_count} sources considered · ${result.mode === 'openai' ? 'AI synthesis' : 'Extractive fallback — configure OPENAI_API_KEY for full model synthesis'}</p>`;
    toast(result.mode === 'openai' ? 'Evidence synthesis generated.' : 'Extractive summary generated. Add an AI key for deeper synthesis.');
  } catch (error) { toast(error.message, true); }
  finally { setButtonBusy(button, false); }
}
async function generateReport() {
  if (!state.selectedProject) return;
  const button = $('generate-report'); setButtonBusy(button, true, 'Writing draft…');
  try {
    const result = await api(`/projects/${state.selectedProject.id}/reports`, { method: 'POST', body: JSON.stringify({}) });
    state.currentReportId = result.report.id;
    await openProject(state.selectedProject.id);
    setTab('draft');
    $('report-output').innerHTML = `<div class="report-markdown">${renderMarkdown(result.report.markdown)}</div>`;
    $('report-actions').classList.remove('hidden');
    $('download-report').onclick = () => window.location.assign(`${API}/reports/${result.report.id}/download?format=md`);
    $('download-report-docx').onclick = () => window.location.assign(`${API}/reports/${result.report.id}/download?format=docx`);
    $('download-report-pdf').onclick = () => window.location.assign(`${API}/reports/${result.report.id}/download?format=pdf`);
    toast(result.mode === 'openai' ? 'Research document generated.' : 'Draft generated from source excerpts. Add OPENAI_API_KEY for a synthesized report.');
    await loadProjects();
  } catch (error) { toast(error.message, true); }
  finally { setButtonBusy(button, false); }
}
function renderMarkdown(md) {
  // Escape first; this preview intentionally supports a safe subset of Markdown.
  let safe = escapeHtml(md);
  safe = safe.replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/^## (.+)$/gm, '<h2>$1</h2>').replace(/^# (.+)$/gm, '<h1>$1</h1>');
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
  safe = safe.replace(/^\- (.+)$/gm, '• $1');
  return safe;
}
async function openConnectors() {
  try {
    const result = await api('/connectors');
    const html = (result.connectors || []).map(item => `
      <div class="connector-card"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.detail)}</small><span class="connector-status ${item.configured ? '' : 'off'}"><i class="status-dot"></i>${item.configured ? 'CONFIGURED' : 'SETUP REQUIRED'}</span></div>`).join('');
    showModal('Source connectors', `<div class="connector-grid">${html}</div><p class="modal-help" style="margin-top:14px">Add provider API keys to your backend environment to enable optional connectors. Social platforms are accessed only through supported official APIs and permitted permissions; this app does not bypass sign-in or scrape private accounts.</p><p class="modal-help">AI engine: <strong>${result.ai_configured ? 'configured' : 'not configured'}</strong>. Set OPENAI_API_KEY for full synthesis and research-grounded chat.</p><button class="outline-button" id="connectors-close-button">Done</button>`);
    $('connectors-close-button').addEventListener('click', closeModal);
  } catch (error) { toast(error.message, true); }
}
async function loadAllSources() {
  const all = [];
  for (const project of state.projects) {
    try {
      const detail = await api(`/projects/${project.id}`);
      detail.sources.forEach(source => all.push({ ...source, project_title: project.title }));
    } catch { /* keep partial library view available */ }
  }
  state.allSources = all;
  renderAllSources();
}
function renderAllSources() {
  const query = ($('library-search')?.value || '').toLowerCase().trim();
  const sources = state.allSources.filter(s => !query || `${s.title} ${s.description} ${s.project_title}`.toLowerCase().includes(query));
  $('library-count-title').textContent = `${sources.length} source${sources.length === 1 ? '' : 's'}`;
  renderSourceRows($('library-sources'), sources.map(s => ({ ...s, description: `${s.project_title} · ${s.description || ''}` })));
}
async function loadAllReports() {
  const reports = [];
  for (const project of state.projects) {
    try { const detail = await api(`/projects/${project.id}`); detail.reports.forEach(report => reports.push({ ...report, project_title: project.title })); }
    catch { /* partial view */ }
  }
  $('all-reports').innerHTML = reports.length ? reports.map(report => `<article class="report-card"><div class="eyebrow">RESEARCH DRAFT</div><h3>${escapeHtml(report.title)}</h3><p>${escapeHtml(report.project_title)} · ${displayDate(report.created_at)}</p><button class="outline-button" data-open-report-project="${report.project_id}">Open project ↗</button></article>`).join('') : `<div class="empty-project-card"><div class="empty-orbit">▤</div><h3>No documents yet.</h3><p>Open a research project and generate a referenced report from its collected sources.</p></div>`;
  document.querySelectorAll('[data-open-report-project]').forEach(button => button.addEventListener('click', () => openProject(Number(button.dataset.openReportProject)).then(() => setTab('draft'))));
}

$('research-form').addEventListener('submit', event => { event.preventDefault(); createResearchProject($('research-question').value); });
$('top-new-project').addEventListener('click', () => { nav('projects'); $('research-question').focus(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
$('side-new-project').addEventListener('click', () => { nav('projects'); $('research-question').focus(); });
$('view-all-projects').addEventListener('click', () => nav('projects'));
$('connectors-open').addEventListener('click', openConnectors);
$('modal-close').addEventListener('click', closeModal);
$('modal-backdrop').addEventListener('click', event => { if (event.target === $('modal-backdrop')) closeModal(); });
$('help-button').addEventListener('click', () => { showModal('About Nexus Research', `<p class="modal-help">Nexus is a source-grounded research workspace. It currently discovers academic works through OpenAlex, Crossref and arXiv, news through GDELT, and can optionally connect Brave Search, YouTube and X with API credentials. You can also import public webpages and PDF/DOCX/TXT/Markdown documents.</p><p class="modal-help">The project is an MVP: Instagram and Facebook connectors are not implemented yet. Collection coverage is provider-dependent, and every generated report should be checked against its original cited sources.</p><button class="outline-button" id="about-close">Close</button>`); $('about-close').addEventListener('click', closeModal); });
$('add-source-open').addEventListener('click', openAddSourceModal);
$('project-research-again').addEventListener('click', researchMore);
document.querySelectorAll('.workspace-tab').forEach(tab => tab.addEventListener('click', () => setTab(tab.dataset.tab)));
document.querySelectorAll('[data-open-tab]').forEach(button => button.addEventListener('click', () => setTab(button.dataset.openTab)));
$('overview-summarize').addEventListener('click', () => summarizeProject($('overview-summarize')));
$('generate-summary').addEventListener('click', () => summarizeProject($('generate-summary')));
$('generate-report').addEventListener('click', generateReport);
$('chat-form').addEventListener('submit', event => { event.preventDefault(); sendChat($('chat-input').value); });
$('source-search').addEventListener('input', () => renderSourceRows($('all-sources'), filteredSources()));
document.querySelectorAll('.filter-chip').forEach(button => button.addEventListener('click', () => {
  state.activeFilter = button.dataset.filter;
  document.querySelectorAll('.filter-chip').forEach(el => el.classList.toggle('active', el === button));
  renderSourceRows($('all-sources'), filteredSources());
}));
$('library-search').addEventListener('input', renderAllSources);
document.querySelectorAll('.side-link[data-nav]').forEach(button => button.addEventListener('click', () => nav(button.dataset.nav)));

$('auth-form').addEventListener('submit', submitAuth);
$('auth-mode-login').addEventListener('click', () => setAuthMode('login'));
$('auth-mode-register').addEventListener('click', () => setAuthMode('register'));
$('logout-button').addEventListener('click', signOut);

(async function init() {
  setAuthMode('register');
  try {
    await api('/health');
    const session = await api('/auth/me');
    showApp(session.user);
    const connectors = await api('/connectors');
    $('ai-status-dot').style.background = connectors.ai_configured ? '#b8e76a' : '#d9a765';
    $('ai-status-text').textContent = connectors.ai_configured
      ? (connectors.vector_search ? 'AI + semantic retrieval connected' : 'AI engine connected')
      : 'AI key required · lexical retrieval active';
    await loadProjects();
  } catch (error) {
    showAuth('register');
    if (error.status && error.status !== 401) toast(error.message, true);
  }
})();
