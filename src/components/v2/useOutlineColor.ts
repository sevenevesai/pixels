import { useCallback, useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { DEFAULT_SETTINGS } from './types';

const SETTING_KEY = 'outline_color';
const isColor = (value: string): boolean => /^#[0-9a-f]{6}$/i.test(value);

export function useOutlineColor() {
  const [outlineColor, setColor] = useState(DEFAULT_SETTINGS.outlineColor);
  const [error, setError] = useState<string | null>(null);
  const revision = useRef(0);
  const pendingWrite = useRef(Promise.resolve());

  useEffect(() => {
    let cancelled = false;
    invoke<string | null>('get_app_setting', { key: SETTING_KEY }).then(value => {
      if (!cancelled && revision.current === 0 && value && isColor(value)) {
        setColor(value);
      }
    }).catch(err => {
      if (!cancelled && revision.current === 0) {
        setError(`Could not load the saved outline color: ${err}`);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const setOutlineColor = useCallback((color: string) => {
    if (!isColor(color)) return;
    const currentRevision = ++revision.current;
    setColor(color);
    setError(null);
    // Serialize picker changes so the last selection is also the last database write.
    pendingWrite.current = pendingWrite.current.then(() =>
      invoke<void>('set_app_setting', { key: SETTING_KEY, value: color })
    ).catch(err => {
      if (revision.current === currentRevision) {
        setError(`Could not remember the outline color: ${err}`);
      }
    });
  }, []);

  return { outlineColor, setOutlineColor, error };
}
