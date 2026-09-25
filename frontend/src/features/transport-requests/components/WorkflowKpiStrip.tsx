import type { Summary } from "../types";

export default function WorkflowKpiStrip({ summary }: { summary: Summary | null }) {
  if (!summary) return null;
  const cards = [
    ["Awaiting decision", summary.for_approval],
    ["Needs details", summary.needs_more_details],
    ["Dispatch queue", summary.dispatch_queue],
    ["Unassigned", summary.approved_unassigned],
    ["Vehicle assigned", summary.approved_assigned],
    ["Ready for dispatch", summary.ready_for_dispatch],
    ["Scheduled today", summary.scheduled_today],
    ["High priority", summary.high_priority],
  ] as const;

  return (
    <section className="workflow-summary" aria-label="Overall Workflow">
      <div
        className="kpi-grid kpi-grid--wide kpi-grid--workspace"
        aria-label="Global transport request status summary"
      >
        {cards.map(([name, value]) => (
          <article className="kpi-card" key={name}>
            <strong>{value}</strong>
            <span>{name}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
