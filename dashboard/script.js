// --- HELPERS ANTI-XSS ---
function escapeHtml(input) {
    if (input === null || input === undefined) return '';
    return String(input)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function safeUrl(url) {
    // Permite http(s) y mailto; bloquea javascript:, data:, etc.
    const s = String(url || '').trim();
    if (/^(https?:|mailto:)/i.test(s)) return s;
    return '#';
}

async function fetchWithTimeout(url, opts = {}, timeoutMs = 8000) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
        return await fetch(url, { ...opts, signal: ctrl.signal });
    } finally {
        clearTimeout(t);
    }
}


// --- NAVEGACIÓN POR PESTAÑAS ---
function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.sidebar .nav-link').forEach(l => l.classList.remove('active'));

    document.getElementById('tab-' + tabId).style.display = 'block';
    document.getElementById('btn-' + tabId).classList.add('active');

    if (tabId === 'resumen') renderCharts();
}

// --- CONFIGURACIÓN Y ESTADO ---
let commentsData = [];
const CSV_COMMENTS = '../output/comments_analizados.csv';
const CSV_POSTS = '../output/posts_summary.csv';
const API_BASE = '/api';

let sentimentChart = null;
let postsChart = null;
let allPostsData = [];
const THEME_STORAGE_KEY = 'dashboard-theme';

const COLORS = {
    pos: '#00e676',
    neu: '#4facfe',
    neg: '#f857a6',
    warm: '#facc15'
};

function updateThemeButton(isLight) {
    const iconEl = document.getElementById('theme-toggle-icon');
    const labelEl = document.getElementById('theme-toggle-label');
    if (!iconEl || !labelEl) return;

    iconEl.className = isLight ? 'ph-bold ph-sun' : 'ph-bold ph-moon';
    labelEl.innerText = isLight ? 'Modo Claro' : 'Modo Oscuro';
}

function applyTheme(theme) {
    const isLight = theme === 'light';
    document.body.classList.toggle('light-mode', isLight);
    updateThemeButton(isLight);
}

function toggleTheme() {
    const isCurrentlyLight = document.body.classList.contains('light-mode');
    const nextTheme = isCurrentlyLight ? 'dark' : 'light';
    applyTheme(nextTheme);
    localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
}

function initTheme() {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    applyTheme(savedTheme === 'light' ? 'light' : 'dark');
}

function showLoadError(msg) {
    console.error(msg);
    const banner = document.createElement('div');
    banner.style.cssText = 'position:fixed;top:10px;right:10px;z-index:9999;background:#f857a6;color:#fff;padding:12px 16px;border-radius:8px;max-width:360px;font-size:0.85rem;box-shadow:0 4px 20px rgba(0,0,0,0.3);';
    banner.textContent = msg;
    document.body.appendChild(banner);
    setTimeout(() => banner.remove(), 8000);
}

// Cargar Datos
async function loadData() {
    try {
        const resPosts = await fetch(CSV_POSTS);
        if (!resPosts.ok) throw new Error(`No se pudo cargar ${CSV_POSTS} (${resPosts.status})`);
        const postsText = await resPosts.text();
        allPostsData = Papa.parse(postsText, { header: true, skipEmptyLines: true }).data;

        const resComms = await fetch(CSV_COMMENTS);
        if (!resComms.ok) throw new Error(`No se pudo cargar ${CSV_COMMENTS} (${resComms.status})`);
        const commsText = await resComms.text();
        commentsData = Papa.parse(commsText, { header: true, skipEmptyLines: true }).data;

        console.log("Posts cargados:", allPostsData.length);
        console.log("Comentarios cargados:", commentsData.length);

        initDashboard();
    } catch (e) {
        showLoadError(`Error cargando CSVs: ${e.message}. Ejecuta primero scraper.py y analizador.py.`);
        initDashboard();
    }
}

function initDashboard() {
    updateKPIs();
    renderCharts();
    renderPostsTable();
    renderTempExamples();

    document.getElementById('sim-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') testComment();
    });
}

function normalizeText(text) {
    return (text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/\s+/g, " ")
        .trim();
}

function findLocalAnalysis(inputText) {
    const target = normalizeText(inputText);
    if (!target) return null;
    const exact = commentsData.find(c => normalizeText(c.comment_text) === target);
    if (exact) return exact;

    if (target.length >= 20) {
        return commentsData.find(c => {
            const source = normalizeText(c.comment_text);
            return source.includes(target) || target.includes(source);
        }) || null;
    }

    return null;
}

// 1. ACTUALIZAR KPIs
function updateKPIs() {
    const totalPosts = allPostsData.length;
    const totalComments = commentsData.length;
    const totalLikes = commentsData.reduce((acc, current) => acc + (parseInt(current.comment_likes) || 0), 0);

    const pos = commentsData.filter(c => c.sentimiento === 'Positivo').length;
    const neu = commentsData.filter(c => c.sentimiento === 'Neutral').length;
    const neg = commentsData.filter(c => c.sentimiento === 'Negativo').length;

    const vibra = totalComments > 0 ? ((pos / totalComments) * 100).toFixed(1) : 0;
    const negativePct = totalComments > 0 ? ((neg / totalComments) * 100).toFixed(1) : 0;

    document.getElementById('kpi-posts').innerText = totalPosts;
    document.getElementById('kpi-comments').innerText = totalComments;
    document.getElementById('kpi-likes').innerText = totalLikes.toLocaleString();
    document.getElementById('kpi-sentiment').innerText = vibra + '%';
    document.getElementById('kpi-negative').innerText = negativePct + '%';

    const totalTemp = commentsData.reduce((acc, c) => acc + (parseFloat(c.temperatura) || 0), 0);
    const avgTemp = totalComments > 0 ? (totalTemp / totalComments).toFixed(2) : "0.00";

    const valEl = document.getElementById('global-temp-value');
    const labelEl = document.getElementById('global-sentiment-label');
    const circleEl = document.getElementById('global-temp-circle');
    const descEl = document.getElementById('global-status-desc');

    valEl.innerText = avgTemp;

    let dominant = "Neutral 🌤️";
    let color = COLORS.neu;
    let diagnosis = "La comunidad se mantiene en un tono informativo y tranquilo.";

    if (pos > neg && pos > neu) {
        dominant = "Positivo 🌿";
        color = COLORS.pos;
        diagnosis = "Ambiente de apoyo y validación literal. Conversación constructiva.";
    } else if (neg > pos && neg > neu) {
        dominant = "Negativo 🚨";
        color = COLORS.neg;
        diagnosis = "Predomina la crítica o el sarcasmo agresivo. Comunidad en tensión.";
    }

    if (avgTemp > 0.6) {
        color = '#fb923c';
        diagnosis = "Sarcasmo detectado. La comunidad se burla indirectamente de los temas.";
    }
    if (avgTemp > 0.85) {
        color = '#f87171';
        diagnosis = "¡Alerta! Nivel máximo de trolling y cinismo detectado en la conversación.";
    }

    labelEl.innerText = dominant;
    labelEl.style.color = color;
    circleEl.style.borderColor = color;
    circleEl.style.boxShadow = `0 0 30px ${color}33`;
    descEl.style.borderColor = color;
    descEl.querySelector('span').innerText = diagnosis;
}

// --- SIMULADOR INTERACTIVO ---
async function testComment() {
    const input = document.getElementById('sim-input');
    const text = input.value.trim();
    if (!text) return;

    const valEl = document.getElementById('global-temp-value');
    const labelEl = document.getElementById('global-sentiment-label');
    const circleEl = document.getElementById('global-temp-circle');
    const descEl = document.getElementById('global-status-desc');

    labelEl.innerText = "ANALIZANDO...";
    valEl.innerText = "??";
    circleEl.style.borderColor = "#8b92a5";

    const localMatch = findLocalAnalysis(text);
    if (localMatch) {
        const localTemp = parseFloat(localMatch.temperatura || 0).toFixed(2);
        const localHumor = localMatch.tipo_humor || "Neutro / Informativo";
        const localJust = localMatch.justificacion || "Resultado recuperado desde datos locales.";

        let color = COLORS.neu;
        if (localTemp < 0.3) color = COLORS.pos;
        else if (localTemp > 0.8) color = COLORS.neg;
        else if (localTemp > 0.5) color = '#fb923c';

        valEl.innerText = localTemp;
        labelEl.innerText = localHumor;
        circleEl.style.borderColor = color;
        circleEl.style.boxShadow = `0 0 30px ${color}66`;
        labelEl.style.color = color;
        descEl.style.borderColor = color;
        descEl.querySelector('span').innerText = localJust;
        return;
    }

    try {
        const response = await fetchWithTimeout(`${API_BASE}/analizar/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ texto: text })
        }, 8000);
        const result = await response.json();

        if (result.status === "success") {
            const data = result.data;
            const temp = parseFloat(data.temperatura).toFixed(2);

            valEl.innerText = temp;
            labelEl.innerText = data.tipo_humor;

            let color = COLORS.neu;
            if (temp < 0.3) color = COLORS.pos;
            else if (temp > 0.8) color = COLORS.neg;
            else if (temp > 0.5) color = '#fb923c';

            circleEl.style.borderColor = color;
            circleEl.style.boxShadow = `0 0 30px ${color}66`;
            labelEl.style.color = color;
            descEl.style.borderColor = color;
            descEl.querySelector('span').innerText = data.justificacion;
        } else {
            labelEl.innerText = "ERROR API";
            descEl.querySelector('span').innerText = result.detail || "Respuesta inesperada";
        }
    } catch (e) {
        console.error("Error en simulador:", e);
        labelEl.innerText = e.name === 'AbortError' ? "TIMEOUT" : "ERROR API";
        descEl.querySelector('span').innerText = "No se pudo conectar con la API. ¿Está corriendo api_sarcasmo en :8001?";
    }
}

// 2. RENDERIZAR GRÁFICOS
function renderCharts() {
    const stats = {
        pos: commentsData.filter(c => c.sentimiento === 'Positivo').length,
        neu: commentsData.filter(c => c.sentimiento === 'Neutral').length,
        neg: commentsData.filter(c => c.sentimiento === 'Negativo').length
    };

    const chartEl = document.getElementById('sentimentChart');
    if (!chartEl) return;
    const ctxSent = chartEl.getContext('2d');
    if (sentimentChart) sentimentChart.destroy();
    sentimentChart = new Chart(ctxSent, {
        type: 'doughnut',
        data: {
            labels: ['Positivo', 'Neutral', 'Negativo'],
            datasets: [{
                data: [stats.pos, stats.neu, stats.neg],
                backgroundColor: [COLORS.pos, COLORS.neu, COLORS.neg],
                borderWidth: 0,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom', labels: { color: '#8b92a5', font: { family: 'Outfit' } } } },
            cutout: '70%'
        }
    });
}

// 3. TABLA DE POSTS COMPLETA
function renderPostsTable() {
    const tbody = document.getElementById('table-posts-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const sortedPosts = [...allPostsData].sort((a, b) => {
        const dateA = a.post_date ? new Date(a.post_date.split('/').reverse().join('-')) : new Date(0);
        const dateB = b.post_date ? new Date(b.post_date.split('/').reverse().join('-')) : new Date(0);
        return dateB - dateA;
    });

    const commsMap = {};
    commentsData.forEach(c => {
        if (!commsMap[c.post_url]) commsMap[c.post_url] = { count: 0, tTemp: 0, pos: 0, neg: 0 };
        commsMap[c.post_url].count++;
        commsMap[c.post_url].tTemp += parseFloat(c.temperatura) || 0;
        if (c.sentimiento === 'Positivo') commsMap[c.post_url].pos++;
        if (c.sentimiento === 'Negativo') commsMap[c.post_url].neg++;
    });

    sortedPosts.forEach((p) => {
        const url = p.post_url || p.url || '';
        const analysis = commsMap[url] || { count: 0, tTemp: 0, pos: 0, neg: 0 };
        const avg = analysis.count > 0 ? (analysis.tTemp / analysis.count).toFixed(2) : "0.00";
        const totalCommentsRaw = parseInt(p.total_comments, 10);
        const totalComments = Number.isFinite(totalCommentsRaw)
            ? Math.max(totalCommentsRaw, analysis.count)
            : analysis.count;

        const tr = document.createElement('tr');

        // Celda 1: enlace al post (URL y texto escapados)
        const td1 = document.createElement('td');
        const wrap = document.createElement('div');
        wrap.style.cssText = 'display:flex; align-items:center; gap:12px;';
        const link = document.createElement('a');
        link.href = safeUrl(url);
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.style.cssText = 'color:var(--text-main); text-decoration:none; font-size:0.85rem; opacity:0.8;';
        const shortUrl = String(url).substring(0, 30);
        link.textContent = `${p.post_date || 'Sin Fecha'} - ${shortUrl}...`;
        wrap.appendChild(link);
        td1.appendChild(wrap);
        tr.appendChild(td1);

        // Celdas 2-3: números (seguros por parseo)
        const td2 = document.createElement('td');
        td2.innerHTML = `<strong>${totalComments}</strong>`;
        tr.appendChild(td2);

        const td3 = document.createElement('td');
        td3.style.color = 'var(--text-dim)';
        td3.textContent = analysis.count;
        tr.appendChild(td3);

        // Celda 4: barra de temperatura (avg es numérico)
        const td4 = document.createElement('td');
        td4.innerHTML = `
            <div style="width:120px;">
                <div style="display:flex; justify-content:space-between; font-size:10px; margin-bottom:4px;">
                    <span>🌡️ Nota</span>
                    <strong>${avg}</strong>
                </div>
                <div class="temp-bar-container">
                    <div class="temp-bar" style="width:${avg * 100}%; background: linear-gradient(90deg, #4facfe, #FF3366);"></div>
                </div>
            </div>
        `;
        tr.appendChild(td4);

        // Celda 5: botón ver — handler por addEventListener (no inline onclick)
        const td5 = document.createElement('td');
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.style.cssText = 'background: rgba(248, 87, 166, 0.1); color: var(--accent-neg); border-color: rgba(248,87,166,0.25); cursor:pointer;';
        badge.innerHTML = '<i class="ph-bold ph-eye"></i>';
        badge.addEventListener('click', () => openModal(url, 'Publicación'));
        td5.appendChild(badge);
        tr.appendChild(td5);

        tbody.appendChild(tr);
    });
}

// --- UTILIDADES ---
function copyText(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        const originalIcon = btn.innerHTML;
        btn.innerHTML = '<i class="ph-bold ph-check" style="color:var(--accent-pos)"></i>';
        setTimeout(() => btn.innerHTML = originalIcon, 1500);
    });
}

// 4. EJEMPLOS DE TEMPERATURA
function renderTempExamples() {
    const tbody = document.getElementById('temp-examples-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const ranges = [
        { min: 0.81, max: 1.0, color: COLORS.neg, label: "Hirviendo" },
        { min: 0.5, max: 0.8, color: '#fb923c', label: "Caliente" },
        { min: 0.0, max: 0.2, color: COLORS.pos, label: "Frío" }
    ];

    ranges.forEach(r => {
        let ex = commentsData.find(c => {
            const t = parseFloat(c.temperatura);
            return t >= r.min && t <= r.max && (c.comment_text || '').length > 10;
        });
        if (!ex) ex = commentsData[0];
        if (!ex) return;

        const tr = document.createElement('tr');

        const td1 = document.createElement('td');
        td1.style.width = '50px';
        td1.innerHTML = `<span style="color:${r.color}; font-weight:700;">${parseFloat(ex.temperatura).toFixed(2)}</span>`;
        tr.appendChild(td1);

        const td2 = document.createElement('td');
        const flex = document.createElement('div');
        flex.style.cssText = 'display:flex; align-items:center; gap:8px;';
        const quote = document.createElement('div');
        quote.style.cssText = `font-style:italic; font-size:0.85rem; border-left:2px solid ${r.color}; padding-left:10px; flex:1;`;
        const snippet = String(ex.comment_text || '').substring(0, 80);
        quote.textContent = `"${snippet}..."`;
        flex.appendChild(quote);

        const copyBtn = document.createElement('button');
        copyBtn.className = 'copy-btn';
        copyBtn.innerHTML = '<i class="ph ph-copy"></i>';
        const fullText = String(ex.comment_text || '').replace(/\n/g, ' ');
        copyBtn.addEventListener('click', () => copyText(fullText, copyBtn));
        flex.appendChild(copyBtn);

        td2.appendChild(flex);
        tr.appendChild(td2);

        const td3 = document.createElement('td');
        td3.style.cssText = 'color:var(--text-dim); font-size:0.75rem;';
        td3.textContent = ex.tipo_humor || '';
        tr.appendChild(td3);

        tbody.appendChild(tr);
    });
}

// 5. MODAL KANBAN
function openModal(postUrl, title) {
    const modal = document.getElementById('commentsModal');
    document.getElementById('modal-title').textContent = "Análisis: " + title;

    const listPos = document.getElementById('modal-list-positivo');
    const listNeu = document.getElementById('modal-list-neutral');
    const listNeg = document.getElementById('modal-list-negativo');

    listPos.innerHTML = '';
    listNeu.innerHTML = '';
    listNeg.innerHTML = '';

    const filtered = commentsData.filter(c => c.post_url === postUrl);
    filtered.forEach((c, i) => {
        const card = document.createElement('div');
        card.className = 'kanban-card';
        card.id = `card-${i}`;
        card.draggable = true;
        card.addEventListener('dragstart', (ev) => {
            ev.dataTransfer.setData("text", card.id);
            ev.dataTransfer.setData("commentText", c.comment_text || '');
        });

        const header = document.createElement('div');
        header.style.cssText = 'display:flex; justify-content:space-between; align-items:flex-start;';
        const nameEl = document.createElement('strong');
        nameEl.textContent = c.commenter_name || 'Anónimo';
        header.appendChild(nameEl);

        const copyBtn = document.createElement('button');
        copyBtn.className = 'copy-btn';
        copyBtn.style.cssText = 'padding:0; margin-top:-5px;';
        copyBtn.innerHTML = '<i class="ph ph-copy"></i>';
        const fullText = String(c.comment_text || '').replace(/\n/g, ' ');
        copyBtn.addEventListener('click', () => copyText(fullText, copyBtn));
        header.appendChild(copyBtn);

        card.appendChild(header);

        const body = document.createElement('p');
        body.textContent = c.comment_text || '';
        card.appendChild(body);

        const meta = document.createElement('div');
        meta.className = 'kanban-meta';
        const tempSpan = document.createElement('span');
        tempSpan.textContent = `🌡️ ${c.temperatura || ''}`;
        const likesSpan = document.createElement('span');
        likesSpan.textContent = `❤️ ${c.comment_likes || 0}`;
        meta.appendChild(tempSpan);
        meta.appendChild(likesSpan);
        card.appendChild(meta);

        if (c.sentimiento === 'Positivo') listPos.appendChild(card);
        else if (c.sentimiento === 'Negativo') listNeg.appendChild(card);
        else listNeu.appendChild(card);
    });

    modal.classList.add('show');
}

function closeModal() {
    document.getElementById('commentsModal').classList.remove('show');
}

// DRAG & DROP
function allowDrop(ev) { ev.preventDefault(); }
async function drop(ev) {
    ev.preventDefault();
    const cardId = ev.dataTransfer.getData("text");
    const commentText = ev.dataTransfer.getData("commentText");
    const dragged = document.getElementById(cardId);

    let targetList = ev.target;
    while (targetList && !targetList.classList.contains('comment-list')) {
        targetList = targetList.parentElement;
    }

    if (!targetList || !dragged) return;

    targetList.appendChild(dragged);
    const newSentiment = targetList.id.includes('positivo')
        ? 'Positivo'
        : (targetList.id.includes('negativo') ? 'Negativo' : 'Neutral');

    try {
        const r = await fetchWithTimeout(`${API_BASE}/update_comment/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: commentText, sentiment: newSentiment })
        }, 5000);
        const d = await r.json();
        console.log("Guardado:", d);
        if (d.status !== 'success' && d.status !== 'noop') {
            showLoadError(`No se pudo persistir el cambio: ${d.message || d.detail}`);
        }
    } catch (e) {
        console.error("Error persistiendo:", e);
        showLoadError(`No se pudo persistir el cambio: ${e.message}`);
    }
}

// Iniciar
initTheme();
loadData();
