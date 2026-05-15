/**
 * 浏览器全局事件 → 后端的统一通道。
 *
 * 与 View 组件事件区分：source 为 [] 表示框架级，event 名以 $ 前缀。
 *
 * 防循环：依赖 W3C 规范——`history.pushState` / `replaceState` **不**触发
 * `hashchange` 也不触发 `popstate`。`mutgui.setHash` 走 pushState/replaceState
 * 通道，因此后端发命令改 hash 不会回环触发 `$hashchange`。
 */

export type SendRaw = (data: string) => void;

interface SystemEventEnvelope {
  source: never[];
  event: string;
  data: Record<string, unknown>;
}

function sendSystemEvent(
  sendRaw: SendRaw,
  name: string,
  data: Record<string, unknown>,
): void {
  const envelope: SystemEventEnvelope = {
    source: [],
    event: `$${name}`,
    data,
  };
  sendRaw(JSON.stringify(envelope));
}

export function setupSystemEvents(sendRaw: SendRaw): () => void {
  const onHashChange = (e: HashChangeEvent) => {
    let previousHash = '';
    try {
      previousHash = new URL(e.oldURL).hash;
    } catch {
      previousHash = '';
    }
    sendSystemEvent(sendRaw, 'hashchange', {
      hash: window.location.hash,
      previousHash,
      cause: 'user',
    });
  };

  window.addEventListener('hashchange', onHashChange);

  return () => {
    window.removeEventListener('hashchange', onHashChange);
  };
}
