'use client';

import { useEffect, useState } from 'react';
import { legalApi } from '../../services/api';

export default function CitationsPage() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    legalApi.getCitations().then(setItems).catch(console.error);
  }, []);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-3">
      <h1 className="text-lg font-bold">Kiểm tra trích dẫn ({items.length})</h1>
      <p className="text-sm text-[#6B7788]">Hiển thị claim, nguồn pháp luật, bằng chứng và lý do PASS / FAIL / UNVERIFIED.</p>
    </div>
  );
}
