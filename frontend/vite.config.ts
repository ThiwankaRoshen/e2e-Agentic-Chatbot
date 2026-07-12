import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  optimizeDeps: {
    include: [
      "@langchain/langgraph-sdk",
      "@langchain/langgraph",
      "@langchain/core",
      "sonner",
      "framer-motion",
      "use-stick-to-bottom",
      "react-markdown",
      "react-syntax-highlighter",
      "uuid",
      "lodash",
      "date-fns",
    ],
  },
});
