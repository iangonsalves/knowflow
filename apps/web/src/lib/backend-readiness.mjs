export const BACKEND_STARTUP_MAX_ATTEMPTS = 24;
export const BACKEND_STARTUP_RETRY_DELAY_MS = 5_000;
export const BACKEND_STARTUP_REQUEST_TIMEOUT_MS = 8_000;

export function shouldRetryBackendStartup(attempt) {
  return Number.isInteger(attempt) && attempt >= 0 && attempt < BACKEND_STARTUP_MAX_ATTEMPTS;
}
