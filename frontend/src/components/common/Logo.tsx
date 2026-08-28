import type { FC } from "react";
import oxfordLogo from "../../assets/images/oxford-suites-logo.png";

export interface LogoProps {
  variant?: "dark" | "light";
  showTagline?: boolean;
  height?: number;
  className?: string;
}

export const Logo: FC<LogoProps> = ({
  variant = "dark",
  showTagline = false,
  height = 32,
  className = "",
}) => {
  const taglineColor = variant === "light" ? "#d3c4b2" : "#8A7F79";

  return (
    <div className={`d-flex align-items-center gap-2 ${className}`.trim()}>
      <img
        src={oxfordLogo}
        alt="Oxford Suites Makati"
        style={{ height: `${height}px`, width: "auto", objectFit: "contain" }}
      />

      {showTagline && (
        <p
          className="mb-0 small"
          style={{
            fontSize: "0.75rem",
            color: taglineColor,
            lineHeight: 1.2,
          }}
        >
          Fleet &amp; transportation management
        </p>
      )}
    </div>
  );
};

export default Logo;
