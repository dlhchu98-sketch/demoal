import type {
  ChatResponse,
  LegalDocumentChunksResponse,
  LegalDocumentListResponse,
  LegalDocumentSummary,
  UserProfile,
} from '../types/legal';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
const TOKEN_KEY = 'legal_ai_access_token';

function getStoredToken(): string {
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(TOKEN_KEY) || '';
}

export function setAuthToken(token: string) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(TOKEN_KEY, token);
  }
}

export function clearAuthToken() {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  const token = getStoredToken();
  const baseHeaders: Record<string, string> = isFormData ? {} : { 'Content-Type': 'application/json' };
  if (token) baseHeaders['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...baseHeaders, ...(init?.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API Error ${res.status}`);
  }
  return res.json();
}

export const legalApi = {
  // Auth
  login: (identifier: string, password: string) =>
    apiFetch<{ access_token: string; user: UserProfile }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    }),
  register: (payload: { username: string; email: string; full_name: string; password: string }) =>
    apiFetch<{ access_token: string; user: UserProfile }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  logout: () => apiFetch('/api/auth/logout', { method: 'POST' }),
  getMe: () => apiFetch<UserProfile>('/api/auth/me'),

  // System & Stats
  getStatus: () => apiFetch<any>('/api/status'),
  getStatistics: () => apiFetch<any>('/api/statistics'),
  getAdminDashboard: () => apiFetch<any>('/api/admin/dashboard'),
  getAdminUsers: () => apiFetch<UserProfile[]>('/api/admin/users'),
  getAdminConfig: () => apiFetch<any>('/api/admin/system-config'),
  getAdminTestResults: () => apiFetch<any[]>('/api/admin/test-results'),

  // Chat & Conversations
  chat: (question: string, conversationId: string | null = null, simulateSelfCorrection = false) =>
    apiFetch<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        conversation_id: conversationId,
        simulate_self_correction: simulateSelfCorrection,
      }),
    }),
  getConversations: () => apiFetch<any[]>('/api/chat/conversations'),
  getHistory: (search?: string) =>
    apiFetch<any[]>(`/api/history${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  getHistoryDetail: (id: string) => apiFetch<ChatResponse>(`/api/history/${id}`),
  deleteHistory: (id: string) => apiFetch(`/api/history/${id}`, { method: 'DELETE' }),

  // Saved Items
  getSaved: (itemType?: string) =>
    apiFetch<any[]>(`/api/saved${itemType ? `?item_type=${itemType}` : ''}`),
  createSaved: (payload: any) =>
    apiFetch<any>('/api/saved', { method: 'POST', body: JSON.stringify(payload) }),
  deleteSaved: (id: string) => apiFetch(`/api/saved/${id}`, { method: 'DELETE' }),

  // Questions & Legal Documents
  getQuestions: (params = '') => apiFetch<any>(`/api/questions${params}`),
  getCategories: () => apiFetch<any>('/api/questions/categories'),
  getDocuments: (params = '') => apiFetch<any>(`/api/documents${params}`),
  getLegalDocuments: (params = '') => apiFetch<LegalDocumentListResponse>(`/api/legal-documents${params}`),
  getLegalDocumentDetail: (documentId: string) =>
    apiFetch<LegalDocumentSummary & { chunks: any[] }>(`/api/legal-documents/${encodeURIComponent(documentId)}`),
  getLegalDocumentChunks: (documentId: string, params = '') =>
    apiFetch<LegalDocumentChunksResponse>(`/api/legal-documents/${encodeURIComponent(documentId)}/chunks${params}`),
  getLegalDocumentsStats: () => apiFetch<any>('/api/legal-documents/stats'),
  scanLegalDocuments: (autoIngest = true, allowUpdate = false) =>
    apiFetch<any>('/api/legal-documents/scan', {
      method: 'POST',
      body: JSON.stringify({ auto_ingest: autoIngest, allow_update: allowUpdate }),
    }),
  ingestLegalDocuments: (filePath: string | null = null, allowUpdate = false) =>
    apiFetch<any>('/api/legal-documents/ingest', {
      method: 'POST',
      body: JSON.stringify({ file_path: filePath, allow_update: allowUpdate }),
    }),
  uploadLegalFolder: (files: File[], allowUpdate = false) => {
    const fd = new FormData();
    files.forEach((f) => {
      const rel = (f as any).webkitRelativePath || f.name;
      fd.append('files', f, rel);
    });
    return apiFetch<any>(`/api/legal-documents/upload-folder?allow_update=${allowUpdate ? 'true' : 'false'}`, {
      method: 'POST',
      body: fd,
    });
  },
  deleteLegalDocument: (documentId: string) =>
    apiFetch<any>(`/api/legal-documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' }),

  // RAG, Agent, Citation, Evaluation
  ragSearch: (query: string, topK = 5) =>
    apiFetch<any>('/api/rag/search', { method: 'POST', body: JSON.stringify({ query, top_k: topK }) }),
  agentAnalyze: (question: string) =>
    apiFetch<any>('/api/agent/analyze', { method: 'POST', body: JSON.stringify({ question }) }),
  getAgentLogs: () => apiFetch<any[]>('/api/agent/logs'),
  getCitations: (status?: string) =>
    apiFetch<any[]>(`/api/citations${status ? `?status=${status}` : ''}`),
  getCitationReport: () => apiFetch<any>('/api/citations/report'),
  getEvaluationResults: () => apiFetch<any>('/api/evaluation/results'),
  runEvaluation: (sampleSize = 60) =>
    apiFetch<any>('/api/evaluation/run', {
      method: 'POST',
      body: JSON.stringify({ sample_size: sampleSize }),
    }),
};
