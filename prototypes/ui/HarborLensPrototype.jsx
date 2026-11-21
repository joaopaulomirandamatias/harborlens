/**
 * HarborLens · by MirandasTech — interactive UI prototype (SPEC-006, design input only).
 *
 * Single-file React component: React hooks, Tailwind CSS utility classes,
 * lucide-react icons and Recharts. Every number, vessel and timestamp below is
 * FICTIONAL example data (synthetic MMSIs use the unassigned MID 199). Nothing
 * here is validated AIS, and nothing here is an implementation of FR-017/FR-018.
 *
 * Domain guard rails encoded in the copy (see docs/requirements/business-rules.md):
 *  - BR-001: a detected stop (stationary candidate) is never presented as a
 *    confirmed vessel activity at a facility; every stop carries "Não validada".
 *  - BR-007 / BR-019: data gaps and window-edge censoring are shown with their
 *    own shape, colour and label; censored durations are lower bounds and are
 *    reported separately in the duration histogram.
 *  - BR-012: population numbers show their denominators.
 *  - NFR-001: the NOT FOR NAVIGATION banner is persistent on every tab.
 *  - NFR-016: WCAG 2.2 AA target — visible focus, shape + colour + text for every
 *    state, contrast-checked tokens, and prefers-reduced-motion support.
 *
 * User-facing copy is Brazilian Portuguese by product decision; code and
 * comments stay in English.
 */
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpDown,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  CircleDashed,
  Clock,
  Copy,
  Crosshair,
  Database,
  Download,
  Eye,
  FileJson,
  FileSpreadsheet,
  FileText,
  Gauge,
  Info,
  Keyboard,
  Layers,
  LayoutDashboard,
  Map as MapIcon,
  MapPin,
  Maximize2,
  Menu,
  Moon,
  Palette,
  Pause,
  Play,
  Ruler,
  Search,
  ShieldCheck,
  Ship,
  Sun,
  Timer,
  Waves,
  X,
  XCircle,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

/* ------------------------------------------------------------------------- */
/* Design tokens                                                              */
/* ------------------------------------------------------------------------- */

const THEMES = {
  light: {
    bg: "#f5f7fa",
    surface: "#ffffff",
    surface2: "#f1f5f9",
    border: "#e2e8f0",
    borderStrong: "#cbd5e1",
    fg: "#0b1726",
    muted: "#475569",
    accent: "#0f766e",
    accentHover: "#115e59",
    accentFg: "#ffffff",
    accentSoft: "#e6f6f4",
    accentText: "#0f766e",
    warnBg: "#fff8e6",
    warnBorder: "#f5c451",
    warnText: "#8a3c0c",
    dangerBg: "#fdf0f0",
    dangerBorder: "#f3b4b4",
    dangerText: "#b42318",
    okBg: "#ecf8f3",
    okBorder: "#9fdcc4",
    okText: "#05603a",
    violetBg: "#f3efff",
    violetText: "#5b21b6",
    ocean: "#0b3a5b",
    chartGrid: "#e2e8f0",
    chartAxis: "#475569",
    glow: "rgba(15,118,110,0.20)",
  },
  dark: {
    bg: "#060d18",
    surface: "#0b1626",
    surface2: "#102036",
    border: "#1d2d45",
    borderStrong: "#2b3f5c",
    fg: "#e7eef7",
    muted: "#a6b4c8",
    accent: "#2dd4bf",
    accentHover: "#5eead4",
    accentFg: "#032826",
    accentSoft: "rgba(45,212,191,0.12)",
    accentText: "#5eead4",
    warnBg: "rgba(251,191,36,0.09)",
    warnBorder: "rgba(251,191,36,0.38)",
    warnText: "#fcd34d",
    dangerBg: "rgba(248,113,113,0.10)",
    dangerBorder: "rgba(248,113,113,0.38)",
    dangerText: "#fca5a5",
    okBg: "rgba(52,211,153,0.10)",
    okBorder: "rgba(52,211,153,0.35)",
    okText: "#6ee7b7",
    violetBg: "rgba(196,181,253,0.12)",
    violetText: "#c4b5fd",
    ocean: "#7dd3fc",
    chartGrid: "#1d2d45",
    chartAxis: "#a6b4c8",
    glow: "rgba(45,212,191,0.24)",
  },
};

/** Map palette is fixed (tactical dark). Marker colours are checked >= 3:1 against land and water. */
const MAP = {
  land: "#142236",
  landEdge: "#2a3b55",
  water: "#0a1a30",
  waterDeep: "#071326",
  channel: "#38bdf8",
  grid: "#1b2b44",
  label: "#cbd5e1",
  labelMuted: "#8ea0b8",
};

/** Marker fills: dark set is used on the map (light violet for the triangle), light set on light surfaces. */
const SHAPE_COLORS = {
  dark: { completa: "#2dd4bf", borda: "#fbbf24", desconhecida: "#c4b5fd" },
  light: { completa: "#0f766e", borda: "#b45309", desconhecida: "#6d28d9" },
};

const STATUS_META = {
  completa: { label: "Parada completa no período", short: "Completa", shape: "circle" },
  borda: { label: "Começou ou terminou fora do período", short: "Parcial no período", shape: "diamond" },
  desconhecida: { label: "Início/fim desconhecido", short: "Início/fim desconhecido", shape: "triangle" },
};

const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent";

const TOKEN_KEYS = Object.keys(THEMES.light);

function buildThemeCss() {
  const block = (name) =>
    `.hl-theme-${name}{${TOKEN_KEYS.map((k) => `--hl-${k}:${THEMES[name][k]};`).join("")}color-scheme:${name};}`;
  return `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
${block("light")}
${block("dark")}
.hl-root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased;}
.hl-bg{background-color:var(--hl-bg);}
.hl-surface{background-color:var(--hl-surface);}
.hl-surface2{background-color:var(--hl-surface2);}
.hl-border{border-color:var(--hl-border);}
.hl-border-strong{border-color:var(--hl-borderStrong);}
.hl-fg{color:var(--hl-fg);}
.hl-muted{color:var(--hl-muted);}
.hl-accent-text{color:var(--hl-accentText);}
.hl-accent-soft{background-color:var(--hl-accentSoft);}
.hl-accent-border{border-color:var(--hl-accent);}
.hl-btn-primary{background-color:var(--hl-accent);color:var(--hl-accentFg);}
.hl-btn-primary:hover{background-color:var(--hl-accentHover);}
.hl-btn-secondary{background-color:var(--hl-surface);color:var(--hl-fg);border-color:var(--hl-borderStrong);}
.hl-btn-secondary:hover{background-color:var(--hl-surface2);}
.hl-btn-ghost{color:var(--hl-fg);}
.hl-btn-ghost:hover{background-color:var(--hl-surface2);}
.hl-tone-neutral{background-color:var(--hl-surface2);border-color:var(--hl-border);color:var(--hl-fg);}
.hl-tone-accent{background-color:var(--hl-accentSoft);border-color:var(--hl-accent);color:var(--hl-accentText);}
.hl-tone-warn{background-color:var(--hl-warnBg);border-color:var(--hl-warnBorder);color:var(--hl-warnText);}
.hl-tone-danger{background-color:var(--hl-dangerBg);border-color:var(--hl-dangerBorder);color:var(--hl-dangerText);}
.hl-tone-ok{background-color:var(--hl-okBg);border-color:var(--hl-okBorder);color:var(--hl-okText);}
.hl-tone-violet{background-color:var(--hl-violetBg);border-color:var(--hl-violetText);color:var(--hl-violetText);}
.hl-text-warn{color:var(--hl-warnText);}
.hl-text-danger{color:var(--hl-dangerText);}
.hl-text-ok{color:var(--hl-okText);}
.hl-text-violet{color:var(--hl-violetText);}
.hl-card-hover{transition:border-color .2s ease,box-shadow .2s ease,transform .2s ease;}
.hl-card-hover:hover{border-color:var(--hl-accent);box-shadow:0 0 0 1px var(--hl-glow),0 12px 28px -16px var(--hl-glow);}
.hl-row{transition:background-color .15s ease;}
.hl-row:hover{background-color:var(--hl-surface2);}
.hl-row-selected{background-color:var(--hl-accentSoft);}
.hl-hatch{background-image:repeating-linear-gradient(135deg,rgba(251,191,36,.6) 0 3px,transparent 3px 7px);}
.hl-tabular{font-variant-numeric:tabular-nums;}
.hl-shimmer{background:linear-gradient(90deg,var(--hl-surface2) 0%,var(--hl-border) 50%,var(--hl-surface2) 100%);background-size:200% 100%;animation:hl-shimmer 1.1s linear infinite;}
@keyframes hl-shimmer{from{background-position:200% 0}to{background-position:-200% 0}}
.hl-enter{animation:hl-enter .2s ease-out both;}
@keyframes hl-enter{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.hl-pop{animation:hl-pop .18s ease-out both;}
.hl-tip{animation:hl-tip .15s ease-out both;}
@keyframes hl-tip{from{opacity:0;translate:0 4px}to{opacity:1;translate:0 0}}
@keyframes hl-pop{from{opacity:0;transform:translateY(4px) scale(.98)}to{opacity:1;transform:none}}
.hl-ping{transform-box:fill-box;transform-origin:center;}
.hl-marker{cursor:pointer;outline:none;}
.hl-marker:focus-visible .hl-marker-focus{stroke:#5eead4;stroke-width:2.5;opacity:1;}
.hl-halo{paint-order:stroke;stroke:#020617;stroke-width:3px;stroke-linejoin:round;}
.hl-scroll{scrollbar-width:thin;scrollbar-color:var(--hl-borderStrong) transparent;}
@media (prefers-reduced-motion: reduce){
  .hl-root *,.hl-root *::before,.hl-root *::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important;scroll-behavior:auto!important;}
}
`;
}

/* ------------------------------------------------------------------------- */
/* Time, number and coordinate formatting (pt-BR, UTC)                       */
/* ------------------------------------------------------------------------- */

const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const utc = (day, h, m = 0) => Date.UTC(2024, 0, day, h, m);

const WINDOW_START = utc(2, 0);
const WINDOW_END = utc(4, 0);
const GAP_START = utc(3, 3);
const GAP_END = utc(3, 5);
const PROCESSED_AT = utc(4, 9, 15);

const pad2 = (n) => String(n).padStart(2, "0");

function fmtDateTime(ms) {
  const d = new Date(ms);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${pad2(d.getUTCHours())}:${pad2(
    d.getUTCMinutes()
  )} UTC`;
}
function fmtClock(ms) {
  const d = new Date(ms);
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}
function fmtDay(ms) {
  const d = new Date(ms);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}
function fmtDuration(minutes) {
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m}min`;
  return m ? `${h}h ${m}min` : `${h}h`;
}
function fmtInt(n) {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}
function fmtDec(x, digits = 1) {
  return x.toFixed(digits).replace(".", ",");
}
function fmtCoord(lat, lon) {
  return `${fmtDec(Math.abs(lat), 4)}° N, ${fmtDec(Math.abs(lon), 4)}° O`;
}
const toIso = (ms) => new Date(ms).toISOString().replace(".000Z", "Z");
const GAP_LABEL = `${fmtDay(GAP_START)} 2024, ${fmtClock(GAP_START)}–${fmtClock(GAP_END)} UTC`;
const WINDOW_LABEL = `${fmtDateTime(WINDOW_START)} → ${fmtDateTime(WINDOW_END - MIN)}`;

/* ------------------------------------------------------------------------- */
/* Fictional example data                                                     */
/* ------------------------------------------------------------------------- */

const RECORDS = { received: 4981, invalid: 12, duplicate: 37, outside: 112, analysed: 4820 };

const RAW_STOPS = [
  { n: 1, start: utc(2, 2, 10), end: utc(2, 6, 25), status: "completa", lon: -95.282, lat: 29.749, radius: 85, type: "Navio-tanque", approach: 180, depart: 0 },
  { n: 2, start: utc(2, 0, 4), end: utc(2, 3, 40), status: "borda", edge: "inicio", lon: -95.215, lat: 29.736, radius: 120, type: "Rebocador", approach: 180, depart: 0 },
  { n: 3, start: utc(2, 5, 30), end: utc(2, 9, 2), status: "completa", lon: -95.155, lat: 29.731, radius: 60, type: "Carga geral", approach: 0, depart: 180 },
  { n: 4, start: utc(2, 8, 15), end: utc(2, 8, 58), status: "completa", lon: -95.09, lat: 29.727, radius: 40, type: "Rebocador", approach: 175, depart: 355 },
  { n: 5, start: utc(2, 10, 17), end: utc(2, 14, 32), status: "completa", lon: -95.018, lat: 29.705, radius: 150, type: "Navio-tanque", approach: 300, depart: 160 },
  { n: 6, start: utc(2, 13, 5), end: utc(2, 19, 50), status: "completa", lon: -94.985, lat: 29.612, radius: 310, type: "Porta-contêineres", approach: 290, depart: 100 },
  { n: 7, start: utc(2, 16, 40), end: utc(2, 17, 35), status: "completa", lon: -94.962, lat: 29.585, radius: 55, type: "Embarcação de serviço", approach: 120, depart: 300 },
  { n: 8, start: utc(2, 20, 12), end: utc(3, 1, 47), status: "completa", lon: -94.905, lat: 29.497, radius: 420, type: "Navio-tanque", approach: 300, depart: 120 },
  { n: 9, start: utc(3, 1, 55), end: utc(3, 2, 58), status: "desconhecida", edge: "fim", lon: -94.858, lat: 29.43, radius: 210, type: "Graneleiro", approach: 120, depart: 300 },
  { n: 10, start: utc(3, 5, 2), end: utc(3, 9, 30), status: "desconhecida", edge: "inicio", lon: -94.885, lat: 29.388, radius: 95, type: "Navio-tanque", approach: 10, depart: 0 },
  { n: 11, start: utc(3, 12, 0), end: utc(3, 15, 48), status: "completa", lon: -94.755, lat: 29.345, radius: 180, type: "Carga geral", approach: 330, depart: 150 },
  { n: 12, start: utc(3, 19, 30), end: utc(3, 23, 57), status: "borda", edge: "fim", lon: -94.64, lat: 29.3, radius: 390, type: "Navio-tanque", approach: 20, depart: 200 },
];

const LON0 = -95.33;
const LON1 = -94.55;
const LAT0 = 29.24;
const LAT1 = 29.8;
const VW = 1000;
const VH = 640;
const project = (lon, lat) => [((lon - LON0) / (LON1 - LON0)) * VW, ((LAT1 - lat) / (LAT1 - LAT0)) * VH];

const STOPS = RAW_STOPS.map((s) => {
  const durMin = (s.end - s.start) / MIN;
  const [x, y] = project(s.lon, s.lat);
  return {
    ...s,
    id: s.n,
    code: `#${pad2(s.n)}`,
    mmsi: String(199000100 + s.n),
    durMin,
    positions: Math.max(8, Math.round(durMin / 2)),
    x,
    y,
  };
});

function statusDetail(stop) {
  if (stop.status === "borda" && stop.edge === "inicio")
    return "Começou antes do início do período analisado. A duração mostrada é um mínimo.";
  if (stop.status === "borda") return "Terminou depois do fim do período analisado. A duração mostrada é um mínimo.";
  if (stop.status === "desconhecida" && stop.edge === "fim")
    return `Fim desconhecido: sem dados a partir de ${fmtDateTime(GAP_START)}.`;
  if (stop.status === "desconhecida") return `Início desconhecido: sem dados até ${fmtDateTime(GAP_END)}.`;
  return "Início e fim observados dentro do período analisado.";
}
const isLowerBound = (stop) => stop.status !== "completa";
const isActiveAt = (stop, t) => t >= stop.start && t <= stop.end;
const inGap = (t) => t >= GAP_START && t < GAP_END;

/** Deterministic pseudo-random generator so the example tracks are stable across renders. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildTrack(stop) {
  const rng = mulberry32(stop.n * 9973 + 17);
  const cosLat = Math.cos((stop.lat * Math.PI) / 180);
  const toLonLat = (dx, dy) => [stop.lon + dx / (111320 * cosLat), stop.lat + dy / 111320];
  const usable = (t) => t >= WINDOW_START && t < WINDOW_END && !inGap(t);
  const points = [];
  const leg = (phase, angleDeg, sign) => {
    for (let i = 12; i >= 1; i -= 1) {
      const step = phase === "antes" ? 13 - i : i;
      const k = phase === "antes" ? i : step;
      const t = phase === "antes" ? stop.start - k * 5 * MIN : stop.end + k * 5 * MIN;
      if (!usable(t)) continue;
      const dist = Math.pow(k, 1.25) * 14 + stop.radius * 1.15;
      const a = ((angleDeg + sign * k * 2.2 + (rng() - 0.5) * 5) * Math.PI) / 180;
      const [lon, lat] = toLonLat(Math.cos(a) * dist, Math.sin(a) * dist);
      const sog = Math.max(0.6, 0.6 + 8.2 * (1 - Math.exp(-k / 4.2)) + (rng() - 0.5) * 0.5);
      points.push({ t, lon, lat, sog: Number(sog.toFixed(2)), phase, sign });
    }
  };
  leg("antes", stop.approach, -1);
  for (let k = 0; k < stop.positions; k += 1) {
    const t = stop.start + ((stop.end - stop.start) * k) / (stop.positions - 1);
    const r = stop.radius * Math.sqrt(rng()) * 0.95;
    const a = rng() * Math.PI * 2;
    const [lon, lat] = toLonLat(Math.cos(a) * r, Math.sin(a) * r);
    const sog = 0.04 + rng() * 0.3 + (rng() > 0.93 ? 0.08 : 0);
    points.push({ t, lon, lat, sog: Number(sog.toFixed(2)), phase: "durante" });
  }
  leg("depois", stop.depart, 1);
  points.sort((p, q) => p.t - q.t);
  const during = points.filter((p) => p.phase === "durante");
  const maxSog = Math.max(...during.map((p) => p.sog));
  const maxGapMin = (stop.end - stop.start) / MIN / (stop.positions - 1);
  return { points, during, maxSog, maxGapMin };
}

const TRACKS = new Map(STOPS.map((s) => [s.id, buildTrack(s)]));

const HOURLY = Array.from({ length: 48 }, (_, i) => {
  const t0 = WINDOW_START + i * HOUR;
  const t1 = t0 + HOUR;
  const gap = t0 >= GAP_START && t0 < GAP_END;
  const active = STOPS.filter((s) => s.start < t1 && s.end >= t0);
  return {
    i,
    t0,
    gap,
    ativas: gap ? null : active.length,
    semDados: gap ? 6 : null,
    codes: active.map((s) => s.code),
  };
});

const DURATION_BUCKETS = [
  { key: "<1h", label: "até 1h", min: 0, max: 60 },
  { key: "1-2h", label: "1h a 2h", min: 60, max: 120 },
  { key: "2-4h", label: "2h a 4h", min: 120, max: 240 },
  { key: "4-6h", label: "4h a 6h", min: 240, max: 360 },
  { key: ">6h", label: "mais de 6h", min: 360, max: Infinity },
].map((b) => {
  const inBucket = STOPS.filter((s) => s.durMin >= b.min && s.durMin < b.max);
  return {
    ...b,
    completa: inBucket.filter((s) => s.status === "completa").length,
    borda: inBucket.filter((s) => s.status === "borda").length,
    desconhecida: inBucket.filter((s) => s.status === "desconhecida").length,
  };
});

const STATUS_COUNTS = {
  completa: STOPS.filter((s) => s.status === "completa").length,
  borda: STOPS.filter((s) => s.status === "borda").length,
  desconhecida: STOPS.filter((s) => s.status === "desconhecida").length,
};

const CLI_COMMAND = "harborlens --input tests/fixtures/synthetic_ais.csv --out results";
const SOURCE_FILE = "exemplo_houston_2024-01-02_a_03.csv";

const NOT_FOR_NAVIGATION =
  "Somente para pesquisa histórica — não use para navegação (NOT FOR NAVIGATION). As paradas mostradas não são atracações, fundeios ou escalas confirmadas.";

/* ------------------------------------------------------------------------- */
/* Small utilities                                                            */
/* ------------------------------------------------------------------------- */

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}
function luminance(hex) {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}
const isHex = (v) => /^#[0-9a-f]{6}$/i.test(v);

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch (err) {
      return false;
    }
  }
}

function downloadText(filename, mime, text) {
  try {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    return true;
  } catch (e) {
    return false;
  }
}

function usePrefersReducedMotion() {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const onChange = () => setReduced(mq.matches);
    onChange();
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else mq.addListener(onChange);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener("change", onChange);
      else mq.removeListener(onChange);
    };
  }, []);
  return reduced;
}

/** Brief shimmer after a filter change: tactile feedback without blocking input. */
function useBriefLoading(deps, ms = 220) {
  const [loading, setLoading] = useState(false);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return undefined;
    }
    setLoading(true);
    const id = setTimeout(() => setLoading(false), ms);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return loading;
}

/* ------------------------------------------------------------------------- */
/* Primitive components (shadcn/ui-like)                                      */
/* ------------------------------------------------------------------------- */

function Card({ className = "", hover = false, children, ...rest }) {
  return (
    <div
      className={`rounded-xl border hl-border hl-surface shadow-sm shadow-slate-900/5 ${hover ? "hl-card-hover" : ""} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

function CardHeader({ title, subtitle, icon: Icon, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
      <div className="flex min-w-0 items-start gap-3">
        {Icon ? (
          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg hl-accent-soft hl-accent-text">
            <Icon size={16} aria-hidden="true" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold leading-6">{title}</h3>
          {subtitle ? <p className="text-xs leading-5 hl-muted">{subtitle}</p> : null}
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

function Button({ variant = "secondary", size = "md", icon: Icon, children, className = "", ...rest }) {
  const variants = {
    primary: "hl-btn-primary border border-transparent shadow-sm",
    secondary: "hl-btn-secondary border",
    ghost: "hl-btn-ghost border border-transparent",
  };
  const sizes = { sm: "h-8 px-3 text-xs gap-1.5", md: "h-10 px-4 text-sm gap-2", icon: "h-9 w-9 justify-center" };
  return (
    <button
      type="button"
      className={`inline-flex select-none items-center rounded-lg font-medium transition-all duration-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${variants[variant]} ${sizes[size]} ${FOCUS} ${className}`}
      {...rest}
    >
      {Icon ? <Icon size={size === "sm" ? 14 : 16} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

function Tooltip({ content, children, side = "top", className = "" }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const pos =
    side === "bottom"
      ? "top-full mt-2 left-1/2 -translate-x-1/2"
      : side === "left"
      ? "right-full mr-2 top-1/2 -translate-y-1/2"
      : "bottom-full mb-2 left-1/2 -translate-x-1/2";
  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      aria-describedby={id}
    >
      {children}
      <span id={id} role="tooltip" className="sr-only">
        {content}
      </span>
      {open ? (
        <span
          aria-hidden="true"
          className={`hl-tip pointer-events-none absolute z-50 w-max max-w-[min(16rem,80vw)] rounded-lg border border-white/10 bg-slate-950/95 px-2.5 py-1.5 text-xs font-medium leading-5 text-slate-50 shadow-lg backdrop-blur-md ${pos}`}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}

function Badge({ tone = "neutral", icon: Icon, children, className = "", interactive = false }) {
  const tones = {
    neutral: "hl-tone-neutral",
    accent: "hl-tone-accent",
    warn: "hl-tone-warn",
    danger: "hl-tone-danger",
    ok: "hl-tone-ok",
    violet: "hl-tone-violet",
  };
  return (
    <span
      tabIndex={interactive ? 0 : undefined}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium leading-5 ${tones[tone]} ${
        interactive ? `cursor-help ${FOCUS}` : ""
      } ${className}`}
    >
      {Icon ? <Icon size={12} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

function UnvalidatedBadge({ side = "top" }) {
  return (
    <Tooltip content="Ainda sem confirmação independente" side={side}>
      <Badge tone="warn" icon={CircleDashed} interactive>
        Não validada
      </Badge>
    </Tooltip>
  );
}

function ShapeGlyph({ shape, color, size = 14, stroke = "none", strokeWidth = 0 }) {
  const s = size;
  const common = { fill: color, stroke, strokeWidth };
  return (
    <svg width={s} height={s} viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      {shape === "circle" ? <circle cx="8" cy="8" r="6" {...common} /> : null}
      {shape === "diamond" ? <path d="M8 1.5 L14.5 8 L8 14.5 L1.5 8 Z" {...common} /> : null}
      {shape === "triangle" ? <path d="M8 1.8 L14.6 13.8 H1.4 Z" {...common} /> : null}
      {shape === "square" ? <rect x="3" y="3" width="10" height="10" rx="1.5" {...common} /> : null}
    </svg>
  );
}

function StatusChip({ status, palette = "light", compact = false }) {
  const meta = STATUS_META[status];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
      <ShapeGlyph shape={meta.shape} color={SHAPE_COLORS[palette][status]} />
      <span>{compact ? meta.short : meta.label}</span>
    </span>
  );
}

function Segmented({ options, value, onChange, label }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap rounded-lg border hl-border hl-surface2 p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all duration-200 ${FOCUS} ${
              active ? "hl-surface shadow-sm hl-fg" : "hl-muted hover:opacity-90"
            }`}
          >
            {o.glyph}
            {o.label}
            {typeof o.count === "number" ? <span className="hl-tabular hl-muted">({o.count})</span> : null}
          </button>
        );
      })}
    </div>
  );
}

function SkeletonRows({ rows = 4, className = "h-12" }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={`hl-shimmer rounded-lg ${className}`} />
      ))}
    </div>
  );
}

function CopyButton({ text, label = "Copiar comando", onResult, size = "md", variant = "secondary" }) {
  const [state, setState] = useState("idle");
  useEffect(() => {
    if (state === "idle") return undefined;
    const id = setTimeout(() => setState("idle"), 2000);
    return () => clearTimeout(id);
  }, [state]);
  const onClick = async () => {
    const ok = await copyText(text);
    setState(ok ? "ok" : "fail");
    if (onResult) onResult(ok);
  };
  return (
    <Button
      variant={variant}
      size={size}
      icon={state === "ok" ? Check : Copy}
      onClick={onClick}
      aria-live="polite"
      className={state === "ok" ? "hl-accent-border" : ""}
    >
      {state === "ok" ? "Copiado!" : state === "fail" ? "Não foi possível copiar" : label}
    </Button>
  );
}

function DownloadButton({ icon, label, filename, mime, build, notify }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return undefined;
    const id = setTimeout(() => setDone(false), 2200);
    return () => clearTimeout(id);
  }, [done]);
  const onClick = () => {
    const ok = downloadText(filename, mime, build());
    setDone(ok);
    notify(
      ok
        ? { tone: "ok", title: `${label.replace("Baixar ", "")} pronto`, body: `${filename} · dados de exemplo, não validados` }
        : { tone: "danger", title: "Não foi possível gerar o arquivo", body: "O navegador bloqueou o download." }
    );
  };
  return (
    <Button variant={done ? "secondary" : "primary"} icon={done ? Check : icon} onClick={onClick} className="w-full justify-center sm:w-auto">
      {done ? "Arquivo gerado!" : label}
    </Button>
  );
}

function Accordion({ title, subtitle, icon: Icon, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <Card>
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className={`flex w-full items-center justify-between gap-3 rounded-xl px-5 py-4 text-left ${FOCUS}`}
        >
          <span className="flex items-center gap-3">
            {Icon ? (
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg hl-surface2 hl-muted">
                <Icon size={16} aria-hidden="true" />
              </span>
            ) : null}
            <span>
              <span className="block text-sm font-semibold">{title}</span>
              {subtitle ? <span className="block text-xs hl-muted">{subtitle}</span> : null}
            </span>
          </span>
          <span className="flex items-center gap-2 text-xs hl-muted">
            {open ? "Recolher" : "Expandir"}
            <ChevronDown size={16} aria-hidden="true" className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
          </span>
        </button>
      </h3>
      {open ? (
        <div id={id} className="hl-pop border-t hl-border px-5 py-4">
          {children}
        </div>
      ) : null}
    </Card>
  );
}

function Toasts({ items, onDismiss }) {
  const tone = { ok: CheckCircle2, danger: XCircle, info: Info, warn: AlertTriangle };
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed bottom-40 right-4 z-[60] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2 sm:bottom-28"
    >
      {items.map((t) => {
        const Icon = tone[t.tone] || Info;
        return (
          <div
            key={t.id}
            className="hl-pop pointer-events-auto flex items-start gap-3 rounded-xl border border-white/10 bg-slate-950/90 p-3 text-slate-50 shadow-xl backdrop-blur-md"
          >
            <Icon
              size={18}
              aria-hidden="true"
              className={t.tone === "danger" ? "text-red-300" : t.tone === "warn" ? "text-amber-300" : "text-teal-300"}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{t.title}</p>
              {t.body ? <p className="text-xs text-slate-300">{t.body}</p> : null}
            </div>
            <button
              type="button"
              onClick={() => onDismiss(t.id)}
              aria-label="Fechar aviso"
              className={`rounded-md p-1 text-slate-300 hover:bg-white/10 ${FOCUS}`}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}

function useToasts() {
  const [items, setItems] = useState([]);
  const seq = useRef(0);
  const dismiss = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (t) => {
      seq.current += 1;
      const id = seq.current;
      setItems((xs) => [...xs.slice(-2), { ...t, id }]);
      setTimeout(() => dismiss(id), 3200);
    },
    [dismiss]
  );
  return { items, push, dismiss };
}

function ChartTooltipBox({ children }) {
  return (
    <div className="rounded-lg border hl-border hl-surface px-3 py-2 text-xs shadow-lg hl-fg">
      {children}
    </div>
  );
}

function svgPatterns(palette) {
  const c = SHAPE_COLORS[palette];
  return (
    <defs>
      <pattern id={`hl-hatch-${palette}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="rgba(251,191,36,0.10)" />
        <rect width="2.5" height="6" fill="rgba(217,119,6,0.75)" />
      </pattern>
      <pattern id={`hl-stripe-${palette}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill={c.borda} opacity="0.35" />
        <rect width="3" height="6" fill={c.borda} />
      </pattern>
      <pattern id={`hl-dots-${palette}`} width="6" height="6" patternUnits="userSpaceOnUse">
        <rect width="6" height="6" fill={c.desconhecida} opacity="0.35" />
        <circle cx="3" cy="3" r="1.8" fill={c.desconhecida} />
      </pattern>
    </defs>
  );
}

/* ------------------------------------------------------------------------- */
/* Tab 1 — Visão geral                                                        */
/* ------------------------------------------------------------------------- */

function KpiCard({ icon: Icon, label, value, hint, tone = "accent", onClick, actionLabel }) {
  const toneClass = { accent: "hl-tone-accent", warn: "hl-tone-warn", danger: "hl-tone-danger", neutral: "hl-tone-neutral" }[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group flex h-full flex-col rounded-xl border hl-border hl-surface p-5 text-left shadow-sm hl-card-hover ${FOCUS}`}
    >
      <div className="flex w-full items-center justify-between gap-2">
        <span className="text-xs font-medium hl-muted">{label}</span>
        <span className={`inline-flex h-8 w-8 items-center justify-center rounded-lg border ${toneClass}`}>
          <Icon size={16} aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 text-3xl font-semibold tracking-tight hl-tabular">{value}</p>
      <p className="mt-1 w-full text-xs leading-5 hl-muted">{hint}</p>
      <span className="mt-auto inline-flex items-center gap-1 pt-3 text-xs font-medium hl-accent-text">
        {actionLabel}
        <ArrowRight size={12} aria-hidden="true" className="transition-transform duration-200 group-hover:translate-x-0.5" />
      </span>
    </button>
  );
}

function HourlyTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0].payload;
  const title = `${fmtDay(d.t0)} 2024, ${fmtClock(d.t0)}–${pad2(new Date(d.t0).getUTCHours())}:59 UTC`;
  return (
    <ChartTooltipBox>
      <p className="font-semibold hl-tabular">{title}</p>
      {d.gap ? (
        <p className="mt-1 flex items-center gap-1.5 hl-text-warn">
          <span className="hl-hatch inline-block h-3 w-3 rounded-sm border border-amber-500" aria-hidden="true" />
          Sem dados neste intervalo
        </p>
      ) : (
        <>
          <p className="mt-1 hl-tabular">
            {d.ativas} {d.ativas === 1 ? "parada ativa" : "paradas ativas"}
          </p>
          {d.codes.length ? <p className="hl-muted hl-tabular">{d.codes.join(" · ")}</p> : null}
        </>
      )}
    </ChartTooltipBox>
  );
}

function DurationTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0].payload;
  const total = d.completa + d.borda + d.desconhecida;
  return (
    <ChartTooltipBox>
      <p className="font-semibold">Duração {d.label}</p>
      <p className="hl-tabular hl-muted">
        {total} {total === 1 ? "parada" : "paradas"}
      </p>
      <ul className="mt-1 space-y-0.5">
        {["completa", "borda", "desconhecida"].map((k) => (
          <li key={k} className="flex items-center gap-1.5 hl-tabular">
            <StatusChip status={k} compact />
            <span className="ml-auto pl-3 font-semibold">{d[k]}</span>
          </li>
        ))}
      </ul>
      {d.borda + d.desconhecida > 0 ? <p className="mt-1 hl-muted">Parciais: a duração é um mínimo.</p> : null}
    </ChartTooltipBox>
  );
}

function OverviewTab({ palette, reduced, openStop, openMap, openQuality, notify }) {
  const t = THEMES[palette];
  const c = SHAPE_COLORS[palette];
  const [filter, setFilter] = useState("todas");
  const [sort, setSort] = useState({ key: "start", dir: "asc" });
  const loading = useBriefLoading([filter, sort.key, sort.dir]);

  const rows = useMemo(() => {
    const list = STOPS.filter((s) => filter === "todas" || s.status === filter);
    const val = (s) => (sort.key === "mmsi" ? s.mmsi : sort.key === "dur" ? s.durMin : sort.key === "end" ? s.end : sort.key === "n" ? s.n : s.start);
    return [...list].sort((a, b) => (val(a) > val(b) ? 1 : -1) * (sort.dir === "asc" ? 1 : -1));
  }, [filter, sort]);

  const toggleSort = (key) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  const SortIcon = ({ k }) => (sort.key !== k ? <ArrowUpDown size={12} aria-hidden="true" /> : sort.dir === "asc" ? <ArrowUp size={12} aria-hidden="true" /> : <ArrowDown size={12} aria-hidden="true" />);
  const ariaSort = (k) => (sort.key !== k ? "none" : sort.dir === "asc" ? "ascending" : "descending");

  const th = (k, label, extra = "") => (
    <th scope="col" aria-sort={ariaSort(k)} className={`px-3 py-2 text-left text-xs font-medium hl-muted ${extra}`}>
      <button type="button" onClick={() => toggleSort(k)} className={`inline-flex items-center gap-1 rounded ${FOCUS}`}>
        {label}
        <SortIcon k={k} />
      </button>
    </th>
  );

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden">
        <div className="relative px-5 py-6 sm:px-6">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 opacity-60"
            style={{ background: `radial-gradient(60rem 18rem at 100% 0%, ${t.accentSoft}, transparent 60%)` }}
          />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-medium hl-muted">Análises · Porto de Houston</p>
              <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[28px] sm:leading-9">Houston · 2–3 jan 2024</h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Badge tone="ok" icon={CheckCircle2}>
                  Análise concluída
                </Badge>
                <UnvalidatedBadge />
                <Tooltip content="Critério de baixa velocidade sustentada, versão 0.2">
                  <Badge tone="neutral" icon={Layers} interactive>
                    Método v0.2
                  </Badge>
                </Tooltip>
              </div>
              <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2 xl:grid-cols-3">
                <div>
                  <dt className="text-xs hl-muted">Período analisado</dt>
                  <dd className="hl-tabular">{WINDOW_LABEL}</dd>
                </div>
                <div>
                  <dt className="text-xs hl-muted">Área de pesquisa</dt>
                  <dd>Houston Ship Channel e Galveston Bay</dd>
                </div>
                <div>
                  <dt className="text-xs hl-muted">Processada em</dt>
                  <dd className="hl-tabular">{fmtDateTime(PROCESSED_AT)}</dd>
                </div>
              </dl>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" icon={MapIcon} onClick={() => openMap()}>
                Abrir mapa histórico
              </Button>
              <Button icon={ShieldCheck} onClick={openQuality}>
                Origem e qualidade
              </Button>
            </div>
          </div>
        </div>
      </Card>

      <section aria-label="Indicadores da análise" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          icon={Crosshair}
          label="Paradas detectadas"
          value={fmtInt(STOPS.length)}
          hint={`${STATUS_COUNTS.completa} completas · ${STATUS_COUNTS.borda} parciais no período · ${STATUS_COUNTS.desconhecida} com início/fim desconhecido`}
          onClick={() => openMap()}
          actionLabel="Ver no mapa"
        />
        <KpiCard
          icon={CircleDashed}
          tone="warn"
          label="Não validadas"
          value="100%"
          hint={`${STOPS.length} de ${STOPS.length} paradas ainda sem confirmação independente`}
          onClick={() => openStop(1)}
          actionLabel="Entender o critério"
        />
        <KpiCard
          icon={Clock}
          tone="danger"
          label="Intervalo sem dados"
          value="1"
          hint={`${GAP_LABEL} · 2h sem registros`}
          onClick={() => openMap(null, GAP_START + 20 * MIN)}
          actionLabel="Ver na linha do tempo"
        />
        <KpiCard
          icon={Database}
          tone="neutral"
          label="Registros AIS analisados"
          value={fmtInt(RECORDS.analysed)}
          hint={`de ${fmtInt(RECORDS.received)} recebidos · ${fmtInt(RECORDS.received - RECORDS.analysed)} descartados na limpeza`}
          onClick={openQuality}
          actionLabel="Ver qualidade"
        />
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader
            icon={Activity}
            title="Paradas detectadas por hora"
            subtitle="Quantas paradas estavam em curso em cada hora (UTC). O trecho hachurado não tem registros."
          />
          <div
            className="h-72 px-2 pb-2 pt-4"
            role="img"
            aria-label={`Gráfico de barras com paradas em curso por hora entre 2 e 3 jan 2024. Sem dados em ${GAP_LABEL}.`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={HOURLY} margin={{ top: 8, right: 12, left: -16, bottom: 0 }} barCategoryGap={2}>
                {svgPatterns(palette)}
                <CartesianGrid vertical={false} stroke={t.chartGrid} strokeDasharray="3 3" />
                <XAxis
                  dataKey="i"
                  ticks={[0, 6, 12, 18, 24, 30, 36, 42]}
                  interval={0}
                  tickFormatter={(i) => `${i < 24 ? "2" : "3"} jan ${pad2(i % 24)}h`}
                  tick={{ fill: t.chartAxis, fontSize: 11 }}
                  axisLine={{ stroke: t.chartGrid }}
                  tickLine={false}
                />
                <YAxis allowDecimals={false} domain={[0, 6]} tick={{ fill: t.chartAxis, fontSize: 11 }} axisLine={false} tickLine={false} />
                <RTooltip content={<HourlyTooltip />} cursor={{ fill: t.accentSoft }} />
                <Bar dataKey="ativas" stackId="h" fill={t.accent} radius={[4, 4, 0, 0]} isAnimationActive={!reduced} animationDuration={500} />
                <Bar dataKey="semDados" stackId="h" fill={`url(#hl-hatch-${palette})`} stroke="#d97706" strokeWidth={1} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap items-center gap-4 px-5 pb-5 text-xs hl-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ background: t.accent }} aria-hidden="true" />
              Paradas em curso
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="hl-hatch inline-block h-3 w-3 rounded-sm border border-amber-500" aria-hidden="true" />
              Sem dados neste intervalo ({GAP_LABEL})
            </span>
          </div>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader
            icon={Timer}
            title="Distribuição por duração das paradas"
            subtitle="Paradas parciais ou com início/fim desconhecido aparecem separadas: a duração delas é um mínimo."
          />
          <div className="h-72 px-2 pb-2 pt-4" role="img" aria-label="Histograma da duração das 12 paradas, separado por situação no período.">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={DURATION_BUCKETS} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                {svgPatterns(palette)}
                <CartesianGrid vertical={false} stroke={t.chartGrid} strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fill: t.chartAxis, fontSize: 11 }} axisLine={{ stroke: t.chartGrid }} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: t.chartAxis, fontSize: 11 }} axisLine={false} tickLine={false} />
                <RTooltip content={<DurationTooltip />} cursor={{ fill: t.accentSoft }} />
                <Bar dataKey="completa" stackId="d" fill={c.completa} isAnimationActive={!reduced} animationDuration={500} />
                <Bar dataKey="borda" stackId="d" fill={`url(#hl-stripe-${palette})`} isAnimationActive={!reduced} animationDuration={500} />
                <Bar dataKey="desconhecida" stackId="d" fill={`url(#hl-dots-${palette})`} radius={[4, 4, 0, 0]} isAnimationActive={!reduced} animationDuration={500} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-2 px-5 pb-5 text-xs hl-muted">
            {["completa", "borda", "desconhecida"].map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <StatusChip status={k} palette={palette} compact />
                <span className="hl-tabular">({STATUS_COUNTS[k]})</span>
              </span>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          icon={Ship}
          title="Análise recente · paradas detectadas"
          subtitle="Clique em uma linha para abrir o detalhe da parada. Todas as paradas são não validadas."
          actions={
            <Segmented
              label="Filtrar por situação no período"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "todas", label: "Todas", count: STOPS.length },
                { value: "completa", label: "Completas", count: STATUS_COUNTS.completa, glyph: <ShapeGlyph shape="circle" color={c.completa} size={10} /> },
                { value: "borda", label: "Parciais", count: STATUS_COUNTS.borda, glyph: <ShapeGlyph shape="diamond" color={c.borda} size={10} /> },
                { value: "desconhecida", label: "Desconhecidas", count: STATUS_COUNTS.desconhecida, glyph: <ShapeGlyph shape="triangle" color={c.desconhecida} size={10} /> },
              ]}
            />
          }
        />
        <div className="relative mt-4 overflow-x-auto px-2 pb-3 hl-scroll">
          {loading ? (
            <div className="px-3 py-2">
              <SkeletonRows rows={Math.min(rows.length || 3, 6)} className="h-11" />
            </div>
          ) : (
            <table className="w-full min-w-[760px] border-separate border-spacing-0 text-sm">
              <caption className="sr-only">Paradas detectadas na análise Houston · 2–3 jan 2024</caption>
              <thead>
                <tr className="border-b hl-border">
                  {th("n", "Parada")}
                  {th("mmsi", "Navio (MMSI)")}
                  {th("start", "Início (UTC)")}
                  {th("end", "Fim (UTC)")}
                  {th("dur", "Duração")}
                  <th scope="col" className="px-3 py-2 text-left text-xs font-medium hl-muted">
                    Situação no período
                  </th>
                  <th scope="col" className="px-3 py-2 text-left text-xs font-medium hl-muted">
                    Validação
                  </th>
                  <th scope="col" className="px-3 py-2">
                    <span className="sr-only">Abrir</span>
                  </th>
                </tr>
              </thead>
              <tbody className="hl-enter">
                {rows.map((s) => (
                  <tr
                    key={s.id}
                    tabIndex={0}
                    onClick={() => openStop(s.id)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), openStop(s.id))}
                    aria-label={`Abrir detalhe da parada ${s.code}, navio ${s.mmsi}`}
                    className={`hl-row cursor-pointer ${FOCUS}`}
                  >
                    <td className="border-t hl-border px-3 py-3 font-semibold hl-tabular">{s.code}</td>
                    <td className="border-t hl-border px-3 py-3 hl-tabular">{s.mmsi}</td>
                    <td className="border-t hl-border px-3 py-3 hl-tabular">{fmtDateTime(s.start)}</td>
                    <td className="border-t hl-border px-3 py-3 hl-tabular">{fmtDateTime(s.end)}</td>
                    <td className="border-t hl-border px-3 py-3 hl-tabular">
                      {isLowerBound(s) ? <span className="hl-muted">≥ </span> : null}
                      {fmtDuration(s.durMin)}
                    </td>
                    <td className="border-t hl-border px-3 py-3">
                      <StatusChip status={s.status} palette={palette} compact />
                    </td>
                    <td className="border-t hl-border px-3 py-3" onClick={(e) => e.stopPropagation()}>
                      <UnvalidatedBadge />
                    </td>
                    <td className="border-t hl-border px-3 py-3 text-right">
                      <ChevronRight size={16} aria-hidden="true" className="inline hl-muted" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="px-3 pt-3 text-xs hl-muted">
            “≥” indica duração mínima: a parada começou ou terminou fora do período, ou encosta no intervalo sem dados.
          </p>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Tab 2 — Mapa histórico                                                     */
/* ------------------------------------------------------------------------- */

const fmt1 = (v) => v.toFixed(1);

function smoothPath(lonlat, closed) {
  const p = lonlat.map(([lon, lat]) => project(lon, lat));
  const n = p.length;
  const get = (i) => (closed ? p[(i + n) % n] : p[Math.max(0, Math.min(n - 1, i))]);
  let d = `M${fmt1(p[0][0])} ${fmt1(p[0][1])}`;
  const last = closed ? n : n - 1;
  for (let i = 0; i < last; i += 1) {
    const p0 = get(i - 1);
    const p1 = get(i);
    const p2 = get(i + 1);
    const p3 = get(i + 2);
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${fmt1(c1[0])} ${fmt1(c1[1])} ${fmt1(c2[0])} ${fmt1(c2[1])} ${fmt1(p2[0])} ${fmt1(p2[1])}`;
  }
  return closed ? `${d} Z` : d;
}
const lineTo = (lon, lat) => {
  const [x, y] = project(lon, lat);
  return ` L${fmt1(x)} ${fmt1(y)}`;
};

const GEO = (() => {
  const bay = smoothPath(
    [
      [-95.005, 29.7], [-94.985, 29.725], [-94.95, 29.745], [-94.9, 29.765], [-94.84, 29.775], [-94.78, 29.765],
      [-94.73, 29.735], [-94.7, 29.69], [-94.69, 29.63], [-94.715, 29.575], [-94.7, 29.545], [-94.62, 29.532],
      [-94.52, 29.53], [-94.45, 29.52], [-94.45, 29.47], [-94.55, 29.455], [-94.64, 29.43], [-94.7, 29.4],
      [-94.735, 29.372], [-94.748, 29.352], [-94.77, 29.336], [-94.82, 29.318], [-94.88, 29.298], [-94.95, 29.275],
      [-95.03, 29.25], [-95.1, 29.225], [-95.25, 29.2], [-95.27, 29.25], [-95.12, 29.275], [-95.02, 29.312],
      [-94.95, 29.345], [-94.905, 29.372], [-94.93, 29.415], [-94.965, 29.455], [-95.0, 29.5], [-95.02, 29.545],
      [-95.02, 29.59], [-95.015, 29.635], [-95.02, 29.665], [-95.015, 29.69],
    ],
    true
  );
  const gulf =
    smoothPath(
      [
        [-95.12, 29.17], [-95.0, 29.225], [-94.9, 29.262], [-94.83, 29.29], [-94.775, 29.318], [-94.756, 29.338],
        [-94.72, 29.352], [-94.66, 29.372], [-94.58, 29.398], [-94.5, 29.43], [-94.4, 29.47],
      ],
      false
    ) +
    lineTo(-94.0, 29.47) +
    lineTo(-94.0, 28.7) +
    lineTo(-95.6, 28.7) +
    lineTo(-95.6, 29.05) +
    " Z";
  const river = smoothPath(
    [
      [-95.4, 29.761], [-95.32, 29.757], [-95.29, 29.75], [-95.25, 29.742], [-95.215, 29.737], [-95.18, 29.733],
      [-95.155, 29.731], [-95.12, 29.729], [-95.09, 29.727], [-95.06, 29.722], [-95.035, 29.713], [-95.018, 29.705],
      [-95.005, 29.698],
    ],
    false
  );
  const sanJacinto = smoothPath([[-95.062, 29.722], [-95.075, 29.75], [-95.07, 29.78], [-95.085, 29.83]], false);
  const clearLake = smoothPath([[-95.02, 29.548], [-95.05, 29.556], [-95.085, 29.552], [-95.1, 29.562], [-95.08, 29.572], [-95.04, 29.566]], true);
  const channel = smoothPath(
    [
      [-95.005, 29.698], [-94.995, 29.66], [-94.982, 29.615], [-94.962, 29.585], [-94.935, 29.54], [-94.905, 29.497],
      [-94.88, 29.465], [-94.858, 29.43], [-94.83, 29.395], [-94.8, 29.365], [-94.765, 29.345], [-94.73, 29.33],
      [-94.68, 29.312], [-94.62, 29.298], [-94.5, 29.27],
    ],
    false
  );
  const spur = smoothPath([[-94.83, 29.395], [-94.865, 29.386], [-94.89, 29.384]], false);
  const turning = project(-95.287, 29.75);
  const graticule = {
    lons: [-95.3, -95.2, -95.1, -95.0, -94.9, -94.8, -94.7, -94.6].map((lon) => ({ lon, x: project(lon, 29.5)[0] })),
    lats: [29.3, 29.4, 29.5, 29.6, 29.7].map((lat) => ({ lat, y: project(-95, lat)[1] })),
  };
  const terminals = [
    { code: "T1", lon: -95.27, lat: 29.766 },
    { code: "T2", lon: -95.13, lat: 29.748 },
    { code: "T3", lon: -95.028, lat: 29.68 },
    { code: "T4", lon: -95.03, lat: 29.612 },
    { code: "T5", lon: -94.918, lat: 29.379 },
    { code: "T6", lon: -94.8, lat: 29.311 },
  ].map((t) => ({ ...t, xy: project(t.lon, t.lat) }));
  const places = [
    { name: "Houston", lon: -95.305, lat: 29.785, kind: "land" },
    { name: "Pasadena", lon: -95.18, lat: 29.706, kind: "land" },
    { name: "Baytown", lon: -95.005, lat: 29.772, kind: "land" },
    { name: "La Porte", lon: -95.1, lat: 29.66, kind: "land" },
    { name: "Texas City", lon: -95.0, lat: 29.395, kind: "land" },
    { name: "Galveston", lon: -94.865, lat: 29.284, kind: "land" },
    { name: "Bolivar", lon: -94.61, lat: 29.408, kind: "land" },
    { name: "Galveston Bay", lon: -94.86, lat: 29.56, kind: "water" },
    { name: "Trinity Bay", lon: -94.835, lat: 29.68, kind: "water" },
    { name: "East Bay", lon: -94.6, lat: 29.49, kind: "water" },
    { name: "Golfo do México", lon: -94.66, lat: 29.27, kind: "water" },
  ].map((p) => ({ ...p, xy: project(p.lon, p.lat) }));
  const channelLabel = project(-95.205, 29.749);
  return { bay, gulf, river, sanJacinto, clearLake, channel, spur, turning, graticule, terminals, places, channelLabel };
})();

const HOME_CAM = { x: VW / 2, y: VH / 2, k: 1 };
function clampCam(cam) {
  const k = Math.min(4, Math.max(1, cam.k));
  const hw = VW / 2 / k;
  const hh = VH / 2 / k;
  return { k, x: Math.min(VW - hw, Math.max(hw, cam.x)), y: Math.min(VH - hh, Math.max(hh, cam.y)) };
}

function MapMarker({ stop, cam, selected, active, dimmed, reduced, onSelect }) {
  const meta = STATUS_META[stop.status];
  const color = SHAPE_COLORS.dark[stop.status];
  const sx = (stop.x - cam.x) * cam.k + VW / 2;
  const sy = (stop.y - cam.y) * cam.k + VH / 2;
  const transition = reduced ? "none" : "transform 600ms cubic-bezier(.2,.7,.2,1), opacity 200ms ease";
  const r = 8;
  const shape =
    meta.shape === "circle" ? (
      <circle r={r} fill={color} stroke="#020617" strokeWidth="2" />
    ) : meta.shape === "diamond" ? (
      <path d={`M0 ${-r - 2} L${r + 2} 0 L0 ${r + 2} L${-r - 2} 0 Z`} fill={color} stroke="#020617" strokeWidth="2" />
    ) : (
      <path d={`M0 ${-r - 2} L${r + 2} ${r} L${-r - 2} ${r} Z`} fill={color} stroke="#020617" strokeWidth="2" />
    );
  return (
    <g
      className="hl-marker"
      style={{ transform: `translate(${sx}px, ${sy}px)`, transition, opacity: dimmed ? 0.55 : 1 }}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`Parada ${stop.code}, navio (MMSI) ${stop.mmsi}, ${meta.label}, início ${fmtDateTime(stop.start)}, duração ${
        isLowerBound(stop) ? "de pelo menos " : ""
      }${fmtDuration(stop.durMin)}, não validada${active ? ", em curso no horário selecionado" : ""}`}
      onClick={() => onSelect(stop.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(stop.id);
        }
      }}
    >
      <circle r="20" fill="transparent" />
      {selected && !reduced ? (
        <circle r="14" fill="none" stroke={color} strokeWidth="2" className="hl-ping motion-safe:animate-ping" opacity="0.7" />
      ) : null}
      {selected ? <circle r="16" fill="none" stroke="#f8fafc" strokeWidth="1.5" opacity="0.9" /> : null}
      <circle r="18" fill="none" className="hl-marker-focus" stroke="transparent" opacity="0" />
      {shape}
      <text x="15" y="4" fontSize="12" fontWeight="600" fill={selected ? "#ffffff" : MAP.label} className="hl-halo hl-tabular">
        {stop.code}
      </text>
    </g>
  );
}

function TacticalMap({ stops, selectedId, time, cam, setCam, reduced, onSelect, highlightActive }) {
  const geoTransition = reduced ? "none" : "transform 600ms cubic-bezier(.2,.7,.2,1)";
  const gapNow = inGap(time);
  const ordered = [...stops].sort((a, b) => (a.id === selectedId ? 1 : 0) - (b.id === selectedId ? 1 : 0));
  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} preserveAspectRatio="xMidYMid meet" className="absolute inset-0 h-full w-full" role="group" aria-label="Mapa ilustrativo do Houston Ship Channel até Galveston Bay com as paradas detectadas">
      <defs>
        <linearGradient id="hl-gulf" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={MAP.water} />
          <stop offset="1" stopColor={MAP.waterDeep} />
        </linearGradient>
        <pattern id="hl-map-hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="3" height="10" fill="rgba(251,191,36,0.22)" />
        </pattern>
      </defs>
      <rect x={-3000} y={-3000} width={7000} height={7000} fill={MAP.land} />
      <g style={{ transform: `translate(${VW / 2 - cam.x * cam.k}px, ${VH / 2 - cam.y * cam.k}px) scale(${cam.k})`, transition: geoTransition }}>
        {GEO.graticule.lons.map((g) => (
          <line key={g.lon} x1={g.x} x2={g.x} y1={-200} y2={VH + 200} stroke={MAP.grid} strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        {GEO.graticule.lats.map((g) => (
          <line key={g.lat} y1={g.y} y2={g.y} x1={-200} x2={VW + 200} stroke={MAP.grid} strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        <path d={GEO.gulf} fill="url(#hl-gulf)" stroke={MAP.landEdge} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        <path d={GEO.bay} fill={MAP.water} stroke={MAP.landEdge} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        <path d={GEO.clearLake} fill={MAP.water} stroke={MAP.landEdge} strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <path d={GEO.sanJacinto} fill="none" stroke={MAP.water} strokeWidth="5" strokeLinecap="round" />
        <path d={GEO.river} fill="none" stroke={MAP.landEdge} strokeWidth="12" strokeLinecap="round" />
        <path d={GEO.river} fill="none" stroke={MAP.water} strokeWidth="9.5" strokeLinecap="round" />
        <ellipse cx={GEO.turning[0]} cy={GEO.turning[1]} rx="9" ry="6" fill={MAP.water} />
        <path d={GEO.river} fill="none" stroke={MAP.channel} strokeOpacity="0.55" strokeWidth="1.4" strokeDasharray="6 5" vectorEffect="non-scaling-stroke" />
        <path d={GEO.channel} fill="none" stroke={MAP.channel} strokeOpacity="0.55" strokeWidth="1.4" strokeDasharray="6 5" vectorEffect="non-scaling-stroke" />
        <path d={GEO.spur} fill="none" stroke={MAP.channel} strokeOpacity="0.55" strokeWidth="1.4" strokeDasharray="6 5" vectorEffect="non-scaling-stroke" />
        {GEO.graticule.lons.filter((g) => g.lon > -95.25).map((g) => (
          <text key={`l${g.lon}`} x={g.x + 4} y={14} fontSize="10" fill={MAP.labelMuted} className="hl-tabular">
            {fmtDec(Math.abs(g.lon), 1)}° O
          </text>
        ))}
        {GEO.graticule.lats.map((g) => (
          <text key={`a${g.lat}`} x={6} y={g.y - 4} fontSize="10" fill={MAP.labelMuted} className="hl-tabular">
            {fmtDec(g.lat, 1)}° N
          </text>
        ))}
        {GEO.places.map((p) => (
          <text
            key={p.name}
            x={p.xy[0]}
            y={p.xy[1]}
            textAnchor="middle"
            fontSize={p.kind === "water" ? 13 : 12}
            fontStyle={p.kind === "water" ? "italic" : "normal"}
            fontWeight={p.kind === "water" ? 500 : 600}
            letterSpacing={p.kind === "water" ? "0.08em" : "0"}
            fill={p.kind === "water" ? "#7dd3fc" : MAP.label}
            opacity={p.kind === "water" ? 0.8 : 0.9}
            className="hl-halo"
          >
            {p.name}
          </text>
        ))}
        <text x={GEO.channelLabel[0]} y={GEO.channelLabel[1] - 10} fontSize="10" textAnchor="middle" fill="#7dd3fc" className="hl-halo" opacity="0.9">
          Houston Ship Channel
        </text>
        {GEO.terminals.map((t) => (
          <g key={t.code} transform={`translate(${t.xy[0]} ${t.xy[1]})`} opacity="0.95">
            <rect x="-5" y="-5" width="10" height="10" rx="2" fill="#0b1626" stroke="#94a3b8" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
            <text x="-8" y="4" textAnchor="end" fontSize="10" fill="#a3b1c4" className="hl-halo">
              {t.code}
            </text>
          </g>
        ))}
      </g>
      {gapNow ? <rect x={-3000} y={-3000} width={7000} height={7000} fill="url(#hl-map-hatch)" /> : null}
      {ordered.map((s) => {
        const active = isActiveAt(s, time);
        return (
          <MapMarker
            key={s.id}
            stop={s}
            cam={cam}
            selected={s.id === selectedId}
            active={active}
            dimmed={highlightActive && !active && s.id !== selectedId}
            reduced={reduced}
            onSelect={onSelect}
          />
        );
      })}
    </svg>
  );
}

function Timeline({ time, setTime, playing, setPlaying, stops, selectedId }) {
  const total = (WINDOW_END - WINDOW_START) / MIN;
  const value = Math.round((time - WINDOW_START) / MIN);
  const pct = (ms) => ((ms - WINDOW_START) / (WINDOW_END - WINDOW_START)) * 100;
  const step = (deltaMin) => setTime(Math.min(WINDOW_END - MIN, Math.max(WINDOW_START, time + deltaMin * MIN)));
  const gapNow = inGap(time);
  const ctl = `inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-slate-100 transition-colors hover:bg-white/10 ${FOCUS}`;
  return (
    <div className="rounded-xl border border-white/10 bg-slate-950/75 p-3 text-slate-100 shadow-xl backdrop-blur-md">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ctl} onClick={() => step(-60)} aria-label="Voltar 1 hora">
          <ChevronsLeft size={16} aria-hidden="true" />
        </button>
        <button type="button" className={ctl} onClick={() => step(-10)} aria-label="Voltar 10 minutos">
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => setPlaying(!playing)}
          aria-label={playing ? "Pausar reprodução" : "Reproduzir linha do tempo"}
          className={`inline-flex h-8 items-center gap-1.5 rounded-lg bg-teal-400 px-3 text-xs font-semibold text-slate-950 transition-colors hover:bg-teal-300 ${FOCUS}`}
        >
          {playing ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
          {playing ? "Pausar" : "Reproduzir"}
        </button>
        <button type="button" className={ctl} onClick={() => step(10)} aria-label="Avançar 10 minutos">
          <ChevronRight size={16} aria-hidden="true" />
        </button>
        <button type="button" className={ctl} onClick={() => step(60)} aria-label="Avançar 1 hora">
          <ChevronsRight size={16} aria-hidden="true" />
        </button>
        <span className="ml-auto text-xs text-slate-300 hl-tabular">
          {gapNow ? (
            <span className="inline-flex items-center gap-1.5 text-amber-200">
              <span className="hl-hatch inline-block h-3 w-3 rounded-sm border border-amber-400" aria-hidden="true" />
              Sem dados neste intervalo
            </span>
          ) : (
            "Arraste ou use as setas do teclado"
          )}
        </span>
      </div>

      <div className="relative mt-3" aria-hidden="true">
        <div className="relative h-4">
          {stops.map((s) => (
            <span
              key={s.id}
              className="absolute top-1 h-2 rounded-full"
              style={{
                left: `${pct(s.start)}%`,
                width: `${Math.max(0.6, pct(s.end) - pct(s.start))}%`,
                background: SHAPE_COLORS.dark[s.status],
                opacity: s.id === selectedId ? 1 : 0.45,
                outline: s.id === selectedId ? "1.5px solid #f8fafc" : "none",
              }}
            />
          ))}
        </div>
      </div>

      <div className="relative mt-1 h-8">
        <div className="absolute inset-x-0 top-3 h-2 rounded-full bg-white/10" aria-hidden="true" />
        <div className="absolute left-0 top-3 h-2 rounded-full bg-teal-400/60" style={{ width: `${(value / total) * 100}%` }} aria-hidden="true" />
        <div
          className="hl-hatch absolute top-1.5 h-5 rounded border border-amber-400/80"
          style={{ left: `${pct(GAP_START)}%`, width: `${pct(GAP_END) - pct(GAP_START)}%` }}
          title="Sem dados neste intervalo"
          aria-hidden="true"
        />
        <input
          type="range"
          min={0}
          max={total - 1}
          step={10}
          value={value}
          onChange={(e) => {
            setPlaying(false);
            setTime(WINDOW_START + Number(e.target.value) * MIN);
          }}
          aria-label="Linha do tempo em UTC"
          aria-valuetext={`${fmtDateTime(time)}${gapNow ? ", sem dados neste intervalo" : ""}`}
          className="peer absolute inset-0 z-10 h-8 w-full cursor-pointer opacity-0"
        />
        <span
          aria-hidden="true"
          className="pointer-events-none absolute top-1 h-6 w-6 -translate-x-1/2 rounded-full border-2 border-slate-950 bg-white shadow-lg ring-teal-300 transition-shadow peer-focus-visible:ring-4"
          style={{ left: `${(value / total) * 100}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-slate-300 hl-tabular" aria-hidden="true">
        <span>2 jan 00:00</span>
        <span className="hidden sm:inline">2 jan 12:00</span>
        <span>3 jan 00:00</span>
        <span className="hidden sm:inline">3 jan 12:00</span>
        <span>3 jan 23:59</span>
      </div>
    </div>
  );
}

function MapLegend() {
  return (
    <Card className="p-4">
      <h3 className="text-sm font-semibold">Legenda</h3>
      <ul className="mt-3 space-y-2.5 text-xs">
        {["completa", "borda", "desconhecida"].map((k) => (
          <li key={k} className="flex items-center gap-2.5">
            <ShapeGlyph shape={STATUS_META[k].shape} color={SHAPE_COLORS.dark[k]} size={16} stroke="#020617" strokeWidth={1} />
            <span>{STATUS_META[k].label}</span>
          </li>
        ))}
        <li className="flex items-center gap-2.5">
          <ShapeGlyph shape="square" color="#0b1626" size={16} stroke="#94a3b8" strokeWidth={1.5} />
          <span>Terminal ilustrativo (T1–T6)</span>
        </li>
        <li className="flex items-center gap-2.5">
          <svg width="16" height="16" aria-hidden="true">
            <line x1="1" y1="8" x2="15" y2="8" stroke="#38bdf8" strokeWidth="1.6" strokeDasharray="4 3" />
          </svg>
          <span>Canal de navegação (traçado aproximado)</span>
        </li>
        <li className="flex items-center gap-2.5">
          <span className="hl-hatch inline-block h-4 w-4 rounded-sm border border-amber-400" aria-hidden="true" />
          <span>Sem dados neste intervalo</span>
        </li>
      </ul>
      <p className="mt-3 border-t hl-border pt-3 text-xs hl-muted">
        Forma, cor e rótulo indicam a situação de cada parada. Todas são não validadas.
      </p>
    </Card>
  );
}

function MapTab({ selectedId, setSelectedId, time, setTime, reduced, openStop }) {
  const [cam, setCam] = useState(HOME_CAM);
  const [playing, setPlaying] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState({ completa: true, borda: true, desconhecida: true });
  const [highlightActive, setHighlightActive] = useState(true);
  const loading = useBriefLoading([query, statusFilter.completa, statusFilter.borda, statusFilter.desconhecida]);
  const listRef = useRef(null);

  const visible = useMemo(() => {
    const q = query.trim().replace("#", "");
    return STOPS.filter((s) => statusFilter[s.status] && (!q || s.mmsi.includes(q) || s.code.includes(q)));
  }, [query, statusFilter]);
  const selected = STOPS.find((s) => s.id === selectedId);
  const activeCount = visible.filter((s) => isActiveAt(s, time)).length;

  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => {
      setTime((t) => {
        const next = t + 10 * MIN;
        if (next >= WINDOW_END) {
          setPlaying(false);
          return WINDOW_END - MIN;
        }
        return next;
      });
    }, 140);
    return () => clearInterval(id);
  }, [playing, setTime]);

  useEffect(() => {
    const el = listRef.current && listRef.current.querySelector(`[data-stop="${selectedId}"]`);
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  }, [selectedId, reduced, loading]);

  const select = (id, { syncTime = true } = {}) => {
    const s = STOPS.find((x) => x.id === id);
    setSelectedId(id);
    setCam((c) => clampCam({ x: s.x, y: s.y, k: Math.max(c.k, 2.2) }));
    if (syncTime && !isActiveAt(s, time)) {
      setPlaying(false);
      setTime(Math.max(WINDOW_START, s.start));
    }
  };

  const glassBtn = `inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-100 transition-colors hover:bg-white/10 ${FOCUS}`;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-3">
        <div className="flex h-[620px] flex-col overflow-hidden rounded-xl border hl-border shadow-sm sm:h-[660px] lg:h-[720px]" style={{ background: MAP.land }}>
          <div className="relative min-h-0 flex-1">
          <TacticalMap
            stops={visible}
            selectedId={selectedId}
            time={time}
            cam={cam}
            setCam={setCam}
            reduced={reduced}
            onSelect={(id) => select(id, { syncTime: false })}
            highlightActive={highlightActive}
          />

          <div className="absolute right-16 top-3 max-w-[calc(100%-5.5rem)] rounded-xl border border-white/10 bg-slate-950/75 px-4 py-3 text-slate-100 shadow-xl backdrop-blur-md" aria-live="polite">
            <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-300">
              <Clock size={12} aria-hidden="true" /> Relógio UTC
            </p>
            <p className="mt-0.5 text-lg font-semibold hl-tabular sm:text-xl">{fmtDateTime(time)}</p>
            <p className="mt-0.5 text-xs text-slate-300 hl-tabular">
              {inGap(time) ? (
                <span className="inline-flex items-center gap-1.5 text-amber-200">
                  <span className="hl-hatch inline-block h-3 w-3 rounded-sm border border-amber-400" aria-hidden="true" />
                  Sem dados neste intervalo
                </span>
              ) : (
                `${activeCount} ${activeCount === 1 ? "parada em curso" : "paradas em curso"} neste horário`
              )}
            </p>
          </div>

          <div className="absolute right-3 top-3 flex flex-col items-end gap-2">
            <div className="flex flex-col rounded-xl border border-white/10 bg-slate-950/75 p-1 shadow-xl backdrop-blur-md">
              <button type="button" className={glassBtn} aria-label="Aproximar" onClick={() => setCam((c) => clampCam({ ...c, k: c.k * 1.5 }))}>
                <ZoomIn size={16} aria-hidden="true" />
              </button>
              <button type="button" className={glassBtn} aria-label="Afastar" onClick={() => setCam((c) => clampCam({ ...c, k: c.k / 1.5 }))}>
                <ZoomOut size={16} aria-hidden="true" />
              </button>
              <button type="button" className={glassBtn} aria-label="Ver área completa" onClick={() => setCam(HOME_CAM)}>
                <Maximize2 size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
          <span className="absolute bottom-3 left-3 rounded-lg border border-white/10 bg-slate-950/75 px-2.5 py-1 text-[11px] font-medium text-slate-200 backdrop-blur-md">
            Mapa ilustrativo · traçados aproximados
          </span>

          {inGap(time) ? (
            <div className="hl-pop pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-xl border border-amber-300/40 bg-slate-950/80 px-4 py-3 text-center text-amber-100 shadow-xl backdrop-blur-md">
              <p className="flex items-center justify-center gap-2 text-sm font-semibold">
                <AlertTriangle size={16} aria-hidden="true" /> Sem dados neste intervalo
              </p>
              <p className="mt-0.5 text-xs text-amber-100/90 hl-tabular">{GAP_LABEL}</p>
            </div>
          ) : null}

          </div>
          <div className="border-t border-white/10 p-3">
            <Timeline time={time} setTime={setTime} playing={playing} setPlaying={setPlaying} stops={visible} selectedId={selectedId} />
          </div>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 text-xs hl-muted">
          <input
            type="checkbox"
            checked={highlightActive}
            onChange={(e) => setHighlightActive(e.target.checked)}
            className={`h-4 w-4 rounded accent-teal-400 ${FOCUS}`}
          />
          Esmaecer paradas que não estão em curso no horário do relógio
        </label>
      </div>

      <aside className="space-y-4" aria-label="Lista de paradas e legenda">
        <Card className="flex flex-col">
          <div className="space-y-3 p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">
                Paradas detectadas <span className="hl-muted hl-tabular">({visible.length} de {STOPS.length})</span>
              </h2>
              <Badge tone="warn" icon={CircleDashed}>
                Todas não validadas
              </Badge>
            </div>
            <label className="relative block">
              <span className="sr-only">Buscar por navio (MMSI) ou número da parada</span>
              <Search size={14} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 hl-muted" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar navio (MMSI) ou nº da parada"
                className={`h-9 w-full rounded-lg border hl-border hl-surface2 pl-8 pr-3 text-sm hl-fg placeholder:text-slate-400 ${FOCUS}`}
              />
            </label>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por situação no período">
              {["completa", "borda", "desconhecida"].map((k) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={statusFilter[k]}
                  onClick={() => setStatusFilter((f) => ({ ...f, [k]: !f[k] }))}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-all duration-200 active:scale-95 ${FOCUS} ${
                    statusFilter[k] ? "hl-border-strong hl-surface2" : "hl-border opacity-60 line-through"
                  }`}
                >
                  <ShapeGlyph shape={STATUS_META[k].shape} color={SHAPE_COLORS.dark[k]} size={11} />
                  {STATUS_META[k].short}
                  <span className="hl-muted hl-tabular">{STATUS_COUNTS[k]}</span>
                </button>
              ))}
            </div>
          </div>
          <div ref={listRef} className="max-h-[420px] space-y-2 overflow-y-auto border-t hl-border p-3 hl-scroll lg:max-h-[372px]">
            {loading ? (
              <SkeletonRows rows={4} className="h-[74px]" />
            ) : visible.length === 0 ? (
              <p className="px-2 py-8 text-center text-sm hl-muted">Nenhuma parada corresponde aos filtros.</p>
            ) : (
              visible.map((s) => {
                const sel = s.id === selectedId;
                const active = isActiveAt(s, time);
                return (
                  <button
                    key={s.id}
                    type="button"
                    data-stop={s.id}
                    aria-pressed={sel}
                    onClick={() => select(s.id)}
                    className={`hl-pop w-full rounded-xl border p-3 text-left transition-all duration-200 hl-card-hover ${FOCUS} ${
                      sel ? "hl-accent-border hl-accent-soft shadow-[0_0_0_1px_rgba(45,212,191,0.35)]" : "hl-border hl-surface2"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <ShapeGlyph shape={STATUS_META[s.status].shape} color={SHAPE_COLORS.dark[s.status]} size={14} />
                      <span className="text-sm font-semibold hl-tabular">{s.code}</span>
                      <span className="text-xs hl-muted">Navio (MMSI)</span>
                      <span className="text-xs font-medium hl-tabular">{s.mmsi}</span>
                      {active ? (
                        <span className="ml-auto inline-flex items-center gap-1 text-[11px] font-medium hl-accent-text">
                          <Activity size={12} aria-hidden="true" /> Em curso
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs hl-muted hl-tabular">
                      <span>{fmtDateTime(s.start)}</span>
                      <span>
                        {isLowerBound(s) ? "≥ " : ""}
                        {fmtDuration(s.durMin)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] hl-muted">{STATUS_META[s.status].label}</p>
                  </button>
                );
              })
            )}
          </div>
          {selected ? (
            <div className="border-t hl-border p-4">
              <div className="mb-3 flex items-center justify-between gap-2 text-xs">
                <span className="hl-muted">
                  Selecionada: <span className="font-semibold hl-fg hl-tabular">{selected.code}</span> · {selected.mmsi}
                </span>
                <UnvalidatedBadge side="left" />
              </div>
              <Button variant="primary" icon={ArrowRight} className="w-full justify-center" onClick={() => openStop(selected.id)}>
                Ver detalhes da parada
              </Button>
            </div>
          ) : null}
        </Card>
        <MapLegend />
      </aside>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Tab 3 — Detalhe da parada                                                  */
/* ------------------------------------------------------------------------- */

function MiniMap({ stop, track, reduced }) {
  const W = 520;
  const H = 340;
  const cosLat = Math.cos((stop.lat * Math.PI) / 180);
  const local = track.points.map((p) => ({
    ...p,
    dx: (p.lon - stop.lon) * 111320 * cosLat,
    dy: (p.lat - stop.lat) * 111320,
  }));
  const extent = Math.max(stop.radius * 1.6, ...local.map((p) => Math.max(Math.abs(p.dx), Math.abs(p.dy)))) * 1.08;
  const scale = (Math.min(W, H) / 2 - 22) / extent;
  const sx = (dx) => W / 2 + dx * scale;
  const sy = (dy) => H / 2 - dy * scale;
  const line = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${fmt1(sx(p.dx))} ${fmt1(sy(p.dy))}`).join(" ");
  const before = local.filter((p) => p.phase === "antes");
  const after = local.filter((p) => p.phase === "depois");
  const during = local.filter((p) => p.phase === "durante");
  const firstDuring = during[0];
  const lastDuring = during[during.length - 1];
  const nice = [25, 50, 100, 200, 250, 500, 1000, 2000];
  const barM = nice.reduce((best, v) => (Math.abs(v * scale - W / 5) < Math.abs(best * scale - W / 5) ? v : best), nice[0]);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label={`Mini-mapa da parada ${stop.code}: ${stop.positions} posições AIS dentro de um raio aproximado de ${stop.radius} metros.`}>
      <rect width={W} height={H} fill={MAP.water} />
      {Array.from({ length: 11 }, (_, i) => (
        <g key={i}>
          <line x1={(W / 10) * i} x2={(W / 10) * i} y1="0" y2={H} stroke={MAP.grid} strokeWidth="1" />
          <line y1={(H / 10) * i} y2={(H / 10) * i} x1="0" x2={W} stroke={MAP.grid} strokeWidth="1" />
        </g>
      ))}
      <circle cx={W / 2} cy={H / 2} r={stop.radius * scale} fill="rgba(45,212,191,0.08)" stroke="#2dd4bf" strokeWidth="1.5" strokeDasharray="5 4" />
      {before.length ? (
        <path d={line([...before, firstDuring])} fill="none" stroke="#94a3b8" strokeWidth="1.8" strokeDasharray="4 3" />
      ) : null}
      {after.length ? <path d={line([lastDuring, ...after])} fill="none" stroke="#cbd5e1" strokeWidth="1.8" strokeDasharray="4 3" /> : null}
      {before.map((p) => (
        <circle key={`b${p.t}`} cx={sx(p.dx)} cy={sy(p.dy)} r="2.6" fill="#94a3b8" />
      ))}
      {after.map((p) => (
        <circle key={`a${p.t}`} cx={sx(p.dx)} cy={sy(p.dy)} r="2.6" fill="#cbd5e1" />
      ))}
      {during.map((p, i) => (
        <circle key={`d${i}`} cx={sx(p.dx)} cy={sy(p.dy)} r="2.4" fill="#2dd4bf" opacity="0.65" />
      ))}
      <g transform={`translate(${W / 2} ${H / 2})`}>
        <line x1="-9" x2="9" y1="0" y2="0" stroke="#f8fafc" strokeWidth="1.6" />
        <line y1="-9" y2="9" x1="0" x2="0" stroke="#f8fafc" strokeWidth="1.6" />
        <circle r="3" fill="#020617" stroke="#f8fafc" strokeWidth="1.4" />
      </g>
      <g transform={`translate(16 ${H - 18})`}>
        <rect x="-6" y="-16" width={barM * scale + 64} height="26" rx="6" fill="rgba(2,6,23,0.7)" />
        <line x1="0" x2={barM * scale} y1="0" y2="0" stroke="#e2e8f0" strokeWidth="2" />
        <line x1="0" x2="0" y1="-4" y2="4" stroke="#e2e8f0" strokeWidth="2" />
        <line x1={barM * scale} x2={barM * scale} y1="-4" y2="4" stroke="#e2e8f0" strokeWidth="2" />
        <text x={barM * scale + 8} y="4" fontSize="11" fill="#e2e8f0" className="hl-tabular">
          {fmtInt(barM)} m
        </text>
      </g>
      <g transform={`translate(${W - 24} 28)`}>
        <path d="M0 -12 L6 4 L0 0 L-6 4 Z" fill="#e2e8f0" />
        <text y="18" textAnchor="middle" fontSize="11" fontWeight="600" fill="#e2e8f0">
          N
        </text>
      </g>
    </svg>
  );
}

function SogTooltip({ active, payload }) {
  if (!active || !payload || !payload.length || payload[0].value == null) return null;
  const d = payload[0].payload;
  const phase = { antes: "Antes da parada", durante: "Durante a parada", depois: "Depois da parada" }[d.phase];
  return (
    <ChartTooltipBox>
      <p className="font-semibold hl-tabular">{fmtDateTime(d.t)}</p>
      <p className="hl-tabular">{fmtDec(d.sog, 2)} nós</p>
      <p className="hl-muted">{phase}</p>
    </ChartTooltipBox>
  );
}

function buildReport(stop, track) {
  return {
    title: `HarborLens · Houston 2–3 jan 2024 · Parada ${stop.code}`,
    notice:
      "EXAMPLE DATA. NOT FOR NAVIGATION. Algorithmically detected low-speed stop; unvalidated. Not a confirmed vessel activity at any facility.",
    synthetic_example: true,
    validation_status: "unvalidated",
    method: { name: "Método v0.2", min_points: 8, max_speed_knots: 0.5, min_duration_minutes: 30, max_gap_minutes: 15, max_radius_meters: 1000 },
    analysis_window_utc: { start: toIso(WINDOW_START), end: toIso(WINDOW_END) },
    data_gaps_utc: [{ start: toIso(GAP_START), end: toIso(GAP_END) }],
    stop: {
      code: stop.code,
      mmsi: stop.mmsi,
      start_utc: toIso(stop.start),
      end_utc: toIso(stop.end),
      duration_minutes: Math.round(stop.durMin),
      duration_is_lower_bound: isLowerBound(stop),
      boundary_status: stop.status === "completa" ? "observed" : stop.status === "borda" ? "censored_by_window" : "unknown_due_to_gap",
      centroid_wgs84: { lon: stop.lon, lat: stop.lat },
      approx_drift_radius_meters: stop.radius,
      ais_positions: stop.positions,
      max_speed_during_stop_knots: track.maxSog,
    },
    source: { file: SOURCE_FILE, processed_at_utc: toIso(PROCESSED_AT), records_analysed: RECORDS.analysed },
  };
}
function buildGeoJson(stop, track) {
  return {
    type: "FeatureCollection",
    name: `harborlens-parada-${pad2(stop.n)}`,
    notice: "EXAMPLE DATA. NOT FOR NAVIGATION. Unvalidated algorithmic stop.",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [stop.lon, stop.lat] },
        properties: {
          code: stop.code,
          mmsi: stop.mmsi,
          start_utc: toIso(stop.start),
          end_utc: toIso(stop.end),
          validation_status: "unvalidated",
          synthetic_example: true,
          approx_drift_radius_meters: stop.radius,
        },
      },
      {
        type: "Feature",
        geometry: { type: "LineString", coordinates: track.points.map((p) => [Number(p.lon.toFixed(6)), Number(p.lat.toFixed(6))]) },
        properties: { code: stop.code, kind: "example_track", validation_status: "unvalidated" },
      },
    ],
  };
}
function buildCsv(stop, track) {
  const phase = { antes: "Antes da parada", durante: "Durante a parada", depois: "Depois da parada" };
  const head = "Parada,Navio (MMSI),Data e hora (UTC),Latitude,Longitude,Velocidade sobre o fundo (nós),Fase,Situação";
  const rows = track.points.map((p) =>
    [stop.code, stop.mmsi, toIso(p.t), p.lat.toFixed(6), p.lon.toFixed(6), p.sog.toFixed(2), phase[p.phase], "Não validada (dados de exemplo)"].join(",")
  );
  return `${head}\n${rows.join("\n")}\n`;
}

function MetricTile({ icon: Icon, label, value, hint, info }) {
  return (
    <div className="rounded-xl border hl-border hl-surface2 p-4">
      <p className="flex items-center gap-1.5 text-xs font-medium hl-muted">
        <Icon size={14} aria-hidden="true" />
        {label}
        {info ? (
          <Tooltip content={info}>
            <span tabIndex={0} className={`inline-flex rounded ${FOCUS}`} aria-label={`Mais informações: ${label}`}>
              <Info size={12} aria-hidden="true" />
            </span>
          </Tooltip>
        ) : null}
      </p>
      <p className="mt-1.5 text-base font-semibold hl-tabular">{value}</p>
      {hint ? <p className="mt-0.5 text-xs hl-muted">{hint}</p> : null}
    </div>
  );
}

function PeriodStrip({ stop, palette }) {
  const pct = (ms) => ((ms - WINDOW_START) / (WINDOW_END - WINDOW_START)) * 100;
  const color = SHAPE_COLORS[palette][stop.status];
  return (
    <div className="px-5 pb-5">
      <p className="text-xs font-medium hl-muted">Posição da parada no período analisado</p>
      <div className="relative mt-2 h-7 rounded-lg border hl-border hl-surface2" role="img" aria-label={`Parada de ${fmtDateTime(stop.start)} a ${fmtDateTime(stop.end)}, dentro do período de 2 a 3 jan 2024. Sem dados em ${GAP_LABEL}.`}>
        <span className="absolute inset-y-0 left-1/2 w-px hl-border border-l" aria-hidden="true" />
        <span className="hl-hatch absolute inset-y-1 rounded border border-amber-500" style={{ left: `${pct(GAP_START)}%`, width: `${pct(GAP_END) - pct(GAP_START)}%` }} aria-hidden="true" />
        <span
          className="absolute inset-y-1.5 rounded-md"
          style={{ left: `${pct(stop.start)}%`, width: `${Math.max(1, pct(stop.end) - pct(stop.start))}%`, background: color }}
          aria-hidden="true"
        />
      </div>
      <div className="mt-1 flex justify-between text-[11px] hl-muted hl-tabular" aria-hidden="true">
        <span>2 jan 00:00</span>
        <span>3 jan 00:00</span>
        <span>3 jan 23:59</span>
      </div>
    </div>
  );
}

function DetailTab({ palette, selectedId, setSelectedId, reduced, notify, openMap }) {
  const t = THEMES[palette];
  const stop = STOPS.find((s) => s.id === selectedId) || STOPS[0];
  const track = TRACKS.get(stop.id);
  const idx = STOPS.findIndex((s) => s.id === stop.id);
  const go = (delta) => setSelectedId(STOPS[(idx + delta + STOPS.length) % STOPS.length].id);

  const chartPts = track.points.map((p) => ({ ...p }));
  if (stop.status === "desconhecida" && stop.edge === "fim") chartPts.push({ t: GAP_START, sog: null }, { t: GAP_END, sog: null });
  if (stop.status === "desconhecida" && stop.edge === "inicio") chartPts.unshift({ t: GAP_START, sog: null }, { t: GAP_START + MIN, sog: null });
  const domain = [Math.min(...chartPts.map((p) => p.t)), Math.max(...chartPts.map((p) => p.t))];
  const showGap = GAP_END > domain[0] && GAP_START < domain[1];
  const spanH = (domain[1] - domain[0]) / HOUR;
  const tickStep = spanH <= 3 ? 30 * MIN : spanH <= 7 ? HOUR : 2 * HOUR;
  const timeTicks = [];
  for (let x = Math.ceil(domain[0] / tickStep) * tickStep; x <= domain[1]; x += tickStep) timeTicks.push(x);

  const criteria = [
    { label: "Pelo menos 8 posições AIS", value: `${fmtInt(stop.positions)} posições` },
    { label: "Velocidade sobre o fundo de até 0,5 nó", value: `máximo de ${fmtDec(track.maxSog, 2)} nó` },
    { label: "Duração de pelo menos 30 min", value: `${isLowerBound(stop) ? "≥ " : ""}${fmtDuration(stop.durMin)}` },
    { label: "Intervalo de até 15 min entre posições", value: `maior intervalo ≈ ${fmtDuration(Math.max(1, Math.ceil(track.maxGapMin)))}` },
    { label: "Posições dentro de um raio de até 1 km", value: `≈ ${fmtInt(stop.radius)} m` },
  ];

  return (
    <div className="space-y-6">
      <Card className="p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label htmlFor="stop-picker" className="text-xs font-medium hl-muted sm:w-40">
            Parada detectada
          </label>
          <div className="flex flex-1 items-center gap-2">
            <Button size="icon" variant="secondary" aria-label="Parada anterior" onClick={() => go(-1)}>
              <ChevronLeft size={16} aria-hidden="true" />
            </Button>
            <div className="relative flex-1">
              <select
                id="stop-picker"
                value={stop.id}
                onChange={(e) => setSelectedId(Number(e.target.value))}
                className={`h-10 w-full appearance-none rounded-lg border hl-border-strong hl-surface pl-3 pr-9 text-sm font-medium hl-fg hl-tabular ${FOCUS}`}
              >
                {STOPS.map((s) => (
                  <option key={s.id} value={s.id}>
                    {`${s.code} — Navio ${s.mmsi} · ${STATUS_META[s.status].short}`}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 hl-muted" />
            </div>
            <Button size="icon" variant="secondary" aria-label="Próxima parada" onClick={() => go(1)}>
              <ChevronRight size={16} aria-hidden="true" />
            </Button>
          </div>
          <Button icon={MapIcon} onClick={() => openMap(stop.id)} className="justify-center">
            Ver no mapa
          </Button>
        </div>
      </Card>

      <div key={stop.id} className={`space-y-6 ${reduced ? "" : "hl-enter"}`}>
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5">
              <div>
                <p className="text-xs font-medium hl-muted">Resumo da parada</p>
                <h2 className="mt-0.5 text-xl font-semibold tracking-tight hl-tabular">
                  Parada {stop.code} · Navio {stop.mmsi}
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center rounded-full border hl-border px-2.5 py-1">
                  <StatusChip status={stop.status} palette={palette} />
                </span>
                <UnvalidatedBadge />
              </div>
            </div>
            <p className="px-5 pt-2 text-sm hl-muted">{statusDetail(stop)}</p>
            <div className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
              <MetricTile
                icon={Ship}
                label="Navio (MMSI)"
                value={stop.mmsi}
                hint={`Tipo informado no AIS: ${stop.type}`}
                info="O MMSI é transmitido pelo próprio navio e não garante identidade permanente."
              />
              <MetricTile icon={Clock} label="Início (UTC)" value={fmtDateTime(stop.start)} hint={stop.status !== "completa" && stop.edge === "inicio" ? "Início não observado" : "Primeira posição da parada"} />
              <MetricTile icon={Clock} label="Fim (UTC)" value={fmtDateTime(stop.end)} hint={stop.status !== "completa" && stop.edge === "fim" ? "Fim não observado" : "Última posição da parada"} />
              <MetricTile
                icon={Timer}
                label={isLowerBound(stop) ? "Duração mínima" : "Duração total"}
                value={`${isLowerBound(stop) ? "≥ " : ""}${fmtDuration(stop.durMin)}`}
                hint={isLowerBound(stop) ? "A duração real pode ser maior" : "Entre a primeira e a última posição"}
              />
              <MetricTile
                icon={Ruler}
                label="Raio aproximado de deriva"
                value={`≈ ${fmtInt(stop.radius)} m`}
                hint="Distância máxima até a posição central"
              />
              <MetricTile icon={MapPin} label="Posições AIS" value={fmtInt(stop.positions)} hint={`Posição central: ${fmtCoord(stop.lat, stop.lon)}`} />
            </div>
            <PeriodStrip stop={stop} palette={palette} />
          </Card>

          <Card className="hl-tone-warn border p-5">
            <div className="flex items-start gap-3">
              <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border hl-tone-warn">
                <AlertTriangle size={18} aria-hidden="true" />
              </span>
              <div>
                <h3 className="text-sm font-semibold">Não validada: detectada por algoritmo</h3>
                <p className="mt-1 text-sm leading-6">
                  Esta parada foi marcada porque o navio transmitiu velocidade muito baixa por tempo suficiente. Ela ainda não foi conferida com
                  nenhuma fonte independente e não informa o motivo nem a finalidade da parada.
                </p>
              </div>
            </div>
            <h4 className="mt-4 text-xs font-semibold uppercase tracking-wider">Critério do Método v0.2</h4>
            <ul className="mt-2 space-y-2">
              {criteria.map((c) => (
                <li key={c.label} className="flex items-start gap-2 text-sm">
                  <Check size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                  <span>
                    {c.label}
                    <span className="block text-xs opacity-90 hl-tabular">Nesta parada: {c.value}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <Card className="overflow-hidden">
            <CardHeader icon={Crosshair} title="Trajetória e aglomeração de posições" subtitle="Mini-mapa ampliado ao redor da posição central (ilustrativo)." />
            <div className="hl-theme-dark mx-5 mt-4 aspect-[52/34] overflow-hidden rounded-xl border border-white/10">
              <MiniMap stop={stop} track={track} reduced={reduced} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-2 px-5 py-4 text-xs hl-muted">
              <span className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-teal-400" aria-hidden="true" /> Posições durante a parada
              </span>
              <span className="inline-flex items-center gap-1.5">
                <svg width="18" height="8" aria-hidden="true">
                  <line x1="0" y1="4" x2="18" y2="4" stroke="#94a3b8" strokeWidth="2" strokeDasharray="4 3" />
                </svg>
                Trajetória antes e depois
              </span>
              <span className="inline-flex items-center gap-1.5">
                <svg width="12" height="12" aria-hidden="true">
                  <circle cx="6" cy="6" r="5" fill="none" stroke="#14b8a6" strokeWidth="1.5" strokeDasharray="3 2" />
                </svg>
                Raio aproximado de deriva
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Crosshair size={12} aria-hidden="true" /> Posição central
              </span>
            </div>
          </Card>

          <Card>
            <CardHeader icon={Gauge} title="Velocidade sobre o fundo (nós)" subtitle="A faixa destacada é a parada; a linha tracejada é o limite de 0,5 nó do método." />
            <div className="h-80 px-2 pb-2 pt-4" role="img" aria-label={`Velocidade ao longo do tempo para a parada ${stop.code}: cai para perto de zero durante a parada.`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartPts} margin={{ top: 8, right: 20, left: -8, bottom: 0 }}>
                  {svgPatterns(palette)}
                  <CartesianGrid stroke={t.chartGrid} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    scale="time"
                    domain={domain}
                    tickFormatter={fmtClock}
                    tick={{ fill: t.chartAxis, fontSize: 11 }}
                    axisLine={{ stroke: t.chartGrid }}
                    tickLine={false}
                    ticks={timeTicks}
                    interval={0}
                  />
                  <YAxis domain={[0, 10]} ticks={[0, 2, 4, 6, 8, 10]} tick={{ fill: t.chartAxis, fontSize: 11 }} axisLine={false} tickLine={false} unit=" nós" width={64} />
                  <ReferenceArea x1={Math.max(stop.start, domain[0])} x2={Math.min(stop.end, domain[1])} fill={t.accentSoft} fillOpacity={palette === "dark" ? 1 : 0.9} />
                  {showGap ? (
                    <ReferenceArea
                      x1={Math.max(GAP_START, domain[0])}
                      x2={Math.min(GAP_END, domain[1])}
                      fill={`url(#hl-hatch-${palette})`}
                      label={{ value: "Sem dados", position: "insideTop", fill: t.warnText, fontSize: 11 }}
                    />
                  ) : null}
                  {stop.status === "borda" && stop.edge === "inicio" ? (
                    <ReferenceLine x={WINDOW_START} stroke={t.warnText} strokeDasharray="4 3" label={{ value: "Início do período", position: "insideTopLeft", fill: t.warnText, fontSize: 11 }} />
                  ) : null}
                  {stop.status === "borda" && stop.edge === "fim" ? (
                    <ReferenceLine x={WINDOW_END - MIN} stroke={t.warnText} strokeDasharray="4 3" label={{ value: "Fim do período", position: "insideTopRight", fill: t.warnText, fontSize: 11 }} />
                  ) : null}
                  <ReferenceLine y={0.5} stroke={t.warnText} strokeDasharray="5 4" label={{ value: "limite 0,5 nó", position: "insideTopRight", fill: t.warnText, fontSize: 11 }} />
                  <RTooltip content={<SogTooltip />} />
                  <Line type="monotone" dataKey="sog" stroke={t.accent} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={!reduced} animationDuration={600} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="px-5 pb-5 text-xs hl-muted">
              Horários em UTC,{" "}
              {fmtDay(domain[0]) === fmtDay(domain[1]) ? `${fmtDay(domain[0])} de 2024` : `${fmtDay(domain[0])} a ${fmtDay(domain[1])} de 2024`}. A velocidade é a
              informada pelo próprio navio.
            </p>
          </Card>
        </div>

        <Card>
          <CardHeader icon={FileText} title="Origem e exportação" subtitle="De onde vem esta parada, em linguagem simples." />
          <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-2">
            <div className="space-y-3 text-sm leading-6">
              <p>
                Esta parada vem do arquivo de exemplo <span className="font-medium">{SOURCE_FILE}</span>, que contém registros fictícios criados para
                esta demonstração (não são registros AIS reais). O <span className="font-medium">Método v0.2</span> procurou trechos em que o navio
                ficou quase parado por pelo menos 30 minutos.
              </p>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
                <div>
                  <dt className="text-xs hl-muted">Arquivo de origem</dt>
                  <dd className="break-all">{SOURCE_FILE}</dd>
                </div>
                <div>
                  <dt className="text-xs hl-muted">Método</dt>
                  <dd>Método v0.2</dd>
                </div>
                <div>
                  <dt className="text-xs hl-muted">Processado em</dt>
                  <dd className="hl-tabular">{fmtDateTime(PROCESSED_AT)}</dd>
                </div>
                <div>
                  <dt className="text-xs hl-muted">Registros AIS analisados</dt>
                  <dd className="hl-tabular">{fmtInt(RECORDS.analysed)}</dd>
                </div>
              </dl>
            </div>
            <div className="space-y-3">
              <p className="text-xs hl-muted">Os arquivos levam o aviso de dados de exemplo, de parada não validada e de uso proibido para navegação.</p>
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                <DownloadButton
                  icon={FileSpreadsheet}
                  label="Baixar planilha (CSV)"
                  filename={`harborlens-parada-${pad2(stop.n)}.csv`}
                  mime="text/csv;charset=utf-8"
                  build={() => buildCsv(stop, track)}
                  notify={notify}
                />
                <DownloadButton
                  icon={MapIcon}
                  label="Baixar mapa (GeoJSON)"
                  filename={`harborlens-parada-${pad2(stop.n)}.geojson`}
                  mime="application/geo+json"
                  build={() => JSON.stringify(buildGeoJson(stop, track), null, 2)}
                  notify={notify}
                />
                <DownloadButton
                  icon={FileJson}
                  label="Baixar relatório (JSON)"
                  filename={`harborlens-parada-${pad2(stop.n)}-relatorio.json`}
                  mime="application/json"
                  build={() => JSON.stringify(buildReport(stop, track), null, 2)}
                  notify={notify}
                />
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Tab 4 — Origem e qualidade                                                 */
/* ------------------------------------------------------------------------- */

const QUALITY = [
  {
    title: "Integridade temporal",
    state: "ok",
    text: "Todos os horários estão em UTC, em ordem e dentro do período analisado. Nenhuma data futura ou inválida.",
  },
  {
    title: "Cobertura espacial",
    state: "warn",
    text: `A área de pesquisa é um retângulo aproximado, não o limite oficial do porto. ${fmtInt(RECORDS.outside)} registros ficaram fora dela e foram descartados.`,
  },
  {
    title: "Duplicidade de mensagens",
    state: "ok",
    text: `${fmtInt(RECORDS.duplicate)} mensagens repetidas (mesmo navio, horário e posição) foram removidas antes da análise.`,
  },
  {
    title: "Lacunas de sinal",
    state: "fail",
    text: `Sem dados em ${GAP_LABEL}. Duas paradas encostam nesse intervalo e têm início ou fim desconhecido. Nada foi preenchido por estimativa.`,
  },
  {
    title: "Valores fora do intervalo válido",
    state: "ok",
    text: `${fmtInt(RECORDS.invalid)} registros com identificador, coordenada ou velocidade inválidos foram descartados.`,
  },
  {
    title: "Confirmação independente das paradas",
    state: "warn",
    text: "Nenhuma das 12 paradas foi conferida com uma fonte independente. Todas permanecem não validadas.",
  },
];
const QUALITY_STATE = {
  ok: { label: "Aprovado", tone: "ok", icon: CheckCircle2, cls: "hl-text-ok" },
  warn: { label: "Atenção", tone: "warn", icon: AlertTriangle, cls: "hl-text-warn" },
  fail: { label: "Falha", tone: "danger", icon: XCircle, cls: "hl-text-danger" },
};

function QualityTab({ notify }) {
  const counts = QUALITY.reduce((acc, q) => ({ ...acc, [q.state]: (acc[q.state] || 0) + 1 }), {});
  const segs = [
    { label: "Registros AIS analisados", value: RECORDS.analysed, cls: "bg-teal-600" },
    { label: "Fora da área de pesquisa", value: RECORDS.outside, cls: "bg-amber-500" },
    { label: "Mensagens repetidas", value: RECORDS.duplicate, cls: "bg-sky-500" },
    { label: "Valores inválidos", value: RECORDS.invalid, cls: "bg-rose-500" },
  ];
  return (
    <div className="space-y-6">
      <div role="alert" className="flex flex-col gap-3 rounded-xl border hl-tone-warn p-5 sm:flex-row sm:items-start">
        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border hl-tone-warn">
          <AlertTriangle size={20} aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-base font-semibold">Uso dos dados em revisão</h2>
          <p className="mt-1 text-sm leading-6">
            A permissão para reutilizar e redistribuir a fonte destes dados ainda não foi aprovada. Até a revisão terminar, use os resultados
            apenas para pesquisa e não publique registros de navios individuais.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-1">
          <CardHeader icon={Database} title="Contagem de registros" subtitle="Cada número mostra a base sobre a qual foi calculado." />
          <div className="space-y-4 p-5">
            <div>
              <p className="text-xs hl-muted">Registros recebidos</p>
              <p className="text-3xl font-semibold hl-tabular">{fmtInt(RECORDS.received)}</p>
            </div>
            <div className="flex h-3 w-full overflow-hidden rounded-full hl-surface2" role="img" aria-label="Divisão dos registros recebidos">
              {segs.map((s) => (
                <span key={s.label} className={`${s.cls} h-full`} style={{ width: `${(s.value / RECORDS.received) * 100}%`, minWidth: 3 }} />
              ))}
            </div>
            <ul className="space-y-2 text-sm">
              {segs.map((s) => (
                <li key={s.label} className="flex items-center gap-2">
                  <span className={`inline-block h-2.5 w-2.5 rounded-sm ${s.cls}`} aria-hidden="true" />
                  <span>{s.label}</span>
                  <span className="ml-auto font-medium hl-tabular">{fmtInt(s.value)}</span>
                  <span className="w-14 text-right text-xs hl-muted hl-tabular">{fmtDec((s.value / RECORDS.received) * 100, 1)}%</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader
            icon={ShieldCheck}
            title="Verificações de qualidade"
            subtitle="Cada item combina ícone, cor e rótulo."
            actions={
              <div className="flex flex-wrap gap-1.5">
                {["ok", "warn", "fail"].map((k) => (
                  <Badge key={k} tone={QUALITY_STATE[k].tone} icon={QUALITY_STATE[k].icon}>
                    <span className="hl-tabular">{counts[k] || 0}</span> {QUALITY_STATE[k].label}
                  </Badge>
                ))}
              </div>
            }
          />
          <ul className="divide-y p-2 hl-border" role="list">
            {QUALITY.map((q) => {
              const s = QUALITY_STATE[q.state];
              const Icon = s.icon;
              return (
                <li key={q.title} className="hl-row flex items-start gap-3 rounded-lg border-0 px-3 py-3.5">
                  <Icon size={20} aria-hidden="true" className={`mt-0.5 shrink-0 ${s.cls}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold">{q.title}</h3>
                      <Badge tone={s.tone} icon={Icon}>
                        {s.label}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm leading-6 hl-muted">{q.text}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      <Accordion title="Detalhes técnicos" subtitle="Como reproduzir a análise de referência" icon={Keyboard}>
        <div className="space-y-4 text-sm">
          <p className="leading-6 hl-muted">
            Comando de referência do repositório. Ele executa o Método v0.2 sobre o arquivo sintético incluído no projeto. Os números desta
            demonstração são ilustrativos e não são a saída desse comando.
          </p>
          <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-950 text-slate-100">
            <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-2 text-xs text-slate-300">
              <span>Terminal</span>
            </div>
            <pre className="overflow-x-auto px-4 py-3 text-[13px] leading-6 hl-scroll">
              <code>{CLI_COMMAND}</code>
            </pre>
          </div>
          <CopyButton
            text={CLI_COMMAND}
            onResult={(ok) =>
              notify(ok ? { tone: "ok", title: "Comando copiado", body: "Cole no terminal para reproduzir a análise de referência." } : { tone: "danger", title: "Não foi possível copiar", body: "Selecione o texto do comando manualmente." })
            }
          />
          <div className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
            <div className="rounded-xl border hl-border hl-surface2 p-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider hl-muted">Parâmetros do Método v0.2</h4>
              <ul className="mt-2 space-y-1 hl-tabular">
                <li>Pelo menos 8 posições</li>
                <li>Velocidade de até 0,5 nó</li>
                <li>Duração de pelo menos 30 min</li>
                <li>Intervalo de até 15 min entre posições</li>
                <li>Raio de até 1 km</li>
              </ul>
            </div>
            <div className="rounded-xl border hl-border hl-surface2 p-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider hl-muted">Área de pesquisa</h4>
              <p className="mt-2 leading-6 hl-tabular">Longitude de 95,70° O a 94,20° O; latitude de 29,10° N a 30,10° N (WGS84).</p>
              <p className="mt-1 text-xs hl-muted">Retângulo de pesquisa, não é o limite oficial do porto.</p>
            </div>
          </div>
        </div>
      </Accordion>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Tab 5 — Guia visual                                                        */
/* ------------------------------------------------------------------------- */

const SWATCHES = [
  { key: "bg", name: "Fundo da página", on: null },
  { key: "surface", name: "Superfície (cards)", on: null },
  { key: "fg", name: "Texto principal", on: "surface" },
  { key: "muted", name: "Texto secundário", on: "surface" },
  { key: "accent", name: "Ação principal", on: "surface" },
  { key: "accentText", name: "Texto de destaque", on: "surface" },
  { key: "warnText", name: "Alerta (âmbar)", on: "surface" },
  { key: "dangerText", name: "Falha", on: "surface" },
  { key: "okText", name: "Aprovado", on: "surface" },
  { key: "violetText", name: "Desconhecido (roxo)", on: "surface" },
];

const GLOSSARY = [
  { tech: "stationary candidate", term: "Parada detectada", plain: "Trecho em que o navio ficou quase parado segundo o algoritmo. Não diz o motivo nem confirma o local." },
  { tech: "run", term: "Análise", plain: "Uma execução do método sobre um arquivo e um período." },
  { tech: "unvalidated", term: "Não validada", plain: "Ainda sem confirmação independente." },
  { tech: "analysis window", term: "Período analisado", plain: "Intervalo de datas e horas coberto pela análise, em UTC." },
  { tech: "left/right censored", term: "Começou ou terminou fora do período", plain: "A parada encosta no início ou no fim do período; a duração mostrada é um mínimo." },
  { tech: "unknown boundary", term: "Início/fim desconhecido", plain: "A parada encosta em um intervalo sem dados; não sabemos quando começou ou terminou." },
  { tech: "data gap", term: "Sem dados neste intervalo", plain: "Horário sem registros. Nada é estimado ou preenchido." },
  { tech: "MMSI", term: "Navio (MMSI)", plain: "Número transmitido pelo navio. Não garante identidade permanente." },
  { tech: "SOG", term: "Velocidade sobre o fundo (nós)", plain: "Velocidade informada pelo próprio navio em relação ao fundo." },
  { tech: "stationary-v0.2", term: "Método v0.2", plain: "Versão do critério de baixa velocidade usado para detectar as paradas." },
  { tech: "retained observations", term: "Registros AIS analisados", plain: "Registros que passaram pela limpeza e entraram na análise." },
  { tech: "centroid / radius", term: "Posição central / raio aproximado de deriva", plain: "Ponto médio das posições e a distância máxima até ele." },
  { tech: "rights review required", term: "Uso dos dados em revisão", plain: "A permissão de reutilização da fonte ainda não foi aprovada." },
];

function SwatchColumn({ name, themeKey, notify }) {
  const th = THEMES[themeKey];
  const [copied, setCopied] = useState(null);
  return (
    <div className={`hl-theme-${themeKey} hl-fg rounded-xl border p-4`} style={{ background: th.bg, borderColor: th.border }}>
      <h4 className="flex items-center gap-2 text-sm font-semibold">
        {themeKey === "light" ? <Sun size={14} aria-hidden="true" /> : <Moon size={14} aria-hidden="true" />}
        {name}
      </h4>
      <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {SWATCHES.map((s) => {
          const value = th[s.key];
          const ratio = s.on && isHex(value) && isHex(th[s.on]) ? contrast(value, th[s.on]) : null;
          return (
            <li key={s.key}>
              <button
                type="button"
                onClick={async () => {
                  const ok = await copyText(value);
                  setCopied(ok ? s.key : null);
                  if (ok) setTimeout(() => setCopied(null), 1600);
                  if (!ok) notify({ tone: "danger", title: "Não foi possível copiar a cor" });
                }}
                className={`flex w-full items-center gap-3 rounded-lg border p-2 text-left transition-all duration-200 hover:-translate-y-px ${FOCUS}`}
                style={{ background: th.surface, borderColor: th.border }}
                aria-label={`${s.name}, ${value}. Copiar valor`}
              >
                <span className="h-9 w-9 shrink-0 rounded-md border" style={{ background: value, borderColor: th.borderStrong }} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium">{s.name}</span>
                  <span className="block text-[11px] hl-muted hl-tabular">
                    {copied === s.key ? "Copiado!" : value}
                    {ratio ? ` · contraste ${fmtDec(ratio, 1)}:1` : ""}
                  </span>
                </span>
                {copied === s.key ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" className="hl-muted" />}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function GuideTab({ palette, reduced, notify }) {
  const mapChecks = [
    { k: "completa", name: "Círculo · completa" },
    { k: "borda", name: "Losango · parcial" },
    { k: "desconhecida", name: "Triângulo · desconhecido (roxo claro)" },
  ];
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Guia visual</h1>
            <p className="mt-1 text-sm hl-muted">Tokens, tipografia, espaçamentos e componentes usados no protótipo.</p>
          </div>
          <Badge tone={reduced ? "accent" : "neutral"} icon={Activity}>
            Movimento reduzido do sistema: {reduced ? "ativado (pulso e transições desligados)" : "desativado"}
          </Badge>
        </div>
      </Card>

      <section aria-labelledby="g-colors" className="space-y-3">
        <h2 id="g-colors" className="text-sm font-semibold">
          Tokens de cor
        </h2>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <SwatchColumn name="Tema claro" themeKey="light" notify={notify} />
          <SwatchColumn name="Tema escuro" themeKey="dark" notify={notify} />
        </div>
        <Card className="p-4">
          <h3 className="text-sm font-semibold">Marcadores do mapa sobre o fundo escuro</h3>
          <p className="mt-1 text-xs hl-muted">Elementos gráficos precisam de contraste mínimo de 3:1 com o fundo do mapa.</p>
          <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {mapChecks.map((m) => {
              const col = SHAPE_COLORS.dark[m.k];
              const r = Math.min(contrast(col, MAP.land), contrast(col, MAP.water));
              return (
                <li key={m.k} className="flex items-center gap-3 rounded-lg border border-white/10 p-3 text-slate-100" style={{ background: MAP.land }}>
                  <ShapeGlyph shape={STATUS_META[m.k].shape} color={col} size={20} />
                  <span className="text-xs">
                    <span className="block font-medium">{m.name}</span>
                    <span className="hl-tabular text-slate-300">
                      {col} · {fmtDec(r, 1)}:1 {r >= 3 ? "· atende 3:1" : "· abaixo de 3:1"}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-sm font-semibold">Hierarquia tipográfica · Inter</h2>
          <div className="mt-4 space-y-4">
            {[
              { cls: "text-[28px] leading-9 font-semibold tracking-tight", label: "Título de página · 28/36 · 600", sample: "Houston · 2–3 jan 2024" },
              { cls: "text-lg leading-7 font-semibold", label: "Título de seção · 18/28 · 600", sample: "Paradas detectadas por hora" },
              { cls: "text-sm leading-6", label: "Corpo · 14/24 · 400", sample: "Ainda sem confirmação independente." },
              { cls: "text-xs leading-5 font-medium", label: "Legenda · 12/20 · 500", sample: "Período analisado" },
              { cls: "text-2xl font-semibold hl-tabular", label: "Números tabulares · 24 · 600", sample: "4.820 · 14:32 UTC · 4h 15min" },
            ].map((r) => (
              <div key={r.label} className="border-b hl-border pb-3 last:border-0">
                <p className="text-[11px] font-medium uppercase tracking-wider hl-muted">{r.label}</p>
                <p className={`mt-1 ${r.cls}`}>{r.sample}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="text-sm font-semibold">Espaçamentos · grade de 8px</h2>
          <ul className="mt-4 space-y-2.5">
            {[8, 16, 24, 32, 40, 48, 64].map((px) => (
              <li key={px} className="flex items-center gap-3 text-xs">
                <span className="w-12 hl-tabular hl-muted">{px}px</span>
                <span className="h-3 rounded-sm bg-teal-500/70" style={{ width: px * 3 }} aria-hidden="true" />
                <span className="hl-muted hl-tabular">{px / 8}×</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs hl-muted">Cards usam cantos de 12px, respiro interno de 20–24px e sombras suaves.</p>
        </Card>
      </div>

      <Card className="p-5">
        <h2 className="text-sm font-semibold">Componentes</h2>
        <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider hl-muted">Botões</h3>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" icon={Download} onClick={() => notify({ tone: "info", title: "Botão principal", body: "Usado para a ação mais importante da tela." })}>
                Principal
              </Button>
              <Button icon={Eye} onClick={() => notify({ tone: "info", title: "Botão secundário" })}>
                Secundário
              </Button>
              <Button variant="ghost" icon={BookOpen} onClick={() => notify({ tone: "info", title: "Botão discreto" })}>
                Discreto
              </Button>
              <Button disabled>Indisponível</Button>
            </div>
            <h3 className="pt-2 text-xs font-semibold uppercase tracking-wider hl-muted">Selos de estado</h3>
            <div className="flex flex-wrap gap-2">
              <Badge tone="ok" icon={CheckCircle2}>
                Aprovado
              </Badge>
              <Badge tone="warn" icon={AlertTriangle}>
                Atenção
              </Badge>
              <Badge tone="danger" icon={XCircle}>
                Falha
              </Badge>
              <UnvalidatedBadge />
              <Tooltip content="Dados fictícios criados para demonstração">
                <Badge tone="violet" icon={Info} interactive>
                  Dados de exemplo
                </Badge>
              </Tooltip>
            </div>
            <h3 className="pt-2 text-xs font-semibold uppercase tracking-wider hl-muted">Situação da parada</h3>
            <div className="flex flex-col gap-1.5">
              {["completa", "borda", "desconhecida"].map((k) => (
                <StatusChip key={k} status={k} palette={palette} />
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider hl-muted">Card com destaque ao passar o mouse</h3>
            <Card hover className="p-4">
              <p className="text-xs hl-muted">Paradas detectadas</p>
              <p className="mt-1 text-2xl font-semibold hl-tabular">12</p>
              <p className="text-xs hl-muted">8 completas · 4 parciais ou desconhecidas</p>
            </Card>
            <h3 className="pt-2 text-xs font-semibold uppercase tracking-wider hl-muted">Banner de aviso</h3>
            <div className="flex items-start gap-2 rounded-xl border hl-tone-warn p-3 text-sm">
              <AlertTriangle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
              <span>Uso dos dados em revisão</span>
            </div>
            <h3 className="pt-2 text-xs font-semibold uppercase tracking-wider hl-muted">Linha de tabela</h3>
            <div className="overflow-hidden rounded-xl border hl-border">
              {STOPS.slice(0, 2).map((s) => (
                <div key={s.id} className="hl-row flex items-center gap-3 border-b hl-border px-3 py-2.5 text-sm last:border-0">
                  <span className="font-semibold hl-tabular">{s.code}</span>
                  <span className="hl-tabular">{s.mmsi}</span>
                  <span className="hl-muted hl-tabular">{fmtDuration(s.durMin)}</span>
                  <span className="ml-auto">
                    <StatusChip status={s.status} palette={palette} compact />
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-6 rounded-xl border border-dashed hl-border-strong p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Keyboard size={16} aria-hidden="true" /> Anel de foco
          </h3>
          <p className="mt-1 text-xs hl-muted">Use a tecla Tab para percorrer os elementos abaixo. O anel aparece só na navegação por teclado.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button variant="primary">Primeiro</Button>
            <Button>Segundo</Button>
            <input aria-label="Campo de exemplo" placeholder="Campo de texto" className={`h-10 rounded-lg border hl-border-strong hl-surface px-3 text-sm hl-fg ${FOCUS}`} />
            <a href="#g-colors" className={`rounded text-sm font-medium underline underline-offset-4 hl-accent-text ${FOCUS}`}>
              Link de exemplo
            </a>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader icon={BookOpen} title="Glossário de tradução" subtitle="Como os termos técnicos do sistema aparecem na plataforma." />
        <div className="relative mt-4 overflow-x-auto px-2 pb-3 hl-scroll">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr>
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium hl-muted">
                  Termo técnico do sistema
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium hl-muted">
                  Termo adotado na plataforma
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium hl-muted">
                  Explicação simples
                </th>
              </tr>
            </thead>
            <tbody>
              {GLOSSARY.map((g) => (
                <tr key={g.tech} className="hl-row">
                  <td className="border-t hl-border px-3 py-2.5">
                    <code className="rounded hl-surface2 px-1.5 py-0.5 text-xs">{g.tech}</code>
                  </td>
                  <td className="border-t hl-border px-3 py-2.5 font-medium">
                    <span className="inline-flex items-center gap-1.5">
                      <ArrowRight size={12} aria-hidden="true" className="hl-muted" />
                      {g.term}
                    </span>
                  </td>
                  <td className="border-t hl-border px-3 py-2.5 hl-muted">{g.plain}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Shell                                                                      */
/* ------------------------------------------------------------------------- */

const TABS = [
  { id: "visao", label: "Visão geral", icon: LayoutDashboard },
  { id: "mapa", label: "Mapa histórico", icon: MapIcon },
  { id: "detalhe", label: "Detalhe da parada", icon: Crosshair },
  { id: "qualidade", label: "Origem e qualidade", icon: ShieldCheck },
  { id: "guia", label: "Guia visual", icon: Palette },
];

export default function HarborLensPrototype() {
  const [theme, setTheme] = useState("light");
  const [tab, setTab] = useState("visao");
  const [selectedId, setSelectedId] = useState(1);
  const [mapTime, setMapTime] = useState(utc(2, 10, 30));
  const [menuOpen, setMenuOpen] = useState(false);
  const reduced = usePrefersReducedMotion();
  const toasts = useToasts();
  const tabRefs = useRef({});

  const palette = tab === "mapa" ? "dark" : theme;
  const css = useMemo(buildThemeCss, []);

  const changeTab = (id, focus = false) => {
    setTab(id);
    setMenuOpen(false);
    if (typeof window !== "undefined" && window.scrollTo) window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    if (focus && tabRefs.current[id]) tabRefs.current[id].focus();
  };
  const openStop = (id) => {
    setSelectedId(id);
    changeTab("detalhe");
  };
  const openMap = (id, time) => {
    if (id) {
      setSelectedId(id);
      const s = STOPS.find((x) => x.id === id);
      setMapTime(Math.max(WINDOW_START, s.start));
    }
    if (time) setMapTime(time);
    changeTab("mapa");
  };
  const onTabKey = (e) => {
    const i = TABS.findIndex((x) => x.id === tab);
    const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    changeTab(TABS[(next + TABS.length) % TABS.length].id, true);
  };
  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    if (tab === "mapa")
      toasts.push({ tone: "info", title: `Tema ${next === "light" ? "claro" : "escuro"} escolhido`, body: "O mapa histórico continua escuro; o tema vale para as outras abas." });
  };

  const current = TABS.find((x) => x.id === tab);

  return (
    <div className={`hl-root hl-theme-${palette} hl-bg hl-fg min-h-screen text-sm`}>
      <style>{css}</style>
      <a
        href="#hl-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-teal-700 focus:px-3 focus:py-2 focus:text-white"
      >
        Pular para o conteúdo
      </a>

      <header
        className="sticky z-40 border-b hl-border backdrop-blur-md"
        style={{ top: "env(safe-area-inset-top, 0px)", background: palette === "dark" ? "rgba(6,13,24,0.82)" : "rgba(255,255,255,0.85)" }}
      >
        <div className="mx-auto flex max-w-[1440px] items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-900 to-teal-600 text-white shadow-sm">
              <Waves size={18} aria-hidden="true" />
            </span>
            <div className="min-w-0 leading-tight">
              <p className="text-[15px] font-semibold tracking-tight">
                HarborLens <span className="block text-xs font-normal hl-muted sm:inline sm:text-[15px]">· by MirandasTech</span>
              </p>
              <p className="hidden text-xs hl-muted sm:block">Pesquisa histórica de tráfego marítimo · Houston</p>
            </div>
          </div>
          <Tooltip content="Dados fictícios criados para demonstração. Não são registros AIS reais." side="bottom">
            <Badge tone="violet" icon={Info} interactive className="ml-1">
              Dados de exemplo
            </Badge>
          </Tooltip>
          <div className="ml-auto flex items-center gap-2">
            <Tooltip
              side="bottom"
              content={
                tab === "mapa"
                  ? `Tema ${theme === "light" ? "claro" : "escuro"} escolhido. O mapa histórico permanece escuro.`
                  : `Alternar para tema ${theme === "light" ? "escuro" : "claro"}`
              }
            >
              <button
                type="button"
                onClick={toggleTheme}
                aria-label={`Alternar para tema ${theme === "light" ? "escuro" : "claro"}`}
                className={`inline-flex h-9 items-center gap-2 rounded-lg border hl-border-strong px-2.5 text-xs font-medium transition-all duration-200 hl-btn-secondary ${FOCUS}`}
              >
                {theme === "light" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
                <span className="hidden sm:inline">{theme === "light" ? "Claro" : "Escuro"}</span>
              </button>
            </Tooltip>
            <button
              type="button"
              className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border hl-border-strong md:hidden hl-btn-secondary ${FOCUS}`}
              aria-expanded={menuOpen}
              aria-controls="hl-mobile-nav"
              aria-label={menuOpen ? "Fechar menu" : "Abrir menu"}
              onClick={() => setMenuOpen((v) => !v)}
            >
              {menuOpen ? <X size={16} aria-hidden="true" /> : <Menu size={16} aria-hidden="true" />}
            </button>
          </div>
        </div>

        <nav className="mx-auto hidden max-w-[1440px] px-4 sm:px-6 md:block lg:px-8" aria-label="Seções">
          <div role="tablist" aria-label="Seções da plataforma" className="-mb-px flex gap-1 overflow-x-auto hl-scroll" onKeyDown={onTabKey}>
            {TABS.map((x) => {
              const active = x.id === tab;
              const Icon = x.icon;
              return (
                <button
                  key={x.id}
                  ref={(el) => (tabRefs.current[x.id] = el)}
                  id={`tab-${x.id}`}
                  role="tab"
                  type="button"
                  aria-selected={active}
                  aria-controls={`panel-${x.id}`}
                  tabIndex={active ? 0 : -1}
                  onClick={() => changeTab(x.id)}
                  className={`relative inline-flex shrink-0 items-center gap-2 rounded-t-lg px-3 py-2.5 text-sm font-medium transition-all duration-200 ${FOCUS} ${
                    active ? "hl-fg" : "hl-muted hover:opacity-80"
                  }`}
                >
                  <Icon size={16} aria-hidden="true" />
                  {x.label}
                  <span
                    aria-hidden="true"
                    className={`absolute inset-x-2 bottom-0 h-0.5 rounded-full transition-all duration-200 ${active ? "opacity-100" : "opacity-0"}`}
                    style={{ background: THEMES[palette].accent }}
                  />
                </button>
              );
            })}
          </div>
        </nav>

        {menuOpen ? (
          <nav id="hl-mobile-nav" className="hl-pop border-t hl-border px-4 py-2 md:hidden" aria-label="Seções">
            <ul className="space-y-1">
              {TABS.map((x) => {
                const Icon = x.icon;
                const active = x.id === tab;
                return (
                  <li key={x.id}>
                    <button
                      type="button"
                      aria-current={active ? "page" : undefined}
                      onClick={() => changeTab(x.id)}
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${FOCUS} ${active ? "hl-accent-soft hl-accent-text" : "hl-btn-ghost"}`}
                    >
                      <Icon size={16} aria-hidden="true" />
                      {x.label}
                      {active ? <Check size={14} aria-hidden="true" className="ml-auto" /> : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        ) : null}
        <div className="mx-auto flex max-w-[1440px] items-center gap-2 px-4 pb-2 text-xs hl-muted md:hidden">
          <current.icon size={14} aria-hidden="true" />
          {current.label}
        </div>
      </header>

      <main id="hl-main" className="mx-auto max-w-[1440px] px-4 pb-44 pt-6 sm:px-6 sm:pb-32 lg:px-8 lg:pb-28">
        <div
          key={tab}
          id={`panel-${tab}`}
          role="tabpanel"
          aria-labelledby={`tab-${tab}`}
          tabIndex={-1}
          className={reduced ? "" : "hl-enter"}
        >
          {tab === "visao" ? (
            <OverviewTab
              palette={palette}
              reduced={reduced}
              openStop={openStop}
              openMap={openMap}
              openQuality={() => changeTab("qualidade")}
              notify={toasts.push}
            />
          ) : null}
          {tab === "mapa" ? (
            <MapTab selectedId={selectedId} setSelectedId={setSelectedId} time={mapTime} setTime={setMapTime} reduced={reduced} openStop={openStop} />
          ) : null}
          {tab === "detalhe" ? (
            <DetailTab palette={palette} selectedId={selectedId} setSelectedId={setSelectedId} reduced={reduced} notify={toasts.push} openMap={openMap} />
          ) : null}
          {tab === "qualidade" ? <QualityTab notify={toasts.push} /> : null}
          {tab === "guia" ? <GuideTab palette={palette} reduced={reduced} notify={toasts.push} /> : null}
        </div>
      </main>

      <Toasts items={toasts.items} onDismiss={toasts.dismiss} />

      <div
        role="note"
        aria-label="Aviso de uso"
        className="fixed inset-x-0 bottom-0 z-50 border-t border-amber-300/50 bg-slate-950/95 text-amber-50 backdrop-blur-md"
        style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
      >
        <div className="mx-auto flex max-w-[1440px] items-start gap-3 px-4 py-3 sm:items-center sm:px-6 lg:px-8">
          <AlertTriangle size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-amber-300 sm:mt-0" />
          <p className="text-xs leading-5 sm:text-sm">{NOT_FOR_NAVIGATION}</p>
        </div>
      </div>
    </div>
  );
}
