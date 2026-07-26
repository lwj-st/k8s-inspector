from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI


HookCallable = Callable[[FastAPI], Awaitable[None] | None]


@dataclass(frozen=True)
class LifespanHook:
    name: str
    start: HookCallable
    stop: HookCallable


_HOOKS: list[LifespanHook] = []


def register_lifespan_hook(*, name: str, start: HookCallable, stop: HookCallable) -> None:
    if not name.strip():
        raise ValueError("lifespan hook 名称不能为空")
    if any(item.name == name for item in _HOOKS):
        raise ValueError(f"lifespan hook 已注册：{name}")
    _HOOKS.append(LifespanHook(name=name, start=start, stop=stop))


async def _invoke(callback: HookCallable, app: FastAPI) -> None:
    result = callback(app)
    if inspect.isawaitable(result):
        await result


def build_lifespan():
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        started: list[LifespanHook] = []
        app.state.lifespan_hook_error = None
        if app.state.platform_initialization_error is None:
            try:
                for hook in _HOOKS:
                    await _invoke(hook.start, app)
                    started.append(hook)
            except Exception as exc:
                app.state.lifespan_hook_error = f"扩展组件 {hook.name} 启动失败：{type(exc).__name__}"
                for active in reversed(started):
                    try:
                        await _invoke(active.stop, app)
                    except Exception:
                        pass
                started.clear()
        app.state.lifespan_started_hooks = [hook.name for hook in started]
        try:
            yield
        finally:
            for hook in reversed(started):
                try:
                    await _invoke(hook.stop, app)
                except Exception:
                    pass

    return lifespan
