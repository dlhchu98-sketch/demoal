// =========================================================================
// Legal AI Assistant — USER PORTAL (8 dedicated pages)
// 1. Trang chủ | 2. Trợ lý pháp luật | 3. Theo dõi quá trình xử lý (7 bước)
// 4. Kết quả tra cứu (A-E) | 5. Tra cứu văn bản | 6. Lịch sử tra cứu
// 7. Văn bản đã lưu | 8. Tài khoản
// =========================================================================

window.LegalApp = window.LegalApp || {};

(function (ns) {
  const { esc, fmtDate, statusBadge, api, toast } = ns;

  ns.USER_NAV = [
    { id: 'home', label: 'Trang chủ', icon: 'home', subtitle: 'Khám phá lĩnh vực pháp luật và đặt câu hỏi tra cứu nhanh' },
    { id: 'chat', label: 'Trợ lý pháp luật', icon: 'message-square-text', subtitle: 'Hỏi đáp pháp luật nhiều lượt với RAG, Agent và Citation Validator' },
    { id: 'process', label: 'Theo dõi quá trình xử lý', icon: 'git-branch', subtitle: 'Tiến trình 7 bước thật từ Backend (không giả lập trạng thái)' },
    { id: 'result', label: 'Kết quả tra cứu', icon: 'file-check-2', subtitle: 'Cấu trúc kết luận pháp lý chuẩn A–E kèm căn cứ và kiểm chứng' },
    { id: 'documents', label: 'Tra cứu văn bản pháp luật', icon: 'book-open-text', subtitle: 'Tìm kiếm, lọc và xem toàn văn các Điều/Khoản/Điểm văn bản' },
    { id: 'history', label: 'Lịch sử tra cứu', icon: 'history', subtitle: 'Xem lại các cuộc hội thoại, tóm tắt và tiếp tục tra cứu' },
    { id: 'saved', label: 'Văn bản đã lưu', icon: 'bookmark', subtitle: 'Văn bản yêu thích, điều khoản và câu trả lời đã lưu' },
    { id: 'account', label: 'Tài khoản', icon: 'user-circle', subtitle: 'Đăng nhập, đăng ký, thông tin cá nhân và đổi mật khẩu' },
  ];

  // -------------------------------------------------------------------------
  // Page 1: Trang chủ (Home)
  // -------------------------------------------------------------------------
  ns.renderUserHome = async function (container) {
    container.innerHTML = `<div class="p-8 text-center text-sm text-slate-500">Đang tải dữ liệu trang chủ...</div>`;
    const [catData, qData, stats] = await Promise.all([
      api('/api/questions/categories').catch(() => ({ loaded: false, items: [], domains: [] })),
      api('/api/questions?page=1&page_size=12').catch(() => ({ loaded: false, items: [], total_questions: 0 })),
      api('/api/statistics').catch(() => ({ total_documents: 0, total_queries: 0, total_questions: 0, app_mode: 'demo' })),
    ]);

    const domainCounts = {};
    (catData.items || []).forEach((c) => {
      const dom = c.domain || 'Pháp luật Việt Nam';
      domainCounts[dom] = (domainCounts[dom] || 0) + (c.question_count || 0);
    });
    const domainList = Object.entries(domainCounts);

    const sampleQuestions = (qData.items || []).slice(0, 8);

    container.innerHTML = `
      <div class="space-y-6">
        <!-- Hero Search Banner -->
        <section class="rounded-2xl bg-gradient-to-br from-[#0F2544] via-[#17355E] to-[#1E4B85] text-white p-6 lg:p-8 shadow-sm">
          <div class="max-w-3xl space-y-4">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/20 text-xs font-semibold text-blue-100">
              <i data-lucide="scale" class="w-3.5 h-3.5"></i>
              <span>LEGAL AI ASSISTANT · RAG · Multi-Agent · Citation Validator</span>
            </div>
            <h2 class="text-2xl lg:text-3xl font-bold leading-snug">
              Tra cứu pháp luật Việt Nam có căn cứ trích dẫn và tự kiểm chứng
            </h2>
            <p class="text-sm text-blue-100/90 leading-relaxed">
              Hỗ trợ người dùng phổ thông và sinh viên đặt câu hỏi bằng ngôn ngữ tự nhiên, tự động phân tích tình huống,
              đối chiếu văn bản pháp luật theo Điều/Khoản/Điểm và kiểm tra độ tin cậy của từng trích dẫn trước khi trả lời.
            </p>
            <div class="bg-white rounded-xl p-2 flex flex-col sm:flex-row gap-2 shadow-md">
              <input id="homeQuickQuestion" type="text"
                placeholder="Nhập tình huống pháp lý của bạn (vd: Đơn phương chấm dứt hợp đồng lao động cần báo trước bao nhiêu ngày?)"
                class="flex-1 px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 focus:outline-none rounded-lg"
                onkeydown="if(event.key==='Enter'){window.LegalApp.askFromHome();}" />
              <button onclick="window.LegalApp.askFromHome()"
                class="btn-navy px-5 py-2.5 rounded-lg text-sm font-semibold inline-flex items-center justify-center gap-2 shrink-0">
                <i data-lucide="send" class="w-4 h-4"></i>
                <span>Tra cứu ngay</span>
              </button>
            </div>
            <div class="flex flex-wrap gap-4 text-xs text-blue-100/80 pt-1">
              <span><strong>${stats.total_questions || 0}</strong> tình huống pháp luật mẫu</span>
              <span>•</span>
              <span><strong>${stats.total_documents || 0}</strong> văn bản pháp luật trong kho</span>
              <span>•</span>
              <span><strong>${stats.total_queries || 0}</strong> lượt tra cứu đã ghi nhận</span>
            </div>
          </div>
        </section>

        <!-- Legal Domains -->
        <section class="space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-base font-bold text-[#0F2544]">Các lĩnh vực pháp luật</h3>
            <button onclick="window.LegalApp.navigate('documents')" class="text-xs font-semibold text-[#2563EB] hover:underline">
              Xem kho văn bản →
            </button>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            ${domainList.length ? domainList.map(([dom, cnt]) => `
              <button onclick="window.LegalApp.openDomainQuestions('${esc(dom)}')"
                class="card p-4 text-left hover:border-[#2563EB] hover:shadow-md transition group">
                <div class="flex items-center justify-between">
                  <div class="w-9 h-9 rounded-lg bg-[#EFF6FF] text-[#1D4ED8] flex items-center justify-center">
                    <i data-lucide="landmark" class="w-4 h-4"></i>
                  </div>
                  <span class="text-xs font-semibold text-slate-500">${cnt} câu hỏi</span>
                </div>
                <div class="font-bold text-sm text-[#0F2544] mt-3 group-hover:text-[#2563EB]">${esc(dom)}</div>
                <div class="text-xs text-slate-500 mt-1">Xem tình huống và hỏi trực tiếp AI</div>
              </button>
            `).join('') : `<div class="col-span-4 card p-5 text-sm text-slate-500">Chưa nạp bộ câu hỏi pháp luật (.docx).</div>`}
          </div>
        </section>

        <!-- Sample Situations from Real Question Bank -->
        <section class="card p-5 space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-bold text-[#0F2544]">Tình huống mẫu thường gặp</h3>
              <p class="text-xs text-slate-500">Trích trực tiếp từ tài liệu Bộ câu hỏi pháp luật (QUESTION DATASET — không đưa vào Qdrant)</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <select id="homeDomainFilter" onchange="window.LegalApp.filterHomeQuestions()"
                class="px-3 py-1.5 rounded-lg border border-slate-200 text-xs bg-white text-slate-700">
                <option value="">Tất cả lĩnh vực</option>
                ${(catData.domains || []).map((d) => `<option value="${esc(d)}">${esc(d)}</option>`).join('')}
              </select>
              <select id="homeDiffFilter" onchange="window.LegalApp.filterHomeQuestions()"
                class="px-3 py-1.5 rounded-lg border border-slate-200 text-xs bg-white text-slate-700">
                <option value="">Tất cả mức độ</option>
                <option value="Easy">Easy</option>
                <option value="Medium">Medium</option>
                <option value="Multi-document">Multi-document</option>
                <option value="Hard">Hard</option>
                <option value="Citation-focused">Citation-focused</option>
              </select>
            </div>
          </div>
          <div id="homeQuestionsGrid" class="grid grid-cols-1 md:grid-cols-2 gap-3">
            ${ns._renderSampleQuestionCards(sampleQuestions)}
          </div>
        </section>

        <!-- Usage Guide & AI Limitation Disclaimer -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <section class="card p-5 space-y-3">
            <h3 class="text-sm font-bold text-[#0F2544] flex items-center gap-2">
              <i data-lucide="compass" class="w-4 h-4 text-[#2563EB]"></i>
              <span>Hướng dẫn sử dụng</span>
            </h3>
            <ol class="space-y-2 text-xs text-slate-600 list-decimal pl-4">
              <li>Nhập câu hỏi tình huống pháp luật cụ thể bằng tiếng Việt tự nhiên (nêu rõ thời điểm, loại hợp đồng hoặc bối cảnh).</li>
              <li>Hệ thống tự động chạy đủ <strong>7 bước</strong> (Phân tích → Phân rã → Tìm kiếm Qdrant → Đối chiếu → Kiểm tra trích dẫn → Trả kết quả).</li>
              <li>Kiểm tra mục <strong>C. Căn cứ pháp lý</strong> và <strong>D. Kết quả kiểm chứng</strong>, bấm vào từng trích dẫn để đọc nguyên văn văn bản gốc.</li>
            </ol>
          </section>
          <section class="rounded-xl bg-amber-50 border border-amber-200 p-5 space-y-2">
            <h3 class="text-sm font-bold text-amber-900 flex items-center gap-2">
              <i data-lucide="alert-triangle" class="w-4 h-4 text-amber-600"></i>
              <span>Cảnh báo giới hạn của AI pháp lý</span>
            </h3>
            <p class="text-xs text-amber-900/90 leading-relaxed">
              Hệ thống <strong>chỉ hỗ trợ tra cứu, tổng hợp và dẫn nguồn pháp luật</strong>, không thay thế tư vấn pháp lý chính thức của luật sư hoặc cơ quan nhà nước có thẩm quyền.
              Khi kho dữ liệu chưa có văn bản phù hợp hoặc đang chạy chế độ <strong>DEMO</strong>, hệ thống sẽ báo rõ <em>Chưa đủ bằng chứng</em> và tuyệt đối không tự bịa số hiệu hay điều luật.
            </p>
          </section>
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns._renderSampleQuestionCards = function (items) {
    if (!items || !items.length) {
      return `<div class="col-span-2 text-xs text-slate-500 py-4 text-center">Không tìm thấy câu hỏi phù hợp với bộ lọc.</div>`;
    }
    return items.map((q) => `
      <button onclick="window.LegalApp.askSpecificQuestion(${JSON.stringify(q.question).replace(/"/g, '&quot;')})"
        class="p-3.5 rounded-xl border border-slate-200 hover:border-[#2563EB] hover:bg-[#EFF6FF]/40 text-left transition flex flex-col justify-between gap-2">
        <div class="text-xs font-medium text-slate-800 leading-relaxed">${esc(q.question)}</div>
        <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">${esc(q.domain)}</span>
          <span class="px-2 py-0.5 rounded bg-[#EFF6FF] text-[#1D4ED8]">${esc(q.category_name)}</span>
          <span class="px-2 py-0.5 rounded border border-slate-200 text-slate-500">${esc(q.difficulty)}</span>
        </div>
      </button>
    `).join('');
  };

  ns.filterHomeQuestions = async function () {
    const dom = document.getElementById('homeDomainFilter')?.value || '';
    const diff = document.getElementById('homeDiffFilter')?.value || '';
    const params = new URLSearchParams({ page: '1', page_size: '8' });
    if (dom) params.set('domain', dom);
    if (diff) params.set('difficulty', diff);
    const grid = document.getElementById('homeQuestionsGrid');
    if (!grid) return;
    grid.innerHTML = `<div class="col-span-2 text-xs text-slate-500 py-4 text-center">Đang lọc câu hỏi...</div>`;
    try {
      const res = await api(`/api/questions?${params.toString()}`);
      grid.innerHTML = ns._renderSampleQuestionCards(res.items || []);
    } catch (e) {
      grid.innerHTML = `<div class="col-span-2 text-xs text-red-600">${esc(e.message)}</div>`;
    }
  };

  ns.openDomainQuestions = function (domain) {
    const sel = document.getElementById('homeDomainFilter');
    if (sel) {
      sel.value = domain;
      ns.filterHomeQuestions();
      sel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  ns.askFromHome = function () {
    const input = document.getElementById('homeQuickQuestion');
    const q = input?.value?.trim();
    if (!q) {
      toast('Vui lòng nhập câu hỏi pháp luật trước khi gửi.', 'warn');
      return;
    }
    ns.askSpecificQuestion(q);
  };

  ns.askSpecificQuestion = function (questionText) {
    ns.state.pendingQuestion = questionText;
    ns.navigate('chat');
  };

  // -------------------------------------------------------------------------
  // Page 2: Trợ lý pháp luật (Multi-turn Chatbot)
  // -------------------------------------------------------------------------
  ns.renderUserChat = async function (container) {
    const conversations = await api('/api/chat/conversations').catch(() => []);
    ns.state.conversations = conversations;

    container.innerHTML = `
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        <!-- Left Conversations Column -->
        <aside class="lg:col-span-4 xl:col-span-3 card p-4 space-y-3">
          <button onclick="window.LegalApp.startNewConversation()"
            class="w-full btn-navy py-2.5 px-3 rounded-xl text-xs font-semibold inline-flex items-center justify-center gap-2">
            <i data-lucide="plus-circle" class="w-4 h-4"></i>
            <span>Cuộc hội thoại mới</span>
          </button>
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wide pt-1">Hội thoại gần đây (${conversations.length})</div>
          <div id="chatConversationList" class="space-y-1.5 max-h-[540px] overflow-y-auto">
            ${conversations.length ? conversations.map((c) => `
              <div class="group flex items-start justify-between gap-2 p-2.5 rounded-lg border cursor-pointer transition ${
                ns.state.activeConversationId === c.conversation_id
                  ? 'bg-[#EFF6FF] border-[#93C5FD]'
                  : 'border-slate-200 hover:bg-slate-50'
              }" onclick="window.LegalApp.loadConversation('${esc(c.conversation_id)}')">
                <div class="min-w-0 flex-1">
                  <div class="text-xs font-semibold text-[#0F2544] truncate">${esc(c.title)}</div>
                  <div class="text-[11px] text-slate-500 mt-0.5 flex items-center gap-1.5">
                    <span>${c.message_count} lượt</span>
                    <span>·</span>
                    <span>${esc(c.latest_citation_status)}</span>
                  </div>
                </div>
                <button onclick="event.stopPropagation(); window.LegalApp.deleteConversation('${esc(c.conversation_id)}')"
                  title="Xóa cuộc hội thoại" class="p-1 text-slate-400 hover:text-red-600 opacity-70 group-hover:opacity-100">
                  <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                </button>
              </div>
            `).join('') : `<div class="text-xs text-slate-400 py-6 text-center">Chưa có cuộc hội thoại nào.</div>`}
          </div>
        </aside>

        <!-- Right Chat Thread & Input -->
        <section class="lg:col-span-8 xl:col-span-9 space-y-4">
          <div class="card p-4 lg:p-5 space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <h2 class="text-base font-bold text-[#0F2544]">Trợ lý tra cứu pháp luật AI</h2>
                <p class="text-xs text-slate-500">Agent tự động chạy đủ 7 bước xử lý và kiểm chứng trích dẫn trước khi trả kết quả</p>
              </div>
              <div class="flex items-center gap-2">
                ${ns.state.appMode === 'demo' ? `
                  <label class="inline-flex items-center gap-1.5 text-xs bg-slate-50 border border-slate-200 px-2.5 py-1.5 rounded-lg text-slate-700 cursor-pointer">
                    <input id="chatSimSelfCorr" type="checkbox" ${ns.state.simulateSelfCorrection ? 'checked' : ''}
                      onchange="window.LegalApp.state.simulateSelfCorrection = this.checked" />
                    <span>Mô phỏng Self-Correction (DEMO)</span>
                  </label>
                ` : ''}
                ${ns.state.lastChatResponse ? `
                  <button onclick="window.LegalApp.navigate('process')" class="btn-soft px-3 py-1.5 rounded-lg text-xs font-semibold">
                    Xem 7 bước
                  </button>
                  <button onclick="window.LegalApp.navigate('result')" class="btn-soft px-3 py-1.5 rounded-lg text-xs font-semibold">
                    Xem báo cáo A–E
                  </button>
                ` : ''}
              </div>
            </div>

            <!-- Messages List -->
            <div id="chatMessagesBox" class="space-y-4 max-h-[520px] overflow-y-auto pr-1">
              ${ns._renderChatMessages(ns.state.chatMessages)}
            </div>

            <!-- Chat Composer -->
            <div class="border-t border-slate-100 pt-3 space-y-2.5">
              <textarea id="chatInput" rows="3"
                placeholder="Nhập câu hỏi pháp luật của bạn (Enter + Ctrl để gửi)..."
                class="w-full rounded-xl border border-slate-300 focus:border-[#2563EB] focus:ring-2 focus:ring-blue-100 p-3 text-sm focus:outline-none"
                onkeydown="if(event.key==='Enter' && (event.ctrlKey || event.metaKey)){window.LegalApp.sendChatMessage();}"></textarea>
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="text-[11px] text-slate-500">
                  Mẹo: Nêu rõ loại văn bản hoặc tình huống cụ thể để RAG truy xuất chính xác Điều/Khoản/Điểm.
                </span>
                <div class="flex items-center gap-2">
                  <button onclick="document.getElementById('chatInput').value=''"
                    class="px-3 py-2 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-100">
                    Xóa nội dung
                  </button>
                  <button id="chatSendBtn" onclick="window.LegalApp.sendChatMessage()"
                    class="btn-navy px-5 py-2 rounded-lg text-xs font-semibold inline-flex items-center gap-2">
                    <i data-lucide="send" class="w-3.5 h-3.5"></i>
                    <span>Gửi câu hỏi</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    `;
    lucide.createIcons();

    if (ns.state.pendingQuestion) {
      const q = ns.state.pendingQuestion;
      ns.state.pendingQuestion = null;
      const input = document.getElementById('chatInput');
      if (input) input.value = q;
      await ns.sendChatMessage();
    }
  };

  ns._renderChatMessages = function (messages) {
    if (!messages || !messages.length) {
      return `
        <div class="py-10 text-center space-y-3">
          <div class="w-12 h-12 rounded-2xl bg-[#EFF6FF] text-[#1D4ED8] mx-auto flex items-center justify-center">
            <i data-lucide="scale" class="w-6 h-6"></i>
          </div>
          <div class="text-sm font-bold text-[#0F2544]">Bắt đầu cuộc hội thoại tra cứu pháp luật</div>
          <p class="text-xs text-slate-500 max-w-md mx-auto">
            Đặt câu hỏi bên dưới hoặc chọn một tình huống gợi ý. Mọi câu trả lời đều kèm tiến trình xử lý 7 bước và kết quả kiểm chứng trích dẫn.
          </p>
        </div>
      `;
    }

    return messages.map((m) => `
      <div class="space-y-3">
        <!-- User Bubble -->
        <div class="flex justify-end">
          <div class="max-w-[85%] rounded-2xl rounded-tr-sm bg-[#0F2544] text-white px-4 py-3 text-sm leading-relaxed shadow-sm">
            ${esc(m.question)}
          </div>
        </div>
        <!-- Assistant Card -->
        <div class="rounded-2xl rounded-tl-sm bg-slate-50 border border-slate-200 p-4 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 pb-2">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-xs font-bold text-[#0F2544]">Legal AI Assistant</span>
              ${statusBadge(m.citation_status)}
              ${m.is_mock ? `<span class="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-warn">DEMO (is_mock=true)</span>` : `<span class="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-blue">LIVE</span>`}
              <span class="text-[11px] text-slate-400">${m.processing_time_ms} ms</span>
            </div>
            <div class="flex items-center gap-1.5">
              <button onclick="window.LegalApp.copyText(${JSON.stringify(m.answer).replace(/"/g, '&quot;')})"
                title="Sao chép câu trả lời" class="px-2 py-1 rounded-md text-[11px] font-medium text-slate-600 hover:bg-white border border-transparent hover:border-slate-200 inline-flex items-center gap-1">
                <i data-lucide="copy" class="w-3 h-3"></i><span>Sao chép</span>
              </button>
              <button onclick="window.LegalApp.saveAnswerItem('${esc(m.request_id)}')"
                title="Lưu câu trả lời" class="px-2 py-1 rounded-md text-[11px] font-medium text-slate-600 hover:bg-white border border-transparent hover:border-slate-200 inline-flex items-center gap-1">
                <i data-lucide="bookmark" class="w-3 h-3"></i><span>Lưu</span>
              </button>
              <button onclick="window.LegalApp.inspectResponse('${esc(m.request_id)}', 'result')"
                class="px-2 py-1 rounded-md text-[11px] font-semibold text-[#2563EB] hover:bg-blue-50">
                Chi tiết A–E →
              </button>
            </div>
          </div>

          <div class="text-sm text-slate-800 whitespace-pre-line leading-relaxed">${esc(m.answer)}</div>

          ${(m.citations && m.citations.length) ? `
            <div class="space-y-1.5 pt-1">
              <div class="text-xs font-bold text-[#0F2544]">Căn cứ pháp lý (${m.citations.length}):</div>
              <div class="grid grid-cols-1 gap-2">
                ${m.citations.map((c, idx) => `
                  <div class="p-2.5 rounded-lg bg-white border border-slate-200 text-xs flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span class="font-semibold text-[#0F2544]">${idx + 1}. ${esc(c.document_title || c.document_name)}</span>
                      ${c.document_number ? `<span class="text-slate-500"> (${esc(c.document_number)})</span>` : ''}
                      ${c.article ? `<span class="ml-1.5 px-1.5 py-0.5 rounded bg-[#EFF6FF] text-[#1D4ED8] font-medium">${esc(c.article)}${c.clause ? ' · ' + esc(c.clause) : ''}</span>` : ''}
                    </div>
                    <div class="flex items-center gap-2">
                      ${statusBadge(c.validation_status)}
                      ${c.document_id ? `<button onclick="window.LegalApp.openSourceDocModal('${esc(c.document_id)}', '${esc(c.chunk_id || '')}')" class="text-[#2563EB] font-semibold hover:underline">Xem văn bản gốc</button>` : ''}
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}

          <!-- Feedback Bar -->
          <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200/80 text-[11px]">
            <span class="text-slate-500">${esc(m.disclaimer)}</span>
            <div class="flex items-center gap-1.5 shrink-0">
              <span class="text-slate-500">Đánh giá:</span>
              <button onclick="window.LegalApp.rateResponse('${esc(m.request_id)}', 5, true)" class="px-2 py-0.5 rounded border border-slate-200 bg-white hover:border-emerald-400 hover:text-emerald-700">Hữu ích</button>
              <button onclick="window.LegalApp.rateResponse('${esc(m.request_id)}', 2, false)" class="px-2 py-0.5 rounded border border-slate-200 bg-white hover:border-amber-400 hover:text-amber-700">Cần cải thiện</button>
            </div>
          </div>
        </div>
      </div>
    `).join('');
  };

  ns.startNewConversation = function () {
    ns.state.activeConversationId = null;
    ns.state.chatMessages = [];
    ns.renderCurrentPage();
  };

  ns.loadConversation = async function (conversationId) {
    try {
      const msgs = await api(`/api/chat/conversations/${encodeURIComponent(conversationId)}`);
      ns.state.activeConversationId = conversationId;
      ns.state.chatMessages = msgs;
      ns.state.lastChatResponse = msgs[msgs.length - 1] || null;
      if (ns.state.currentPage !== 'chat') {
        ns.navigate('chat');
      } else {
        ns.renderCurrentPage();
      }
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.deleteConversation = async function (conversationId) {
    if (!confirm('Xác nhận xóa cuộc hội thoại này khỏi lịch sử?')) return;
    try {
      await api(`/api/chat/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE' });
      if (ns.state.activeConversationId === conversationId) {
        ns.state.activeConversationId = null;
        ns.state.chatMessages = [];
      }
      toast('Đã xóa cuộc hội thoại.', 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.sendChatMessage = async function () {
    const input = document.getElementById('chatInput');
    const btn = document.getElementById('chatSendBtn');
    const q = input?.value?.trim();
    if (!q) {
      toast('Vui lòng nhập câu hỏi pháp luật.', 'warn');
      return;
    }
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span>Đang chạy 7 bước xử lý...</span>`;
    }
    try {
      const res = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          question: q,
          conversation_id: ns.state.activeConversationId,
          simulate_self_correction: Boolean(ns.state.simulateSelfCorrection),
        }),
      });
      ns.state.activeConversationId = res.conversation_id;
      ns.state.chatMessages = [...(ns.state.chatMessages || []), res];
      ns.state.lastChatResponse = res;
      if (input) input.value = '';
      await ns.renderCurrentPage();
      const box = document.getElementById('chatMessagesBox');
      if (box) box.scrollTop = box.scrollHeight;
    } catch (e) {
      toast(e.message || 'Lỗi khi gửi câu hỏi.', 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  ns.copyText = async function (txt) {
    try {
      await navigator.clipboard.writeText(txt);
      toast('Đã sao chép nội dung vào clipboard.', 'success');
    } catch {
      toast('Không thể sao chép tự động trên trình duyệt này.', 'warn');
    }
  };

  ns.rateResponse = async function (requestId, rating, helpful) {
    try {
      await api(`/api/chat/${encodeURIComponent(requestId)}/feedback`, {
        method: 'POST',
        body: JSON.stringify({ rating, helpful }),
      });
      toast('Cảm ơn bạn đã gửi đánh giá chất lượng câu trả lời!', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.saveAnswerItem = async function (requestId) {
    const item = (ns.state.chatMessages || []).find((m) => m.request_id === requestId) || ns.state.lastChatResponse;
    if (!item) return;
    try {
      await api('/api/saved', {
        method: 'POST',
        body: JSON.stringify({
          item_type: 'answer',
          target_id: item.request_id,
          title: item.question,
          subtitle: `${item.verification_label} · ${item.app_mode.toUpperCase()}`,
          content: item.answer,
          metadata: { citation_status: item.citation_status, conversation_id: item.conversation_id },
        }),
      });
      toast('Đã lưu câu trả lời vào mục Văn bản đã lưu.', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.inspectResponse = async function (requestId, targetPage) {
    try {
      const detail = await api(`/api/history/${encodeURIComponent(requestId)}`);
      ns.state.lastChatResponse = detail;
      ns.navigate(targetPage);
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // -------------------------------------------------------------------------
  // Page 3: Theo dõi quá trình xử lý (7 REAL Steps from Backend)
  // -------------------------------------------------------------------------
  ns.renderUserProcess = async function (container) {
    const historyList = await api('/api/history?limit=15').catch(() => []);
    let resp = ns.state.lastChatResponse;
    if (!resp && historyList.length > 0) {
      resp = await api(`/api/history/${encodeURIComponent(historyList[0].id)}`).catch(() => null);
      ns.state.lastChatResponse = resp;
    }

    if (!resp) {
      container.innerHTML = `
        <div class="card p-10 text-center space-y-3">
          <div class="text-base font-bold text-[#0F2544]">Chưa có phiên xử lý nào để theo dõi</div>
          <p class="text-xs text-slate-500">Hãy gửi một câu hỏi trong mục Trợ lý pháp luật để xem trạng thái thật của 7 bước xử lý.</p>
          <button onclick="window.LegalApp.navigate('chat')" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Đi tới Trợ lý pháp luật</button>
        </div>
      `;
      return;
    }

    const steps = (resp.processing_status && resp.processing_status.steps) || [];
    const sc = resp.self_correction || { attempts: 0, performed: false, max_attempts: 2, steps: [] };

    container.innerHTML = `
      <div class="space-y-5">
        <div class="card p-5 flex flex-wrap items-center justify-between gap-3">
          <div class="space-y-1 min-w-0 flex-1">
            <div class="text-xs font-semibold text-slate-500 uppercase">Câu hỏi đang theo dõi</div>
            <div class="text-base font-bold text-[#0F2544]">${esc(resp.question)}</div>
            <div class="flex flex-wrap items-center gap-2 text-xs pt-1">
              ${statusBadge(resp.citation_status)}
              <span class="text-slate-500">Thời gian xử lý: <strong>${resp.processing_time_ms} ms</strong></span>
              <span class="text-slate-500">· Chế độ: <strong>${esc(resp.app_mode.toUpperCase())}</strong></span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            ${historyList.length > 1 ? `
              <select onchange="window.LegalApp.inspectResponse(this.value, 'process')"
                class="px-3 py-2 rounded-lg border border-slate-200 text-xs bg-white max-w-xs">
                ${historyList.map((h) => `<option value="${esc(h.id)}" ${h.id === resp.request_id ? 'selected' : ''}>${esc(h.question.slice(0, 65))}</option>`).join('')}
              </select>
            ` : ''}
            <button onclick="window.LegalApp.navigate('result')" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">
              Xem kết quả A–E →
            </button>
          </div>
        </div>

        <!-- 7-Step Pipeline Tracker -->
        <div class="card p-5 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-[#0F2544]">Tiến trình xử lý 7 bước (Trạng thái thật từ Backend)</h3>
            <span class="text-xs text-slate-500">Agent tự động thực hiện toàn bộ quy trình</span>
          </div>
          <div class="space-y-3">
            ${steps.map((s) => {
              const colorMap = {
                completed: 'border-emerald-200 bg-emerald-50/60',
                warning: 'border-amber-200 bg-amber-50/60',
                error: 'border-red-200 bg-red-50/60',
                pending: 'border-slate-200 bg-slate-50',
              };
              const numColor = {
                completed: 'bg-emerald-600 text-white',
                warning: 'bg-amber-500 text-white',
                error: 'bg-red-600 text-white',
                pending: 'bg-slate-400 text-white',
              };
              return `
                <div class="p-4 rounded-xl border ${colorMap[s.status] || colorMap.pending} flex items-start gap-3.5">
                  <div class="w-8 h-8 rounded-full ${numColor[s.status] || numColor.pending} flex items-center justify-center text-xs font-bold shrink-0">
                    ${s.step_number}
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <div class="text-sm font-bold text-[#0F2544]">Bước ${s.step_number}: ${esc(s.label)}</div>
                      <div class="flex items-center gap-2">
                        ${s.duration_ms != null ? `<span class="text-[11px] text-slate-500">${s.duration_ms} ms</span>` : ''}
                        ${statusBadge(s.status)}
                      </div>
                    </div>
                    <p class="text-xs text-slate-700 mt-1 leading-relaxed">${esc(s.detail)}</p>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>

        <!-- Self-Correction Trace -->
        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">Nhật ký Self-Correction (Tự điều chỉnh trích dẫn)</h3>
          ${sc.performed && sc.steps && sc.steps.length ? `
            <div class="space-y-2.5">
              ${sc.steps.map((st) => `
                <div class="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-xs space-y-1">
                  <div class="font-bold text-amber-900">Lần thử ${st.attempt}/${sc.max_attempts}: ${esc(st.initial_status)} → ${esc(st.resulting_status)}</div>
                  <div class="text-slate-700"><strong>Hành động:</strong> ${esc(st.action)}</div>
                  <div class="text-slate-600">${esc(st.detail)}</div>
                </div>
              `).join('')}
            </div>
          ` : `
            <p class="text-xs text-slate-500">Không phát sinh vòng lặp Self-Correction trong lượt xử lý này (${sc.attempts}/${sc.max_attempts} lượt thử).</p>
          `}
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  // -------------------------------------------------------------------------
  // Page 4: Kết quả tra cứu (Structured A-E Legal Output)
  // -------------------------------------------------------------------------
  ns.renderUserResult = async function (container) {
    const historyList = await api('/api/history?limit=15').catch(() => []);
    let resp = ns.state.lastChatResponse;
    if (!resp && historyList.length > 0) {
      resp = await api(`/api/history/${encodeURIComponent(historyList[0].id)}`).catch(() => null);
      ns.state.lastChatResponse = resp;
    }

    if (!resp) {
      container.innerHTML = `
        <div class="card p-10 text-center space-y-3">
          <div class="text-base font-bold text-[#0F2544]">Chưa có kết quả tra cứu</div>
          <p class="text-xs text-slate-500">Vui lòng đặt câu hỏi trong Trợ lý pháp luật để xem báo cáo kết quả chuẩn cấu trúc A–E.</p>
          <button onclick="window.LegalApp.navigate('chat')" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Đặt câu hỏi ngay</button>
        </div>
      `;
      return;
    }

    const checkIcon = (v) =>
      v === true
        ? '<span class="text-emerald-700 font-semibold">Đạt</span>'
        : v === false
        ? '<span class="text-red-600 font-semibold">Không đạt</span>'
        : '<span class="text-slate-400">Chưa xác minh</span>';

    container.innerHTML = `
      <div class="space-y-5">
        <!-- Header Bar -->
        <div class="card p-5 flex flex-wrap items-center justify-between gap-3">
          <div class="space-y-1 flex-1 min-w-0">
            <div class="text-xs text-slate-500 font-semibold uppercase">Báo cáo kết quả tra cứu pháp luật</div>
            <h2 class="text-lg font-bold text-[#0F2544]">${esc(resp.question)}</h2>
            <div class="flex flex-wrap items-center gap-2 pt-1">
              ${statusBadge(resp.citation_status)}
              <span class="text-xs font-semibold text-slate-700">${esc(resp.verification_label)}</span>
              ${resp.is_mock ? `<span class="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-warn">Dữ liệu DEMO (is_mock=true)</span>` : ''}
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            ${historyList.length > 1 ? `
              <select onchange="window.LegalApp.inspectResponse(this.value, 'result')"
                class="px-3 py-2 rounded-lg border border-slate-200 text-xs bg-white max-w-xs">
                ${historyList.map((h) => `<option value="${esc(h.id)}" ${h.id === resp.request_id ? 'selected' : ''}>${esc(h.question.slice(0, 65))}</option>`).join('')}
              </select>
            ` : ''}
            <button onclick="window.LegalApp.saveAnswerItem('${esc(resp.request_id)}')" class="btn-soft px-3.5 py-2 rounded-lg text-xs font-semibold">Lưu kết quả</button>
            <button onclick="window.LegalApp.navigate('process')" class="btn-navy px-3.5 py-2 rounded-lg text-xs font-semibold">Xem tiến trình 7 bước</button>
          </div>
        </div>

        <!-- A. Kết luận -->
        <section class="card p-5 border-l-4 border-l-[#0F2544] space-y-2">
          <h3 class="text-sm font-bold text-[#0F2544]">A. Kết luận</h3>
          <div class="text-sm text-slate-800 whitespace-pre-line leading-relaxed">${esc(resp.conclusion || resp.answer)}</div>
        </section>

        <!-- B. Phân tích tình huống -->
        <section class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">B. Phân tích tình huống</h3>
          <div class="text-sm text-slate-700 whitespace-pre-line leading-relaxed">${esc(resp.answer)}</div>
          ${(resp.analysis && resp.analysis.length) ? `
            <div class="pt-2 space-y-2">
              <div class="text-xs font-semibold text-slate-500 uppercase">Các vấn đề pháp lý đã phân rã</div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                ${resp.analysis.map((a, i) => `
                  <div class="p-3 rounded-lg bg-[#F8FAFC] border border-slate-200 text-xs space-y-1">
                    <div class="font-bold text-[#0F2544]">Vấn đề ${i + 1}${a.legal_domain ? ` · ${esc(a.legal_domain)}` : ''}</div>
                    <div class="text-slate-700">${esc(a.issue)}</div>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
        </section>

        <!-- C. Căn cứ pháp lý -->
        <section class="card p-5 space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-[#0F2544]">C. Căn cứ pháp lý (${(resp.citations || []).length})</h3>
            <span class="text-xs text-slate-500">Bấm "Xem văn bản gốc" để đối chiếu nguyên văn trong CSDL</span>
          </div>
          ${(resp.citations && resp.citations.length) ? `
            <div class="space-y-3">
              ${resp.citations.map((c, idx) => `
                <div class="p-4 rounded-xl border border-slate-200 bg-[#F8FAFC] space-y-2.5">
                  <div class="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div class="text-sm font-bold text-[#0F2544]">${idx + 1}. ${esc(c.document_title || c.document_name)}</div>
                      <div class="flex flex-wrap gap-2 text-xs text-slate-600 mt-1">
                        <span><strong>Số hiệu:</strong> ${esc(c.document_number || 'Chưa xác định')}</span>
                        <span>•</span>
                        <span><strong>Điều:</strong> ${esc(c.article || 'Chưa tách')}</span>
                        ${c.clause ? `<span>• <strong>Khoản:</strong> ${esc(c.clause)}</span>` : ''}
                        ${c.point ? `<span>• <strong>Điểm:</strong> ${esc(c.point)}</span>` : ''}
                      </div>
                    </div>
                    <div class="flex items-center gap-2">
                      ${statusBadge(c.validation_status)}
                      ${c.document_id ? `
                        <button onclick="window.LegalApp.openSourceDocModal('${esc(c.document_id)}', '${esc(c.chunk_id || '')}')"
                          class="btn-soft px-3 py-1 rounded-lg text-xs font-semibold">
                          Xem văn bản gốc
                        </button>
                      ` : ''}
                    </div>
                  </div>
                  <div class="p-3 rounded-lg bg-white border border-slate-200 text-xs text-slate-700 whitespace-pre-line leading-relaxed">
                    ${esc(c.quoted_text || c.evidence)}
                  </div>
                  <div class="flex flex-wrap gap-4 text-[11px] text-slate-500">
                    <span><strong>Nguồn:</strong> ${esc(c.source || 'Chưa ghi nhận')}</span>
                    <span><strong>Hiệu lực:</strong> ${esc(c.validity_status || 'Chưa xác minh được hiệu lực')}</span>
                    ${c.effective_date ? `<span><strong>Ngày hiệu lực:</strong> ${esc(c.effective_date)}</span>` : ''}
                  </div>
                </div>
              `).join('')}
            </div>
          ` : `
            <div class="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900">
              Không tìm thấy trích dẫn văn bản pháp luật phù hợp trong kho dữ liệu Qdrant.
            </div>
          `}
        </section>

        <!-- D. Kết quả kiểm chứng -->
        <section class="card p-5 space-y-3">
          <h3 class="text-sm font-bold text-[#0F2544]">D. Kết quả kiểm chứng trích dẫn</h3>
          <div class="flex flex-wrap items-center gap-3 p-3.5 rounded-xl bg-slate-50 border border-slate-200">
            ${statusBadge(resp.citation_status)}
            <span class="text-sm font-bold text-[#0F2544]">${esc(resp.verification_label)}</span>
          </div>
          ${(resp.validation_details && resp.validation_details.length) ? `
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="bg-slate-50 text-slate-500 uppercase border-b border-slate-200">
                  <tr>
                    <th class="px-3 py-2.5">Nguồn trích dẫn</th>
                    <th class="px-3 py-2.5">Văn bản tồn tại</th>
                    <th class="px-3 py-2.5">Số hiệu đúng</th>
                    <th class="px-3 py-2.5">Điều/Khoản tồn tại</th>
                    <th class="px-3 py-2.5">Khớp nội dung</th>
                    <th class="px-3 py-2.5">Hỗ trợ kết luận</th>
                    <th class="px-3 py-2.5">Hiệu lực</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  ${resp.validation_details.map((vd) => `
                    <tr>
                      <td class="px-3 py-2.5 font-medium text-[#0F2544]">
                        ${esc(vd.document_title)}
                        <div class="text-[11px] text-slate-500">${esc(vd.location)}</div>
                      </td>
                      <td class="px-3 py-2.5">${checkIcon(vd.checks.document_exists)}</td>
                      <td class="px-3 py-2.5">${checkIcon(vd.checks.number_valid)}</td>
                      <td class="px-3 py-2.5">${checkIcon(vd.checks.structure_exists)}</td>
                      <td class="px-3 py-2.5">${checkIcon(vd.checks.quote_matches)}</td>
                      <td class="px-3 py-2.5">${checkIcon(vd.checks.supports_claim)}</td>
                      <td class="px-3 py-2.5">${checkIcon(vd.checks.validity_verified)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : ''}
        </section>

        <!-- E. Giới hạn câu trả lời -->
        <section class="rounded-xl bg-amber-50 border border-amber-200 p-5 space-y-2">
          <h3 class="text-sm font-bold text-amber-900">E. Giới hạn câu trả lời</h3>
          <ul class="list-disc pl-5 space-y-1 text-xs text-amber-900/90">
            ${(resp.limitations && resp.limitations.length ? resp.limitations : [resp.disclaimer]).map((lim) => `<li>${esc(lim)}</li>`).join('')}
          </ul>
        </section>
      </div>
    `;
    lucide.createIcons();
  };

  // Modal xem nguyên văn văn bản gốc khi bấm vào căn cứ pháp lý
  ns.openSourceDocModal = async function (documentId, highlightChunkId) {
    const modal = document.getElementById('docModal');
    const body = document.getElementById('docModalBody');
    const titleEl = document.getElementById('docModalTitle');
    if (!modal || !body) return;
    modal.classList.remove('hidden');
    body.innerHTML = `<div class="p-6 text-center text-sm text-slate-500">Đang tải nội dung văn bản gốc...</div>`;
    try {
      const detail = await api(`/api/legal-documents/${encodeURIComponent(documentId)}`);
      if (titleEl) titleEl.textContent = `${detail.title} ${detail.document_number ? '(' + detail.document_number + ')' : ''}`;
      body.innerHTML = `
        <div class="space-y-4">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs bg-slate-50 p-3 rounded-lg border border-slate-200">
            <div><span class="text-slate-500">Số hiệu:</span> <strong>${esc(detail.document_number || 'Chưa xác định')}</strong></div>
            <div><span class="text-slate-500">Loại:</span> <strong>${esc(detail.document_type || 'Chưa xác định')}</strong></div>
            <div><span class="text-slate-500">Cơ quan:</span> <strong>${esc(detail.issuing_authority || 'Chưa xác định')}</strong></div>
            <div><span class="text-slate-500">Hiệu lực:</span> <strong>${esc(detail.status || detail.effective_date || 'Chưa xác định')}</strong></div>
          </div>
          <div class="space-y-2.5 max-h-[55vh] overflow-y-auto pr-1">
            ${(detail.chunks || []).map((ch) => `
              <div class="p-3 rounded-lg border text-xs space-y-1 ${ch.chunk_id === highlightChunkId ? 'bg-[#EFF6FF] border-[#2563EB] ring-1 ring-blue-200' : 'bg-white border-slate-200'}">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="flex flex-wrap gap-1.5">
                    ${ch.chapter ? `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700">${esc(ch.chapter)}</span>` : ''}
                    ${ch.article ? `<span class="px-2 py-0.5 rounded bg-[#EFF6FF] text-[#1D4ED8] font-semibold">${esc(ch.article)}</span>` : ''}
                    ${ch.clause ? `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700">${esc(ch.clause)}</span>` : ''}
                    ${ch.point ? `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700">${esc(ch.point)}</span>` : ''}
                  </div>
                  <button onclick="window.LegalApp.saveClauseItem('${esc(detail.document_id)}','${esc(ch.chunk_id)}',${JSON.stringify(detail.title).replace(/"/g, '&quot;')},${JSON.stringify((ch.article || '') + ' ' + (ch.clause || '')).replace(/"/g, '&quot;')},${JSON.stringify(ch.content).replace(/"/g, '&quot;')})"
                    class="text-[#2563EB] hover:underline font-semibold">Lưu điều khoản</button>
                </div>
                <div class="whitespace-pre-line text-slate-800 leading-relaxed">${esc(ch.content)}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    } catch (e) {
      body.innerHTML = `<div class="p-4 text-sm text-red-700 bg-red-50 rounded-lg">${esc(e.message)}</div>`;
    }
  };

  ns.closeSourceDocModal = function () {
    document.getElementById('docModal')?.classList.add('hidden');
  };

  // -------------------------------------------------------------------------
  // Page 5: Tra cứu văn bản pháp luật (User Document Browser)
  // -------------------------------------------------------------------------
  ns.renderUserDocuments = async function (container) {
    const f = ns.state.userDocFilters || { search: '', document_type: '', status: '' };
    const params = new URLSearchParams();
    if (f.search) params.set('search', f.search);
    if (f.document_type) params.set('document_type', f.document_type);
    if (f.status) params.set('status', f.status);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const data = await api(`/api/legal-documents${qs}`).catch(() => ({ loaded: false, items: [], document_types: [], statuses: [], note: '' }));

    container.innerHTML = `
      <div class="space-y-5">
        <div class="card p-5 space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-base font-bold text-[#0F2544]">Tra cứu văn bản pháp luật</h2>
              <p class="text-xs text-slate-500">${esc(data.note)}</p>
            </div>
            <span class="text-xs font-semibold px-3 py-1 rounded-full bg-[#EFF6FF] text-[#1D4ED8]">
              ${data.total_documents || 0} văn bản · ${data.total_chunks || 0} điều khoản/chunk
            </span>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
            <input id="userDocSearch" type="text" value="${esc(f.search)}"
              placeholder="Tìm theo tên văn bản, số hiệu, từ khóa..."
              class="md:col-span-2 px-3.5 py-2 rounded-lg border border-slate-300 text-sm"
              onkeydown="if(event.key==='Enter'){window.LegalApp.applyUserDocFilters();}" />
            <select id="userDocType" class="px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white">
              <option value="">Tất cả loại văn bản</option>
              ${(data.document_types || []).map((t) => `<option value="${esc(t)}" ${f.document_type === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}
            </select>
            <div class="flex gap-2">
              <select id="userDocStatus" class="flex-1 px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white">
                <option value="">Tất cả tình trạng hiệu lực</option>
                ${(data.statuses || []).map((st) => `<option value="${esc(st)}" ${f.status === st ? 'selected' : ''}>${esc(st)}</option>`).join('')}
              </select>
              <button onclick="window.LegalApp.applyUserDocFilters()" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold shrink-0">Lọc</button>
            </div>
          </div>
        </div>

        ${!data.loaded ? `
          <div class="card p-10 text-center space-y-2">
            <div class="text-sm font-bold text-[#0F2544]">Chưa có dữ liệu văn bản pháp luật</div>
            <p class="text-xs text-slate-500 max-w-lg mx-auto">${esc(data.note)}</p>
          </div>
        ` : `
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            ${(data.items || []).map((doc) => `
              <div class="card p-4 space-y-3 hover:border-[#2563EB] transition">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <h3 class="text-sm font-bold text-[#0F2544]">${esc(doc.title)}</h3>
                    <div class="text-xs text-slate-500 mt-0.5">
                      Số hiệu: <strong>${esc(doc.document_number || 'Chưa xác định')}</strong> · ${esc(doc.document_type || 'Chưa xác định')}
                    </div>
                  </div>
                  ${statusBadge(doc.qdrant_sync_status)}
                </div>
                <div class="flex flex-wrap gap-3 text-xs text-slate-600">
                  <span>Cơ quan: <strong>${esc(doc.issuing_authority || 'Chưa xác định')}</strong></span>
                  <span>Hiệu lực: <strong>${esc(doc.status || doc.effective_date || 'Chưa xác định')}</strong></span>
                  <span><strong>${doc.chunk_count}</strong> chunks</span>
                </div>
                <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button onclick="window.LegalApp.saveDocumentItem('${esc(doc.document_id)}',${JSON.stringify(doc.title).replace(/"/g, '&quot;')},${JSON.stringify(doc.document_number || '').replace(/"/g, '&quot;')})"
                    class="btn-soft px-3 py-1.5 rounded-lg text-xs font-semibold">Lưu văn bản</button>
                  <button onclick="window.LegalApp.openSourceDocModal('${esc(doc.document_id)}','')"
                    class="btn-navy px-3 py-1.5 rounded-lg text-xs font-semibold">Xem nội dung & Điều khoản</button>
                </div>
              </div>
            `).join('')}
          </div>
        `}
      </div>
    `;
    lucide.createIcons();
  };

  ns.applyUserDocFilters = function () {
    ns.state.userDocFilters = {
      search: document.getElementById('userDocSearch')?.value?.trim() || '',
      document_type: document.getElementById('userDocType')?.value || '',
      status: document.getElementById('userDocStatus')?.value || '',
    };
    ns.renderCurrentPage();
  };

  ns.saveDocumentItem = async function (docId, title, docNumber) {
    try {
      await api('/api/saved', {
        method: 'POST',
        body: JSON.stringify({
          item_type: 'document',
          target_id: docId,
          title,
          subtitle: docNumber || 'Văn bản pháp luật',
          content: `Mã văn bản: ${docId}`,
          metadata: { document_id: docId, document_number: docNumber },
        }),
      });
      toast('Đã lưu văn bản vào danh sách yêu thích.', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  ns.saveClauseItem = async function (docId, chunkId, docTitle, location, content) {
    try {
      await api('/api/saved', {
        method: 'POST',
        body: JSON.stringify({
          item_type: 'clause',
          target_id: chunkId,
          title: `${docTitle} — ${location.trim() || chunkId}`,
          subtitle: `Chunk: ${chunkId}`,
          content,
          metadata: { document_id: docId, chunk_id: chunkId },
        }),
      });
      toast('Đã lưu điều khoản vào Văn bản đã lưu.', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // -------------------------------------------------------------------------
  // Page 6: Lịch sử tra cứu (History & Resume Conversation)
  // -------------------------------------------------------------------------
  ns.renderUserHistory = async function (container) {
    const search = ns.state.historySearch || '';
    const items = await api(`/api/history${search ? '?search=' + encodeURIComponent(search) : ''}`).catch(() => []);

    container.innerHTML = `
      <div class="space-y-4">
        <div class="card p-4 flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-2 flex-1 min-w-[220px]">
            <input id="historySearchInput" type="text" value="${esc(search)}" placeholder="Tìm câu hỏi hoặc nội dung đã tra cứu..."
              class="flex-1 px-3.5 py-2 rounded-lg border border-slate-300 text-sm"
              onkeydown="if(event.key==='Enter'){window.LegalApp.state.historySearch=this.value;window.LegalApp.renderCurrentPage();}" />
            <button onclick="window.LegalApp.state.historySearch=document.getElementById('historySearchInput').value;window.LegalApp.renderCurrentPage();"
              class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Tìm</button>
          </div>
          <span class="text-xs text-slate-500">Tổng: <strong>${items.length}</strong> lượt tra cứu</span>
        </div>

        ${!items.length ? `
          <div class="card p-10 text-center text-sm text-slate-500">Chưa có lịch sử tra cứu.</div>
        ` : `
          <div class="space-y-3">
            ${items.map((h) => `
              <div class="card p-4 space-y-2">
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0 flex-1">
                    <div class="text-sm font-bold text-[#0F2544]">${esc(h.question)}</div>
                    <div class="text-xs text-slate-500 mt-1">${fmtDate(h.created_at)} · ${h.citations_count} trích dẫn · ${h.processing_time_ms} ms</div>
                  </div>
                  <div class="flex items-center gap-2">
                    ${statusBadge(h.citation_status)}
                    ${h.is_mock ? `<span class="px-2 py-0.5 rounded-full text-[11px] badge-warn">DEMO</span>` : ''}
                  </div>
                </div>
                <p class="text-xs text-slate-600 leading-relaxed">${esc(h.answer_preview)}</p>
                <div class="flex flex-wrap justify-end gap-2 pt-2 border-t border-slate-100">
                  <button onclick="window.LegalApp.loadConversation('${esc(h.conversation_id || h.id)}')" class="btn-navy px-3 py-1.5 rounded-lg text-xs font-semibold">Tiếp tục hội thoại</button>
                  <button onclick="window.LegalApp.inspectResponse('${esc(h.id)}', 'result')" class="btn-soft px-3 py-1.5 rounded-lg text-xs font-semibold">Xem kết quả A–E</button>
                  <button onclick="window.LegalApp.inspectResponse('${esc(h.id)}', 'process')" class="btn-soft px-3 py-1.5 rounded-lg text-xs font-semibold">Xem 7 bước</button>
                  <button onclick="window.LegalApp.deleteHistoryItem('${esc(h.id)}')" class="px-3 py-1.5 rounded-lg text-xs font-semibold text-red-600 hover:bg-red-50">Xóa</button>
                </div>
              </div>
            `).join('')}
          </div>
        `}
      </div>
    `;
    lucide.createIcons();
  };

  ns.deleteHistoryItem = async function (id) {
    if (!confirm('Xác nhận xóa lượt tra cứu này?')) return;
    try {
      await api(`/api/history/${encodeURIComponent(id)}`, { method: 'DELETE' });
      toast('Đã xóa bản ghi lịch sử.', 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // -------------------------------------------------------------------------
  // Page 7: Văn bản đã lưu (Saved Documents / Clauses / Answers)
  // -------------------------------------------------------------------------
  ns.renderUserSaved = async function (container) {
    const tab = ns.state.savedTab || '';
    const items = await api(`/api/saved${tab ? '?item_type=' + tab : ''}`).catch(() => []);
    const typeLabels = { document: 'Văn bản yêu thích', clause: 'Điều khoản đã lưu', answer: 'Câu trả lời đã lưu' };

    container.innerHTML = `
      <div class="space-y-4">
        <div class="card p-4 flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap gap-2">
            ${[['', 'Tất cả'], ['document', 'Văn bản yêu thích'], ['clause', 'Điều khoản đã lưu'], ['answer', 'Câu trả lời đã lưu']].map(([val, lbl]) => `
              <button onclick="window.LegalApp.state.savedTab='${val}';window.LegalApp.renderCurrentPage();"
                class="px-3.5 py-1.5 rounded-lg text-xs font-semibold ${tab === val ? 'btn-navy' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}">
                ${lbl}
              </button>
            `).join('')}
          </div>
          <span class="text-xs text-slate-500">${items.length} mục đã lưu</span>
        </div>

        ${!items.length ? `
          <div class="card p-10 text-center text-sm text-slate-500">
            Chưa có mục nào được lưu. Bạn có thể bấm nút <strong>Lưu</strong> ở Trợ lý pháp luật hoặc Tra cứu văn bản.
          </div>
        ` : `
          <div class="space-y-3">
            ${items.map((it) => `
              <div class="card p-4 space-y-2">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-[#EFF6FF] text-[#1D4ED8]">${typeLabels[it.item_type] || it.item_type}</span>
                    <h3 class="text-sm font-bold text-[#0F2544] mt-1">${esc(it.title)}</h3>
                    ${it.subtitle ? `<div class="text-xs text-slate-500">${esc(it.subtitle)} · ${fmtDate(it.created_at)}</div>` : ''}
                  </div>
                  <button onclick="window.LegalApp.deleteSavedItem('${esc(it.id)}')" class="text-xs font-semibold text-red-600 hover:underline">Bỏ lưu</button>
                </div>
                ${it.content ? `<div class="text-xs text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-200 whitespace-pre-line max-h-40 overflow-y-auto">${esc(it.content)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        `}
      </div>
    `;
    lucide.createIcons();
  };

  ns.deleteSavedItem = async function (id) {
    try {
      await api(`/api/saved/${encodeURIComponent(id)}`, { method: 'DELETE' });
      toast('Đã xóa khỏi danh sách đã lưu.', 'success');
      ns.renderCurrentPage();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // -------------------------------------------------------------------------
  // Page 8: Tài khoản (Auth / Profile / Change Password / Logout)
  // -------------------------------------------------------------------------
  ns.renderUserAccount = async function (container) {
    const user = ns.state.currentUser;
    if (!user) {
      container.innerHTML = ns.renderAuthForms(false);
      lucide.createIcons();
      return;
    }

    container.innerHTML = `
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div class="card p-6 space-y-4">
          <div class="flex items-center gap-3.5">
            <div class="w-12 h-12 rounded-2xl bg-[#0F2544] text-white flex items-center justify-center font-bold text-lg">
              ${esc((user.full_name || user.username || 'U')[0].toUpperCase())}
            </div>
            <div>
              <h2 class="text-base font-bold text-[#0F2544]">${esc(user.full_name)}</h2>
              <div class="text-xs text-slate-500">${esc(user.email)} · @${esc(user.username)}</div>
              <span class="inline-block mt-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${user.role === 'admin' ? 'bg-[#0F2544] text-white' : 'badge-blue'}">
                Vai trò: ${user.role === 'admin' ? 'Quản trị viên (Admin)' : 'Người dùng (User)'}
              </span>
            </div>
          </div>

          <div class="space-y-3 pt-2 border-t border-slate-100">
            <label class="block text-xs font-semibold text-slate-600">Họ và tên</label>
            <div class="flex gap-2">
              <input id="profileFullName" type="text" value="${esc(user.full_name)}" class="flex-1 px-3 py-2 rounded-lg border border-slate-300 text-sm" />
              <button onclick="window.LegalApp.updateProfile()" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold">Cập nhật</button>
            </div>
          </div>

          <div class="flex flex-wrap gap-2 pt-3 border-t border-slate-100">
            ${user.role === 'admin' ? `
              <button onclick="window.LegalApp.switchPortal('admin')" class="btn-navy px-4 py-2 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5">
                <i data-lucide="shield" class="w-3.5 h-3.5"></i>
                <span>Mở Admin Portal</span>
              </button>
            ` : ''}
            <button onclick="window.LegalApp.logout()" class="px-4 py-2 rounded-lg text-xs font-semibold border border-red-200 bg-red-50 text-red-700 hover:bg-red-100">
              Đăng xuất
            </button>
          </div>
        </div>

        <div class="card p-6 space-y-4">
          <h3 class="text-base font-bold text-[#0F2544]">Đổi mật khẩu</h3>
          <div class="space-y-3">
            <div>
              <label class="block text-xs font-semibold text-slate-600 mb-1">Mật khẩu hiện tại</label>
              <input id="curPwd" type="password" class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600 mb-1">Mật khẩu mới (tối thiểu 6 ký tự)</label>
              <input id="newPwd" type="password" class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
            </div>
            <button onclick="window.LegalApp.changePassword()" class="btn-navy px-5 py-2 rounded-lg text-xs font-semibold">
              Lưu mật khẩu mới
            </button>
          </div>
        </div>
      </div>
    `;
    lucide.createIcons();
  };

  ns.renderAuthForms = function (adminRequired) {
    return `
      <div class="max-w-3xl mx-auto space-y-5">
        ${adminRequired ? `
          <div class="rounded-xl bg-amber-50 border border-amber-300 p-4 text-xs text-amber-900 flex items-center gap-2.5">
            <i data-lucide="lock" class="w-4 h-4 text-amber-700 shrink-0"></i>
            <span><strong>Admin Portal yêu cầu quyền Quản trị viên.</strong> Vui lòng đăng nhập bằng tài khoản có vai trò <code>admin</code>.</span>
          </div>
        ` : ''}
        <div class="grid grid-cols-1 ${adminRequired ? '' : 'md:grid-cols-2'} gap-5">
          <div class="card p-6 space-y-4">
            <h2 class="text-base font-bold text-[#0F2544]">Đăng nhập hệ thống</h2>
            <div class="space-y-3">
              <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Email hoặc tên đăng nhập</label>
                <input id="loginIdent" type="text" placeholder="${adminRequired ? 'admin@legalai.vn' : 'user@legalai.vn hoặc admin@legalai.vn'}"
                  class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Mật khẩu</label>
                <input id="loginPwd" type="password" placeholder="••••••••"
                  class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm"
                  onkeydown="if(event.key==='Enter'){window.LegalApp.submitLogin(${adminRequired});}" />
              </div>
              <button onclick="window.LegalApp.submitLogin(${adminRequired})" class="w-full btn-navy py-2.5 rounded-lg text-xs font-semibold">
                Đăng nhập
              </button>
              <div class="p-3 rounded-lg bg-[#EFF6FF] border border-blue-200 text-[11px] text-slate-700 space-y-1">
                <div class="font-semibold text-[#0F2544]">Tài khoản kiểm thử mặc định:</div>
                <div>• Quản trị viên: <code>admin@legalai.vn</code> / <code>Admin@123</code></div>
                <div>• Người dùng: <code>user@legalai.vn</code> / <code>User@123</code></div>
              </div>
            </div>
          </div>

          ${!adminRequired ? `
            <div class="card p-6 space-y-4">
              <h2 class="text-base font-bold text-[#0F2544]">Đăng ký tài khoản mới</h2>
              <div class="space-y-3">
                <div>
                  <label class="block text-xs font-semibold text-slate-600 mb-1">Họ và tên</label>
                  <input id="regName" type="text" placeholder="Nguyễn Văn A" class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                </div>
                <div>
                  <label class="block text-xs font-semibold text-slate-600 mb-1">Tên đăng nhập</label>
                  <input id="regUser" type="text" placeholder="nguyenvana" class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                </div>
                <div>
                  <label class="block text-xs font-semibold text-slate-600 mb-1">Email</label>
                  <input id="regEmail" type="email" placeholder="nguyenvana@email.com" class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                </div>
                <div>
                  <label class="block text-xs font-semibold text-slate-600 mb-1">Mật khẩu (tối thiểu 6 ký tự)</label>
                  <input id="regPwd" type="password" class="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                </div>
                <button onclick="window.LegalApp.submitRegister()" class="w-full btn-soft py-2.5 rounded-lg text-xs font-semibold">
                  Tạo tài khoản người dùng
                </button>
              </div>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  };
})(window.LegalApp);
