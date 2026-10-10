import { Link } from 'react-router-dom';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { Panel } from '../../components/Panel/Panel';

export function UnauthorizedScreen() {
  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh', padding: '1rem' }}>
      <Panel accent="var(--cl-coral)">
        <EmptyState
          icon="ghost"
          title="Off Limits"
          message="Your current role doesn't have access to this area."
          action={<Link to="/home">Back to Home</Link>}
        />
      </Panel>
    </div>
  );
}
