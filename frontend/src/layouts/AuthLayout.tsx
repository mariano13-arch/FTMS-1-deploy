import type { FC, ReactNode } from "react";
import AuthImagePanel from "../components/common/AuthImagePanel";

const ROAD_OFFSET_PX = 264;

interface AuthLayoutProps {
  children: ReactNode;
}

export const AuthLayout: FC<AuthLayoutProps> = ({ children }) => {
  return (
    <div className="min-vh-100 bg-white d-flex align-items-center justify-content-center p-3 p-md-4 position-relative overflow-hidden">
      {/* DETAILED ROAD BAND */}
      <div
        className="position-absolute start-0 end-0 overflow-hidden pointer-events-none"
        style={{
          top: `calc(50% + ${ROAD_OFFSET_PX}px)`,
          height: "56px",
          zIndex: 0,
        }}
      >
        {/* Road surface */}
        <div
          className="position-absolute top-0 start-0 w-100 h-100"
          style={{ backgroundColor: "#3b0b14" }}
        />
        {/* Top edge line */}
        <div
          className="position-absolute top-0 start-0 end-0"
          style={{ height: "1px", backgroundColor: "rgba(184, 147, 90, 0.4)" }}
        />
        {/* Center lane marking */}
        <div
          className="auth-road-line-animated position-absolute start-0 end-0 top-50 translate-middle-y opacity-75"
          style={{ height: "4px" }}
        />
        {/* Bottom edge line */}
        <div
          className="position-absolute bottom-0 start-0 end-0"
          style={{ height: "1px", backgroundColor: "rgba(184, 147, 90, 0.2)" }}
        />
      </div>

      {/* LOGIN CARD */}
      <div
        className="position-relative w-100 rounded-4 shadow-lg auth-page-carry d-flex flex-column flex-lg-row"
        style={{
          maxWidth: "896px",
          minHeight: "600px",
          backgroundColor: "#5E1220",
          zIndex: 1,
        }}
      >
        {/* Inner Panel Wrapper */}
        <div className="position-absolute top-0 start-0 w-100 h-100 rounded-4 overflow-hidden d-flex flex-column flex-lg-row">
          {/* Left Column: Image Panel */}
          <div className="d-none d-lg-block col-lg-6 p-2 p-xl-3">
            <AuthImagePanel />
          </div>

          {/* Right Column: Form Window */}
          <div className="col-12 col-lg-6 d-flex align-items-center justify-content-center p-2 p-xl-3">
            <div
              className="w-100 h-100 rounded-4 d-flex align-items-center justify-content-center p-4 p-sm-5"
              style={{ backgroundColor: "#FAF6F1" }}
            >
              <div className="w-100" style={{ maxWidth: "380px" }}>
                {children}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthLayout;
