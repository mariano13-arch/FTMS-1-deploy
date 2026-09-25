import { useHistory, useParams } from "react-router-dom";
import RequestDetailsDrawer from "../components/RequestDetailsDrawer";

export default function TransportRequestDetailPage() {
  const { requestId = "" } = useParams<{ requestId: string }>();
  const history = useHistory();

  return (
    <section className="request-standalone-detail" aria-label="Transport request detail">
      <RequestDetailsDrawer
        requestId={requestId}
        standalone
        onClose={() => history.push("/transport-requests")}
      />
    </section>
  );
}
