import axios from "axios";

export const api = axios.create({
  baseURL: "",
  timeout: 15000,
  withCredentials: true,
});

api.interceptors.request.use((cfg) => {
  try {
    const raw = localStorage.getItem("club");
    if (raw) {
      const c = JSON.parse(raw);
      if (c?.name) cfg.headers["X-Org"] = c.name;
    }
  } catch {}
  // attach JWT if stored (fallback)
  const t = localStorage.getItem("access_token");
  if (t) cfg.headers["Authorization"] = `Bearer ${t}`;
  return cfg;
});

api.interceptors.response.use(
  (res) => {
    // store token if returned
    if (res.data?.access_token) try { localStorage.setItem("access_token", res.data.access_token); } catch {}
    return res;
  },
  (err) => {
    if (!err.response && err.code === "ECONNABORTED") {
      err.message = "Request timed out — backend may be down";
    }
    if (err.response?.status === 401 && !location.pathname.includes("/login")) {
      // auto-redirect to login on auth failure (but allow sandbox)
      // console.warn("401 -> login");
    }
    // Surface structured conflict errors
    if (err.response?.status === 409 && err.response?.data?.reason) {
      err.message = err.response.data.reason + (err.response.data.alternatives ? " Alternatives: " + JSON.stringify(err.response.data.alternatives) : "");
    }
    return Promise.reject(err);
  }
);

export type EventStatus = "draft" | "room_identified" | "pending_approval" | "live" | "closed";

export type Event = {
  id: string;
  org: string | null;
  title: string;
  date: string;
  start_time?: string | null;
  end_time?: string | null;
  expected_headcount: number;
  room?: string | null;
  room_capacity?: number | null;
  speaker?: string | null;
  purpose?: string | null;
  chairperson?: string | null;
  staff_in_charge?: string | null;
  need_onfoot?: boolean;
  status: EventStatus;
  form_id?: string | null;
  form_link?: string | null;
  sheet_link?: string | null;
  sheet_id?: string | null;
  form_fields_json?: string | null;
  announcement_draft?: string | null;
  permission_letter?: string | null;
  onfoot_letter?: string | null;
  email_draft?: string | null;
  permission_email_sent?: boolean;
  permission_email_message_id?: string | null;
  permission_email_sent_at?: string | null;
  registrant_count: number;
  created_at: string;
};

export type ChatReq = {
  message: string;
  event_id?: string;
  fields?: { title: string; type: string; required?: boolean; options?: string[] }[];
  description?: string;
  date?: string; // YYYY-MM-DD explicit picker (takes precedence)
  start_time?: string;
  end_time?: string;
  speaker?: string;
  purpose?: string;
  chairperson?: string;
  staff_in_charge?: string;
  need_onfoot?: boolean;
};

export type ChatResp = { response: string; event_id: string | null; status: EventStatus | string; permission_letter?: string | null; onfoot_letter?: string | null; announcement_draft?: string | null; email_draft?: string | null; permission_email_sent?: boolean; permission_email_message_id?: string | null; permission_email_sent_at?: string | null };
export type ApproveResp = { message: string; event: Event; agent_response?: string };
export type RegistrationResp = { event_id: string; count: number; source?: string; sheet_link?: string | null; sheet_id?: string | null; mock?: boolean; sync?: unknown };

export const chat = (data: ChatReq) => api.post<ChatResp>("/chat", data).then(r => r.data);
export const listEvents = (scope: "all" | "mine" = "all") => api.get<Event[]>(`/events?scope=${scope}`).then(r => r.data);
export const getEvent = (id: string) => api.get<Event>(`/events/${id}`).then(r => r.data);
export const approve = (id: string, approved: boolean) => api.post<ApproveResp>(`/events/${id}/approve`, { approved }).then(r => r.data);
export const sendPermission = (id: string, payload: { edited_email?: string; regenerate_instruction?: string }) =>
  api.post(`/events/${id}/send-permission-email`, payload).then(r => r.data);
export const getRegistrations = (id: string) => api.get<RegistrationResp>(`/events/${id}/registrations`).then(r => r.data);
export const syncEvent = (id: string) => api.post(`/events/${id}/sync`).then(r => r.data);

export type OrgSettings = {
  org: string;
  institution_name: string;
  institution_place: string;
  faculty_email: string;
  announcement_recipients: string;
  chairperson: string;
  staff_in_charge: string;
  updated_at?: string;
};

export const getSettings = (org: string) => api.get<OrgSettings>(`/settings/${encodeURIComponent(org)}`).then(r => r.data);
export const listSettings = () => api.get<OrgSettings[]>(`/settings`).then(r => r.data);
export const saveSettings = (org: string, data: OrgSettings) => api.put<OrgSettings>(`/settings/${encodeURIComponent(org)}`, data).then(r => r.data);

export type GoogleStatus = { org: string; connected: boolean; configured: boolean; missing_fields: string[]; token_file: string };
export const getGoogleStatus = (org: string) => api.get<GoogleStatus>(`/auth/google/status?org=${encodeURIComponent(org)}`).then(r => r.data);
export const getGoogleUrl = (org: string) => api.get<{url:string|null; connected?:boolean; error?:string; fallback?:string}>(`/auth/google/url?org=${encodeURIComponent(org)}`).then(r => r.data);
export const disconnectGoogle = (org: string) => api.post(`/auth/google/disconnect?org=${encodeURIComponent(org)}`).then(r => r.data);
