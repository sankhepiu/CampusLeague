import { env } from '../../core/config/env';
import { session } from './session';
import { ApiRequestError, type ApiError, type RequestOptions } from './types';

const REQUEST_TIMEOUT_MS = 15_000;

/** Callback invoked whenever a request comes back 401, so the auth provider
 * can clear local state without every call site needing to know about it. */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function toApiError(code: string, message: string, field?: string): ApiError {
  return field ? { code, message, field } : { code, message };
}

async function parseErrorBody(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    if (body && typeof body.code === 'string' && typeof body.message === 'string') {
      return body as ApiError;
    }
  } catch {
    /* body wasn't JSON (or was empty) */
  }
  return toApiError(`HTTP_${response.status}`, response.statusText || 'Request failed');
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const token = session.getToken();

  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      method: options.method ?? 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal ?? controller.signal,
    });

    if (response.status === 401) {
      onUnauthorized?.();
      throw new ApiRequestError(toApiError('UNAUTHORIZED', 'Your session has expired. Please log in again.'));
    }

    if (!response.ok) {
      throw new ApiRequestError(await parseErrorBody(response));
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiRequestError) throw err;
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiRequestError(toApiError('TIMEOUT', 'The request took too long. Please try again.'));
    }
    throw new ApiRequestError(toApiError('NETWORK_ERROR', 'Could not reach the server. Check your connection.'));
  } finally {
    clearTimeout(timeout);
  }
}
