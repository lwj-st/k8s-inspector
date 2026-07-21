# 2026-07-21 默认错误关键字补充记录

## 背景

用户要求系统预置常见 error、Python 报错和前端报错关键字，减少首次使用时的手动配置成本。

## 修正内容

文件：

1. `backend/app/services/keyword_service.py`
2. `backend/tests/test_whitelist_api.py`

实现：

1. 扩充 `DEFAULT_KEYWORDS`，覆盖通用网络、Python、数据库、前端/Node.js/浏览器常见错误。
2. 预置规则仍使用 `builtin=True`，由 `ensure_default_keywords()` 在数据库初始化和关键字列表/匹配时自动补齐。
3. 不在前端硬编码关键字，前端继续从 `/api/v1/keywords` 读取系统关键字库。

## 新增关键字范围

1. 通用：`connection refused`、`timeout`
2. Python：`Traceback (most recent call last)`、`ModuleNotFoundError`、`ImportError`、`SyntaxError`、`IndentationError`、`KeyError`、`TypeError`、`ValueError`
3. 数据库：`OperationalError`
4. 前端/Node.js/浏览器：`UnhandledPromiseRejection`、`TypeError:`、`ReferenceError`、`ChunkLoadError`、`Loading chunk`、`Failed to fetch`、`NetworkError`、`Cannot read properties of undefined`、`Cannot read property`

## 注意

1. 这些是默认启用的内置规则，用户仍可在关键字库页面禁用。
2. 白名单逻辑不变，误报仍可按 namespace、label selector、pod、container、keyword 忽略。
