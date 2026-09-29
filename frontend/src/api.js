const TOKEN_KEY = "cnc_offset_token";
const USER_KEY = "cnc_offset_user";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api${path}`, { ...options, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const msg = data?.detail || data?.message || `请求失败 (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

export function login(username, password) {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function fetchSubmissions() {
  return request("/submissions");
}

export function fetchSubmission(id) {
  return request(`/submissions/${id}`);
}

// 刀号只能从「仍可投」的刀里点选：roster_tool_id 为空选（会整笔退回）
export function createSubmission(roster_tool_id, offset_um) {
  return request("/submissions", {
    method: "POST",
    body: JSON.stringify({
      roster_tool_id: roster_tool_id || null,
      offset_um: Number(offset_um),
    }),
  });
}

// ---------- 清册 ----------

export function fetchTools() {
  return request("/roster/tools");
}

export function fetchEvents() {
  return request("/roster/events");
}

export function registerTool(tool_code, investable) {
  return request("/roster/tools", {
    method: "POST",
    body: JSON.stringify({ tool_code, investable }),
  });
}

export function delistTool(id) {
  return request(`/roster/tools/${id}/delist`, { method: "POST" });
}

export function relistTool(id) {
  return request(`/roster/tools/${id}/relist`, { method: "POST" });
}
