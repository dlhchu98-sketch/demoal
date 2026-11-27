'use client';

import { useCallback, useEffect, useState } from 'react';
import { legalApi } from '../../services/api';
import type {
  LegalDocumentChunksResponse,
  LegalDocumentListResponse,
  LegalDocumentSummary,
} from '../../types/legal';

export default function DocumentsPage() {
  const [data, setData] = useState<LegalDocumentListResponse | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [docType, setDocType] = useState('');
  const [authority, setAuthority] = useState('');
  const [allowUpdate, setAllowUpdate] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<LegalDocumentSummary | null>(null);
  const [chunksData, setChunksData] = useState<LegalDocumentChunksResponse | null>(null);

  const loadData = useCallback(async () => {
    const params = new URLSearchParams();
    if (search.trim()) params.set('search', search.trim());
    if (docType) params.set('document_type', docType);
    if (authority) params.set('issuing_authority', authority);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const [listRes, statsRes] = await Promise.all([
      legalApi.getLegalDocuments(qs),
      legalApi.getLegalDocumentsStats(),
    ]);
    setData(listRes);
    setStats(statsRes);
    if (listRes.items.length > 0) {
      const target = listRes.items.find((d) => d.document_id === selectedDoc?.document_id) || listRes.items[0];
      setSelectedDoc(target);
      const chunksRes = await legalApi.getLegalDocumentChunks(target.document_id);
      setChunksData(chunksRes);
    } else {
      setSelectedDoc(null);
      setChunksData(null);
    }
  }, [search, docType, authority, selectedDoc?.document_id]);

  useEffect(() => {
    loadData().catch((err) => setNotice({ type: 'error', text: err.message }));
  }, [loadData]);

  async function handleScanSync() {
    setScanning(true);
    setNotice(null);
    try {
      const res = await legalApi.scanLegalDocuments(true, allowUpdate);
      setNotice({
        type: res.error_count > 0 ? 'error' : 'success',
        text: res.message,
      });
      await loadData();
    } catch (err: any) {
      setNotice({ type: 'error', text: err.message || 'Lỗi đồng bộ dữ liệu' });
    } finally {
      setScanning(false);
    }
  }

  async function handleFolderUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const list = Array.from(e.target.files || []);
    if (!list.length) return;
    setScanning(true);
    setNotice({ type: 'info', text: `Đang tải lên ${list.length} tệp, tự động lọc & chuyển đổi .doc/.docx/.pdf sang chuẩn RAG...` });
    try {
      const res = await legalApi.uploadLegalFolder(list, allowUpdate);
      setNotice({
        type: res.error_count > 0 ? 'error' : 'success',
        text: res.message,
      });
      await loadData();
    } catch (err: any) {
      setNotice({ type: 'error', text: err.message || 'Lỗi tải lên thư mục văn bản' });
    } finally {
      setScanning(false);
      e.target.value = '';
    }
  }

  async function handleSelectDoc(doc: LegalDocumentSummary) {
    setSelectedDoc(doc);
    try {
      const chunksRes = await legalApi.getLegalDocumentChunks(doc.document_id);
      setChunksData(chunksRes);
    } catch (err: any) {
      setNotice({ type: 'error', text: err.message });
    }
  }

  async function handleDelete(doc: LegalDocumentSummary) {
    if (!confirm(`Xác nhận xóa văn bản "${doc.title}" và vector Qdrant liên quan?`)) return;
    try {
      const res = await legalApi.deleteLegalDocument(doc.document_id);
      setNotice({
        type: 'success',
        text: `Đã xóa "${res.title}" (${res.deleted_chunks} chunks, ${res.deleted_vectors} vectors Qdrant).`,
      });
      await loadData();
    } catch (err: any) {
      setNotice({ type: 'error', text: err.message });
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold text-[#243247]">Kho văn bản pháp luật</h1>
            <p className="text-xs text-[#6B7788] mt-0.5">
              {stats?.qdrant_detail || 'Đang kiểm tra kết nối Qdrant...'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <label className="inline-flex items-center gap-1.5 text-xs text-[#243247] bg-[#F5F8FC] border border-slate-200 px-3 py-2 rounded-lg">
              <input
                type="checkbox"
                checked={allowUpdate}
                onChange={(e) => setAllowUpdate(e.target.checked)}
              />
              <span>Cho phép cập nhật file sửa đổi</span>
            </label>
            <label className="px-4 py-2 rounded-lg bg-[#0F2544] hover:bg-[#1E3A5F] text-white text-xs font-semibold cursor-pointer">
              <span>Upload cả thư mục gốc (.doc, .docx, .pdf)</span>
              <input
                type="file"
                multiple
                // @ts-expect-error webkitdirectory supported by Chromium/Edge/Firefox/Safari
                webkitdirectory=""
                directory=""
                className="hidden"
                onChange={handleFolderUpload}
              />
            </label>
            <button
              onClick={handleScanSync}
              disabled={scanning}
              className="px-4 py-2 rounded-lg bg-[#EFF6FF] hover:bg-[#DBEAFE] text-[#1D4ED8] border border-blue-200 text-xs font-semibold disabled:opacity-50"
            >
              {scanning ? 'Đang xử lý...' : 'Quét thư mục & Đồng bộ dữ liệu'}
            </button>
          </div>
        </div>

        {notice && (
          <div
            className={`p-3 rounded-lg text-xs border ${
              notice.type === 'error'
                ? 'bg-red-50 border-red-200 text-red-800'
                : notice.type === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-[#EAF3FC] border-[#CBE0F5] text-[#243247]'
            }`}
          >
            {notice.text}
          </div>
        )}
      </div>

      {!data?.loaded ? (
        <div className="bg-white border border-slate-200 rounded-xl p-10 text-center space-y-2">
          <h2 className="text-sm font-bold text-[#243247]">Chưa có dữ liệu văn bản pháp luật</h2>
          <p className="text-xs text-[#6B7788]">
            Chưa có dữ liệu văn bản pháp luật. Vui lòng thêm văn bản vào thư mục data/legal_documents/ và thực hiện đồng bộ.
          </p>
        </div>
      ) : (
        <>
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col md:flex-row gap-3">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm kiếm tên văn bản, số hiệu, cơ quan ban hành..."
              className="flex-1 px-3 py-2 rounded-lg border border-slate-300 text-sm"
            />
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white"
            >
              <option value="">Tất cả loại văn bản</option>
              {data.document_types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              value={authority}
              onChange={(e) => setAuthority(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white"
            >
              <option value="">Tất cả cơ quan ban hành</option>
              {data.issuing_authorities.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F5F8FC] text-[#6B7788] uppercase border-b border-slate-200">
                <tr>
                  <th className="px-3 py-3">STT</th>
                  <th className="px-3 py-3">Tên văn bản</th>
                  <th className="px-3 py-3">Số hiệu</th>
                  <th className="px-3 py-3">Loại văn bản</th>
                  <th className="px-3 py-3">Cơ quan ban hành</th>
                  <th className="px-3 py-3">Ngày ban hành</th>
                  <th className="px-3 py-3">Ngày hiệu lực</th>
                  <th className="px-3 py-3">Trạng thái</th>
                  <th className="px-3 py-3 text-right">Số lượng chunk</th>
                  <th className="px-3 py-3">Trạng thái đồng bộ Qdrant</th>
                  <th className="px-3 py-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((doc, idx) => (
                  <tr
                    key={doc.document_id}
                    onClick={() => handleSelectDoc(doc)}
                    className={`cursor-pointer ${
                      selectedDoc?.document_id === doc.document_id ? 'bg-[#FDF2F3]/50' : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="px-3 py-3">{idx + 1}</td>
                    <td className="px-3 py-3 font-semibold text-[#243247]">{doc.title}</td>
                    <td className="px-3 py-3">{doc.document_number || 'Chưa xác định'}</td>
                    <td className="px-3 py-3">{doc.document_type || 'Chưa xác định'}</td>
                    <td className="px-3 py-3">{doc.issuing_authority || 'Chưa xác định'}</td>
                    <td className="px-3 py-3">{doc.issue_date || 'Chưa xác định'}</td>
                    <td className="px-3 py-3">{doc.effective_date || 'Chưa xác định'}</td>
                    <td className="px-3 py-3">{doc.status || 'Chưa xác định'}</td>
                    <td className="px-3 py-3 text-right font-semibold">{doc.chunk_count}</td>
                    <td className="px-3 py-3">
                      {doc.qdrant_sync_status === 'synced'
                        ? `Đã đồng bộ (${doc.qdrant_synced_chunks}/${doc.chunk_count})`
                        : doc.qdrant_sync_status === 'failed'
                        ? 'Lỗi đồng bộ'
                        : 'Chờ đồng bộ'}
                    </td>
                    <td className="px-3 py-3 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(doc);
                        }}
                        className="text-red-700 hover:underline font-semibold"
                      >
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedDoc && chunksData && (
            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
              <div>
                <h2 className="text-base font-bold text-[#243247]">{selectedDoc.title}</h2>
                <p className="text-xs text-[#6B7788] mt-1">
                  Mã: {selectedDoc.document_id} · Số hiệu: {selectedDoc.document_number || 'Chưa xác định'} · Checksum:{' '}
                  <code>{selectedDoc.checksum.slice(0, 16)}...</code>
                </p>
              </div>
              <div className="space-y-2 max-h-[480px] overflow-y-auto">
                {chunksData.items.map((ch) => (
                  <div key={ch.chunk_id} className="p-3 rounded-lg bg-[#F5F8FC] border border-slate-200 space-y-1">
                    <div className="flex flex-wrap gap-1.5 text-[11px]">
                      <span className="font-semibold text-[#3976A9]">{ch.chunk_id}</span>
                      {ch.chapter && <span className="px-2 py-0.5 bg-white rounded border">{ch.chapter}</span>}
                      {ch.article && (
                        <span className="px-2 py-0.5 bg-[#EAF3FC] text-[#3976A9] rounded font-semibold">
                          {ch.article}
                        </span>
                      )}
                      {ch.clause && <span className="px-2 py-0.5 bg-white rounded border">{ch.clause}</span>}
                      {ch.point && <span className="px-2 py-0.5 bg-white rounded border">{ch.point}</span>}
                    </div>
                    <p className="text-xs text-[#243247] whitespace-pre-line">{ch.content}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
