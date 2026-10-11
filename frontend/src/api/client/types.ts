export interface ApiFieldError {
  field: string;
  code: string;
  message: string;
}

export interface ClubOption {
  slug: string;
  name: string;
  short: string;
  color: string;
}

export interface ApiError {
  code: string;
  message: string;
  field?: string | null;
  /** Present on `400 validation_error` — one entry per invalid field, so a
   * form can mark all of them at once instead of just the first. */
  errors?: ApiFieldError[];
  /** Present on `409 choose_club`: the clubs this login is valid in. */
  clubs?: ClubOption[];
}

export class ApiRequestError extends Error implements ApiError {
  code: string;
  field?: string | null;
  errors?: ApiFieldError[];
  clubs?: ClubOption[];

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'ApiRequestError';
    this.code = error.code;
    this.field = error.field;
    this.errors = error.errors;
    this.clubs = error.clubs;
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

/** The {count, next, previous, results} envelope every list endpoint uses. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
