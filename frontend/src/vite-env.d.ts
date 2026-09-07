/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_TOMTOM_MAPS_KEY?: string;
  readonly VITE_SESSION_IDLE_TIMEOUT_SECONDS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
