// "Gemelo" HTML de la presentación: imita la API de pptxgenjs que usa build_deck.js y escribe un HTML con las
// mismas posiciones, tamaños y colores (1 in = 96 px). Sirve para la QA visual (Chrome headless) y para el PDF.
// Uso: TWIN=1 NODE_PATH=.build/node_modules node build_deck.js
const fs = require("fs");
const path = require("path");

const SCHEME = ["text1", "text2", "background1", "background2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6"];
const SLOT = { text1: "dk1", text2: "dk2", background1: "lt1", background2: "lt2" };
const PX = 96, PT = 96 / 72;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

class Slide {
  constructor(pres, master) { this.pres = pres; this.master = master; this.items = []; this.notes = ""; }
  addText(t, o = {}) {
    if (o.placeholder) {
      const ph = this.master.objects.find((x) => x.placeholder && x.placeholder.options.name === o.placeholder);
      o = Object.assign({}, ph.placeholder.options, o);
    }
    this.items.push({ k: "text", t, o });
  }
  addShape(type, o) { this.items.push({ k: "shape", type, o }); }
  addImage(o) { this.items.push({ k: "img", o }); }
  addChart(type, data, o) { this.items.push({ k: "chart", data, o }); }
  addTable(rows, o) { this.items.push({ k: "table", rows, o }); }
  addNotes(n) { this.notes = n; }
}

class Twin {
  constructor() {
    this.slides = []; this.masters = {};
    this.SchemeColor = Object.fromEntries(SCHEME.map((k) => [k, "@" + k]));
    this.shapes = { ROUNDED_RECTANGLE: "rrect", RECTANGLE: "rect", OVAL: "oval", CHEVRON: "chevron" };
    this.charts = { BAR: "bar" };
  }
  set themeColors(c) { this._c = c; }
  defineSlideMaster(m) { this.masters[m.title] = m; }
  addSection() {}
  addSlide({ masterName }) { const s = new Slide(this, this.masters[masterName]); this.slides.push(s); return s; }
  col(c) {
    if (!c) return "transparent";
    if (c[0] === "@") { const k = c.slice(1); return "#" + this._c[SLOT[k] || k]; }
    return "#" + c;
  }
  rgba(c, tr) {
    const h = this.col(c).slice(1); if (h.length !== 6) return "transparent";
    const a = 1 - (tr || 0) / 100;
    return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
  }
  box(o) { return `left:${o.x * PX}px;top:${o.y * PX}px;width:${o.w * PX}px;height:${o.h * PX}px;`; }
  text(it) {
    const o = it.o;
    const m = o.margin === 0 ? 0 : (o.margin != null ? o.margin * PT : null);
    const pad = m === null ? `${0.05 * PX}px ${0.1 * PX}px` : `${m}px`;
    const jc = { top: "flex-start", middle: "center", bottom: "flex-end" }[o.valign || "top"];
    const base = `font-family:Arial;font-size:${(o.fontSize || 18) * PT}px;color:${this.col(o.color)};` +
      `font-weight:${o.bold ? 700 : 400};font-style:${o.italic ? "italic" : "normal"};text-align:${o.align || "left"};` +
      (o.charSpacing ? `letter-spacing:${o.charSpacing * PT}px;` : "");
    let runs = typeof it.t === "string" ? [{ text: it.t, options: {} }] : it.t;
    // agrupar en párrafos
    const paras = [[]];
    runs.forEach((r, i) => { paras[paras.length - 1].push(r); if (r.options && r.options.breakLine && i < runs.length - 1) paras.push([]); });
    const sa = (o.paraSpaceAfter || 0) * PT;
    const html = paras.map((p) => {
      const bullet = p.some((r) => r.options && r.options.bullet);
      const inner = p.map((r) => {
        const ro = r.options || {};
        const st = (ro.color ? `color:${this.col(ro.color)};` : "") + (ro.bold ? "font-weight:700;" : "");
        return `<span style="${st}">${esc(r.text)}</span>`;
      }).join("");
      return bullet ? `<p class="b" style="margin:0 0 ${sa}px 0">${inner}</p>` : `<p style="margin:0 0 ${sa}px 0">${inner}</p>`;
    }).join("");
    return `<div class="tx" data-name="${esc(o.objectName || "texto")}" style="${this.box(o)}padding:${pad};${base}justify-content:${jc}"><div class="in">${html}</div></div>`;
  }
  shape(it) {
    const o = it.o;
    const fill = o.fill ? this.rgba(o.fill.color, o.fill.transparency) : "transparent";
    const lw = o.line && o.line.width ? o.line.width * PT : 0;
    const border = lw ? `${lw}px ${o.line.dashType === "dash" ? "dashed" : "solid"} ${this.col(o.line.color)}` : "none";
    let extra = "";
    if (it.type === "rrect") extra = `border-radius:${(o.rectRadius || 0.1) * PX}px;`;
    if (it.type === "oval") extra = "border-radius:50%;";
    if (it.type === "chevron") return `<div class="sh" style="${this.box(o)}background:${fill};clip-path:polygon(0 0,60% 0,100% 50%,60% 100%,0 100%,40% 50%)"></div>`;
    return `<div class="sh" style="${this.box(o)}background:${fill};border:${border};box-sizing:border-box;${extra}"></div>`;
  }
  img(it) {
    const o = it.o;
    return `<img class="im" src="${path.relative(this.outDir, o.path)}" style="${this.box(o)}object-fit:fill">`;
  }
  chart(it) {
    const o = it.o, d = it.data[0];
    const max = o.valAxisMaxVal || Math.max(...d.values) * 1.15;
    const n = d.labels.length, rowH = (o.h * PX) / n;
    const fs = (o.catAxisLabelFontSize || 12) * PT;
    const rows = d.labels.map((l, i) => {
      const pct = (d.values[i] / max) * 100;
      const v = o.dataLabelFormatCode === "0" ? Math.round(d.values[i]) : d.values[i].toFixed(1);
      return `<div class="cr" style="height:${rowH}px"><div class="cl" style="font-size:${fs}px">${esc(l)}</div>` +
        `<div class="cb"><div class="bar" style="width:${pct}%;height:${rowH * (1 / (1 + (o.barGapWidthPct || 150) / 100))}px;background:#${o.chartColors[i % o.chartColors.length]}"></div>` +
        `<span style="font-size:${(o.dataLabelFontSize || 12) * PT}px;font-weight:700;color:#${o.dataLabelColor}">${v}</span></div></div>`;
    }).join("");
    return `<div class="ch" style="${this.box(o)}">${rows}</div>`;
  }
  table(it) {
    const o = it.o;
    const cols = o.colW.map((w) => `<col style="width:${w * PX}px">`).join("");
    const rows = it.rows.map((r) => `<tr style="height:${o.rowH * PX}px">` + r.map((c) => {
      const co = c.options || {};
      const bg = co.fill ? this.col(co.fill.color) : (o.fill ? this.col(o.fill.color) : "transparent");
      return `<td style="background:${bg};color:${this.col(co.color)};font-weight:${co.bold ? 700 : 400};text-align:${co.align || o.align || "left"};border:${o.border.pt * PT}px solid #${o.border.color}">${esc(c.text)}</td>`;
    }).join("") + "</tr>").join("");
    return `<table class="tb" style="left:${o.x * PX}px;top:${o.y * PX}px;width:${o.w * PX}px;font-size:${o.fontSize * PT}px">${cols}${rows}</table>`;
  }
  async writeFile({ fileName }) {
    const out = fileName.replace(/\.pptx$/, "_gemelo.html");
    this.outDir = path.dirname(out);
    const pages = this.slides.map((s, i) => {
      const m = s.master;
      let body = "";
      (m.objects || []).forEach((ob) => { if (ob.text) body += this.text({ t: ob.text.text, o: ob.text.options }); });
      if (m.slideNumber) body += this.text({ t: String(i + 1), o: Object.assign({ margin: 0 }, m.slideNumber) });
      s.items.forEach((it) => { body += this[it.k](it); });
      return `<section class="slide" id="s${i + 1}" style="background:${this.col(m.background.color)}">${body}</section>`;
    }).join("\n");
    const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Presentación (gemelo HTML)</title><style>
@page{size:13.333in 7.5in;margin:0}
html,body{margin:0;padding:0;background:#000}
.slide{position:relative;width:1280px;height:720px;overflow:hidden;page-break-after:always;break-after:page}
.tx,.sh,.im,.ch,.tb{position:absolute}
.tx{display:flex;flex-direction:column;box-sizing:border-box;line-height:1.2;overflow:visible}
.tx .in{width:100%}
p.b{padding-left:1.15em;text-indent:-1.15em}p.b::before{content:"•";display:inline-block;width:1.15em;text-indent:0}
.ch{display:flex;flex-direction:column;font-family:Arial;color:#F2F4F8}
.cr{display:flex;align-items:center}.cl{width:42%;text-align:right;padding-right:10px;box-sizing:border-box;white-space:nowrap}
.cb{flex:1;display:flex;align-items:center;gap:6px;padding-right:46px}.bar{min-width:2px}
.tb{border-collapse:collapse;font-family:Arial;table-layout:fixed}.tb td{padding:0 6px;vertical-align:middle}
.ovf{outline:3px solid #ff00ff !important}
</style></head><body>
${pages}
<script>
const bad=[];document.querySelectorAll('.tx').forEach(e=>{const i=e.querySelector('.in');const h=e.clientHeight, w=e.clientWidth;
 const ih=i.scrollHeight+parseFloat(getComputedStyle(e).paddingTop)+parseFloat(getComputedStyle(e).paddingBottom);
 if(ih>h+1||i.scrollWidth>w+1){if(location.hash==='#qa')e.classList.add('ovf');bad.push(e.closest('section').id+': '+e.dataset.name+' ('+Math.round(ih)+'>'+h+')');}});
document.body.setAttribute('data-overflow',JSON.stringify(bad));
</script></body></html>`;
    fs.writeFileSync(out, html);
    return out;
  }
}
module.exports = Twin;
