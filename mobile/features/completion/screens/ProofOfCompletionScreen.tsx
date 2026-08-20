import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';

export default function ProofOfCompletionScreen() {
  return (
    <AppScreen title="Proof of Completion" description="Completion evidence will be tied to a real active trip later.">
      <EmptyState
        title="No completion to record."
        message="Camera, signature, upload, and completion persistence are not implemented."
      />
    </AppScreen>
  );
}
