import type { Toast } from "./types";

// Avisos pequenos: confirmaciones de comandos (ack), errores del servidor y "cargando...".
export default function Toasts({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  if (!toasts.length) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} onClick={() => onDismiss(t.id)}>
          {t.kind === "loading" && <span className="spin" />}
          {t.text}
        </div>
      ))}
    </div>
  );
}
