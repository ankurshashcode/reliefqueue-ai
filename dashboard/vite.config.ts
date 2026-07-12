import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { defineConfig } from 'vite';

const productApiTarget =
  process.env.RELIEFQUEUE_API_PROXY_TARGET
  || process.env.RELIEFQUEUE_PRODUCT_API_TARGET
  || 'http://127.0.0.1:5001';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  server: {
    hmr: process.env.DISABLE_HMR !== 'true',
    watch: process.env.DISABLE_HMR === 'true' ? null : {},
    proxy: {
      '/api': {
        target: productApiTarget,
        changeOrigin: false,
      },
    },
  },
});
