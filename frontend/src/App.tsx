import { useEffect, useState } from 'react';
import { BrowseView } from './components/BrowseView';
import { ImportView } from './components/ImportView';
import { checkHealth } from './api';

type HealthState =
  | { status: 'checking' }
  | { status: 'ok' }
  | { status: 'error' };

type Tab = 'import' | 'browse';

const HEALTH_LABEL: Record<HealthState['status'], string> = {
  checking: 'Connecting',
  ok: 'Online',
  error: 'Service unavailable',
};

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'checking' });
  const [activeTab, setActiveTab] = useState<Tab>('import');

  useEffect(() => {
    checkHealth()
      .then(() => setHealth({ status: 'ok' }))
      .catch(() => setHealth({ status: 'error' }));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-brand">
          <h1>EcoTEA WP1</h1>
          <span className="app-subtitle">Technology &amp; Cost Database</span>
        </div>
        <nav className="tab-nav" aria-label="Primary">
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
        <span
          className={`health-indicator health-${health.status}`}
          role="status"
          aria-live="polite"
          title={HEALTH_LABEL[health.status]}
        >
          <span className="health-dot" aria-hidden="true" />
          {HEALTH_LABEL[health.status]}
        </span>
      </header>

      <main className="app-main">
        {activeTab === 'import' && <ImportView />}
        {activeTab === 'browse' && <BrowseView />}
      </main>
    </div>
  );
}

export default App;
