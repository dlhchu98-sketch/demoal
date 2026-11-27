'use client';

import { useEffect, useState } from 'react';
import { legalApi, setAuthToken } from '../../services/api';

export default function AdminPortalPage() {
  const [dashboard, setDashboard] = useState<any>(null);
  const [needLogin, setNeedLogin] = useState(false);
  const [identifier, setIdentifier] = useState('admin@legalai.vn');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function loadDashboard() {
    setError(null);
    try {
      const data = await legalApi.getAdminDashboard();
      setDashboard(data);
      setNeedLogin(false);
    } catch (e: any) {
      setNeedLogin(true);
      setError(e.message || 'Yêu cầu đăng nhập Quản trị viên.');
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  async function handleAdminLogin() {
    setError(null);
    try {
      const res = await legalApi.login(identifier, password);
      if (res.user.role !== 'admin') {
        setError('Tài khoản này không có quyền Quản trị viên (Admin).');
        return;
      }
      setAuthToken(res.access_token);
      await loadDashboard();
    } catch (e: any) {
      setError(e.message || 'Đăng nhập thất bại.');
    }
  }

  if (needLogin) {
    return (
      <div className="max-w-md mx-auto bg-white border border-slate-200 rounded-xl p-6 space-y-4">
        <div className="text-xs font-bold uppercase text-[#2563EB]">Admin Portal · RBAC Protected</div>
        <h1 className="text-lg font-bold text-[#0F2544]">Đăng nhập Quản trị viên</h1>
        {error && <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">{error}</div>}
        <div className="space-y-3">
          <input
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            placeholder="admin@legalai.vn"
            className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Mật khẩu quản trị"
            className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm"
          />
          <button
            onClick={handleAdminLogin}
            className="w-full py-2.5 rounded-lg bg-[#0F2544] hover:bg-[#1E3A5F] text-white text-xs font-semibold"
          >
            Đăng nhập Admin Portal
          </button>
        </div>
      </div>
    );
  }

  if (!dashboard) {
    return <div className="p-6 text-sm text-slate-500">Đang tải Admin Dashboard...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="bg-[#0F2544] text-white rounded-xl p-6">
        <div className="text-xs uppercase font-semibold text-blue-200">Admin Portal ({dashboard.app_mode.toUpperCase()})</div>
        <h1 className="text-xl font-bold mt-1">Bảng điều khiển quản trị Legal AI Assistant</h1>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-slate-500">Tổng số văn bản</div>
          <div className="text-2xl font-bold text-[#0F2544] mt-1">{dashboard.total_documents}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-slate-500">Tổng lượt tra cứu</div>
          <div className="text-2xl font-bold text-[#0F2544] mt-1">{dashboard.total_queries}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-slate-500">Số lần kiểm chứng Citation</div>
          <div className="text-2xl font-bold text-[#0F2544] mt-1">{dashboard.total_citations_checked}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs text-slate-500">Số lỗi Citation (FAIL)</div>
          <div className="text-2xl font-bold text-red-600 mt-1">{dashboard.citation_fail_count}</div>
        </div>
      </div>
    </div>
  );
}
