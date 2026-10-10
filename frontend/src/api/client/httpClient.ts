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

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${env.apiBaseUrl}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const token = session.getToken();

  // Receipt uploads (POST /expenses) are the one endpoint that isn't JSON.
  // For FormData we must NOT set Content-Type ourselves — the browser needs
  // to add the multipart boundary, which it only does when it picks the
  // header itself. Setting it manually breaks the upload.
  const isFormData = options.body instanceof FormData;

  try {
    const response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        // Django REST's TokenAuthentication expects "Token <key>", not "Bearer".
        ...(token ? { Authorization: `Token ${token}` } : {}),
        ...options.headers,
      },
      body: isFormData ? (options.body as FormData) : options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal ?? controller.signal,
    });

    if (response.status === 401) {
      onUnauthorized?.();
      throw new ApiRequestError(toApiError('not_authenticated', 'Your session has expired. Please log in again.'));
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
      throw new ApiRequestError(toApiError('timeout', 'The request took too long. Please try again.'));
    }
    throw new ApiRequestError(toApiError('network_error', 'Could not reach the server. Check your connection.'));
  } finally {
    clearTimeout(timeout);
  }
}
