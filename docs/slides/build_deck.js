// Genera docs/slides/presentacion.pptx y docs/slides/guion.md.
// Uso (desde docs/slides/):  NODE_PATH=.build/node_modules node build_deck.js
// Todas las cifras salen de docs/informe/informe.md y analysis/results/*.md (no se inventa ningún número).
const path = require("path");
const fs = require("fs");
const TWIN = !!process.env.TWIN;
const pptxgen = TWIN ? require("./twin.js") : require("pptxgenjs");

const SKILL = process.env.PPTX_SKILL_DIR;
const { applyTheme } = SKILL ? require(path.join(SKILL, "scripts/apply_theme.js")) : { applyTheme: null };

const HERE = __dirname;
const FIG = (f) => path.join(HERE, "..", "figures", f);
const IMG = (f) => path.join(HERE, "img", f);

// ---------- Tema ----------
const HEX = {
  bg: "0B0E14", text: "F2F4F8", surface: "171D29", muted: "A3ADBD",
  green: "2EE6A6", amber: "FF9F43", grey: "7D8796", light: "C9CED6", red: "FF6B6B", line: "2A3344",
};
const THEME = {
  name: "Reforma RL oscuro",
  headFontFace: "Arial",
  bodyFontFace: "Arial",
  colors: {
    dk1: HEX.bg, lt1: HEX.text, dk2: HEX.surface, lt2: HEX.muted,
    accent1: HEX.green, accent2: HEX.amber, accent3: HEX.grey, accent4: HEX.light,
    accent5: HEX.red, accent6: HEX.line, hlink: HEX.green, folHlink: HEX.muted,
  },
};

const pres = new pptxgen();
if (TWIN) pres.themeColors = THEME.colors;
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Semáforos inteligentes en Av. La Reforma con RL multiagente";
pres.subject = "CC3104 Aprendizaje por Refuerzo, UVG, 2026";
pres.author = "Equipo del proyecto";
const C = pres.SchemeColor;
// Alias legibles de los colores de esquema
const S = {
  bg: C.text1, text: C.background1, surface: C.text2, muted: C.background2,
  green: C.accent1, amber: C.accent2, grey: C.accent3, light: C.accent4, red: C.accent5, line: C.accent6,
};

const W = 13.333, MX = 0.6;

// ---------- Layouts ----------
pres.defineSlideMaster({
  title: "PORTADA",
  background: { color: S.bg },
  objects: [],
});
pres.defineSlideMaster({
  title: "CONTENIDO",
  background: { color: S.bg },
  margin: [0.4, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.35, w: W - 2 * MX, h: 0.95,
        fontFace: "Arial", fontSize: 30, bold: true, color: S.text, valign: "middle", margin: 0 }, text: "" } },
    { text: { text: "Semáforos inteligentes en Av. La Reforma · CC3104 · UVG 2026",
        options: { x: MX, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: S.muted, margin: 0 } } },
  ],
  slideNumber: { x: 12.15, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: S.muted, align: "right" },
});

// ---------- Ayudas ----------
const notes = []; // [titulo, notas]
let n = 0;
function newSlide(section, title, master = "CONTENIDO") {
  const s = pres.addSlide({ masterName: master, sectionTitle: section });
  n += 1;
  if (master === "CONTENIDO") s.addText(title, { placeholder: "title" });
  return s;
}
function note(s, title, text) { s.addNotes(text); notes.push([title, text]); }

function card(s, x, y, w, h, name, fill = S.surface) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill },
    line: { color: S.line, width: 0.75 }, objectName: name });
}
// Motivo visual: punto de "semáforo" de color antes de cada encabezado
function dot(s, x, y, color, d = 0.22, name = "punto") {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color }, line: { color, width: 0 }, objectName: name });
}
function head(s, x, y, w, text, color, size = 18) {
  dot(s, x, y + 0.09, color, 0.22, "punto " + text);
  s.addText(text, { x: x + 0.35, y, w: w - 0.35, h: 0.4, fontSize: size, bold: true, color: S.text,
    margin: 0, valign: "middle", isTextBox: true, objectName: "encabezado " + text });
}
function txt(s, text, o) {
  s.addText(text, Object.assign({ fontSize: 16, color: S.text, margin: 0, valign: "top", isTextBox: true,
    paraSpaceAfter: 6 }, o));
}
function bullets(s, items, o) {
  const arr = items.map((t, i) => ({ text: t, options: { bullet: { indent: 18 }, breakLine: i < items.length - 1 } }));
  txt(s, arr, Object.assign({ paraSpaceAfter: 10 }, o));
}
function stat(s, x, y, w, big, label, color, name, bigSize = 40) {
  s.addText(big, { x, y, w, h: 0.75, fontSize: bigSize, bold: true, color, margin: 0, valign: "bottom",
    isTextBox: true, objectName: name + " cifra" });
  s.addText(label, { x, y: y + 0.8, w, h: 0.7, fontSize: 14, color: S.muted, margin: 0, valign: "top",
    isTextBox: true, objectName: name + " etiqueta" });
}
// Barras horizontales nativas, una serie con un color por barra (hex obligatorio)
function hbar(s, labels, values, colors, x, y, w, h, name, fmt = "0.0", maxV) {
  const opts = {
    x, y, w, h, barDir: "bar", objectName: name,
    chartColors: colors, catAxisOrientation: "maxMin",
    catAxisLabelColor: HEX.text, catAxisLabelFontSize: 14, catAxisLabelFontFace: "+mn-lt",
    catAxisLineShow: false, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: HEX.text, dataLabelFontSize: 14,
    dataLabelFontBold: true, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: fmt,
    barGapWidthPct: 45, showLegend: false, showTitle: false,
    plotArea: { fill: { color: HEX.bg } }, chartArea: { fill: { color: HEX.bg } },
  };
  if (maxV) { opts.valAxisMaxVal = maxV; opts.valAxisMinVal = 0; }
  s.addChart(pres.charts.BAR, [{ name: "serie", labels, values }], opts);
}
function img(s, file, x, y, w, h, name, framed = true) {
  if (framed) s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.12, y: y - 0.12, w: w + 0.24, h: h + 0.24,
    rectRadius: 0.12, fill: { color: "FFFFFF" }, line: { color: "FFFFFF", width: 0 }, objectName: name + " marco" });
  s.addImage({ path: file, x, y, w, h, objectName: name, altText: name });
}
function caption(s, text, y = 6.55, x = MX, w = W - 2 * MX) {
  s.addText(text, { x, y, w, h: 0.35, fontSize: 11, italic: true, color: S.muted, margin: 0, isTextBox: true,
    objectName: "nota al pie" });
}
const G = HEX.green, A = HEX.amber, GR = HEX.grey, LG = HEX.light;

// =====================================================================
// 1. Portada
pres.addSection({ title: "Introducción" });
{
  const s = newSlide("Introducción", "", "PORTADA");
  txt(s, "CC3104 APRENDIZAJE POR REFUERZO · UVG · 2026", { x: MX + 0.2, y: 1.3, w: 9, h: 0.4, fontSize: 14,
    bold: true, color: S.green, charSpacing: 2, objectName: "curso" });
  s.addText([
    { text: "Semáforos inteligentes", options: { breakLine: true } },
    { text: "en Av. La Reforma", options: { color: S.green } },
  ], { x: MX + 0.2, y: 1.85, w: 9.2, h: 2.1, fontSize: 48, bold: true, color: S.text, margin: 0,
    valign: "top", isTextBox: true, objectName: "titulo" });
  txt(s, "Aprendizaje por refuerzo multiagente en un corredor real de 5 cruces", { x: MX + 0.2, y: 4.1, w: 8.6,
    h: 0.9, fontSize: 22, color: S.muted, objectName: "subtitulo" });
  txt(s, "Integrantes: <completar>", { x: MX + 0.2, y: 5.6, w: 8, h: 0.45, fontSize: 18, color: S.text,
    objectName: "integrantes" });
  // semáforo (motivo)
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 10.6, y: 1.4, w: 1.5, h: 4.3, rectRadius: 0.3,
    fill: { color: S.surface }, line: { color: S.line, width: 1 }, objectName: "semaforo caja" });
  [[HEX.red, 30], [A, 30], [G, 0]].forEach(([col, tr], i) => s.addShape(pres.shapes.OVAL, {
    x: 10.85, y: 1.7 + i * 1.3, w: 1.0, h: 1.0, fill: { color: col, transparency: tr ? 75 : 0 },
    line: { color: col, width: 0 }, objectName: "luz " + i }));
  note(s, "Portada",
    "Buenos días. Somos <completar integrantes>. Presentamos nuestro proyecto final de Aprendizaje por Refuerzo: " +
    "semáforos inteligentes en la Avenida La Reforma usando aprendizaje por refuerzo multiagente. " +
    "La idea es sencilla de contar: tomamos un tramo real de Reforma con cinco semáforos consecutivos, lo " +
    "simulamos en SUMO y comparamos, con el mismo protocolo, los controladores clásicos contra agentes que " +
    "aprenden a decidir la siguiente fase. Les vamos a contar qué funcionó, qué no, y un hallazgo sobre la " +
    "recompensa que cambió nuestras conclusiones. Al final hay una demo en vivo con los modelos entrenados.");
}

// 2. Problema
{
  const s = newSlide("Introducción", "El problema: semáforos que no ven la demanda");
  txt(s, "Los semáforos de tiempo fijo reparten el verde sin saber cuántos vehículos esperan en cada aproximación.",
    { x: MX, y: 1.6, w: 6.2, h: 1.4, fontSize: 22, objectName: "mensaje" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y: 3.4, w: 6.2, h: 1.6, rectRadius: 0.12,
    fill: { color: S.bg }, line: { color: S.amber, width: 1.25, dashType: "dash" }, objectName: "dato pendiente" });
  txt(s, "<dato: cifra de congestión en Ciudad de Guatemala con fuente verificable>", { x: MX + 0.3, y: 3.6,
    w: 5.6, h: 1.2, fontSize: 18, color: S.amber, valign: "middle", objectName: "dato texto" });
  const st = [["1.65 km", "corredor en zonas 9 y 10"], ["5", "semáforos consecutivos"],
    ["123–547 m", "entre cruces: coordinación difícil"]];
  st.forEach(([b, l], i) => {
    const y = 1.6 + i * 1.65;
    card(s, 7.4, y, 5.33, 1.45, "tarjeta " + b);
    s.addText(b, { x: 7.65, y: y + 0.2, w: 2.95, h: 1.05, fontSize: 30, bold: true, color: S.green, margin: 0,
      valign: "middle", isTextBox: true, objectName: "cifra " + b });
    txt(s, l, { x: 10.65, y: y + 0.2, w: 1.95, h: 1.05, fontSize: 15, color: S.muted, valign: "middle",
      objectName: "etiqueta " + b });
  });
  note(s, "El problema",
    "La Avenida La Reforma es uno de los ejes más cargados de la ciudad: un bulevar con arriate central, tres " +
    "carriles por sentido y calles transversales de una vía. Sus semáforos funcionan con tiempos fijos: " +
    "reparten el verde según un plan, sin saber cuántos vehículos esperan realmente en cada aproximación. " +
    "<dato: aquí va una cifra de congestión con fuente verificable; no la inventamos>. " +
    "Además, los cruces están a distancias muy desiguales, de 123 a 547 metros, así que coordinarlos no es " +
    "trivial: entre la 15 y la 14 calle caben muy pocos carros y una cola bloquea enseguida al cruce anterior.");
}

// 3. Pregunta
{
  const s = newSlide("Introducción", "Pregunta de investigación");
  card(s, MX, 1.6, W - 2 * MX, 2.6, "tarjeta pregunta");
  txt(s, "¿Cuánto reduce el RL multiagente el tiempo de espera en un corredor real de Guatemala frente al control " +
    "actual, y se mantiene esa mejora ante condiciones que no vio en el entrenamiento?",
    { x: MX + 0.5, y: 1.85, w: W - 2 * MX - 1, h: 2.1, fontSize: 26, bold: true, valign: "middle",
      objectName: "pregunta" });
  const chips = [["Frente a tiempo fijo y actuado", A], ["Frente a max-pressure", LG],
    ["Hora no vista · +30 % · incidente", G]];
  chips.forEach(([t, col], i) => {
    const x = MX + i * 4.1;
    card(s, x, 4.75, 3.85, 1.2, "chip " + t);
    dot(s, x + 0.3, 5.24, col);
    txt(s, t, { x: x + 0.7, y: 4.85, w: 3.0, h: 1.0, fontSize: 17, valign: "middle", objectName: "chip texto " + i });
  });
  note(s, "Pregunta de investigación",
    "Nuestra pregunta tiene dos partes. Primero, cuánto reduce el aprendizaje por refuerzo multiagente la espera " +
    "frente al control actual. Y segundo, si esa mejora se mantiene cuando cambian las condiciones. " +
    "Para que la respuesta sea honesta comparamos contra tres referencias: el tiempo fijo, un controlador " +
    "actuado y max-pressure, que es una regla clásica de la literatura y es exigente. Y para la segunda parte " +
    "evaluamos en una hora que el agente no vio, el mediodía, con 30 % más demanda y con un carril cerrado por " +
    "un incidente.");
}

// 4. Escenario
pres.addSection({ title: "Modelo y métodos" });
{
  const s = newSlide("Modelo y métodos", "Escenario: corredor real de 5 cruces en SUMO");
  img(s, FIG("escenario_corredor.png"), 0.85, 1.55, 3.3, 5.17, "Figura corredor de Reforma");
  head(s, 4.9, 1.6, 7.8, "Red construida con geometría de OpenStreetMap", G);
  txt(s, "Sur a norte: 15, 14, 12, 10a y 6a calle; 3 carriles por sentido; transversales de una vía.",
    { x: 5.25, y: 2.05, w: 7.4, h: 0.8, fontSize: 16, color: S.muted, objectName: "red texto" });
  head(s, 4.9, 3.0, 7.8, "Cruce C12 (12 calle) para un agente", "2F7FD8");
  txt(s, "El más cargado; en rojo, el tramo del incidente de E7.",
    { x: 5.25, y: 3.45, w: 7.4, h: 0.5, fontSize: 16, color: S.muted, objectName: "c12 texto" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.9, y: 4.35, w: 7.83, h: 1.75, rectRadius: 0.12,
    fill: { color: S.surface }, line: { color: S.amber, width: 1.5 }, objectName: "aviso sintetico" });
  head(s, 5.15, 4.55, 7.4, "Datos sintéticos y provisionales", A);
  txt(s, "Conteos (7352 veh/h en el corredor en hora pico) y ciclo fijo de 110 s generados por script, no medidos en campo.",
    { x: 5.5, y: 5.05, w: 7.0, h: 1.15, fontSize: 16, objectName: "aviso texto" });
  note(s, "Escenario",
    "Este es el corredor que modelamos: 1.65 kilómetros de Reforma entre la Plaza Obelisco y la 5a calle, con cinco " +
    "semáforos consecutivos. La red se construyó con las coordenadas, sentidos y carriles de OpenStreetMap, y " +
    "está georreferenciada. Para los métodos de un solo agente recortamos el cruce de la 12 calle, en azul, que " +
    "es el más cargado. El tramo en rojo es donde simulamos el incidente. " +
    "Algo importante desde ya: los conteos vehiculares y el ciclo del semáforo fijo son sintéticos y " +
    "provisionales. Los generó un script con valores plausibles; no son conteos de campo. Por eso nuestros " +
    "resultados son una comparación metodológica entre controladores, no una predicción de lo que pasaría en la calle.");
}

// 5. MDP
{
  const s = newSlide("Modelo y métodos", "Formulación: MDP por cruce, Dec-POMDP en el corredor");
  const cells = [
    ["Estado", G, "Fase actual, verde mínimo cumplido, densidad y cola por carril (24 valores en C12)."],
    ["Acción", A, "Siguiente fase verde cada 5 s; el entorno impone amarillo de 3 s y verde mínimo de 10 s."],
    ["Recompensa", G, "Reducción de la espera acumulada, incluida la de vehículos que esperan para entrar. γ = 0.99."],
    ["Dec-POMDP", LG, "5 agentes con observación local y recompensa de equipo; estado global solo al entrenar (CTDE)."],
  ];
  cells.forEach(([h, col, t], i) => {
    const x = MX + (i % 2) * 6.15, y = 1.55 + Math.floor(i / 2) * 2.55;
    card(s, x, y, 5.95, 2.3, "tarjeta " + h);
    head(s, x + 0.3, y + 0.3, 5.4, h, col, 20);
    txt(s, t, { x: x + 0.65, y: y + 0.85, w: 5.05, h: 1.3, fontSize: 17, color: S.muted, objectName: "texto " + h });
  });
  caption(s, "Episodio: 3600 s simulados = 720 decisiones por agente.", 6.68);
  note(s, "Formulación",
    "Formalmente, cada cruce es un MDP. El estado es la observación de sumo-rl: qué fase está activa, si ya se " +
    "cumplió el verde mínimo, y la densidad y la cola de cada carril; en la 12 calle son 24 valores. La acción es " +
    "elegir la siguiente fase verde cada 5 segundos; el amarillo y el verde mínimo los impone el entorno, por " +
    "seguridad, no el agente. La recompensa es cuánto bajó la espera acumulada, y como veremos en un momento, " +
    "incluye a los vehículos que esperan para entrar. En el corredor tenemos cinco agentes que solo ven su cruce: " +
    "eso es un Dec-POMDP. Usamos recompensa de equipo y, en los métodos centralizados, un estado global que solo " +
    "existe durante el entrenamiento. En ejecución cada semáforo decide solo.");
}

// 6. Métodos
{
  const s = newSlide("Modelo y métodos", "Métodos: de reglas clásicas a RL multiagente");
  const cols = [
    ["Líneas base", "sin aprendizaje", GR, ["Tiempo fijo (Webster, 110 s)", "Actuado", "Max-pressure"]],
    ["Un agente", "cruce C12", G, ["Q-Learning", "Dyna-Q (n = 5, 10, 50)", "DQN + Double + Dueling + PER", "PPO"]],
    ["Multiagente", "corredor de 5 cruces", G, ["IDQN (+ colas de vecinos)", "QMIX", "MAPPO", "Comunicación (DIAL)"]],
  ];
  cols.forEach(([h, sub, col, items], i) => {
    const x = MX + i * 4.1, y = 1.55;
    card(s, x, y, 3.85, 4.6, "columna " + h);
    head(s, x + 0.3, y + 0.3, 3.4, h, col, 22);
    txt(s, sub, { x: x + 0.65, y: y + 0.75, w: 3.0, h: 0.4, fontSize: 15, color: S.muted, objectName: "sub " + h });
    items.forEach((t, j) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.3, y: y + 1.35 + j * 0.78, w: 3.25, h: 0.62,
        rectRadius: 0.08, fill: { color: S.bg }, line: { color: S.line, width: 0.75 }, objectName: "item " + t });
      txt(s, t, { x: x + 0.45, y: y + 1.35 + j * 0.78, w: 3.0, h: 0.62, fontSize: 15, valign: "middle",
        objectName: "item texto " + t });
    });
  });
  caption(s, "Más complejidad hacia la derecha · 3 líneas base y 16 configuraciones de RL con el mismo protocolo.", 6.45);
  note(s, "Métodos",
    "Comparamos una escalera de métodos. A la izquierda, tres líneas base sin aprendizaje: el tiempo fijo, " +
    "calculado con Webster; el actuado de SUMO, que extiende el verde mientras detecta vehículos; y max-pressure, " +
    "que en cada intervalo da verde a la fase con mayor diferencia de ocupación entre entrada y salida. " +
    "En el cruce de la 12 calle probamos un agente: Q-Learning y Dyna-Q tabulares, DQN con sus tres mejoras, y PPO. " +
    "En el corredor completo, multiagente: aprendices independientes IDQN, QMIX, MAPPO con crítico centralizado y " +
    "comunicación aprendida al estilo DIAL. En total, 16 configuraciones de RL, todas con la misma fábrica de " +
    "entornos y el mismo presupuesto.");
}

// 7. Hallazgo clave
{
  const s = newSlide("Modelo y métodos", "Hallazgo clave: el agente aprendía a bloquear una entrada");
  txt(s, "Con la recompensa estándar de sumo-rl, los autos que no caben en el carril esperan fuera de la red sin costo.",
    { x: MX, y: 1.5, w: 12.1, h: 0.8, fontSize: 20, objectName: "explicacion" });
  const hc = (t, col) => ({ text: t, options: { bold: true, color: col || HEX.text, fill: { color: HEX.surface } } });
  const c = (t, o = {}) => ({ text: t, options: Object.assign({ color: HEX.text }, o) });
  const rows = [
    [hc(""), hc("Tiempo fijo", A), hc("DQN original", HEX.red), hc("DQN corregido", G)],
    [c("Espera media", { color: HEX.muted }), c("29.2 s"), c("14.9 s", { bold: true }), c("19.7 s")],
    [c("No entró (backlog)", { color: HEX.muted }), c("0.21 %"), c("4.92 %", { bold: true, color: HEX.red }), c("0.46 %")],
    [c("Demora total", { color: HEX.muted }), c("31.6 s"), c("97.1 s", { bold: true, color: HEX.red }), c("34.4 s", { bold: true, color: G })],
  ];
  s.addTable(rows, { x: MX, y: 2.45, w: 7.6, colW: [2.3, 1.7, 1.8, 1.8], rowH: 0.62, fontSize: 16,
    fontFace: "Arial", valign: "middle", align: "center", border: { type: "solid", pt: 0.75, color: HEX.line },
    fill: { color: HEX.bg }, objectName: "tabla atajo" });
  caption(s, "Cruce C12, 40 episodios de entrenamiento, 3 semillas de evaluación (corridas de sanidad).", 5.05, MX, 7.6);
  card(s, 8.6, 2.45, 4.13, 3.1, "tarjeta correccion");
  head(s, 8.9, 2.7, 3.7, "Corrección", G, 20);
  bullets(s, ["La recompensa suma la espera de los pendientes de entrar", "Métrica principal: demora total por vehículo demandado"],
    { x: 8.95, y: 3.3, w: 3.55, h: 2.1, fontSize: 16, objectName: "correccion lista" });
  txt(s, "La espera media premiaba el atajo; la demora total lo castiga.", { x: MX, y: 5.8, w: 12.1, h: 0.5,
    fontSize: 18, bold: true, color: S.amber, objectName: "conclusion atajo" });
  note(s, "Hallazgo clave",
    "Este es el hallazgo que más nos enseñó. En las primeras corridas, todos los agentes parecían aprender y le " +
    "ganaban al tiempo fijo en espera media. Por ejemplo, un DQN bajaba la espera a 14.9 segundos contra 29.2 del " +
    "fijo. Pero mirando más de cerca, habían aprendido a cerrar una entrada: casi 5 % de la demanda nunca entraba a " +
    "la red. La recompensa de sumo-rl solo cuenta la espera sobre los carriles, y cuando un carril se llena la " +
    "penalización queda acotada; los que no caben esperan afuera gratis. Contando a esos vehículos, la demora total " +
    "era 97.1 segundos, tres veces la del fijo. La corrección fue doble: entrenar con una recompensa que suma la " +
    "espera de los pendientes, y medir todo con la demora total por vehículo demandado, que no se puede mejorar " +
    "dejando autos fuera. El mismo DQN bajó a 0.46 % de backlog y 34.4 segundos.");
}

// 8. Protocolo
{
  const s = newSlide("Modelo y métodos", "Protocolo: mismo presupuesto, semillas separadas");
  const steps = [
    ["Entrenar", "5 semillas × 200 episodios = 144 000 decisiones por agente", G],
    ["Validar", "Checkpoint cada 20 episodios; se elige el mejor con semillas 2000 y 2001", LG],
    ["Evaluar", "10 episodios nunca vistos (semillas 1000 a 1009)", LG],
    ["Comparar", "Media ± IC95; t de Welch con corrección de Holm", A],
  ];
  steps.forEach(([h, t, col], i) => {
    const x = MX + i * 3.08;
    card(s, x, 1.6, 2.85, 2.75, "paso " + h);
    s.addText(String(i + 1), { x: x + 0.3, y: 1.8, w: 0.6, h: 0.6, fontSize: 28, bold: true, color: col, margin: 0,
      isTextBox: true, objectName: "numero " + h });
    txt(s, h, { x: x + 0.95, y: 1.85, w: 1.8, h: 0.5, fontSize: 20, bold: true, valign: "middle", objectName: "paso titulo " + h });
    txt(s, t, { x: x + 0.3, y: 2.55, w: 2.3, h: 1.7, fontSize: 15, color: S.muted, objectName: "paso texto " + h });
    if (i < 3) s.addShape(pres.shapes.CHEVRON, { x: x + 2.89, y: 2.85, w: 0.16, h: 0.26,
      fill: { color: S.line }, line: { color: S.line, width: 0 }, objectName: "flecha " + i, flipH: false });
  });
  card(s, MX, 4.7, W - 2 * MX, 1.6, "tarjeta metrica");
  head(s, MX + 0.3, 4.92, 11.5, "Métrica principal: demora total (s/veh demandado)", G, 20);
  txt(s, "Espera en la red + retraso de inserción + espera afuera de quienes nunca entraron.",
    { x: MX + 0.65, y: 5.45, w: 11.3, h: 0.6, fontSize: 17, color: S.muted, objectName: "metrica texto" });
  note(s, "Protocolo",
    "Para que la comparación sea justa, todos los métodos de RL siguen el mismo protocolo. Cada configuración se " +
    "entrena con cinco semillas y el mismo presupuesto: 200 episodios de una hora, que son 144 000 decisiones por " +
    "agente. Cada 20 episodios guardamos un checkpoint y elegimos el mejor con dos semillas de validación. Ese " +
    "modelo se evalúa en diez episodios con semillas que nunca se usaron para entrenar ni para elegir. Reportamos " +
    "media e intervalo de confianza del 95 %, donde la unidad es la semilla de entrenamiento, y comparamos con " +
    "la prueba t de Welch corregida por Holm. Con cinco semillas el poder es bajo: «sin diferencia detectable» no " +
    "significa «iguales». Y la métrica principal es la demora total que acabamos de explicar.");
}

// 9. E1
pres.addSection({ title: "Resultados" });
{
  const s = newSlide("Resultados", "E1 · Max-pressure es una línea base muy fuerte");
  txt(s, "Corredor, hora pico · demora total (s/veh)", { x: MX, y: 1.5, w: 6.6, h: 0.4, fontSize: 16, bold: true,
    color: S.muted, objectName: "titulo grafica" });
  hbar(s, ["Tiempo fijo (±8.5)", "Actuado (±6.1)", "Max-pressure (±2.5)"], [79.1, 63.4, 41.7], [A, GR, LG],
    MX, 1.95, 6.8, 3.4, "Grafica E1 corredor", "0.0", 95);
  caption(s, "Media ± IC95 entre 10 episodios de evaluación.", 5.45, MX, 6.8);
  const st = [["−47 %", "max-pressure frente al fijo en el corredor (41.7 vs 79.1 s)", G],
    ["−41 %", "en el cruce C12 (19.8 vs 33.6 s)", G], ["12.7–15.7 %", "de la demanda no entra con +30 % de demanda", HEX.red]];
  st.forEach(([b, l, col], i) => {
    const y = 1.55 + i * 1.6;
    card(s, 7.9, y, 4.83, 1.42, "tarjeta " + b);
    s.addText(b, { x: 8.15, y: y + 0.15, w: 4.4, h: 0.6, fontSize: 30, bold: true, color: col, margin: 0,
      valign: "middle", isTextBox: true, objectName: "cifra " + b });
    txt(s, l, { x: 8.15, y: y + 0.8, w: 4.4, h: 0.55, fontSize: 14, color: S.muted, objectName: "etiqueta " + b });
  });
  note(s, "E1 líneas base",
    "El primer experimento responde qué tan bueno es lo actual. En el corredor en hora pico, el tiempo fijo tiene " +
    "79.1 segundos de demora total por vehículo, el actuado 63.4 y max-pressure 41.7: casi la mitad que el fijo. " +
    "En el cruce de la 12 calle pasa lo mismo, 19.8 contra 33.6. Max-pressure también deja el menor backlog. " +
    "Esto es importante para el resto de la charla: max-pressure es una regla de una línea que no aprende nada, y " +
    "aun así es la vara más alta. Con 30 % más demanda el corredor se satura en las tres líneas base, con entre " +
    "12.7 y 15.7 % de la demanda sin poder entrar.");
}

// 10. E2–E4
{
  const s = newSlide("Resultados", "E2–E4 · Un cruce: DQN y PPO cerca de max-pressure");
  txt(s, "Cruce C12, hora pico · demora total (s/veh)", { x: MX, y: 1.5, w: 7, h: 0.4, fontSize: 16, bold: true,
    color: S.muted, objectName: "titulo grafica" });
  hbar(s, ["Tiempo fijo", "Actuado", "Max-pressure", "Q-Learning", "Dyna-Q n=50", "DQN base", "DQN completo", "PPO"],
    [33.6, 38.0, 19.8, 39.0, 47.3, 22.7, 21.1, 23.8], [A, GR, LG, "1E9A73", "1E9A73", G, G, G],
    MX, 1.9, 7.0, 4.5, "Grafica E2-E4 cruce", "0.0", 56);
  caption(s, "DQN completo = Double + Dueling + PER. Media de 5 semillas (líneas base: 10 episodios).", 6.45, MX, 7.2);
  const f = [["E2 · Planificar no ayudó", "Dyna-Q n=50: +8.2 s frente a Q-Learning (p = 0.16); ningún tabular alcanza al fijo."],
    ["E3 · Variantes de DQN en el ruido", "Completo frente a base: −1.6 s (p = 0.23)."],
    ["E4 · DQN ≈ PPO", "PPO +2.8 s (p = 0.10); ambos sin diferencia detectable con max-pressure."]];
  f.forEach(([h, t], i) => {
    const y = 1.55 + i * 1.62;
    card(s, 8.0, y, 4.73, 1.45, "hallazgo " + i);
    txt(s, h, { x: 8.25, y: y + 0.15, w: 4.3, h: 0.4, fontSize: 17, bold: true, color: S.green, objectName: "hallazgo titulo " + i });
    txt(s, t, { x: 8.25, y: y + 0.6, w: 4.3, h: 0.8, fontSize: 14, color: S.muted, objectName: "hallazgo texto " + i });
  });
  note(s, "E2 a E4 un cruce",
    "En el cruce aislado probamos tres preguntas. E2: ¿ayuda planificar? No. Dyna-Q con 50 pasos de planificación " +
    "quedó incluso 8 segundos peor que Q-Learning, sin diferencia detectable, y ningún método tabular alcanzó al " +
    "tiempo fijo; además dejan autos afuera. E3: ¿qué mejora de DQN aporta más? Ninguna se separa del ruido; la " +
    "versión completa con Double, Dueling y PER tiene la media más baja, 21.1 segundos, y es la que usamos después. " +
    "E4: DQN contra PPO. Rinden parecido: 21.1 contra 23.8 segundos, sin diferencia detectable entre ellos ni con " +
    "max-pressure, que tiene 19.8. Los dos bajan claramente la demora frente al fijo y al actuado.");
}

// 11. E5–E6
{
  const s = newSlide("Resultados", "E5–E6 · MAPPO mejora al fijo, no a max-pressure");
  txt(s, "Corredor, hora pico · demora total (s/veh)", { x: MX, y: 1.5, w: 7, h: 0.4, fontSize: 16, bold: true,
    color: S.muted, objectName: "titulo grafica" });
  hbar(s, ["Tiempo fijo (±8.5)", "Actuado (±6.1)", "Max-pressure (±2.5)", "IDQN (±38.1)", "IDQN + vecinos (±6.8)",
    "QMIX (±20.5)", "MAPPO (±7.3)", "Comunicación (±14.9)"],
    [79.1, 63.4, 41.7, 64.1, 51.9, 55.0, 46.8, 46.2], [A, GR, LG, G, G, G, G, G],
    MX, 1.9, 7.2, 4.5, "Grafica E5-E6 corredor", "0.0", 92);
  caption(s, "Media ± IC95 entre 5 semillas de entrenamiento (líneas base: 10 episodios).", 6.45, MX, 7.2);
  card(s, 8.1, 1.55, 4.63, 1.75, "tarjeta mappo");
  s.addText("−41 %", { x: 8.35, y: 1.65, w: 4.2, h: 0.8, fontSize: 40, bold: true, color: S.green, margin: 0,
    valign: "middle", isTextBox: true, objectName: "cifra mappo" });
  txt(s, "MAPPO frente al tiempo fijo (p Holm < 0.001)", { x: 8.35, y: 2.5, w: 4.2, h: 0.7, fontSize: 14,
    color: S.muted, objectName: "etiqueta mappo" });
  card(s, 8.1, 3.45, 4.63, 1.4, "tarjeta mp");
  txt(s, "+5.1 s frente a max-pressure", { x: 8.35, y: 3.6, w: 4.2, h: 0.45, fontSize: 18, bold: true, color: S.light,
    objectName: "cifra mp" });
  txt(s, "p = 0.13: sin diferencia detectable", { x: 8.35, y: 4.1, w: 4.2, h: 0.6, fontSize: 14, color: S.muted,
    objectName: "etiqueta mp" });
  card(s, 8.1, 5.0, 4.63, 1.4, "tarjeta ola");
  txt(s, "Sin ola verde", { x: 8.35, y: 5.15, w: 4.2, h: 0.45, fontSize: 18, bold: true, color: S.amber, objectName: "cifra ola" });
  txt(s, "Comunicación: 4.1 paradas/veh; líneas base: 2.7–3.9", { x: 8.35, y: 5.65, w: 4.2, h: 0.65, fontSize: 14,
    color: S.muted, objectName: "etiqueta ola" });
  note(s, "E5 y E6 corredor multiagente",
    "En el corredor completo, E5 compara qué tan centralizado es el entrenamiento. MAPPO obtiene 46.8 segundos: " +
    "41 % menos que el tiempo fijo y 26 % menos que el actuado, ambos significativos tras Holm. El orden de las " +
    "medias es el esperado, MAPPO, luego QMIX, luego IDQN, y sobre todo MAPPO es mucho más estable entre semillas; " +
    "pero con cinco semillas esas diferencias no son detectables. Lo central: MAPPO queda 5.1 segundos por encima " +
    "de max-pressure, sin diferencia detectable. En E6, la comunicación aprendida baja la media de IDQN al nivel de " +
    "MAPPO, 46.2 segundos, pero no vemos ola verde: los vehículos paran más veces que con cualquier línea base. La " +
    "ganancia viene de vaciar colas, no de sincronizar cruces.");
}

// 12. E7
{
  const s = newSlide("Resultados", "E7 · La ventaja se pierde con +30 % de demanda");
  const hc = (t) => ({ text: t, options: { bold: true, color: HEX.text, fill: { color: HEX.surface } } });
  const c = (t, o = {}) => ({ text: t, options: Object.assign({ color: HEX.text }, o) });
  const best = { bold: true, color: G }, bad = { bold: true, color: HEX.red, fill: { color: "3A1E24" } };
  const rows = [
    [hc("Corredor · s/veh"), hc("Pico"), hc("Mediodía"), hc("+30 %"), hc("Incidente")],
    [c("Tiempo fijo", { color: A, bold: true, align: "left" }), c("79.1"), c("30.4"), c("345.7"), c("198.4")],
    [c("Actuado", { color: HEX.muted, bold: true, align: "left" }), c("63.4"), c("18.7"), c("320.4"), c("180.5")],
    [c("Max-pressure", { color: LG, bold: true, align: "left" }), c("41.7"), c("21.1"), c("252.2", best), c("161.8", best)],
    [c("MAPPO", { color: G, bold: true, align: "left" }), c("36.8", best), c("17.2", best), c("373.3", bad), c("165.5")],
    [c("Comunicación", { color: G, bold: true, align: "left" }), c("36.8", best), c("20.7"), c("281.8"), c("175.2")],
  ];
  s.addTable(rows, { x: MX, y: 1.6, w: 7.7, colW: [2.3, 1.35, 1.35, 1.35, 1.35], rowH: 0.62, fontSize: 17,
    fontFace: "Arial", valign: "middle", align: "center", border: { type: "solid", pt: 0.75, color: HEX.line },
    fill: { color: HEX.bg }, objectName: "tabla E7" });
  caption(s, "Demora total media de 10 episodios. Agentes: una semilla por familia, elegida por validación (favorece a los agentes).",
    5.55, MX, 7.7);
  caption(s, "Cruce C12 con incidente (2 de 3 carriles de la aproximación sur cerrados): max-pressure 158, DQN 190, " +
    "PPO 192, actuado 201, fijo 228 s/veh.", 6.05, MX, 7.7);
  card(s, 8.7, 1.6, 4.03, 2.2, "tarjeta x13");
  s.addText("+48 %", { x: 8.95, y: 1.7, w: 3.6, h: 0.8, fontSize: 40, bold: true, color: S.red, margin: 0,
    valign: "middle", isTextBox: true, objectName: "cifra x13" });
  txt(s, "MAPPO frente a max-pressure con +30 % de demanda (y +8 % frente al fijo)", { x: 8.95, y: 2.55, w: 3.6, h: 1.1,
    fontSize: 14, color: S.muted, objectName: "etiqueta x13" });
  card(s, 8.7, 4.0, 4.03, 2.2, "tarjeta degradacion");
  s.addText("×10.1 vs ×6.0", { x: 8.95, y: 4.1, w: 3.6, h: 0.8, fontSize: 30, bold: true, color: S.amber, margin: 0,
    valign: "middle", isTextBox: true, objectName: "cifra degradacion" });
  txt(s, "Degradación de la demora de pico a +30 %: MAPPO frente a max-pressure", { x: 8.95, y: 4.95, w: 3.6, h: 1.1,
    fontSize: 14, color: S.muted, objectName: "etiqueta degradacion" });
  note(s, "E7 robustez",
    "E7 pregunta si el mejor agente generaliza. A mediodía, una hora que no vio, todos los agentes siguen ganándole " +
    "al tiempo fijo, y MAPPO tiene la menor demora del corredor. Con el carril cerrado, MAPPO y comunicación mejoran " +
    "al fijo y al actuado, pero no a max-pressure. En el cruce aislado, con dos carriles cerrados en la aproximación " +
    "sur, DQN y PPO mejoran 16 % al tiempo fijo pero quedan 21 % por detrás de max-pressure. La caída está con 30 % más demanda: MAPPO sube a 373 segundos, " +
    "8 % peor que el tiempo fijo y 48 % peor que max-pressure, y deja casi un cuarto de la demanda sin entrar. Con " +
    "las cinco semillas de E5 el resultado es el mismo. Su demora se multiplica por 10 respecto de la hora pico, " +
    "contra 6 de max-pressure. Ojo: aquí cada agente es una sola semilla, la mejor en validación, así que la tabla " +
    "incluso favorece a los agentes. Lo aprendido no se sostiene fuera del rango de demanda del entrenamiento.");
}

// 13. E8
{
  const s = newSlide("Resultados", "E8 · En el cruce, menos demora cuesta equidad");
  txt(s, "Cruce C12 · espera máxima en la 12 calle (s)", { x: MX, y: 1.5, w: 6.8, h: 0.4, fontSize: 16, bold: true,
    color: S.muted, objectName: "titulo grafica" });
  hbar(s, ["Tiempo fijo", "Actuado", "Max-pressure", "DQN", "PPO"], [113, 100, 271, 222, 168], [A, GR, LG, G, G],
    MX, 1.9, 6.8, 3.6, "Grafica E8 equidad cruce", "0", 330);
  caption(s, "Media de 5 semillas (líneas base: 10 episodios). +48 % a +140 % frente al fijo.", 5.6, MX, 6.8);
  card(s, 7.8, 1.55, 4.93, 2.25, "tarjeta corredor");
  head(s, 8.05, 1.75, 4.5, "En el corredor, sin ese costo", G);
  txt(s, "Espera máxima en transversales: MAPPO 314 s, max-pressure 420 s, tiempo fijo 524 s.", { x: 8.4, y: 2.25,
    w: 4.15, h: 1.4, fontSize: 17, color: S.muted, objectName: "texto corredor" });
  card(s, 7.8, 4.0, 4.93, 2.25, "tarjeta co2");
  head(s, 8.05, 4.2, 4.5, "CO₂ frente al tiempo fijo", A);
  txt(s, "Actuado −11.3 %, max-pressure −9.6 %; agentes aprendidos entre −8.4 % y +2.7 %.", { x: 8.4, y: 4.7,
    w: 4.15, h: 1.4, fontSize: 17, color: S.muted, objectName: "texto co2" });
  note(s, "E8 equidad y CO2",
    "E8 pregunta si se sacrifica a las calles transversales. En el cruce aislado, sí: max-pressure, DQN y PPO bajan " +
    "la demora total favoreciendo a Reforma, y la espera máxima de un vehículo en la 12 calle sube de 113 segundos " +
    "con el fijo a entre 168 y 271. PPO es el más equitativo de los aprendidos. Es el trade-off clásico entre " +
    "eficiencia y equidad. En el corredor, en promedio, ese costo no apareció: MAPPO tiene esperas máximas en " +
    "transversales menores que las líneas base, aunque alguna semilla individual sí abandonó una calle. Probamos " +
    "una penalización de equidad: ayudó a QMIX pero no fue detectable. Y en CO2, los que menos emiten son el " +
    "actuado y max-pressure; los agentes paran más veces y quedan entre −8.4 y +2.7 % respecto del fijo.");
}

// 14. Resumen
{
  const s = newSlide("Resultados", "Resumen: el RL vence al fijo, no a max-pressure");
  img(s, FIG("resumen_demora_total.png"), 1.05, 1.55, 11.24, 5.2, "Figura resumen de demora total");
  note(s, "Resumen de resultados",
    "Esta figura resume todo. A la izquierda el corredor, a la derecha el cruce; las líneas punteadas son el tiempo " +
    "fijo y max-pressure. Los mejores métodos aprendidos, MAPPO y comunicación en el corredor y DQN y PPO en el " +
    "cruce, mejoran claramente al tiempo fijo y al actuado. Pero quedan en la misma banda que max-pressure o un poco " +
    "por encima. Los métodos tabulares ni siquiera llegan al tiempo fijo. Fíjense también en el ancho de los " +
    "intervalos: IDQN y QMIX varían mucho entre semillas, y MAPPO es el más estable de los multiagente. " +
    "Recuerden que la magnitud frente al fijo depende de conteos sintéticos; la comparación contra max-pressure " +
    "depende menos de ese supuesto, porque todos ven exactamente la misma demanda.");
}

// 15. Demo
pres.addSection({ title: "Demo y cierre" });
{
  const s = newSlide("Demo y cierre", "Demo en vivo: tiempo fijo contra MAPPO");
  img(s, IMG("demo_100_ui.jpg"), MX + 0.05, 1.55, 8.3, 4.67, "Captura de la demo con incidente", false);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y: 1.5, w: 8.4, h: 4.77, rectRadius: 0.06,
    fill: { color: S.bg, transparency: 100 }, line: { color: S.line, width: 1 }, objectName: "marco demo" });
  caption(s, "Captura del video de respaldo: incidente en Reforma entre la 12 y la 10a calle.", 6.4, MX, 8.4);
  bullets(s, ["Dos simulaciones SUMO sincronizadas: misma demanda y semilla",
    "En vivo: inyectar autos, cambiar la hora, cerrar carriles",
    "«Mejora» = espera en vivo, no la demora total evaluada"],
    { x: 9.35, y: 1.6, w: 3.4, h: 3.6, fontSize: 16, objectName: "demo lista" });
  card(s, 9.3, 5.25, 3.43, 1.0, "tarjeta plan b");
  txt(s, "Plan B: video de 4:06", { x: 9.5, y: 5.25, w: 3.1, h: 1.0, fontSize: 16, bold: true, color: S.amber,
    valign: "middle", objectName: "plan b" });
  note(s, "Demo en vivo",
    "Ahora la demo. Son dos simulaciones de SUMO corriendo en paralelo con la misma demanda y la misma semilla: " +
    "arriba el semáforo de tiempo fijo y abajo MAPPO, el modelo entrenado real. Vamos a: uno, arrancar en " +
    "hora pico y acelerar para ver cómo se separan las curvas; dos, inyectar carros en la entrada sur y en la 12 " +
    "calle; tres, cerrar dos carriles entre la 12 y la 10a calle y ver cómo crece la cola. Una aclaración: la tarjeta " +
    "«Mejora» usa la espera promedio en vivo, que no es la demora total de la evaluación; los números oficiales son " +
    "los que ya mostramos. Si algo falla, tenemos el video de respaldo de unos cuatro minutos.");
}

// 16. Ética y limitaciones
{
  const s = newSlide("Demo y cierre", "Ética y limitaciones");
  card(s, MX, 1.55, 5.95, 3.15, "tarjeta no ve");
  head(s, MX + 0.3, 1.8, 5.4, "Lo que el modelo no ve", HEX.red, 20);
  bullets(s, ["Peatones: fases mínimas como restricción dura", "Emergencias: prioridad por encima del agente",
    "Buses y motos: la recompensa cuenta vehículos, no personas"],
    { x: MX + 0.4, y: 2.4, w: 5.3, h: 2.2, fontSize: 17, objectName: "no ve lista" });
  card(s, 6.78, 1.55, 5.95, 3.15, "tarjeta limitaciones");
  head(s, 7.08, 1.8, 5.4, "Limitaciones", A, 20);
  bullets(s, ["Conteos y ciclo fijo sintéticos", "5 semillas: poco poder estadístico",
    "Detectores perfectos en simulación; brecha con la calle"],
    { x: 7.18, y: 2.4, w: 5.3, h: 2.2, fontSize: 17, objectName: "limitaciones lista" });
  card(s, MX, 4.95, W - 2 * MX, 1.4, "tarjeta quien gana");
  head(s, MX + 0.3, 5.15, 11.5, "¿Quién gana y quién pierde?", LG, 20);
  txt(s, "En el cruce gana quien va por Reforma; la espera máxima en la transversal sube hasta 140 % frente al fijo.",
    { x: MX + 0.65, y: 5.65, w: 11.3, h: 0.55, fontSize: 17, color: S.muted, objectName: "quien gana texto" });
  note(s, "Ética y limitaciones",
    "Hay cosas que nuestro modelo no ve y que importan. No hay peatones: un controlador que solo optimiza demora " +
    "vehicular puede recortar las ventanas para cruzar, así que las fases peatonales deberían ser una restricción " +
    "dura. No sabe que existen las ambulancias: esa prioridad tiene que ir por encima del agente. Y la recompensa " +
    "cuenta vehículos, no personas, así que no distingue un bus lleno de un carro. " +
    "Entre las limitaciones: los datos son sintéticos, cinco semillas dan poco poder estadístico, y en la simulación " +
    "el agente ve colas exactas por carril, algo que en la calle exigiría detectores en cada carril. Además, " +
    "optimizar demora total es una decisión de valores: en el cruce ganan quienes van por la avenida y pierden las " +
    "transversales. Eso debería decidirse con la Municipalidad y la ciudadanía.");
}

// 17. Conclusiones
{
  const s = newSlide("Demo y cierre", "Conclusiones y trabajo futuro");
  const concl = [
    ["Sí mejora frente al control actual", "−41 % (MAPPO, corredor) y −37 % (DQN, cruce)", G],
    ["No supera a max-pressure", "Ninguna diferencia a favor del RL", LG],
    ["Se degrada fuera de lo entrenado", "Con +30 % de demanda, MAPPO queda peor que el fijo", HEX.red],
    ["Medir bien cambia la conclusión", "Demora total en lugar de espera media", A],
  ];
  concl.forEach(([h, t, col], i) => {
    const y = 1.55 + i * 1.2;
    s.addText(String(i + 1), { x: MX, y, w: 0.6, h: 1.0, fontSize: 32, bold: true, color: col, margin: 0,
      valign: "middle", isTextBox: true, objectName: "conclusion numero " + i });
    txt(s, h, { x: MX + 0.75, y: y + 0.05, w: 6.6, h: 0.45, fontSize: 19, bold: true, objectName: "conclusion " + i });
    txt(s, t, { x: MX + 0.75, y: y + 0.52, w: 6.6, h: 0.45, fontSize: 15, color: S.muted, objectName: "conclusion texto " + i });
  });
  card(s, 8.3, 1.55, 4.43, 4.75, "tarjeta futuro");
  head(s, 8.55, 1.8, 4.0, "Trabajo futuro", G, 20);
  bullets(s, ["Conteos reales en video y ciclos cronometrados", "Peatones, buses y motos", "Más semillas y demanda variable",
    "Max-pressure como respaldo (aprendizaje residual)"],
    { x: 8.6, y: 2.4, w: 3.95, h: 3.8, fontSize: 16, objectName: "futuro lista" });
  note(s, "Conclusiones y trabajo futuro",
    "Respondiendo la pregunta, con datos sintéticos: primero, sí hay mejora frente al control actual: MAPPO baja la " +
    "demora total 41 % en el corredor y DQN 37 % en el cruce. Segundo, ningún método aprendido superó a max-pressure: " +
    "una regla clásica bien implementada fue la vara que el RL no pasó con este presupuesto. Tercero, los agentes " +
    "se degradan más que las reglas clásicas cuando la demanda sale del rango de entrenamiento. Y cuarto, un " +
    "hallazgo metodológico: con la recompensa estándar y la espera media, todos habrían parecido mejores mientras " +
    "bloqueaban entradas. Como trabajo futuro, lo primero son datos reales; después, peatones, buses y motos, más " +
    "semillas y entrenamiento con demanda variable, y usar max-pressure como respaldo o punto de partida del agente.");
}

// 18. Uso de IA
{
  const s = newSlide("Demo y cierre", "Declaración del uso de IA");
  card(s, MX, 1.55, 7.3, 3.15, "tarjeta herramienta");
  head(s, MX + 0.3, 1.8, 6.8, "Claude Code (Anthropic)", G, 20);
  bullets(s, ["Plan del proyecto y contratos entre módulos", "Código, pruebas y análisis, con agentes en ramas paralelas",
    "Borradores del informe y de esta presentación"],
    { x: MX + 0.4, y: 2.4, w: 6.7, h: 2.2, fontSize: 18, objectName: "uso lista" });
  card(s, 8.15, 1.55, 4.58, 3.15, "tarjeta responsabilidad");
  head(s, 8.4, 1.8, 4.1, "Responsabilidad", A, 20);
  txt(s, "El equipo revisó el código y los números, y responde por ellos.", { x: 8.45, y: 2.4, w: 4.0, h: 1.0,
    fontSize: 18, objectName: "responsabilidad texto" });
  txt(s, "<completar: qué se verificó a mano>", { x: 8.45, y: 3.6, w: 4.0, h: 0.9, fontSize: 16, color: S.amber,
    objectName: "responsabilidad pendiente" });
  ["Plan", "Ramas en paralelo", "Pruebas automáticas", "Revisión humana"].forEach((t, i) => {
    const x = MX + i * 3.08;
    card(s, x, 5.0, 2.85, 1.2, "flujo " + t);
    dot(s, x + 0.3, 5.49, i === 3 ? A : G);
    txt(s, t, { x: x + 0.7, y: 5.0, w: 2.05, h: 1.2, fontSize: 17, bold: true, valign: "middle", objectName: "flujo texto " + t });
    if (i < 3) s.addShape(pres.shapes.CHEVRON, { x: x + 2.89, y: 5.47, w: 0.16, h: 0.26,
      fill: { color: S.line }, line: { color: S.line, width: 0 }, objectName: "flecha flujo " + i });
  });
  note(s, "Uso de IA",
    "Declaramos que usamos IA generativa de forma intensiva. La herramienta principal fue Claude Code, un asistente " +
    "de programación que trabaja desde la terminal. Con él redactamos el plan y los contratos entre módulos, y " +
    "varios agentes trabajaron en paralelo, cada uno en su rama: red y demanda, líneas base, métodos, experimentos, " +
    "demo web y análisis. También generó los borradores del informe y de esta presentación a partir de las tablas " +
    "de resultados. El asistente puede equivocarse de formas difíciles de notar, por eso el equipo revisó el código " +
    "y los números y asume la responsabilidad. <completar: qué verificó el equipo a mano y otras herramientas usadas>.");
}

// 19. Preguntas
{
  const s = newSlide("Demo y cierre", "", "PORTADA");
  s.addText("¿Preguntas?", { x: MX + 0.2, y: 2.2, w: 9, h: 1.4, fontSize: 60, bold: true, color: S.text, margin: 0,
    isTextBox: true, objectName: "preguntas" });
  txt(s, "github.com/Alexistodj124/ProyectoFinalAR", { x: MX + 0.2, y: 3.9, w: 9, h: 0.5, fontSize: 20,
    color: S.green, objectName: "repositorio" });
  txt(s, "CC3104 Aprendizaje por Refuerzo · UVG · 2026", { x: MX + 0.2, y: 4.5, w: 9, h: 0.5, fontSize: 16,
    color: S.muted, objectName: "curso cierre" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 10.6, y: 1.4, w: 1.5, h: 4.3, rectRadius: 0.3,
    fill: { color: S.surface }, line: { color: S.line, width: 1 }, objectName: "semaforo caja" });
  [[HEX.red, 1], [A, 1], [G, 0]].forEach(([col, dim], i) => s.addShape(pres.shapes.OVAL, {
    x: 10.85, y: 1.7 + i * 1.3, w: 1.0, h: 1.0, fill: { color: col, transparency: dim ? 75 : 0 },
    line: { color: col, width: 0 }, objectName: "luz " + i }));
  note(s, "Preguntas",
    "Gracias. En resumen: el RL multiagente le gana al semáforo fijo y al actuado en nuestra simulación, pero una " +
    "regla clásica como max-pressure sigue siendo igual o mejor, y los agentes se degradan con más demanda. El código, " +
    "el informe y los resultados están en el repositorio. Con gusto respondemos sus preguntas.");
}

// ---------- Escribir ----------
(async () => {
  const out = path.join(HERE, "presentacion.pptx");
  await pres.writeFile({ fileName: out });
  if (TWIN) return console.log("gemelo HTML escrito");
  if (applyTheme) await applyTheme(out, THEME);
  let md = "# Guion de la presentación\n\n" +
    "Semáforos inteligentes en Av. La Reforma con RL multiagente · CC3104 · UVG 2026. " +
    `${notes.length} diapositivas, unos 15–20 minutos (≈1 min por diapositiva; la demo puede tomar 2–3 min). ` +
    "Las notas también están en el campo de notas de `presentacion.pptx`. Lo marcado con `<completar>` o `<dato>` " +
    "lo llena el equipo; no se inventaron cifras (todas salen de `docs/informe/informe.md` y `analysis/results/`).\n\n";
  notes.forEach(([t, txt], i) => { md += `## ${i + 1}. ${t}\n\n${txt}\n\n`; });
  fs.writeFileSync(path.join(HERE, "guion.md"), md);
  console.log("ok", out, notes.length, "diapositivas");
})();
