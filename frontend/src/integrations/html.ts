import { registerNamespace } from '@mutgui/core';

/** 注册 `html` 命名空间 — key 原样作为 HTML 标签名，覆盖原生标签和 Web Components。 */
registerNamespace('html', (key) => key);
