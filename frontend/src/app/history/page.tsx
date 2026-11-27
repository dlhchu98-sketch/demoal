'use client';

import { useEffect, useState } from 'react';
import { legalApi } from '../../services/api';

export default function HistoryPage() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    legalApi.getHistory().then(setItems).catch(console.error);
  }, []);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-3">
      <h1 className="text-lg font-bold">Lịch sử tra cứu ({items.length})</h1>
      {items.length === 0 ? (
        <p className="text-sm text-[#6B7788]">Chưa có lịch sử tra cứu.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {items.map((h) => (
            <li key={h.id} className="p-3 rounded-lg border border-slate-200">
              <div className="font-semibold">{h.question}</div>
              <div className="text-xs text-[#6B7788] mt-1">{h.citation_status} · {h.created_at}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
