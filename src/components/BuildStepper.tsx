const STEPS = [
  { n: 1, label: "Scan", hint: "Read the website" },
  { n: 2, label: "Review", hint: "Confirm details" },
  { n: 3, label: "Generate", hint: "Build the stack" },
  { n: 4, label: "Ready", hint: "Try the stack" },
];

// A clear, shared progress indicator across the build phase so each step is
// labeled and the user always knows where they are.
export default function BuildStepper({ current }: { current: number }) {
  return (
    <div className="stepper">
      {STEPS.map((s, i) => {
        const state = s.n < current ? "done" : s.n === current ? "active" : "todo";
        return (
          <div className="stepper-item" key={s.n}>
            <div className={`stepper-node ${state}`}>{state === "done" ? "✓" : s.n}</div>
            <div className="stepper-text">
              <div className="stepper-label">{s.label}</div>
              <div className="stepper-hint">{s.hint}</div>
            </div>
            {i < STEPS.length - 1 && <div className={`stepper-line ${s.n < current ? "done" : ""}`} />}
          </div>
        );
      })}
    </div>
  );
}
