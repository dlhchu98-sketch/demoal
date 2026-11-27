'use client';

import { useEffect, useState } from 'react';
import { legalApi } from '../services/api';

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    legalApi.getStatistics().then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="p-6 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm">
        Lỗi kết nối Backend FastAPI: {error}
      </div>
    );
  }
  if (!stats) {
    return <div className="p-6 text-sm text-[#6B7788]">Đang tải số liệu hệ thống...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="bg-white border border-slate-200 rounded-xl p-6 border-l-4 border-l-[#B83B48]">
        <div className="text-xs font-bold text-[#B83B48] uppercase">LEGAL ASSISTANT ({stats.app_mode.toUpperCase()})</div>
        <h1 className="text-xl font-bold mt-1">Trợ lý tra cứu pháp luật sử dụng RAG, Agent và Citation Validator</h1>
        <p className="text-sm text-[#6B7788] mt-1">
          Hỗ trợ tra cứu, tổng hợp và dẫn nguồn pháp luật Việt Nam (không thay thế tư vấn pháp lý chính thức).
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-[#6B7788]">Nhóm chủ đề câu hỏi</div>
          <div className="text-2xl font-bold mt-1">
            {stats.total_question_categories} / {stats.expected_question_categories}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-[#6B7788]">Tổng câu hỏi</div>
          <div className="text-2xl font-bold mt-1">{stats.total_questions}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-[#6B7788]">Văn bản pháp luật</div>
          <div className="text-2xl font-bold mt-1">{stats.total_documents}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-[#6B7788]">Tổng lượt tra cứu</div>
          <div className="text-2xl font-bold mt-1">{stats.total_queries}</div>
        </div>
      </div>
    </div>
  );
}
