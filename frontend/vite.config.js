import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // The browser calls /api/... on the vite origin and vite forwards it to
    // Flask. Same-origin requests mean no CORS, no cookie/port headaches,
    // and one env var to change when you deploy.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
});