import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 构建产物直接落进 Flask 的静态目录 static/vue/，
 * base 与 Flask 的 static_url_path="/static" 对齐：
 *   /static/vue/assets/xxx.js -> static/vue/assets/xxx.js
 * 因此后端不需要新增任何静态路由，也不需要 Node 常驻服务。
 */
export default defineConfig(({ command }) => ({
  plugins: [vue()],
  base: command === 'build' ? '/static/vue/' : '/',
  build: {
    outDir: '../static/vue',
    assetsDir: 'assets',
    emptyOutDir: true,
    sourcemap: false,
  },
}))
