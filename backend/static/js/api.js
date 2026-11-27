// =========================================================================
// Legal AI Assistant — Shared API Client, Auth Token Store & Formatters
// =========================================================================

window.LegalApp = window.LegalApp || {};

(function (ns) {
  const TOKEN_KEY = 'legal_ai_access_token';
  const USER_KEY = 'legal_ai_user_profile';
  const API_BASE_KEY = 'legal_ai_api_base';

  const IS_GITHUB_PAGES =
    typeof window !== 'undefined' &&
    (window.location.hostname.endsWith('github.io') || window.location.protocol === 'file:');

  // Cho phép truyền ?api=https://your-backend-url để nối giao diện GitHub Pages tới FastAPI thật
  (function initApiBaseFromUrl() {
    try {
      const qs = new URLSearchParams(window.location.search);
      const qApi = qs.get('api');
      if (qApi) {
        localStorage.setItem(API_BASE_KEY, qApi.replace(/\/+$/, ''));
      }
    } catch {}
  })();

  ns.isStaticPreview = function () {
    return IS_GITHUB_PAGES && !ns.getApiBase();
  };

  ns.getApiBase = function () {
    try {
      return (localStorage.getItem(API_BASE_KEY) || '').replace(/\/+$/, '');
    } catch {
      return '';
    }
  };

  ns.setApiBase = function (url) {
    try {
      const clean = String(url || '').trim().replace(/\/+$/, '');
      if (clean) localStorage.setItem(API_BASE_KEY, clean);
      else localStorage.removeItem(API_BASE_KEY);
    } catch {}
  };

  ns._staticQuestionsCache = null;
  async function loadStaticQuestions() {
    if (ns._staticQuestionsCache) return ns._staticQuestionsCache;
    try {
      const r = await fetch('./data/questions_dataset.json');
      if (r.ok) {
        ns._staticQuestionsCache = await r.json();
        return ns._staticQuestionsCache;
      }
    } catch {}
    return { domains: [], categories: [], questions: [] };
  }

  async function handleStaticPreviewApi(path, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const ds = await loadStaticQuestions();

    if (path.startsWith('/api/status')) {
      return {
        app_name: 'LEGAL ASSISTANT',
        app_mode: 'demo',
        database: { name: 'Database', status: 'demo', detail: 'GitHub Pages Static Preview (nhập Backend URL để kết nối thật)' },
        qdrant: { name: 'Qdrant Vector DB', status: 'demo', detail: 'Cần kết nối FastAPI Backend để truy xuất Qdrant thật' },
        llm: { name: 'LLM', status: 'demo', detail: 'Chế độ xem trước tĩnh trên GitHub Pages' },
        rag: { name: 'RAG Pipeline', status: 'demo', detail: 'Chế độ xem trước tĩnh' },
        agent: { name: 'LangGraph Agent', status: 'demo', detail: 'Chế độ xem trước tĩnh' },
        citation_validator: { name: 'Citation Validator', status: 'demo', detail: 'Chế độ xem trước tĩnh' },
        question_bank_loaded: (ds.questions || []).length > 0,
        legal_corpus_loaded: false,
      };
    }
    if (path.startsWith('/api/statistics')) {
      return {
        app_mode: 'demo',
        is_demo_data: true,
        total_question_categories: (ds.categories || []).length,
        expected_question_categories: (ds.categories || []).length || 17,
        total_questions: (ds.questions || []).length,
        total_documents: 0,
        total_queries: 0,
      };
    }
    if (path.startsWith('/api/questions/categories')) {
      return {
        loaded: (ds.categories || []).length > 0,
        domains: ds.domains || [],
        total_categories: (ds.categories || []).length,
        items: ds.categories || [],
      };
    }
    if (path.startsWith('/api/questions')) {
      const u = new URL(path, 'https://preview.local');
      const dom = (u.searchParams.get('domain') || '').toLowerCase();
      const diff = (u.searchParams.get('difficulty') || '').toLowerCase();
      let items = ds.questions || [];
      if (dom) items = items.filter((q) => (q.domain || '').toLowerCase() === dom);
      if (diff) items = items.filter((q) => (q.difficulty || '').toLowerCase() === diff);
      return {
        loaded: items.length > 0,
        total_questions: items.length,
        domains: ds.domains || [],
        items: items.slice(0, 12),
      };
    }
    if (path.startsWith('/api/chat') && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const q = body.question || '';
      const reqId = 'GH-PREVIEW-' + Date.now();
      return {
        request_id: reqId,
        conversation_id: body.conversation_id || 'GH-CONV-1',
        question: q,
        answer: `[XEM TRƯỚC TĨNH TRÊN GITHUB PAGES — is_mock=true]\n\nGiao diện đang chạy bản tĩnh trên GitHub Pages (chưa kết nối tới máy chủ FastAPI Backend).\nĐể chạy RAG, Agent, Citation Validator và Upload thư mục văn bản thật, hãy chạy 'python app.py' và nhập địa chỉ Backend (vd: http://127.0.0.1:8001) hoặc mở trực tiếp cổng localhost.`,
        conclusion: 'Đang ở chế độ xem trước tĩnh trên GitHub Pages; chưa kết nối máy chủ FastAPI Backend.',
        explanation: 'Vui lòng chạy Backend FastAPI và gắn URL Backend để sử dụng đầy đủ chức năng AI thật.',
        limitations: ['GitHub Pages chỉ phục vụ giao diện tĩnh (HTML/JS/CSS), không chạy Python/Qdrant trực tiếp.'],
        analysis: [{ issue: 'Phân tích câu hỏi pháp lý (Static Preview)', legal_domain: 'Pháp luật Việt Nam' }],
        citations: [],
        citation_status: 'UNVERIFIED',
        verification_label: 'Chưa đủ bằng chứng (GitHub Pages Static Preview)',
        validation_details: [],
        self_correction: { attempts: 0, performed: false, max_attempts: 2, steps: [] },
        processing_status: {
          current_step: 7,
          total_steps: 7,
          overall_state: 'insufficient_evidence',
          steps: [
            { step_number: 1, stage: 'receive_question', label: 'Tiếp nhận câu hỏi', status: 'completed', detail: 'Đã nhận câu hỏi trên giao diện tĩnh.' },
            { step_number: 2, stage: 'query_analysis', label: 'Phân tích câu hỏi', status: 'warning', detail: 'Cần kết nối Backend FastAPI.' },
            { step_number: 3, stage: 'issue_decomposition', label: 'Phân rã vấn đề pháp lý', status: 'warning', detail: 'Cần kết nối Backend FastAPI.' },
            { step_number: 4, stage: 'document_retrieval', label: 'Tìm kiếm văn bản', status: 'warning', detail: 'Chưa kết nối Qdrant.' },
            { step_number: 5, stage: 'legal_analysis', label: 'Đối chiếu và phân tích', status: 'warning', detail: 'Chưa có bằng chứng gốc.' },
            { step_number: 6, stage: 'citation_validation', label: 'Kiểm tra trích dẫn', status: 'warning', detail: 'Chưa kiểm chứng trên dữ liệu thật.' },
            { step_number: 7, stage: 'final_response', label: 'Trả kết quả', status: 'warning', detail: 'Trả về thông báo giới hạn GitHub Pages Preview.' },
          ],
        },
        disclaimer: 'Lưu ý: Bản xem trước tĩnh trên GitHub Pages; chạy Backend FastAPI để dùng đầy đủ RAG + Agent.',
        is_mock: true,
        app_mode: 'demo',
        processing_time_ms: 15,
        created_at: new Date().toISOString(),
      };
    }
    if (path.startsWith('/api/legal-documents')) {
      return {
        loaded: false,
        total_documents: 0,
        total_chunks: 0,
        document_types: [],
        issuing_authorities: [],
        statuses: [],
        items: [],
        note: 'Đang xem bản tĩnh trên GitHub Pages. Kết nối Backend FastAPI để quản lý và đồng bộ kho văn bản pháp luật.',
      };
    }
    if (path.startsWith('/api/chat/conversations') || path.startsWith('/api/history') || path.startsWith('/api/saved')) {
      return [];
    }
    throw new Error('Chức năng này cần kết nối máy chủ FastAPI Backend (hiện đang ở bản tĩnh GitHub Pages).');
  }

  ns.auth = {
    getToken() {
      try {
        return localStorage.getItem(TOKEN_KEY) || '';
      } catch {
        return '';
      }
    },
    setSession(token, user) {
      try {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify(user));
      } catch {}
    },
    clearSession() {
      try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
      } catch {}
    },
    getCachedUser() {
      try {
        const raw = localStorage.getItem(USER_KEY);
        return raw ? JSON.parse(raw) : null;
      } catch {
        return null;
      }
    },
  };

  ns.esc = function esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  ns.fmtDate = function fmtDate(iso) {
    if (!iso) return 'Chưa xác định';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      return d.toLocaleString('vi-VN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return String(iso);
    }
  };

  ns.statusBadge = function statusBadge(status) {
    const s = String(status || 'UNVERIFIED').toUpperCase();
    if (s === 'PASS' || s === 'COMPLETED' || s === 'ONLINE' || s === 'SYNCED' || s === 'PASSED') {
      const labelMap = {
        PASS: 'Đã xác minh (PASS)',
        COMPLETED: 'Hoàn tất',
        ONLINE: 'Hoạt động',
        SYNCED: 'Đã đồng bộ',
        PASSED: 'Đạt (PASS)',
      };
      return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold badge-pass">${labelMap[s] || s}</span>`;
    }
    if (s === 'FAIL' || s === 'ERROR' || s === 'OFFLINE' || s === 'FAILED') {
      const labelMap = {
        FAIL: 'Không hợp lệ (FAIL)',
        ERROR: 'Lỗi xử lý',
        OFFLINE: 'Ngoại tuyến',
        FAILED: 'Lỗi đồng bộ',
      };
      return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold badge-fail">${labelMap[s] || s}</span>`;
    }
    if (s === 'DEMO') {
      return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold badge-blue">DEMO</span>`;
    }
    const labelMap = {
      UNVERIFIED: 'Chưa đủ bằng chứng',
      WARNING: 'Cảnh báo',
      PENDING: 'Chờ xử lý',
      NOT_CONFIGURED: 'Chưa cấu hình',
    };
    return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold badge-warn">${labelMap[s] || status}</span>`;
  };

  ns.toast = function toast(message, type = 'info') {
    const el = document.getElementById('toast');
    if (!el) return;
    const styles = {
      success: 'border-emerald-300 bg-emerald-50 text-emerald-900',
      error: 'border-red-300 bg-red-50 text-red-900',
      warn: 'border-amber-300 bg-amber-50 text-amber-900',
      info: 'border-blue-200 bg-white text-slate-800',
    };
    el.className = `fixed bottom-5 right-5 z-50 max-w-md rounded-xl px-4 py-3 text-sm font-medium shadow-lg border ${styles[type] || styles.info}`;
    el.textContent = message;
    el.classList.remove('hidden');
    clearTimeout(ns._toastTimer);
    ns._toastTimer = setTimeout(() => el.classList.add('hidden'), 4200);
  };

  ns.api = async function api(path, options = {}) {
    if (ns.isStaticPreview()) {
      return handleStaticPreviewApi(path, options);
    }
    const base = ns.getApiBase();
    const url = path.startsWith('http') ? path : `${base}${path}`;
    const token = ns.auth.getToken();
    const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData;
    const headers = { ...(options.headers || {}) };
    if (!isForm && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    let res;
    try {
      res = await fetch(url, { ...options, headers });
    } catch (networkErr) {
      if (IS_GITHUB_PAGES) {
        ns.setApiBase('');
        ns.toast('Không thể kết nối Backend URL (trình duyệt chặn HTTP từ HTTPS hoặc máy chủ chưa chạy). Tự chuyển sang chế độ xem trước tĩnh GitHub Pages.', 'warn');
        return handleStaticPreviewApi(path, options);
      }
      throw networkErr;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = typeof data.detail === 'string' ? data.detail : `Lỗi API (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  };
})(window.LegalApp);
