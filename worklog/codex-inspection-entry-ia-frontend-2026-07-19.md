# 巡检入口 IA 前端复核

## 当前实现

- 名称空间巡检以名称空间下拉为主入口，保留高级手动输入。
- Pod 巡检先选名称空间，再选择“全部 Pod”“Label Selector”“单个 Pod”。
- 全部 Pod 和 Label Selector 复用 namespace inspection；单 Pod 使用 pod inspection。
- 单 Pod 选项由一次 namespace 巡检结果生成。
- 保存、常用范围、导入、导出位于次级区域；导入导出内容只在弹窗中出现。
- 白名单忽略、证据查看和模板匹配入口保留。

## 验证

- 指定页面测试：35 passed
- 前端全量：47 passed
- 前端 build：通过
