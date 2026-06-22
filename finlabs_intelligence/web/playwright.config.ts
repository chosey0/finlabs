import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:42817",
    channel: "chrome",
    headless: true,
  },
  webServer: [
    {
      command: "UV_CACHE_DIR=/tmp/finlabs-uv-cache PYTHONPATH=../.. uv run python ../../scripts/run_news_intelligence_e2e_api.py",
      url: "http://127.0.0.1:42818/api/health",
      reuseExistingServer: true,
    },
    {
      command: "VITE_API_BASE_URL=http://127.0.0.1:42818 bun run dev --host 127.0.0.1 --port 42817",
      url: "http://127.0.0.1:42817",
      reuseExistingServer: true,
    },
  ],
});
