import { useEffect, useState } from "react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import { getFuelModelInfo, getFuelReadiness, type FuelModelInfo, type FuelReadiness } from "../fuel-analytics/api";
import { getMaintenanceModelInfo, getMaintenanceReadiness, type MaintenanceModelInfo, type MaintenanceReadiness } from "../maintenance/api";
import SettingsLayout, { SettingsStatus } from "./SettingsLayout";
import "./SettingsPage.css";

type Models = { fuel: FuelModelInfo; fuelReadiness: FuelReadiness; maintenance: MaintenanceModelInfo; maintenanceReadiness: MaintenanceReadiness };
const YesNo = ({ value }: { value: boolean }) => <span className={value ? "settings-yes" : "settings-no"}>{value ? "Yes" : "No"}</span>;

export default function AiModelsSettingsPage() {
  const [models, setModels] = useState<Models | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getFuelModelInfo(controller.signal), getFuelReadiness(controller.signal), getMaintenanceModelInfo(controller.signal), getMaintenanceReadiness(controller.signal)])
      .then(([fuel, fuelReadiness, maintenance, maintenanceReadiness]) => { setModels({ fuel, fuelReadiness, maintenance, maintenanceReadiness }); setState("ready"); })
      .catch((error) => { if (!(error instanceof DOMException && error.name === "AbortError")) setState("error"); });
    return () => controller.abort();
  }, []);
  return <SettingsLayout>{state === "loading" ? <LoadingIndicator variant="card" message="Loading AI / ML model status…" /> : state === "error" || !models ? <section className="settings-panel settings-error" role="alert"><strong>Model status unavailable</strong><p>Fuel and maintenance technical information could not be loaded.</p></section> : <div className="settings-models">
    <section className="settings-panel"><header><div><small>AI / ML model status</small><h2>Fuel Analytics Model</h2></div><SettingsStatus value={models.fuel.availability === "available" ? "Available" : "Blocked"} /></header><dl>
      <div><dt>Identity / version</dt><dd>{models.fuel.model_name} · {models.fuel.model_version}</dd></div><div><dt>Model type</dt><dd>{models.fuel.model_type}</dd></div><div><dt>Model role</dt><dd>{models.fuel.model_role}</dd></div><div><dt>Target</dt><dd>{models.fuel.target}</dd></div><div><dt>Prediction semantics</dt><dd>{models.fuel.prediction_semantics}</dd></div><div><dt>Input readiness</dt><dd>{models.fuelReadiness.inputs.filter((item) => item.status === "available").length} / {models.fuelReadiness.inputs.length} available</dd></div>
    </dl><div className="settings-features">{models.fuel.features.map((feature) => <span key={feature}>{feature}</span>)}</div><p className="settings-note">{models.fuel.accuracy_note}</p></section>
    <section className="settings-panel"><header><div><small>AI / ML model status</small><h2>Maintenance Prediction Model</h2></div><SettingsStatus value={models.maintenanceReadiness.production_ready ? "Available" : "Blocked"} /></header><dl>
      <div><dt>Deployment state</dt><dd>{models.maintenanceReadiness.deployment_state}</dd></div><div><dt>Production ready</dt><dd><YesNo value={models.maintenanceReadiness.production_ready} /></dd></div><div><dt>Direct OBD feed allowed</dt><dd><YesNo value={models.maintenanceReadiness.direct_obd_feed_allowed} /></dd></div><div><dt>Unit scaling verified</dt><dd><YesNo value={models.maintenanceReadiness.unit_scaling_verified} /></dd></div><div><dt>Vehicle compatibility verified</dt><dd><YesNo value={models.maintenanceReadiness.vehicle_compatibility_verified} /></dd></div><div><dt>Identity / version</dt><dd>{models.maintenance.model_name} · {models.maintenance.model_version}</dd></div><div><dt>Model type</dt><dd>XGBoost binary classification</dd></div><div><dt>Threshold</dt><dd>{models.maintenance.decision_threshold}</dd></div><div><dt>Score semantics</dt><dd>{models.maintenance.score_semantics}</dd></div>
    </dl><div className="settings-features">{models.maintenance.features.map((feature) => <span key={feature}>{feature}</span>)}</div><p className="settings-blocking"><strong>Blocking reason:</strong> {models.maintenanceReadiness.blocking_reason}</p><p className="settings-note"><strong>Human review:</strong> Mechanic confirmation required. No specific component diagnosis or remaining useful life estimation.</p></section>
  </div>}</SettingsLayout>;
}
