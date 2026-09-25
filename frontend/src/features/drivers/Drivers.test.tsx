import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import App from "../../App";

const auth=vi.hoisted(()=>({user:{id:1,username:"dispatch",display_name:"Dispatcher",role:"DISPATCHER"},loading:false,signIn:vi.fn(),signOut:vi.fn(),expire:vi.fn()}));
vi.mock("../../contexts/AuthContext",()=>({useAuth:()=>auth}));
const driver={id:1,driver_code:"DRV-001",external_hr_id:null,first_name:"Juan",middle_name:"",last_name:"Dela Cruz",full_name:"Juan Dela Cruz",contact_number:"0917",email:"juan@example.test",photo_url:null,employment_status:"ACTIVE",date_hired:null,linked_user:null,linked_user_display:null,license_number:"N01",license_category:"",license_codes:"",license_issue_date:null,license_expiry_date:"2027-08-13",medical_certificate_expiry_date:"2027-08-13",work_shift:"DAY",shift_label:"Day Shift",shift_hours:"06:00 AM – 06:00 PM",weekly_rest_days:["MONDAY","THURSDAY"],schedule_status:"ON_SHIFT",eligibility_status:"ELIGIBLE",eligibility_reasons:[],safety_score:null,safety_score_status:"NOT_SCORED",created_at:"2026-08-13T00:00:00Z",updated_at:"2026-08-13T00:00:00Z"};
const json=(value:unknown,status=200)=>Promise.resolve(new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}}));
const renderPage=()=>render(<MemoryRouter initialEntries={["/drivers"]}><App/></MemoryRouter>);
beforeEach(()=>{auth.user={id:1,username:"dispatch",display_name:"Dispatcher",role:"DISPATCHER"};vi.restoreAllMocks()});

test("renders real driver split view and honest safety/eligibility details",async()=>{
 vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("documents")?json({count:0,next:null,previous:null,results:[]}):json({count:1,next:null,previous:null,results:[driver]}));renderPage();
 expect((await screen.findAllByText("Juan Dela Cruz")).length).toBeGreaterThan(1);expect(screen.queryByText("Planned module")).not.toBeInTheDocument();expect(screen.queryByText("+ Add Driver")).not.toBeInTheDocument();
 expect(within(screen.getByLabelText("Driver safety score")).getByText("—")).toBeInTheDocument();
 fireEvent.click(screen.getByRole("tab",{name:"Safety"}));const panel=screen.getByText("Safety scoring will become available when validated driving-behavior and incident inputs are integrated.").parentElement!;expect(panel).toHaveTextContent("—");expect(panel).toHaveTextContent("Not yet scored");expect(panel.textContent).not.toMatch(/\b\d{1,3}\s*\/\s*100\b/);
 fireEvent.click(screen.getByRole("tab",{name:"Eligibility"}));expect(screen.queryByText("All current readiness evidence is present.")).not.toBeInTheDocument();expect(screen.queryByText("Safety Score is not currently used for eligibility.")).not.toBeInTheDocument();expect(screen.queryByText("License-code and vehicle compatibility are not evaluated yet.")).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("tab",{name:"Overview"}));expect(screen.getAllByText("Not linked")).toHaveLength(2);
 expect(screen.queryByText("External Workforce/HRMS schedules become authoritative when that integration is available.")).not.toBeInTheDocument();
});
test("supports empty state, search and filters",async()=>{const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(()=>json({count:0,next:null,previous:null,results:[]}));renderPage();expect(await screen.findByText("No driver records available.")).toBeInTheDocument();fireEvent.change(screen.getByLabelText("Search drivers"),{target:{value:"Juan"}});fireEvent.change(screen.getByLabelText("Employment"),{target:{value:"ACTIVE"}});fireEvent.change(screen.getByLabelText("Eligibility"),{target:{value:"ELIGIBLE"}});await waitFor(()=>expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("eligibility_status=ELIGIBLE"))});
test("role controls expose manager documents and super admin creation",async()=>{vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("documents")?json({count:0,next:null,previous:null,results:[]}):json({count:1,next:null,previous:null,results:[driver]}));auth.user.role="FLEET_MANAGER";const rendered=renderPage();await screen.findAllByText("Juan Dela Cruz");expect(screen.getByText("Edit")).toBeInTheDocument();fireEvent.click(screen.getByRole("tab",{name:"Documents"}));expect(await screen.findByText("Upload Document")).toBeInTheDocument();rendered.unmount();auth.user.role="FLEET_ADMIN";renderPage();expect(await screen.findByText("+ Add Driver")).toBeInTheDocument();fireEvent.click(screen.getByText("+ Add Driver"));expect(screen.getByRole("dialog",{name:"Add Driver"})).toBeInTheDocument()});
test("selection updates the detail pane and credentials render",async()=>{const second={...driver,id:2,driver_code:"DRV-002",first_name:"Maria",last_name:"Santos",full_name:"Maria Santos",license_number:"N02"};vi.spyOn(globalThis,"fetch").mockImplementation(()=>json({count:2,next:null,previous:null,results:[driver,second]}));renderPage();await screen.findByRole("button",{name:/Maria Santos/});fireEvent.click(screen.getByRole("button",{name:/Maria Santos/}));const detail=screen.getByRole("heading",{name:"Maria Santos"}).closest("header")!;expect(within(detail).getByText("DRV-002")).toBeInTheDocument();fireEvent.click(screen.getByRole("tab",{name:"Credentials"}));expect(screen.getByText("N02")).toBeInTheDocument()});

test("shows an authoritative real safety score in the driver header",async()=>{
 const scored={...driver,safety_score:87,safety_score_status:"REAL_SCORED",safety_score_source:"REAL"};
 vi.spyOn(globalThis,"fetch").mockImplementation(()=>json({count:1,next:null,previous:null,results:[scored]}));renderPage();await screen.findAllByText("Juan Dela Cruz");expect(within(screen.getByLabelText("Driver safety score")).getByText("87")).toBeInTheDocument();fireEvent.click(screen.getByRole("tab",{name:"Safety"}));const safetyPanel=screen.getByRole("heading",{name:"Safety Score"}).parentElement!;expect(within(safetyPanel).getByText("87")).toBeInTheDocument();
});

test("renders the professional demo safety profile and event history",async()=>{
 const history=Array.from({length:11},(_,index)=>({id:index+1,occurred_at:`2026-08-${String(20-index).padStart(2,"0")}T08:00:00Z`,event_type:"HARSH_BRAKING",event_label:index===10?"Sharp Turn":`Harsh Braking ${index+1}`,source:"DEMO_SEED"}));
 const demo={...driver,safety_score:92,safety_score_status:"DEMO_SCORED",safety_score_source:"DEMO_SEED",safety_completed_trips:180,safety_driving_hours:245,safety_event_count:40,safety_events_per_hour:0.1633,safety_event_counts:{HARSH_BRAKING:14},safety_history:history};
 vi.spyOn(globalThis,"fetch").mockImplementation(()=>json({count:1,next:null,previous:null,results:[demo]}));renderPage();await screen.findAllByText("Juan Dela Cruz");expect(within(screen.getByLabelText("Driver safety score")).getByText("92")).toBeInTheDocument();fireEvent.click(screen.getByRole("tab",{name:"Safety"}));const safetyProfile=screen.getByText("Demo safety dataset").parentElement!;expect(within(safetyProfile).getByText("92")).toBeInTheDocument();expect(screen.getByText("Harsh Braking 1")).toBeInTheDocument();expect(screen.getByText("Completed Trips").parentElement).toHaveTextContent("180");const pager=screen.getByText("Page 1 of 2").parentElement!;expect(screen.queryByText("Sharp Turn")).not.toBeInTheDocument();fireEvent.click(within(pager).getByRole("button",{name:"Next"}));expect(screen.getByText("Sharp Turn")).toBeInTheDocument();expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
});

test("paginates the authoritative registry without duplicate rows and updates selection", async () => {
 const first={...driver,id:1,driver_code:"DRV-PH-0001",full_name:"Adrian Aquino Abad",first_name:"Adrian",middle_name:"Aquino",last_name:"Abad"};
 const second={...driver,id:21,driver_code:"OLD-HISTORY-001",full_name:"Legacy Operator",first_name:"Legacy",last_name:"Operator",employment_status:"TERMINATED"};
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>{
  const url=String(input); const page=new URL(url,"http://localhost").searchParams.get("page") ?? "1";
  return page==="2"
   ? json({count:174,next:"?page=3&page_size=20",previous:"?page=1&page_size=20",results:[second]})
   : json({count:174,next:"?page=2&page_size=20",previous:null,results:[first]});
 });
 renderPage();
 expect(await screen.findByText("Showing 1–20 of 174")).toBeInTheDocument();
 const registry=screen.getByRole("region",{name:"Driver registry"});
 expect(within(registry).getByText("DRV-PH-0001")).toBeInTheDocument();
 fireEvent.click(within(registry).getByRole("button",{name:"Next"}));
 expect(await screen.findByText("Showing 21–40 of 174")).toBeInTheDocument();
 expect(within(registry).getByText("OLD-HISTORY-001")).toBeInTheDocument();
 expect(within(registry).queryByText("DRV-PH-0001")).not.toBeInTheDocument();
 expect(screen.getByRole("heading",{name:"Legacy Operator"})).toBeInTheDocument();
 fireEvent.click(within(registry).getByRole("button",{name:"Previous"}));
 expect(await screen.findByText("Showing 1–20 of 174")).toBeInTheDocument();
 expect(within(registry).getByText("DRV-PH-0001")).toBeInTheDocument();
 expect(fetchMock.mock.calls.some(([input])=>String(input).includes("page=2")&&String(input).includes("page_size=20"))).toBe(true);
});

test("search and driver filters reset pagination and use filtered backend totals", async () => {
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>{
  const params=new URL(String(input),"http://localhost").searchParams;
  if(params.get("eligibility_status")==="RESTRICTED") return json({count:0,next:null,previous:null,results:[]});
  if(params.get("employment_status")==="TERMINATED") return json({count:23,next:"?page=2",previous:null,results:[{...driver,id:90,driver_code:"OLD-HISTORY-001",full_name:"Legacy Operator",first_name:"Legacy",last_name:"Operator",employment_status:"TERMINATED"}]});
  if(params.get("search")==="ALJOHN") return json({count:1,next:null,previous:null,results:[{...driver,id:101,driver_code:"123-GFD",full_name:"ALJOHN ANDAMON MARIANO",first_name:"ALJOHN",middle_name:"ANDAMON",last_name:"MARIANO",eligibility_status:"RESTRICTED"}]});
  if(params.get("page")==="2") return json({count:174,next:"?page=3",previous:"?page=1",results:[{...driver,id:21,driver_code:"DRV-PH-0021"}]});
  return json({count:174,next:"?page=2",previous:null,results:[driver]});
 });
 renderPage(); await screen.findByText("Showing 1–20 of 174");
 const registry=screen.getByRole("region",{name:"Driver registry"});
 fireEvent.click(within(registry).getByRole("button",{name:"Next"}));
 await screen.findByText("Page 2 of 9");
 fireEvent.change(screen.getByLabelText("Search drivers"),{target:{value:"ALJOHN"}});
 expect(await screen.findByText("Showing 1–1 of 1")).toBeInTheDocument();
 expect(screen.getByRole("heading",{name:"ALJOHN ANDAMON MARIANO"})).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText("Employment"),{target:{value:"TERMINATED"}});
 await waitFor(()=>expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("page=1"));
 fireEvent.change(screen.getByLabelText("Search drivers"),{target:{value:""}});
 expect(await screen.findByText("Showing 1–20 of 23")).toBeInTheDocument();
 expect(screen.getByRole("heading",{name:"Legacy Operator"})).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText("Eligibility"),{target:{value:"RESTRICTED"}});
 expect(await screen.findByText("No driver records available.")).toBeInTheDocument();
 expect(screen.getByText("Showing 0–0 of 0")).toBeInTheDocument();
 expect(fetchMock.mock.calls.at(-1)?.[0].toString()).toContain("page=1");
});
