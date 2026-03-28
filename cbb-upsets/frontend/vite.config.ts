import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "../src/cbb/ui/static/react"),
    emptyOutDir: true,
    sourcemap: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(__dirname, "index.html"),
      output: {
        inlineDynamicImports: true,
        entryFileNames: "dashboard-react.js",
        assetFileNames: (assetInfo) =>
          assetInfo.name?.endsWith(".css")
            ? "dashboard-react.css"
            : "react-[name][extname]",
      },
    },
  },
});
