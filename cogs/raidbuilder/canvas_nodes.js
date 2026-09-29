// Embedded into the offline editor by canvas.py. Imported files are JSON data only.
const nodeSchema = 'fablereborn.raid-node';
const nodeCollections = ['teams', 'roles', 'statuses', 'resources', 'actions'];
const systemSources = [
  ['party_level_total', 'Total character levels'],
  ['party_level_average', 'Average character level'],
  ['party_guild_members', 'Players who belong to a guild'],
  ['party_guild_count', 'Distinct party guilds'],
];
const serverCatalogue = decode('__NODE_LIBRARY_BASE64__');
const serverNodes = serverCatalogue.entries;
const promptText = new TextDecoder().decode(Uint8Array.from(atob('__NODE_PROMPT_BASE64__'), c => c.charCodeAt(0)));
const nodeStorageKey = 'fable-node-packs:v1';
let localNodes = [];
try { const saved = JSON.parse(localStorage.getItem(nodeStorageKey) || '[]'); if (Array.isArray(saved)) localNodes = saved; } catch {}
let nodeDraft = { name: 'My custom mechanic', description: '', entry: selected, selected: [selected], after: '', query: '' };

function downloadText(name, content, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = el('a', { href: url, download: name });
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function defaultNodeCatalogues() {
  return {
    teams: [{ id: 'party', label: 'Party' }],
    roles: [{ id: 'adventurer', label: 'Adventurer', team: 'party', hp: 0, slots: 0 }],
    statuses: [], resources: [{ id: 'corruption', label: 'Corruption', initial: 0, min: 0, max: 100 }],
    actions: [
      { id: 'strike', label: 'Strike', effect: 'boss_damage', target: 'self', amount: 20, resource: '', cost_resource: '', cost: 0 },
      { id: 'mend', label: 'Mend', effect: 'heal', target: 'lowest', amount: 15, resource: '', cost_resource: '', cost: 0 },
    ],
  };
}

function normalizeNodePack(candidate) {
  if (new TextEncoder().encode(JSON.stringify(candidate)).length > 250000) throw new Error('Node packs must be smaller than 250 KB.');
  if (!candidate || candidate.schema !== nodeSchema || candidate.version !== 1) throw new Error('Choose a Fable .node.json pack, version 1.');
  if (typeof candidate.name !== 'string' || !candidate.name.trim() || candidate.name.length > 100 ||
      typeof (candidate.description ?? '') !== 'string' || (candidate.description || '').length > 1000) throw new Error('Use a name of 1–100 characters and description of at most 1000.');
  if (!Array.isArray(candidate.nodes) || !candidate.nodes.length || candidate.nodes.length > 30) throw new Error('A node pack needs 1–30 steps.');
  const result = { schema: nodeSchema, version: 1, name: candidate.name.trim(), description: (candidate.description || '').trim(), entry: candidate.entry,
    nodes: candidate.nodes.map(n => ({ ...nodeDefault(n.id, n.kind || 'scene'), ...clone(n) })), catalogues: defaultNodeCatalogues() };
  for (const key of nodeCollections) if (candidate.catalogues && key in candidate.catalogues) result.catalogues[key] = clone(candidate.catalogues[key]);
  const ids = new Set(result.nodes.map(n => n.id));
  if (!ids.has(result.entry) || ids.has('pack_success') || ids.has('pack_failure')) throw new Error('Choose an entry inside this pack; pack_success and pack_failure are reserved.');
  const graph = new Map();
  for (const n of result.nodes) {
    graph.set(n.id, edges(n).map(e => e.object[e.key]));
    for (const target of graph.get(n.id)) if (!ids.has(target) && !['$next', '$failure'].includes(target)) throw new Error(`${n.title}: links must stay inside the pack or use $next / $failure.`);
  }
  const visited = new Set(), pending = [result.entry];
  while (pending.length) { const id = pending.pop(); if (!visited.has(id)) { visited.add(id); pending.push(...(graph.get(id) || [])); } }
  if (result.nodes.some(n => !visited.has(n.id))) throw new Error('Every selected step must be reachable from the pack entry.');
  const trial = { version: 2, start: result.entry, player_hp: 100, max_steps: 250, layout: {}, ...clone(result.catalogues), nodes: clone(result.nodes) };
  for (const n of trial.nodes) for (const edge of edges(n)) {
    if (edge.object[edge.key] === '$next') edge.object[edge.key] = 'pack_success';
    if (edge.object[edge.key] === '$failure') edge.object[edge.key] = 'pack_failure';
  }
  trial.nodes.push({ ...nodeDefault('pack_success', 'ending'), outcome: 'victory' }, { ...nodeDefault('pack_failure', 'ending'), outcome: 'defeat' });
  const errors = validateNodeSpec(trial);
  if (errors.length) throw new Error(errors.slice(0, 5).join('\n'));
  return result;
}

function validateNodeSpec(encounter) {
  const original = pack;
  try { pack = clone(pack); pack.definition.config.encounter = encounter; return validate(); }
  finally { pack = original; }
}

function extractNodePack() {
  const ids = [nodeDraft.entry, ...nodeDraft.selected.filter(id => id !== nodeDraft.entry)];
  if (!nodeDraft.selected.includes(nodeDraft.entry)) throw new Error('Include the entry in the selected steps.');
  const selectedNodes = ids.map(id => { const n = nodes().find(n => n.id === id); if (!n) throw new Error('Choose existing steps.'); return clone(n); });
  for (const n of selectedNodes) for (const edge of edges(n)) {
    if (!ids.includes(edge.object[edge.key])) {
      const target = nodes().find(n => n.id === edge.object[edge.key]);
      if (!target) throw new Error('Fix missing step links before saving this pack.');
      edge.object[edge.key] = edge.key === 'failure' || target.kind === 'ending' && target.outcome === 'defeat' ? '$failure' : '$next';
    }
  }
  return normalizeNodePack({ schema: nodeSchema, version: 1, name: nodeDraft.name, description: nodeDraft.description,
    entry: nodeDraft.entry, nodes: selectedNodes, catalogues: Object.fromEntries(nodeCollections.map(k => [k, clone(spec()[k])])) });
}

function saveLocalNode(candidate) {
  const normalized = normalizeNodePack(candidate);
  if (localNodes.length >= 100) throw new Error('This browser already has 100 node packs. Delete an entry first.');
  const updated = [...localNodes, normalized];
  localStorage.setItem(nodeStorageKey, JSON.stringify(updated));
  localNodes = updated;
  return normalized;
}

function nodeUnique(key, used) {
  let candidate = key.slice(0, 64), n = 1;
  while (used.has(candidate)) { const suffix = '_' + n++; candidate = key.slice(0, 64 - suffix.length) + suffix; }
  used.add(candidate); return candidate;
}

function sameData(a, b) {
  if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((v, i) => sameData(v, b[i]));
  if (a && typeof a === 'object') return b && typeof b === 'object' && Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => Object.hasOwn(b, k) && sameData(a[k], b[k]));
  return a === b;
}

function compileNodePack(candidate, after) {
  const template = normalizeNodePack(candidate), result = clone(spec());
  const anchor = after ? result.nodes.find(n => n.id === after) : null;
  if (after && (!anchor || ['choice', 'ending'].includes(anchor.kind))) throw new Error('Choose a step with a Next output.');
  const success = anchor ? anchor.next : result.start;
  const failure = (anchor && ['battle', 'trial', 'check', 'system'].includes(anchor.kind) && anchor.failure) || result.nodes.find(n => n.kind === 'ending' && n.outcome === 'defeat')?.id || success;
  const maps = {}, nodeMap = new Map(), usedNodes = new Set(result.nodes.map(n => n.id));
  for (const n of template.nodes) nodeMap.set(n.id, nodeUnique('custom_' + n.id, usedNodes));
  for (const collection of nodeCollections) {
    const used = new Set(result[collection].map(i => i.id)), mapping = maps[collection] = new Map();
    for (const item of template.catalogues[collection]) {
      const adjusted = clone(item); if (collection === 'roles') adjusted.team = maps.teams.get(item.team);
      const same = result[collection].find(i => sameData(i, adjusted));
      mapping.set(item.id, same && ['teams', 'roles'].includes(collection) ? same.id : nodeUnique('custom_' + item.id, used));
    }
  }
  const enemyMap = new Map(), usedEnemies = new Set(['boss', ...result.nodes.flatMap(n => (n.enemies || []).map(e => e.id))]);
  for (const n of template.nodes) for (const e of n.enemies || []) if (!enemyMap.has(e.id)) enemyMap.set(e.id, e.id === 'boss' ? 'boss' : nodeUnique('custom_' + e.id, usedEnemies));
  function remap(value) {
    if (Array.isArray(value)) return value.map(remap);
    if (!value || typeof value !== 'object') return value;
    const out = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, remap(v)]));
    for (const [key, collection] of [['resource','resources'],['cost_resource','resources'],['output_resource','resources'],['status','statuses'],['on_hit_status','statuses'],['team','teams']])
      if (key in out) out[key] = maps[collection].get(out[key]) ?? out[key];
    if (out.roles) out.roles = out.roles.map(r => maps.roles.get(r) ?? r);
    for (const key of ['subject','target']) {
      const v = out[key]; if (typeof v !== 'string') continue;
      if (key === 'subject' && maps.resources.has(v)) out[key] = maps.resources.get(v);
      else if (v.includes(':')) {
        const [prefix, id] = v.split(':');
        const mapping = { team: maps.teams, team_alive: maps.teams, role: maps.roles, role_alive: maps.roles,
          status_count: maps.statuses, enemy: enemyMap, enemy_hp: enemyMap }[prefix];
        out[key] = prefix + ':' + (mapping?.get(id) ?? id);
      }
    }
    return out;
  }
  for (const collection of nodeCollections) for (const item of template.catalogues[collection]) {
    const id = maps[collection].get(item.id);
    if (!result[collection].some(i => i.id === id)) result[collection].push({ ...remap(item), id });
  }
  const originalNodeCount = result.nodes.length;
  template.nodes.forEach((original, index) => {
    const n = remap(original); n.id = nodeMap.get(n.id);
    for (const e of n.enemies || []) e.id = enemyMap.get(e.id);
    for (const edge of edges(n)) { const to = edge.object[edge.key]; edge.object[edge.key] = to === '$next' ? success : to === '$failure' ? failure : nodeMap.get(to); }
    n.pack_name = template.name; result.nodes.push(n);
    const position = originalNodeCount + index;
    result.layout[n.id] = { x: 50 + position % 4 * 285, y: 50 + Math.floor(position / 4) * 250 };
  });
  const entry = nodeMap.get(template.entry);
  if (anchor) anchor.next = entry; else result.start = entry;
  const errors = validateNodeSpec(result); if (errors.length) throw new Error(errors.slice(0, 5).join('\n'));
  return { spec: result, entry };
}

function nodeOperation(fn) { try { fn(); } catch (error) { report('Node library', [error.message]); } }
function draftControl(label, control) { control.setAttribute('aria-label', label); return el('label', { class: 'field' }, el('span', { text: label }), control); }
function renderNodeLibrary(box) {
  nodeDraft.selected = nodeDraft.selected.filter(id => nodes().some(n => n.id === id));
  box.append(el('h2', { text: 'Node Library' }), hint('Build a mechanic from one or more steps, save it, and reuse it in another Advanced raid. Saved copies include teams, roles, statuses, actions and meters.'));
  box.append(el('div', { class: 'row' }, btn('Import Node File', () => $('node-file-input').click(), 'small'),
    btn('Download AI Prompt', () => downloadText('Fable-Node-Authoring-Prompt.txt', promptText, 'text/plain'), 'small')));
  const creator = el('details', { open: true }, el('summary', { text: 'Create from this raid' }));
  creator.append(draftControl('Pack name', el('input', { value: nodeDraft.name, maxLength: 100, onchange: e => nodeDraft.name = e.target.value })),
    draftControl('Pack description', el('textarea', { value: nodeDraft.description, maxLength: 1000, onchange: e => nodeDraft.description = e.target.value })),
    hint('Select up to 30 connected steps. Outgoing links become Next / Failure ports.'));
  const choices = el('div', { class: 'checklist' });
  for (const n of nodes()) choices.append(el('label', {}, el('input', { type: 'checkbox', checked: nodeDraft.selected.includes(n.id), onchange: e => {
    nodeDraft.selected = nodeDraft.selected.filter(id => id !== n.id); if (e.target.checked) nodeDraft.selected.push(n.id);
  } }), ' ' + n.title));
  creator.append(choices);
  const entry = el('select', { onchange: e => nodeDraft.entry = e.target.value });
  for (const n of nodes()) entry.append(el('option', { value: n.id, text: n.title, selected: n.id === nodeDraft.entry }));
  creator.append(draftControl('Pack entry', entry), btn('Save Selected Steps', () => nodeOperation(() => {
    saveLocalNode(extractNodePack()); renderInspector();
    $('save-state').textContent = 'Node saved in this browser • Download Node, then import in Discord to keep it in your GM library';
  }), 'secondary'));
  box.append(creator, hint('Browser nodes stay on this device. Download a .node.json and attach it to raidmode node import <node_id> to save in Discord. Use raidmode node publish <node_id> to share.'));
  const after = el('select', { onchange: e => nodeDraft.after = e.target.value });
  after.append(el('option', { value: '', text: 'Before raid start', selected: !nodeDraft.after }));
  for (const n of nodes().filter(n => !['ending','choice'].includes(n.kind))) after.append(el('option', { value: n.id, text: 'After ' + n.title, selected: nodeDraft.after === n.id }));
  box.append(draftControl('Insert position', after));
  box.append(draftControl('Find a node', el('input', { type: 'search', value: nodeDraft.query, onchange: e => { nodeDraft.query = e.target.value; renderInspector(); } })));
  const entries = [...localNodes.map((p, i) => ({ package: p, local: i, id: 'browser_' + i, label: 'This browser' })),
    ...serverNodes.map(n => ({ ...n, label: `${n.visibility} · ${n.id} · v${n.version}${n.has_unpublished_changes ? ' · unpublished edits' : ''}` }))];
  for (const item of entries.filter(n => (n.package.name + ' ' + n.id).toLowerCase().includes(nodeDraft.query.toLowerCase()))) {
    const p = item.package, card = el('details', {}, el('summary', { text: p.name }), hint(item.label), hint(p.description || 'Reusable raid mechanic'), hint(`${p.nodes.length} steps`));
    card.append(el('div', { class: 'row' }, btn('Insert Node', () => nodeOperation(() => {
      const compiled = compileNodePack(p, nodeDraft.after);
      change(() => { raid().config.encounter = compiled.spec; selected = compiled.entry; tab = 'step'; });
    }), 'small'), btn('Download Node', () => downloadText(`${item.id}.node.json`, JSON.stringify(p, null, 2)), 'small')));
    if (item.local !== undefined) card.append(btn('Delete Browser Copy', () => nodeOperation(() => {
      const updated = localNodes.filter((_, i) => i !== item.local); localStorage.setItem(nodeStorageKey, JSON.stringify(updated)); localNodes = updated; renderInspector();
    }), 'small danger'));
    box.append(card);
  }
  if (!entries.length) box.append(hint('No saved nodes yet. Save selected steps or import a node file.'));
  box.append(hint('Community entries reflect the library when this canvas was downloaded. Download a fresh canvas for new releases. Inserted nodes are independent copies.'));
  if (serverCatalogue.omitted) box.append(hint(`${serverCatalogue.omitted} more packs are available in Discord. Use raidmode node list, then node export <node_id> and Import Node File. The canvas includes a size-limited library snapshot.`));
}

const nodeInput = el('input', { id: 'node-file-input', class: 'visually-hidden', type: 'file', accept: '.json,application/json' });
document.body.append(nodeInput);
nodeInput.onchange = async e => {
  try {
    const file = e.target.files[0]; if (!file) return;
    if (file.size > 250000) throw new Error('Node files must be smaller than 250 KB.');
    saveLocalNode(JSON.parse(await file.text())); tab = 'node_library'; renderInspector();
    $('save-state').textContent = 'Node imported into this browser • Insert a copy or download it for Discord';
  } catch (error) { report('Could not import node', [error.message]); }
  e.target.value = '';
};
