/*
 * heizkurve-card – Home Assistant Lovelace Custom Card
 * Anzeige und Bearbeitung einer Wärmepumpen-Heizkurve (x = Außentemperatur, y = Vorlauftemperatur).
 * Jeder Stützpunkt ist eine number-Entity; Punkte lassen sich vertikal ziehen.
 * Vanilla JS, Shadow DOM, keine externen Abhängigkeiten.
 */

const CARD_VERSION = '1.3.0';
const PENDING_TIMEOUT_MS = 10000;
const ERROR_VISIBLE_MS = 6000;
const UNAVAILABLE = ['unavailable', 'unknown', 'none', ''];

// ---------- Hilfsfunktionen ----------

const num = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function decimalsOf(n) {
  if (!Number.isFinite(n)) return 0;
  const s = String(n);
  if (s.includes('e-')) return parseInt(s.split('e-')[1], 10) || 0;
  const i = s.indexOf('.');
  return i < 0 ? 0 : s.length - i - 1;
}

function niceStep(range, target) {
  if (!(range > 0)) return 1;
  const raw = range / Math.max(1, target);
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / pow;
  const m = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
  return m * pow;
}

const r1 = (v) => Math.round(v * 10) / 10;

function stateValue(stateObj) {
  if (!stateObj || UNAVAILABLE.includes(String(stateObj.state).toLowerCase())) return null;
  return num(stateObj.state);
}

// ---------- Konfigurations-Validierung ----------

const ENTITY_RE = /^[a-z0-9_]+\.[a-z0-9_]+$/;

function validateConfig(config) {
  const fail = (msg) => {
    throw new Error(`heizkurve-card: ${msg}`);
  };
  if (!config || typeof config !== 'object') fail('Konfiguration fehlt.');

  if (!Array.isArray(config.points)) fail('"points" muss eine Liste mit mindestens 2 Einträgen { x, entity } sein.');
  // Im Editor frisch hinzugefügte Punkte ohne Entity werden übersprungen statt als Fehler gemeldet
  const pts = config.points.filter((p) => !(p && typeof p === 'object' && (p.entity === '' || p.entity == null)));
  if (pts.length < 2) {
    fail('"points" muss eine Liste mit mindestens 2 Einträgen { x, entity } sein.');
  }
  const seen = new Set();
  const points = pts
    .map((p, i) => {
      if (!p || typeof p !== 'object' || Array.isArray(p)) fail(`points[${i}] muss ein Objekt { x, entity } sein.`);
      const x = typeof p.x === 'number' ? p.x : typeof p.x === 'string' && p.x.trim() !== '' ? Number(p.x) : NaN;
      if (!Number.isFinite(x)) fail(`points[${i}].x muss eine Zahl sein (ist: ${JSON.stringify(p.x)}).`);
      if (typeof p.entity !== 'string' || !p.entity.startsWith('number.') || !ENTITY_RE.test(p.entity)) {
        fail(`points[${i}].entity muss eine number-Entity sein, z. B. "number.heizkurve_m20" (ist: ${JSON.stringify(p.entity)}).`);
      }
      if (seen.has(x)) fail(`x = ${x} kommt in "points" mehrfach vor.`);
      seen.add(x);
      return { x, entity: p.entity };
    })
    .sort((a, b) => a.x - b.x);

  for (const key of ['outdoor_entity', 'flow_entity']) {
    const v = config[key];
    if (v !== undefined && v !== null && (typeof v !== 'string' || !ENTITY_RE.test(v))) {
      fail(`"${key}" muss eine Entity-ID sein, z. B. "sensor.aussentemperatur" (ist: ${JSON.stringify(v)}).`);
    }
  }

  const yr = {};
  for (const key of ['y_min', 'y_max']) {
    const v = config[key];
    if (v === undefined || v === null) continue;
    if (typeof v !== 'number' || !Number.isFinite(v)) fail(`"${key}" muss eine Zahl sein (ist: ${JSON.stringify(v)}).`);
    yr[key] = v;
  }
  let step;
  if (config.step !== undefined && config.step !== null && config.step !== '') {
    step = typeof config.step === 'number' ? config.step : Number(config.step);
    if (!Number.isFinite(step) || step <= 0) fail(`"step" muss eine Zahl größer 0 sein, z. B. 1 (ist: ${JSON.stringify(config.step)}).`);
  }
  if (yr.y_min !== undefined && yr.y_max !== undefined && yr.y_min >= yr.y_max) {
    fail(`"y_min" (${yr.y_min}) muss kleiner als "y_max" (${yr.y_max}) sein.`);
  }
  if (config.title !== undefined && config.title !== null && typeof config.title !== 'string' && typeof config.title !== 'number') {
    fail('"title" muss ein Text sein.');
  }

  return {
    title: config.title != null ? String(config.title) : '',
    outdoor_entity: config.outdoor_entity || null,
    flow_entity: config.flow_entity || null,
    y_min: yr.y_min,
    y_max: yr.y_max,
    step,
    points,
  };
}

// ---------- Styles ----------

const CARD_BG = 'var(--ha-card-background, var(--card-background-color, #fff))';

const STYLE = `
  :host { display: block; }
  ha-card { display: block; overflow: hidden; padding: 12px 12px 8px; box-sizing: border-box; }
  .head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
          gap: 2px 12px; padding: 4px 4px 4px; }
  .title { font-size: 18px; font-weight: 500; color: var(--primary-text-color); line-height: 1.3; }
  .title:empty { display: none; }
  .info { font-size: 12px; color: var(--secondary-text-color); line-height: 1.4; }
  .info .op { color: var(--accent-color, #ff9800); font-weight: 600; }
  .chart { position: relative; width: 100%; min-height: 160px; }
  svg { display: block; width: 100%; height: auto; overflow: visible; font-family: inherit;
        user-select: none; -webkit-user-select: none; -webkit-tap-highlight-color: transparent; }
  svg.dragging, svg.dragging * { cursor: ns-resize !important; }
  .grid { stroke: var(--divider-color, rgba(127,127,127,.25)); stroke-width: 1; shape-rendering: crispEdges; }
  .axis { stroke: var(--secondary-text-color, #727272); stroke-width: 1; shape-rendering: crispEdges; }
  .tick { fill: var(--secondary-text-color, #727272); font-size: 11px; }
  .tick.na { opacity: .45; }
  .axt { fill: var(--secondary-text-color, #727272); font-size: 11px; font-weight: 600; }
  .curve { fill: none; stroke: var(--primary-color, #03a9f4); stroke-width: 2.5;
           stroke-linejoin: round; stroke-linecap: round; }
  .pt { cursor: ns-resize; touch-action: none; outline: none; }
  .pt .hit { fill: transparent; pointer-events: all; }
  .pt .dot { fill: var(--primary-color, #03a9f4); stroke: ${CARD_BG}; stroke-width: 2;
             transform-box: fill-box; transform-origin: center; transition: transform .12s ease; }
  .pt:hover .dot, .pt.drag .dot { transform: scale(1.35); }
  .pt .ring { fill: none; stroke: var(--primary-color, #03a9f4); stroke-width: 2; opacity: 0; }
  svg.kbd .pt:focus .ring { opacity: .55; }
  .lbl { fill: var(--primary-text-color, #212121); font-size: 12px; font-weight: 600; opacity: 0;
         pointer-events: none; paint-order: stroke; stroke: ${CARD_BG}; stroke-width: 4px; stroke-linejoin: round;
         transition: opacity .1s; }
  .pt:hover .lbl, svg.kbd .pt:focus .lbl, .pt.drag .lbl { opacity: 1; }
  .pt.na { cursor: not-allowed; }
  .pt.na .mk { fill: none; stroke: var(--secondary-text-color, #727272); stroke-width: 1.5;
               stroke-dasharray: 2 2; opacity: .7; }
  .opdot { fill: var(--accent-color, #ff9800); stroke: ${CARD_BG}; stroke-width: 2.5; }
  .optarget { fill: none; stroke: var(--accent-color, #ff9800); stroke-width: 2; }
  .opg { stroke: var(--accent-color, #ff9800); stroke-width: 1; stroke-dasharray: 3 3; opacity: .7; }
  .msg { margin: 6px 4px 2px; padding: 6px 10px; border-radius: 6px; font-size: 13px;
         color: var(--error-color, #db4437); border: 1px solid currentColor; }
  .msg[hidden] { display: none; }
  .warn { font-size: 12px; color: var(--secondary-text-color); padding: 2px 4px; }
  .warn:empty { display: none; }
`;

// ---------- Card ----------

class HeizkurveCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
    this._sig = null;
    this._pending = new Map(); // entity_id -> { value, timer }
    this._drag = null;
    this._dirty = false;
    this._width = 0;
    this._model = null;
    this._geo = null;
    this._renderCount = 0;
    this._kbd = false;
    this._lastPointer = -1e9;
    this._errTimer = null;
    this._onWindowKey = this._onWindowKey.bind(this);
    this._ro = new ResizeObserver((entries) => {
      const w = Math.floor(entries[entries.length - 1].contentRect.width);
      if (w > 0 && w !== this._width) {
        this._width = w;
        if (this._drag) this._dirty = true;
        else this._update(false);
      }
    });
  }

  // ----- Card-API -----

  static getConfigElement() {
    return document.createElement('heizkurve-card-editor');
  }

  /**
   * Sucht number-Entities nach dem Muster *heizkurve*_m20 / _0 / _p5 (auch *feinkurve*) und baut
   * daraus die Punkte. Die feine Heizkurve der Bösch-Integration hat Vorrang, weil sie – wenn
   * vorhanden – die wirksame Kurve ist. Dazu passend die gemittelte Außentemperatur.
   */
  static getStubConfig(hass) {
    const ids = Object.keys((hass && hass.states) || {});
    const groups = {};
    for (const id of ids) {
      const mm = /^(number\..*(?:heizkurve|heating_curve|feinkurve)[a-z0-9_]*?)_(m|p)?(\d+)$/.exec(id);
      if (!mm) continue;
      const x = (mm[2] === 'm' ? -1 : 1) * Number(mm[3]);
      (groups[mm[1]] = groups[mm[1]] || []).push({ x, entity: id });
    }
    const fine = (g) => (g[0].entity.includes('feinkurve') ? 1 : 0);
    const best = Object.values(groups)
      .filter((g) => g.length >= 2)
      .sort((a, b) => fine(b) - fine(a) || b.length - a.length)[0];
    const name = (x) => (x < 0 ? `m${-x}` : x > 0 ? `p${x}` : '0');
    const outdoor =
      ids.find((id) => /^sensor\..*aussentemperatur_gemittelt$/.test(id)) ||
      ids.find((id) => /^sensor\..*(?:aussentemperatur|outdoor_temperature)$/.test(id));
    const cfg = {
      title: best && fine(best) ? 'Feine Heizkurve' : 'Heizkurve',
      points: best
        ? best.sort((a, b) => a.x - b.x)
        : [-20, -10, 0, 10, 20].map((x) => ({ x, entity: `number.heizkurve_${name(x)}` })),
    };
    if (outdoor) cfg.outdoor_entity = outdoor;
    return cfg;
  }

  setConfig(config) {
    const cfg = validateConfig(config); // wirft bei Fehlern -> HA zeigt Fehlerkarte
    if (this._drag) this._endDrag(false, true);
    this._config = cfg;
    this._sig = null;
    if (!this._chart) this._buildShell();
    this._titleEl.textContent = cfg.title;
    if (this._hass) this._update(true);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._reconcilePending();
    if (this._drag) {
      // Während des Ziehens keine Updates von außen übernehmen.
      this._dirty = true;
      return;
    }
    this._update(false);
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 5;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: 5, min_rows: 4 };
  }

  connectedCallback() {
    if (this._chart) this._ro.observe(this._chart);
  }

  disconnectedCallback() {
    this._ro.disconnect();
    if (this._drag) this._endDrag(false, true);
  }

  // ----- Aufbau -----

  _buildShell() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head"><div class="title"></div><div class="info"></div></div>
        <div class="chart"></div>
        <div class="warn"></div>
        <div class="msg" role="alert" hidden></div>
      </ha-card>`;
    const $ = (s) => this.shadowRoot.querySelector(s);
    this._titleEl = $('.title');
    this._infoEl = $('.info');
    this._chart = $('.chart');
    this._warnEl = $('.warn');
    this._msgEl = $('.msg');

    const c = this._chart;
    c.addEventListener('pointerdown', (e) => this._onPointerDown(e));
    c.addEventListener('pointermove', (e) => this._onPointerMove(e));
    c.addEventListener('pointerup', (e) => this._onPointerUp(e));
    c.addEventListener('pointercancel', (e) => this._onPointerCancel(e));
    c.addEventListener('lostpointercapture', (e) => this._onPointerCancel(e));
    c.addEventListener('keydown', (e) => this._onKeyDown(e));
    // Fokus ohne vorherigen Pointer-Kontakt = Tastatur → Fokusring/Label zeigen
    c.addEventListener('focusin', () => {
      if (!this._drag && !this._restoring && performance.now() - this._lastPointer > 300) this._setKbd(true);
    });
    if (this.isConnected) this._ro.observe(c);
  }

  // ----- State-Handling -----

  _signature() {
    const h = this._hass;
    const c = this._config;
    const ent = (id) => {
      const s = id && h.states[id];
      if (!s) return '∅';
      const a = s.attributes || {};
      return `${s.state}|${a.min}|${a.max}|${a.step}|${a.unit_of_measurement}|${a.friendly_name}`;
    };
    const parts = c.points.map((p) => ent(p.entity));
    parts.push(ent(c.outdoor_entity), ent(c.flow_entity));
    parts.push([...this._pending].map(([k, v]) => `${k}=${v.value}`).join(','));
    parts.push(this._width, this._locale());
    return parts.join('§');
  }

  _update(force) {
    if (!this._config || !this._hass || !this._chart) return;
    const sig = this._signature();
    if (!force && sig === this._sig) return;
    this._sig = sig;
    this._render();
  }

  _reconcilePending() {
    if (!this._hass) return;
    for (const [entity, p] of this._pending) {
      const v = stateValue(this._hass.states[entity]);
      if (v !== null && Math.abs(v - p.value) < 1e-9) {
        clearTimeout(p.timer);
        this._pending.delete(entity);
      }
    }
  }

  _locale() {
    const h = this._hass;
    return (h && ((h.locale && h.locale.language) || h.language)) || undefined;
  }

  _fmt(v, decimals) {
    try {
      return new Intl.NumberFormat(this._locale(), {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(v);
    } catch (_) {
      return v.toFixed(decimals);
    }
  }

  _buildModel() {
    const h = this._hass;
    const points = this._config.points.map((p, i) => {
      const s = h.states[p.entity];
      const a = (s && s.attributes) || {};
      const pend = this._pending.get(p.entity);
      const real = stateValue(s);
      // Schrittweite: Karten-Option "step" vor Entity-Attribut, Fallback 1
      const step = this._config.step || (num(a.step) > 0 ? num(a.step) : 1);
      return {
        i,
        x: p.x,
        entity: p.entity,
        name: a.friendly_name || p.entity,
        missing: !s,
        real,
        value: pend && real !== null ? pend.value : real,
        min: num(a.min),
        max: num(a.max),
        step,
        decimals: Math.max(decimalsOf(step), real !== null ? Math.min(decimalsOf(real), 2) : 0),
        unit: a.unit_of_measurement || '°C',
      };
    });
    const c = this._config;
    const outdoor = c.outdoor_entity ? stateValue(h.states[c.outdoor_entity]) : null;
    const flow = c.flow_entity ? stateValue(h.states[c.flow_entity]) : null;
    return { points, outdoor, flow };
  }

  _computeGeo(model) {
    const W = Math.max(240, this._width || this._chart.clientWidth || 400);
    const H = Math.round(clamp(W * 0.56, 210, 320));
    const m = { l: 42, r: 16, t: 26, b: 42 };
    const pw = W - m.l - m.r;
    const ph = H - m.t - m.b;
    const pts = model.points;

    let xMin = pts[0].x;
    let xMax = pts[pts.length - 1].x;
    if (xMax === xMin) {
      xMin -= 5;
      xMax += 5;
    }

    const target = Math.max(3, Math.floor(ph / 30));
    const vals = pts.map((p) => p.value).filter((v) => v !== null);
    if (model.flow !== null) vals.push(model.flow);
    const cfg = this._config;
    let lo = vals.length ? Math.min(...vals) : 20;
    let hi = vals.length ? Math.max(...vals) : 45;
    if (cfg.y_min !== undefined) lo = cfg.y_min;
    if (cfg.y_max !== undefined) hi = cfg.y_max;
    if (cfg.y_min === undefined || cfg.y_max === undefined) {
      const pad = Math.max(2, (hi - lo) * 0.12);
      if (cfg.y_min === undefined) lo = (cfg.y_max !== undefined ? Math.min(lo, hi - 10) : lo) - pad;
      if (cfg.y_max === undefined) hi = (cfg.y_min !== undefined ? Math.max(hi, lo + 10) : hi) + pad;
    }
    let step = niceStep(hi - lo, target);
    if (cfg.y_min === undefined) lo = Math.floor(lo / step) * step;
    if (cfg.y_max === undefined) hi = Math.ceil(hi / step) * step;
    step = niceStep(hi - lo, target);

    const sx = (x) => m.l + ((x - xMin) / (xMax - xMin)) * pw;
    const sy = (v) => m.t + ((hi - v) / (hi - lo)) * ph;
    return { W, H, m, pw, ph, xMin, xMax, yMin: lo, yMax: hi, yStep: step, sx, sy };
  }

  // ----- Rendering -----

  _render() {
    this._renderCount++;
    const model = this._buildModel();
    const g = this._computeGeo(model);
    this._model = model;
    this._geo = g;
    const { W, H, m, pw, ph, sx, sy } = g;
    const pts = model.points;
    const unit = (pts.find((p) => !p.missing) || { unit: '°C' }).unit;

    // Fokus merken, damit er nach dem Neuaufbau erhalten bleibt
    const active = this.shadowRoot.activeElement;
    const focusIdx = active && active.dataset ? active.dataset.i : undefined;

    let s = `<svg class="${this._kbd ? 'kbd' : ''}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="group" aria-label="${esc(
      this._config.title || 'Heizkurve'
    )}">`;

    // y-Gitter + Beschriftung
    const yDec = decimalsOf(g.yStep);
    const yStart = Math.ceil((g.yMin - 1e-9) / g.yStep) * g.yStep;
    for (let v = yStart; v <= g.yMax + 1e-9; v += g.yStep) {
      const y = r1(sy(v));
      s += `<line class="grid" x1="${m.l}" x2="${m.l + pw}" y1="${y}" y2="${y}"/>`;
      s += `<text class="tick" x="${m.l - 6}" y="${y}" text-anchor="end" dominant-baseline="middle">${this._fmt(v, yDec)}</text>`;
    }

    // x-Gitter an den Stützpunkten; Beschriftung ausdünnen, wenn zu eng
    let minGap = Infinity;
    for (let i = 1; i < pts.length; i++) minGap = Math.min(minGap, sx(pts[i].x) - sx(pts[i - 1].x));
    const every = Math.max(1, Math.ceil(26 / minGap));
    pts.forEach((p, i) => {
      const x = r1(sx(p.x));
      s += `<line class="grid" x1="${x}" x2="${x}" y1="${m.t}" y2="${m.t + ph}"/>`;
      if (i % every === 0 || i === pts.length - 1) {
        if (i === pts.length - 1 && i % every !== 0 && i - Math.floor(i / every) * every < every / 2) return;
        s += `<text class="tick${p.value === null ? ' na' : ''}" x="${x}" y="${m.t + ph + 16}" text-anchor="middle">${this._fmt(
          p.x,
          decimalsOf(p.x)
        )}</text>`;
      }
    });

    // Achsen + Titel
    s += `<line class="axis" x1="${m.l}" x2="${m.l + pw}" y1="${m.t + ph}" y2="${m.t + ph}"/>`;
    s += `<line class="axis" x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${m.t + ph}"/>`;
    s += `<text class="axt" x="${m.l - 6}" y="${m.t - 12}" text-anchor="start">Vorlauf ${esc(unit)}</text>`;
    s += `<text class="axt" x="${m.l + pw}" y="${H - 4}" text-anchor="end">Außen °C</text>`;

    // Betriebspunkt (Positionen setzt _placeOp, damit er beim Ziehen mitläuft)
    if (model.outdoor !== null) {
      s += '<g class="op"><line class="opg opv"/><line class="opg oph"/>';
      s += '<circle class="optarget" r="6"><title></title></circle><circle class="opdot" r="8"><title></title></circle></g>';
    }

    // Kurve
    s += `<path class="curve" d="${this._pathD()}"/>`;

    // Stützpunkte
    pts.forEach((p) => {
      const x = r1(sx(p.x));
      if (p.value === null) {
        const why = p.missing ? 'Entity nicht gefunden' : 'nicht verfügbar';
        s += `<g class="pt na" data-i="${p.i}"><circle class="mk" cx="${x}" cy="${m.t + ph}" r="5"/>`;
        s += `<circle class="hit" cx="${x}" cy="${m.t + ph}" r="12"/><title>${esc(p.name)}: ${why}</title></g>`;
        return;
      }
      s += `<g class="pt" data-i="${p.i}" tabindex="0" role="slider" aria-orientation="vertical"
              aria-label="${esc(p.name)} (außen ${p.x} °C)"
              aria-valuemin="${p.min ?? ''}" aria-valuemax="${p.max ?? ''}">
              <circle class="hit" r="22"/><circle class="ring" r="11"/><circle class="dot" r="6"/>
              <text class="lbl" text-anchor="middle"></text></g>`;
    });
    s += '</svg>';

    this._chart.innerHTML = s;
    this._svg = this._chart.firstElementChild;
    pts.forEach((p) => p.value !== null && this._placePoint(p.i));
    this._unit = unit;
    this._placeOp();

    // Kopfzeile
    this._renderInfo(model, unit);
    const missing = pts.filter((p) => p.missing).map((p) => p.entity);
    const c = this._config;
    for (const id of [c.outdoor_entity, c.flow_entity]) if (id && !this._hass.states[id]) missing.push(id);
    this._warnEl.textContent = missing.length ? `Nicht gefunden: ${missing.join(', ')}` : '';

    if (focusIdx !== undefined) {
      const el = this._svg.querySelector(`.pt[data-i="${focusIdx}"]:not(.na)`);
      if (el) {
        this._restoring = true;
        el.focus({ preventScroll: true });
        this._restoring = false;
      }
    }
  }

  /**
   * Betriebspunkt: x = Außentemperatur. y = Vorlauf-Sensor, falls vorhanden (dann zusätzlich
   * ein Ring für den Kurven-Sollwert), sonst der Kurvenwert bei dieser Außentemperatur.
   */
  _placeOp() {
    const g = this._svg && this._svg.querySelector('.op');
    if (!g) return;
    const model = this._model;
    const { sx, sy, m, pw, ph, xMin, xMax } = this._geo;
    const target = this._curveAt(model.outdoor);
    const hasFlow = model.flow !== null;
    const yv = hasFlow ? model.flow : target;
    if (yv === null) {
      g.style.display = 'none';
      return;
    }
    g.style.display = '';
    const ox = r1(clamp(sx(clamp(model.outdoor, xMin, xMax)), m.l, m.l + pw));
    const oy = r1(clamp(sy(yv), m.t, m.t + ph));
    const set = (sel, attrs) => {
      const el = g.querySelector(sel);
      for (const k in attrs) el.setAttribute(k, attrs[k]);
      return el;
    };
    set('.opv', { x1: ox, x2: ox, y1: oy, y2: m.t + ph });
    set('.oph', { x1: m.l, x2: ox, y1: oy, y2: oy });
    set('.opdot', { cx: ox, cy: oy });
    const u = this._unit;
    const out = `außen ${this._fmt(model.outdoor, 1)} °C`;
    g.querySelector('.opdot title').textContent = hasFlow
      ? `Betriebspunkt: ${out}, Vorlauf ${this._fmt(model.flow, 1)} ${u}`
      : `Betriebspunkt lt. Kurve: ${out}, Vorlauf-Soll ${this._fmt(target, 1)} ${u}`;
    const ring = g.querySelector('.optarget');
    if (hasFlow && target !== null) {
      ring.style.display = '';
      set('.optarget', { cx: ox, cy: r1(clamp(sy(target), m.t, m.t + ph)) });
      ring.querySelector('title').textContent = `Soll lt. Kurve: ${this._fmt(target, 1)} ${u}`;
    } else {
      ring.style.display = 'none';
    }
  }

  _renderInfo(model, unit) {
    const parts = [];
    if (model.outdoor !== null) parts.push(`Außen ${this._fmt(model.outdoor, 1)} °C`);
    if (model.flow !== null) parts.push(`Vorlauf ${this._fmt(model.flow, 1)} ${unit}`);
    const target = model.outdoor !== null ? this._curveAt(model.outdoor) : null;
    if (target !== null) parts.push(`Kurve ${this._fmt(target, 1)} ${unit}`);
    const op = model.outdoor !== null && (model.flow !== null || target !== null);
    this._infoEl.innerHTML = parts.length
      ? (op ? '<span class="op">●</span> ' : '') + parts.map(esc).join(' · ')
      : '';
  }

  /** Lineare Interpolation der Kurve an Außentemperatur x (außerhalb: Randwert). */
  _curveAt(x) {
    const av = this._model.points.filter((p) => p.value !== null);
    if (!av.length) return null;
    if (x <= av[0].x) return av[0].value;
    if (x >= av[av.length - 1].x) return av[av.length - 1].value;
    for (let i = 1; i < av.length; i++) {
      const a = av[i - 1];
      const b = av[i];
      if (x <= b.x) return a.value + ((x - a.x) / (b.x - a.x)) * (b.value - a.value);
    }
    return null;
  }

  _pathD() {
    const { sx, sy, m, ph } = this._geo;
    let d = '';
    let pen = false;
    for (const p of this._model.points) {
      if (p.value === null) {
        pen = false; // Linie unterbrechen
        continue;
      }
      d += `${pen ? 'L' : 'M'}${r1(sx(p.x))},${r1(clamp(sy(p.value), m.t, m.t + ph))}`;
      pen = true;
    }
    return d;
  }

  /** Setzt Position, Label und ARIA eines Punktes anhand des Modellwerts (ohne Neuaufbau). */
  _placePoint(i) {
    const p = this._model.points[i];
    const el = this._svg && this._svg.querySelector(`.pt[data-i="${i}"]`);
    if (!el || p.value === null) return;
    const { sx, sy, m, ph, W } = this._geo;
    const cx = r1(sx(p.x));
    const cy = r1(clamp(sy(p.value), m.t, m.t + ph));
    for (const c of el.querySelectorAll('circle')) {
      c.setAttribute('cx', cx);
      c.setAttribute('cy', cy);
    }
    const txt = `${this._fmt(p.value, p.decimals)} ${p.unit}`;
    const lbl = el.querySelector('.lbl');
    lbl.textContent = txt;
    const ly = cy - 16 < 12 ? cy + 26 : cy - 16;
    let anchor = 'middle';
    if (cx > W - 34) anchor = 'end';
    else if (cx < 34) anchor = 'start';
    lbl.setAttribute('x', anchor === 'end' ? cx + 8 : anchor === 'start' ? cx - 8 : cx);
    lbl.setAttribute('y', ly);
    lbl.setAttribute('text-anchor', anchor);
    el.setAttribute('aria-valuenow', p.value);
    el.setAttribute('aria-valuetext', txt);
  }

  // ----- Werte -----

  /** Auf step runden und auf min/max begrenzen. */
  _constrain(p, v) {
    // Mit eigener Schrittweite auf Vielfache davon runden (z. B. ganze Grad), sonst ab Entity-min
    const base = this._config.step || p.min === null ? 0 : p.min;
    const dec = Math.max(decimalsOf(p.step), decimalsOf(base));
    let out = base + Math.round((v - base) / p.step) * p.step;
    out = Number(out.toFixed(dec));
    if (p.min !== null) out = Math.max(p.min, out);
    if (p.max !== null) out = Math.min(p.max, out);
    return out;
  }

  _write(entity, value) {
    const prev = this._pending.get(entity);
    if (prev) clearTimeout(prev.timer);
    const entry = { value, timer: null };
    this._pending.set(entity, entry);
    this._update(true); // optimistisch anzeigen

    let call;
    try {
      call = this._hass.callService('number', 'set_value', { entity_id: entity, value });
    } catch (err) {
      call = Promise.reject(err);
    }
    Promise.resolve(call).then(
      () => {
        if (this._pending.get(entity) !== entry) return; // schon bestätigt oder überholt
        // Falls der neue State nie ankommt, nach Timeout auf echten State zurückfallen
        entry.timer = setTimeout(() => {
          if (this._pending.get(entity) !== entry) return;
          this._pending.delete(entity);
          this._refreshSoon();
        }, PENDING_TIMEOUT_MS);
      },
      (err) => {
        const name = (this._hass.states[entity] && this._hass.states[entity].attributes.friendly_name) || entity;
        this._showError(`Konnte „${name}“ nicht setzen: ${(err && (err.message || err.error)) || err || 'unbekannter Fehler'}`);
        if (this._pending.get(entity) !== entry) return; // neuerer Wert ausstehend
        this._pending.delete(entity);
        this._refreshSoon();
      }
    );
  }

  _refreshSoon() {
    if (this._drag) this._dirty = true;
    else this._update(true);
  }

  _showError(msg) {
    console.warn('heizkurve-card:', msg);
    this._msgEl.textContent = msg;
    this._msgEl.hidden = false;
    clearTimeout(this._errTimer);
    this._errTimer = setTimeout(() => (this._msgEl.hidden = true), ERROR_VISIBLE_MS);
  }

  // ----- Interaktion -----

  _svgY(clientY) {
    const ctm = this._svg && this._svg.getScreenCTM();
    if (!ctm) return clientY;
    return new DOMPoint(0, clientY).matrixTransform(ctm.inverse()).y;
  }

  _onPointerDown(e) {
    this._lastPointer = performance.now();
    if (this._drag) return;
    const pt = e.target.closest && e.target.closest('.pt');
    if (!pt || pt.classList.contains('na')) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    const i = Number(pt.dataset.i);
    const p = this._model.points[i];
    if (p.value === null) return;
    e.preventDefault();
    this._setKbd(false);
    pt.focus({ preventScroll: true });
    try {
      pt.setPointerCapture(e.pointerId);
    } catch (_) {
      /* ignore */
    }
    // Clientkoordinate des Ausgangspunkts merken (relativ ziehen, kein Sprung beim Greifen)
    this._drag = { i, pointerId: e.pointerId, el: pt, start: p.value, value: p.value, y0: this._svgY(e.clientY) };
    pt.classList.add('drag');
    this._svg.classList.add('dragging');
    window.addEventListener('keydown', this._onWindowKey, true);
  }

  _onPointerMove(e) {
    const d = this._drag;
    if (!d || e.pointerId !== d.pointerId) return;
    e.preventDefault();
    const g = this._geo;
    const p = this._model.points[d.i];
    const dy = this._svgY(e.clientY) - d.y0;
    let v = d.start - (dy * (g.yMax - g.yMin)) / g.ph;
    v = clamp(v, g.yMin, g.yMax);
    v = this._constrain(p, v);
    if (v === d.value) return;
    d.value = v;
    p.value = v;
    this._placePoint(d.i);
    this._svg.querySelector('.curve').setAttribute('d', this._pathD());
    this._placeOp();
    this._renderInfo(this._model, this._unit);
  }

  _onPointerUp(e) {
    const d = this._drag;
    if (!d || e.pointerId !== d.pointerId) return;
    this._endDrag(true);
  }

  _onPointerCancel(e) {
    const d = this._drag;
    if (!d || e.pointerId !== d.pointerId) return;
    this._endDrag(false);
  }

  _onWindowKey(e) {
    if (e.key === 'Escape' && this._drag) {
      e.preventDefault();
      e.stopPropagation();
      this._endDrag(false);
    }
  }

  _endDrag(commit, silent = false) {
    const d = this._drag;
    if (!d) return;
    this._drag = null;
    window.removeEventListener('keydown', this._onWindowKey, true);
    try {
      if (d.el.hasPointerCapture && d.el.hasPointerCapture(d.pointerId)) d.el.releasePointerCapture(d.pointerId);
    } catch (_) {
      /* ignore */
    }
    d.el.classList.remove('drag');
    if (this._svg) this._svg.classList.remove('dragging');
    this._dirty = false;
    if (silent) return;
    if (commit && d.value !== d.start) {
      this._write(this._config.points[d.i].entity, d.value);
    } else {
      this._update(true); // alten Wert / externe Updates übernehmen
    }
  }

  _setKbd(on) {
    this._kbd = on;
    if (this._svg) this._svg.classList.toggle('kbd', on);
  }

  _onKeyDown(e) {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    const pt = e.target.closest && e.target.closest('.pt');
    if (!pt || pt.classList.contains('na')) return;
    e.preventDefault();
    this._setKbd(true);
    if (this._drag) return;
    const p = this._model.points[Number(pt.dataset.i)];
    if (p.value === null) return;
    // Zum nächsten Rasterwert in Pfeilrichtung (35,5 → 36 statt 37 bei step 1)
    const base = this._config.step || p.min === null ? 0 : p.min;
    const k = (p.value - base) / p.step;
    const n = e.key === 'ArrowUp' ? Math.floor(k + 1e-9) + 1 : Math.ceil(k - 1e-9) - 1;
    const v = this._constrain(p, base + n * p.step);
    if (v !== p.value) this._write(p.entity, v);
  }
}


// ---------- Visueller Editor ----------

const MDI_DELETE = 'M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z';

const EDITOR_LABELS = {
  title: 'Titel',
  outdoor_entity: 'Außentemperatur-Sensor (Betriebspunkt x)',
  flow_entity: 'Vorlauf-Sensor (Betriebspunkt y, optional)',
  y_min: 'y min (leer = automatisch)',
  y_max: 'y max (leer = automatisch)',
  step: 'Schrittweite °C (leer = von Entity)',
  x: 'Außen °C',
  entity: 'number-Entity',
};

const MAIN_SCHEMA = [
  { name: 'title', selector: { text: {} } },
  { name: 'outdoor_entity', selector: { entity: { domain: 'sensor' } } },
  { name: 'flow_entity', selector: { entity: { domain: 'sensor' } } },
  {
    type: 'grid',
    name: '',
    schema: [
      { name: 'y_min', selector: { number: { mode: 'box', step: 1 } } },
      { name: 'y_max', selector: { number: { mode: 'box', step: 1 } } },
      { name: 'step', selector: { number: { mode: 'box', min: 0.1, step: 0.1 } } },
    ],
  },
];
const X_SCHEMA = [{ name: 'x', selector: { number: { mode: 'box', step: 1 } } }];
const ENTITY_SCHEMA = [{ name: 'entity', selector: { entity: { domain: 'number' } } }];

const EDITOR_STYLE = `
  :host { display: block; }
  h3 { font-size: 15px; font-weight: 500; margin: 20px 0 4px; color: var(--primary-text-color); }
  .hint { font-size: 12px; color: var(--secondary-text-color); margin: 0 0 8px; }
  .row, .cols { display: grid; grid-template-columns: 96px minmax(0, 1fr) 48px; column-gap: 8px; }
  /* An der Oberkante ausrichten: Beide Felder sind 56 px hoch, das Zahlenfeld (ha-input)
     hat aber 8 px Innenabstand darunter */
  .row { align-items: start; }
  .row { margin-bottom: 8px; }
  .cols { font-size: 12px; color: var(--secondary-text-color); margin: 4px 0 4px; padding-left: 2px; }
  .row ha-form { display: block; min-width: 0; }
  .row ha-icon-button { justify-self: center; margin-top: 4px; color: var(--secondary-text-color); }
  .add { font: inherit; font-size: 14px; font-weight: 500; color: var(--primary-color); background: none;
         border: 1px solid var(--divider-color); border-radius: 18px; padding: 6px 16px; cursor: pointer; }
  .add:hover { background: rgba(127,127,127,.08); }
`;

/** Stellt sicher, dass HA-interne Formular-Elemente (ha-form, Selektoren) geladen sind. */
async function ensureHaForm() {
  if (customElements.get('ha-form') && customElements.get('ha-entity-picker')) return;
  try {
    const helpers = window.loadCardHelpers && (await window.loadCardHelpers());
    if (helpers) {
      const c = await helpers.createCardElement({ type: 'entities', entities: [] });
      if (c && c.constructor.getConfigElement) await c.constructor.getConfigElement();
    }
  } catch (_) {
    /* HA lädt ha-form sonst selbst */
  }
}

class HeizkurveCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
    this._forms = [];
    this._ready = false;
  }

  set hass(hass) {
    this._hass = hass;
    for (const f of this._forms) f.hass = hass;
  }

  setConfig(config) {
    this._config = { ...config, points: Array.isArray(config.points) ? config.points.map((p) => ({ ...p })) : [] };
    if (!this._ready) {
      this._ready = true;
      ensureHaForm().then(() => this._build());
      return;
    }
    // Nur neu aufbauen, wenn sich die Anzahl der Punkte geändert hat (sonst Fokus beim Tippen behalten)
    if (this._rows !== this._config.points.length) this._build();
    else this._sync();
  }

  _form(schema, data, onChange, labels = true) {
    const f = document.createElement('ha-form');
    f.hass = this._hass;
    f.schema = schema;
    f.data = data;
    // In den Punkt-Zeilen keine Labels: die Spaltenköpfe stehen darüber, so fluchten die Felder
    f.computeLabel = labels ? (s) => EDITOR_LABELS[s.name] || s.name : () => '';
    f.addEventListener('value-changed', (e) => {
      e.stopPropagation();
      onChange(e.detail.value);
    });
    this._forms.push(f);
    return f;
  }

  _build() {
    if (!this._config) return;
    const root = this.shadowRoot;
    root.innerHTML = `<style>${EDITOR_STYLE}</style><div class="main"></div>
      <h3>Stützpunkte</h3>
      <p class="hint">Je Punkt Außentemperatur und zugehörige number-Entity. Reihenfolge egal, die Karte sortiert nach x.</p>
      <div class="cols"><span>Außen °C</span><span>number-Entity</span><span></span></div>
      <div class="points"></div>
      <button class="add" type="button">+ Punkt hinzufügen</button>`;
    this._forms = [];

    this._mainForm = this._form(MAIN_SCHEMA, this._mainData(), (v) => {
      const cfg = { ...this._config };
      for (const k of ['title', 'outdoor_entity', 'flow_entity', 'y_min', 'y_max', 'step']) {
        if (v[k] === undefined || v[k] === null || v[k] === '') delete cfg[k];
        else cfg[k] = v[k];
      }
      this._emit(cfg);
    });
    root.querySelector('.main').appendChild(this._mainForm);

    const list = root.querySelector('.points');
    this._pointForms = this._config.points.map((p, i) => {
      const row = document.createElement('div');
      row.className = 'row';
      const fx = this._form(X_SCHEMA, { x: p.x }, (v) => this._setPoint(i, { x: v.x }), false);
      fx.className = 'x';
      const fe = this._form(ENTITY_SCHEMA, { entity: p.entity }, (v) => this._setPoint(i, { entity: v.entity }), false);
      fe.className = 'ent';
      const del = document.createElement('ha-icon-button');
      del.path = MDI_DELETE;
      del.label = 'Punkt entfernen';
      del.title = 'Punkt entfernen';
      del.addEventListener('click', () => {
        const pts = this._config.points.filter((_, j) => j !== i);
        this._emit({ ...this._config, points: pts });
      });
      row.append(fx, fe, del);
      list.appendChild(row);
      return { fx, fe };
    });
    this._rows = this._config.points.length;

    root.querySelector('.add').addEventListener('click', () => {
      const pts = this._config.points;
      const xs = pts.map((p) => Number(p.x)).filter(Number.isFinite);
      const x = xs.length ? Math.max(...xs) + 5 : 0;
      this._emit({ ...this._config, points: [...pts, { x, entity: '' }] });
    });
  }

  _mainData() {
    const c = this._config;
    return { title: c.title, outdoor_entity: c.outdoor_entity, flow_entity: c.flow_entity, y_min: c.y_min, y_max: c.y_max, step: c.step };
  }

  _sync() {
    if (!this._mainForm) return;
    this._mainForm.data = this._mainData();
    this._config.points.forEach((p, i) => {
      const r = this._pointForms[i];
      if (!r) return;
      r.fx.data = { x: p.x };
      r.fe.data = { entity: p.entity };
    });
  }

  _setPoint(i, patch) {
    const pts = this._config.points.map((p, j) => (j === i ? { ...p, ...patch } : p));
    this._emit({ ...this._config, points: pts });
  }

  _emit(config) {
    this._config = config;
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
  }
}

if (!customElements.get('heizkurve-card-editor')) customElements.define('heizkurve-card-editor', HeizkurveCardEditor);

if (!customElements.get('heizkurve-card')) {
  customElements.define('heizkurve-card', HeizkurveCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'heizkurve-card',
    name: 'Heizkurve',
    description: 'Wärmepumpen-Heizkurve anzeigen und per Drag bearbeiten (number-Entities).',
    preview: true,
  });
  console.info(`%c HEIZKURVE-CARD %c v${CARD_VERSION} `, 'background:#03a9f4;color:#fff', 'background:#555;color:#fff');
}
