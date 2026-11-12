'use strict';

/* ======================================================================
   Utilitaires
   ====================================================================== */
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  file: '<path d="M14 3.5H7.5a2 2 0 00-2 2v13a2 2 0 002 2h9a2 2 0 002-2V8z"/><path d="M14 3.5V8h4.5M9 13h6M9 16.5h4"/>',
  folder: '<path d="M3.5 7.5a2 2 0 012-2h4l2 2.5h7a2 2 0 012 2v7.5a2 2 0 01-2 2h-13a2 2 0 01-2-2z"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  up: '<path d="M12 19V6M6.5 11.5L12 6l5.5 5.5"/>',
  filenew: '<path d="M14 3.5H7.5a2 2 0 00-2 2v13a2 2 0 002 2h9a2 2 0 002-2V8z"/><path d="M14 3.5V8h4.5M12 11.5v6M9 14.5h6"/>',
  foldernew: '<path d="M3.5 7.5a2 2 0 012-2h4l2 2.5h7a2 2 0 012 2v7.5a2 2 0 01-2 2h-13a2 2 0 01-2-2z"/><path d="M12 11v5M9.5 13.5h5"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
  home: '<path d="M3.5 11.5L12 4l8.5 7.5"/><path d="M5.5 10v9.5h13V10"/><path d="M10 19.5v-5h4v5"/>',
  server: '<rect x="3.5" y="4" width="17" height="6.5" rx="2"/><rect x="3.5" y="13.5" width="17" height="6.5" rx="2"/><path d="M7.5 7.25h.01M7.5 16.75h.01"/>',
  route: '<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="18" r="2.2"/><path d="M8.2 6H15a3 3 0 010 6H9a3 3 0 000 6h6.8"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  box: '<path d="M20.5 7.5L12 3 3.5 7.5v9L12 21l8.5-4.5z"/><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9"/>',
  play: '<path d="M7 4.5l12 7.5-12 7.5z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  refresh: '<path d="M20 11a8 8 0 10-2.2 5.6"/><path d="M20 4.5V11h-6.5"/>',
  trash: '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l.9 12.5h9.2L17.5 7"/>',
  terminal: '<path d="M4 6l6 6-6 6M12.5 19H20"/>',
  sliders: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  save: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
  download: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 20h14"/>',
};
const ic = (name, size) => `<svg class="i" viewBox="0 0 24 24" ${size ? `style="font-size:${size}px"` : ''}>${ICONS[name] || ''}</svg>`;

function fmtBytes(n) {
  if (n == null) return '—';
  const u = ['o', 'Ko', 'Mo', 'Go', 'To'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)} ${u[i]}`;
}
const fmtRate = (n) => (n == null ? '—' : `${fmtBytes(n)}/s`);
const fmtPct = (n) => (n == null ? '—' : `${n.toFixed(n < 10 ? 1 : 0)} %`);
function ago(iso) {
  const t = Date.parse(iso);
  if (!t || iso.startsWith('0001')) return '—';
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 129600) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} j`;
}

let toastTimer;
function toast(msg, isErr = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = `toast show${isErr ? ' err' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = 'toast'), isErr ? 6000 : 2800);
}

// Journaux du serveur : retire les codes ANSI (couleurs, effacement de ligne), les caractères de contrôle,
// les restes de l'invite « > » du terminal et le bruit des connexions RCON du panel.
function cleanLog(raw) {
  return String(raw)
    .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '')
    .replace(/\r/g, '')
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '')
    .split('\n')
    .map((l) => l.replace(/^>\.{0,6}(?=\[\d{2}:\d{2}:\d{2})/, ''))
    .filter((l) => l.trim() !== '>' && !/Thread RCON Client .* (started|shutting down)\s*$/.test(l))
    .join('\n');
}

async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'X-Requested-With': 'mc-panel' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === 'string' ? j.detail : (j.detail || []).map((d) => `${(d.loc || []).slice(1).join('.')} : ${d.msg}`).join(' · ');
    } catch { /* corps non JSON */ }
    throw new Error(msg || `Erreur ${res.status}`);
  }
  return res.json();
}

/* ======================================================================
   État
   ====================================================================== */
const S = { view: 'home', sel: null, tab: 'perf', ov: null, err: null, filter: '', busy: false };
const server = (name) => (S.ov?.servers || []).find((s) => s.name === name);

function statusOf(s) {
  if (!s) return { key: 'dead', label: 'Introuvable' };
  if (s.status === 'running') {
    if (s.health === 'starting') return { key: 'starting', label: 'Démarrage…' };
    if (s.health === 'unhealthy') return { key: 'unhealthy', label: 'Ne répond pas' };
    return { key: 'running', label: 'En ligne' };
  }
  if (s.status === 'restarting') return { key: 'restarting', label: 'Redémarrage…' };
  if (s.status === 'created') return { key: 'created', label: 'Créé' };
  return { key: 'exited', label: 'Arrêté' };
}
const isUp = (s) => s.status === 'running' || s.status === 'restarting';

/* ======================================================================
   Schéma des paramètres de itzg/minecraft-server
   ====================================================================== */
const bool = (k, label) => ({ k, label, t: 'bool' });
const SCHEMA = [
  { title: 'Jeu', fields: [
    { k: 'TYPE', label: 'Type de serveur', t: 'select', opts: ['VANILLA', 'PAPER', 'PURPUR', 'FOLIA', 'SPIGOT', 'BUKKIT', 'FABRIC', 'QUILT', 'FORGE', 'NEOFORGE'] },
    { k: 'VERSION', label: 'Version', t: 'text', ph: 'LATEST' },
    { k: 'MODE', label: 'Mode de jeu', t: 'select', opts: ['survival', 'creative', 'adventure', 'spectator'] },
    { k: 'DIFFICULTY', label: 'Difficulté', t: 'select', opts: ['peaceful', 'easy', 'normal', 'hard'] },
    { k: 'MAX_PLAYERS', label: 'Joueurs max', t: 'number', ph: '20' },
    { k: 'MOTD', label: 'Message du serveur (MOTD)', t: 'text', wide: true },
    bool('HARDCORE', 'Hardcore'), bool('PVP', 'PvP'), bool('ONLINE_MODE', 'Mode en ligne (comptes premium)'),
    bool('ALLOW_NETHER', 'Nether'), bool('ALLOW_FLIGHT', 'Vol autorisé'), bool('ENABLE_COMMAND_BLOCK', 'Blocs de commande'),
    bool('FORCE_GAMEMODE', 'Forcer le mode de jeu'),
  ] },
  { title: 'Monde', fields: [
    { k: 'LEVEL', label: 'Nom du monde', t: 'text', ph: 'world' },
    { k: 'SEED', label: 'Graine', t: 'text' },
    { k: 'VIEW_DISTANCE', label: 'Distance de vue', t: 'number', ph: '10' },
    { k: 'SIMULATION_DISTANCE', label: 'Distance de simulation', t: 'number', ph: '10' },
    { k: 'SPAWN_PROTECTION', label: 'Protection du spawn', t: 'number', ph: '16' },
    { k: 'MAX_WORLD_SIZE', label: 'Taille max du monde', t: 'number' },
  ] },
  { title: 'Joueurs', fields: [
    { k: 'OPS', label: 'Opérateurs', t: 'list', wide: true },
  ] },
];

// Champs affichés dans la section « Ressources et performances » (et non dans SCHEMA).
const INIT_FIELD = { k: 'INIT_MEMORY', label: 'Mémoire réservée au démarrage', t: 'text', ph: 'ex. 1G',
  hint: 'Optionnel. La même valeur que la mémoire maximale évite les ralentissements en cours de jeu.' };
const AIKAR_FIELD = { ...bool('USE_AIKAR_FLAGS', 'Optimisation anti-saccades (flags Aikar)'),
  hint: 'Réglages Java recommandés pour Paper/Spigot, utiles à partir de 4G.' };
const JVM_FIELD = { k: 'JVM_OPTS', label: 'Options Java supplémentaires', t: 'text', wide: true,
  hint: 'Avancé : arguments passés à Java. Laisse vide en cas de doute.' };
const TZ_FIELD = { k: 'TZ', label: 'Fuseau horaire', t: 'text', ph: 'Europe/Paris',
  hint: 'Heure utilisée dans les journaux du serveur.' };
// Valeurs appliquées par itzg/minecraft-server quand la variable n'est pas définie.
const DEFAULTS = {
  TYPE: 'VANILLA', MODE: 'survival', DIFFICULTY: 'easy',
  HARDCORE: 'FALSE', PVP: 'TRUE', ONLINE_MODE: 'TRUE', ALLOW_NETHER: 'TRUE', ALLOW_FLIGHT: 'FALSE',
  ENABLE_COMMAND_BLOCK: 'FALSE', FORCE_GAMEMODE: 'FALSE', ENFORCE_WHITELIST: 'FALSE',
  USE_AIKAR_FLAGS: 'FALSE',
};

const WHITELIST_FIELD = { k: 'WHITELIST', label: 'Joueurs autorisés', t: 'list', wide: true };
const ENFORCE_FIELD = bool('ENFORCE_WHITELIST', 'Expulser immédiatement les joueurs retirés de la liste');
const KNOWN_ENV = new Set(['EULA', 'MEMORY', 'WHITELIST', 'ENABLE_WHITELIST', 'ENFORCE_WHITELIST',
  'INIT_MEMORY', 'JVM_OPTS', 'TZ', 'USE_AIKAR_FLAGS', ...SCHEMA.flatMap((g) => g.fields.map((f) => f.k))]);

// Listes à ajouter / retirer : « player » (pseudos) ou « host » (noms de domaine mc-router).
const PLIST_KINDS = {
  player: { empty: 'Aucun joueur pour l\'instant', max: 36, re: /^[A-Za-z0-9_-]{1,36}$/, error: 'Pseudo invalide (lettres, chiffres et _ uniquement)', lower: false },
  host: { empty: 'Aucun hostname pour l\'instant', max: 253, re: /^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$/, error: 'Hostname invalide (ex. survie.exemple.com)', lower: true },
};

const plistItems = (names, act = 'list-del', kind = 'player') => (names.length
  ? names.map((n) => `<li data-name="${esc(n)}"><span>${esc(n)}</span><button type="button" class="icon-btn" data-act="${act}" title="Retirer">${ic('trash', 18)}</button></li>`).join('')
  : `<li class="plist-empty">${PLIST_KINDS[kind].empty}</li>`);

const plistHtml = (hiddenAttrs, names, inputId, placeholder, kind = 'player') => `<div class="plist" data-kind="${kind}">
  <input type="hidden" ${hiddenAttrs} value="${esc(names.join(','))}">
  <div class="plist-add"><input class="plist-input" id="${inputId}" placeholder="${esc(placeholder)}" autocomplete="off" maxlength="${PLIST_KINDS[kind].max}">
    <button type="button" class="btn" data-act="list-add">${ic('plus')} Ajouter</button></div>
  <ul class="plist-items">${plistItems(names, 'list-del', kind)}</ul></div>`;

function plistAdd(root) {
  const cfg = PLIST_KINDS[root.dataset.kind || 'player'];
  const input = root.querySelector('.plist-input');
  const hidden = root.querySelector('input[type=hidden]');
  const names = hidden.value ? hidden.value.split(',') : [];
  const wanted = input.value.split(/[\s,]+/).filter(Boolean);
  if (!wanted.length) return;
  for (let n of wanted) {
    if (!cfg.re.test(n)) { toast(`${cfg.error} : « ${n} »`, true); return; }
    if (cfg.lower) n = n.toLowerCase();
    if (!names.some((x) => x.toLowerCase() === n.toLowerCase())) names.push(n);
  }
  hidden.value = names.join(',');
  root.querySelector('.plist-items').innerHTML = plistItems(names, 'list-del', root.dataset.kind || 'player');
  input.value = '';
  input.focus();
}

function plistRemove(li) {
  const root = li.closest('.plist');
  const hidden = root.querySelector('input[type=hidden]');
  const names = hidden.value.split(',').filter((n) => n && n !== li.dataset.name);
  hidden.value = names.join(',');
  root.querySelector('.plist-items').innerHTML = plistItems(names, 'list-del', root.dataset.kind || 'player');
}

function fieldHtml(f, val) {
  const v = val ?? '';
  const common = `data-env="${f.k}" id="env-${f.k}"`;
  let input;
  if (f.t === 'select' || f.t === 'bool') {
    const opts = f.t === 'bool' ? [['TRUE', 'Oui'], ['FALSE', 'Non']] : f.opts.map((o) => [o, o]);
    let cur = f.t === 'bool' ? String(v).toUpperCase() : v;
    if (cur && !opts.some(([o]) => o === cur)) opts.push([cur, cur]);
    // Une seule entrée par valeur : l'entrée qui correspond à la valeur par défaut (valeur '' = non définie)
    // porte le suffixe « (défaut) » en gris. Sans valeur par défaut connue, on garde une entrée « (défaut) ».
    const def = DEFAULTS[f.k];
    const items = opts.map(([o, l]) => ({ value: o === def ? '' : o, label: l, isDef: o === def }));
    if (def === undefined) items.unshift({ value: '', label: '(défaut)', grey: true });
    if (cur === def) cur = '';
    const sel = items.find((i) => i.value === cur) || items[0];
    const render = (i) => (i.grey ? `<span class="grey">${esc(i.label)}</span>` : `${esc(i.label)}${i.isDef ? ' <span class="grey">(défaut)</span>' : ''}`);
    input = `<div class="dd">
      <input type="hidden" ${common} value="${esc(sel.value)}">
      <button type="button" class="dd-btn" id="dd-${f.k}" aria-haspopup="listbox"><span class="dd-text">${render(sel)}</span>${ic('chevron')}</button>
      <ul class="dd-list" role="listbox" hidden>${items.map((i) => `<li role="option" data-v="${esc(i.value)}">${render(i)}</li>`).join('')}</ul></div>`;
  } else if (f.t === 'list') {
    const names = String(v).split(',').map((s) => s.trim()).filter(Boolean);
    input = plistHtml(common, names, `ls-${f.k}`, 'Pseudo du joueur');
  } else {
    input = `<input ${common} type="${f.t === 'number' ? 'number' : 'text'}" value="${esc(v)}" placeholder="${esc(f.ph || '')}">`;
  }
  return `<div class="field${f.wide ? ' wide' : ''}"><label for="${{ list: 'ls-', select: 'dd-', bool: 'dd-' }[f.t] || 'env-'}${f.k}">${esc(f.label)}</label>${input}${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ''}</div>`;
}

const ACCESS_MODES = [['none', 'Aucune'], ['whitelist', 'Liste blanche'], ['blacklist', 'Liste noire']];

function accessSection(spec, isNew) {
  const mode = spec.access_mode || 'none';
  const env = spec.env || {};
  return `<div class="field wide"><label>Contrôle d'accès</label>
      <input type="hidden" data-f="access_mode" value="${mode}">
      <div class="seg" role="radiogroup">${ACCESS_MODES.map(([m, l]) =>
        `<button type="button" class="seg-btn ${m === mode ? 'on' : ''}" data-act="access" data-mode="${m}">${l}</button>`).join('')}</div>
      <span class="hint" id="access-hint">${{ none: 'Tout le monde peut se connecter.', whitelist: 'Seuls les joueurs de la liste peuvent se connecter.',
        blacklist: 'Les joueurs de la liste sont bannis ; tous les autres peuvent se connecter.' }[mode]}</span></div>
    <div class="access-pane fields" data-pane="whitelist" style="grid-column:1/-1" ${mode === 'whitelist' ? '' : 'hidden'}>
      ${fieldHtml(WHITELIST_FIELD, env.WHITELIST)}${fieldHtml(ENFORCE_FIELD, env.ENFORCE_WHITELIST)}
    </div>
    <div class="access-pane fields" data-pane="blacklist" style="grid-column:1/-1" ${mode === 'blacklist' ? '' : 'hidden'}>
      <div class="field wide"><label for="ls-BAN">Joueurs bannis</label>
        ${isNew ? '<span class="hint">Disponible une fois le serveur créé et démarré.</span>' : `<div class="plist">
          <div class="plist-add"><input class="plist-input" id="ls-BAN" placeholder="Pseudo du joueur à bannir" autocomplete="off" maxlength="36">
            <button type="button" class="btn" data-act="ban-add">${ic('plus')} Bannir</button></div>
          <ul class="plist-items" id="ban-items"><li class="plist-empty">Chargement…</li></ul></div>
          <span class="hint">Appliqué immédiatement (le serveur doit être démarré), sans passer par « Appliquer ».</span>`}
      </div>
    </div>`;
}

async function loadBans() {
  const ul = $('#ban-items');
  if (!ul || !S.sel) return;
  try {
    const { players } = await api(`/servers/${encodeURIComponent(S.sel)}/banned`);
    ul.innerHTML = plistItems(players, 'ban-del');
  } catch (e) { ul.innerHTML = `<li class="plist-empty">${esc(e.message)}</li>`; }
}

const DEFAULT_SPEC = { name: '', image_tag: 'latest', memory: '2G', mem_limit: null, cpu_limit: null, hosts: '', host_port: null,
  access_mode: 'none', router_default: false, data_path: null, restart: 'unless-stopped', env: { TYPE: 'VANILLA', VERSION: 'LATEST' } };

function serverForm(spec, isNew) {
  const env = spec.env || {};
  const extra = Object.entries(env).filter(([k]) => !KNOWN_ENV.has(k)).map(([k, v]) => `${k}=${v}`).join('\n');
  const inp = (f, label, val, attrs = '', hint = '') =>
    `<div class="field"><label>${label}${attrs.includes('required') ? ' <span class="req">*</span>' : ''}</label><input data-f="${f}" value="${esc(val ?? '')}" ${attrs}>${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
  return `
  <form id="srv-form" autocomplete="off" onsubmit="return false">
    <div class="form-section"><h3>Serveur</h3><div class="fields">
      ${inp('name', 'Nom', spec.name, `required ${isNew ? '' : 'disabled'} placeholder="survie" pattern="[a-z0-9][a-z0-9_-]*"`, isNew ? 'a-z, 0-9, - et _ (sert de nom au conteneur).' : '')}
      ${inp('image_tag', 'Tag de l\'image itzg/minecraft-server', spec.image_tag, 'required placeholder="latest"', 'Ex. latest, java21, java17, stable.')}
      <div class="field"><label>Redémarrage automatique</label><select data-f="restart">
        ${[['unless-stopped', 'Toujours (sauf si arrêté manuellement)'], ['always', 'Toujours'], ['on-failure', 'Seulement après un plantage'], ['no', 'Jamais']]
          .map(([r, label]) => `<option value="${r}" ${r === spec.restart ? 'selected' : ''}>${label}</option>`).join('')}</select></div>
      ${fieldHtml(TZ_FIELD, env.TZ)}
    </div></div>

    <div class="form-section"><h3>Ressources et performances</h3>
      <div class="subhead">Mémoire</div>
      <div class="fields">
        ${inp('memory', 'Mémoire maximale de Java', spec.memory, 'required placeholder="2G"', 'Le réglage principal : ce que le serveur Minecraft peut utiliser au maximum (ex. 2G, 4G).')}
        ${fieldHtml(INIT_FIELD, env.INIT_MEMORY)}
        ${inp('mem_limit', 'Plafond du conteneur Docker', spec.mem_limit, 'placeholder="3G"', 'Optionnel. Docker coupe le serveur s\'il dépasse : prévois ~1 Go de plus que la mémoire maximale. Vide = pas de plafond.')}
      </div>
      <div class="subhead">Processeur</div>
      <div class="fields">
        ${inp('cpu_limit', 'Limite de cœurs', spec.cpu_limit, 'type="number" step="0.1" min="0.1" placeholder="2"', 'Optionnel. Nombre maximum de cœurs utilisables (ex. 2 ou 1.5). Vide = pas de limite.')}
      </div>
      <div class="subhead">Optimisation Java</div>
      <div class="fields">
        ${fieldHtml(AIKAR_FIELD, env.USE_AIKAR_FLAGS)}
        ${fieldHtml(JVM_FIELD, env.JVM_OPTS)}
      </div>
    </div>

    <div class="form-section"><h3>Réseau</h3><div class="fields">
      <div class="field wide"><label for="ls-hosts">Hostname(s) mc-router</label>
        ${plistHtml('data-f="hosts"', (spec.hosts || '').split(',').filter(Boolean), 'ls-hosts', 'survie.exemple.com', 'host')}
        <span class="hint">Noms de domaine avec lesquels les joueurs se connectent à ce serveur. Tu peux en ajouter plusieurs.</span></div>
      <div class="field"><label>&nbsp;</label><label class="check"><input type="checkbox" data-f="router_default" ${spec.router_default ? 'checked' : ''}> Serveur par défaut du routeur <span class="hint">(un seul, hostname requis)</span></label></div>
      ${inp('host_port', 'Port publié (optionnel)', spec.host_port, 'type="number" min="1" max="65535" placeholder="25566"', 'Connexion directe sans routeur.')}
      ${inp('data_path', 'Dossier de données (optionnel)', spec.data_path, `${isNew ? '' : 'disabled'} placeholder="/var/lib/docker/volumes"`, 'Vide = emplacement par défaut (en gris). Ou indique un chemin absolu sur le serveur, ex. /srv/minecraft/survie.')}
    </div></div>

    ${SCHEMA.map((g) => `<div class="form-section"><h3>${g.title}</h3><div class="fields">${g.fields.map((f) => fieldHtml(f, env[f.k])).join('')}${g.title === 'Joueurs' ? accessSection(spec, isNew) : ''}</div></div>`).join('')}

    <div class="form-section"><h3>Variables personnalisées</h3><div class="fields">
      <div class="field wide"><label>Une variable par ligne : NOM=valeur</label>
        <textarea data-f="extra" placeholder="MODRINTH_PROJECTS=lithium,fabric-api&#10;ENABLE_RCON=true">${esc(extra)}</textarea>
        <span class="hint">Toute variable d'environnement supportée par itzg/minecraft-server.</span></div>
    </div></div>

    <div class="form-section"><label class="check"><input type="checkbox" data-f="eula" ${String(env.EULA).toUpperCase() === 'TRUE' ? 'checked' : ''}>
      J'accepte l'<a href="https://www.minecraft.net/en-us/eula" target="_blank" rel="noopener">EULA de Minecraft</a> <span class="req">*</span></label></div>

    <div class="form-actions">
      <button class="btn primary" data-act="save-server" data-new="${isNew ? 1 : 0}">${ic('save')} ${isNew ? 'Créer le serveur' : 'Appliquer'}</button>
      <span class="hint">${isNew ? 'Le premier lancement télécharge l\'image Docker (quelques minutes).' : 'Docker ne modifie pas un conteneur à chaud : il est recréé (monde conservé) et redémarré s\'il tournait.'}</span>
    </div>
  </form>`;
}

function readServerForm() {
  const root = $('#srv-form');
  const val = (f) => root.querySelector(`[data-f="${f}"]`);
  const text = (f) => val(f).value.trim();
  const orNull = (f) => text(f) || null;
  const env = {};
  root.querySelectorAll('[data-env]').forEach((el) => { if (el.value.trim() !== '') env[el.dataset.env] = el.value.trim(); });
  text('extra').split('\n').forEach((line) => {
    const i = line.indexOf('=');
    if (i > 0) env[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  });
  env.EULA = val('eula').checked ? 'TRUE' : 'FALSE';
  return {
    name: text('name'), image_tag: text('image_tag') || 'latest', memory: text('memory') || '2G',
    mem_limit: orNull('mem_limit'), cpu_limit: text('cpu_limit') ? Number(text('cpu_limit')) : null,
    hosts: text('hosts'), host_port: text('host_port') ? Number(text('host_port')) : null,
    access_mode: val('access_mode').value, router_default: val('router_default').checked, data_path: orNull('data_path'), restart: val('restart').value, env,
  };
}

/* ======================================================================
   Graphiques SVG
   ====================================================================== */
function chart(points, series, { max = null, floor = 0 } = {}) {
  if (points.length < 2) return '<div class="empty">Collecte des données…</div>';
  const W = 600, H = 130, P = 4;
  const peak = Math.max(floor, ...series.flatMap((s) => points.map((p) => p[s.key] ?? 0)));
  const top = max || peak * 1.15 || 1;
  const x = (i) => (i / (points.length - 1)) * W;
  const y = (v) => H - P - (Math.min(v, top) / top) * (H - 2 * P);
  const grid = [0.25, 0.5, 0.75].map((f) => `<line class="grid-line" x1="0" x2="${W}" y1="${H * f}" y2="${H * f}"/>`).join('');
  const paths = series.map((s, idx) => {
    const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p[s.key] ?? 0).toFixed(1)}`).join('');
    return (idx === 0 ? `<path class="area" d="${d}L${W} ${H}L0 ${H}Z"/>` : '') + `<path class="line ${s.cls || ''}" d="${d}"/>`;
  }).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${grid}${paths}</svg>`;
}

// Bandeau d'alerte tant que le mot de passe est encore celui par défaut (admin / admin).
function renderWarn() {
  const el = $('#warn');
  if (!el) return;
  const show = !!S.ov?.default_password;
  if (el.hidden === !show && (!show || el.childElementCount)) return;
  el.hidden = !show;
  el.innerHTML = show ? `<span><b>Mot de passe par défaut (admin / admin).</b> Change-le pour protéger ton serveur.</span>
    <button class="btn" data-act="profile">Changer maintenant</button>` : '';
}

/* ======================================================================
   Rail et panneau de liste
   ====================================================================== */
const NAV = [
  { id: 'home', icon: 'home', title: 'Accueil' },
  { id: 'server', icon: 'server', title: 'Serveurs' },
  { id: 'fs', icon: 'file', title: 'Fichiers' },
  { id: 'router', icon: 'route', title: 'Routeur' },
  { id: 'docker', icon: 'box', title: 'Docker' },
];

function renderRail() {
  const servers = S.ov?.servers || [];
  const alerts = {
    server: servers.some((s) => ['unhealthy', 'restarting'].includes(statusOf(s).key)),
    docker: S.ov && !S.ov.docker.ok,
  };
  const up = S.ov?.docker?.ok;
  $('#rail').innerHTML = `
    <button class="fab" data-nav="new" title="Nouveau serveur">${ic('plus', 26)}</button>
    ${NAV.map((n) => `<button class="rail-btn ${S.view === n.id || (n.id === 'server' && S.view === 'new') ? 'active' : ''}" data-nav="${n.id}" title="${n.title}">
      ${ic(n.icon)}${alerts[n.id] ? '<span class="dot"></span>' : ''}</button>`).join('')}
    <span class="rail-spacer"></span>
    <button class="avatar ${S.ov ? (up ? 'up' : 'down') : ''}" data-act="profile" title="Profil — ${up ? 'Docker connecté' : 'Docker injoignable'}">MC</button>`;
}

function renderPanel() {
  const titles = { home: 'Accueil', server: 'Serveurs', fs: 'Fichiers', new: 'Nouveau serveur', router: 'Routeur', docker: 'Docker' };
  $('#panel-title').textContent = titles[S.view];
  document.querySelector('.nav').classList.toggle('no-panel', !['server', 'fs'].includes(S.view));
  const servers = (S.ov?.servers || []).filter((s) => s.name.includes(S.filter.toLowerCase()));
  const row = (s) => {
    const st = statusOf(s);
    const n = s.stats?.players;
    return `<button class="item ${S.view === 'server' && S.sel === s.name ? 'active' : ''}" data-nav="server" data-name="${esc(s.name)}">
      <span class="led ${st.key}"></span><span class="name">${esc(s.name)}</span>
      <span class="meta">${n != null ? `${n}/${s.stats.max_players ?? '?'}` : ''}</span></button>`;
  };
  if (S.view === 'fs') {   // tous les serveurs, par ordre alphabétique
    const sorted = [...servers].sort(byName);
    $('#panel-list').innerHTML = `<div class="group-label">Serveurs (A → Z)</div>${sorted.length
      ? sorted.map((s) => `<button class="item ${S.sel === s.name ? 'active' : ''}" data-nav="fs" data-name="${esc(s.name)}">
          <span class="led ${statusOf(s).key}"></span><span class="name">${esc(s.name)}</span></button>`).join('')
      : '<div class="empty">Aucun serveur</div>'}`;
    return;
  }
  const up = servers.filter(isUp), down = servers.filter((s) => !isUp(s));
  let html = `<div class="group-label">En ligne</div>${up.length ? up.map(row).join('') : '<div class="empty">Aucun serveur en ligne</div>'}`;
  if (down.length) html += `<div class="group-label">Arrêtés</div>${down.map(row).join('')}`;
  $('#panel-list').innerHTML = html;
}

/* ======================================================================
   Navigation
   ====================================================================== */
function go(view, sel = null, tab = 'perf') {
  S.view = view; S.sel = sel; S.tab = tab;
  renderRail(); renderPanel(); mountMain(); updateLive();
}

function mountMain() {
  const m = $('#main');
  m.scrollTop = 0;
  if (S.view === 'home') m.innerHTML = '<div class="page-head"><h2>Vue d\'ensemble</h2></div><div id="live"></div>';
  else if (S.view === 'new') m.innerHTML = `<div class="page-head"><h2>Nouveau serveur</h2></div>${serverForm(DEFAULT_SPEC, true)}`;
  else if (S.view === 'server') mountServer();
  else if (S.view === 'router') mountRouter();
  else if (S.view === 'docker') mountDocker();
  else if (S.view === 'fs') mountFs();
}

/* ---------------------------------------------------------------- Accueil */
function liveHome() {
  if (!$('#live')) return;
  const ov = S.ov;
  if (!ov) { $('#live').innerHTML = '<div class="empty">Chargement…</div>'; return; }
  const h = ov.host || {};
  const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
  const bar = (p) => `<div class="bar"><i style="width:${p}%"></i></div>`;
  const run = ov.servers.filter(isUp);
  const players = run.reduce((n, s) => n + (s.stats?.players || 0), 0);
  $('#live').innerHTML = `
    ${ov.docker.ok ? '' : `<div class="banner">${esc(ov.docker.error)}</div>`}
    <div class="grid cols-4">
      <div class="card"><h3>Serveurs actifs</h3><div class="stat">${run.length}<small>/ ${ov.servers.length}</small></div><div class="sub">${players} joueur${players > 1 ? 's' : ''} connecté${players > 1 ? 's' : ''}</div></div>
      <div class="card"><h3>CPU de l'hôte</h3><div class="stat">${fmtPct(h.cpu)}</div><div class="sub">${h.cores ?? '?'} cœurs</div>${bar(h.cpu || 0)}</div>
      <div class="card"><h3>Mémoire de l'hôte</h3><div class="stat">${fmtBytes(h.mem_used)}</div><div class="sub">sur ${fmtBytes(h.mem_total)}</div>${bar(pct(h.mem_used, h.mem_total))}</div>
      <div class="card"><h3>Disque</h3><div class="stat">${fmtBytes(h.disk_used)}</div><div class="sub">sur ${fmtBytes(h.disk_total)}</div>${bar(pct(h.disk_used, h.disk_total))}</div>
    </div>
    <div class="section-title">Serveurs</div>
    <div class="card">${ov.servers.length ? `<table><thead><tr><th>Nom</th><th>État</th><th>Joueurs</th><th>CPU</th><th>Mémoire</th><th>Hostname</th></tr></thead><tbody>
      ${ov.servers.map((s) => {
        const st = statusOf(s), t = s.stats;
        return `<tr class="click" data-nav="server" data-name="${esc(s.name)}"><td><b>${esc(s.name)}</b></td>
          <td><span class="pill"><span class="led ${st.key}"></span>${st.label}</span></td>
          <td>${t?.players != null ? `${t.players} / ${t.max_players}` : '—'}</td><td>${t ? fmtPct(t.cpu) : '—'}</td>
          <td>${t ? fmtBytes(t.mem) : '—'}</td><td class="mono">${esc(s.spec.hosts || '—')}</td></tr>`;
      }).join('')}</tbody></table>` : `<div class="empty">Aucun serveur pour l'instant. <a href="#" data-nav="new">Crée le premier</a>.</div>`}</div>
    <div class="section-title">Routeur</div>
    <div class="card"><div class="chart-head"><div><b>mc-router</b> · ${esc(ov.router?.exists ? ov.router.status : 'non créé')}</div>
      <a href="#" data-nav="router" class="hint">Configurer →</a></div></div>`;
}

/* ---------------------------------------------------------------- Sauvegardes */
const REASON_LABELS = { manuelle: 'Manuelle', 'avant-modif': 'Avant modification', 'avant-restauration': 'Avant restauration' };
const fmtDate = (ts) => new Date(ts * 1000).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });

function mountBackups() {
  $('#tabbody').innerHTML = `
    <div class="card"><div class="chart-head"><div><b>Sauvegardes du monde</b>
      <div class="hint" style="margin-top:4px">Archive du dossier de données du serveur (monde, configuration, plugins, mods), sans les journaux. Le serveur peut rester allumé.</div></div>
      <button class="btn primary" data-act="backup-create" id="backup-btn">${ic('save')} Créer une sauvegarde</button></div>
      <div id="backup-state" style="margin-top:12px"></div></div>
    <div class="section-title">Sauvegardes existantes <span id="backup-total" class="hint"></span></div>
    <div class="card" id="backup-list"><div class="empty">Chargement…</div></div>
    <p class="hint" style="margin-top:12px">Stockées dans le volume de données du panel, sur le même disque que le serveur : pense à télécharger les sauvegardes importantes.</p>`;
}

async function loadBackups() {
  const list = $('#backup-list');
  if (!list || !S.sel) return null;
  let data;
  try { data = await api(`/servers/${encodeURIComponent(S.sel)}/backups`); } catch (e) { list.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return null; }
  if (!$('#backup-list')) return null;
  const job = data.job, busy = job?.state === 'running';
  $('#backup-state').innerHTML = !data.supported
    ? '<div class="banner">Les sauvegardes nécessitent que le panel tourne via le docker-compose.yml fourni.</div>'
    : busy ? `<div class="notice"><span class="spin"></span> ${esc(job.label)}… ne ferme pas cette page si possible.</div>`
    : job?.state === 'failed' ? `<div class="banner">Échec : ${esc(job.error || 'erreur inconnue')}</div>` : '';
  const btn = $('#backup-btn'); if (btn) btn.disabled = busy || !data.supported;
  $('#backup-total').textContent = data.backups.length ? `· ${data.backups.length} · ${fmtBytes(data.total_size)}` : '';
  list.innerHTML = data.backups.length ? `<table><thead><tr><th>Date</th><th>Type</th><th>Taille</th><th></th></tr></thead><tbody>
    ${data.backups.map((b) => `<tr><td>${esc(fmtDate(b.created))}</td><td><span class="pill">${esc(REASON_LABELS[b.reason] || b.reason)}</span></td><td>${fmtBytes(b.size)}</td>
      <td style="text-align:right;white-space:nowrap">
        <a class="btn" href="/api/servers/${encodeURIComponent(S.sel)}/backups/${encodeURIComponent(b.file)}" download>${ic('download')} Télécharger</a>
        <button class="btn" data-act="backup-restore" data-file="${esc(b.file)}" ${busy ? 'disabled' : ''}>${ic('refresh')} Restaurer</button>
        <button class="icon-btn" data-act="backup-del" data-file="${esc(b.file)}" title="Supprimer" ${busy ? 'disabled' : ''}>${ic('trash', 18)}</button></td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">Aucune sauvegarde pour l\'instant.</div>';
  return data;
}

// Lance une sauvegarde et attend sa fin (utilisé avant un changement risqué).
async function backupAndWait(reason, onProgress) {
  const name = encodeURIComponent(S.sel);
  await api(`/servers/${name}/backups?reason=${reason}`, { method: 'POST' });
  for (let i = 0; i < 1200; i++) {            // 1 h max
    await new Promise((r) => setTimeout(r, 2000));
    const { job } = await api(`/servers/${name}/backups`);
    if (onProgress) onProgress();
    if (job?.state === 'failed') throw new Error(job.error || 'sauvegarde échouée');
    if (job?.state === 'done') return;
  }
  throw new Error('délai dépassé');
}

/* ---------------------------------------------------------------- Confirmation personnalisée */
function askModal({ title, body = '', input = null, check = null, confirmLabel = 'Continuer', danger = false }) {
  return new Promise((resolve) => {
    $('#modal').innerHTML = modalShell(`<div class="modal-head"><h2>${esc(title)}</h2></div>
      <div class="ask-body">${body}</div>
      ${input ? `<div class="field" style="margin-top:12px"><label for="ask-input">${esc(input.label)}</label>
        <input id="ask-input" value="${esc(input.value || '')}" placeholder="${esc(input.placeholder || '')}" autocomplete="off" maxlength="255"></div>` : ''}
      ${check ? `<label class="check" style="margin:16px 0 4px"><input type="checkbox" id="ask-check" ${check.checked ? 'checked' : ''}> ${esc(check.label)}</label>` : ''}
      <div class="ask-actions"><button class="btn" data-ask="no">Annuler</button>
        <button class="btn ${danger ? 'danger-fill' : 'primary'}" data-ask="yes">${esc(confirmLabel)}</button></div>`);
    const finish = (ok) => {
      const checked = $('#ask-check')?.checked ?? false;
      const value = $('#ask-input')?.value ?? '';
      $('#modal').innerHTML = '';
      document.removeEventListener('click', onClick, true);
      document.removeEventListener('keydown', onKey, true);
      resolve({ ok, checked, value });
    };
    const onClick = (e) => {
      const b = e.target.closest?.('[data-ask]');
      if (b) { e.stopPropagation(); finish(b.dataset.ask === 'yes'); }
      else if (e.target.classList?.contains('modal-backdrop')) { e.stopPropagation(); finish(false); }
    };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
      else if (e.key === 'Enter' && e.target.id === 'ask-input') { e.preventDefault(); e.stopPropagation(); finish(true); }
    };
    document.addEventListener('click', onClick, true);
    document.addEventListener('keydown', onKey, true);
    $('#ask-input')?.focus();
    $('#ask-input')?.select();
  });
}

/* ---------------------------------------------------------------- Explorateur de fichiers */
const byName = (a, b) => a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' });
const fsApi = (kind, extra = '') => `/servers/${encodeURIComponent(S.sel)}/fs/${kind}?path=${encodeURIComponent(S.fsPath)}${extra}`;
const fsJoin = (name) => (S.fsPath ? `${S.fsPath}/${name}` : name);
const fsParent = () => S.fsPath.split('/').slice(0, -1).join('/');

function mountFs() {
  const servers = [...(S.ov?.servers || [])].sort(byName);
  if (!S.sel || !server(S.sel)) { S.sel = servers[0]?.name || null; renderPanel(); }
  if (!S.sel) {
    $('#main').innerHTML = '<div class="page-head"><h2>Fichiers</h2></div><div class="card"><div class="empty">Aucun serveur pour l\'instant.</div></div>';
    return;
  }
  if (S.fsFor !== S.sel) { S.fsFor = S.sel; S.fsPath = ''; S.fsFile = null; }
  $('#main').innerHTML = `<div class="page-head"><h2>${esc(S.sel)}</h2><span class="grow"></span><div class="fs-tools" id="fs-tools"></div></div>
    <div class="crumbs" id="fs-crumbs"></div><div id="fs-body"></div>`;
  fsRender();
}

function fsRender() {
  if (!$('#fs-body')) return;
  const editing = !!S.fsFile;
  $('#fs-tools').innerHTML = editing ? '' : `
    <button class="btn" data-act="fs-new-file">${ic('filenew')} Nouveau fichier</button>
    <button class="btn" data-act="fs-new-dir">${ic('foldernew')} Nouveau dossier</button>
    <label class="btn">${ic('download')} Importer<input type="file" id="fs-upload" multiple hidden></label>
    <button class="icon-btn" data-act="fs-refresh" title="Actualiser">${ic('refresh', 18)}</button>`;
  let acc = '';
  const crumbs = (S.fsPath ? S.fsPath.split('/') : []).map((p) => {
    acc = acc ? `${acc}/${p}` : p;
    return `<span class="crumb-sep">›</span><button class="crumb" data-act="fs-go" data-path="${esc(acc)}">${esc(p)}</button>`;
  }).join('');
  const fileCrumb = editing ? `<span class="crumb-sep">›</span><b>${esc(S.fsFile.name)}</b>` : '';
  $('#fs-crumbs').innerHTML = `<button class="crumb" data-act="fs-go" data-path="">/data</button>${crumbs}${fileCrumb}`;
  if (editing) fsEditor(); else loadFs();
}

async function loadFs() {
  const body = $('#fs-body');
  if (!body) return;
  const token = `${S.sel}|${S.fsPath}`;
  body.innerHTML = '<div class="card"><div class="empty">Chargement…</div></div>';
  try {
    const { entries } = await api(fsApi('list'));
    if (token !== `${S.sel}|${S.fsPath}` || S.fsFile || !$('#fs-body')) return;
    const dl = (n) => `/api/servers/${encodeURIComponent(S.sel)}/fs/download?path=${encodeURIComponent(fsJoin(n))}`;
    body.innerHTML = `<div class="card fs-card"><table class="fs-table"><tbody>
      ${S.fsPath ? `<tr class="click" data-act="fs-go" data-path="${esc(fsParent())}"><td colspan="3"><span class="fs-name">${ic('up', 18)} <span>..</span></span></td></tr>` : ''}
      ${entries.map((e) => `<tr>
        <td><button class="fs-name" data-act="fs-open" data-name="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}">${ic(e.dir ? 'folder' : 'file', 18)} <span>${esc(e.name)}</span></button></td>
        <td class="fs-size">${e.dir ? '' : fmtBytes(e.size)}</td>
        <td class="fs-actions">${e.dir ? '' : `<a class="icon-btn" href="${dl(e.name)}" title="Télécharger" download>${ic('download', 18)}</a>`}
          <button class="icon-btn" data-act="fs-rename" data-name="${esc(e.name)}" title="Renommer">${ic('pencil', 18)}</button>
          <button class="icon-btn" data-act="fs-del" data-name="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}" title="Supprimer">${ic('trash', 18)}</button></td></tr>`).join('')}
      </tbody></table>${entries.length ? '' : '<div class="empty">Dossier vide.</div>'}</div>
      <p class="hint" style="margin-top:12px">Glisse des fichiers ici pour les importer dans ce dossier. Certains fichiers sont réécrits par le serveur ou au redémarrage.</p>`;
  } catch (e) { body.innerHTML = `<div class="card"><div class="empty">${esc(e.message)}</div></div>`; }
}

async function fsOpenFile(name) {
  const path = fsJoin(name);
  try {
    const r = await api(`/servers/${encodeURIComponent(S.sel)}/fs/read?path=${encodeURIComponent(path)}`);
    S.fsFile = { path, name, original: r.content };
    fsRender();
  } catch (e) { toast(e.message, true); }
}

function fsEditor() {
  const f = S.fsFile, running = isUp(server(S.sel) || {});
  const props = f.name === 'server.properties';
  $('#fs-body').innerHTML = `<div class="card">
    <div class="chart-head"><div class="hint mono">/data/${esc(f.path)}</div>
      <div style="display:flex;gap:8px;align-items:center"><span class="hint" id="fs-dirty"></span>
        <button class="btn" data-act="fs-close">Fermer</button>
        <button class="btn primary" data-act="fs-save">${ic('save')} Enregistrer</button></div></div>
    ${props ? '<div class="banner" style="margin:12px 0 0">Ce fichier est <b>régénéré au démarrage</b> à partir des paramètres du serveur : tes changements seront écrasés. Modifie plutôt l\'onglet Paramètres du serveur.</div>' : ''}
    <textarea id="fs-editor" class="editor" spellcheck="false" wrap="off">${esc(f.original)}</textarea>
    <p class="hint" style="margin:10px 0 0">Ctrl+S pour enregistrer. ${running ? 'Le serveur tourne : redémarre-le pour appliquer, et sache que le jeu peut réécrire certains fichiers.' : 'Les changements seront pris en compte au prochain démarrage.'}</p></div>`;
  $('#fs-editor').addEventListener('input', fsMarkDirty);
}

const fsDirty = () => S.fsFile && $('#fs-editor') && $('#fs-editor').value !== S.fsFile.original;
function fsMarkDirty() { const el = $('#fs-dirty'); if (el) el.textContent = fsDirty() ? '● modifié' : ''; }

async function fsSave() {
  if (!S.fsFile || !$('#fs-editor')) return false;
  const content = $('#fs-editor').value;
  try {
    await api(`/servers/${encodeURIComponent(S.sel)}/fs/write`, { method: 'PUT', body: { path: S.fsFile.path, content } });
    S.fsFile.original = content;
    fsMarkDirty();
    toast('Fichier enregistré');
    return true;
  } catch (e) { toast(e.message, true); return false; }
}

async function fsUpload(fileList) {
  const files = [...fileList];
  if (!files.length || !S.sel) return;
  let ok = 0;
  for (const [i, file] of files.entries()) {
    toast(`Import de ${file.name} (${i + 1}/${files.length})…`);
    try {
      const res = await fetch(`/api${fsApi('upload', `&filename=${encodeURIComponent(file.name)}`)}`,
        { method: 'PUT', headers: { 'X-Requested-With': 'mc-panel', 'Content-Type': 'application/octet-stream' }, body: file });
      if (!res.ok) {
        let msg = res.statusText;
        try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* corps non JSON */ }
        throw new Error(msg);
      }
      ok++;
    } catch (e) { toast(`${file.name} : ${e.message}`, true); }
  }
  if (ok) toast(`${ok} fichier${ok > 1 ? 's' : ''} importé${ok > 1 ? 's' : ''}`);
  if (!S.fsFile) loadFs();
}

/* Changements de type / version : peuvent rendre un monde existant illisible. */
function versionParts(v) {
  return /^\d+(\.\d+){1,2}$/.test(v) ? v.split('.').map(Number) : null;
}
function riskyChanges(oldSpec, newSpec) {
  const o = oldSpec.env || {}, n = newSpec.env || {};
  const ot = String(o.TYPE || 'VANILLA').toUpperCase(), nt = String(n.TYPE || 'VANILLA').toUpperCase();
  const ov = String(o.VERSION || 'LATEST'), nv = String(n.VERSION || 'LATEST');
  const risks = [];
  if (ot !== nt) {
    risks.push(`Le type passe de <b>${esc(ot)}</b> à <b>${esc(nt)}</b> : les plugins ou mods de l'ancien type ne seront plus chargés, et les objets ou blocs ajoutés par des mods peuvent disparaître du monde.`);
  }
  if (ov.toUpperCase() !== nv.toUpperCase()) {
    const a = versionParts(ov), b = versionParts(nv);
    let down = false;
    if (a && b) { for (let i = 0; i < 3; i++) { const d = (b[i] || 0) - (a[i] || 0); if (d) { down = d < 0; break; } } }
    risks.push(down
      ? `La version <b>baisse</b> de ${esc(ov)} à ${esc(nv)} : <b>risque élevé</b>, Minecraft peut refuser de charger ou abîmer un monde enregistré dans une version plus récente.`
      : `La version passe de ${esc(ov)} à ${esc(nv)} : le monde peut être converti, et un retour en arrière ne sera plus possible sans sauvegarde.`);
  }
  return risks;
}

/* ---------------------------------------------------------------- Mods / Plugins */
const PLUGIN_TYPES = new Set(['PAPER', 'PURPUR', 'SPIGOT', 'BUKKIT', 'FOLIA', 'PUFFERFISH']);
const MOD_TYPES = new Set(['FABRIC', 'FORGE', 'NEOFORGE', 'QUILT']);

function filesKind(spec) {
  const type = String((spec.env || {}).TYPE || 'VANILLA').toUpperCase();
  return PLUGIN_TYPES.has(type) ? 'plugins' : MOD_TYPES.has(type) ? 'mods' : null;
}

function mountFiles(s) {
  const kind = filesKind(s.spec);
  if (!kind) {
    $('#tabbody').innerHTML = `<div class="card"><b>Ce type de serveur n'accepte ni mods ni plugins.</b>
      <p class="hint" style="margin-top:6px">Dans l'onglet Paramètres, choisis le type <b>Paper</b> (plugins) ou <b>Fabric / Forge / NeoForge</b> (mods), puis clique sur « Appliquer ».</p></div>`;
    return;
  }
  const label = kind === 'plugins' ? 'plugins' : 'mods';
  $('#tabbody').innerHTML = `
    <div class="card dropzone" id="dropzone">
      <div><b>Ajouter des ${label}</b></div>
      <p class="hint" style="margin:6px 0 14px">Glisse tes fichiers <b>.jar</b> ici, ou choisis-les depuis ton ordinateur (128 Mo max par fichier).</p>
      <label class="btn primary">${ic('download')} Choisir des fichiers<input type="file" id="file-input" accept=".jar" multiple hidden></label>
      <div id="upload-state" style="margin-top:12px"></div>
    </div>
    <div class="section-title">Installés dans le dossier ${esc(kind)}</div>
    <div class="card" id="file-list"><div class="empty">Chargement…</div></div>
    <p class="hint" style="margin-top:12px">Les changements sont pris en compte au prochain redémarrage du serveur.</p>`;
  loadFiles();
}

async function loadFiles() {
  const s = server(S.sel), kind = s && filesKind(s.spec), box = $('#file-list');
  if (!kind || !box) return;
  try {
    const { files } = await api(`/servers/${encodeURIComponent(S.sel)}/files/${kind}`);
    box.innerHTML = files.length ? `<table><thead><tr><th>Fichier</th><th>Taille</th><th></th></tr></thead><tbody>
      ${files.map((f) => `<tr><td>${esc(f.name)}</td><td>${fmtBytes(f.size)}</td>
        <td style="text-align:right"><button class="icon-btn" data-act="file-del" data-name="${esc(f.name)}" title="Supprimer">${ic('trash', 18)}</button></td></tr>`).join('')}</tbody></table>`
      : `<div class="empty">Aucun fichier pour l'instant.</div>`;
  } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

async function uploadFiles(fileList) {
  const s = server(S.sel), kind = s && filesKind(s.spec), state = $('#upload-state');
  if (!kind || !state) return;
  const files = [...fileList];
  let ok = 0;
  for (const [i, file] of files.entries()) {
    if (!/\.jar$/i.test(file.name)) { toast(`« ${file.name} » ignoré : seuls les .jar sont acceptés.`, true); continue; }
    state.innerHTML = `<div class="notice"><span class="spin"></span> Envoi de ${esc(file.name)} (${i + 1}/${files.length})…</div>`;
    try {
      const res = await fetch(`/api/servers/${encodeURIComponent(S.sel)}/files/${kind}?filename=${encodeURIComponent(file.name)}`,
        { method: 'PUT', headers: { 'X-Requested-With': 'mc-panel', 'Content-Type': 'application/octet-stream' }, body: file });
      if (!res.ok) {
        let msg = res.statusText;
        try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* corps non JSON */ }
        throw new Error(msg);
      }
      ok++;
    } catch (e) { toast(`${file.name} : ${e.message}`, true); }
  }
  state.innerHTML = ok ? `<div class="notice">${ok} fichier${ok > 1 ? 's' : ''} envoyé${ok > 1 ? 's' : ''}. Redémarre le serveur pour les charger.
    ${isUp(server(S.sel)) ? '<button class="btn" data-act="restart" style="margin-left:auto">Redémarrer</button>' : ''}</div>` : '';
  loadFiles();
}

/* ---------------------------------------------------------------- Serveur */
function mountServer() {
  if (!S.sel) {                       // premier serveur, sinon formulaire de création
    const first = (S.ov?.servers || [])[0];
    if (!first) { S.view = 'new'; renderRail(); renderPanel(); mountMain(); return; }
    S.sel = first.name;
    renderPanel();
  }
  const s = server(S.sel);
  if (!s) { go('home'); return; }
  $('#main').innerHTML = `<div id="head"></div>
    <div class="tabs">
      ${[['perf', 'activity', 'Performances'], ['console', 'terminal', 'Console'], ['files', 'box', 'Mods / Plugins'], ['backups', 'save', 'Sauvegardes'], ['settings', 'sliders', 'Paramètres']]
        .map(([id, icon, label]) => `<button class="tab ${S.tab === id ? 'active' : ''}" data-tab="${id}">${ic(icon, 17)}${label}</button>`).join('')}
    </div><div id="tabbody"></div>`;
  if (S.tab === 'files') {
    mountFiles(s);
  } else if (S.tab === 'backups') {
    mountBackups();
  } else if (S.tab === 'console') {
    $('#tabbody').innerHTML = `<pre class="console" id="log"></pre>
      <form class="cmd" id="cmd-form"><input id="cmd" placeholder="Commande (ex. list, say Bonjour, op pseudo)" autocomplete="off"><button class="btn primary">Envoyer</button></form>
      <div class="cmd-out" id="cmd-out"></div>`;
  } else if (S.tab === 'settings') {
    $('#tabbody').innerHTML = serverForm(s.spec, false);
    if (s.spec.access_mode === 'blacklist') loadBans();
  }
}

function liveServerHead(s) {
  const st = statusOf(s), up = isUp(s), b = S.busy ? 'disabled' : '';
  $('#head').innerHTML = `<div class="page-head"><h2>${esc(s.name)}</h2>
    <span class="pill"><span class="led ${st.key}"></span>${st.label}${up ? ` · ${ago(s.started_at)}` : ''}</span>
    <span class="grow"></span>
    ${up ? `<button class="btn" ${b} data-act="restart">${ic('refresh')} Redémarrer</button><button class="btn" ${b} data-act="stop">${ic('stop')} Arrêter</button>`
         : `<button class="btn primary" ${b} data-act="start">${ic('play')} Démarrer</button>`}
    <button class="btn danger" ${b} data-act="delete">${ic('trash')} Supprimer</button></div>`;
}

async function liveServer() {
  const s = server(S.sel);
  if (!s) { go('home'); return; }
  liveServerHead(s);
  const token = `${S.sel}/${S.tab}`;
  if (S.tab === 'perf') {
    let pts = [];
    try { pts = (await api(`/servers/${encodeURIComponent(S.sel)}/stats`)).points; } catch { /* ignoré */ }
    if (token !== `${S.sel}/${S.tab}` || S.view !== 'server') return;
    const t = pts[pts.length - 1] || {};
    const limited = !!s.spec.mem_limit;
    const memMax = limited ? t.mem_limit : null;
    $('#tabbody').innerHTML = `
      <div class="grid cols-4">
        <div class="card"><h3>CPU</h3><div class="stat">${t.cpu != null ? fmtPct(t.cpu) : '—'}</div><div class="sub">100 % = un cœur</div></div>
        <div class="card"><h3>Mémoire</h3><div class="stat">${fmtBytes(t.mem)}</div><div class="sub">${limited ? `limite ${fmtBytes(t.mem_limit)}` : `JVM ${esc(s.spec.memory)}`}</div></div>
        <div class="card"><h3>Joueurs</h3><div class="stat">${t.players ?? '—'}<small>/ ${t.max_players ?? '?'}</small></div><div class="sub">${esc(t.version || '')}</div></div>
        <div class="card"><h3>Latence</h3><div class="stat">${t.latency_ms != null ? t.latency_ms : '—'}<small>ms</small></div><div class="sub">ping Minecraft</div></div>
      </div>
      <div class="grid cols-2" style="margin-top:16px">
        <div class="card"><div class="chart-head"><h3>CPU</h3><span class="hint">${fmtPct(t.cpu)}</span></div>${chart(pts, [{ key: 'cpu' }], { floor: 100 })}</div>
        <div class="card"><div class="chart-head"><h3>Mémoire</h3><span class="hint">${fmtBytes(t.mem)}</span></div>${chart(pts, [{ key: 'mem' }], { max: memMax })}</div>
        <div class="card"><div class="chart-head"><h3>Joueurs</h3><span class="hint">${t.players ?? '—'}</span></div>${chart(pts, [{ key: 'players' }], { floor: 4 })}</div>
        <div class="card"><div class="chart-head"><h3>Réseau</h3><span class="hint">↓ ${fmtRate(t.rx_rate)} · ↑ ${fmtRate(t.tx_rate)}</span></div>${chart(pts, [{ key: 'rx_rate' }, { key: 'tx_rate', cls: 'line2' }], { floor: 1024 })}</div>
      </div>
      <p class="hint" style="margin-top:14px">Historique des 30 dernières minutes, mesuré toutes les 5 s.</p>`;
  } else if (S.tab === 'console') {
    try {
      const logs = cleanLog((await api(`/servers/${encodeURIComponent(S.sel)}/logs?tail=300`)).logs);
      const el = $('#log');
      if (el && token === `${S.sel}/${S.tab}`) {
        const stick = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
        if (el.textContent !== logs) { el.textContent = logs; if (stick) el.scrollTop = el.scrollHeight; }
      }
    } catch { /* ignoré */ }
  } else if (S.tab === 'backups') {
    await loadBackups();
  }
}

/* ---------------------------------------------------------------- Routeur */
const ROUTER_DEFAULT = { image_tag: 'latest', host_port: 25565, mappings: '', env: {} };

function routerForm(spec, exists) {
  const extra = Object.entries(spec.env || {}).map(([k, v]) => `${k}=${v}`).join('\n');
  return `<form id="router-form" autocomplete="off" onsubmit="return false">
    <div class="form-section"><h3>Paramètres du routeur</h3><div class="fields">
      <div class="field"><label>Tag de l'image itzg/mc-router <span class="req">*</span></label><input data-r="image_tag" required value="${esc(spec.image_tag)}"></div>
      <div class="field"><label>Port public (hôte) <span class="req">*</span></label><input data-r="host_port" required type="number" min="1" max="65535" value="${spec.host_port}"><span class="hint">Port sur lequel les joueurs se connectent (25565 par défaut).</span></div>
      <div class="field wide"><label>Routes manuelles supplémentaires</label>
        <textarea data-r="mappings" placeholder="vieux.exemple.com=autre-machine:25565">${esc(spec.mappings)}</textarea>
        <span class="hint">Une route par ligne : hostname=hôte:port. Les serveurs créés ici sont découverts automatiquement via leur hostname.</span></div>
      <div class="field wide"><label>Variables d'environnement personnalisées</label>
        <textarea data-r="env" placeholder="API_KEY=secret">${esc(extra)}</textarea></div>
    </div></div>
    <div class="form-actions"><button class="btn primary" data-act="save-router">${ic('save')} ${exists ? 'Appliquer (recrée le routeur)' : 'Créer le routeur'}</button>
      <span class="hint">Le routeur est recréé : les joueurs connectés sont déconnectés brièvement.</span></div>
  </form>`;
}

function mountRouter() {
  const r = S.ov?.router;
  $('#main').innerHTML = `<div id="head"></div><div id="rlive"></div><div class="section-title">Configuration</div>
    <div id="rform">${routerForm(r?.spec || ROUTER_DEFAULT, !!r?.exists)}</div>`;
}

async function liveRouter() {
  const r = S.ov?.router;
  if (!r) return;
  const up = r.status === 'running', b = S.busy ? 'disabled' : '';
  $('#head').innerHTML = `<div class="page-head"><h2>mc-router</h2>
    <span class="pill"><span class="led ${up ? 'running' : 'exited'}"></span>${r.exists ? (up ? `En ligne · ${ago(r.started_at)}` : r.status) : 'Non créé'}</span><span class="grow"></span>
    ${r.exists ? (up ? `<button class="btn" ${b} data-act="r-restart">${ic('refresh')} Redémarrer</button><button class="btn" ${b} data-act="r-stop">${ic('stop')} Arrêter</button>`
                    : `<button class="btn primary" ${b} data-act="r-start">${ic('play')} Démarrer</button>`)
               + `<button class="btn danger" ${b} data-act="r-delete">${ic('trash')} Supprimer</button>` : ''}</div>`;
  let detail = { stats: r.stats, live_routes: null }, logs = '';
  if (r.exists) {
    try { detail = await api('/router'); } catch { /* ignoré */ }
    try { logs = cleanLog((await api('/router/logs?tail=80')).logs); } catch { /* ignoré */ }
  }
  if (S.view !== 'router') return;
  const t = detail.stats;
  const routes = [];
  for (const s of S.ov.servers) {
    for (const h of (s.spec.hosts || '').split(',').filter(Boolean)) routes.push({ host: h, backend: `mc-${s.name}:25565`, name: s.name, def: s.spec.router_default, up: isUp(s) });
  }
  const live = detail.live_routes;
  $('#rlive').innerHTML = `
    ${r.exists ? `<div class="grid cols-4">
      <div class="card"><h3>CPU</h3><div class="stat">${t ? fmtPct(t.cpu) : '—'}</div></div>
      <div class="card"><h3>Mémoire</h3><div class="stat">${t ? fmtBytes(t.mem) : '—'}</div></div>
      <div class="card"><h3>Trafic</h3><div class="stat" style="font-size:20px">↓ ${t ? fmtRate(t.rx_rate) : '—'}</div><div class="sub">↑ ${t ? fmtRate(t.tx_rate) : '—'}</div></div>
      <div class="card"><h3>Routes actives</h3><div class="stat">${live ? live.length : '—'}</div><div class="sub">${live ? 'selon l\'API mc-router' : 'API injoignable'}</div></div>
    </div>` : '<div class="banner" style="background:#ebe7dc;color:var(--ink-2)">Le routeur n\'existe pas encore. Configure-le ci-dessous puis crée-le : il redirigera les joueurs vers le bon serveur selon le hostname utilisé.</div>'}
    <div class="section-title">Routes (découvertes depuis les serveurs)</div>
    <div class="card">${routes.length ? `<table><thead><tr><th>Hostname</th><th>Serveur</th><th>Backend</th><th>État</th></tr></thead><tbody>
      ${routes.map((x) => `<tr class="click" data-nav="server" data-name="${esc(x.name)}"><td class="mono">${esc(x.host)}</td><td>${esc(x.name)}${x.def ? ' <span class="pill">défaut</span>' : ''}</td>
        <td class="mono">${esc(x.backend)}</td><td><span class="pill"><span class="led ${x.up ? 'running' : 'exited'}"></span>${x.up ? 'en ligne' : 'arrêté'}</span></td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">Aucun serveur n\'a de hostname. Renseigne-le dans ses paramètres (section Réseau).</div>'}</div>
    ${r.exists ? `<div class="section-title">Journal du routeur</div><pre class="console" id="rlog" style="height:240px"></pre>` : ''}`;
  const el = $('#rlog');
  if (el) { el.textContent = logs; el.scrollTop = el.scrollHeight; }
}

/* ---------------------------------------------------------------- Docker */
async function mountDocker() {
  $('#main').innerHTML = `<div class="page-head"><h2>Docker</h2></div><div id="dinfo"></div>
    <div class="section-title">Images</div><div class="card" id="dimages"><div class="empty">Chargement…</div></div>
    <div class="section-title">Télécharger / mettre à jour une image</div>
    <div class="card"><div class="fields" style="align-items:end">
      <div class="field"><label>Image</label><select id="pull-kind"><option value="server">itzg/minecraft-server</option><option value="router">itzg/mc-router</option></select></div>
      <div class="field"><label>Tag</label><input id="pull-tag" value="latest"></div>
      <div class="field"><button class="btn primary" data-act="pull">${ic('download')} Télécharger</button></div></div>
      <p class="hint">Après une mise à jour de <code>latest</code>, ouvre les paramètres du serveur et clique sur « Appliquer » pour le recréer avec la nouvelle image.</p></div>`;
  try {
    const { images } = await api('/images');
    $('#dimages').innerHTML = images.length ? `<table><thead><tr><th>Image</th><th>Taille</th><th>Créée</th></tr></thead><tbody>
      ${images.map((i) => `<tr><td class="mono">${esc(i.tag)}</td><td>${fmtBytes(i.size)}</td><td>${esc((i.created || '').slice(0, 10))}</td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">Aucune image itzg téléchargée pour l\'instant.</div>';
  } catch (e) { $('#dimages').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

function liveDocker() {
  const d = S.ov?.docker;
  if (!d || !$('#dinfo')) return;
  $('#dinfo').innerHTML = d.ok ? `<div class="grid cols-4">
      <div class="card"><h3>Version</h3><div class="stat" style="font-size:22px">${esc(d.version)}</div><div class="sub">${esc(d.os || '')}</div></div>
      <div class="card"><h3>Conteneurs</h3><div class="stat">${d.containers_running}<small>/ ${d.containers_total}</small></div><div class="sub">en cours / total</div></div>
      <div class="card"><h3>Images</h3><div class="stat">${d.images}</div></div>
      <div class="card"><h3>Ressources</h3><div class="stat">${d.cpus}<small>cœurs</small></div><div class="sub">${fmtBytes(d.mem_total)} de RAM</div></div></div>`
    : `<div class="banner">${esc(d.error)}</div>`;
}

/* ======================================================================
   Mise à jour périodique
   ====================================================================== */
async function updateLive() {
  if (S.view === 'home') liveHome();
  else if (S.view === 'server') await liveServer();
  else if (S.view === 'router') await liveRouter();
  else if (S.view === 'docker') liveDocker();
}

async function tick() {
  try { S.ov = await api('/overview'); S.err = null; } catch (e) { S.err = e.message; }
  renderWarn();
  renderRail(); renderPanel();
  if (S.view === 'server' && S.ov && !server(S.sel)) { go('home'); return; }
  if (S.view === 'fs' && S.ov && S.sel && !server(S.sel)) { go('fs'); return; }
  await updateLive();
}

/* ======================================================================
   Actions
   ====================================================================== */
async function run(label, fn) {
  S.busy = true; updateLive();
  try { await fn(); } catch (e) { toast(`${label} : ${e.message}`, true); }
  S.busy = false;
  await tick();
}

/* ======================================================================
   Profil : compte et mise à jour du logiciel
   ====================================================================== */
const modal = { user: '', updating: false };

function closeModal() {
  if (modal.updating) return;
  $('#modal').innerHTML = '';
}

const modalShell = (inner) => `<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true">${inner}</div></div>`;

function profileHtml(acc, sys) {
  const latest = sys?.latest;
  let badge = '<span class="pill">Version inconnue</span>';
  if (sys?.up_to_date === true) badge = '<span class="pill"><span class="led running"></span>À jour</span>';
  else if (sys?.up_to_date === false) badge = '<span class="pill"><span class="led starting"></span>Mise à jour disponible</span>';
  const date = latest ? new Date(latest.date).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }) : '';
  const blocked = !sys?.supported || !latest;
  return modalShell(`
    <div class="modal-head"><h2>Profil</h2><button class="btn" data-act="close-modal">Fermer</button></div>

    <div class="form-section"><h3>Compte</h3>
      <div class="fields" style="grid-template-columns:1fr">
        <div class="field"><label for="acc-user">Nom d'utilisateur</label><input id="acc-user" value="${esc(acc.username)}" autocomplete="username"></div>
        <div class="field"><label for="acc-cur">Mot de passe actuel <span class="req">*</span></label><input id="acc-cur" type="password" autocomplete="current-password"></div>
        <div class="field"><label for="acc-new">Nouveau mot de passe</label><input id="acc-new" type="password" autocomplete="new-password"><span class="hint">8 caractères minimum. Laisse vide pour ne pas le changer.</span></div>
        <div class="field"><label for="acc-new2">Confirmer le nouveau mot de passe</label><input id="acc-new2" type="password" autocomplete="new-password"></div>
      </div>
      <div style="margin-top:14px"><button class="btn primary" data-act="save-account">${ic('save')} Enregistrer</button>
        <span class="hint" style="margin-left:10px">Tu devras te reconnecter ensuite.</span></div>
    </div>

    <div class="form-section"><h3>Logiciel</h3>
      <div class="kv"><span>Version installée</span><b class="mono">${esc(sys?.current || 'inconnue')}</b></div>
      <div class="kv"><span>Dernière version</span><b class="mono">${esc(latest?.short || 'GitHub injoignable')}</b></div>
      ${latest ? `<div class="hint" style="margin:2px 0 10px">${esc(latest.message)} · ${esc(date)}</div>` : ''}
      <div style="margin:10px 0">${badge}</div>
      <button class="btn primary" data-act="do-update" ${blocked ? 'disabled' : ''}>${ic('download')} Mettre à jour</button>
      <div id="upd-state" style="margin-top:12px"></div>
      <p class="hint" style="margin-top:10px">${!sys ? 'Impossible de lire les informations de version.'
        : !sys.supported ? 'Mise à jour indisponible : lance le panel avec le docker-compose.yml fourni (volume .:/project).'
        : 'Reconstruit le panel depuis GitHub. Tes serveurs Minecraft ne sont pas interrompus.'}</p>
    </div>`);
}

async function openProfile() {
  $('#modal').innerHTML = modalShell('<div class="empty">Chargement…</div>');
  let acc;
  try { acc = await api('/account'); } catch (e) { toast(e.message, true); closeModal(); return; }
  modal.user = acc.username;
  let sys = null;
  try { sys = await api('/system'); } catch { /* version indisponible */ }
  $('#modal').innerHTML = profileHtml(acc, sys);
  if (sys?.update?.state === 'running') watchUpdate();
}

async function watchUpdate() {
  modal.updating = true;
  const setBox = (html) => { const el = $('#upd-state'); if (el) el.innerHTML = html; };
  const btn = $('[data-act="do-update"]'); if (btn) btn.disabled = true;
  setBox('<div class="notice"><span class="spin"></span> Reconstruction du panel en cours (quelques minutes). Ne ferme pas cette page.</div>');
  let sawDown = false, sawRunning = false;
  const deadline = Date.now() + 20 * 60 * 1000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 3000));
    try {
      const st = await api('/system/update');
      if (st.state === 'failed') {
        modal.updating = false;
        setBox(`<div class="banner">La mise à jour a échoué (le panel actuel reste en place).</div><pre class="console" style="height:170px">${esc(st.logs || '')}</pre>`);
        if (btn) btn.disabled = false;
        return;
      }
      if (st.state === 'running') sawRunning = true;
      // « idle » après avoir vu l'updater tourner = le nouveau panel a démarré et l'a nettoyé.
      if (st.state === 'done' || (st.state === 'idle' && (sawDown || sawRunning))) { location.reload(); return; }
    } catch {
      sawDown = true;
      setBox('<div class="notice"><span class="spin"></span> Redémarrage du panel…</div>');
    }
  }
  modal.updating = false;
  setBox('<div class="banner">Délai dépassé. Vérifie <code>docker logs mc-panel-updater</code> sur le serveur.</div>');
}

const ACTIONS = {
  'fs-go': async (btn) => {
    if (S.fsFile && fsDirty() && !(await askModal({ title: 'Modifications non enregistrées', body: '<p style="margin:0">Quitter ce fichier sans enregistrer ?</p>', confirmLabel: 'Quitter sans enregistrer', danger: true })).ok) return;
    S.fsFile = null; S.fsPath = btn.dataset.path; fsRender();
  },
  'fs-open': (btn) => {
    if (btn.dataset.dir === '1') { S.fsPath = fsJoin(btn.dataset.name); fsRender(); } else fsOpenFile(btn.dataset.name);
  },
  'fs-refresh': () => loadFs(),
  'fs-close': async () => {
    if (fsDirty() && !(await askModal({ title: 'Modifications non enregistrées', body: '<p style="margin:0">Fermer ce fichier sans enregistrer ?</p>', confirmLabel: 'Fermer sans enregistrer', danger: true })).ok) return;
    S.fsFile = null; fsRender();
  },
  'fs-save': () => fsSave(),
  'fs-new-file': async () => {
    const { ok, value } = await askModal({ title: 'Nouveau fichier', confirmLabel: 'Créer', input: { label: `Nom du fichier dans /data/${S.fsPath}`, placeholder: 'exemple.yml' } });
    const name = value.trim();
    if (!ok || !name) return;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/fs/create`, { method: 'POST', body: { path: fsJoin(name), kind: 'file' } }); await fsOpenFile(name); }
    catch (e) { toast(e.message, true); }
  },
  'fs-new-dir': async () => {
    const { ok, value } = await askModal({ title: 'Nouveau dossier', confirmLabel: 'Créer', input: { label: `Nom du dossier dans /data/${S.fsPath}`, placeholder: 'mon-dossier' } });
    const name = value.trim();
    if (!ok || !name) return;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/fs/create`, { method: 'POST', body: { path: fsJoin(name), kind: 'dir' } }); toast('Dossier créé'); }
    catch (e) { toast(e.message, true); }
    loadFs();
  },
  'fs-rename': async (btn) => {
    const old = btn.dataset.name;
    const { ok, value } = await askModal({ title: 'Renommer', confirmLabel: 'Renommer', input: { label: 'Nouveau nom', value: old } });
    const name = value.trim();
    if (!ok || !name || name === old) return;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/fs/rename`, { method: 'POST', body: { path: fsJoin(old), new_name: name } }); toast('Renommé'); }
    catch (e) { toast(e.message, true); }
    loadFs();
  },
  'fs-del': async (btn) => {
    const name = btn.dataset.name, isDir = btn.dataset.dir === '1';
    const { ok } = await askModal({ title: isDir ? 'Supprimer le dossier' : 'Supprimer le fichier', confirmLabel: 'Supprimer', danger: true,
      body: `<p style="margin:0 0 8px">Supprimer définitivement ${isDir ? 'ce dossier <b>et tout son contenu</b>' : 'ce fichier'} ? Cette action est irréversible.</p>
        <p class="hint mono" style="margin:0">/data/${esc(fsJoin(name))}</p>` });
    if (!ok) return;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/fs?path=${encodeURIComponent(fsJoin(name))}`, { method: 'DELETE' }); toast('Supprimé'); }
    catch (e) { toast(e.message, true); }
    loadFs();
  },
  'backup-create': async () => {
    try { await api(`/servers/${encodeURIComponent(S.sel)}/backups`, { method: 'POST' }); toast('Sauvegarde lancée'); }
    catch (e) { toast(e.message, true); }
    loadBackups();
  },
  'backup-del': async (btn) => {
    const file = btn.dataset.file;
    const { ok } = await askModal({ title: 'Supprimer la sauvegarde', confirmLabel: 'Supprimer', danger: true,
      body: `<p style="margin:0">Supprimer définitivement cette sauvegarde ?</p><p class="hint mono" style="margin-top:8px">${esc(file)}</p>` });
    if (!ok) return;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/backups/${encodeURIComponent(file)}`, { method: 'DELETE' }); toast('Sauvegarde supprimée'); }
    catch (e) { toast(e.message, true); }
    loadBackups();
  },
  'backup-restore': async (btn) => {
    const file = btn.dataset.file;
    const { ok } = await askModal({ title: 'Restaurer cette sauvegarde', confirmLabel: 'Restaurer', danger: true,
      body: `<p style="margin:0 0 10px">Tout le contenu actuel du serveur <b>${esc(S.sel)}</b> (monde, configuration, plugins, mods) sera <b>remplacé</b> par cette sauvegarde.</p>
        <ul class="ask-list"><li>Une sauvegarde « avant restauration » de l'état actuel est créée d'abord.</li>
        <li>Le serveur est arrêté puis redémarré automatiquement s'il tournait.</li></ul>
        <p class="hint mono" style="margin-top:8px">${esc(file)}</p>` });
    if (!ok) return;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/backups/${encodeURIComponent(file)}/restore`, { method: 'POST' }); toast('Restauration lancée'); }
    catch (e) { toast(e.message, true); }
    loadBackups();
  },
  'file-del': async (btn) => {
    const name = btn.dataset.name, s = server(S.sel), kind = s && filesKind(s.spec);
    if (!kind || !confirm(`Supprimer « ${name} » ?`)) return;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/files/${kind}?filename=${encodeURIComponent(name)}`, { method: 'DELETE' }); toast('Fichier supprimé'); }
    catch (e) { toast(e.message, true); }
    loadFiles();
  },
  access: (btn) => {
    const mode = btn.dataset.mode, form = btn.closest('form');
    form.querySelector('[data-f="access_mode"]').value = mode;
    form.querySelectorAll('.seg-btn').forEach((b) => b.classList.toggle('on', b === btn));
    form.querySelectorAll('.access-pane').forEach((p) => { p.hidden = p.dataset.pane !== mode; });
    $('#access-hint').textContent = { none: 'Tout le monde peut se connecter.', whitelist: 'Seuls les joueurs de la liste peuvent se connecter.',
      blacklist: 'Les joueurs de la liste sont bannis ; tous les autres peuvent se connecter.' }[mode];
    if (mode === 'blacklist') loadBans();
  },
  'ban-add': async () => {
    const input = $('#ls-BAN'), names = input.value.split(/[\s,]+/).filter(Boolean);
    try {
      for (const player of names) await api(`/servers/${encodeURIComponent(S.sel)}/ban`, { method: 'POST', body: { player } });
      input.value = '';
      if (names.length) toast(names.length > 1 ? 'Joueurs bannis' : `${names[0]} banni`);
    } catch (e) { toast(e.message, true); }
    loadBans();
  },
  'ban-del': async (btn) => {
    const player = btn.closest('li').dataset.name;
    try { await api(`/servers/${encodeURIComponent(S.sel)}/pardon`, { method: 'POST', body: { player } }); toast(`${player} débanni`); }
    catch (e) { toast(e.message, true); }
    loadBans();
  },
  'list-add': (btn) => plistAdd(btn.closest('.plist')),
  'list-del': (btn) => plistRemove(btn.closest('li')),
  profile: () => openProfile(),
  'close-modal': () => closeModal(),
  'save-account': async (btn) => {
    const cur = $('#acc-cur').value, user = $('#acc-user').value.trim();
    const np = $('#acc-new').value, np2 = $('#acc-new2').value;
    if (!cur) { toast('Entre ton mot de passe actuel.', true); return; }
    if (np !== np2) { toast('Les deux nouveaux mots de passe sont différents.', true); return; }
    const body = { current_password: cur, new_username: user && user !== modal.user ? user : null, new_password: np || null };
    if (!body.new_username && !body.new_password) { toast('Rien à modifier.', true); return; }
    btn.disabled = true;
    try {
      await api('/account', { method: 'POST', body });
      toast('Identifiants modifiés — reconnexion…');
      setTimeout(() => location.reload(), 1200);
    } catch (e) { toast(e.message, true); btn.disabled = false; }
  },
  'do-update': async (btn) => {
    if (!confirm('Mettre à jour le panel ?\n\nIl sera reconstruit depuis GitHub puis redémarré (quelques secondes d\'indisponibilité). Tes serveurs Minecraft ne sont pas touchés.')) return;
    btn.disabled = true;
    try {
      const r = await api('/system/update', { method: 'POST' });
      toast(`Mise à jour vers ${r.target} lancée`);
      watchUpdate();
    } catch (e) { toast(e.message, true); btn.disabled = false; }
  },
  start: () => run('Démarrage', async () => { await api(`/servers/${S.sel}/start`, { method: 'POST' }); toast('Serveur démarré'); }),
  stop: () => run('Arrêt', async () => { toast('Arrêt en cours (sauvegarde du monde)…'); await api(`/servers/${S.sel}/stop`, { method: 'POST' }); toast('Serveur arrêté'); }),
  restart: () => run('Redémarrage', async () => { toast('Redémarrage en cours…'); await api(`/servers/${S.sel}/restart`, { method: 'POST' }); toast('Serveur redémarré'); }),
  delete: async () => {
    if (!confirm(`Supprimer le serveur « ${S.sel} » ?`)) return;
    const wipe = confirm('Supprimer AUSSI le monde et toutes les données ?\n\nOK = tout effacer (irréversible)\nAnnuler = garder les données (volume conservé)');
    const name = S.sel;
    await run('Suppression', async () => { await api(`/servers/${name}?remove_data=${wipe}`, { method: 'DELETE' }); toast('Serveur supprimé'); });
    go('home');
  },
  'save-server': async (btn) => {
    const isNew = btn.dataset.new === '1';
    if (!$('#srv-form').reportValidity()) return;
    let spec;
    try { spec = readServerForm(); } catch (e) { toast(e.message, true); return; }
    if (isNew && !$('#srv-form [data-f="eula"]').checked) { toast('Accepte l\'EULA de Minecraft pour continuer.', true); return; }
    let backupFirst = false;
    if (!isNew) {
      const risks = riskyChanges(server(S.sel)?.spec || {}, spec);
      if (risks.length) {
        const answer = await askModal({
          title: 'Changement risqué', confirmLabel: 'Appliquer quand même',
          body: `<p style="margin:0 0 10px">Ce serveur existe déjà. Ce changement peut abîmer son monde :</p><ul class="ask-list">${risks.map((r) => `<li>${r}</li>`).join('')}</ul>`,
          check: { label: 'Faire une sauvegarde avant d\'appliquer (recommandé)', checked: true },
        });
        if (!answer.ok) return;
        backupFirst = answer.checked;
      }
    }
    btn.disabled = true; btn.innerHTML = '<span class="spin"></span> En cours…';
    if (backupFirst) {
      try {
        toast('Sauvegarde du monde en cours…');
        btn.innerHTML = '<span class="spin"></span> Sauvegarde…';
        await backupAndWait('avant-modif');
        btn.innerHTML = '<span class="spin"></span> En cours…';
      } catch (e) {
        toast(`Sauvegarde impossible, changement annulé : ${e.message}`, true);
        btn.disabled = false; btn.innerHTML = `${ic('save')} Appliquer`;
        return;
      }
    }
    toast(isNew ? 'Création… (téléchargement de l\'image si nécessaire)' : 'Application… le serveur est recréé');
    try {
      await api(isNew ? '/servers' : `/servers/${encodeURIComponent(S.sel)}`, { method: isNew ? 'POST' : 'PUT', body: spec });
      toast(isNew ? 'Serveur créé' : 'Paramètres appliqués');
      S.ov = await api('/overview');
      go('server', spec.name, isNew ? 'perf' : 'settings');
    } catch (e) {
      toast(e.message, true);
      btn.disabled = false; btn.innerHTML = `${ic('save')} ${isNew ? 'Créer le serveur' : 'Appliquer'}`;
    }
  },
  'r-start': () => run('Routeur', () => api('/router/start', { method: 'POST' })),
  'r-stop': () => run('Routeur', () => api('/router/stop', { method: 'POST' })),
  'r-restart': () => run('Routeur', () => api('/router/restart', { method: 'POST' })),
  'r-delete': async () => { if (confirm('Supprimer le routeur ?')) await run('Routeur', () => api('/router', { method: 'DELETE' })); mountMain(); },
  'save-router': async (btn) => {
    if (!$('#router-form').reportValidity()) return;
    const f = (k) => $(`#router-form [data-r="${k}"]`).value.trim();
    const env = {};
    f('env').split('\n').forEach((l) => { const i = l.indexOf('='); if (i > 0) env[l.slice(0, i).trim()] = l.slice(i + 1).trim(); });
    btn.disabled = true; btn.innerHTML = '<span class="spin"></span> En cours…';
    try {
      await api('/router', { method: 'PUT', body: { image_tag: f('image_tag') || 'latest', host_port: Number(f('host_port')) || 25565, mappings: f('mappings'), env } });
      toast('Routeur appliqué');
      await tick(); mountMain(); updateLive();
    } catch (e) { toast(e.message, true); btn.disabled = false; btn.innerHTML = `${ic('save')} Appliquer`; }
  },
  pull: async (btn) => {
    const kind = $('#pull-kind').value, tag = $('#pull-tag').value.trim() || 'latest';
    btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Téléchargement…';
    try { await api(`/images/pull?kind=${kind}&tag=${encodeURIComponent(tag)}`, { method: 'POST' }); toast('Image à jour'); mountDocker(); }
    catch (e) { toast(e.message, true); btn.disabled = false; btn.innerHTML = `${ic('download')} Télécharger`; }
  },
};

document.addEventListener('change', (e) => {
  if (e.target.id === 'file-input') { uploadFiles(e.target.files); e.target.value = ''; }
  if (e.target.id === 'fs-upload') { fsUpload(e.target.files); e.target.value = ''; }
});
['dragover', 'dragleave', 'drop'].forEach((type) => document.addEventListener(type, (e) => {
  const zone = e.target.closest?.('#dropzone, #fs-body');
  if (!zone || (zone.id === 'fs-body' && S.fsFile)) return;     // pas d'envoi par glisser pendant l'édition
  e.preventDefault();
  zone.classList.toggle('over', type === 'dragover');
  if (type === 'drop') (zone.id === 'fs-body' ? fsUpload : uploadFiles)(e.dataTransfer.files);
}));

const closeDropdowns = (except = null) => document.querySelectorAll('.dd-list:not([hidden])').forEach((l) => { if (l !== except) l.hidden = true; });

document.addEventListener('keydown', (e) => {
  if (e.target.id === 'fs-editor') {   // Ctrl+S enregistre ; Tab insère deux espaces (utile en YAML)
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); fsSave(); return; }
    if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      const t = e.target, a = t.selectionStart;
      t.setRangeText('  ', a, t.selectionEnd, 'end');
      fsMarkDirty();
      return;
    }
  }
  if (e.key === 'Escape') { closeDropdowns(); closeModal(); }
  if (e.key === 'Enter' && e.target.classList?.contains('plist-input')) {
    e.preventDefault();
    if (e.target.id === 'ls-BAN') ACTIONS['ban-add'](); else plistAdd(e.target.closest('.plist'));
  }
});

document.addEventListener('click', (e) => {
  const ddBtn = e.target.closest('.dd-btn');
  if (ddBtn) {
    const list = ddBtn.nextElementSibling;
    closeDropdowns(list);
    list.hidden = !list.hidden;
    return;
  }
  const ddItem = e.target.closest('.dd-list li');
  if (ddItem) {
    const dd = ddItem.closest('.dd');
    dd.querySelector('input[type=hidden]').value = ddItem.dataset.v;
    dd.querySelector('.dd-text').innerHTML = ddItem.innerHTML;
    dd.querySelector('.dd-list').hidden = true;
    return;
  }
  closeDropdowns();
  if (e.target.classList?.contains('modal-backdrop')) { closeModal(); return; }
  const nav = e.target.closest('[data-nav]');
  if (nav) {
    e.preventDefault();
    go(nav.dataset.nav, nav.dataset.name || null);
    return;
  }
  const tab = e.target.closest('[data-tab]');
  if (tab) { S.tab = tab.dataset.tab; mountServer(); updateLive(); return; }
  const act = e.target.closest('[data-act]');
  if (act && ACTIONS[act.dataset.act]) { e.preventDefault(); ACTIONS[act.dataset.act](act); }
});

document.addEventListener('submit', async (e) => {
  if (e.target.id !== 'cmd-form') return;
  e.preventDefault();
  const input = $('#cmd');
  // Les commandes Minecraft sont en minuscules (« HELP » est inconnu) ; les arguments gardent leur casse.
  const command = input.value.trim().replace(/^\S+/, (w) => w.toLowerCase());
  if (!command) return;
  input.value = '';
  try {
    const { output } = await api(`/servers/${encodeURIComponent(S.sel)}/command`, { method: 'POST', body: { command } });
    $('#cmd-out').textContent = `> ${command}\n${cleanLog(output) || '(aucune réponse)'}`;
  } catch (err) { toast(err.message, true); }
  updateLive();
});

$('#filter').addEventListener('input', (e) => { S.filter = e.target.value; renderPanel(); });

(async function init() {
  go('home');
  await tick();
  setInterval(tick, 3000);
})();
