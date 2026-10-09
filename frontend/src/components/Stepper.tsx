export interface StepInfo {
  id: string; // matches the section id "step-<id>"
  label: string;
  note: string;
  state: "done" | "current" | "todo";
}

export function Stepper({ steps, onSelect }: { steps: StepInfo[]; onSelect?: (id: string) => void }) {
  return (
    <nav aria-label="Progress">
      <ol className="stepper">
        {steps.map((s, i) => (
          <li key={s.id}>
            <button
              className={`step ${s.state}`}
              aria-current={s.state === "current" ? "step" : undefined}
              onClick={() => {
                onSelect?.(s.id);
                document.getElementById(`step-${s.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              <span className="step-dot">{s.state === "done" ? "✓" : i + 1}</span>
              <span className="step-text">
                <strong>{s.label}</strong>
                <span>{s.note}</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
