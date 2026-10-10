export interface ApiError {
  code: string;
  message: string;
  field?: string;
}

export class ApiRequestError extends Error implements ApiError {
  code: string;
  field?: string;

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'ApiRequestError';
    this.code = error.code;
    this.field = error.field;
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}
