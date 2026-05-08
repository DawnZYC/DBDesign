import { useEffect, useState } from 'react';
import { BrowseView } from './components/BrowseView';
import { ImportView } from './components/ImportView';
import { checkHealth } from './api';

type HealthState =
  | { status: 'checking' }
  | { status: 'ok'; database: string }
  | { status: 'error'; message: string };

type Tab = 'import' | 'browse';

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'checking' });
  const [activeTab, setActiveTab] = useState<Tab>('import');

  useEffect(() => {
    checkHealth()
      .then((res) => setHealth({ status: 'ok', database: res.database }))
      .catch((err) => setHealth({ status: 'error', message: (err as Error).message }));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>EcoTEA WP1</h1>
        <nav className="tab-nav">
          <button
            type="button"
            className={`tab ${activeTab === 'import' ? 'active' : ''}`}
            onClick={() => setActiveTab('import')}
          >
            Import Data
          </button>
          <button
            type="button"
            className={`tab ${activeTab === 'browse' ? 'active' : ''}`}
            onClick={() => setActiveTab('browse')}
          >
            Browse Data
          </button>
        </nav>
        <span className={`health-pill health-${health.status}`}>
          {health.status === 'checking' && 'Checking backend...'}
          {health.status === 'ok' && `Backend OK · DB ${health.database}`}
          {health.status === 'error' && `Backend error: ${health.message}`}
        </span>
      </header>

      <main className="app-main">
        {activeTab === 'import' && <ImportView />}
        {activeTab === 'browse' && <BrowseView />}
      </main>

      <footer className="app-footer">
        <a href="/api/health" target="_blank" rel="noreferrer">
          /api/health
        </a>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
          API Docs
        </a>
      </footer>
    </div>
  );
}

export default App;
