import { KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { ApiError } from "../../../services/api";
import { getPlaceDetails, suggestPlaces } from "../api";
import type { PlaceDetails, PlaceSuggestion } from "../types";
import LoadingIndicator from "../../../components/common/LoadingIndicator";

let fallbackSession = 0;
const newSessionId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  fallbackSession += 1;
  return `00000000-0000-4000-8000-${String(fallbackSession).padStart(12, "0")}`;
};

type Props = {
  kind: "pickup" | "destination";
  initialName?: string; initialAddress?: string; initialLatitude?: string; initialLongitude?: string;
  errors: Record<string, string>;
};

export default function LocationAutocomplete({ kind, initialName = "", initialAddress = "", initialLatitude = "", initialLongitude = "", errors }: Props) {
  const title = kind === "pickup" ? "Pickup" : "Destination"; const listId = useId(); const rootRef = useRef<HTMLDivElement>(null);
  const [name, setName] = useState(initialName); const [address, setAddress] = useState(initialAddress); const [latitude, setLatitude] = useState(initialLatitude); const [longitude, setLongitude] = useState(initialLongitude);
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]); const [open, setOpen] = useState(false); const [active, setActive] = useState(-1); const [status, setStatus] = useState<"idle" | "loading" | "empty" | "error" | "unavailable" | "select-error">("idle");
  const sessionRef = useRef<string | null>(null); const selectedRef = useRef<string | null>(initialAddress ? initialAddress : null); const detailsControllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const close = (event: PointerEvent) => { if (!rootRef.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close); return () => { document.removeEventListener("pointerdown", close); detailsControllerRef.current?.abort(); };
  }, []);
  useEffect(() => {
    const query = address.trim(); if (selectedRef.current === address) return;
    if (query.length < 3) return;
    sessionRef.current ??= newSessionId(); const controller = new AbortController();
    const timer = window.setTimeout(() => { void suggestPlaces(query, sessionRef.current!, controller.signal).then(result => { setSuggestions(result.results.slice(0, 5)); setActive(-1); setStatus(result.results.length ? "idle" : "empty"); }).catch(error => { if (error instanceof DOMException && error.name === "AbortError") return; setSuggestions([]); setStatus(error instanceof ApiError && [429, 503].includes(error.status) ? "unavailable" : "error"); }); }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [address]);
  const changeAddress = (value: string) => { detailsControllerRef.current?.abort(); selectedRef.current = null; setAddress(value); setLatitude(""); setLongitude(""); setActive(-1); if (value.trim().length < 3) { setSuggestions([]); setOpen(false); setStatus("idle"); } else { setOpen(true); setStatus("loading"); } };
  const select = async (suggestion: PlaceSuggestion) => {
    const sessionId = sessionRef.current; if (!sessionId) return; detailsControllerRef.current?.abort(); const controller = new AbortController(); detailsControllerRef.current = controller; setStatus("loading");
    try { const detail: PlaceDetails = await getPlaceDetails(suggestion.type, suggestion.id, sessionId, controller.signal); setName(detail.title); setAddress(detail.display_address); setLatitude(String(detail.latitude)); setLongitude(String(detail.longitude)); selectedRef.current = detail.display_address; setSuggestions([]); setOpen(false); setStatus("idle"); sessionRef.current = null; }
    catch (error) { if (!(error instanceof DOMException && error.name === "AbortError")) setStatus("select-error"); }
    finally { if (detailsControllerRef.current === controller) detailsControllerRef.current = null; }
  };
  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") { setOpen(false); setActive(-1); return; }
    if (!open || !suggestions.length) return;
    if (event.key === "ArrowDown") { event.preventDefault(); setActive(value => Math.min(value + 1, suggestions.length - 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive(value => Math.max(value - 1, 0)); }
    else if (event.key === "Enter" && active >= 0) { event.preventDefault(); void select(suggestions[active]); }
  };
  const fieldError = (field: string) => errors[field] && <small className="field-error" role="alert">{errors[field]}</small>;
  return (
    <fieldset className="form-section">
      <legend>{title}</legend>
      <label>
        {title} name
        <input
          name={`${kind}_name`}
          required
          value={name}
          onChange={event => setName(event.target.value)}
        />
        {fieldError(`${kind}_name`)}
      </label>
      <div ref={rootRef} className="location-autocomplete-field">
        <label className="edit-field--wide">
          {title} address
          <input
            name={`${kind}_address`}
            required
            value={address}
            onChange={event => changeAddress(event.target.value)}
            onKeyDown={keyDown}
            onFocus={() => {
              if (address.trim().length >= 3 && selectedRef.current !== address) setOpen(true);
            }}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={open}
            aria-controls={listId}
            aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          />
        </label>
        {fieldError(`${kind}_address`)}
        <input type="hidden" name={`${kind}_latitude`} value={latitude} />
        <input type="hidden" name={`${kind}_longitude`} value={longitude} />
        {fieldError(`${kind}_latitude`)}
        {fieldError(`${kind}_longitude`)}
        {open && (
          <div id={listId} className="location-suggestions" role="listbox" aria-label={`${title} location suggestions`}>
            {status === "loading" ? (
              <div className="location-suggestion-state" role="status"><LoadingIndicator size="sm" message="Searching locations…" /></div>
            ) : status === "empty" ? (
              <div className="location-suggestion-state">No matching locations found.</div>
            ) : status === "error" ? (
              <div className="location-suggestion-state" role="alert">Unable to search locations.</div>
            ) : status === "unavailable" ? (
              <div className="location-suggestion-state" role="alert">Location search temporarily unavailable.</div>
            ) : status === "select-error" ? (
              <div className="location-suggestion-state" role="alert">Unable to select this location.</div>
            ) : suggestions.map((suggestion, index) => (
              <button
                type="button"
                role="option"
                id={`${listId}-${index}`}
                aria-selected={active === index}
                className={active === index ? "active" : ""}
                key={`${suggestion.type}:${suggestion.id}`}
                onMouseEnter={() => setActive(index)}
                onClick={() => void select(suggestion)}
              >
                <strong>{suggestion.title}</strong>
                {suggestion.subtitles.map(value => (
                  <small key={value}>{value}</small>
                ))}
              </button>
            ))}
          </div>
        )}
      </div>
    </fieldset>
  );
}
