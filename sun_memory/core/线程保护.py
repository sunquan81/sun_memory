# -*- coding: utf-8 -*-
"""线程保护 · 全局状态统一锁（2026-09-14 吸收收束版优点）
========================================================
来源：外部 AI《统一收束版》的"统一连接管理（线程安全）"思路
背景：外部审查 🟡1 —— 本库 11 个模块级可变缓存（_索引缓存/_拉边累积/_核心关键词缓存/
      _薄弱点缓存/_缓存网/_向量缓存/...）无锁保护。provider 的 queue_prefetch 走后台线程，
      与主线程同时操作这些全局状态 → 竞态风险。

策略（最小改动·不重构业务流程）：
  · 提供一把全局可重入锁（RLock）：同线程可重复获取（防自锁）
  · 高风险的"缓存读写/攒批计数"段落用 同步() 包装或用 with 加锁()
  · 不改变任何业务逻辑·只保证并发下缓存不被撕裂

用法：
    from 线程保护 import 加锁, 同步
    with 加锁():
        ...读改写缓存...

    @同步
    def 我的函数(): ...
"""
import threading
from contextlib import contextmanager

# 全局可重入锁（同一线程内可重复获取·防自锁）
_全局锁 = threading.RLock()


def 加锁():
    """返回全局锁（配合 with 使用）"""
    return _全局锁


@contextmanager
def 临界区():
    """with 临界区(): ... —— 语义同 加锁()"""
    with _全局锁:
        yield


def 同步(fn):
    """装饰器：整个函数在锁内执行"""
    def wrapper(*args, **kwargs):
        with _全局锁:
            return fn(*args, **kwargs)
    wrapper.__name__ = getattr(fn, '__name__', 'wrapped')
    wrapper.__doc__ = getattr(fn, '__doc__', None)
    return wrapper


def 状态() -> dict:
    """自检：锁是否可用"""
    return {'锁': type(_全局锁).__name__, '可重入': True, '已锁': _全局锁._is_owned() if hasattr(_全局锁, '_is_owned') else None}


if __name__ == '__main__':
    # 自检：重入 + 并发计数
    import time
    print('═══ 线程保护 · 自检 ═══')
    print('  ① 重入:', end=' ')
    with 加锁():
        with 加锁():
            print('OK（同线程两次加锁不卡）')

    counter = {'n': 0}

    @同步
    def 累加():
        v = counter['n']
        time.sleep(0.0005)          # 故意放大竞态窗口
        counter['n'] = v + 1

    import threading as _t
    ts = [_t.Thread(target=累加) for _ in range(50)]
    for t in ts: t.start()
    for t in ts: t.join()
    print(f'  ② 并发 50 线程累加（有锁）: {counter["n"]}（应=50）')
    assert counter['n'] == 50, '锁失效！'
    print('  ③ 状态:', 状态())
    print('═══ 自检通过 ✅ ═══')
