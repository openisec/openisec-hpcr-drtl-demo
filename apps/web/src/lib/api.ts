import axios from "axios";
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL + "/api/v1",
  withCredentials: false,
  headers: { "Content-Type": "application/json" },
});
// リクエスト時にトークンをヘッダーに付与
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
// メモリ内トークン管理（XSS対策でlocalStorageは使わない）
let _token: string | null = null;
export const setToken = (token: string | null) => { _token = token; };
export const getToken = () => _token;
export default api;
export const login = (email: string, password: string) =>
  api.post("/auth/login", { email, password });
export const logout = () => api.post("/auth/logout");
export const getMe = () => api.get("/auth/me");
export const getSessions = () => api.get("/sessions");
export const createSession = (title: string) =>
  api.post("/sessions", { title });
export const createMessage = (sessionId: string, query: string) =>
  api.post(`/sessions/${sessionId}/messages`, { query });
export const recordDecision = (
  sessionId: string,
  messageId: string,
  decision: string,
  reason?: string,
  target_date?: string
) => api.post(`/sessions/${sessionId}/messages/${messageId}/decision`, { decision, reason, target_date });