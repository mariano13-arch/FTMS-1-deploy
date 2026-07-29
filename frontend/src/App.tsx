import { useEffect, useState } from "react";
import { getHealth } from "./services/health";
import "./styles.css";

type ConnectionState = "loading" | "connected" | "error";

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>("loading");

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(() => setConnection("connected"))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setConnection("error");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <section aria-labelledby="page-title">
        <p className="eyebrow">Sprint 0 Development Foundation</p>
        <h1 id="page-title">Fleet and Transportation Management System</h1>
        <div className={`status status--${connection}`} role="status" aria-live="polite">
          <span className="status__indicator" aria-hidden="true" />
          <span>
            Backend connection:{" "}
            {connection === "loading"
              ? "Loading"
              : connection === "connected"
                ? "Connected"
                : "Error"}
          </span>
        </div>
      </section>
    </main>
  );
}
