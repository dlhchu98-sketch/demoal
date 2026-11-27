// =========================================================================
// Legal AI Assistant — ADMIN PORTAL (8 dedicated management pages, RBAC protected)
// 1. Dashboard | 2. Quản lý văn bản | 3. Quản lý dữ liệu RAG | 4. Theo dõi Agent
// 5. Citation Validator | 6. Testing Dashboard | 7. Quản lý người dùng & Phân quyền
// 8. Cấu hình hệ thống
// =========================================================================

window.LegalApp = window.LegalApp || {};

(function (ns) {
  const { esc, fmtDate, statusBadge, api, toast } = ns;

  ns.ADMIN_NAV = [
    { id: 'admin-dashboard', label: 'Dashboard', icon: 'layout-dashboard', subtitle: 'Số liệu hệ thống thật: Văn bản, Lượt tra cứu, Citation, Qdrant & PostgreSQL' },
    { id: 'admin-documents', label: 'Quản lý văn bản', icon: 'file-text', subtitle: 'Upload, thêm mới, sửa metadata, quét trùng lặp và đồng bộ văn bản' },
    { id: 'admin-rag', label: 'Quản lý dữ liệu RAG', icon: 'database', subtitle: 'Pipeline Upload → Extraction → Cleaning → Chunking → Embedding → Indexing' },
    { id: 'admin-agent', label: 'Theo dõi Agent', icon: 'cpu', subtitle: 'Theo dõi từng tác vụ LangGraph Agent, Self-Correction và lỗi xử lý' },
    { id: 'admin-citations', label: 'Citation Validator', icon: 'shield-check', subtitle: 'Thống kê kiểm chứng, lịch sử trích dẫn và kiểm thử 6 tiêu chí' },
    { id: 'admin-testing', label: 'Testing Dashboard', icon: 'flask-conical', subtitle: 'Kết quả kiểm thử thực tế (Unit, API, RAG, Agent, Citation, E2E) & Evaluation' },
    { id: 'admin-users', label: 'Người dùng & Phân quyền', icon: 'users', subtitle: 'Quản lý tài khoản, phân quyền User/Admin, khóa mở và nhật ký hoạt động' },
    { id: 'admin-config', label: 'Cấu hình hệ thống', icon: 'sliders', subtitle: 'Cấu hình LLM, Embedding, Qdrant, PostgreSQL (không lộ API Key)' },
  ];

  // -------------------------------------------------------------------------
  // Admin Page 1: Dashboard (Real stats only)
  // -------------------------------------------------------------------------
  ns.renderAdminDashboard = async function (container) {
    const d = await api('/api/admin/dashboard');
    container.innerHTML = `
      <div class="space-y-5">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div class="card p-4">
            <div class="text-xs text-slate-500">Tổng số văn bản pháp luật</div>
            <div class="text-2xl font-bold text-[#0F2544] mt-1">${d.total_documents}</div>
            <div class="text-[11px] text-emerald-700 mt-1">Đã nạp Qdrant: ${d.ingested_synced_documents} · ${d.total_chunks} chunks</div>
          </div>
          <div class="card p-4">
            <div class="text-xs text-slate-500">Tổng số lượt tra cứu</div>
            <div class="text-2xl font-bold text-[#0F2544] mt-1">${d.total_queries}</div>
            <div class="text-[11px] text-slate-500 mt-1">Người dùng đăng ký: ${d.total_users}</div>
          </div>
          <div class="card p-4">
            <div class="text-xs text-slate-500">Số lần kiểm chứng Citation</div>
            <div class="text-2xl font-bold text-[#0F2544] mt-1">${d.total_citations_checked}</div>
            <div class="text-[11px] text-slate-500 mt-1">Hợp lệ: ${d.citation_pass_count} · Chưa đủ căn cứ: ${d.citation_unverified_count}</div>
          </div>
          <div class="card p-4">
            <div class="text-xs text-slate-500">Số lỗi Citation (FAIL)</div>
            <div class="text-2xl font-bold ${d.citation_fail_count > 0 ? 'text-red-600' : 'text-[#0F2544]'} mt-1">${d.citation_fail_count}</div>
            <div class="text-[11px] text-amber-700 mt-1">Số lượt Self-Correction: ${d.self_correction_count}</div>
          </div>
        </div>

        <!-- Real Service Health -->
        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">Trạng thái hạ tầng hệ thống (Dữ liệu thật)</h3>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            ${[d.backend_status, d.database_status, d.qdrant_status, d.llm_status].map((sv) => `
              <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-bold text-[#0F2544]">${esc(sv.name)}</span>
                  ${statusBadge(sv.status)}
                </div>
                <p class="text-[11px] text-slate-600 leading-snug">${esc(sv.detail)}</p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Recent Activity Tables -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="card p-5 space-y-3">
            <h3 class="text-sm font-bold text-[#0F2544]">Lượt tra cứu gần đây</h3>
            ${d.recent_queries.length ? `
              <div class="space-y-2">
                ${d.recent_queries.slice(0, 6).map((q) => `
                  <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between gap-2 text-xs">
                    <div class="min-w-0 flex-1">
                      <div class="font-semibold text-[#0F2544] truncate">${esc(q.question)}</div>
                      <div class="text-[11px] text-slate-500">${fmtDate(q.created_at)} · ${q.processing_time_ms} ms</div>
                    </div>
                    ${statusBadge(q.citation_status)}
                  </div>
                `).join('')}
              </div>
            ` : `<div class="text-xs text-slate-500">Chưa có lượt tra cứu nào.</div>`}
          </div>

          <div class="card p-5 space-y-3">
            <h3 class="text-sm font-bold text-[#0F2544]">Nhật ký nạp văn bản gần đây</h3>
            ${d.recent_ingestion_logs.length ? `
              <div class="space-y-2">
                ${d.recent_ingestion_logs.slice(0, 6).map((lg) => `
                  <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1">
                    <div class="flex items-center justify-between">
                      <span class="font-semibold text-[#0F2544] truncate">${esc(lg.file_path)}</span>
                      ${statusBadge(lg.status === 'success' ? 'completed' : lg.status === 'error' ? 'error' : 'warning')}
                    </div>
                    <div class="text-[11px] text-slate-600">${esc(lg.message)}</div>
                  </div>
                `).join('')}
              </div>
            ` : `<div class="text-xs text-slate-500">Chưa có nhật ký nạp văn bản.</div>`}
          </div>
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  // -------------------------------------------------------------------------
  // Admin Page 2: Quản lý văn bản (Upload, Add, Edit Metadata, Delete, Scan)
  // -------------------------------------------------------------------------
  ns.renderAdminDocuments = async function (container) {
    const f = ns.state.adminDocFilters || { search: '', document_type: '', issuing_authority: '' };
    const params = new URLSearchParams();
    if (f.search) params.set('search', f.search);
    if (f.document_type) params.set('document_type', f.document_type);
    if (f.issuing_authority) params.set('issuing_authority', f.issuing_authority);
    const qs = params.toString() ? `?${params.toString()}` : '';

    const [data, stats] = await Promise.all([
      api(`/api/legal-documents${qs}`),
      api('/api/legal-documents/stats'),
    ]);

    container.innerHTML = `
      <div class="space-y-5">
        <!-- Toolbar -->
        <div class="card p-5 space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-base font-bold text-[#0F2544]">Quản lý kho văn bản pháp luật</h2>
              <p class="text-xs text-slate-500 mt-0.5">${esc(stats.qdrant_detail)}</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <label class="inline-flex items-center gap-1.5 text-xs bg-slate-50 border border-slate-200 px-3 py-2 rounded-lg">
                <input id="adminAllowUpdate" type="checkbox" ${ns.state.adminAllowUpdate ? 'checked' : ''}
                  onchange="window.LegalApp.state.adminAllowUpdate=this.checked" />
                <span>Cho phép cập nhật file sửa đổi</span>
              </label>
              <label id="adminFolderUploadBtn" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold cursor-pointer inline-flex items-center gap-1.5 shadow-sm">
                <i data-lucide="folder-up" class="w-4 h-4"></i>
                <span>Upload cả thư mục gốc (.doc, .docx, .pdf)</span>
                <input type="file" webkitdirectory directory multiple class="hidden" onchange="window.LegalApp.adminUploadFolder(this)" />
              </label>
              <label class="btn-soft px-3.5 py-2 rounded-lg text-xs font-semibold cursor-pointer inline-flex items-center gap-1.5">
                <i data-lucide="file-up" class="w-3.5 h-3.5"></i>
                <span>Upload tệp lẻ (.doc/.docx/.pdf/.txt/.json)</span>
                <input type="file" accept=".doc,.docx,.pdf,.txt,.json" multiple class="hidden" onchange="window.LegalApp.adminUploadFolder(this)" />
              </label>
              <button onclick="window.LegalApp.adminScanSync()" class="btn-soft px-3.5 py-2 rounded-lg text-xs font-semibold">
                Quét thư mục & Đồng bộ dữ liệu
              </button>
              ${data.failed_documents > 0 ? `
                <button onclick="window.LegalApp.adminResyncFailed()" class="px-3.5 py-2 rounded-lg text-xs font-semibold bg-amber-500 hover:bg-amber-600 text-white">
                  Đồng bộ lại ${data.failed_documents} văn bản lỗi Qdrant
                </button>
              ` : ''}
              <button onclick="document.getElementById('adminAddDocBox').classList.toggle('hidden')"
                class="btn-soft px-3.5 py-2 rounded-lg text-xs font-semibold">
                + Thêm văn bản
              </button>
            </div>
          </div>

          <!-- Folder Upload Auto-Filter & Conversion Progress / Report -->
          <div id="adminFolderProgress" class="hidden p-4 rounded-xl bg-[#EFF6FF] border border-blue-200 text-xs text-[#0F2544] flex items-center gap-2.5">
            <span class="inline-block w-3.5 h-3.5 rounded-full border-2 border-[#2563EB] border-t-transparent animate-spin"></span>
            <span id="adminFolderProgressText">Đang tải thư mục, tự động lọc & chuyển đổi định dạng sang chuẩn RAG...</span>
          </div>

          ${ns.state.lastFolderUploadReport ? ns._renderFolderUploadReport(ns.state.lastFolderUploadReport) : ''}

          <!-- Add Document Inline Form -->
          <div id="adminAddDocBox" class="hidden p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
            <div class="text-xs font-bold text-[#0F2544]">Thêm văn bản pháp luật mới (Lưu JSON & tự động đồng bộ Qdrant)</div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-xs">
              <input id="newDocFilename" placeholder="Tên tệp (vd: luat_giao_duc_2019.json)" class="px-3 py-2 rounded-lg border border-slate-300 bg-white" />
              <input id="newDocTitle" placeholder="Tên văn bản *" class="px-3 py-2 rounded-lg border border-slate-300 bg-white" />
              <input id="newDocNumber" placeholder="Số hiệu (vd: 43/2019/QH14)" class="px-3 py-2 rounded-lg border border-slate-300 bg-white" />
              <input id="newDocType" placeholder="Loại văn bản (Luật, Nghị định...)" class="px-3 py-2 rounded-lg border border-slate-300 bg-white" />
              <input id="newDocAuthority" placeholder="Cơ quan ban hành" class="px-3 py-2 rounded-lg border border-slate-300 bg-white" />
              <input id="newDocEffDate" placeholder="Ngày hiệu lực (YYYY-MM-DD)" class="px-3 py-2 rounded-lg border border-slate-300 bg-white" />
            </div>
            <textarea id="newDocContent" rows="5" placeholder="Dán nguyên văn nội dung văn bản (Chương / Điều / Khoản / Điểm)..."
              class="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white text-xs"></textarea>
            <div class="flex justify-end gap-2">
              <button onclick="document.getElementById('adminAddDocBox').classList.add('hidden')" class="px-3 py-1.5 rounded-lg text-xs text-slate-600">Hủy</button>
              <button onclick="window.LegalApp.adminCreateDoc()" class="btn-navy px-4 py-1.5 rounded-lg text-xs font-semibold">Lưu & Đồng bộ Qdrant</button>
            </div>
          </div>

          <!-- Filters -->
          <div class="grid grid-cols-1 md:grid-cols-4 gap-2.5">
            <input id="adminDocSearch" type="text" value="${esc(f.search)}" placeholder="Tìm tên văn bản, số hiệu..."
              class="md:col-span-2 px-3 py-2 rounded-lg border border-slate-300 text-xs"
              onkeydown="if(event.key==='Enter'){window.LegalApp.applyAdminDocFilters();}" />
            <select id="adminDocType" onchange="window.LegalApp.applyAdminDocFilters()" class="px-3 py-2 rounded-lg border border-slate-300 text-xs bg-white">
              <option value="">Tất cả loại văn bản</option>
              ${(data.document_types || []).map((t) => `<option value="${esc(t)}" ${f.document_type === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}
            </select>
            <select id="adminDocAuth" onchange="window.LegalApp.applyAdminDocFilters()" class="px-3 py-2 rounded-lg border border-slate-300 text-xs bg-white">
              <option value="">Tất cả cơ quan ban hành</option>
              ${(data.issuing_authorities || []).map((a) => `<option value="${esc(a)}" ${f.issuing_authority === a ? 'selected' : ''}>${esc(a)}</option>`).join('')}
            </select>
          </div>
        </div>

        ${!data.loaded ? `
          <div class="card p-10 text-center space-y-2">
            <div class="text-sm font-bold text-[#0F2544]">Chưa có dữ liệu văn bản pháp luật</div>
            <p class="text-xs text-slate-500">Chưa có dữ liệu văn bản pháp luật. Vui lòng thêm văn bản vào thư mục data/legal_documents/ và thực hiện đồng bộ.</p>
          </div>
        ` : `
          <div class="card overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead class="bg-slate-50 text-slate-500 uppercase border-b border-slate-200">
                <tr>
                  <th class="px-3 py-3">STT</th>
                  <th class="px-3 py-3">Tên văn bản</th>
                  <th class="px-3 py-3">Số hiệu</th>
                  <th class="px-3 py-3">Loại văn bản</th>
                  <th class="px-3 py-3">Cơ quan ban hành</th>
                  <th class="px-3 py-3">Ngày ban hành</th>
                  <th class="px-3 py-3">Ngày hiệu lực</th>
                  <th class="px-3 py-3">Trạng thái</th>
                  <th class="px-3 py-3 text-right">Số lượng chunk</th>
                  <th class="px-3 py-3">Trạng thái đồng bộ Qdrant</th>
                  <th class="px-3 py-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                ${data.items.map((doc, i) => `
                  <tr class="hover:bg-slate-50">
                    <td class="px-3 py-3">${i + 1}</td>
                    <td class="px-3 py-3 font-semibold text-[#0F2544] max-w-[220px]">${esc(doc.title)}</td>
                    <td class="px-3 py-3">${esc(doc.document_number || 'Chưa xác định')}</td>
                    <td class="px-3 py-3">${esc(doc.document_type || 'Chưa xác định')}</td>
                    <td class="px-3 py-3">${esc(doc.issuing_authority || 'Chưa xác định')}</td>
                    <td class="px-3 py-3">${esc(doc.issue_date || 'Chưa xác định')}</td>
                    <td class="px-3 py-3">${esc(doc.effective_date || 'Chưa xác định')}</td>
                    <td class="px-3 py-3">${esc(doc.status || 'Chưa xác định')}</td>
                    <td class="px-3 py-3 text-right font-semibold">${doc.chunk_count}</td>
                    <td class="px-3 py-3">
                      ${statusBadge(doc.qdrant_sync_status)}
                      ${doc.qdrant_sync_status === 'synced' ? `<div class="text-[10px] text-emerald-700 mt-0.5">${doc.qdrant_synced_chunks}/${doc.chunk_count} vectors</div>` : ''}
                      ${doc.last_error ? `<div class="text-[10px] text-red-600 mt-0.5 max-w-[200px] truncate" title="${esc(doc.last_error)}">${esc(doc.last_error)}</div>` : ''}
                    </td>
                    <td class="px-3 py-3 text-right whitespace-nowrap space-x-2">
                      <button onclick="window.LegalApp.openSourceDocModal('${esc(doc.document_id)}','')" class="text-[#2563EB] hover:underline font-semibold">Xem</button>
                      <button onclick="window.LegalApp.openEditMetadataPrompt('${esc(doc.document_id)}',${JSON.stringify(doc.title).replace(/"/g, '&quot;')},${JSON.stringify(doc.document_number || '').replace(/"/g, '&quot;')},${JSON.stringify(doc.status || '').replace(/"/g, '&quot;')})" class="text-slate-700 hover:underline font-semibold">Sửa</button>
                      <button onclick="window.LegalApp.adminDeleteDoc('${esc(doc.document_id)}',${JSON.stringify(doc.title).replace(/"/g, '&quot;')})" class="text-red-600 hover:underline font-semibold">Xóa</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;
    lucide.createIcons();
  };

  ns.applyAdminDocFilters = function () {
    ns.state.adminDocFilters = {
      search: document.getElementById('adminDocSearch')?.value?.trim() || '',
      document_type: document.getElementById('adminDocType')?.value || '',
      issuing_authority: document.getElementById('adminDocAuth')?.value || '',
    };
    ns.renderCurrentPage();
  };

  ns.adminScanSync = async function () {
    try {
      const res = await api('/api/legal-documents/scan', {
        method: 'POST',
        body: JSON.stringify({ auto_ingest: true, allow_update: Boolean(ns.state.adminAllowUpdate) }),
      });
      toast(res.message, res.error_count > 0 ? 'warn' : 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.adminResyncFailed = async function () {
    toast('Đang tạo embedding và đồng bộ lại các văn bản lỗi lên Qdrant...', 'info');
    try {
      const res = await api('/api/legal-documents/resync-failed', { method: 'POST' });
      toast(res.message, res.error_count > 0 ? 'warn' : 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns._renderFolderUploadReport = function (rep) {
    const actionLabel = {
      ingested: 'Nạp mới',
      updated: 'Cập nhật',
      skipped_duplicate: 'Trùng lặp',
      conflict_requires_update: 'Cần bật cập nhật',
      filtered_out: 'Tự lọc bỏ qua',
      error: 'Lỗi xử lý',
    };
    return `
      <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3 text-xs">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="font-bold text-[#0F2544]">Kết quả tự động lọc & chuyển đổi thư mục</div>
          <button onclick="window.LegalApp.state.lastFolderUploadReport=null;window.LegalApp.renderCurrentPage();"
            class="text-slate-500 hover:text-slate-800 font-semibold">Đóng báo cáo</button>
        </div>
        <div class="text-slate-700">${esc(rep.message)}</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          <div class="p-2 rounded-lg bg-white border border-slate-200"><div class="text-[11px] text-slate-500">Tổng tệp chọn</div><div class="font-bold text-[#0F2544]">${rep.total_received}</div></div>
          <div class="p-2 rounded-lg bg-white border border-blue-200"><div class="text-[11px] text-slate-500">Tự chuyển đổi</div><div class="font-bold text-[#2563EB]">${rep.converted_count}</div></div>
          <div class="p-2 rounded-lg bg-white border border-emerald-200"><div class="text-[11px] text-slate-500">Nạp mới / Cập nhật</div><div class="font-bold text-emerald-700">${rep.ingested_count + rep.updated_count}</div></div>
          <div class="p-2 rounded-lg bg-white border border-slate-200"><div class="text-[11px] text-slate-500">Trùng SHA-256</div><div class="font-bold text-slate-600">${rep.skipped_duplicate_count}</div></div>
          <div class="p-2 rounded-lg bg-white border border-amber-200"><div class="text-[11px] text-slate-500">Tự lọc bỏ qua</div><div class="font-bold text-amber-700">${rep.filtered_out_count}</div></div>
          <div class="p-2 rounded-lg bg-white border border-red-200"><div class="text-[11px] text-slate-500">Lỗi</div><div class="font-bold text-red-600">${rep.error_count}</div></div>
        </div>
        ${rep.items && rep.items.length ? `
          <details open class="bg-white rounded-lg border border-slate-200 p-2.5">
            <summary class="cursor-pointer font-semibold text-[#0F2544]">Chi tiết từng tệp (${rep.items.length})</summary>
            <div class="mt-2 max-h-56 overflow-y-auto divide-y divide-slate-100">
              ${rep.items.map((it) => `
                <div class="py-1.5 flex flex-wrap items-center justify-between gap-2">
                  <div class="min-w-0 flex-1">
                    <span class="font-medium text-[#0F2544]">${esc(it.original_filename)}</span>
                    ${it.target_filename && it.converted ? `<span class="text-[#2563EB]"> → ${esc(it.target_filename)}</span>` : ''}
                    <div class="text-[11px] text-slate-500">${esc(it.message)}</div>
                  </div>
                  <span class="px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                    it.status === 'success' ? 'badge-pass' : it.status === 'error' ? 'badge-fail' : 'badge-warn'
                  }">${actionLabel[it.action] || esc(it.action)}</span>
                </div>
              `).join('')}
            </div>
          </details>
        ` : ''}
      </div>
    `;
  };

  ns.adminUploadFolder = async function (input) {
    const fileList = Array.from(input.files || []);
    if (!fileList.length) return;

    const prog = document.getElementById('adminFolderProgress');
    const progText = document.getElementById('adminFolderProgressText');
    if (prog) prog.classList.remove('hidden');
    if (progText) {
      progText.textContent = `Đang tải lên ${fileList.length} tệp từ thư mục, tự động lọc & chuyển đổi .doc/.docx/.pdf sang chuẩn RAG và đồng bộ Qdrant...`;
    }

    const fd = new FormData();
    fileList.forEach((f) => {
      const relName = f.webkitRelativePath && f.webkitRelativePath.trim() ? f.webkitRelativePath : f.name;
      fd.append('files', f, relName);
    });

    try {
      const res = await api(
        `/api/legal-documents/upload-folder?allow_update=${ns.state.adminAllowUpdate ? 'true' : 'false'}`,
        { method: 'POST', body: fd }
      );
      ns.state.lastFolderUploadReport = res;
      toast(res.message, res.error_count > 0 ? 'warn' : 'success');
      await ns.renderCurrentPage();
    } catch (e) {
      toast(e.message || 'Lỗi tải lên thư mục văn bản.', 'error');
    } finally {
      if (prog) prog.classList.add('hidden');
      input.value = '';
    }
  };

  ns.adminUploadDoc = async function (input) {
    const file = input.files && input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await api(`/api/legal-documents/upload?allow_update=${ns.state.adminAllowUpdate ? 'true' : 'false'}`, {
        method: 'POST',
        body: fd,
      });
      toast(res.message, res.status === 'error' ? 'error' : 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      input.value = '';
    }
  };

  ns.adminCreateDoc = async function () {
    const payload = {
      filename: document.getElementById('newDocFilename')?.value?.trim() || 'van_ban_moi.json',
      title: document.getElementById('newDocTitle')?.value?.trim() || '',
      document_number: document.getElementById('newDocNumber')?.value?.trim() || null,
      document_type: document.getElementById('newDocType')?.value?.trim() || null,
      issuing_authority: document.getElementById('newDocAuthority')?.value?.trim() || null,
      effective_date: document.getElementById('newDocEffDate')?.value?.trim() || null,
      content: document.getElementById('newDocContent')?.value?.trim() || '',
      allow_update: Boolean(ns.state.adminAllowUpdate),
    };
    if (!payload.title || !payload.content) {
      toast('Vui lòng nhập Tên văn bản và Nội dung văn bản.', 'warn');
      return;
    }
    try {
      const res = await api('/api/legal-documents/create', { method: 'POST', body: JSON.stringify(payload) });
      toast(res.message, res.status === 'error' ? 'error' : 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.openEditMetadataPrompt = async function (docId, curTitle, curNum, curStatus) {
    const title = prompt('Tên văn bản:', curTitle);
    if (title === null) return;
    const document_number = prompt('Số hiệu văn bản:', curNum);
    if (document_number === null) return;
    const status = prompt('Tình trạng hiệu lực (để trống nếu chưa xác định):', curStatus);
    if (status === null) return;
    try {
      await api(`/api/legal-documents/${encodeURIComponent(docId)}`, {
        method: 'PUT',
        body: JSON.stringify({ title, document_number, status }),
      });
      toast('Đã cập nhật metadata văn bản.', 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.adminDeleteDoc = async function (docId, title) {
    if (!confirm(`Xác nhận xóa văn bản "${title}" và chỉ xóa các vector thuộc document_id này trên Qdrant?`)) return;
    try {
      const res = await api(`/api/legal-documents/${encodeURIComponent(docId)}`, { method: 'DELETE' });
      toast(`Đã xóa "${res.title}" (${res.deleted_chunks} chunks DB, ${res.deleted_vectors} vectors Qdrant).`, 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // -------------------------------------------------------------------------
  // Admin Page 3: Quản lý dữ liệu RAG
  // -------------------------------------------------------------------------
  ns.renderAdminRag = async function (container) {
    const [stats, docs] = await Promise.all([api('/api/rag/status'), api('/api/legal-documents')]);
    const stages = ['Upload', 'Extraction', 'Cleaning', 'Chunking', 'Embedding', 'Indexing (Qdrant)'];

    container.innerHTML = `
      <div class="space-y-5">
        <!-- Visual Pipeline -->
        <div class="card p-5 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h2 class="text-sm font-bold text-[#0F2544]">Pipeline xử lý dữ liệu RAG (Module Nguyễn Thanh Hiền)</h2>
            ${statusBadge(stats.qdrant_connected ? 'online' : 'offline')}
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            ${stages.map((st, idx) => `
              <div class="p-3 rounded-xl bg-[#EFF6FF] border border-blue-200 text-center">
                <div class="text-[11px] font-bold text-[#2563EB]">Bước ${idx + 1}</div>
                <div class="text-xs font-bold text-[#0F2544] mt-0.5">${st}</div>
              </div>
            `).join('')}
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2 text-xs">
            <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><div class="text-slate-500">Collection Qdrant</div><div class="font-bold text-[#0F2544] mt-0.5">${esc(stats.qdrant_collection)}</div></div>
            <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><div class="text-slate-500">Vectors trên Qdrant</div><div class="font-bold text-[#0F2544] mt-0.5">${stats.qdrant_points_count} / ${stats.total_chunks} chunks</div></div>
            <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><div class="text-slate-500">Embedding Model</div><div class="font-bold text-[#0F2544] mt-0.5 truncate" title="${esc(stats.embedding_model)}">${esc(stats.embedding_model)}</div></div>
            <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><div class="text-slate-500">Chế độ Qdrant</div><div class="font-bold text-[#0F2544] mt-0.5">${esc(stats.qdrant_backend)}</div></div>
          </div>
        </div>

        <!-- Interactive RAG Vector Search Tester -->
        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">Kiểm thử truy xuất Vector Search (Qdrant)</h3>
          <div class="flex gap-2">
            <input id="ragTestQuery" type="text" placeholder="Nhập truy vấn pháp lý để kiểm tra Top-K chunk từ Qdrant..."
              class="flex-1 px-3.5 py-2 rounded-lg border border-slate-300 text-xs"
              onkeydown="if(event.key==='Enter'){window.LegalApp.runRagSearchTest();}" />
            <button onclick="window.LegalApp.runRagSearchTest()" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Tìm kiếm Qdrant</button>
          </div>
          <div id="ragSearchOutput" class="text-xs text-slate-500">Nhập truy vấn để kiểm tra độ chính xác truy xuất RAG.</div>
        </div>

        <!-- Indexed Documents Management -->
        <div class="card p-5 space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-[#0F2544]">Danh sách tài liệu & đồng bộ theo Document ID</h3>
            <button onclick="window.LegalApp.adminScanSync()" class="btn-soft px-3 py-1.5 rounded-lg text-xs font-semibold">Đồng bộ toàn bộ thư mục</button>
          </div>
          ${docs.items.length ? `
            <div class="space-y-2">
              ${docs.items.map((d) => `
                <div class="p-3 rounded-lg bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div>
                    <div class="font-bold text-[#0F2544]">${esc(d.title)} <span class="font-normal text-slate-500">(${esc(d.document_id)})</span></div>
                    <div class="text-[11px] text-slate-500">Chunks: ${d.qdrant_synced_chunks}/${d.chunk_count} · File: ${esc(d.file_path)} ${d.last_error ? `· Lỗi: ${esc(d.last_error)}` : ''}</div>
                  </div>
                  <div class="flex items-center gap-2">
                    ${statusBadge(d.qdrant_sync_status)}
                    <button onclick="window.LegalApp.adminReingestDoc('${esc(d.document_id)}')" class="btn-soft px-2.5 py-1 rounded text-xs font-semibold">Nạp lại</button>
                    <button onclick="window.LegalApp.adminDeleteDoc('${esc(d.document_id)}',${JSON.stringify(d.title).replace(/"/g, '&quot;')})" class="text-red-600 font-semibold hover:underline">Xóa theo ID</button>
                  </div>
                </div>
              `).join('')}
            </div>
          ` : `<div class="text-xs text-slate-500">Chưa có tài liệu nào được nạp vào RAG.</div>`}
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns.adminReingestDoc = async function (docId) {
    try {
      const res = await api(`/api/legal-documents/${encodeURIComponent(docId)}/reingest`, { method: 'POST' });
      toast(res.message, res.status === 'error' ? 'error' : 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.runRagSearchTest = async function () {
    const q = document.getElementById('ragTestQuery')?.value?.trim();
    const out = document.getElementById('ragSearchOutput');
    if (!q || !out) return;
    out.innerHTML = 'Đang truy vấn Qdrant...';
    try {
      const res = await api('/api/rag/search', { method: 'POST', body: JSON.stringify({ query: q, top_k: 5 }) });
      if (!res.qdrant_available || !res.hits.length) {
        out.innerHTML = `<div class="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900">${esc(res.detail)} (0 kết quả phù hợp)</div>`;
        return;
      }
      out.innerHTML = `<div class="space-y-2">${res.hits.map((h, i) => `
        <div class="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
          <div class="flex justify-between"><strong>${i + 1}. ${esc(h.document_name)} ${h.article ? '· ' + esc(h.article) : ''}</strong><span class="font-semibold text-[#2563EB]">Score: ${h.relevance_score}</span></div>
          <div class="text-slate-700">${esc(h.content)}</div>
        </div>
      `).join('')}</div>`;
    } catch (e) {
      out.innerHTML = `<div class="text-red-600">${esc(e.message)}</div>`;
    }
  };

  // -------------------------------------------------------------------------
  // Admin Page 4: Theo dõi Agent
  // -------------------------------------------------------------------------
  ns.renderAdminAgent = async function (container) {
    const [status, logs] = await Promise.all([api('/api/agent/status'), api('/api/agent/logs?limit=30')]);

    container.innerHTML = `
      <div class="space-y-5">
        <div class="card p-5 space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-bold text-[#0F2544]">Theo dõi Multi-Agent Pipeline (Module Đặng Thị Ngọc Ánh)</h2>
              <p class="text-xs text-slate-500">${esc(status.qdrant_detail)}</p>
            </div>
            ${statusBadge(status.status)}
          </div>
          <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5">
            ${status.pipeline_stages.map((st, i) => `
              <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 text-center">
                <div class="text-[11px] font-semibold text-[#2563EB]">Stage ${i + 1}</div>
                <div class="text-xs font-bold text-[#0F2544] mt-0.5">${esc(st)}</div>
              </div>
            `).join('')}
          </div>
          <div class="grid grid-cols-3 gap-3 text-xs">
            <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><div class="text-slate-500">Tổng lượt chạy Agent</div><div class="text-lg font-bold text-[#0F2544]">${status.total_runs}</div></div>
            <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><div class="text-slate-500">Lượt có Self-Correction</div><div class="text-lg font-bold text-amber-600">${status.self_correction_runs}</div></div>
            <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><div class="text-slate-500">Lượt phát sinh lỗi</div><div class="text-lg font-bold text-red-600">${status.error_runs}</div></div>
          </div>
        </div>

        <!-- Agent Analyze Quick Tester -->
        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">Kiểm thử phân rã vấn đề pháp lý (POST /api/agent/analyze)</h3>
          <div class="flex gap-2">
            <input id="agentTestInput" type="text" placeholder="Nhập câu hỏi phức tạp cần phân rã đa văn bản..." class="flex-1 px-3.5 py-2 rounded-lg border border-slate-300 text-xs" />
            <button onclick="window.LegalApp.runAgentAnalyzeTest()" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Phân tích</button>
          </div>
          <div id="agentAnalyzeOut" class="text-xs text-slate-500"></div>
        </div>

        <!-- Real Agent Run Logs -->
        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">Nhật ký thực thi Agent gần đây (${logs.length})</h3>
          ${logs.length ? `
            <div class="space-y-2.5">
              ${logs.map((lg) => `
                <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-2">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div class="font-bold text-[#0F2544]">${esc(lg.question)}</div>
                    <div class="flex items-center gap-2">
                      ${statusBadge(lg.overall_status)}
                      <span class="text-slate-500">${lg.latency_ms} ms</span>
                      <span class="text-slate-500">Self-correction: ${lg.self_correction_attempts}</span>
                    </div>
                  </div>
                  ${lg.error_message ? `<div class="text-red-600">Lỗi: ${esc(lg.error_message)}</div>` : ''}
                  <div class="flex flex-wrap gap-1.5">
                    ${(lg.stages || []).map((st) => `
                      <span class="px-2 py-0.5 rounded border text-[11px] ${
                        st.status === 'completed' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' :
                        st.status === 'error' ? 'bg-red-50 border-red-200 text-red-800' :
                        'bg-amber-50 border-amber-200 text-amber-800'
                      }">${st.step_number}. ${esc(st.label)}</span>
                    `).join('')}
                  </div>
                </div>
              `).join('')}
            </div>
          ` : `<div class="text-xs text-slate-500">Chưa có nhật ký thực thi Agent.</div>`}
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns.runAgentAnalyzeTest = async function () {
    const q = document.getElementById('agentTestInput')?.value?.trim();
    const out = document.getElementById('agentAnalyzeOut');
    if (!q || !out) return;
    try {
      const res = await api('/api/agent/analyze', { method: 'POST', body: JSON.stringify({ question: q }) });
      out.innerHTML = `
        <div class="p-3 rounded-lg bg-[#EFF6FF] border border-blue-200 space-y-1.5">
          <div><strong>Lĩnh vực:</strong> ${esc(res.detected_domain)} · <strong>Đa văn bản:</strong> ${res.needs_multi_document ? 'Có' : 'Không'}</div>
          <ul class="list-disc pl-4 space-y-1">${res.issues.map((i) => `<li>${esc(i.issue)}</li>`).join('')}</ul>
        </div>
      `;
    } catch (e) {
      out.innerHTML = `<div class="text-red-600">${esc(e.message)}</div>`;
    }
  };

  // -------------------------------------------------------------------------
  // Admin Page 5: Citation Validator
  // -------------------------------------------------------------------------
  ns.renderAdminCitations = async function (container) {
    const filter = ns.state.citFilter || '';
    const [report, list] = await Promise.all([
      api('/api/citations/report'),
      api(`/api/citations${filter ? '?status=' + filter : ''}`),
    ]);

    container.innerHTML = `
      <div class="space-y-5">
        <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <div class="card p-4"><div class="text-xs text-slate-500">Tổng citation đã kiểm</div><div class="text-2xl font-bold text-[#0F2544] mt-1">${report.total_checked}</div></div>
          <div class="card p-4"><div class="text-xs text-slate-500">Hợp lệ (PASS)</div><div class="text-2xl font-bold text-emerald-600 mt-1">${report.valid_count}</div></div>
          <div class="card p-4"><div class="text-xs text-slate-500">Không hợp lệ (FAIL)</div><div class="text-2xl font-bold text-red-600 mt-1">${report.invalid_count}</div></div>
          <div class="card p-4"><div class="text-xs text-slate-500">Thiếu bằng chứng</div><div class="text-2xl font-bold text-amber-600 mt-1">${report.insufficient_count}</div></div>
          <div class="card p-4"><div class="text-xs text-slate-500">Số lần Self-Correction</div><div class="text-2xl font-bold text-[#2563EB] mt-1">${report.total_self_correction_attempts}</div></div>
        </div>

        <!-- Direct Citation Validator 6-point Tester -->
        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">Kiểm thử trực tiếp Citation Validator (6 tiêu chí đối chiếu gốc)</h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-xs">
            <input id="cvClaim" placeholder="Nhận định cần kiểm chứng *" class="md:col-span-3 px-3 py-2 rounded-lg border border-slate-300" />
            <input id="cvDocNum" placeholder="Số hiệu văn bản (vd: 45/2019/QH14)" class="px-3 py-2 rounded-lg border border-slate-300" />
            <input id="cvArticle" placeholder="Điều (vd: Điều 35)" class="px-3 py-2 rounded-lg border border-slate-300" />
            <input id="cvClause" placeholder="Khoản (vd: Khoản 1)" class="px-3 py-2 rounded-lg border border-slate-300" />
            <textarea id="cvEvidence" rows="2" placeholder="Đoạn trích bằng chứng (tùy chọn nếu kiểm tra đối chiếu trực tiếp)" class="md:col-span-3 px-3 py-2 rounded-lg border border-slate-300"></textarea>
          </div>
          <button onclick="window.LegalApp.runCitationValidateTest()" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Kiểm chứng trích dẫn</button>
          <div id="cvOutput" class="text-xs"></div>
        </div>

        <!-- History Table -->
        <div class="card p-5 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-sm font-bold text-[#0F2544]">Lịch sử kiểm chứng trích dẫn (${list.length})</h3>
            <div class="flex gap-1.5">
              ${[['', 'Tất cả'], ['PASS', 'PASS'], ['FAIL', 'FAIL'], ['UNVERIFIED', 'UNVERIFIED']].map(([v, l]) => `
                <button onclick="window.LegalApp.state.citFilter='${v}';window.LegalApp.renderCurrentPage();"
                  class="px-3 py-1 rounded-lg text-xs font-semibold ${filter === v ? 'btn-navy' : 'bg-slate-100 text-slate-600'}">${l}</button>
              `).join('')}
            </div>
          </div>
          ${list.length ? `
            <div class="space-y-2.5">
              ${list.slice(0, 30).map((c) => `
                <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-1.5">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <span class="font-bold text-[#0F2544]">${esc(c.document_name)} ${c.document_number ? '(' + esc(c.document_number) + ')' : ''} ${c.article ? '· ' + esc(c.article) : ''}</span>
                    ${statusBadge(c.validation_status)}
                  </div>
                  <div class="text-slate-700"><strong>Nhận định:</strong> ${esc(c.claim)}</div>
                  <div class="text-slate-600"><strong>Lý do kiểm chứng:</strong> ${esc(c.validation_reason)}</div>
                </div>
              `).join('')}
            </div>
          ` : `<div class="text-xs text-slate-500">Chưa có bản ghi kiểm chứng trích dẫn.</div>`}
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns.runCitationValidateTest = async function () {
    const out = document.getElementById('cvOutput');
    const payload = {
      claim: document.getElementById('cvClaim')?.value?.trim() || '',
      document_number: document.getElementById('cvDocNum')?.value?.trim() || null,
      article: document.getElementById('cvArticle')?.value?.trim() || null,
      clause: document.getElementById('cvClause')?.value?.trim() || null,
      evidence: document.getElementById('cvEvidence')?.value?.trim() || null,
    };
    if (!payload.claim) {
      toast('Vui lòng nhập nhận định cần kiểm chứng.', 'warn');
      return;
    }
    try {
      const res = await api('/api/citations/validate', { method: 'POST', body: JSON.stringify(payload) });
      out.innerHTML = `
        <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
          <div class="flex items-center gap-2">${statusBadge(res.validation_status)} <strong>${esc(res.support_status)}</strong> (Độ khớp: ${Math.round(res.overlap_ratio * 100)}%)</div>
          <div class="text-slate-700">${esc(res.reason)}</div>
        </div>
      `;
    } catch (e) {
      out.innerHTML = `<div class="text-red-600">${esc(e.message)}</div>`;
    }
  };

  // -------------------------------------------------------------------------
  // Admin Page 6: Testing Dashboard & 4-Variant Evaluation
  // -------------------------------------------------------------------------
  ns.renderAdminTesting = async function (container) {
    const [reports, evalData] = await Promise.all([
      api('/api/admin/test-results').catch(() => []),
      api('/api/evaluation/results').catch(() => ({ has_results: false, variants: [], note: '' })),
    ]);

    container.innerHTML = `
      <div class="space-y-5">
        <div class="card p-5 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-bold text-[#0F2544]">Testing Dashboard (Chỉ hiển thị kết quả kiểm thử thực tế)</h2>
              <p class="text-xs text-slate-500">Unit Test · Integration Test · API Test · RAG Test · Agent Test · Citation Test · End-to-End Test</p>
            </div>
          </div>
          ${reports.length ? `
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="bg-slate-50 text-slate-500 uppercase border-b border-slate-200">
                  <tr>
                    <th class="px-3 py-2.5">Bộ kiểm thử</th>
                    <th class="px-3 py-2.5">Nhóm</th>
                    <th class="px-3 py-2.5 text-right">Tổng</th>
                    <th class="px-3 py-2.5 text-right">Đạt</th>
                    <th class="px-3 py-2.5 text-right">Lỗi</th>
                    <th class="px-3 py-2.5 text-right">Thời gian</th>
                    <th class="px-3 py-2.5">Trạng thái</th>
                    <th class="px-3 py-2.5">Thời điểm</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  ${reports.map((r) => `
                    <tr>
                      <td class="px-3 py-2.5 font-semibold text-[#0F2544]">${esc(r.suite_name)}</td>
                      <td class="px-3 py-2.5">${esc(r.category)}</td>
                      <td class="px-3 py-2.5 text-right">${r.total}</td>
                      <td class="px-3 py-2.5 text-right text-emerald-700 font-semibold">${r.passed}</td>
                      <td class="px-3 py-2.5 text-right ${r.failed > 0 ? 'text-red-600 font-semibold' : ''}">${r.failed}</td>
                      <td class="px-3 py-2.5 text-right">${r.duration_ms} ms</td>
                      <td class="px-3 py-2.5">${statusBadge(r.status)}</td>
                      <td class="px-3 py-2.5 text-slate-500">${fmtDate(r.created_at)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : `
            <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
              Chưa có bản ghi chạy kiểm thử tự động nào được nạp vào CSDL. Chạy lệnh <code>python -m pytest backend/tests -v</code> hoặc script ghi nhận báo cáo kiểm thử để cập nhật số liệu thực tế tại đây.
            </div>
          `}
        </div>

        <!-- 4-Variant Evaluation Matrix -->
        <div class="card p-5 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 class="text-sm font-bold text-[#0F2544]">So sánh thực nghiệm 4 phiên bản (Model A → Model D)</h3>
              <p class="text-xs text-slate-500">${esc(evalData.note)}</p>
            </div>
            <button onclick="window.LegalApp.runEvaluationSnapshot()" class="btn-navy px-3.5 py-2 rounded-lg text-xs font-semibold">
              Ghi nhận phiên đánh giá
            </button>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead class="bg-slate-50 text-slate-500 uppercase border-b border-slate-200">
                <tr>
                  <th class="px-3 py-2.5">Phiên bản</th>
                  <th class="px-3 py-2.5 text-right">Recall@K</th>
                  <th class="px-3 py-2.5 text-right">Answer Acc</th>
                  <th class="px-3 py-2.5 text-right">Citation Acc</th>
                  <th class="px-3 py-2.5 text-right">Support Rate</th>
                  <th class="px-3 py-2.5 text-right">Hallucination</th>
                  <th class="px-3 py-2.5 text-right">Latency</th>
                  <th class="px-3 py-2.5 text-right">Self-Correction</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                ${(evalData.variants || []).map((v) => `
                  <tr>
                    <td class="px-3 py-2.5 font-semibold text-[#0F2544]">${esc(v.variant)}</td>
                    <td class="px-3 py-2.5 text-right">${v.recall_at_k ?? 'N/A'}</td>
                    <td class="px-3 py-2.5 text-right">${v.answer_accuracy ?? 'N/A'}</td>
                    <td class="px-3 py-2.5 text-right">${v.citation_accuracy ?? 'N/A'}</td>
                    <td class="px-3 py-2.5 text-right">${v.citation_support_rate ?? 'N/A'}</td>
                    <td class="px-3 py-2.5 text-right">${v.hallucination_rate ?? 'N/A'}</td>
                    <td class="px-3 py-2.5 text-right">${v.latency_ms ?? 'N/A'}</td>
                    <td class="px-3 py-2.5 text-right">${v.self_correction_rate ?? 'N/A'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns.runEvaluationSnapshot = async function () {
    try {
      const res = await api('/api/evaluation/run', { method: 'POST', body: JSON.stringify({ sample_size: 60 }) });
      toast(res.note, 'info');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // -------------------------------------------------------------------------
  // Admin Page 7: Quản lý người dùng & Phân quyền
  // -------------------------------------------------------------------------
  ns.renderAdminUsers = async function (container) {
    const [users, logs] = await Promise.all([api('/api/admin/users'), api('/api/admin/activity-logs?limit=40')]);

    container.innerHTML = `
      <div class="space-y-5">
        <div class="card overflow-x-auto">
          <div class="p-4 border-b border-slate-100 flex items-center justify-between">
            <h2 class="text-sm font-bold text-[#0F2544]">Danh sách tài khoản & Phân quyền (${users.length})</h2>
          </div>
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 text-slate-500 uppercase border-b border-slate-200">
              <tr>
                <th class="px-3 py-3">Tài khoản</th>
                <th class="px-3 py-3">Email</th>
                <th class="px-3 py-3">Họ và tên</th>
                <th class="px-3 py-3">Vai trò</th>
                <th class="px-3 py-3">Trạng thái</th>
                <th class="px-3 py-3">Đăng nhập gần nhất</th>
                <th class="px-3 py-3 text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${users.map((u) => `
                <tr>
                  <td class="px-3 py-3 font-semibold text-[#0F2544]">@${esc(u.username)}</td>
                  <td class="px-3 py-3">${esc(u.email)}</td>
                  <td class="px-3 py-3">${esc(u.full_name)}</td>
                  <td class="px-3 py-3">
                    <select onchange="window.LegalApp.adminChangeUserRole('${esc(u.id)}', this.value)"
                      class="px-2 py-1 rounded border border-slate-300 bg-white text-xs">
                      <option value="user" ${u.role === 'user' ? 'selected' : ''}>user</option>
                      <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>admin</option>
                    </select>
                  </td>
                  <td class="px-3 py-3">${statusBadge(u.is_active ? 'online' : 'offline')}</td>
                  <td class="px-3 py-3 text-slate-500">${fmtDate(u.last_login_at)}</td>
                  <td class="px-3 py-3 text-right">
                    <button onclick="window.LegalApp.adminToggleUserStatus('${esc(u.id)}', ${!u.is_active})"
                      class="font-semibold ${u.is_active ? 'text-red-600' : 'text-emerald-700'} hover:underline">
                      ${u.is_active ? 'Khóa tài khoản' : 'Mở khóa'}
                    </button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>

        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">Nhật ký hoạt động hệ thống (${logs.length})</h3>
          <div class="space-y-1.5 max-h-72 overflow-y-auto">
            ${logs.map((l) => `
              <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-2 text-xs">
                <div><strong class="text-[#0F2544]">@${esc(l.username)}</strong> · <span class="px-1.5 py-0.5 rounded bg-white border border-slate-200">${esc(l.action)}</span> · ${esc(l.detail)}</div>
                <span class="text-[11px] text-slate-400">${fmtDate(l.created_at)}</span>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns.adminChangeUserRole = async function (userId, role) {
    try {
      await api(`/api/admin/users/${encodeURIComponent(userId)}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role }),
      });
      toast('Đã cập nhật quyền người dùng.', 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
      ns.renderCurrentPage();
    }
  };

  ns.adminToggleUserStatus = async function (userId, isActive) {
    try {
      await api(`/api/admin/users/${encodeURIComponent(userId)}/status`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: isActive }),
      });
      toast(isActive ? 'Đã mở khóa tài khoản.' : 'Đã khóa tài khoản.', 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // -------------------------------------------------------------------------
  // Admin Page 8: Cấu hình hệ thống (NEVER exposes raw API keys)
  // -------------------------------------------------------------------------
  ns.renderAdminConfig = async function (container) {
    const [cfg, st] = await Promise.all([api('/api/admin/system-config'), api('/api/status')]);

    container.innerHTML = `
      <div class="space-y-5">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div class="card p-5 space-y-4">
            <h2 class="text-sm font-bold text-[#0F2544]">Cấu hình vận hành & LLM</h2>
            <div class="space-y-3 text-xs">
              <div>
                <label class="block font-semibold text-slate-600 mb-1">Chế độ hệ thống (APP_MODE)</label>
                <select id="cfgAppMode" class="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white">
                  <option value="demo" ${cfg.app_mode === 'demo' ? 'selected' : ''}>DEMO (is_mock=true — kiểm thử giao diện an toàn)</option>
                  <option value="live" ${cfg.app_mode === 'live' ? 'selected' : ''}>LIVE (RAG Qdrant + Agent + Citation Validator thật)</option>
                </select>
              </div>
              <div>
                <label class="block font-semibold text-slate-600 mb-1">Model LLM</label>
                <input id="cfgLlmModel" type="text" value="${esc(cfg.llm_model)}" class="w-full px-3 py-2 rounded-lg border border-slate-300" />
              </div>
              <div>
                <label class="block font-semibold text-slate-600 mb-1">Giới hạn vòng lặp Self-Correction (1–5)</label>
                <input id="cfgMaxSC" type="number" min="1" max="5" value="${cfg.max_self_correction_attempts}" class="w-full px-3 py-2 rounded-lg border border-slate-300" />
              </div>
              <div class="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
                <div><strong>LLM API Key:</strong> <code>${esc(cfg.llm_api_key_masked)}</code></div>
                <div class="text-[11px] text-slate-500">Bảo mật: API Key thật chỉ nạp từ biến môi trường <code>.env</code> và không bao giờ hiển thị công khai.</div>
              </div>
              <button onclick="window.LegalApp.saveAdminConfig()" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Lưu cấu hình</button>
            </div>
          </div>

          <div class="card p-5 space-y-4">
            <h2 class="text-sm font-bold text-[#0F2544]">Kết nối Embedding, Qdrant & PostgreSQL</h2>
            <div class="space-y-2.5 text-xs">
              <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><strong>Embedding Model:</strong><div class="mt-0.5 text-slate-600">${esc(cfg.embedding_model)}</div></div>
              <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><strong>Qdrant:</strong><div class="mt-0.5 text-slate-600">${esc(cfg.qdrant_url)} (mode: ${esc(cfg.qdrant_mode)}, collection: ${esc(cfg.qdrant_collection)})</div></div>
              <div class="p-3 rounded-lg bg-slate-50 border border-slate-200"><strong>Database:</strong><div class="mt-0.5 text-slate-600">${esc(cfg.database_backend)}</div></div>
            </div>
            <div class="space-y-2 pt-2 border-t border-slate-100">
              <div class="text-xs font-bold text-[#0F2544]">Kiểm tra sức khỏe dịch vụ</div>
              ${[st.database, st.qdrant, st.llm, st.rag, st.agent, st.citation_validator].map((sv) => `
                <div class="flex items-center justify-between text-xs py-1">
                  <span class="font-medium text-slate-700">${esc(sv.name)}</span>
                  ${statusBadge(sv.status)}
                </div>
              `).join('')}
            </div>
          </div>
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns.saveAdminConfig = async function () {
    try {
      const res = await api('/api/admin/system-config', {
        method: 'PUT',
        body: JSON.stringify({
          app_mode: document.getElementById('cfgAppMode')?.value,
          llm_model: document.getElementById('cfgLlmModel')?.value?.trim(),
          max_self_correction_attempts: Number(document.getElementById('cfgMaxSC')?.value || 2),
        }),
      });
      ns.state.appMode = res.app_mode;
      toast('Đã cập nhật cấu hình hệ thống.', 'success');
      ns.syncHeaderChrome();
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };
})(window.LegalApp);
