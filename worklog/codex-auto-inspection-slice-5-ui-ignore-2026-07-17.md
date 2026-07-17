# 2026-07-17 Slice 5 UI 忽略命中闭环

## 本次完成

- 完成自动巡检页面证据抽屉中的“日志关键字命中忽略”闭环，仅作用于日志命中，不扩散到模板或其他对象。
- 为每条日志命中增加“忽略此命中”按钮。
- 已在白名单中的命中展示为“已忽略”，按钮禁用。
- 点击忽略后会先出现确认区域，展示以下上下文：
  - 名称空间
  - Label Selector
  - Pod
  - 容器
  - 关键字
- 确认后调用 `/api/v1/whitelists/ignore`，成功时当前抽屉内就地更新为“已忽略”。
- 失败时在抽屉内展示可读错误，且保持抽屉和确认区域不关闭。

## 涉及文件

- `frontend/src/pages/AutoInspectionPage.tsx`
- `frontend/src/pages/AutoInspectionPage.test.tsx`

## 验证结果

- `cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx` 通过
- `cd frontend && npm test -- --run` 通过
- `cd frontend && npm run build` 通过

## 边界说明

- 本次没有修改后端白名单接口契约，复用已有 `ignoreWhitelistLogHit`。
- 本次没有实现“从自动巡检页直接管理完整白名单列表”，只做命中后的忽略闭环。
- 本次没有改动故障模板录入、模板匹配、名称空间选择、证据采集逻辑。

## 需要其他 Agent 注意

- 如果后续要统一“忽略此报错/忽略此命中/已忽略/白名单已生效”文案，建议一次性在 Pod 巡检页、名称空间巡检页、自动巡检页统一，不要单页各自改。
- 如果后续要把确认区域改为弹窗，需要保留当前字段完整性，不能丢掉名称空间、Label Selector、Pod、容器、关键字这五项。
