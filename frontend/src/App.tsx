import { useEffect, useState } from 'react';
import { BrowseView } from './components/BrowseView';
import { ConvertView } from './components/ConvertView';
import { ImportView } from './components/ImportView';
import { checkHealth } from './api';
import type { ConvertResult } from './types';

type HealthState = { status: 'checking' } | { status: 'ok' } | { status: 'error' };

type Tab = 'convert' | 'import' | 'browse';

const HEALTH_LABEL: Record<HealthState['status'], string> = {
  checking: 'Connecting',
  ok: 'Online',
  error: 'Service unavailable',
};

const STEPS: Array<{ id: Tab; index: string; title: string; description: string }> = [
  {
    id: 'convert',
    index: '01',
    title: 'Convert',
    description: 'Map VT model files to the unified EcoTEA workbook.',
  },
  {
    id: 'import',
    index: '02',
    title: 'Import',
    description: 'Load EcoTEA workbooks into the database.',
  },
  {
    id: 'browse',
    index: '03',
    title: 'Browse',
    description: 'Search and inspect technology records.',
  },
];

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'checking' });
  const [activeTab, setActiveTab] = useState<Tab>('convert');
  const [pendingConversion, setPendingConversion] = useState<ConvertResult | null>(null);

  useEffect(() => {
    checkHealth()
      .then(() => setHealth({ status: 'ok' }))
      .catch(() => setHealth({ status: 'error' }));
  }, []);

  const handleHandoffToImport = (result: ConvertResult) => {
    setPendingConversion(result);
    setActiveTab('import');
  };

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Workflow steps">
        <div className="sidebar-brand">
          <div className="brand-mark" aria-hidden="true">
            EW
          </div>
          <div className="brand-text">
            <div className="brand-title">EcoTEA WP1</div>
            <div className="brand-subtitle">Technology &amp; Cost Database</div>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {STEPS.map((step) => {
            const isActive = activeTab === step.id;
            return (
              <button
                key={step.id}
                type="button"
                className={`sidebar-step ${isActive ? 'active' : ''}`}
                onClick={() => setActiveTab(step.id)}
                aria-current={isActive ? 'page' : undefined}
              >
                <span className="step-index">{step.index}</span>
                <span className="step-content">
                  <span className="step-title">{step.title}</span>
                  <span className="step-description">{step.description}</span>
                </span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <span
            className={`health-indicator health-${health.status}`}
            role="status"
            aria-live="polite"
          >
            <span className="health-dot" aria-hidden="true" />
            {HEALTH_LABEL[health.status]}
          </span>
        </div>
      </aside>

      <main className="app-main">
        <header className="page-header">
          <div>
            <div className="page-eyebrow">{STEPS.find((s) => s.id === activeTab)?.index}</div>
            <h1 className="page-title">{STEPS.find((s) => s.id === activeTab)?.title}</h1>
            <p className="page-description">{STEPS.find((s) => s.id === activeTab)?.description}</p>
          </div>
        </header>

        {activeTab === 'convert' && <ConvertView onHandoffToImport={handleHandoffToImport} />}
        {activeTab === 'import' && (
          <ImportView
            handoff={pendingConversion}
            onHandoffConsumed={() => setPendingConversion(null)}
          />
        )}
        {activeTab === 'browse' && <BrowseView />}
      </main>
    </div>
  );
}

export default App;
