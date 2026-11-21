import { test, expect, type Page } from '@playwright/test';
import { mockTauri, drop, openFolder } from './tauriMock';

async function pickColor(page: Page, color: string) {
  await page.getByLabel('Outline color').evaluate((element: HTMLInputElement, color) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, color);
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, color);
}

test('folder scope includes nested assets, distinguishes duplicate names, and excludes caches and links', async ({ page }) => {
  await mockTauri(page);
  await openFolder(page);
  await expect(page.getByLabel('Include subfolders')).not.toBeChecked();
  await expect(page.locator('.nav-name')).toHaveText(['root.png']);

  await page.getByLabel('Include subfolders').check();
  await expect(page.locator('.nav-name')).toHaveText([
    'characters/idle/frame.webp', 'characters/sprite.PNG', 'props/sprite.PNG', 'root.png',
  ]);
  const reads = await page.evaluate(() => window.nativeMock.calls
    .filter(c => c.command === 'plugin:fs|read_dir').map(c => c.args.path));
  expect(reads.every(path => !/\.pixels|loop/.test(path))).toBe(true);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.setViewportSize({ width: 1000, height: 700 });
  await expect(page.getByLabel('Include subfolders')).toBeInViewport();
  await expect(page.getByRole('button', { name: 'Bulk Process', exact: true })).toBeInViewport();
  await page.screenshot({ path: test.info().outputPath('subfolders.png') });

  await page.getByLabel('Include subfolders').uncheck();
  await expect(page.locator('.nav-name')).toHaveText(['root.png']);
});

test('bulk receives exactly the selected scope and prevents navigation until cancellation completes', async ({ page }) => {
  await mockTauri(page, { batchListenerDelay: 30 });
  await openFolder(page);
  await page.getByLabel('Include subfolders').check();
  await expect(page.locator('.nav-name')).toHaveCount(4);
  await page.getByRole('button', { name: 'Bulk Process', exact: true }).click();
  await expect(page.getByText('This folder and all subfolders', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Apply to All', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.nativeMock.calls
    .find(c => c.command === 'batch_process_command')?.args.paths)).toEqual([
      'C:\\Art\\characters\\idle\\frame.webp', 'C:\\Art\\characters\\sprite.PNG',
      'C:\\Art\\props\\sprite.PNG', 'C:\\Art\\root.png',
    ]);
  await expect(page.getByLabel('Include subfolders')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Open Folder', exact: true })).toBeDisabled();
  await expect(page.locator('.bulk-progress-file')).toHaveText('characters/idle/frame.webp');
  await drop(page, ['C:\\Other']);
  await expect(page.getByRole('alert')).toContainText('Wait for the bulk operation');
  await expect(page.locator('.workspace-path')).toHaveText('Art');

  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.locator('.bulk-result-message')).toContainText('Cancelled');
  await expect(page.locator('.nav-name')).toHaveCount(4);
  await page.getByRole('button', { name: 'Revert All', exact: true }).first().click();
  await expect(page.getByText('Reverted 4 images to originals')).toBeVisible();
  await expect(page.locator('.nav-name')).toHaveCount(4);

  await page.getByLabel('Include subfolders').uncheck();
  await expect(page.locator('.nav-name')).toHaveText(['root.png']);
  await page.getByRole('button', { name: 'Bulk Process', exact: true }).click();
  await expect(page.getByText('This folder only', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Apply to All', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.nativeMock.calls
    .filter(c => c.command === 'batch_process_command').at(-1)?.args.paths)).toEqual(['C:\\Art\\root.png']);
  await page.evaluate(() => window.nativeMock.finishBatch());
  await expect(page.locator('.bulk-result-message')).toHaveText('Done — 1 images processed');
});

test('cancelling while batch listeners register never starts a bulk job', async ({ page }) => {
  await mockTauri(page, { batchListenerDelay: 700 });
  await openFolder(page);
  await page.getByRole('button', { name: 'Bulk Process', exact: true }).click();
  await page.getByRole('button', { name: 'Apply to All', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.locator('.bulk-result-message')).toHaveText('Cancelled — 0 processed, 0 failed');
  const jobs = await page.evaluate(() => window.nativeMock.calls.filter(c => c.command === 'batch_process_command'));
  expect(jobs).toHaveLength(0);
  await expect(page.getByLabel('Include subfolders')).toBeEnabled();
});

test('native drops open folders and images, show hover feedback, and reject unsupported drops', async ({ page }) => {
  await mockTauri(page);
  await page.evaluate(() => window.nativeMock.emit('tauri://drag-enter', { paths: ['C:\\Art'], position: { x: 0, y: 0 } }));
  await expect(page.getByRole('status')).toHaveText('Drop an image or folder to open');
  await page.evaluate(() => window.nativeMock.emit('tauri://drag-leave', {}));
  await expect(page.getByRole('status')).toHaveCount(0);
  await drop(page, ['C:\\Art']);
  await expect(page.locator('.nav-name')).toHaveText(['root.png']);
  await drop(page, ['C:\\Art\\characters\\sprite.PNG']);
  await expect(page.getByRole('heading', { name: 'sprite.PNG', exact: true })).toBeVisible();
  await expect(page.locator('.folder-nav')).toHaveCount(0);
  await drop(page, ['C:\\notes.txt']);
  await expect(page.getByRole('alert')).toContainText('PNG, JPG, JPEG, BMP, or WebP');
  await expect(page.getByRole('heading', { name: 'sprite.PNG', exact: true })).toBeVisible();
  await drop(page, ['C:\\Art', 'C:\\Other']);
  await expect(page.getByRole('alert')).toContainText('one image or one folder');

  await page.evaluate(() => window.nativeMock.dialogs.push('C:\\Other\\other.jpg'));
  await page.getByRole('button', { name: 'Open Image', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'other.jpg', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.nativeMock.listenerCount('tauri://drag-drop'))).toBe(1);
});

test('switching scope or closing a folder ignores stale scans and thumbnail selections', async ({ page }) => {
  await mockTauri(page, { readDelay: 150, thumbnailDelay: 250 });
  await openFolder(page);
  await page.getByLabel('Include subfolders').check();
  await page.getByLabel('Include subfolders').uncheck();
  await expect(page.locator('.nav-name')).toHaveText(['root.png']);
  await page.getByRole('button', { name: 'root.png', exact: true }).click();
  await drop(page, ['C:\\Other']);
  await expect(page.locator('.nav-name')).toHaveText(['other.jpg']);
  await expect(page.locator('.editor-title')).toHaveCount(0);
  await page.getByLabel('Include subfolders').check();
  await page.locator('.workspace-path-bar').getByRole('button', { name: 'Close', exact: true }).click();
  // Give superseded filesystem work time to finish; it must not reopen the workspace.
  await page.waitForTimeout(400);
  await expect(page.getByRole('heading', { name: 'No Workspace Open' })).toBeVisible();
  await expect(page.locator('.folder-nav')).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('empty roots can include child images and unreadable subfolders cannot create a partial bulk job', async ({ page }) => {
  await mockTauri(page, { failRead: 'C:/Art/props' });
  await openFolder(page, 'C:\\NestedOnly');
  await expect(page.getByRole('button', { name: 'Bulk Process', exact: true })).toBeDisabled();
  await page.getByLabel('Include subfolders').check();
  await expect(page.locator('.nav-name')).toHaveText(['children/nested.png']);
  await drop(page, ['C:\\Art']);
  await expect(page.getByRole('alert')).toContainText('Access denied');
  await expect(page.locator('.nav-name')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Bulk Process', exact: true })).toBeDisabled();
  await page.getByLabel('Include subfolders').uncheck();
  await expect(page.locator('.nav-name')).toHaveText(['root.png']);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('outline color is shared across editor and bulk jobs and restored after reload', async ({ page }) => {
  await mockTauri(page, { savedColor: '#123456' });
  await drop(page, ['C:\\Art\\root.png']);
  await page.getByRole('button', { name: /Skip/ }).click();
  await expect(page.getByLabel('Outline color')).toHaveValue('#123456');
  await pickColor(page, '#aabbcc');
  await expect.poll(() => page.evaluate(() => localStorage.getItem('outline_color'))).toBe('#aabbcc');
  await expect.poll(() => page.evaluate(() => window.nativeMock.calls
    .filter(c => c.command === 'generate_preview_command').at(-1)?.args.outlineSettings.color)).toEqual([170, 187, 204, 255]);

  await openFolder(page);
  await page.getByRole('button', { name: 'Bulk Process', exact: true }).click();
  await expect(page.getByLabel('Outline color')).toHaveValue('#aabbcc');
  await pickColor(page, '#445566');
  await page.getByRole('button', { name: 'Apply to All', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.nativeMock.calls
    .find(c => c.command === 'batch_process_command')?.args.outlineSettings.color)).toEqual([68, 85, 102, 255]);
  await page.evaluate(() => window.nativeMock.finishBatch());
  await page.reload();
  await openFolder(page);
  await page.getByRole('button', { name: 'Bulk Process', exact: true }).click();
  await expect(page.getByLabel('Outline color')).toHaveValue('#445566');
});

test('a late settings read cannot overwrite a new color and rapid writes keep the final selection', async ({ page }) => {
  await mockTauri(page, { savedColor: '#123456', settingDelay: 1200 });
  await openFolder(page);
  await page.getByRole('button', { name: 'Bulk Process', exact: true }).click();
  await page.evaluate(() => { window.nativeMock.holdWrites = true; });
  await pickColor(page, '#abcdef');
  await pickColor(page, '#fedcba');
  await page.waitForTimeout(1300);
  await expect(page.getByLabel('Outline color')).toHaveValue('#fedcba');
  const writes = await page.evaluate(() => window.nativeMock.calls.filter(c => c.command === 'set_app_setting'));
  expect(writes).toHaveLength(1);
  await page.evaluate(() => { window.nativeMock.holdWrites = false; window.nativeMock.releaseWrites(); });
  await expect.poll(() => page.evaluate(() => localStorage.getItem('outline_color'))).toBe('#fedcba');
});

test('invalid saved colors fall back to the default and failed saves are visible', async ({ page }) => {
  await mockTauri(page, { savedColor: 'invalid', failSave: true });
  await openFolder(page);
  await page.getByRole('button', { name: 'Bulk Process', exact: true }).click();
  await expect(page.getByLabel('Outline color')).toHaveValue('#110602');
  await pickColor(page, '#112233');
  await expect(page.getByLabel('Outline color')).toHaveValue('#112233');
  await expect(page.getByRole('alert')).toContainText('Could not remember the outline color');
});

const NUDGE_TEXT = 'Found a bug or want a feature? Tell me on Discord.';
const launchCount = (page: Page) => page.evaluate(() => localStorage.getItem('launch_count'));
const openedUrls = (page: Page) => page.evaluate(() => window.nativeMock.calls
  .filter(c => c.command === 'plugin:opener|open_url').map(c => c.args.url));

test('the permanent Discord community link opens the app redirect', async ({ page }) => {
  await mockTauri(page);
  const link = page.getByRole('link', { name: 'Discord community', exact: true });
  await expect(link).toBeVisible();
  await link.click();
  expect(await openedUrls(page)).toEqual(['https://seveneves.ai/discord/?from=pixels-app']);
});

test('the Discord nudge stays hidden on launches 1 and 2, then appears once on launch 3 and never returns', async ({ page }) => {
  await mockTauri(page);
  await expect.poll(() => launchCount(page)).toBe('1');
  await page.waitForTimeout(3600);
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);

  await page.reload();
  await expect.poll(() => launchCount(page)).toBe('2');
  await page.waitForTimeout(3600);
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);

  await page.reload();
  await expect.poll(() => launchCount(page)).toBe('3');
  await expect(page.getByText(NUDGE_TEXT)).toBeVisible({ timeout: 6000 });
  expect(await page.evaluate(() => localStorage.getItem('discord_nudge_seen'))).toBe('1');
  await expect(page.getByRole('button', { name: 'Join', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Close', exact: true })).toBeVisible();
  // It hides by itself.
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0, { timeout: 14000 });
  expect(await openedUrls(page)).toEqual([]);

  await page.reload();
  await expect.poll(() => launchCount(page)).toBe('4');
  await page.waitForTimeout(3600);
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);
});

test('Join opens the nudge redirect and closing the card keeps it from returning', async ({ page }) => {
  await mockTauri(page, { settings: { launch_count: '2' } });
  await expect(page.getByText(NUDGE_TEXT)).toBeVisible({ timeout: 6000 });
  await page.getByRole('button', { name: 'Join', exact: true }).click();
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);
  expect(await openedUrls(page)).toEqual(['https://seveneves.ai/discord/?from=pixels-nudge']);
  await page.reload();
  await page.waitForTimeout(3600);
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);
});

test('closing the Discord nudge hides it without opening anything', async ({ page }) => {
  await mockTauri(page, { settings: { launch_count: '2' } });
  await expect(page.getByText(NUDGE_TEXT)).toBeVisible({ timeout: 6000 });
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);
  expect(await openedUrls(page)).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem('discord_nudge_seen'))).toBe('1');
});

test('the Discord nudge fails closed when settings cannot be read or written', async ({ page }) => {
  await mockTauri(page, { settings: { launch_count: '5' }, failSettingsRead: true });
  await page.waitForTimeout(3600);
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Discord community', exact: true })).toBeVisible();
});

test('the Discord nudge is not shown when its seen flag cannot be saved', async ({ page }) => {
  await mockTauri(page, { settings: { launch_count: '5' }, failSave: true });
  await page.waitForTimeout(3600);
  await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0);
});
