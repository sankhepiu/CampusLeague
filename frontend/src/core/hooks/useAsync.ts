import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiRequestError, type ApiError } from '../../api/client';

export type AsyncState<T> =
  | { status: 'idle'; data: null; error: null }
  | { status: 'loading'; data: null; error: null }
  | { status: 'success'; data: T; error: null }
  | { status: 'error'; data: null; error: ApiError };

export interface UseAsyncOptions {
  /** When false, the fetch never fires and state stays 'idle' — for data
   * that's only relevant/authorized behind a condition (a role check, a
   * toggle) so it shouldn't be requested for every viewer. Defaults true. */
  enabled?: boolean;
}

/** Runs an async function on mount (or when `deps` change) and tracks
 * loading/success/error state with a normalized ApiError shape. */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: ReadonlyArray<unknown> = [],
  options: UseAsyncOptions = {},
): AsyncState<T> & { reload: () => void } {
  const { enabled = true } = options;
  const [state, setState] = useState<AsyncState<T>>({ status: 'idle', data: null, error: null });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setState({ status: 'idle', data: null, error: null });
      return;
    }

    let cancelled = false;
    setState({ status: 'loading', data: null, error: null });

    fnRef.current()
      .then((data) => {
        if (!cancelled) setState({ status: 'success', data, error: null });
      })
      .catch((err) => {
        if (cancelled) return;
        const apiError: ApiError =
          err instanceof ApiRequestError ? err : { code: 'UNKNOWN', message: 'Something went wrong.' };
        setState({ status: 'error', data: null, error: apiError });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadToken, enabled]);

  const reload = useCallback(() => setReloadToken((n) => n + 1), []);

  return { ...state, reload };
}
