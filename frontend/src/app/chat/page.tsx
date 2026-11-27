'use client';

import { useState } from 'react';
import { legalApi } from '../../services/api';
import type { ChatResponse } from '../../types/legal';

export default function ChatPage() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatResponse[]>([]);

  async function handleSubmit() {
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await legalApi.chat(question.trim(), messages[0]?.conversation_id || null);
      setMessages((prev) => [res, ...prev]);
      setQuestion('');
    } catch (e: any) {
      setError(e.message || 'Lỗi khi gửi câu hỏi');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
        <h1 className="text-lg font-bold">Trợ lý tra cứu pháp luật</h1>
        <textarea
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Nhập câu hỏi pháp luật bằng tiếng Việt..."
          className="w-full rounded-lg border border-slate-300 p-3 text-sm"
        />
        <div className="flex gap-2">
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 rounded-lg bg-[#B83B48] hover:bg-[#D64A55] text-white text-sm font-semibold disabled:opacity-50"
          >
            {loading ? 'Đang phân tích & kiểm tra trích dẫn...' : 'Gửi câu hỏi'}
          </button>
          <button
            onClick={() => setQuestion('')}
            className="px-4 py-2 rounded-lg bg-slate-100 text-sm text-[#6B7788]"
          >
            Xóa nội dung
          </button>
        </div>
        {error && <div className="text-xs text-red-700 bg-red-50 p-3 rounded-lg">{error}</div>}
      </div>

      {messages.map((m) => (
        <div key={m.request_id} className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
          <div className="flex justify-between items-center border-b pb-2">
            <span className="font-bold text-sm">{m.question}</span>
            <span className="text-xs px-2 py-0.5 rounded bg-[#EAF3FC] text-[#3976A9] font-semibold">
              {m.citation_status} {m.is_mock ? '(DEMO)' : '(LIVE)'}
            </span>
          </div>
          <div className="text-sm whitespace-pre-line">{m.answer}</div>
          <div className="text-xs text-[#6B7788]">{m.disclaimer}</div>
        </div>
      ))}
    </div>
  );
}
