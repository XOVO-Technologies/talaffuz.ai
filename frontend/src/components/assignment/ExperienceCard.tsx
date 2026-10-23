import type { AssignmentExperience } from "../../types";

interface Props {
  value: AssignmentExperience;
  disabled: boolean;
  onChange: (next: AssignmentExperience) => void;
}

const QUESTIONS: { key: "hardest" | "helpful" | "issues" | "redo" | "learned"; title: string; hint: string }[] = [
  { key: "hardest", title: "3. What was the hardest part, and why?", hint: "One to three lines." },
  { key: "helpful", title: "4. What helped the most?", hint: "A tool, a method or a habit." },
  { key: "issues", title: "5. Any gaps or problems in your dataset?", hint: "For example background noise, unclear words, or spelling differences." },
  { key: "redo", title: "6. What would you do differently next time?", hint: "One to three lines." },
  { key: "learned", title: "7. What did you learn from this assignment?", hint: "One to three lines." },
];

export function ExperienceCard({ value, disabled, onChange }: Props) {
  const set = <K extends keyof AssignmentExperience>(key: K, next: AssignmentExperience[K]) => onChange({ ...value, [key]: next });
  return (
    <fieldset className="settings" disabled={disabled}>
      <section className="group">
        <h3>1. How long did it take, in hours (an estimate)?</h3>
        <div className="grid">
          <label className="field">
            <span>Recording</span>
            <input type="text" value={value.hours_recording} maxLength={60} placeholder="For example 6 hours" onChange={(e) => set("hours_recording", e.target.value)} />
          </label>
          <label className="field">
            <span>Cutting audio (sentences and words)</span>
            <input type="text" value={value.hours_cutting} maxLength={60} placeholder="For example 4 hours" onChange={(e) => set("hours_cutting", e.target.value)} />
          </label>
          <label className="field">
            <span>Text and metadata</span>
            <input type="text" value={value.hours_text} maxLength={60} placeholder="For example 5 hours" onChange={(e) => set("hours_text", e.target.value)} />
          </label>
        </div>
      </section>
      <section className="group">
        <h3>2. How hard was it? (1 is very easy, 5 is very hard)</h3>
        <div className="grid">
          <label className="field">
            <span>Difficulty</span>
            <select value={value.difficulty ?? ""} onChange={(e) => set("difficulty", e.target.value === "" ? null : Number(e.target.value))}>
              <option value="">Choose</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="field wide">
            <span>Why (optional)</span>
            <input type="text" value={value.difficulty_note} maxLength={400} onChange={(e) => set("difficulty_note", e.target.value)} />
          </label>
        </div>
      </section>
      {QUESTIONS.map((q) => (
        <label key={q.key} className="field wide">
          <span>{q.title}</span>
          <textarea rows={3} value={value[q.key]} maxLength={600} placeholder={q.hint} onChange={(e) => set(q.key, e.target.value)} />
        </label>
      ))}
      <p className="hint">Answer in Roman Urdu or English, in your own words. These answers are saved into EXPERIENCE.md exactly as you write them.</p>
    </fieldset>
  );
}
