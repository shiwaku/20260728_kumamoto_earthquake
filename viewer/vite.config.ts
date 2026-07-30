import { defineConfig } from 'vite'

export default defineConfig({
  // GitHub Pages のプロジェクトページ（/<repo>/ 配下）でもそのまま動くよう相対パスで出す。
  base: './',
  server: { port: 8000 },
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC'),
  },
})
