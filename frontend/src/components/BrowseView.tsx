import { useState } from 'react';
import { TechnologyDetailPanel } from './TechnologyDetailPanel';
import { TechnologyList } from './TechnologyList';

export function BrowseView() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <div className="browse-view">
      <TechnologyList onSelect={setSelectedId} selectedId={selectedId} />
      <TechnologyDetailPanel technologyId={selectedId} />
    </div>
  );
}
