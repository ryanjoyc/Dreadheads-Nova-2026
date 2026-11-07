import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    watch: { ignored: ["**/test-results/**", "**/playwright-report/**", "**/tests/**"] },
    proxy: {
      "/api": {
        target: process.env.SALES_API_URL || "http://127.0.0.1:8003",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
