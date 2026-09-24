import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    server: {
        host: '127.0.0.1',
        port: 5173,
        strictPort: true,
        proxy: {
            '/_backend': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: false,
                rewrite: function (path) { return path.replace(/^\/_backend/, ''); },
            },
        }
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks: {
                    react: ['react', 'react-dom', 'react-router-dom'],
                    mui: ['@mui/material', '@mui/icons-material', '@emotion/react', '@emotion/styled'],
                    query: ['@tanstack/react-query'],
                    charts: ['recharts'],
                },
            },
        },
    },
    test: {
        environment: 'jsdom',
        setupFiles: './src/test/setup.ts',
        css: true,
        testTimeout: 10000,
    }
});
