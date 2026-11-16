import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

// 七层样式，顺序与 scaffold-master/DESIGN.md 一致：
// 令牌 -> 基础 -> 材质 -> 组件 -> 仪器 -> 外壳 -> 页面
import './styles/tokens.css'
import './styles/base.css'
import './styles/materials.css'
import './styles/components.css'
import './styles/instruments.css'
import './styles/layout.css'
import './styles/pages.css'

createApp(App).use(createPinia()).mount('#app')
