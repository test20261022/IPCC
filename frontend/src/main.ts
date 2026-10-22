import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'

import App from '@/App.vue'
import { isApiError } from '@/api/request'
import { permission } from '@/directives/permission'
import router from '@/router'
import '@/styles/index.css'

const app = createApp(App)

// 接口失败的提示已由响应拦截器统一弹出（§79：按钮 loading + 业务幂等），
// 页面里未捕获的 rejection 只是重复噪音，这里只屏蔽「已提示过」的错误，
// 其它未捕获异常照常输出到控制台。
app.config.errorHandler = (error) => {
  if (!isApiError(error)) {
    console.error(error)
  }
}

window.addEventListener('unhandledrejection', (event) => {
  if (isApiError(event.reason)) {
    event.preventDefault()
  }
})

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

Object.entries(ElementPlusIconsVue).forEach(([name, component]) => {
  app.component(name, component)
})

app.directive('permission', permission)

app.mount('#app')
