import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// /api 代理到本机后端（后端仅绑定 127.0.0.1:8765，见 HANDOFF_M11.md §5.1）
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
});
