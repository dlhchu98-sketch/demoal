'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart3,
  BookOpen,
  FileText,
  History,
  Home,
  ListChecks,
  MessageSquareText,
  Scale,
  Settings,
  Shield,
  ShieldCheck,
} from 'lucide-react';

const USER_ITEMS = [
  { href: '/', label: 'Trang chủ', icon: Home },
  { href: '/chat', label: 'Trợ lý pháp luật', icon: MessageSquareText },
  { href: '/questions', label: 'Bộ câu hỏi pháp luật', icon: ListChecks },
  { href: '/documents', label: 'Tra cứu văn bản', icon: BookOpen },
  { href: '/history', label: 'Lịch sử tra cứu', icon: History },
];

const ADMIN_ITEMS = [
  { href: '/admin', label: 'Admin Dashboard', icon: Shield },
  { href: '/documents', label: 'Quản lý văn bản & RAG', icon: FileText },
  { href: '/citations', label: 'Citation Validator', icon: ShieldCheck },
  { href: '/evaluation', label: 'Testing & Evaluation', icon: BarChart3 },
  { href: '/settings', label: 'Cấu hình hệ thống', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const isAdminRoute = pathname.startsWith('/admin');
  const items = isAdminRoute ? ADMIN_ITEMS : USER_ITEMS;

  return (
    <aside
      className={`w-64 min-h-screen flex flex-col shrink-0 border-r ${
        isAdminRoute ? 'bg-[#0F2544] text-slate-100 border-slate-800' : 'bg-white text-slate-800 border-slate-200'
      }`}
    >
      <div
        className={`h-16 px-4 border-b flex items-center gap-2.5 ${
          isAdminRoute ? 'border-slate-800' : 'border-slate-200'
        }`}
      >
        <div
          className={`w-9 h-9 rounded-xl text-white flex items-center justify-center ${
            isAdminRoute ? 'bg-[#2563EB]' : 'bg-[#0F2544]'
          }`}
        >
          <Scale className="w-5 h-5" />
        </div>
        <div>
          <div className={`text-sm font-bold ${isAdminRoute ? 'text-white' : 'text-[#0F2544]'}`}>LEGAL AI</div>
          <div className={`text-[11px] ${isAdminRoute ? 'text-blue-200' : 'text-slate-500'}`}>
            {isAdminRoute ? 'Admin Portal' : 'User Portal'}
          </div>
        </div>
      </div>

      <nav className="flex-1 py-3 space-y-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-2.5 text-sm transition ${
                isAdminRoute
                  ? active
                    ? 'bg-blue-500/20 text-white border-r-2 border-blue-400 font-semibold'
                    : 'text-slate-300 hover:bg-white/10'
                  : active
                  ? 'bg-[#EFF6FF] text-[#0F2544] border-r-2 border-[#2563EB] font-semibold'
                  : 'text-slate-700 hover:bg-slate-50'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className={`p-3 border-t ${isAdminRoute ? 'border-slate-800' : 'border-slate-200'}`}>
        <Link
          href={isAdminRoute ? '/' : '/admin'}
          className={`w-full py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 ${
            isAdminRoute
              ? 'bg-white/10 text-white hover:bg-white/20'
              : 'bg-[#0F2544] text-white hover:bg-[#1E3A5F]'
          }`}
        >
          <Shield className="w-3.5 h-3.5" />
          <span>{isAdminRoute ? 'Sang User Portal' : 'Mở Admin Portal'}</span>
        </Link>
      </div>
    </aside>
  );
}
