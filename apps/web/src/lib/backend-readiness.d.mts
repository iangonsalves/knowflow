export const BACKEND_STARTUP_MAX_ATTEMPTS: number;
export const BACKEND_STARTUP_RETRY_DELAY_MS: number;
export const BACKEND_STARTUP_REQUEST_TIMEOUT_MS: number;
export function shouldRetryBackendStartup(attempt: number): boolean;
