import { Menu } from 'antd';
import React from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import DocumentPage from './pages/DocumentPage';
import EvaluationPage from './pages/EvaluationPage';
import ExternalTaskpackRunsPage from './pages/ExternalTaskpackRunsPage';
import IndexPage from './pages/IndexPage';
import SearchPage from './pages/SearchPage';
import SettingsPage from './pages/SettingsPage';
import TaskCenterPage from './pages/TaskCenterPage';
import TopicDossierPage from './pages/TopicDossierPage';

const items = [
  { key: '/topics', label: '主题研究' },
  { key: '/search', label: '搜索' },
  { key: '/tasks', label: 'Task Center' },
  { key: '/index', label: '索引状态' },
  { key: '/external-taskpack-runs', label: '外部 TaskPack 归档' },
  { key: '/settings', label: '设置' },
  { key: '/evaluation', label: '评测' },
];

const App: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const selected =
    items.find((it) => location.pathname.startsWith(it.key))?.key ?? '/topics';

  return (
    <>
      <header className="site-header">
        <span className="logo">AI 个人研究工作台</span>
        <Menu
          mode="horizontal"
          selectedKeys={[selected]}
          items={items}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, borderBottom: 'none' }}
        />
      </header>
      <Routes>
        <Route path="/" element={<Navigate to="/topics" replace />} />
        <Route path="/topics" element={<TopicDossierPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/document/:id" element={<DocumentPage />} />
        <Route path="/index" element={<IndexPage />} />
        <Route path="/tasks" element={<TaskCenterPage />} />
        <Route path="/external-taskpack-runs" element={<ExternalTaskpackRunsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="*" element={<Navigate to="/topics" replace />} />
      </Routes>
    </>
  );
};

export default App;
