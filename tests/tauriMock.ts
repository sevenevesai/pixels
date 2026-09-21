import { expect, type Page } from '@playwright/test';

interface Entry {
  name: string;
  isFile: boolean;
  isDirectory: boolean;
  isSymlink: boolean;
}

interface MockOptions {
  savedColor?: string;
  readDelay?: number;
  thumbnailDelay?: number;
  settingDelay?: number;
  failRead?: string;
  failSave?: boolean;
  listenerDelay?: number;
  batchListenerDelay?: number;
}

interface NativeMock {
  emit: (event: string, payload: unknown) => void;
  calls: Array<{ command: string; args: Record<string, any> }>;
  dialogs: string[];
  tree: Record<string, Entry[]>;
  finishBatch: (cancelled?: boolean) => void;
  listenerCount: (event: string) => number;
  releaseWrites: () => void;
  holdWrites: boolean;
}

declare global {
  interface Window {
    nativeMock: NativeMock;
  }
}

// Exercise real React components and Tauri JS APIs; native IO is replaced at the IPC boundary.
export async function mockTauri(page: Page, options: MockOptions = {}) {
  await page.addInitScript((options: MockOptions) => {
    const file = (name: string): Entry => ({ name, isFile: true, isDirectory: false, isSymlink: false });
    const dir = (name: string): Entry => ({ name, isFile: false, isDirectory: true, isSymlink: false });
    const callbacks = new Map<number, (event: unknown) => void>();
    const listeners = new Map<number, { event: string; handler: number }>();
    let nextId = 1;
    const normalize = (path: string) => path.replace(/\\/g, '/').replace(/\/$/, '');
    const pause = (ms = 0) => new Promise(resolve => setTimeout(resolve, ms));
    const png = Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII='), c => c.charCodeAt(0));
    const mock: NativeMock = {
      calls: [], dialogs: [], holdWrites: false,
      releaseWrites: () => {}, finishBatch: () => {},
      tree: {
        'C:/Art': [file('root.png'), dir('characters'), dir('props'), dir('.pixels'),
          { ...dir('loop'), isSymlink: true }, file('notes.txt'),
          { ...file('linked.png'), isSymlink: true }],
        'C:/Art/characters': [file('sprite.PNG'), dir('idle'), dir('.pixels')],
        'C:/Art/characters/idle': [file('frame.webp')],
        'C:/Art/props': [file('sprite.PNG')],
        'C:/Other': [file('other.jpg')],
        'C:/NestedOnly': [dir('children')],
        'C:/NestedOnly/children': [file('nested.png')],
        'C:/Empty': [],
      },
      emit(event, payload) {
        for (const [id, listener] of listeners) {
          if (listener.event === event) callbacks.get(listener.handler)?.({ event, id, payload });
        }
      },
      listenerCount: event => [...listeners.values()].filter(l => l.event === event).length,
    };
    window.nativeMock = mock;
    if (options.savedColor && !localStorage.getItem('outline_color')) {
      localStorage.setItem('outline_color', options.savedColor);
    }
    Object.assign(window, {
      __TAURI_EVENT_PLUGIN_INTERNALS__: {
        unregisterListener: (_event: string, id: number) => listeners.delete(id),
      },
      __TAURI_INTERNALS__: {
        metadata: { currentWindow: { label: 'main' }, currentWebview: { label: 'main' } },
        transformCallback(callback: (event: unknown) => void) {
          const id = nextId++;
          callbacks.set(id, callback);
          return id;
        },
        async invoke(command: string, args: Record<string, any> = {}) {
          mock.calls.push({ command, args });
          switch (command) {
            case 'plugin:event|listen': {
              await pause(args.event.startsWith('batch-') ? options.batchListenerDelay : options.listenerDelay);
              const id = nextId++;
              listeners.set(id, { event: args.event, handler: args.handler });
              return id;
            }
            case 'plugin:event|unlisten': return listeners.delete(args.eventId);
            case 'plugin:dialog|open': return mock.dialogs.shift() || null;
            case 'plugin:fs|stat': {
              const isDirectory = normalize(args.path) in mock.tree;
              return { isDirectory, isFile: !isDirectory };
            }
            case 'plugin:fs|read_dir': {
              await pause(options.readDelay);
              if (normalize(args.path) === options.failRead) throw new Error('Access denied');
              const entries = mock.tree[normalize(args.path)];
              if (!entries) throw new Error(`Unexpected directory: ${args.path}`);
              return entries;
            }
            case 'plugin:fs|read_file':
              await pause(options.thumbnailDelay);
              return png;
            case 'get_app_setting': {
              const value = localStorage.getItem(args.key);
              await pause(options.settingDelay);
              return value;
            }
            case 'set_app_setting':
              if (options.failSave) throw new Error('Disk is read-only');
              if (mock.holdWrites) await new Promise<void>(resolve => { mock.releaseWrites = resolve; });
              localStorage.setItem(args.key, args.value);
              return;
            case 'init_workspace_command': return;
            case 'batch_has_manifest_command': return false;
            case 'detect_scale_command':
              return { detected_scale: 1, is_ai_upscaled: false, dimensions: [32, 32], estimated_native_size: [32, 32] };
            case 'detect_outline_command': return { has_outline: false };
            case 'downscale_preview_command':
            case 'generate_preview_command': return png;
            case 'batch_process_command':
              return new Promise<void>(resolve => {
                mock.emit('batch-progress', { index: 0, total: args.paths.length, current_file: args.paths[0], status: 'processing' });
                mock.finishBatch = (cancelled = false) => {
                  mock.emit('batch-complete', { processed: cancelled ? 1 : args.paths.length, failed: 0, cancelled });
                  resolve();
                };
              });
            case 'batch_cancel_command': return mock.finishBatch(true);
            case 'batch_revert_command': return { reverted: 4, failed: 0, errors: [] };
            case 'plugin:updater|check': return null;
            default: throw new Error(`Unexpected command: ${command}`);
          }
        },
      },
    });
  }, options);
  await page.goto('/');
  await expect.poll(() => page.evaluate(() => window.nativeMock.listenerCount('tauri://drag-drop'))).toBe(1);
}

export async function drop(page: Page, paths: string[]) {
  await page.evaluate(paths => {
    window.nativeMock.emit('tauri://drag-drop', { paths, position: { x: 200, y: 200 } });
  }, paths);
}

export async function openFolder(page: Page, path = 'C:\\Art') {
  await page.evaluate(path => window.nativeMock.dialogs.push(path), path);
  await page.getByRole('button', { name: 'Open Folder', exact: true }).first().click();
  await expect(page.getByLabel('Include subfolders')).toBeVisible();
  await expect(page.getByText('Scanning...', { exact: true })).toHaveCount(0);
}
