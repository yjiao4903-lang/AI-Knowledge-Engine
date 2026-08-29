import { Menu } from 'antd';
import React from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import DocumentPage from './pages/DocumentPage';
import EvaluationPage from './pages/EvaluationPage';
import IndexPage from './pages/IndexPage';
import SearchPage from './pages/SearchPage';
import SettingsPage from './pages/SettingsPage';

const items = [
  { key: '/search', label: '搜索' },
  { key: '/index', label: '索引状态' },
  { key: '/settings', label: '设置' },
  { key: '/evaluation', label: '评测' },
];

const App: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const selected =
    items.find((it) => location.pathname.startsWith(it.key))?.key ?? '/search';

  return (
    <>
      <header className="site-header">
        <span className="logo">AI 深度报告知识检索</span>
        <Menu
          mode="horizontal"
          selectedKeys={[selected]}
          items={items}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, borderBottom: 'none' }}
        />
      </header>
      <Routes>
        <Route path="/" element={<Navigate to="/search" replace />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/document/:id" element={<DocumentPage />} />
        <Route path="/index" element={<IndexPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="*" element={<Navigate to="/search" replace />} />
      </Routes>
    </>
  );
};

export default App;
