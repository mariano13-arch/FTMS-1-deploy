import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, Redirect, Route, Switch, useHistory, useParams } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import LiveVehicleMap from "../../components/LiveVehicleMap";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import { StatusBadge, vehicleStatusTone, freshnessTone } from "../../components/common/StatusBadge";
import { useVehicleStatus } from "../../hooks/useVehicleStatus";
import { useConfirmModal } from "../../hooks/useConfirmModal";
import { humanize } from "../../utils/text";
import { ApiError, apiBaseUrl } from "../../services/api";
import type { Role } from "../../services/auth";
import { changeVehicleStatus, createVehicle, createVehicleDocument, createVehicleInspection, documentTypes, editVehicle, fuelTypes, getVehicle, getVehicleDocuments, getVehicleInspections, getVehicles, inspectionConditions, inspectionResults, inspectionTypes, ownershipTypes, transmissionTypes, vehicleTypes, type DocumentPage, type InspectionPage, type Vehicle, type VehicleInspection } from "../../services/vehicles";

const canEdit = (role: Role) => role === "SUPER_ADMIN" || role === "FLEET_MANAGER";

function VehicleList() {
  const { user } = useAuth(); const [page, setPage] = useState<Awaited<ReturnType<typeof getVehicles>> | null>(null);
  const [error, setError] = useState(false); const [query, setQuery] = useState("");
  const [search, setSearch] = useState(""); const [activeFilter, setActiveFilter] = useState(""); const [typeFilter, setTypeFilter] = useState("");
  const [selectedDeviceId, setSelectedDeviceId] = useState(""); const [drawerMode, setDrawerMode] = useState<"overview" | "inspections" | "documents" | "add" | "edit">("overview"); const [menuDeviceId, setMenuDeviceId] = useState("");
  const [creating, setCreating] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false); const [nextPageError, setNextPageError] = useState(false);
  const [statusBusy, setStatusBusy] = useState(""); const [statusError, setStatusError] = useState("");
  const { confirm: confirmAction, ConfirmModalComponent } = useConfirmModal();
  const statusController = useRef<AbortController | null>(null);
  const nextPageController = useRef<AbortController | null>(null); const requestGeneration = useRef(0);
  const tableWrapRef = useRef<HTMLDivElement>(null); const loadMoreRef = useRef<HTMLDivElement>(null);
  const queryRef = useRef(query); const lastLiveSearch = useRef(search);
  useEffect(() => { queryRef.current = query; }, [query]);
  useEffect(() => {
    const generation = ++requestGeneration.current;
    nextPageController.current?.abort(); nextPageController.current = null;
    const controller = new AbortController();
    getVehicles(query, controller.signal).then(result => { if (generation === requestGeneration.current) setPage(result); }).catch((reason: unknown) => {
      if (generation === requestGeneration.current && !(reason instanceof DOMException && reason.name === "AbortError")) setError(true);
    }); return () => controller.abort();
  }, [query]);
  useEffect(() => {
    if (search === lastLiveSearch.current) return;
    lastLiveSearch.current = search;
    const timeout = window.setTimeout(() => {
      const values = new URLSearchParams(queryRef.current);
      const nextSearch = search.trim();
      if (nextSearch) values.set("search", nextSearch); else values.delete("search");
      values.delete("page");
      const nextQuery = values.toString();
      if (nextQuery === queryRef.current) return;
      setSelectedDeviceId(""); setPage(null); setError(false); setQuery(nextQuery);
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [search]);
  useEffect(() => () => { statusController.current?.abort(); nextPageController.current?.abort(); }, []);
  const updateFilters = (nextActive: string, nextType: string) => {
    setActiveFilter(nextActive); setTypeFilter(nextType);
    const values = new URLSearchParams(queryRef.current);
    if (nextActive) values.set("is_active", nextActive); else values.delete("is_active");
    if (nextType) values.set("vehicle_type", nextType); else values.delete("vehicle_type");
    values.delete("page");
    const nextQuery = values.toString();
    if (nextQuery === queryRef.current) return;
    setSelectedDeviceId(""); setPage(null); setError(false); setQuery(nextQuery);
  };
  const toggleStatus = async (vehicle: Vehicle) => {
    const action = vehicle.is_active ? "deactivate" : "reactivate";
    const ok = await confirmAction({
      title: `${action === "deactivate" ? "Deactivate" : "Reactivate"} vehicle`,
      message: `Are you sure you want to ${action} ${vehicle.display_name} (${vehicle.device_id})?`,
      variant: "danger",
      confirmText: action === "deactivate" ? "Deactivate" : "Reactivate",
    });
    if (statusBusy || !ok) return;
    setStatusBusy(vehicle.device_id); setStatusError("");
    const controller = new AbortController(); statusController.current = controller;
    try {
      const updated = await changeVehicleStatus(vehicle.device_id, !vehicle.is_active, controller.signal);
      setPage(current => current ? { ...current, results: current.results.map(item => item.device_id === updated.device_id ? updated : item) } : current);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setStatusError(`Unable to ${action} ${vehicle.display_name}.`);
    } finally {
      if (statusController.current === controller) { statusController.current = null; setStatusBusy(""); }
    }
  };
  const readableType = (value: Vehicle["vehicle_type"]) => humanize(value);
  const makeModel = (vehicle: Vehicle) => [vehicle.manufacturer, vehicle.model].filter(Boolean).join(" ");
  const openDrawer = (deviceId: string, mode: typeof drawerMode = "overview") => { setSelectedDeviceId(deviceId); setDrawerMode(mode); setMenuDeviceId(""); };
  const selectedVehicle = page?.results.find(vehicle => vehicle.device_id === selectedDeviceId) ?? null;
  const exportLoadedVehicles = () => {
    if (!page?.results.length) return;
    const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const headings = ["Display Name", "Device ID", "Plate Number", "VIN", "Vehicle Type", "Manufacturer", "Model", "Model Year", "Passenger Capacity", "Payload Capacity (kg)", "GVWR (kg)", "Ownership Type", "Supplier", "Acquisition Date", "Status"];
    const rows = page.results.map(vehicle => [vehicle.display_name, vehicle.device_id, vehicle.plate_number, vehicle.vin, vehicle.vehicle_type, vehicle.manufacturer, vehicle.model, vehicle.model_year ?? "", vehicle.passenger_capacity ?? "", vehicle.payload_capacity_kg ?? "", vehicle.gvwr_kg ?? "", vehicle.ownership_type, vehicle.supplier_name, vehicle.acquisition_date ?? "", vehicle.is_active ? "Active" : "Inactive"]);
    const blob = new Blob([[headings, ...rows].map(row => row.map(escape).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "vehicles-loaded.csv"; link.click(); URL.revokeObjectURL(url);
  };
  const loadMore = useCallback(() => {
    if (!page?.next || nextPageController.current) return;
    const generation = requestGeneration.current; const controller = new AbortController();
    nextPageController.current = controller; setLoadingMore(true); setNextPageError(false);
    getVehicles(new URL(page.next).search.slice(1), controller.signal).then(nextPage => {
      if (generation !== requestGeneration.current) return;
      setPage(current => {
        if (!current) return current;
        const existing = new Set(current.results.map(vehicle => vehicle.device_id));
        return { ...current, count: nextPage.count, next: nextPage.next, results: [...current.results, ...nextPage.results.filter(vehicle => !existing.has(vehicle.device_id))] };
      });
    }).catch((reason: unknown) => {
      if (generation === requestGeneration.current && !(reason instanceof DOMException && reason.name === "AbortError")) setNextPageError(true);
    }).finally(() => {
      if (nextPageController.current === controller) { nextPageController.current = null; setLoadingMore(false); }
    });
  }, [page]);
  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !page?.next || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) loadMore(); }, { root: tableWrapRef.current, rootMargin: "0px 0px 120px" });
    observer.observe(target); return () => observer.disconnect();
  }, [loadMore, page?.next]);
  return <>{ConfirmModalComponent}<section className="vehicle-registry-page vehicle-registry-page--workspace"><div className="vehicle-registry-header"><div><p className="breadcrumb">Fleet &amp; Safety / Vehicles</p><h1>Vehicles</h1></div></div>
    <div className="vehicle-toolbar"><div className="vehicle-toolbar-primary"><label className="vehicle-search">Search vehicles<input aria-label="Search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Name, device ID, plate, VIN, supplier or PO" /></label>
      <div className="vehicle-toolbar-actions"><button type="button" className="btn-action--filled" disabled={!page?.results.length} onClick={exportLoadedVehicles}>Export Loaded Vehicles</button>
        {user?.role === "SUPER_ADMIN" && <button type="button" className="btn-action--filled" onClick={() => { setSelectedDeviceId(""); setCreating(true); }}>+ Add Vehicle</button>}</div>
      </div>
      <div className="vehicle-toolbar-filters"><label>Status<select name="is_active" value={activeFilter} onChange={event => updateFilters(event.target.value, typeFilter)}><option value="">All</option><option value="true">Active</option><option value="false">Inactive</option></select></label>
        <label>Vehicle Type<select name="vehicle_type" value={typeFilter} onChange={event => updateFilters(activeFilter, event.target.value)}><option value="">All</option>{vehicleTypes.map(value => <option key={value} value={value}>{readableType(value)}</option>)}</select></label></div>
    </div>
    {statusError && <p role="alert" className="message message--error">{statusError}</p>}
    <div className={`vehicle-registry-workspace${selectedVehicle ? " vehicle-registry-workspace--drawer-open" : ""}`}><div className="vehicle-registry-list-panel"><div ref={tableWrapRef} className="vehicle-table-wrap"><table className="vehicle-table"><thead><tr><th scope="col">Vehicle</th><th scope="col">Plate</th><th scope="col">Type</th><th scope="col">Make / Model</th><th scope="col">Capacity</th><th scope="col">Inspection</th><th scope="col">Compliance Records</th><th scope="col">Documents</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
      <tbody>{!page && !error && <tr><td colSpan={10} className="vehicle-table-state"><LoadingIndicator variant="card" message="Loading vehicles…" /></td></tr>}
        {error && <tr><td colSpan={10} className="vehicle-table-state vehicle-table-state--error"><span role="alert">Unable to load vehicles.</span></td></tr>}
        {page?.results.length === 0 && <tr><td colSpan={10} className="vehicle-table-state">No vehicles match these filters.</td></tr>}
        {page?.results.map(vehicle => <tr key={vehicle.device_id} className={selectedDeviceId === vehicle.device_id ? "selected" : undefined}><td><button type="button" className="vehicle-table-name" onClick={() => openDrawer(vehicle.device_id)}>{vehicle.display_name}</button><small>{vehicle.device_id}</small></td>
          <td>{vehicle.plate_number}</td><td>{readableType(vehicle.vehicle_type)}</td><td>{makeModel(vehicle) || <span className="vehicle-table-unavailable">Unavailable</span>}{vehicle.model_year && <small>{vehicle.model_year}</small>}</td>
          <td><span>Pax: {vehicle.passenger_capacity ?? "—"}</span><small>Payload: {vehicle.payload_capacity_kg ? `${vehicle.payload_capacity_kg} kg` : "—"}</small></td><td>{vehicle.latest_inspection ? <><span className={`inspection-result inspection-result--${vehicle.latest_inspection.result.toLowerCase()}`}>{humanize(vehicle.latest_inspection.result)}</span><small>{new Date(`${vehicle.latest_inspection.inspection_date}T00:00:00`).toLocaleDateString()}</small></> : <span className="vehicle-table-unavailable">No inspections</span>}</td><td><span className={`document-health document-health--${vehicle.document_health.toLowerCase()}`} title="Based only on compliance records stored in FTMS">{humanize(vehicle.document_health)}</span></td><td>{vehicle.document_count ? `${vehicle.document_count} doc${vehicle.document_count === 1 ? "" : "s"}` : <span className="vehicle-table-unavailable">No documents</span>}</td><td><StatusBadge status={vehicle.is_active ? "active" : "inactive"} tone={vehicleStatusTone[vehicle.is_active ? "active" : "inactive"]} /></td>
          <td><div className="vehicle-row-menu"><button type="button" className="vehicle-row-menu-toggle" aria-label={`More actions for ${vehicle.display_name}`} aria-haspopup="menu" aria-expanded={menuDeviceId === vehicle.device_id} onClick={() => setMenuDeviceId(current => current === vehicle.device_id ? "" : vehicle.device_id)} onKeyDown={event => { if (event.key === "Escape") setMenuDeviceId(""); }}>⋮</button>{menuDeviceId === vehicle.device_id && <div role="menu" className="vehicle-row-menu-popover"><button role="menuitem" type="button" onClick={() => openDrawer(vehicle.device_id)}>View vehicle</button>{user && canEdit(user.role) && <><button role="menuitem" type="button" onClick={() => openDrawer(vehicle.device_id, "edit")}>Edit vehicle</button><button role="menuitem" type="button" onClick={() => openDrawer(vehicle.device_id, "add")}>Add inspection</button><button role="menuitem" type="button" onClick={() => openDrawer(vehicle.device_id, "documents")}>Upload document</button></>}{user?.role === "SUPER_ADMIN" && <button role="menuitem" type="button" disabled={Boolean(statusBusy)} onClick={() => { setMenuDeviceId(""); void toggleStatus(vehicle); }}>{statusBusy === vehicle.device_id ? "Updating…" : vehicle.is_active ? "Deactivate" : "Reactivate"}</button>}</div>}</div></td></tr>)}</tbody></table><div ref={loadMoreRef} className="vehicle-load-more-sentinel">{loadingMore && <LoadingIndicator size="sm" message="Loading more vehicles…" />}{nextPageError && <><span role="alert">Unable to load more vehicles.</span><button type="button" className="btn-cancel" onClick={loadMore}>Retry</button></>}</div></div>
      {page && <div className="vehicle-pagination vehicle-list-summary"><span>{page.count} vehicle{page.count === 1 ? "" : "s"}</span></div>}</div>
      {selectedVehicle && (drawerMode === "edit" ? <aside className="vehicle-details-drawer vehicle-edit-drawer" role="dialog" aria-modal="true" aria-label={`Edit ${selectedVehicle.display_name}`}><header><div><small>Vehicle record</small><h2>Edit Vehicle</h2><span>{selectedVehicle.device_id}</span></div><button type="button" className="btn-cancel" aria-label="Close Edit Vehicle" onClick={() => setSelectedDeviceId("")}>×</button></header><div className="vehicle-drawer-body"><VehicleForm editing embedded initialVehicle={selectedVehicle} targetDeviceId={selectedVehicle.device_id} onCancel={() => setDrawerMode("overview")} onSaved={saved => { setPage(current => current ? { ...current, results: current.results.map(item => item.device_id === saved.device_id ? saved : item) } : current); setDrawerMode("overview"); }} /></div></aside> : <VehicleDrawer key={`${selectedVehicle.device_id}-${drawerMode}`} vehicle={selectedVehicle} role={user?.role} busy={statusBusy === selectedVehicle.device_id} initialMode={drawerMode} onEdit={() => setDrawerMode("edit")} onInspectionCreated={inspection => setPage(current => current ? { ...current, results: current.results.map(item => item.device_id === selectedVehicle.device_id ? { ...item, latest_inspection: inspection } : item) } : current)} onClose={() => setSelectedDeviceId("")} onToggle={() => void toggleStatus(selectedVehicle)} />)}</div>{creating && <div className="vehicle-create-backdrop"><aside className="vehicle-details-drawer vehicle-create-drawer" role="dialog" aria-modal="true" aria-label="Add Vehicle"><header><div><small>Fleet registry</small><h2>Add Vehicle</h2></div><button type="button" className="btn-cancel" aria-label="Close Add Vehicle" onClick={() => setCreating(false)}>×</button></header><div className="vehicle-drawer-body"><VehicleForm embedded onCancel={() => setCreating(false)} onSaved={saved => { setCreating(false); setPage(current => current ? { ...current, count: current.count + 1, results: [saved, ...current.results] } : current); setSelectedDeviceId(saved.device_id); setDrawerMode("overview"); }} /></div></aside></div>}
  </section></>;
}

function VehicleDrawer({ vehicle, role, busy, initialMode, onEdit, onInspectionCreated, onClose, onToggle }: { vehicle: Vehicle; role?: Role; busy: boolean; initialMode: "overview" | "inspections" | "documents" | "add"; onEdit: () => void; onInspectionCreated: (inspection: VehicleInspection) => void; onClose: () => void; onToggle: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [tab, setTab] = useState<"overview" | "acquisition" | "compliance" | "inspections" | "documents" | "activity">(initialMode === "documents" ? "documents" : initialMode === "overview" ? "overview" : "inspections");
  const [adding, setAdding] = useState(initialMode === "add"); const [inspectionPage, setInspectionPage] = useState<InspectionPage | null>(null); const [inspectionQuery, setInspectionQuery] = useState(""); const [inspectionReload, setInspectionReload] = useState(0); const [inspectionState, setInspectionState] = useState<"idle" | "loading" | "error">(initialMode === "overview" ? "idle" : "loading"); const [inspectionDetail, setInspectionDetail] = useState<VehicleInspection | null>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
  useEffect(() => {
    if (tab !== "inspections") return;
    const controller = new AbortController();
    getVehicleInspections(vehicle.device_id, inspectionQuery, controller.signal).then(page => { setInspectionPage(page); setInspectionState("idle"); }).catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setInspectionState("error"); });
    return () => controller.abort();
  }, [inspectionQuery, inspectionReload, tab, vehicle.device_id]);
  const value = (item: string | number | null) => item === null || item === "" ? "Unavailable" : String(item);
  const changeInspectionPage = (url: string) => { setInspectionPage(null); setInspectionState("loading"); setInspectionQuery(new URL(url).search.slice(1)); };
  const selectTab = (next: typeof tab) => { setTab(next); setInspectionDetail(null); setAdding(false); if (next === "inspections" && tab !== "inspections") setInspectionState("loading"); };
  return <aside className="vehicle-details-drawer" role="dialog" aria-labelledby="vehicle-drawer-title"><header><div><small>Vehicle record</small><h2 id="vehicle-drawer-title">{vehicle.display_name}</h2><span>{vehicle.device_id}</span></div><button ref={closeRef} type="button" className="btn-cancel" aria-label="Close vehicle details" onClick={onClose}>×</button></header><div className="nav nav-pills vehicle-tabs" role="tablist">{(["overview", "acquisition", "compliance", "inspections", "documents", "activity"] as const).map(item => <button key={item} type="button" role="tab" className={`nav-link${tab === item ? " active" : ""}`} aria-selected={tab === item} onClick={() => selectTab(item)}>{humanize(item)}</button>)}</div><div className="vehicle-drawer-body">
    {tab === "overview" && <><section><h3>Registry</h3><dl><div><dt>Display Name</dt><dd>{vehicle.display_name}</dd></div><div><dt>Plate</dt><dd>{vehicle.plate_number}</dd></div><div><dt>Type</dt><dd>{humanize(vehicle.vehicle_type)}</dd></div><div><dt>Status</dt><dd><StatusBadge status={vehicle.is_active ? "active" : "inactive"} tone={vehicleStatusTone[vehicle.is_active ? "active" : "inactive"]} /></dd></div></dl></section>
      <section><h3>Identity</h3><dl><div className="wide"><dt>Device ID</dt><dd>{vehicle.device_id}</dd></div><div><dt>VIN</dt><dd>{value(vehicle.vin)}</dd></div><div><dt>Engine Number</dt><dd>{value(vehicle.engine_number)}</dd></div><div className="wide"><dt>Chassis Number</dt><dd>{value(vehicle.chassis_number)}</dd></div></dl></section>
      <section><h3>Specifications</h3><dl><div><dt>Manufacturer</dt><dd>{value(vehicle.manufacturer)}</dd></div><div><dt>Model</dt><dd>{value(vehicle.model)}</dd></div><div><dt>Model Year</dt><dd>{value(vehicle.model_year)}</dd></div><div><dt>Color</dt><dd>{value(vehicle.color)}</dd></div><div><dt>Fuel Type</dt><dd>{vehicle.fuel_type ? humanize(vehicle.fuel_type) : "Not recorded"}</dd></div><div><dt>Transmission</dt><dd>{vehicle.transmission_type ? humanize(vehicle.transmission_type) : "Not recorded"}</dd></div><div><dt>Passenger Capacity</dt><dd>{value(vehicle.passenger_capacity)}</dd></div><div><dt>Payload Capacity</dt><dd>{vehicle.payload_capacity_kg ? `${vehicle.payload_capacity_kg} kg` : "Not recorded"}</dd></div><div><dt>GVWR</dt><dd>{vehicle.gvwr_kg ? `${vehicle.gvwr_kg} kg` : "Not recorded"}</dd></div></dl></section>
      <section><h3>Record</h3><dl><div><dt>Created At</dt><dd>{new Date(vehicle.created_at).toLocaleString()}</dd></div><div><dt>Updated At</dt><dd>{new Date(vehicle.updated_at).toLocaleString()}</dd></div></dl></section></>}
    {tab === "acquisition" && <section><h3>Ownership &amp; Acquisition</h3><dl><div><dt>Ownership Type</dt><dd>{vehicle.ownership_type ? humanize(vehicle.ownership_type) : "Not recorded"}</dd></div><div><dt>Supplier</dt><dd>{value(vehicle.supplier_name)}</dd></div><div><dt>Purchase Order</dt><dd>{value(vehicle.purchase_order_number)}</dd></div><div><dt>Acquisition Date</dt><dd>{value(vehicle.acquisition_date)}</dd></div><div><dt>Purchase Price</dt><dd>{vehicle.purchase_price ? `${vehicle.purchase_currency || "—"} ${vehicle.purchase_price}` : "Not recorded"}</dd></div><div><dt>Warranty Expiry</dt><dd>{value(vehicle.warranty_expiry_date)}</dd></div><div><dt>Registration Expiry</dt><dd>{value(vehicle.registration_expiry_date)}</dd></div><div><dt>Insurance Expiry</dt><dd>{value(vehicle.insurance_expiry_date)}</dd></div></dl></section>}
    {tab === "compliance" && <><section><h3>Compliance Records</h3><dl><div><dt>Document Health</dt><dd><span className={`document-health document-health--${vehicle.document_health.toLowerCase()}`}>{humanize(vehicle.document_health)}</span></dd></div><div><dt>Basis</dt><dd>Records stored in FTMS</dd></div><div><dt>Registration Master Expiry</dt><dd>{value(vehicle.registration_expiry_date)}</dd></div><div><dt>Insurance Master Expiry</dt><dd>{value(vehicle.insurance_expiry_date)}</dd></div></dl></section><VehicleDocuments vehicle={vehicle} role={role} complianceOnly /></>}
    {tab === "inspections" && <>{adding ? <InspectionForm vehicle={vehicle} onCancel={() => setAdding(false)} onCreated={inspection => { setAdding(false); setInspectionDetail(inspection); setInspectionState("loading"); setInspectionReload(value => value + 1); onInspectionCreated(inspection); }} /> : inspectionDetail ? <InspectionDetail vehicle={vehicle} inspection={inspectionDetail} onBack={() => setInspectionDetail(null)} /> : <><div className="inspection-list-heading"><strong>Inspection history</strong>{role && canEdit(role) && <button type="button" className="btn-action--filled" onClick={() => setAdding(true)}>+ Add Inspection</button>}</div>{inspectionState === "loading" && <div role="status" className="inspection-state"><LoadingIndicator variant="card" message="Loading inspections…" /></div>}{inspectionState === "error" && <p role="alert" className="inspection-state inspection-state--error">Unable to load inspections.</p>}{inspectionState === "idle" && inspectionPage?.results.length === 0 && <p className="inspection-state">No inspections recorded.</p>}{inspectionState === "idle" && inspectionPage && inspectionPage.results.length > 0 && <div className="inspection-list">{inspectionPage.results.map(inspection => <article key={inspection.id}><div><span className={`inspection-result inspection-result--${inspection.result.toLowerCase()}`}>{humanize(inspection.result)}</span><strong>{new Date(`${inspection.inspection_date}T00:00:00`).toLocaleDateString()}</strong><small>{humanize(inspection.inspection_type)} · {inspection.inspector_name}</small>{inspection.odometer_km !== null && <small>{inspection.odometer_km.toLocaleString()} km</small>}{(inspection.issues_found || inspection.notes) && <p>{inspection.issues_found || inspection.notes}</p>}</div><button type="button" className="btn-filter" onClick={() => setInspectionDetail(inspection)}>View Inspection</button></article>)}</div>}{inspectionState === "idle" && inspectionPage && <nav className="inspection-pagination" aria-label="Inspection pages"><span>{inspectionPage.count} inspection{inspectionPage.count === 1 ? "" : "s"}</span><div><button type="button" className="btn-filter" disabled={!inspectionPage.previous} onClick={() => changeInspectionPage(inspectionPage.previous!)}>Previous</button><button type="button" className="btn-filter" disabled={!inspectionPage.next} onClick={() => changeInspectionPage(inspectionPage.next!)}>Next</button></div></nav>}</>}</>}
    {tab === "documents" && <VehicleDocuments vehicle={vehicle} role={role} />}
    {tab === "activity" && <section><h3>Registry Activity</h3><div className="vehicle-activity"><p><strong>Vehicle created</strong><time>{new Date(vehicle.created_at).toLocaleString()}</time></p><p><strong>Vehicle last updated</strong><time>{new Date(vehicle.updated_at).toLocaleString()}</time></p></div></section>}
  </div><footer>{role && canEdit(role) && <><button type="button" className="btn-action--filled" onClick={onEdit}>Edit</button>{tab === "overview" && <button type="button" className="btn-action--filled" onClick={() => { setTab("inspections"); setAdding(true); }}>Add Inspection</button>}</>}{role === "SUPER_ADMIN" && <button type="button" className="btn-action--filled" disabled={busy} onClick={onToggle}>{busy ? "Updating…" : vehicle.is_active ? "Deactivate" : "Reactivate"}</button>}</footer></aside>;
}

function VehicleDocuments({ vehicle, role, complianceOnly = false }: { vehicle: Vehicle; role?: Role; complianceOnly?: boolean }) {
  const [page, setPage] = useState<DocumentPage | null>(null); const [query, setQuery] = useState("");
  const [state, setState] = useState<"loading" | "idle" | "error">("loading"); const [uploading, setUploading] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [reload, setReload] = useState(0);
  useEffect(() => { const controller = new AbortController(); getVehicleDocuments(vehicle.device_id, query, controller.signal).then(result => { setPage(result); setState("idle"); }).catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setState("error"); }); return () => controller.abort(); }, [vehicle.device_id, query, reload]);
  const changePage = (url: string) => { setPage(null); setQuery(new URL(url).search.slice(1)); };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (busy) return; setBusy(true); setError("");
    try { await createVehicleDocument(vehicle.device_id, new FormData(event.currentTarget)); setUploading(false); setPage(null); setState("loading"); setQuery(""); setReload(value => value + 1); }
    catch (reason) { setError(reason instanceof ApiError && reason.status === 400 ? "Please correct the document information." : "Unable to upload document."); }
    finally { setBusy(false); }
  };
  if (uploading) return <form className="vehicle-document-form" onSubmit={submit}><header><strong>Upload document</strong><button type="button" className="btn-cancel" aria-label="Cancel document upload" onClick={() => setUploading(false)}>×</button></header><label>Document Type<select name="document_type" required defaultValue=""><option value="" disabled>Select type</option>{documentTypes.map(type => <option key={type} value={type}>{humanize(type)}</option>)}</select></label><label>Title<input name="title" required /></label><label>Reference Number<input name="reference_number" /></label><label>Issuer / Provider<input name="issuer_name" /></label><label>Issued Date<input name="issued_date" type="date" /></label><label>Effective Date<input name="effective_date" type="date" /></label><label>Expiry Date<input name="expiry_date" type="date" /></label><label className="wide">File<input name="file" type="file" required accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" /></label>{error && <p role="alert" className="message message--error">{error}</p>}<footer><button type="button" className="btn-cancel" onClick={() => setUploading(false)}>Cancel</button><button className="btn-action--filled" disabled={busy}>{busy ? "Uploading…" : "Upload Document"}</button></footer></form>;
  const complianceTypes = new Set(["OFFICIAL_RECEIPT", "CERTIFICATE_OF_REGISTRATION", "INSURANCE", "EMISSION_CERTIFICATE", "PMVIC_CERTIFICATE"]);
  const records = complianceOnly ? page?.results.filter(document => complianceTypes.has(document.document_type)) : page?.results;
  return <><div className="inspection-list-heading"><strong>{complianceOnly ? "Compliance evidence" : "Vehicle documents"}</strong>{role && canEdit(role) && <button type="button" className="btn-action--filled" onClick={() => setUploading(true)}>+ Upload Document</button>}</div>{state === "loading" && <div role="status" className="inspection-state"><LoadingIndicator variant="card" message="Loading documents…" /></div>}{state === "error" && <p role="alert" className="inspection-state inspection-state--error">Unable to load documents.</p>}{state === "idle" && records?.length === 0 && <p className="inspection-state">{complianceOnly ? "No compliance evidence recorded." : "No vehicle documents recorded."}</p>}{state === "idle" && records && records.length > 0 && <div className="vehicle-document-list">{records.map(document => <article key={document.id}><div><strong>{document.title}</strong><small>{humanize(document.document_type)} · {document.uploaded_by_name}</small><small>{document.issuer_name || "Issuer not recorded"}{document.reference_number ? ` · ${document.reference_number}` : ""}</small><small>{document.effective_date ? `Effective ${document.effective_date}` : document.issued_date ? `Issued ${document.issued_date}` : "Issue date not recorded"}</small>{document.expiry_date && <small>Expires {document.expiry_date}</small>}</div><a className="button btn-filter" href={`${apiBaseUrl}${document.download_url}`} target="_blank" rel="noreferrer">Open</a></article>)}</div>}{state === "idle" && page && <nav className="inspection-pagination" aria-label="Document pages"><span>{page.count} document{page.count === 1 ? "" : "s"}</span><div><button type="button" className="btn-filter" disabled={!page.previous} onClick={() => changePage(page.previous!)}>Previous</button><button type="button" className="btn-filter" disabled={!page.next} onClick={() => changePage(page.next!)}>Next</button></div></nav>}</>;
}

function InspectionForm({ vehicle, onCancel, onCreated }: { vehicle: Vehicle; onCancel: () => void; onCreated: (inspection: VehicleInspection) => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const inFlight = useRef(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (inFlight.current) return; inFlight.current = true; setBusy(true); setError(""); const data = new FormData(event.currentTarget); const payload: Record<string, unknown> = {};
    for (const key of ["inspection_date", "inspection_type", "result", "exterior_condition", "interior_condition", "tires_condition", "lights_condition", "brakes_condition", "fluids_condition", "safety_equipment_condition", "notes", "issues_found"]) payload[key] = String(data.get(key) ?? "");
    for (const key of ["odometer_km", "fuel_level_percent"]) { const raw = String(data.get(key) ?? ""); payload[key] = raw === "" ? null : Number(raw); }
    try { onCreated(await createVehicleInspection(vehicle.device_id, payload)); }
    catch (reason) { setError(reason instanceof ApiError && reason.status === 400 ? "Please correct the inspection information." : "Unable to save inspection."); }
    finally { inFlight.current = false; setBusy(false); }
  };
  return <form className="inspection-form" onSubmit={submit}><header><div><small>New inspection</small><strong>{vehicle.display_name}</strong></div><button type="button" className="btn-cancel" aria-label="Cancel inspection" onClick={onCancel}>×</button></header><label>Inspection Date<input name="inspection_date" type="date" required /></label><label>Inspection Type<select name="inspection_type" required defaultValue=""><option value="" disabled>Select type</option>{inspectionTypes.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Result<select name="result" required defaultValue=""><option value="" disabled>Select result</option>{inspectionResults.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Odometer (km)<input name="odometer_km" type="number" min="0" /></label><label>Fuel Level (%)<input name="fuel_level_percent" type="number" min="0" max="100" /></label><fieldset><legend>Condition checks</legend>{["exterior", "interior", "tires", "lights", "brakes", "fluids", "safety_equipment"].map(item => <label key={item}>{humanize(item)}<select name={`${item}_condition`} defaultValue="NOT_CHECKED">{inspectionConditions.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label>)}</fieldset><label className="wide">Issues Found<textarea name="issues_found" rows={2} /></label><label className="wide">Notes<textarea name="notes" rows={2} /></label>{error && <p role="alert" className="message message--error">{error}</p>}<footer><button type="button" className="btn-cancel" onClick={onCancel}>Cancel</button><button className="btn-confirm" disabled={busy}>{busy ? "Saving…" : "Save Inspection"}</button></footer></form>;
}

function InspectionDetail({ vehicle, inspection, onBack }: { vehicle: Vehicle; inspection: VehicleInspection; onBack: () => void }) {
  const value = (item: string | number | null, suffix = "") => item === null || item === "" ? "Unavailable" : `${item}${suffix}`;
  const conditions = [["Exterior", inspection.exterior_condition], ["Interior", inspection.interior_condition], ["Tires", inspection.tires_condition], ["Lights", inspection.lights_condition], ["Brakes", inspection.brakes_condition], ["Fluids", inspection.fluids_condition], ["Safety Equipment", inspection.safety_equipment_condition]];
  return <div className="inspection-detail"><button type="button" className="inspection-back" onClick={onBack}>← Inspection history</button><header><div><span className={`inspection-result inspection-result--${inspection.result.toLowerCase()}`}>{humanize(inspection.result)}</span><strong>{new Date(`${inspection.inspection_date}T00:00:00`).toLocaleDateString()}</strong><small>{humanize(inspection.inspection_type)}</small></div></header><section><h3>Vehicle</h3><dl><div><dt>Display Name</dt><dd>{vehicle.display_name}</dd></div><div><dt>Plate</dt><dd>{vehicle.plate_number}</dd></div><div className="wide"><dt>Device ID</dt><dd>{vehicle.device_id}</dd></div></dl></section><section><h3>Inspection Details</h3><dl><div><dt>Odometer</dt><dd>{inspection.odometer_km === null ? "Unavailable" : `${inspection.odometer_km.toLocaleString()} km`}</dd></div><div><dt>Fuel Level</dt><dd>{value(inspection.fuel_level_percent, "%")}</dd></div><div className="wide"><dt>Inspector</dt><dd>{inspection.inspector_name}</dd></div>{conditions.map(([label, condition]) => <div key={label}><dt>{label}</dt><dd>{humanize(condition)}</dd></div>)}{inspection.issues_found && <div className="wide"><dt>Issues Found</dt><dd>{inspection.issues_found}</dd></div>}{inspection.notes && <div className="wide"><dt>Notes</dt><dd>{inspection.notes}</dd></div>}</dl></section><section><h3>Record</h3><dl><div><dt>Created At</dt><dd>{new Date(inspection.created_at).toLocaleString()}</dd></div><div><dt>Updated At</dt><dd>{new Date(inspection.updated_at).toLocaleString()}</dd></div></dl></section></div>;
}
function VehicleForm({ editing = false, embedded = false, initialVehicle = null, targetDeviceId, onSaved, onCancel }: { editing?: boolean; embedded?: boolean; initialVehicle?: Vehicle | null; targetDeviceId?: string; onSaved?: (vehicle: Vehicle) => void; onCancel?: () => void }) {
  const { user } = useAuth(); const { deviceId: routeDeviceId = "" } = useParams<{ deviceId: string }>(); const history = useHistory(); const deviceId = targetDeviceId ?? routeDeviceId;
  const [vehicle, setVehicle] = useState<Vehicle | null>(initialVehicle); const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const submitInFlight = useRef(false);
  const submitController = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; submitController.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!editing || initialVehicle) return;
    let active = true; const controller = new AbortController();
    getVehicle(deviceId, controller.signal)
      .then((loaded) => { if (active) setVehicle(loaded); })
      .catch((reason: unknown) => {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof ApiError && reason.status === 403 ? "You do not have permission to edit this vehicle." : reason instanceof ApiError && reason.status === 404 ? "Vehicle not found." : "Unable to load vehicle.");
        }
      });
    return () => { active = false; controller.abort(); };
  }, [editing, deviceId, initialVehicle]);
  if (!user || (editing ? !canEdit(user.role) : user.role !== "SUPER_ADMIN")) return <Redirect to="/vehicles" />;
  if (editing && !vehicle && !error) return <LoadingIndicator variant="card" message="Loading vehicle…" />;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitInFlight.current) return;
    submitInFlight.current = true;
    setError(""); setFieldErrors({}); const data = new FormData(event.currentTarget); const payload: Record<string, unknown> = {};
    for (const key of ["device_id", "plate_number", "display_name", "vehicle_type", "manufacturer", "model", "vin", "engine_number", "chassis_number", "color", "fuel_type", "transmission_type", "ownership_type", "supplier_name", "purchase_order_number", "purchase_currency"]) if (!editing || key !== "device_id") payload[key] = String(data.get(key) ?? "");
    for (const key of ["model_year", "passenger_capacity"]) { const value = String(data.get(key) ?? ""); payload[key] = value ? Number(value) : null; }
    for (const key of ["payload_capacity_kg", "gvwr_kg", "acquisition_date", "warranty_expiry_date", "registration_expiry_date", "insurance_expiry_date", "purchase_price"]) { const value = String(data.get(key) ?? ""); payload[key] = value || null; }
    setBusy(true);
    const controller = new AbortController(); submitController.current = controller;
    try {
      const saved = editing
        ? await editVehicle(deviceId, payload, controller.signal)
        : await createVehicle(payload, controller.signal);
      if (mounted.current) {
        if (onSaved) onSaved(saved);
        else history.push(`/vehicles/${encodeURIComponent(saved.device_id)}`);
      }
    }
    catch (reason) {
      if (!mounted.current) return;
      if (reason instanceof ApiError && reason.body && typeof reason.body === "object") {
        const safe = Object.fromEntries(
          Object.entries(reason.body as Record<string, unknown>).map(([key, value]) => [
            key, Array.isArray(value) ? String(value[0]) : String(value),
          ]),
        );
        setFieldErrors(safe); setError("Please correct the vehicle information.");
      } else if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError("Unable to save vehicle.");
      }
    } finally {
      if (submitController.current === controller) {
        submitController.current = null;
        submitInFlight.current = false;
        if (mounted.current) setBusy(false);
      }
    }
  };
  return <>{!embedded && <h1>{editing ? "Edit vehicle" : "Create vehicle"}</h1>}<form key={editing ? deviceId : "create"} className="vehicle-form vehicle-asset-form" onSubmit={submit}>
    <fieldset><legend>Identity</legend><label>Device ID<input name="device_id" required={!editing} disabled={editing} defaultValue={vehicle?.device_id} pattern="[A-Z0-9][A-Z0-9._-]{0,63}" aria-describedby="device_id-error" />{fieldErrors.device_id && <span id="device_id-error" role="alert">{fieldErrors.device_id}</span>}</label><label>Display name<input name="display_name" required defaultValue={vehicle?.display_name} aria-describedby="display_name-error" />{fieldErrors.display_name && <span id="display_name-error" role="alert">{fieldErrors.display_name}</span>}</label><label>Plate number<input name="plate_number" required defaultValue={vehicle?.plate_number} aria-describedby="plate_number-error" />{fieldErrors.plate_number && <span id="plate_number-error" role="alert">{fieldErrors.plate_number}</span>}</label><label>VIN<input name="vin" defaultValue={vehicle?.vin} /></label><label>Engine Number<input name="engine_number" defaultValue={vehicle?.engine_number} /></label><label>Chassis Number<input name="chassis_number" defaultValue={vehicle?.chassis_number} /></label></fieldset>
    <fieldset><legend>Vehicle Specifications</legend><label>Vehicle type<select name="vehicle_type" defaultValue={vehicle?.vehicle_type ?? "OTHER"}>{vehicleTypes.map(v => <option key={v} value={v}>{humanize(v)}</option>)}</select></label><label>Manufacturer<input name="manufacturer" defaultValue={vehicle?.manufacturer} /></label><label>Model<input name="model" defaultValue={vehicle?.model} /></label><label>Model year<input name="model_year" type="number" min="1980" max={new Date().getUTCFullYear() + 1} defaultValue={vehicle?.model_year ?? ""} /></label><label>Color<input name="color" defaultValue={vehicle?.color} /></label><label>Fuel Type<select name="fuel_type" defaultValue={vehicle?.fuel_type ?? ""}><option value="">Not recorded</option>{fuelTypes.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Transmission<select name="transmission_type" defaultValue={vehicle?.transmission_type ?? ""}><option value="">Not recorded</option>{transmissionTypes.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Passenger Capacity<input name="passenger_capacity" type="number" min="1" max="100" defaultValue={vehicle?.passenger_capacity ?? ""} /></label><label>Payload Capacity (kg)<input name="payload_capacity_kg" type="number" min="0" step="0.01" defaultValue={vehicle?.payload_capacity_kg ?? ""} /></label><label>GVWR (kg)<input name="gvwr_kg" type="number" min="0" step="0.01" defaultValue={vehicle?.gvwr_kg ?? ""} /></label></fieldset>
    <fieldset><legend>Ownership &amp; Acquisition</legend><label>Ownership Type<select name="ownership_type" defaultValue={vehicle?.ownership_type ?? ""}><option value="">Not recorded</option>{ownershipTypes.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Supplier Name<input name="supplier_name" defaultValue={vehicle?.supplier_name} /></label><label>Purchase Order Number<input name="purchase_order_number" defaultValue={vehicle?.purchase_order_number} /></label><label>Acquisition Date<input name="acquisition_date" type="date" defaultValue={vehicle?.acquisition_date ?? ""} /></label><label>Purchase Price<input name="purchase_price" type="number" min="0" step="0.01" defaultValue={vehicle?.purchase_price ?? ""} /></label><label>Currency<input name="purchase_currency" maxLength={3} defaultValue={vehicle?.purchase_currency} /></label><label>Warranty Expiry<input name="warranty_expiry_date" type="date" defaultValue={vehicle?.warranty_expiry_date ?? ""} /></label></fieldset>
    <fieldset><legend>Registration &amp; Insurance</legend><label>Registration Expiry<input name="registration_expiry_date" type="date" defaultValue={vehicle?.registration_expiry_date ?? ""} /></label><label>Insurance Expiry<input name="insurance_expiry_date" type="date" defaultValue={vehicle?.insurance_expiry_date ?? ""} /></label></fieldset>
    {error && <p role="alert" className="message message--error">{error}</p>}<div className="vehicle-form-actions">{embedded && <button type="button" className="btn-cancel" onClick={onCancel}>Cancel</button>}<button className="btn-confirm" disabled={busy}>{busy ? "Saving…" : "Save vehicle"}</button></div>
  </form></>;
}
function LiveStatus({ deviceId }: { deviceId: string }) {
  const [now, setNow] = useState(() => Date.now()); const { status: vehicle, requestState, realtimeState } = useVehicleStatus(deviceId);
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  const latest = vehicle?.latest ?? null; const stale = latest && now - Date.parse(latest.recorded_at) > 60_000;
  const value = (number: number | null, suffix: string) => number === null ? "Unavailable" : `${number.toLocaleString()} ${suffix}`;
  return <section aria-labelledby="pilot-title"><p className="eyebrow">Live MQTT/WebSocket pilot</p><h2 id="pilot-title">Simulated Pilot Data</h2><p>Real-time status: {realtimeState}</p>
    {requestState === "loading" && <LoadingIndicator size="sm" message="Loading vehicle status…" />}{requestState === "error" && !vehicle && <p className="message message--error">Latest-status request failed.</p>}
    {vehicle && !latest && <p>Waiting for the first telemetry event…</p>}{latest && <><StatusBadge status={stale ? "stale" : "fresh"} tone={freshnessTone[stale ? "stale" : "fresh"]} />
      <dl className="telemetry-grid"><div><dt>Speed</dt><dd>{value(latest.gnss_speed_kph, "km/h")}</dd></div><div><dt>RPM</dt><dd>{value(latest.rpm, "rpm")}</dd></div>
        <div><dt>Coolant</dt><dd>{value(latest.coolant_c, "°C")}</dd></div><div><dt>Engine load</dt><dd>{value(latest.engine_load_pct, "%")}</dd></div>
        <div><dt>Driving event</dt><dd>{latest.driving_event.replaceAll("_", " ")}</dd></div><div><dt>Position</dt><dd>{latest.latitude.toFixed(4)}, {latest.longitude.toFixed(4)}</dd></div>
        <div><dt>Recorded at</dt><dd>{new Date(latest.recorded_at).toLocaleString()}</dd></div><div><dt>Received at</dt><dd>{new Date(latest.received_at).toLocaleString()}</dd></div></dl></>}
    <LiveVehicleMap latest={latest} /></section>;
}
function VehicleDetail() {
  const { deviceId = "" } = useParams<{ deviceId: string }>(); const { user } = useAuth(); const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [state, setState] = useState<"loading"|"error"|"missing">("loading");
  const [actionError, setActionError] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const { confirm: confirmAction, ConfirmModalComponent } = useConfirmModal();
  const mounted = useRef(true);
  const actionInFlight = useRef(false);
  const actionController = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; actionController.current?.abort();
    };
  }, []);
  useEffect(() => {
    let active = true; const controller = new AbortController();
    getVehicle(deviceId, controller.signal)
      .then((loaded) => { if (active) setVehicle(loaded); })
      .catch((error: unknown) => {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          setState(error instanceof ApiError && error.status === 404 ? "missing" : "error");
        }
      });
    return () => { active = false; controller.abort(); };
  }, [deviceId]);
  if (!vehicle || vehicle.device_id !== deviceId) return <div role={state === "error" ? "alert" : undefined}>{state === "loading" ? <LoadingIndicator size="sm" message="Loading vehicle…" /> : state === "missing" ? "Vehicle not found." : "Unable to load vehicle."}</div>;
  const toggle = async () => {
    if (actionInFlight.current) return;
    const action = vehicle.is_active ? "deactivate" : "reactivate";
    const ok = await confirmAction({
      title: `${action === "deactivate" ? "Deactivate" : "Reactivate"} vehicle`,
      message: `Are you sure you want to ${action} ${vehicle.display_name} (${vehicle.device_id})?`,
      variant: "danger",
      confirmText: action === "deactivate" ? "Deactivate" : "Reactivate",
    });
    if (!ok) return;
    actionInFlight.current = true;
    setActionBusy(true);
    setActionError("");
    const controller = new AbortController(); actionController.current = controller;
    try {
      const updated = await changeVehicleStatus(
        vehicle.device_id, !vehicle.is_active, controller.signal,
      );
      if (mounted.current) setVehicle(updated);
    } catch (error) {
      if (
        mounted.current &&
        !(error instanceof DOMException && error.name === "AbortError")
      ) setActionError(`Unable to ${action} this vehicle.`);
    } finally {
      if (actionController.current === controller) {
        actionController.current = null;
        actionInFlight.current = false;
        if (mounted.current) setActionBusy(false);
      }
    }
  };
  return <>{ConfirmModalComponent}<div className="page-title"><div><p className="eyebrow">{vehicle.device_id}</p><h1>{vehicle.display_name}</h1></div>
    {user && canEdit(user.role) && <Link className="btn-action--filled" to="edit">Edit</Link>}{user?.role === "SUPER_ADMIN" && <button className="btn-action--filled" disabled={actionBusy} onClick={() => void toggle()}>{actionBusy ? "Updating…" : vehicle.is_active ? "Deactivate" : "Reactivate"}</button>}</div>
    {actionError && <p role="alert" className="message message--error">{actionError}</p>}<dl className="registry-grid">{Object.entries(vehicle).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{key === "is_active" ? <StatusBadge status={value ? "active" : "inactive"} tone={vehicleStatusTone[value ? "active" : "inactive"]} /> : value === null || value === "" ? "Unavailable" : String(value)}</dd></div>)}</dl>
    <LiveStatus deviceId={vehicle.device_id} /></>;
}
function VehicleEditRoute() {
  const { deviceId = "" } = useParams<{ deviceId: string }>();
  return <VehicleForm key={deviceId} editing />;
}
function VehicleDetailRoute() {
  const { deviceId = "" } = useParams<{ deviceId: string }>();
  return <VehicleDetail key={deviceId} />;
}
export default function VehicleRoutes() {
  return <Switch>
    <Route path="/vehicles/new" exact><VehicleForm /></Route>
    <Route path="/vehicles/:deviceId/edit" exact><VehicleEditRoute /></Route>
    <Route path="/vehicles/:deviceId" exact><VehicleDetailRoute /></Route>
    <Route path="/vehicles" exact><VehicleList /></Route>
  </Switch>;
}
