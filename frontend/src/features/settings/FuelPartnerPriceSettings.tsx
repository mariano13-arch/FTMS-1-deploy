import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { hasCapability } from "../../services/auth";
import {
  getPartnerFuelPrices,
  recordPartnerFuelPrice,
  type PartnerFuelGrade,
  type PartnerFuelPriceSettings,
} from "../../services/fuelPartnerPrices";

const dateTime = (value:string) => new Date(value).toLocaleString("en-PH", {
  dateStyle:"medium", timeStyle:"short", timeZone:"Asia/Manila",
});

export default function FuelPartnerPriceSettings() {
  const { user } = useAuth();
  const canEdit = hasCapability(user, "SYSTEM_SETTINGS", "MANAGE_PRICES");
  const [data, setData] = useState<PartnerFuelPriceSettings|null>(null);
  const [grade, setGrade] = useState<PartnerFuelGrade|"">("");
  const [price, setPrice] = useState("");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (signal?:AbortSignal) => {
    try { setData(await getPartnerFuelPrices(signal)); setError(""); }
    catch (failure) {
      if (!(failure instanceof DOMException && failure.name === "AbortError"))
        setError("Preferred fuel partner prices are unavailable.");
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController(); void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  const submit = async (event:FormEvent) => {
    event.preventDefault();
    if (!grade || !price || !effectiveAt) return;
    setBusy(true); setError("");
    try {
      await recordPartnerFuelPrice({
        fuel_grade:grade, price_per_liter:price,
        effective_at:new Date(effectiveAt).toISOString(),
      });
      setGrade(""); setPrice(""); setEffectiveAt(""); await load();
    } catch { setError("Unable to record the Shell reference price."); }
    finally { setBusy(false); }
  };
  return <section className="settings-panel fuel-partner-settings">
    <header><div><h2>Preferred Fuel Partner</h2><p>Shell reference prices used for estimated dispatch fuel cost. They do not affect recommendation ranking.</p></div></header>
    {error && <div className="alert alert-danger m-2 py-1 px-2 small" role="alert">{error}</div>}
    {!data && !error && <p className="settings-loading">Loading Shell reference prices…</p>}
    {data && <>
      <div className="fuel-partner-products">
        {data.products.map((product) => <article key={product.fuel_grade}>
          <span><strong>{product.label}</strong><small>{product.vehicle_count} fleet vehicles</small></span>
          {product.current_price ? <span className="fuel-partner-price"><strong>₱{product.current_price.price_per_liter}/L</strong><small>Effective {dateTime(product.current_price.effective_at)}</small></span> : <span className="fuel-partner-price"><strong>Not configured</strong></span>}
          {product.history.length > 1 && <details><summary>Recent history</summary>{product.history.map((item) => <small key={item.id}>₱{item.price_per_liter}/L · {dateTime(item.effective_at)}</small>)}</details>}
        </article>)}
      </div>
      {canEdit && <form className="fuel-partner-form" onSubmit={submit}>
        <h3>Record Shell Reference Price</h3>
        <label>Fuel Grade<select required value={grade} onChange={(event) => setGrade(event.target.value as PartnerFuelGrade|"")}><option value="">Select grade</option>{data.products.map((product) => <option key={product.fuel_grade} value={product.fuel_grade}>{product.label}</option>)}</select></label>
        <label>Price per Liter (PHP)<input required inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} placeholder="Enter factual PHP/L price" /></label>
        <label>Effective Date / Time<input required type="datetime-local" max={new Date().toISOString().slice(0,16)} value={effectiveAt} onChange={(event) => setEffectiveAt(event.target.value)} /></label>
        <button className="btn btn-sm btn-primary" disabled={busy}>{busy ? "Recording…" : "Record Price"}</button>
      </form>}
    </>}
  </section>;
}
