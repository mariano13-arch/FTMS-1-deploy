export const statuses = ["FOR_APPROVAL", "NEEDS_MORE_DETAILS", "APPROVED", "REJECTED", "READY_FOR_DISPATCH", "CANCELLED"] as const;
export const priorities = ["LOW", "NORMAL", "HIGH", "URGENT"] as const;
export const requestTypes = ["AIRPORT_PICKUP", "AIRPORT_DROPOFF", "GUEST_TRANSFER", "VIP_TRANSPORT", "STAFF_SHUTTLE", "SUPPLIER_PICKUP", "FOOD_DELIVERY", "CATERING_DELIVERY", "BANQUET_LOGISTICS", "BRANCH_TRANSFER", "OTHER"] as const;
export const sourceSystems = ["HOTEL_MANAGEMENT_SYSTEM", "RESTAURANT_MANAGEMENT_SYSTEM", "MANUAL_STAFF_ENTRY", "OTHER_SUBSYSTEM"] as const;
export const vehicleTypes = ["SEDAN", "SUV", "VAN", "SHUTTLE_BUS", "SERVICE_TRUCK", "MOTORCYCLE", "OTHER"] as const;
export type RequestStatus = typeof statuses[number];
export type AssignedVehicle = { id?: number; device_id: string; plate_number: string; display_name: string; vehicle_type: string; passenger_capacity: number | null; is_active: boolean };
export type TransportEvent = { id: number; event_type: string; previous_status: string; new_status: string; performed_by: string; note: string; created_at: string };
export type TransportRequestBase = {
  id: string; request_number: string; source_system: string; external_reference: string; request_type: string;
  request_category: "PASSENGER_TRANSPORT" | "DELIVERY_LOGISTICS" | null;
  requester_name: string; requester_contact: string; pickup_name: string; pickup_address: string;
  pickup_latitude: string; pickup_longitude: string; destination_name: string; destination_address: string;
  destination_latitude: string; destination_longitude: string; scheduled_pickup_at: string;
  required_vehicle_type: string; estimated_duration_minutes: number; passenger_count: number;
  luggage_count: number; load_description: string; load_quantity: number | null;
  estimated_weight_kg: string | null; handling_instructions: string;
  temperature_requirement: string; priority: string; notes: string; status: RequestStatus;
  assigned_vehicle: AssignedVehicle | null; created_by: string; approved_by: string | null; approved_at: string | null;
  created_at: string; updated_at: string;
};
export type TransportRequestListItem = TransportRequestBase & { latest_event_type: string | null; latest_event_at: string | null };
export type TransportRequest = TransportRequestBase & { events: TransportEvent[] };
export type CalendarRequest = TransportRequestBase & { calendar_date: string; planning_end_at: string; vehicle_conflict: boolean; conflicting_requests: string[] };
export type RequestPage = { count: number; next: string | null; previous: string | null; results: TransportRequestListItem[] };
export type TransportRoute = {
  request_id: string; traffic_mode: "live"; distance_meters: number; duration_seconds: number;
  traffic_delay_seconds: number; departure_time: string; arrival_time: string;
  geometry: { type: "LineString"; coordinates: [number, number][] };
};
export type PlaceSuggestion = { id: string; type: "poi" | "address" | "street" | "intersection" | "area"; title: string; subtitles: string[] };
export type PlaceSuggestions = { results: PlaceSuggestion[] };
export type PlaceDetails = PlaceSuggestion & { display_address: string; latitude: number; longitude: number };
export type Summary = {
  total: number; for_approval: number; needs_more_details: number; approval_queue: number;
  dispatch_queue: number; approved_unassigned: number; approved_assigned: number;
  ready_for_dispatch: number; scheduled_today: number; high_priority: number;
};
export type CalendarResponse = { start: string; end: string; timezone: string; results: CalendarRequest[] };
