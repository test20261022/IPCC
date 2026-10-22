import type { RouteRecordRaw } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 菜单与页签标题 */
    title?: string
    /** Element Plus 图标组件名 */
    icon?: string
    /** 访问所需权限码（§59），为空表示登录即可访问 */
    permission?: string
    /** 是否在菜单中隐藏 */
    hidden?: boolean
    /** 分组路由即使只有一个子路由也保持子菜单形态 */
    alwaysShow?: boolean
  }
}

/** 无需权限即可访问的路由 */
export const constantRoutes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', hidden: true },
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在', hidden: true },
  },
  {
    // 兜底路由：直接渲染 404 组件，**不能**用 redirect。
    // 原因：路由记录上的 redirect 由 vue-router 在处理跳转时（早于 beforeEach）执行，
    // 会把尚未注册的动态路由（如 '/'、'/outbound/types'）提前改写成 /404，导致守卫失效。
    // 这里只做「兜底渲染」：未匹配路径显示 404，动态路由注册后静态路径优先级更高，仍能正常命中。
    path: '/:pathMatch(.*)*',
    name: 'CatchAll',
    component: () => import('@/views/error/404.vue'),
    meta: { hidden: true },
  },
]

/**
 * 需要权限的路由。
 * meta.permission 与后端权限码一一对应（§59），菜单与路由都据此过滤。
 */
export const asyncRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Root',
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '首页', icon: 'HomeFilled' },
      },
    ],
  },
  {
    path: '/outbound',
    name: 'Outbound',
    component: () => import('@/layout/index.vue'),
    redirect: '/outbound/types',
    meta: { title: '智能外呼', icon: 'PhoneFilled', alwaysShow: true },
    children: [
      {
        path: 'types',
        name: 'OutboundTypeList',
        component: () => import('@/views/outbound/type/index.vue'),
        meta: { title: '外呼类型', icon: 'Files', permission: 'outbound:type:list' },
      },
      {
        path: 'scenes',
        name: 'OutboundSceneList',
        component: () => import('@/views/outbound/scene/index.vue'),
        meta: { title: '外呼场景', icon: 'Grid', permission: 'outbound:scene:list' },
      },
      {
        path: 'numbers',
        name: 'OutboundNumberList',
        component: () => import('@/views/outbound/number/index.vue'),
        meta: { title: '外呼号码', icon: 'Phone', permission: 'outbound:number:list' },
      },
      {
        path: 'tasks',
        name: 'OutboundTaskList',
        component: () => import('@/views/outbound/task/index.vue'),
        meta: { title: '外呼任务', icon: 'Tickets', permission: 'outbound:task:list' },
      },
      {
        path: 'lists',
        name: 'OutboundListData',
        component: () => import('@/views/outbound/list/index.vue'),
        meta: { title: '外呼名单', icon: 'Document', permission: 'outbound:list:list' },
      },
      {
        path: 'records',
        name: 'OutboundRecordList',
        component: () => import('@/views/outbound/record/index.vue'),
        meta: { title: '执行记录', icon: 'VideoPlay', permission: 'outbound:task:list' },
      },
      {
        path: 'agents',
        name: 'OutboundAgentList',
        component: () => import('@/views/outbound/agent/index.vue'),
        meta: { title: '坐席与分配', icon: 'User', permission: 'outbound:agent:list' },
      },
      {
        path: 'sessions',
        name: 'OutboundSessionList',
        component: () => import('@/views/outbound/session/index.vue'),
        meta: { title: '外呼会话', icon: 'ChatDotRound', permission: 'outbound:session:list' },
      },
      {
        path: 'ivr',
        name: 'OutboundIvrFlow',
        component: () => import('@/views/outbound/ivr/index.vue'),
        meta: { title: 'IVR 外呼策略', icon: 'Guide', permission: 'outbound:ivr:list' },
      },
      {
        path: 'callback',
        name: 'OutboundCallback',
        component: () => import('@/views/outbound/callback/index.vue'),
        meta: { title: '回呼流程', icon: 'PhoneFilled', permission: 'outbound:callback:list' },
      },
      {
        path: 'monitor',
        name: 'OutboundMonitor',
        component: () => import('@/views/outbound/monitor/index.vue'),
        meta: { title: '实时监控', icon: 'Odometer', permission: 'outbound:monitor:view' },
      },
      {
        path: 'reports',
        name: 'OutboundCallFlowReport',
        component: () => import('@/views/outbound/report/index.vue'),
        meta: { title: '话务流水报表', icon: 'DataLine', permission: 'outbound:report:list' },
      },
    ],
  },
  {
    path: '/qc',
    name: 'Qc',
    component: () => import('@/layout/index.vue'),
    redirect: '/qc/tasks',
    meta: { title: '对话质检', icon: 'ChatDotRound', alwaysShow: true },
    children: [
      {
        path: 'tasks',
        name: 'QcTaskList',
        component: () => import('@/views/qc/tasks/index.vue'),
        meta: { title: '质检任务', icon: 'Tickets', permission: 'qc:task:list' },
      },
      {
        path: 'workspace',
        name: 'QcWorkspace',
        component: () => import('@/views/qc/workspace/index.vue'),
        meta: { title: '我的质检', icon: 'EditPen', permission: 'qc:review:work' },
      },
      {
        path: 'conversations',
        name: 'QcConversationList',
        component: () => import('@/views/qc/conversations/index.vue'),
        meta: { title: '对话数据', icon: 'ChatLineSquare', permission: 'qc:conversation:list' },
      },
      {
        path: 'cases',
        name: 'QcCaseList',
        component: () => import('@/views/qc/cases/index.vue'),
        meta: { title: '优秀案例库', icon: 'Star', permission: 'qc:case:list' },
      },
      {
        path: 'report',
        name: 'QcReport',
        component: () => import('@/views/qc/report/index.vue'),
        meta: { title: '质检报表', icon: 'DataLine', permission: 'qc:report:list' },
      },
      {
        path: 'reviewers',
        name: 'QcReviewerGroupList',
        component: () => import('@/views/qc/reviewers/index.vue'),
        meta: { title: '专家组', icon: 'UserFilled', permission: 'qc:reviewer:list' },
      },
    ],
  },
]
