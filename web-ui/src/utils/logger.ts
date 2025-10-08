/* eslint-disable no-console */
/**
 * Logger utility that only logs messages in development mode or when debug parameter is present
 */

// Check if we're in development mode
const isDevelopment = process.env.NODE_ENV === "development";

// Check if debug parameter is in URL
const hasDebugParam = (): boolean => {
  if (typeof window !== "undefined") {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.has("debug");
  }
  return false;
};

// Only log if in development mode or debug param is present
const shouldLog = (): boolean => isDevelopment || hasDebugParam();

const logger = {
  log: (...args: unknown[]): void => {
    if (shouldLog()) {
      console.log(...args);
    }
  },

  warn: (...args: unknown[]): void => {
    if (shouldLog()) {
      console.warn(...args);
    }
  },

  error: (...args: unknown[]): void => {
    // Always log errors regardless of environment
    console.error(...args);
  },

  info: (...args: unknown[]): void => {
    if (shouldLog()) {
      console.info(...args);
    }
  },
};

export default logger;
