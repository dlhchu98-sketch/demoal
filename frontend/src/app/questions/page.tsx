'use client';

import { useEffect, useState } from 'react';
import { legalApi } from '../../services/api';

export default function QuestionsPage() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    legalApi.getQuestions().then(setData).catch(console.error);
  }, []);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-3">
      <h1 className="text-lg font-bold">Bộ câu hỏi pháp luật (34 nhóm chủ đề)</h1>
      <p className="text-sm text-[#6B7788]">{data?.note || 'Đang tải danh sách câu hỏi...'}</p>
    </div>
  );
}
