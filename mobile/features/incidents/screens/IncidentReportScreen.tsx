import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';

export default function IncidentReportScreen() {
  return (
    <AppScreen title="Incident Report" description="Incident capture will be enabled only during an eligible trip.">
      <EmptyState
        title="Reporting is not connected."
        message="No incident, photo, location, or backend record can be submitted in Phase 1."
      />
    </AppScreen>
  );
}
