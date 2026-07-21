# 2026-07-21 UI 第二阶段：关键字库页面紧凑化

## 本轮范围

- 只处理 `关键字库` 页面。
- 不改关键字匹配规则。
- 不改白名单匹配范围。
- 不拆新导航，不改后端接口。

## 本轮完成

- 页面保持标题 `关键字库`，改成 `关键字 / 白名单` 双 tab。
- 关键字列表从大卡片改成紧凑表格。
- 白名单列表从大卡片改成紧凑表格。
- 描述、范围、备注长文本默认省略，完整内容保留在 `title`。
- 新增 / 编辑 / 导入 / 导出全部放入弹窗。
- 导入导出 JSON 改为可滚动代码框，不再占主页面空间。
- 按钮统一改小，沿用 `mini-button`。
- 启用状态使用绿色风格，停用使用灰色/禁用风格。

## 涉及文件

- `frontend/src/pages/WhitelistsPage.tsx`
- `frontend/src/pages/WhitelistsPage.test.tsx`
- `frontend/src/pages/DiagnosisPage.test.tsx`
- `frontend/src/pages/AutoInspectionPage.test.tsx`
- `frontend/src/pages/TemplatesPage.test.tsx`

## 为什么改了其他测试

- 这轮页面紧凑化过程中，仓库里已有 `DiagnosisPage`、`AutoInspectionPage`、`TemplatesPage` 的 UI 结构更新。
- 这些测试还保留旧的“唯一文本命中”或旧容器结构断言，导致前端全量测试不绿。
- 本轮只做了最小断言修正，没有改这些页面业务逻辑。

## 验证结果

- `cd frontend && npm test -- --run src/pages/WhitelistsPage.test.tsx`
  - 4 passed
- `cd frontend && npm test -- --run`
  - 52 passed
- `cd frontend && npm run build`
  - passed

## 边界说明

- 当前关键字库仍是单页双 tab，不是两个导航入口，符合本轮要求。
- 当前表格未引入新的第三方表格组件，保持仓库现有样式体系。
- 如果后续要进一步提升密度，可以继续加：
  - 表头筛选
  - 内置/启用快速过滤
  - 范围复制按钮
  - 备注详情 hover 卡片
