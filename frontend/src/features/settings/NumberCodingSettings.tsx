import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { hasCapability } from "../../services/auth";
import { getVehicles, type Vehicle } from "../../services/vehicles";
import {
  getNumberCodingRules, getNumberCodingSuspensions, getVehicleCodingExemptions,
  saveNumberCodingRule, saveNumberCodingSuspension, saveVehicleCodingExemption,
  type NumberCodingRule, type NumberCodingSuspension, type VehicleCodingExemption,
} from "../../services/numberCoding";

type Tab = "rules" | "suspensions" | "exemptions";
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const phDateTime = (value:string) => new Date(value).toLocaleString("en-PH", { timeZone:"Asia/Manila" });
const localInput = (value:string) => value ? value.slice(0, 16) : "";
const activeBadge = (active:boolean) => <span className={`settings-status settings-status--${active ? "configured" : "disabled"}`}>{active ? "Active" : "Inactive"}</span>;

const blankRule = { authority:"", jurisdiction:"", weekday:"0", digits:"", start_time:"", end_time:"", effective_from:"", effective_until:"", source_reference:"", notes:"", is_active:true };
const blankPeriod = { authority:"", jurisdiction:"", starts_at:"", ends_at:"", reason:"", source_reference:"", is_active:true };
const blankExemption = { ...blankPeriod, vehicle:"" };

export default function NumberCodingSettings() {
  const { user } = useAuth();
  const canEdit = hasCapability(user, "SYSTEM_SETTINGS", "MANAGE_NUMBER_CODING");
  const [tab, setTab] = useState<Tab>("rules");
  const [rules, setRules] = useState<NumberCodingRule[]>([]);
  const [suspensions, setSuspensions] = useState<NumberCodingSuspension[]>([]);
  const [exemptions, setExemptions] = useState<VehicleCodingExemption[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [ruleForm, setRuleForm] = useState(blankRule);
  const [periodForm, setPeriodForm] = useState(blankPeriod);
  const [exemptionForm, setExemptionForm] = useState(blankExemption);
  const [editing, setEditing] = useState<number|null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (signal?:AbortSignal) => {
    try {
      const [nextRules, nextSuspensions, nextExemptions, vehiclePage] = await Promise.all([
        getNumberCodingRules(signal), getNumberCodingSuspensions(signal),
        getVehicleCodingExemptions(signal), getVehicles("page_size=100", signal),
      ]);
      setRules(nextRules); setSuspensions(nextSuspensions); setExemptions(nextExemptions);
      setVehicles(vehiclePage.results); setError("");
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) setError("Number Coding settings are unavailable.");
    }
  }, []);
  // The initial API synchronization intentionally populates local view state.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  const reset = (nextTab:Tab = tab) => {
    setEditing(null); setShowForm(false); setError(""); setTab(nextTab);
    setRuleForm(blankRule); setPeriodForm(blankPeriod); setExemptionForm(blankExemption);
  };
  const submit = async (event:FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (tab === "rules") {
        const digits = ruleForm.digits.split(",").map((item) => Number(item.trim())).filter((item) => Number.isInteger(item));
        if (!digits.length || digits.some((digit) => digit < 0 || digit > 9)) throw new Error("Enter comma-separated digits from 0 to 9.");
        if ((ruleForm.start_time || ruleForm.end_time) && (!ruleForm.start_time || !ruleForm.end_time || ruleForm.start_time >= ruleForm.end_time)) throw new Error("Enter a valid time window with the end after the start.");
        await saveNumberCodingRule({ ...ruleForm, weekday:Number(ruleForm.weekday), restricted_last_digits:digits, start_time:ruleForm.start_time || null, end_time:ruleForm.end_time || null, effective_until:ruleForm.effective_until || null, digits:undefined }, editing ?? undefined);
      } else if (tab === "suspensions") {
        if (periodForm.starts_at >= periodForm.ends_at) throw new Error("End must be after start.");
        await saveNumberCodingSuspension(periodForm, editing ?? undefined);
      } else {
        if (!exemptionForm.vehicle) throw new Error("Select a real FTMS vehicle.");
        if (exemptionForm.starts_at >= exemptionForm.ends_at) throw new Error("End must be after start.");
        await saveVehicleCodingExemption({ ...exemptionForm, vehicle:Number(exemptionForm.vehicle) }, editing ?? undefined);
      }
      reset(); await load();
    } catch (cause) { setError(cause instanceof Error && !cause.message.startsWith("API request") ? cause.message : "Unable to save Number Coding configuration."); }
    finally { setBusy(false); }
  };
  const toggle = async (id:number, active:boolean) => {
    setBusy(true); setError("");
    try {
      if (tab === "rules") await saveNumberCodingRule({ is_active:!active }, id);
      else if (tab === "suspensions") await saveNumberCodingSuspension({ is_active:!active }, id);
      else await saveVehicleCodingExemption({ is_active:!active }, id);
      await load();
    } catch { setError("Unable to update Number Coding status."); } finally { setBusy(false); }
  };
  const editRule = (item:NumberCodingRule) => { setEditing(item.id); setShowForm(true); setRuleForm({ authority:item.authority, jurisdiction:item.jurisdiction, weekday:String(item.weekday), digits:item.restricted_last_digits.join(", "), start_time:item.start_time?.slice(0, 5) ?? "", end_time:item.end_time?.slice(0, 5) ?? "", effective_from:item.effective_from, effective_until:item.effective_until ?? "", source_reference:item.source_reference, notes:item.notes, is_active:item.is_active }); };
  const editSuspension = (item:NumberCodingSuspension) => { setEditing(item.id); setShowForm(true); setPeriodForm({ authority:item.authority, jurisdiction:item.jurisdiction, starts_at:localInput(item.starts_at), ends_at:localInput(item.ends_at), reason:item.reason, source_reference:item.source_reference, is_active:item.is_active }); };
  const editExemption = (item:VehicleCodingExemption) => { setEditing(item.id); setShowForm(true); setExemptionForm({ vehicle:String(item.vehicle), authority:item.authority, jurisdiction:item.jurisdiction, starts_at:localInput(item.starts_at), ends_at:localInput(item.ends_at), reason:item.reason, source_reference:item.source_reference, is_active:item.is_active }); };
  const actions = (id:number, active:boolean, edit:()=>void) => canEdit ? <div className="number-coding-actions"><button type="button" onClick={edit}>Edit</button><button type="button" disabled={busy} onClick={() => void toggle(id, active)}>{active ? "Deactivate" : "Activate"}</button></div> : null;
  return <section className="settings-panel number-coding-settings"><header><div><h2>Number Coding</h2><p>Maintain configured weekly restrictions, official suspensions, and verified exemptions.</p></div>{canEdit && <button type="button" className="btn btn-sm btn-primary" onClick={() => { reset(tab); setShowForm(true); }}>Add {tab === "rules" ? "Rule" : tab === "suspensions" ? "Suspension" : "Exemption"}</button>}</header>
    <nav className="number-coding-tabs" aria-label="Number Coding sections">{([['rules','Weekly Rules'],['suspensions','Temporary Suspensions'],['exemptions','Vehicle Exemptions']] as const).map(([key, name]) => <button type="button" className={tab === key ? "active" : ""} key={key} onClick={() => reset(key)}>{name}</button>)}</nav>
    {error && <div className="alert alert-danger m-2 py-1 px-2 small" role="alert">{error}</div>}
    {canEdit && showForm && <form className="number-coding-form" onSubmit={submit}>
      {tab === "rules" ? <><label>Weekday<select value={ruleForm.weekday} onChange={(e) => setRuleForm({...ruleForm,weekday:e.target.value})}>{weekdays.map((day,index) => <option value={index} key={day}>{day}</option>)}</select></label><label>Restricted Digits<input required value={ruleForm.digits} onChange={(e) => setRuleForm({...ruleForm,digits:e.target.value})} placeholder="1, 2" /></label><label>Start Time<input type="time" value={ruleForm.start_time} onChange={(e) => setRuleForm({...ruleForm,start_time:e.target.value})} /></label><label>End Time<input type="time" value={ruleForm.end_time} onChange={(e) => setRuleForm({...ruleForm,end_time:e.target.value})} /></label><label>Effective From<input required type="date" value={ruleForm.effective_from} onChange={(e) => setRuleForm({...ruleForm,effective_from:e.target.value})} /></label><label>Effective Until<input type="date" value={ruleForm.effective_until} onChange={(e) => setRuleForm({...ruleForm,effective_until:e.target.value})} /></label><label>Authority<input required value={ruleForm.authority} onChange={(e) => setRuleForm({...ruleForm,authority:e.target.value})} /></label><label>Jurisdiction<input required value={ruleForm.jurisdiction} onChange={(e) => setRuleForm({...ruleForm,jurisdiction:e.target.value})} /></label><label>Source / Reference<input value={ruleForm.source_reference} onChange={(e) => setRuleForm({...ruleForm,source_reference:e.target.value})} /></label><label>Notes<input value={ruleForm.notes} onChange={(e) => setRuleForm({...ruleForm,notes:e.target.value})} /></label><p className="number-coding-help">Configure the official applicable time window before activating this rule.</p></> : tab === "suspensions" ? <PeriodFields value={periodForm} onChange={setPeriodForm} /> : <><label>Vehicle<select required value={exemptionForm.vehicle} onChange={(e) => setExemptionForm({...exemptionForm,vehicle:e.target.value})}><option value="">Select vehicle</option>{vehicles.map((vehicle) => <option key={vehicle.id} value={vehicle.id}>{vehicle.display_name} · {vehicle.plate_number}</option>)}</select></label><PeriodFields value={exemptionForm} onChange={setExemptionForm} /></>}
      <div className="number-coding-form-actions"><button className="btn btn-sm btn-primary" disabled={busy}>{busy ? "Saving…" : editing ? "Save Changes" : "Create"}</button><button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => reset()}>Cancel</button></div>
    </form>}
    <div className="number-coding-table-wrap"><table><thead><tr>{tab === "rules" ? <><th>Weekday</th><th>Restricted Digits</th><th>Time Window</th><th>Effective Dates</th><th>Authority / Jurisdiction</th></> : tab === "suspensions" ? <><th>Authority / Jurisdiction</th><th>Start / End</th><th>Reason</th><th>Source / Reference</th></> : <><th>Vehicle</th><th>Start / End</th><th>Authority</th><th>Reason / Reference</th></>}<th>Status</th><th>Actions</th></tr></thead><tbody>
      {tab === "rules" && rules.map((item) => <tr key={item.id}><td>{item.weekday_label}</td><td>{item.restricted_last_digits.join(", ")}</td><td>{item.start_time && item.end_time ? `${item.start_time.slice(0,5)}–${item.end_time.slice(0,5)}` : "Not configured"}</td><td>{item.effective_from}<small>{item.effective_until ?? "No end date"}</small></td><td>{item.authority}<small>{item.jurisdiction}</small></td><td>{activeBadge(item.is_active)}</td><td>{actions(item.id,item.is_active,()=>editRule(item))}</td></tr>)}
      {tab === "suspensions" && suspensions.map((item) => <tr key={item.id}><td>{item.authority}<small>{item.jurisdiction}</small></td><td>{phDateTime(item.starts_at)}<small>{phDateTime(item.ends_at)}</small></td><td>{item.reason}</td><td>{item.source_reference}</td><td>{activeBadge(item.is_active)}</td><td>{actions(item.id,item.is_active,()=>editSuspension(item))}</td></tr>)}
      {tab === "exemptions" && exemptions.map((item) => <tr key={item.id}><td>{item.vehicle_display_name}<small>{item.plate_number}</small></td><td>{phDateTime(item.starts_at)}<small>{phDateTime(item.ends_at)}</small></td><td>{item.authority}</td><td>{item.reason}<small>{item.source_reference}</small></td><td>{activeBadge(item.is_active)}</td><td>{actions(item.id,item.is_active,()=>editExemption(item))}</td></tr>)}
    </tbody></table></div>
  </section>;
}

type Period = typeof blankPeriod;
function PeriodFields<T extends Period>({ value, onChange }:{ value:T; onChange:(value:T)=>void }) {
  return <><label>Authority<input required value={value.authority} onChange={(e) => onChange({...value,authority:e.target.value})} /></label><label>Jurisdiction<input required value={value.jurisdiction} onChange={(e) => onChange({...value,jurisdiction:e.target.value})} /></label><label>Start<input required type="datetime-local" value={value.starts_at} onChange={(e) => onChange({...value,starts_at:e.target.value})} /></label><label>End<input required type="datetime-local" value={value.ends_at} onChange={(e) => onChange({...value,ends_at:e.target.value})} /></label><label>Reason<input required value={value.reason} onChange={(e) => onChange({...value,reason:e.target.value})} /></label><label>Source / Reference<input required value={value.source_reference} onChange={(e) => onChange({...value,source_reference:e.target.value})} /></label></>;
}
