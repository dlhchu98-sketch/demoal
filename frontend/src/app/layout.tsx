import './globals.css';
import type { Metadata } from 'next';
import { Sidebar } from '../components/Sidebar';

export const metadata: Metadata = {
  title: 'LEGAL ASSISTANT — Trợ lý tra cứu pháp luật Việt Nam',
  description: 'Trợ lý tra cứu pháp luật sử dụng RAG, Agent và cơ chế tự kiểm tra trích dẫn.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="min-h-screen flex bg-[#F5F8FC] text-[#243247]">
        <Sidebar />
        <main className="flex-1 p-6 max-w-7xl mx-auto w-full">{children}</main>
      </body>
    </html>
  );
}
