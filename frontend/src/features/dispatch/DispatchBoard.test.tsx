import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import DispatchBoardPage from "./DispatchBoardPage";
import { plannedPaths } from "../../app/navigation";

const request={id:"request-1",request_number:"TR-001",source_system:"HOTEL_MANAGEMENT_SYSTEM",external_reference:"HMS-1",request_type:"GUEST_TRANSFER",request_category:"PASSENGER_TRANSPORT",requester_name:"Front Desk",requester_contact:"",pickup_name:"Oxford Suites",pickup_address:"Makati",pickup_latitude:"14.5",pickup_longitude:"121",destination_name:"NAIA",destination_address:"Pasay",destination_latitude:"14.4",destination_longitude:"121.1",scheduled_pickup_at:"2026-08-14T02:00:00Z",required_vehicle_type:"VAN",estimated_duration_minutes:60,passenger_count:2,luggage_count:1,load_description:"",load_quantity:null,estimated_weight_kg:null,handling_instructions:"",temperature_requirement:"",priority:"NORMAL",notes:"",status:"APPROVED",assigned_vehicle:null,created_by:"Manager",approved_by:"Manager",approved_at:"2026-08-13T00:00:00Z",created_at:"2026-08-13T00:00:00Z",updated_at:"2026-08-13T00:00:00Z",latest_event_type:"APPROVED",latest_event_at:"2026-08-13T00:00:00Z"};
const secondRequest={...request,id:"request-2",request_number:"TR-002",external_reference:"HMS-2",pickup_name:"BGC",destination_name:"Oxford Suites"};
const driver={id:1,driver_code:"DRV-001",full_name:"Juan Dela Cruz",eligibility_status:"ELIGIBLE"};
const vehicle={id:1,device_id:"VAN-01",plate_number:"ABC-123",display_name:"Guest Van",vehicle_type:"VAN",passenger_capacity:8,is_active:true,current_location_available:true};
const board={summary:{approved_requests:1,awaiting_assignment:1,confirmed_assignments:0,ready_for_dispatch:0,optimizer_eligible:1,needs_attention:0,no_eligible_driver:0,no_gis_vehicle:0,schedule_conflict:0},requests:[request],assignments:[],eligible_drivers:[driver],active_vehicles:[vehicle],assignment_audit:{"request-1":[]}};
const recommendation={generated_at:"2026-08-14T00:00:00Z",optimizer:"GOOGLE_OR_TOOLS",routing_source:"TOMTOM",requests_considered:1,requests_recommended:1,recommendations:[{transport_request_id:"request-1",request_number:"TR-001",recommended_vehicle:vehicle,recommended_driver:driver,travel_time_seconds:600,distance_meters:5200,traffic_delay_seconds:60,recommendation_token:"signed",explanation:["Driver eligibility is ELIGIBLE","TomTom route/matrix cell is valid"],schedule_context:{selected:{start:"2026-08-14T02:00:00Z",end:"2026-08-14T03:00:00Z"},driver:{status:"AVAILABLE",windows:[]},vehicle:{status:"AVAILABLE",windows:[]}},gis_preview:{status:"METRICS_AVAILABLE",vehicle_location:{vehicle_id:"VAN-01",latitude:14.5,longitude:121},pickup:{latitude:"14.5",longitude:"121",label:"Oxford Suites"},destination:{latitude:"14.4",longitude:"121.1",label:"NAIA"},geometry:null}}],unassigned:[],candidate_comparison:{"request-1":[{driver,vehicle,travel_time_seconds:600,distance_meters:5200,traffic_delay_seconds:60,result:"RECOMMENDED"}]},excluded_candidates:{"request-1":[{kind:"VEHICLE",name:"Old Van",code:"OLD-01",reason:"NO_FRESH_TELEMETRY",details:["No fresh telemetry"]}]},comparison_scope:{limit:50,limited:false}};
const json=(value:unknown,status=200)=>Promise.resolve(new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}}));
const isOptimization=(input:RequestInfo|URL)=>String(input).endsWith("recommendations/");
const requestIds=(init?:RequestInit)=>JSON.parse(String(init?.body??"{}")).request_ids as string[]|undefined;
beforeEach(()=>vi.restoreAllMocks());

test("dispatch board is a real route rather than a planned module",()=>{
 expect(plannedPaths.some(item=>item.path==="/dispatch-board")).toBe(false);
});

test("renders the real approved queue and honest empty-safe dispatch controls",async()=>{
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>isOptimization(input)?json({...recommendation,recommendations:[],candidate_comparison:{},excluded_candidates:{},unassigned:[{transport_request_id:"request-1",request_number:"TR-001",reason:"No fresh vehicle telemetry"}]}):json(board));render(<DispatchBoardPage/>);
 expect(screen.getByText("Loading dispatch board…")).toBeInTheDocument();
 expect(await screen.findByText("TR-001")).toBeInTheDocument();
 expect((await screen.findAllByText("No fresh vehicle telemetry")).length).toBeGreaterThan(0);
 expect(screen.getByRole("button",{name:"Refresh Optimization"})).toBeInTheDocument();
 const call=fetchMock.mock.calls.find(([input])=>isOptimization(input));expect(requestIds(call?.[1])).toEqual(["request-1"]);
 expect(screen.queryByText(/Safety Score|Driver Accepted|Start Trip|Complete Trip/)).not.toBeInTheDocument();
});

test("shows OR-Tools recommendation with real TomTom metrics and confirms only on click",async()=>{
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>isOptimization(input)?json(recommendation):String(input).endsWith("confirm/")?json({id:1,transport_request_id:"request-1",request_number:"TR-001",vehicle,driver,selection_mode:"OPTIMIZED",override_reason:"",confirmed_by:"Operator",confirmed_at:"2026-08-14T00:01:00Z",created_at:"2026-08-14T00:01:00Z",updated_at:"2026-08-14T00:01:00Z"},201):json(board));
 render(<DispatchBoardPage/>);await screen.findByText("TR-001");
 expect((await screen.findAllByText("Juan Dela Cruz")).length).toBeGreaterThan(0);expect(screen.getAllByText("10 min").length).toBeGreaterThan(0);expect(screen.getAllByText("5.2 km").length).toBeGreaterThan(0);
 expect(fetchMock.mock.calls.some(call=>String(call[0]).endsWith("confirm/"))).toBe(false);
 fireEvent.click(screen.getByRole("button",{name:"Confirm Recommendation"}));
 expect(await screen.findByText("Confirmed Assignment")).toBeInTheDocument();
 expect(screen.getByRole("button",{name:"Prepare for Dispatch"})).toBeInTheDocument();
});

test("manual modification requires a reason and identifies no-location vehicles",async()=>{
 const noLocation={...vehicle,id:2,device_id:"VAN-02",current_location_available:false};
 vi.spyOn(globalThis,"fetch").mockImplementation(input=>isOptimization(input)?json({...recommendation,recommendations:[],candidate_comparison:{},excluded_candidates:{},unassigned:[]}):json({...board,active_vehicles:[noLocation]}));render(<DispatchBoardPage/>);await screen.findByText("TR-001");await waitFor(()=>expect(screen.getByRole("button",{name:"Refresh Optimization"})).toBeEnabled());
 fireEvent.click(screen.getByRole("button",{name:"Modify Assignment"}));
 fireEvent.change(screen.getByLabelText("Eligible Driver"),{target:{value:"1"}});fireEvent.change(screen.getByLabelText("Valid Vehicle"),{target:{value:"2"}});
 expect(screen.getByRole("option",{name:/Current location unavailable — manual assignment only/})).toBeInTheDocument();
 expect(screen.getByRole("button",{name:"Confirm Manual Assignment"})).toBeDisabled();
 fireEvent.change(screen.getByLabelText("Override reason"),{target:{value:"Guest requirement"}});
 await waitFor(()=>expect(screen.getByRole("button",{name:"Confirm Manual Assignment"})).toBeEnabled());
 expect(screen.queryByText(/ETA/)).not.toBeInTheDocument();
});

test("renders controlled recommendation errors and backend infeasibility reasons",async()=>{
 vi.spyOn(globalThis,"fetch").mockImplementation(input=>isOptimization(input)?json({...recommendation,recommendations:[],requests_recommended:0,unassigned:[{transport_request_id:"request-1",request_number:"TR-001",reason:"No fresh vehicle telemetry"}]}):json(board));render(<DispatchBoardPage/>);await screen.findByText("TR-001");expect((await screen.findAllByText("No fresh vehicle telemetry")).length).toBeGreaterThan(0);
});

test("renders explainability, candidates, GIS truth, schedules, and no fabricated safety score",async()=>{
 vi.spyOn(globalThis,"fetch").mockImplementation(input=>isOptimization(input)?json(recommendation):json(board));render(<DispatchBoardPage/>);await screen.findByText("TR-001");
 expect(await screen.findByText("Why recommended")).toBeInTheDocument();expect(screen.getByText("Candidate Comparison")).toBeInTheDocument();expect(screen.getByText("Why excluded")).toBeInTheDocument();expect(screen.getByText("No Fresh Telemetry")).toBeInTheDocument();expect(screen.getByText("GIS Recommendation Preview")).toBeInTheDocument();expect(screen.getByText(/no route line is drawn/i)).toBeInTheDocument();expect(screen.getByText("Resource Schedule")).toBeInTheDocument();expect(screen.getByText(/Driver timeline · AVAILABLE/)).toBeInTheDocument();expect(screen.getByText(/Vehicle timeline · AVAILABLE/)).toBeInTheDocument();expect(screen.queryByText(/Safety Score/)).not.toBeInTheDocument();
});

test("shows automatic optimization loading without any automatic confirmation",async()=>{
 let resolveOptimization:(value:Response)=>void=()=>{};const pending=new Promise<Response>(resolve=>{resolveOptimization=resolve});
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>isOptimization(input)?pending:json(board));render(<DispatchBoardPage/>);await screen.findByText("TR-001");
 expect(await screen.findByRole("status",{name:""})).toHaveTextContent("Optimizing assignment…");expect(screen.queryByRole("button",{name:"Confirm Recommendation"})).not.toBeInTheDocument();expect(fetchMock.mock.calls.some(([input])=>String(input).endsWith("confirm/"))).toBe(false);
 resolveOptimization(await json(recommendation));expect(await screen.findByRole("button",{name:"Confirm Recommendation"})).toBeInTheDocument();
});

test("changing approved selection optimizes only the new request and ignores a stale prior response",async()=>{
 let resolveFirst:(value:Response)=>void=()=>{};const firstPending=new Promise<Response>(resolve=>{resolveFirst=resolve});
 const secondRecommendation={...recommendation,recommendations:[{...recommendation.recommendations[0],transport_request_id:"request-2",request_number:"TR-002"}],candidate_comparison:{"request-2":recommendation.candidate_comparison["request-1"]},excluded_candidates:{"request-2":[]}};
 const twoRequestBoard={...board,requests:[request,secondRequest],summary:{...board.summary,approved_requests:2,awaiting_assignment:2,optimizer_eligible:2},assignment_audit:{"request-1":[],"request-2":[]}};
 const calls:string[][]=[];vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{if(!isOptimization(input))return json(twoRequestBoard);const ids=requestIds(init)??[];calls.push(ids);return ids[0]==="request-1"?firstPending:json(secondRecommendation)});
 render(<DispatchBoardPage/>);await screen.findByText("TR-001");fireEvent.click(screen.getByRole("button",{name:/TR-002 Guest Transfer/}));expect(await screen.findByRole("heading",{level:2,name:"TR-002"})).toBeInTheDocument();
 resolveFirst(await json(recommendation));await waitFor(()=>expect(screen.getByRole("heading",{level:2,name:"TR-002"})).toBeInTheDocument());expect(calls).toEqual([["request-1"],["request-2"]]);
});

test("does not auto-optimize non-approved or already confirmed requests",async()=>{
 const ready={...request,status:"READY_FOR_DISPATCH"};const confirmed={...board,requests:[ready],assignments:[{id:1,transport_request_id:"request-1",request_number:"TR-001",vehicle,driver,selection_mode:"MANUAL",override_reason:"Fixture",confirmed_by:"Operator",confirmed_at:"2026-08-14T00:01:00Z",created_at:"2026-08-14T00:01:00Z",updated_at:"2026-08-14T00:01:00Z"}]};
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(()=>json(confirmed));render(<DispatchBoardPage/>);await screen.findByText("TR-001");await waitFor(()=>expect(screen.getByText("Confirmed Assignment")).toBeInTheDocument());expect(fetchMock.mock.calls.some(([input])=>isOptimization(input))).toBe(false);expect(screen.getByRole("button",{name:"Refresh Optimization"})).toBeDisabled();
});

test("shows controlled auto-optimization error and allows explicit retry",async()=>{
 let attempts=0;vi.spyOn(globalThis,"fetch").mockImplementation(input=>{if(!isOptimization(input))return json(board);attempts+=1;return attempts===1?json({detail:"Dispatch matrix is temporarily unavailable."},502):json(recommendation)});render(<DispatchBoardPage/>);await screen.findByText("TR-001");expect(await screen.findByText("API request failed (502)")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"Refresh Optimization"}));expect(await screen.findByRole("button",{name:"Confirm Recommendation"})).toBeInTheDocument();expect(attempts).toBe(2);
});

test("renders a truthful Smart Consolidation recommendation and keeps it non-persistent",async()=>{
 const delivery={...request,request_type:"SUPPLIER_PICKUP",request_category:"DELIVERY_LOGISTICS",passenger_count:0,estimated_weight_kg:"400.00",load_description:"Supplies"};
 const deliveryBoard={...board,requests:[delivery]};
 const consolidation={generated_at:"2026-08-14T00:00:00Z",optimizer:"GOOGLE_OR_TOOLS_ROUTING_MODEL",routing_source:"TOMTOM",candidate_limit:4,exclusions:[],recommendation:{request_ids:["request-1","request-2"],requests:[delivery,{...delivery,id:"request-2",request_number:"TR-002",estimated_weight_kg:"300.00"}],driver,vehicle,route:{stops:[{sequence:1,request_id:"request-1",request_number:"TR-001",stop_type:"PICKUP",label:"Oxford Suites",latitude:"14.5",longitude:"121",load_change_kg:"400.00"},{sequence:2,request_id:"request-2",request_number:"TR-002",stop_type:"PICKUP",label:"BGC",latitude:"14.5",longitude:"121",load_change_kg:"300.00"},{sequence:3,request_id:"request-1",request_number:"TR-001",stop_type:"DELIVERY",label:"NAIA",latitude:"14.4",longitude:"121.1",load_change_kg:"-400.00"},{sequence:4,request_id:"request-2",request_number:"TR-002",stop_type:"DELIVERY",label:"Oxford Suites",latitude:"14.4",longitude:"121.1",load_change_kg:"-300.00"}],peak_load_kg:"700.00",capacity_kg:"1000.00",capacity_utilization_percent:70,separate:{vehicles:2,travel_time_seconds:5640,distance_meters:61000},consolidated:{vehicles:1,travel_time_seconds:4320,distance_meters:43000},difference:{vehicles:1,travel_time_seconds:1320,distance_meters:18000}},explanation:["Peak load remains within payload capacity."],recommendation_token:"signed-consolidation",geometry:null}};
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("consolidation-recommendations")?json(consolidation):isOptimization(input)?json({...recommendation,recommendations:[{...recommendation.recommendations[0],recommended_vehicle:vehicle}]}):json(deliveryBoard));
 render(<DispatchBoardPage/>);expect(await screen.findByText("Optimized consolidation recommendation")).toBeInTheDocument();expect(screen.getByText("700.00 / 1000.00 kg")).toBeInTheDocument();expect(screen.getByText(/2 vehicles · 61.0 km · 94 min/)).toBeInTheDocument();expect(screen.getByText(/1 vehicle · 43.0 km · 72 min/)).toBeInTheDocument();expect(screen.getByText(/Multi-stop geometry unavailable/)).toBeInTheDocument();expect(screen.queryByText(/₱|fuel saved|emissions saved/i)).not.toBeInTheDocument();expect(fetchMock.mock.calls.some(([input])=>String(input).includes("consolidations/confirm"))).toBe(false);
 fireEvent.click(screen.getByRole("button",{name:"Keep Separate"}));expect(screen.queryByText("Optimized consolidation recommendation")).not.toBeInTheDocument();expect(fetchMock.mock.calls.some(([input])=>String(input).includes("consolidations/confirm"))).toBe(false);
});

test("renders backend consolidation exclusions without frontend guessing",async()=>{
 const delivery={...request,request_type:"SUPPLIER_PICKUP",request_category:"DELIVERY_LOGISTICS",passenger_count:0,estimated_weight_kg:"400.00",load_description:"Supplies"};
 vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("consolidation-recommendations")?json({generated_at:"2026-08-14T00:00:00Z",optimizer:"GOOGLE_OR_TOOLS_ROUTING_MODEL",routing_source:"TOMTOM",candidate_limit:4,recommendation:null,exclusions:["TR-002: Combined load exceeds vehicle payload."]}):isOptimization(input)?json(recommendation):json({...board,requests:[delivery]}));
 render(<DispatchBoardPage/>);expect(await screen.findByText("No feasible consolidation opportunity.")).toBeInTheDocument();expect(screen.getByText("Why not?")).toBeInTheDocument();expect(screen.getByText("TR-002: Combined load exceeds vehicle payload.")).toBeInTheDocument();
});
