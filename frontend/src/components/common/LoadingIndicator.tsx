import type { ComponentProps, FC } from "react";
import "./LoadingIndicator.css";

type DotsRingProps = ComponentProps<"span"> & {
  dots?: number;
  dotScale?: number;
  radiusScale?: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function DotsRing({
  className = "",
  style,
  dots = 8,
  dotScale = 0.16,
  radiusScale = 0.34,
  ...props
}: DotsRingProps) {
  const dotCount = Math.max(4, Math.floor(dots));
  const safeDotScale = clamp(dotScale, 0.2, 0.4);
  const safeRadiusScale = clamp(radiusScale, 0, 0.5 - safeDotScale / 2);

  return (
    <span
      role="status"
      aria-label="Loading"
      className={`ld-dots-ring ${className}`.trim()}
      style={style}
      {...props}
    >
      <span aria-hidden="true" className="ld-dots-ring__track">
        {Array.from({ length: dotCount }, (_, index) => {
          const angle = (index / dotCount) * Math.PI * 2;
          const x = Math.sin(angle) * safeRadiusScale * 100;
          const y = -Math.cos(angle) * safeRadiusScale * 100;

          return (
            <span
              key={index}
              className="ld-dots-ring__dot-wrapper"
              style={{
                width: `calc(${safeDotScale} * 100 * var(--ld-q))`,
                height: `calc(${safeDotScale} * 100 * var(--ld-q))`,
                transform: `translate(-50%, -50%) translate(calc(${x} * var(--ld-q)), calc(${y} * var(--ld-q)))`,
              }}
            >
              <span
                className="ld-dots-ring__dot"
                style={{
                  animationDelay: `calc(var(--ld-duration, 1s) / ${dotCount} * ${index - dotCount})`,
                }}
              />
            </span>
          );
        })}
      </span>
    </span>
  );
}

export interface LoadingIndicatorProps {
  size?: "sm" | "md" | "lg";
  variant?: "inline" | "card" | "fullpage";
  message?: string;
  ariaLabel?: string;
  dots?: number;
  className?: string;
}

export const LoadingIndicator: FC<LoadingIndicatorProps> = ({
  size = "md",
  variant = "inline",
  message,
  ariaLabel = "Loading",
  dots = 8,
  className = "",
}) => {
  return (
    <div
      className={`ld-indicator ld-indicator--${variant} ld-indicator--${size} ${className}`.trim()}
      role="status"
      aria-label={ariaLabel}
    >
      <DotsRing dots={dots} />
      {(message || variant === "fullpage") && (
        <span className="ld-indicator__text">
          {message || "Loading…"}
        </span>
      )}
    </div>
  );
};

export default LoadingIndicator;
