import React, { useState, useEffect } from "react";
import Logo from "./Logo";
import oxfordSignage from "../../assets/images/oxford-signage.jpg";
import oxfordRoom from "../../assets/images/oxford-room.jpg";
import oxfordBuilding from "../../assets/images/oxford-building.jpg";

const SLIDE_DURATION_MS = 3000;

interface Slide {
  src: string;
  alt: string;
}

const slides: Slide[] = [
  { src: oxfordSignage, alt: "Oxford Suites Makati signage" },
  { src: oxfordRoom, alt: "Oxford Suites Makati deluxe room" },
  { src: oxfordBuilding, alt: "Oxford Suites Makati building" },
];

export const AuthImagePanel: React.FC = () => {
  const [currentIndex, setCurrentIndex] = useState<number>(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % slides.length);
    }, SLIDE_DURATION_MS);

    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className="position-relative w-100 h-100 rounded-4 overflow-hidden"
      style={{ backgroundColor: "#221C1D" }}
    >
      {/* Carousel Images with Smooth Crossfade */}
      {slides.map((slide, index) => (
        <img
          key={slide.src}
          src={slide.src}
          alt={slide.alt}
          className="position-absolute top-0 start-0 w-100 h-100 object-fit-cover"
          style={{
            opacity: index === currentIndex ? 1 : 0,
            transition: "opacity 700ms ease-in-out",
            zIndex: 0,
          }}
        />
      ))}

      {/* Dark Gradient Overlay (Bottom) */}
      <div
        className="position-absolute start-0 end-0 bottom-0"
        style={{
          height: "50%",
          background:
            "linear-gradient(to top, rgba(34, 28, 29, 0.9), transparent)",
          zIndex: 1,
        }}
      />

      {/* Dark Gradient Overlay (Top) */}
      <div
        className="position-absolute start-0 end-0 top-0"
        style={{
          height: "25%",
          background:
            "linear-gradient(to bottom, rgba(34, 28, 29, 0.6), transparent)",
          zIndex: 1,
        }}
      />

      {/* Overlay Content */}
      <div
        className="position-relative h-100 d-flex flex-column justify-content-between p-4 p-lg-5"
        style={{ zIndex: 2 }}
      >
        {/* Top Bar with Logo Chip */}
        <div className="d-flex align-items-center justify-content-between">
          <div
            className="rounded-3 px-3 py-2 shadow-sm"
            style={{ backgroundColor: "rgba(250, 246, 241, 0.95)" }}
          >
            <Logo variant="dark" height={38} />
          </div>
        </div>

        {/* Bottom Headline & Carousel Dots */}
        <div>
          <h2
            className="fw-bold text-white mb-4"
            style={{ fontSize: "1.75rem", lineHeight: 1.3 }}
          >
            Every trip,
            <br />
            perfectly tracked.
          </h2>

          {/* Dynamic Indicators */}
          <div className="d-flex align-items-center gap-2">
            {slides.map((slide, index) => {
              const isActive = index === currentIndex;
              return (
                <button
                  key={slide.src}
                  type="button"
                  onClick={() => setCurrentIndex(index)}
                  aria-label={`Show slide ${index + 1}`}
                  className="border-0 p-0 shadow-none cursor-pointer"
                  style={{
                    height: "6px",
                    width: isActive ? "20px" : "6px",
                    borderRadius: "10px",
                    backgroundColor: isActive
                      ? "#9E1B32"
                      : "rgba(250, 246, 241, 0.4)",
                    transition: "all 300ms ease-in-out",
                  }}
                />
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthImagePanel;
