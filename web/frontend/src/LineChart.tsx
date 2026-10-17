import { useEffect, useRef } from "react";
import type { Point } from "./useBackend";
import { WINDOW_S } from "./useBackend";

interface Props {
  title: string;
  unit: string;
  field: "wait" | "queue";
  fijo: Point[];
  rl: Point[];
}

// Grafica de lineas dibujada a mano en canvas: ultimos WINDOW_S segundos de tiempo simulado.
export default function LineChart({ title, unit, field, fijo, rl }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cv = ref.current!, parent = box.current!;
    const w = parent.clientWidth, h = parent.clientHeight, dpr = window.devicePixelRatio || 1;
    cv.width = w * dpr; cv.height = h * dpr;
    const g = cv.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const L = 44, R = 8, T = 8, B = 20;
    const tMax = Math.max(fijo[fijo.length - 1]?.t ?? 0, rl[rl.length - 1]?.t ?? 0, WINDOW_S);
    const tMin = tMax - WINDOW_S;
    let yMax = 1;
    for (const p of [...fijo, ...rl]) yMax = Math.max(yMax, p[field]);
    yMax *= 1.15;
    const X = (t: number) => L + ((t - tMin) / WINDOW_S) * (w - L - R);
    const Y = (v: number) => T + (1 - v / yMax) * (h - T - B);

    g.font = "12px system-ui, sans-serif"; g.fillStyle = "#8b95a7"; g.strokeStyle = "#232a38"; g.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const v = (yMax * i) / 4, y = Y(v);
      g.beginPath(); g.moveTo(L, y); g.lineTo(w - R, y); g.stroke();
      g.textAlign = "right"; g.fillText(v.toFixed(v < 10 ? 1 : 0), L - 6, y + 4);
    }
    g.textAlign = "center";
    for (let i = 0; i <= 5; i++) {
      const t = tMin + (WINDOW_S * i) / 5;
      g.fillText(`${Math.round(t / 60)}m`, X(t), h - 5);
    }
    const draw = (pts: Point[], color: string) => {
      if (pts.length < 2) return;
      g.strokeStyle = color; g.lineWidth = 2.5; g.lineJoin = "round";
      g.beginPath();
      pts.forEach((p, i) => (i ? g.lineTo(X(p.t), Y(p[field])) : g.moveTo(X(p.t), Y(p[field]))));
      g.stroke();
    };
    draw(fijo, "#ff9f43");
    draw(rl, "#2ee6a6");
  }, [fijo, rl, field]);

  return (
    <div className="chart">
      <div className="chart-title">{title} <small>({unit})</small>
        <span className="key"><i style={{ background: "#ff9f43" }} />Fijo<i style={{ background: "#2ee6a6" }} />RL</span>
      </div>
      <div className="chart-box" ref={box}><canvas ref={ref} /></div>
    </div>
  );
}
