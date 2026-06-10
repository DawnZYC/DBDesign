import { useEffect, useState } from 'react';
import { BrowseView } from './components/BrowseView';
import { ImportView } from './components/ImportView';
import { ChatPage } from './pages/ChatPage';
import { checkHealth } from './api';

type HealthState =
  | { status: 'checking' }
  | { status: 'ok'; database: string }
  | { status: 'error'; message: string };

type Tab = 'chat' | 'import' | 'browse';

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'checking' });
  // M4: 默认进入 AI 助手（原来是 'import'）
  const [activeTab, setActiveTab] = useState<Tab>('chat');

  useEffect(() => {
    checkHealth()
      .then((res) => setHealth({ status: 'ok', database: res.database }))
      .catch((err) => setHealth({ status: 'error', message: (err as Error).message }));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>SG-TIMES</h1>
        <nav className="tab-nav">
          <button
            type="button"
            className={`tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            AI 助手
          </button>
          <button
            type="button"
            className={`tab ${activeTab === 'browse' ? 'active' : ''}`}
            onClick={() => setActiveTab('browse')}
          >
            数据浏览
          </button>
          <button
            type="button"
            className={`tab ${activeTab === 'import' ? 'active' : ''}`}
            onClick={() => setActiveTab('import')}
          >
            数据接入
          </button>
        </nav>
        <span className={`health-pill health-${health.status}`}>
          {health.status === 'checking' && '后端检测中…'}
          {health.status === 'ok' && `后端正常 · DB ${health.database}`}
          {health.status === 'error' && `后端异常：${health.message}`}
        </span>
      </header>

      <main className="app-main">
        {activeTab === 'chat' && <ChatPage />}
        {activeTab === 'browse' && <BrowseView />}
        {activeTab === 'import' && <ImportView />}
      </main>

      <footer className="app-footer">
        <a href="/api/health" target="_blank" rel="noreferrer">
          /api/health
        </a>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
          API 文档
        </a>
      </footer>
    </div>
  );
}

export default App;
