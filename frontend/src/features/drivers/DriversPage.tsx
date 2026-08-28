import { FormEvent, useEffect, useRef, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { humanize as words } from "../../utils/text";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  StatusBadge,
  driverEmploymentTone,
  driverEligibilityTone,
} from "../../components/common/StatusBadge";
import {
  createDriver,
  createDriverDocument,
  driverDocumentTypes,
  editDriver,
  eligibilityStatuses,
  employmentStatuses,
  getDriverDocuments,
  getDrivers,
  type Driver,
  type DriverDocument,
} from "../../services/drivers";
import { ApiError } from "../../services/api";

const shown = (value: string | null) => value || "Not linked";
const saveError = (error: unknown) => {
  if (!(error instanceof ApiError))
    return "Unable to save the Driver. Please try again.";
  if (error.status === 403)
    return "Your staff session changed or does not have permission. Refresh and sign in again.";
  if (typeof error.body === "object" && error.body !== null) {
    if ("detail" in error.body && typeof error.body.detail === "string")
      return error.body.detail;
    const messages = Object.entries(error.body).flatMap(([field, value]) => {
      const details = Array.isArray(value)
        ? value.filter((item): item is string => typeof item === "string")
        : typeof value === "string"
          ? [value]
          : [];
      return details.map((detail) => `${words(field)}: ${detail}`);
    });
    if (messages.length) return messages.join(" ");
  }
  return "Unable to save the Driver. Review the account details and try again.";
};
export default function DriversPage() {
  const { user } = useAuth();
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [count, setCount] = useState(0);
  const [selected, setSelected] = useState<Driver | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [search, setSearch] = useState("");
  const [employment, setEmployment] = useState("");
  const [eligibility, setEligibility] = useState("");
  const [tab, setTab] = useState("overview");
  const [formMode, setFormMode] = useState<"add" | "edit" | null>(null);
  const [documents, setDocuments] = useState<DriverDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (search.trim()) params.set("search", search.trim());
    if (employment) params.set("employment_status", employment);
    if (eligibility) params.set("eligibility_status", eligibility);
    getDrivers(params.toString(), controller.signal)
      .then((page) => {
        setDrivers(page.results);
        setCount(page.count);
        setSelected(
          (current) =>
            page.results.find((item) => item.id === current?.id) ??
            page.results[0] ??
            null,
        );
        setState("ready");
      })
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError"))
          setState("error");
      });
    return () => controller.abort();
  }, [search, employment, eligibility]);
  useEffect(() => {
    if (tab !== "documents" || !selected) return;
    const controller = new AbortController();
    getDriverDocuments(selected.id, controller.signal).then((page) =>
      setDocuments(page.results),
    );
    return () => controller.abort();
  }, [selected, tab]);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const data = new FormData(event.currentTarget);
      let saved: Driver;
      if (formMode === "edit" && selected) {
        saved = await editDriver(selected.id, data);
      } else {
        const created = await createDriver(data);
        saved = created;
        setNotice(
          created.onboarding.email_status === "SENT"
            ? "Driver created. Mobile account provisioned and setup email sent."
            : created.onboarding.email_status === "NOT_SENT_MISSING_EMAIL"
              ? "Driver and mobile account created, but no setup email was sent because the driver email is missing."
              : "Driver and mobile account created, but the setup email could not be sent.",
        );
      }
      setDrivers((items) =>
        formMode === "edit"
          ? items.map((item) => (item.id === saved.id ? saved : item))
          : [saved, ...items],
      );
      setSelected(saved);
      setFormMode(null);
    } catch (error) {
      setFormError(saveError(error));
    } finally {
      setSaving(false);
    }
  };
  const upload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    setUploading(true);
    try {
      const saved = await createDriverDocument(
        selected.id,
        new FormData(event.currentTarget),
      );
      setDocuments((items) => [saved, ...items]);
      event.currentTarget.reset();
    } finally {
      setUploading(false);
    }
  };
  return (
    <section className="drivers-page drivers-page--workspace">
      <header className="d-flex justify-content-between align-items-start gap-3">
        <div>
          <p className="breadcrumb text-secondary small mb-1">
            Fleet &amp; Safety / Drivers
          </p>
          <h1 className="mb-1">Drivers &amp; Safety Scores</h1>
        </div>
        <div className="drivers-header-actions">
          {user?.role === "SUPER_ADMIN" && (
            <button
              className="btn-action--filled"
              onClick={() => {
                setFormError(null);
                setFormMode("add");
              }}
            >
              + Add Driver
            </button>
          )}
        </div>
      </header>
      {notice && (
        <p className="drivers-notice" role="status">
          {notice}
        </p>
      )}
      <div className="drivers-toolbar">
        <label className="drivers-search">
          Search
          <input
            aria-label="Search drivers"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name or driver code"
          />
        </label>
        <label>
          Employment
          <select
            value={employment}
            onChange={(e) => setEmployment(e.target.value)}
          >
            <option value="">All statuses</option>
            {employmentStatuses.map((value) => (
              <option key={value} value={value}>
                {words(value)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Eligibility
          <select
            value={eligibility}
            onChange={(e) => setEligibility(e.target.value)}
          >
            <option value="">All eligibility</option>
            {eligibilityStatuses.map((value) => (
              <option key={value} value={value}>
                {words(value)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="drivers-workspace">
        <section className="driver-list" aria-label="Driver registry">
          <header>
            <strong>Driver registry</strong>
            <span>{count} drivers</span>
          </header>
          {state === "loading" && (
            <LoadingIndicator variant="card" message="Loading drivers…" />
          )}
          {state === "error" && <p role="alert">Unable to load drivers.</p>}
          {state === "ready" && drivers.length === 0 && (
            <p>No driver records available.</p>
          )}
          {drivers.map((driver) => (
            <button
              key={driver.id}
              className={selected?.id === driver.id ? "selected" : ""}
              onClick={() => setSelected(driver)}
            >
              <span
                className={`driver-avatar driver-avatar--${driverEmploymentTone[driver.employment_status] ?? "neutral"}`}
              >
                {driver.first_name[0]}
                {driver.last_name[0]}
              </span>
              <span>
                <strong>{driver.full_name}</strong>
                <small>{driver.driver_code}</small>
              </span>
              <span>
                <StatusBadge
                  status={driver.eligibility_status}
                  tone={
                    driverEligibilityTone[driver.eligibility_status] ??
                    "neutral"
                  }
                />
              </span>
            </button>
          ))}
        </section>
        <section className="driver-detail">
          {!selected ? (
            <div className="driver-empty">
              Select a driver to view their operational record.
            </div>
          ) : (
            <>
              <header>
                <span
                  className={`driver-avatar driver-avatar--${driverEmploymentTone[selected.employment_status] ?? "neutral"}`}
                >
                  {selected.first_name[0]}
                  {selected.last_name[0]}
                </span>
                <div>
                  <h2>{selected.full_name}</h2>
                  <small>{selected.driver_code}</small>
                </div>
                <span>
                  <StatusBadge
                    status={selected.employment_status}
                    tone={
                      driverEmploymentTone[selected.employment_status] ??
                      "neutral"
                    }
                  />
                </span>
                <span>
                  <StatusBadge
                    status={selected.eligibility_status}
                    tone={
                      driverEligibilityTone[selected.eligibility_status] ??
                      "neutral"
                    }
                  />
                </span>
                <span className="driver-safety-score">
                  <small>Safety score</small>
                  <strong>—</strong>
                </span>
                {user?.role !== "DISPATCHER" && (
                  <button
                    className="btn-action--filled"
                    onClick={() => {
                      setFormError(null);
                      setFormMode("edit");
                    }}
                  >
                    Edit
                  </button>
                )}
              </header>
              <nav className="nav nav-pills driver-tabs" role="tablist">
                {[
                  "overview",
                  "eligibility",
                  "credentials",
                  "safety",
                  "documents",
                ].map((value) => (
                  <button
                    key={value}
                    role="tab"
                    className={`nav-link${tab === value ? " active" : ""}`}
                    aria-selected={tab === value}
                    onClick={() => setTab(value)}
                  >
                    {words(value)}
                  </button>
                ))}
              </nav>
              <div className="driver-tab-panel">
                {tab === "overview" && (
                  <>
                    <DriverData
                      title="Identity"
                      values={[
                        ["Driver code", selected.driver_code],
                        ["Full name", selected.full_name],
                        [
                          "Contact number",
                          selected.contact_number || "Not recorded",
                        ],
                        ["Email", selected.email || "Not recorded"],
                        [
                          "Employment status",
                          words(selected.employment_status),
                        ],
                        ["Date hired", selected.date_hired || "Not recorded"],
                      ]}
                    />
                    <DriverData
                      title="Integration References"
                      values={[
                        ["HR reference", shown(selected.external_hr_id)],
                        [
                          "Driver Mobile account",
                          shown(selected.linked_user_display),
                        ],
                      ]}
                    />
                  </>
                )}
                {tab === "eligibility" && (
                  <>
                    <h3>{words(selected.eligibility_status)}</h3>
                    {selected.eligibility_reasons.length ? (
                      <ul className="driver-eligibility-reasons">
                        {selected.eligibility_reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>All current readiness evidence is present.</p>
                    )}
                    <DriverData
                      title="Readiness evidence"
                      values={[
                        [
                          "Employment status",
                          words(selected.employment_status),
                        ],
                        [
                          "License number",
                          selected.license_number || "Missing",
                        ],
                        [
                          "License expiry",
                          selected.license_expiry_date || "Missing",
                        ],
                        [
                          "Medical certificate expiry",
                          selected.medical_certificate_expiry_date || "Missing",
                        ],
                      ]}
                    />
                    <p>Safety Score is not currently used for eligibility.</p>
                    <p>
                      License-code and vehicle compatibility are not evaluated
                      yet.
                    </p>
                  </>
                )}
                {tab === "credentials" && (
                  <DriverData
                    title="Driver License & Medical Readiness"
                    values={[
                      ["Number", selected.license_number || "Missing"],
                      ["Category", selected.license_category || "Missing"],
                      ["License codes", selected.license_codes || "Missing"],
                      ["Issue date", selected.license_issue_date || "Missing"],
                      [
                        "Expiry date",
                        selected.license_expiry_date || "Missing",
                      ],
                      [
                        "Medical certificate expiry",
                        selected.medical_certificate_expiry_date || "Missing",
                      ],
                    ]}
                  />
                )}{" "}
                {tab === "safety" && (
                  <div className="driver-safety-empty">
                    <h3>Safety Score</h3>
                    <strong>—</strong>
                    <b>Not yet scored</b>
                    <p>
                      Safety scoring will become available when validated
                      driving-behavior and incident inputs are integrated.
                    </p>
                  </div>
                )}
                {tab === "documents" && (
                  <>
                    <div className="driver-documents">
                      {documents.length === 0 ? (
                        <p>No driver documents recorded.</p>
                      ) : (
                        documents.map((document) => (
                          <article key={document.id}>
                            <div>
                              <strong>{document.title}</strong>
                              <small>
                                {words(document.document_type)} ·{" "}
                                {document.reference_number || "No reference"}
                              </small>
                            </div>
                            <a
                              className="button btn-filter"
                              href={document.download_url}
                            >
                              View
                            </a>
                          </article>
                        ))
                      )}
                    </div>
                    {user?.role !== "DISPATCHER" && (
                      <form className="driver-upload" onSubmit={upload}>
                        <select name="document_type" aria-label="Document type">
                          {driverDocumentTypes.map((value) => (
                            <option key={value}>{value}</option>
                          ))}
                        </select>
                        <input
                          name="title"
                          aria-label="Document title"
                          placeholder="Document title"
                          required
                        />
                        <input
                          name="file"
                          aria-label="Document file"
                          type="file"
                          accept=".pdf,.jpg,.jpeg,.png"
                          required
                        />
                        <button className="btn-action--filled" disabled={uploading}>
                          {uploading ? "Uploading…" : "Upload Document"}
                        </button>
                      </form>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </section>
      </div>
      {formMode && (
        <div className="driver-drawer-backdrop">
          <aside
            className="driver-form-drawer"
            role="dialog"
            aria-label={formMode === "add" ? "Add Driver" : "Edit Driver"}
          >
            <header>
              <h2>{formMode === "add" ? "Add Driver" : "Edit Driver"}</h2>
              <button
                className="btn-cancel"
                aria-label="Close driver form"
                onClick={() => setFormMode(null)}
              >
                ×
              </button>
            </header>
            <DriverForm
              driver={formMode === "edit" ? selected : null}
              superAdmin={user?.role === "SUPER_ADMIN"}
              onSubmit={save}
              onCancel={() => setFormMode(null)}
              saving={saving}
              error={formError}
            />
          </aside>
        </div>
      )}
    </section>
  );
}
function DriverData({
  title,
  values,
}: {
  title: string;
  values: [string, string][];
}) {
  const missing = new Set(["Missing", "Not recorded", "Not linked"]);
  return (
    <section className="driver-data">
      <h3>{title}</h3>
      <dl>
        {values.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className={missing.has(value) ? "driver-value--missing" : ""}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
function DriverForm({
  driver,
  superAdmin,
  onSubmit,
  onCancel,
  saving,
  error,
}: {
  driver: Driver | null;
  superAdmin: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const initials = driver
    ? `${driver.first_name[0]}${driver.last_name[0]}`
    : "";
  return (
    <form className="driver-form" onSubmit={onSubmit}>
      <fieldset>
        <legend>Identity</legend>
        <label>
          Driver code
          <input
            name="driver_code"
            required
            defaultValue={driver?.driver_code}
          />
        </label>
        <label>
          First name
          <input name="first_name" required defaultValue={driver?.first_name} />
        </label>
        <label>
          Middle name
          <input name="middle_name" defaultValue={driver?.middle_name} />
        </label>
        <label>
          Last name
          <input name="last_name" required defaultValue={driver?.last_name} />
        </label>
        <label>
          Contact number
          <input name="contact_number" defaultValue={driver?.contact_number} />
        </label>
        <label>
          Email
          <input name="email" type="email" defaultValue={driver?.email} />
        </label>
        <div className="driver-photo-field">
          <span className="driver-photo-preview">
            {photoPreview ? (
              <img src={photoPreview} alt="Photo preview" />
            ) : (
              initials
            )}
          </span>
          <label>
            Photo
            <input
              ref={fileRef}
              name="photo"
              type="file"
              accept=".jpg,.jpeg,.png"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  setPhotoPreview(URL.createObjectURL(file));
                } else {
                  setPhotoPreview(null);
                }
              }}
            />
          </label>
        </div>
      </fieldset>
      <fieldset>
        <legend>Driver License & Medical Readiness</legend>
        <label>
          License number
          <input name="license_number" defaultValue={driver?.license_number} />
        </label>
        <label>
          Category
          <input
            name="license_category"
            defaultValue={driver?.license_category}
          />
        </label>
        <label>
          License codes
          <input name="license_codes" defaultValue={driver?.license_codes} />
        </label>
        <label>
          Issue date
          <input
            name="license_issue_date"
            type="date"
            defaultValue={driver?.license_issue_date ?? ""}
          />
        </label>
        <label>
          Expiry date
          <input
            name="license_expiry_date"
            type="date"
            defaultValue={driver?.license_expiry_date ?? ""}
          />
        </label>
        <label>
          Medical expiry
          <input
            name="medical_certificate_expiry_date"
            type="date"
            defaultValue={driver?.medical_certificate_expiry_date ?? ""}
          />
        </label>
      </fieldset>
      {superAdmin && (
        <fieldset>
          <legend>Employment & Integration</legend>
          <label>
            Employment status
            <select
              name="employment_status"
              defaultValue={driver?.employment_status ?? "ACTIVE"}
            >
              {employmentStatuses.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Date hired
            <input
              name="date_hired"
              type="date"
              defaultValue={driver?.date_hired ?? ""}
            />
          </label>
          <label>
            External HR ID
            <input
              name="external_hr_id"
              defaultValue={driver?.external_hr_id ?? ""}
            />
          </label>
          {driver ? (
            <label>
              Linked user ID
              <input
                name="linked_user"
                type="number"
                defaultValue={driver.linked_user ?? ""}
              />
            </label>
          ) : (
            <p>Driver Mobile account will be provisioned automatically.</p>
          )}
        </fieldset>
      )}
      {error && (
        <p className="message message--error alert alert-danger" role="alert">
          {error}
        </p>
      )}
      <footer>
        <button type="button" className="btn-cancel" onClick={onCancel}>
          Cancel
        </button>
        <button className="btn-confirm" disabled={saving}>
          {saving ? "Saving…" : "Save Driver"}
        </button>
      </footer>
    </form>
  );
}
