import { useEffect, useState } from 'react';
import { BrowseView } from './components/BrowseView';
import { ConvertView } from './components/ConvertView';
import { EmissionFactorView } from './components/EmissionFactorView';
import { ImportView } from './components/ImportView';
import { ChatPage } from './pages/ChatPage';
import { checkHealth } from './api';
import type { ConvertResult } from './types';

type HealthState = { status: 'checking' } | { status: 'ok' } | { status: 'error' };

type Tab = 'chat' | 'convert' | 'import' | 'browse' | 'emission';

const HEALTH_LABEL: Record<HealthState['status'], string> = {
  checking: 'Connecting',
  ok: 'Online',
  error: 'Service unavailable',
};

const STEPS: Array<{ id: Tab; index: string; title: string; description: string }> = [
  {
    id: 'chat',
    index: '01',
    title: 'AI Assistant',
    description: 'Ask in natural language; agents query, interpret, and chart.',
  },
  {
    id: 'convert',
    index: '02',
    title: 'Convert',
    description: 'Map VT model files to the unified EcoTEA workbook.',
  },
  {
    id: 'import',
    index: '03',
    title: 'Import',
    description: 'Load EcoTEA workbooks into the database.',
  },
  {
    id: 'browse',
    index: '04',
    title: 'Browse',
    description: 'Search and inspect technology records.',
  },
  {
    id: 'emission',
    index: '05',
    title: 'Emission Factors',
    description: 'Manually enter or edit emission factors per technology-year.',
  },
];

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'checking' });
  const [activeTab, setActiveTab] = useState<Tab>('chat');
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

  // Views are kept mounted and merely hidden (see below). ECharts instances
  // that finished rendering while their pane was hidden have zero size, and
  // echarts-for-react only auto-resizes on window resize — so fire one when
  // the visible tab changes.
  useEffect(() => {
    window.dispatchEvent(new Event('resize'));
  }, [activeTab]);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Workflow steps">
        <div className="sidebar-brand">
          <div className="brand-mark" aria-hidden="true">
            St
          </div>
          <div className="brand-text">
            <div className="brand-title">Strata</div>
            <div className="brand-subtitle">Energy Model Analytics</div>
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

        {/* All views stay mounted; inactive ones are hidden with CSS. This keeps
            per-view state alive across tab switches — the chat conversation (and
            any in-flight SSE stream), import wizard progress, and browse filters
            survive navigation instead of being destroyed on unmount. */}
        <div className="view-pane" hidden={activeTab !== 'chat'}>
          <ChatPage />
        </div>
        <div className="view-pane" hidden={activeTab !== 'convert'}>
          <ConvertView onHandoffToImport={handleHandoffToImport} />
        </div>
        <div className="view-pane" hidden={activeTab !== 'import'}>
          <ImportView
            handoff={pendingConversion}
            onHandoffConsumed={() => setPendingConversion(null)}
          />
        </div>
        <div className="view-pane" hidden={activeTab !== 'browse'}>
          <BrowseView />
        </div>
        <div className="view-pane" hidden={activeTab !== 'emission'}>
          <EmissionFactorView />
        </div>
      </main>
    </div>
  );
}

export default App;
