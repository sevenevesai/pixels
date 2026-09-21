import { readDir } from '@tauri-apps/plugin-fs';

export const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'bmp', 'webp'];

export interface FolderImage {
  name: string;
  relativePath: string;
  fullPath: string;
  thumbnail?: string;
}

export function isImagePath(path: string): boolean {
  return IMAGE_EXTENSIONS.includes(path.split('.').pop()?.toLowerCase() || '');
}

export function relativeImagePath(path: string, folderPath: string): string {
  const normalized = path.replace(/\\/g, '/');
  const root = folderPath.replace(/\\/g, '/').replace(/\/$/, '') + '/';
  return normalized.startsWith(root) ? normalized.slice(root.length) : normalized;
}

export async function scanFolderImages(
  folderPath: string,
  includeSubfolders: boolean,
  isCurrent: () => boolean = () => true,
): Promise<FolderImage[]> {
  const images: FolderImage[] = [];
  const separator = folderPath.includes('\\') ? '\\' : '/';
  const pending = [{ fullPath: folderPath, relativePath: '' }];

  while (pending.length > 0 && isCurrent()) {
    const directory = pending.pop()!;
    let entries;
    try {
      entries = await readDir(directory.fullPath);
    } catch (error) {
      throw new Error(`Could not read ${directory.fullPath}: ${error}`);
    }
    if (!isCurrent()) return [];

    for (const entry of entries) {
      // Never process backups or follow links out of the selected folder (or into a loop).
      if (entry.isSymlink || entry.name.toLowerCase() === '.pixels') continue;
      const fullPath = directory.fullPath.replace(/[\\/]$/, '') + separator + entry.name;
      const relativePath = directory.relativePath + entry.name;
      if (entry.isDirectory && includeSubfolders) {
        pending.push({ fullPath, relativePath: relativePath + '/' });
      } else if (entry.isFile && isImagePath(entry.name)) {
        images.push({ name: entry.name, relativePath, fullPath });
      }
    }
  }

  return images.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
}
