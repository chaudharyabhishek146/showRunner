"use client";

import type { Plan, StepStatus } from "@/lib/types";

interface Props {
  plan: Plan | null;
  stepStatus: Record<number, StepStatus>;
  activeStep: number | null;
}

/** The rail across the top: where the demo is, and what's still coming. */
export default function StepProgress({ plan, stepStatus, activeStep }: Props) {
  if (!plan) {
    return (
      <div className="progress progress--empty">
        <span className="progress__placeholder">
          No walkthrough loaded yet.
        </span>
      </div>
    );
  }

  const done = plan.steps.filter((s) => stepStatus[s.id] === "done").length;

  return (
    <div className="progress">
      <div className="progress__meta">
        <span className="progress__workflow">{plan.workflow_name}</span>
        <span className="progress__count">
          {done} / {plan.steps.length} complete
        </span>
      </div>

      <ol className="progress__steps">
        {plan.steps.map((step) => {
          const status = stepStatus[step.id] ?? "pending";
          const isActive = step.id === activeStep;
          return (
            <li
              key={step.id}
              className={`pstep pstep--${status}${isActive ? " pstep--active" : ""}`}
              title={step.goal}
            >
              <span className="pstep__dot">
                {status === "done" ? "✓" : step.id}
              </span>
              <span className="pstep__label">{step.title}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
