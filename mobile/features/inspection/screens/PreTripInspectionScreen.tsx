import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';

export default function PreTripInspectionScreen() {
  return (
    <AppScreen title="Pre-Trip Inspection" description="A verified assignment will be required before inspection entry.">
      <EmptyState
        title="Inspection unavailable."
        message="Checklist fields and persistence are intentionally deferred to a later phase."
      />
    </AppScreen>
  );
}
