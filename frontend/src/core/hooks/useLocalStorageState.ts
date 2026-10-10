import { useCallback, useState } from 'react';

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** useState that mirrors its value to localStorage, tolerating unavailable
 * storage. When `initial` is a plain object, a stored value is shallow-merged
 * onto it — so adding a new field to a persisted shape (e.g. Options) never
 * leaves existing users with that field `undefined` after an update. */
export function useLocalStorageState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return initial;
      const parsed = JSON.parse(raw) as T;
      return isPlainObject(initial) && isPlainObject(parsed) ? ({ ...initial, ...parsed } as T) : parsed;
    } catch {
      return initial;
    }
  });

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === 'function' ? (next as (prev: T) => T)(prev) : next;
        try {
          localStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          /* storage unavailable */
        }
        return resolved;
      });
    },
    [key],
  );

  return [value, set] as const;
}
