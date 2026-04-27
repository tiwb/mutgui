import type { ViewPath } from './context';
import { resolveFromSources, type NamespacedSource } from './namespaced-registry';

export interface CommandContext {
  viewId: ViewPath;
}

export type MutguiCommand<Args extends object = Record<string, unknown>> = (
  args: Args,
  context: CommandContext,
) => void;

export interface CommandSource extends NamespacedSource {}

const sources: CommandSource[] = [];

export function registerCommands(source: CommandSource): void {
  sources.unshift(source);
}

export function resolveCommand(name: string): MutguiCommand | null {
  const hit = resolveFromSources(sources, name);
  return typeof hit === 'function' ? (hit as MutguiCommand) : null;
}
