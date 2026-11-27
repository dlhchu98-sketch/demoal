'use client';

import { useEffect, useState } from 'react';
import { legalApi } from '../../services/api';

export default function EvaluationPage() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    legalApi.getEvaluationResults().then(setData).catch(console.error);
  }, []);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-3">
      <h1 className="text-lg font-bold">Đánh giá hệ thống (4 phiên bản)</h1>
      <p className="text-sm text-[#6B7788]">{data?.note || 'Đang tải cấu hình đánh giá...'}</p>
    </div>
  );
}
