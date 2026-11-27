'use client';

import { useEffect, useState } from 'react';
import { legalApi } from '../../services/api';

export default function SettingsPage() {
  const [status, setStatus] = useState<any>(null);
  useEffect(() => {
    legalApi.getStatus().then(setStatus).catch(console.error);
  }, []);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-3">
      <h1 className="text-lg font-bold">Cài đặt hệ thống</h1>
      <p className="text-sm text-[#6B7788]">
        Chế độ hiện tại: <strong>{status?.app_mode?.toUpperCase() || '...'}</strong>
      </p>
    </div>
  );
}
