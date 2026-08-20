import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';

export default function TripHistoryScreen() {
  return (
    <AppScreen title="Trip History" description="Completed driver trips will appear here after API integration.">
      <EmptyState title="No trip history." message="No fabricated completion records are included in this foundation." />
    </AppScreen>
  );
}
