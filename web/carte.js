/* Mini-carte maison, sans dépendance : tuiles OpenStreetMap, glisser, molette, repères et lignes.
   Projection Web Mercator ; les coordonnées sont toujours [lat, lon]. */
(function () {
  "use strict";
  const TUILE = 256, ZMIN = 1, ZMAX = 18, LAT_MAX = 85.0511;
  const NS = "http://www.w3.org/2000/svg";

  function versMonde(lat, lon, z) {
    lat = Math.max(-LAT_MAX, Math.min(LAT_MAX, lat));
    const n = TUILE * Math.pow(2, z), r = lat * Math.PI / 180;
    return { x: (lon + 180) / 360 * n, y: (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n };
  }
  function depuisMonde(x, y, z) {
    const n = TUILE * Math.pow(2, z);
    const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI;
    return { lat: lat, lon: x / n * 360 - 180 };
  }

  function Carte(el, options) {
    options = options || {};
    this.el = el;
    this.onClic = options.onClic || null;
    this.actif = options.actif !== false;
    this.z = options.zoom || 2;
    const c = options.centre || [20, 0];
    const m = versMonde(c[0], c[1], this.z);
    this.cx = m.x; this.cy = m.y;
    this.tuiles = {};
    this.reperes = {}; this.lignes = {};
    el.classList.add("carte");
    el.innerHTML = "";
    this.couche = document.createElement("div"); this.couche.className = "carte-tuiles";
    this.svg = document.createElementNS(NS, "svg"); this.svg.setAttribute("class", "carte-calque");
    this.attrib = document.createElement("div"); this.attrib.className = "carte-attrib";
    this.attrib.textContent = "© OpenStreetMap";
    const zoom = document.createElement("div"); zoom.className = "carte-zoom";
    zoom.innerHTML = '<button type="button" aria-label="Zoom avant">+</button><button type="button" aria-label="Zoom arrière">−</button>';
    zoom.children[0].onclick = (e) => { e.stopPropagation(); this.zoomer(1); };
    zoom.children[1].onclick = (e) => { e.stopPropagation(); this.zoomer(-1); };
    zoom.addEventListener("pointerdown", (e) => e.stopPropagation());
    el.append(this.couche, this.svg, zoom, this.attrib);
    this._evenements();
    this._ro = new ResizeObserver(() => this.dessiner());
    this._ro.observe(el);
    this.dessiner();
  }

  Carte.prototype._evenements = function () {
    const el = this.el;
    let dep = null;
    el.addEventListener("pointerdown", (e) => {
      if (e.button !== undefined && e.button > 0) return;
      dep = { x0: e.clientX, y0: e.clientY, lx: e.clientX, ly: e.clientY, bouge: false };
      try { el.setPointerCapture(e.pointerId); } catch (_) {}
    });
    el.addEventListener("pointermove", (e) => {
      if (!dep) return;
      if (!dep.bouge && Math.abs(e.clientX - dep.x0) + Math.abs(e.clientY - dep.y0) < 5) return;
      dep.bouge = true;
      this.cx -= e.clientX - dep.lx; this.cy -= e.clientY - dep.ly;
      dep.lx = e.clientX; dep.ly = e.clientY;
      this.dessiner();
    });
    el.addEventListener("pointerup", (e) => {
      const d = dep; dep = null;
      if (!d || d.bouge || !this.actif || !this.onClic) return;
      const r = el.getBoundingClientRect();
      const p = depuisMonde(this.cx - r.width / 2 + (e.clientX - r.left), this.cy - r.height / 2 + (e.clientY - r.top), this.z);
      this.onClic(p.lat, p.lon);
    });
    el.addEventListener("pointercancel", () => { dep = null; });
    el.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      this.zoomer(e.deltaY < 0 ? 1 : -1, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
  };

  Carte.prototype.zoomer = function (delta, px, py) {
    const nz = Math.max(ZMIN, Math.min(ZMAX, this.z + delta));
    if (nz === this.z) return;
    const r = this.el.getBoundingClientRect();
    if (px === undefined) { px = r.width / 2; py = r.height / 2; }
    const f = Math.pow(2, nz - this.z);
    // le point sous le curseur reste sous le curseur
    const wx = this.cx - r.width / 2 + px, wy = this.cy - r.height / 2 + py;
    this.cx = wx * f - (px - r.width / 2); this.cy = wy * f - (py - r.height / 2);
    this.z = nz;
    this.dessiner();
  };

  Carte.prototype.vue = function (lat, lon, zoom) {
    if (zoom !== undefined) this.z = Math.max(ZMIN, Math.min(ZMAX, zoom));
    const m = versMonde(lat, lon, this.z); this.cx = m.x; this.cy = m.y;
    this.dessiner();
  };

  /* Cadre une liste de points [lat, lon] dans la carte. */
  Carte.prototype.cadrer = function (points, marge) {
    const r = this.el.getBoundingClientRect();
    const w = Math.max(50, r.width - 2 * (marge || 40)), h = Math.max(50, r.height - 2 * (marge || 40));
    const lats = points.map((p) => p[0]), lons = points.map((p) => p[1]);
    const s = Math.min.apply(null, lats), n = Math.max.apply(null, lats);
    const o = Math.min.apply(null, lons), e = Math.max.apply(null, lons);
    let z = ZMAX;
    for (; z > ZMIN; z--) {
      const a = versMonde(n, o, z), b = versMonde(s, e, z);
      if (Math.abs(b.x - a.x) <= w && Math.abs(b.y - a.y) <= h) break;
    }
    this.z = z;
    const a = versMonde(n, o, z), b = versMonde(s, e, z);
    this.cx = (a.x + b.x) / 2; this.cy = (a.y + b.y) / 2;
    this.dessiner();
  };

  Carte.prototype.repere = function (id, lat, lon, options) {
    this.reperes[id] = { lat: lat, lon: lon, couleur: (options && options.couleur) || "#2a7de1",
                         etiquette: (options && options.etiquette) || "" };
    this.dessiner();
  };
  Carte.prototype.retirerRepere = function (id) { delete this.reperes[id]; this.dessiner(); };
  Carte.prototype.ligne = function (id, a, b, couleur) {
    this.lignes[id] = { a: a, b: b, couleur: couleur || "#555" }; this.dessiner();
  };
  Carte.prototype.effacer = function () { this.reperes = {}; this.lignes = {}; this.dessiner(); };
  Carte.prototype.nombreReperes = function () { return Object.keys(this.reperes).length; };
  Carte.prototype.detruire = function () { this._ro.disconnect(); this.el.innerHTML = ""; };

  Carte.prototype.dessiner = function () {
    const r = this.el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const z = this.z, n = Math.pow(2, z);
    const ox = this.cx - r.width / 2, oy = this.cy - r.height / 2;
    const x0 = Math.floor(ox / TUILE), x1 = Math.floor((ox + r.width) / TUILE);
    const y0 = Math.max(0, Math.floor(oy / TUILE)), y1 = Math.min(n - 1, Math.floor((oy + r.height) / TUILE));
    const vues = {};
    for (let x = x0; x <= x1; x++) {
      for (let y = y0; y <= y1; y++) {
        const cle = z + "/" + x + "/" + y; vues[cle] = true;
        let img = this.tuiles[cle];
        if (!img) {
          img = document.createElement("img");
          img.className = "carte-tuile"; img.alt = ""; img.draggable = false;
          img.onerror = () => { img.style.visibility = "hidden"; };
          img.src = "https://tile.openstreetmap.org/" + z + "/" + (((x % n) + n) % n) + "/" + y + ".png";
          this.couche.appendChild(img); this.tuiles[cle] = img;
        }
        img.style.transform = "translate(" + Math.round(x * TUILE - ox) + "px," + Math.round(y * TUILE - oy) + "px)";
      }
    }
    for (const cle in this.tuiles) if (!vues[cle]) { this.tuiles[cle].remove(); delete this.tuiles[cle]; }
    this._calque(ox, oy, r);
  };

  Carte.prototype._calque = function (ox, oy, r) {
    const svg = this.svg, z = this.z;
    svg.setAttribute("width", r.width); svg.setAttribute("height", r.height);
    svg.innerHTML = "";
    const pt = (lat, lon) => { const m = versMonde(lat, lon, z); return [m.x - ox, m.y - oy]; };
    for (const id in this.lignes) {
      const l = this.lignes[id], a = pt(l.a[0], l.a[1]), b = pt(l.b[0], l.b[1]);
      const e = document.createElementNS(NS, "line");
      e.setAttribute("x1", a[0]); e.setAttribute("y1", a[1]); e.setAttribute("x2", b[0]); e.setAttribute("y2", b[1]);
      e.setAttribute("stroke", l.couleur); e.setAttribute("stroke-width", 3); e.setAttribute("stroke-dasharray", "6 6");
      svg.appendChild(e);
    }
    for (const id in this.reperes) {
      const m = this.reperes[id], p = pt(m.lat, m.lon);
      const g = document.createElementNS(NS, "g");
      g.setAttribute("transform", "translate(" + p[0] + "," + p[1] + ")");
      g.setAttribute("data-repere", id);
      g.innerHTML = '<circle r="9" fill="' + m.couleur + '" stroke="#fff" stroke-width="3"></circle>';
      if (m.etiquette) {
        const t = document.createElementNS(NS, "text");
        t.setAttribute("y", -14); t.setAttribute("text-anchor", "middle"); t.setAttribute("class", "carte-etiquette");
        t.textContent = m.etiquette; g.appendChild(t);
      }
      svg.appendChild(g);
    }
  };

  window.Carte = Carte;
})();
