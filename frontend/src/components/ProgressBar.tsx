interface Props {
  value: number | null | undefined; // 0..1, or null/undefined for "busy, unknown length"
  label: string;
  thick?: boolean;
}

export function ProgressBar({ value, label, thick }: Props) {
  const known = typeof value === "number";
  const pct = known ? Math.max(0, Math.min(1, value)) * 100 : 0;
  return (
    <div
      className={`bar${thick ? " thick" : ""}${known ? "" : " indeterminate"}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={known ? Math.round(pct) : undefined}
    >
      <i style={{ width: `${pct}%` }} />
    </div>
  );
}
