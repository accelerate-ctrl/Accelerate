/// <reference types="vite/client" />

// SVG imports return the file URL as a string at build time.
declare module '*.svg' {
  const src: string;
  export default src;
}
