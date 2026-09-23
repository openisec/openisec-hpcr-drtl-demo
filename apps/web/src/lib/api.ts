import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL + "/api/v1",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

export default api;

// HttpOnly Cookie自体はJSから読めないため、「ログイン試行済みか」の
// 目印としてlocalStorageに非機密フラグを立てておく。値自体に意味はなく、
// 存在有無だけを見る(トークンやセッション内容は一切含まない)。
const SESSION_FLAG_KEY = "openisec_has_session";

export const hasSessionFlag = () =>
  typeof window !== "undefined" && localStorage.getItem(SESSION_FLAG_KEY) === "1";

const setSessionFlag = () => localStorage.setItem(SESSION_FLAG_KEY, "1");
export const clearSessionFlag = () => localStorage.removeItem(SESSION_FLAG_KEY);

export const login = (email: string, password: string) =>
  api.post("/auth/login", { email, password }).then((res) => {
    setSessionFlag();
    return res;
  });

export const logout = () => api.post("/auth/logout").finally(clearSessionFlag);

export const getMe = () => api.get("/auth/me");

export const switchOrg = (organization_id: string, password: string) =>
  api.post("/auth/switch-org", { organization_id, password });

export const updateMyName = (family_name: string, given_name: string) =>
  api.patch("/auth/me", { family_name, given_name });

export const preRegister = (email: string) =>
  api.post("/auth/pre-register", { email });

export const verifyEmail = (token: string) =>
  api.get("/auth/verify-email", { params: { token } });

export const register = (
  email: string,
  password: string,
  password_confirm: string,
  family_name: string,
  given_name: string,
  organization_name: string,
  agree_terms: boolean,
  agree_privacy: boolean,
  marketing_opt_in: boolean,
  token: string
) => api.post("/auth/register", {
  email,
  password,
  password_confirm,
  family_name,
  given_name,
  organization_name,
  agree_terms,
  agree_privacy,
  marketing_opt_in,
  token,
});

export const requestPasswordReset = (email: string) =>
  api.post("/auth/password-reset/request", { email });

export const confirmPasswordReset = (token: string, new_password: string) =>
  api.post("/auth/password-reset/confirm", { token, new_password });

export interface SessionListParams {
  page?: number;
  limit?: number;
  from_date?: string;
  to_date?: string;
  status?: string;
  q?: string;
}

export interface SharedSessionListParams extends SessionListParams {
  created_by?: string;
}

export const getSessions = (params: SessionListParams = {}) =>
  api.get("/sessions", { params });

export const getSharedSessions = (params: SharedSessionListParams = {}) =>
  api.get("/sessions/shared", { params });

export const getSession = (sessionId: string) => api.get(`/sessions/${sessionId}`);

export const saveDraftQuery = (sessionId: string, draft_query: string) =>
  api.patch(`/sessions/${sessionId}/draft`, { draft_query });

export const createSession = (title: string) =>
  api.post("/sessions", { title });

export const createMessage = (sessionId: string, query: string) =>
  api.post(`/sessions/${sessionId}/messages`, { query });

export const recordDecision = (
  sessionId: string,
  messageId: string,
  decision: string,
  ai_recommendation_action: string,
  reason: string,
  target_date: string
) => api.post(`/sessions/${sessionId}/messages/${messageId}/decision`, {
  decision,
  ai_recommendation_action,
  reason,
  target_date,
});

export const saveDraftDecision = (
  sessionId: string,
  messageId: string,
  decision: string,
  ai_recommendation_action: string,
  reason: string,
  target_date: string
) => api.patch(`/sessions/${sessionId}/messages/${messageId}/draft-decision`, {
  decision,
  ai_recommendation_action,
  reason,
  target_date,
});

export const approveMessage = (sessionId: string, messageId: string, comment?: string) =>
  api.post(`/sessions/${sessionId}/messages/${messageId}/approve`, { comment });

export const rejectMessage = (sessionId: string, messageId: string, comment?: string) =>
  api.post(`/sessions/${sessionId}/messages/${messageId}/reject`, { comment });

export const updateAddendum = (sessionId: string, messageId: string, addendum: string) =>
  api.patch(`/sessions/${sessionId}/messages/${messageId}/addendum`, { addendum });

export const closeSession = (sessionId: string, addendum: string) =>
  api.post(`/sessions/${sessionId}/close`, { addendum });

export const deleteSession = (sessionId: string) =>
  api.delete(`/sessions/${sessionId}`);

export const getApprovalQueue = () => api.get("/sessions/approvals");

export const changePassword = (
  current_password: string,
  new_password: string,
  new_password_confirm: string
) => api.post("/auth/change-password", { current_password, new_password, new_password_confirm });

export const getMembers = () => api.get("/auth/members");

export const createMember = (
  email: string,
  family_name: string,
  given_name: string,
  role: string,
  organization_id?: string
) => api.post("/auth/members", { email, family_name, given_name, role, organization_id });

export const updateMember = (
  orgId: string,
  userId: string,
  payload: { role?: string; is_active?: boolean; new_organization_id?: string }
) => api.patch(`/auth/organizations/${orgId}/members/${userId}`, payload);

export const reissueTempPassword = (orgId: string, userId: string) =>
  api.post(`/auth/organizations/${orgId}/members/${userId}/reissue-password`);


export const getOrganizations = () => api.get("/auth/organizations");

export const createOrganization = (name: string) =>
  api.post("/auth/organizations", { name });

export interface AuditLogListParams {
  page?: number;
  limit?: number;
  action?: string;
  actor_email?: string;
  target_user_id?: string;
  from_date?: string;
  to_date?: string;
}

export interface AuthAuditLogListParams {
  page?: number;
  limit?: number;
  action?: string;
  actor_email?: string;
  org_id?: string;
  from_date?: string;
  to_date?: string;
}

export const getOrgAuditLogs = (params: AuditLogListParams = {}) =>
  api.get("/audit-logs/org", { params });

export const getOrgAuditActions = () => api.get("/audit-logs/org/actions");

export const exportOrgAuditLogs = (params: AuditLogListParams = {}) =>
  api.get("/audit-logs/org/export", { params, responseType: "blob" });

export const getAuthAuditLogs = (params: AuthAuditLogListParams = {}) =>
  api.get("/audit-logs/auth", { params });

export const getAuthAuditActions = () => api.get("/audit-logs/auth/actions");

export const exportAuthAuditLogs = (params: AuthAuditLogListParams = {}) =>
  api.get("/audit-logs/auth/export", { params, responseType: "blob" });

export const updateOrganization = (
  orgId: string,
  payload: { name?: string; is_active?: boolean; risk_score_threshold?: number }
) => api.patch(`/auth/organizations/${orgId}`, payload);
