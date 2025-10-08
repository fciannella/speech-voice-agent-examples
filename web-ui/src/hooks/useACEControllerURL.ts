import { useRef } from "react";

const DEFAULT_WEBSOCKET_BASE_URL = "ws://localhost:8100/ws/";
const STREAM_ID = Math.random().toString(36).substring(2, 15);

interface Params {
  onError: (error: Error) => void;
}

interface Output {
  baseUrl: string;
  baseUrlWithStreamID: string;
}

/**
 * Get the ACE Controller URL from the query parameter or use the default
 * @returns The ACE Controller URL
 */
export default function useACEControllerURL({ onError }: Params): Output {
  const urlRef = useRef<string>(null);
  if (!urlRef.current) {
    const params = new URLSearchParams(window.location.search);
    const websocketBaseUrl = params.get("ace-controller-url");
    if (websocketBaseUrl) {
      if (isValidWebsocketURL(websocketBaseUrl)) {
        urlRef.current = websocketBaseUrl;
      } else {
        onError(
          new Error(
            `Invalid websocket URL: "${websocketBaseUrl}", using default ${DEFAULT_WEBSOCKET_BASE_URL} instead`
          )
        );
        urlRef.current = DEFAULT_WEBSOCKET_BASE_URL;
      }
    } else {
      urlRef.current = DEFAULT_WEBSOCKET_BASE_URL;
    }
  }

  return {
    baseUrl: urlRef.current!,
    baseUrlWithStreamID: new URL(STREAM_ID, urlRef.current!).toString(),
  };
}

/**
 * Check if the URL is a valid websocket URL
 * @param url - The URL to check
 * @returns True if the URL is a valid websocket URL, false otherwise
 */
function isValidWebsocketURL(url: string): boolean {
  try {
    const parsedUrl = new URL(STREAM_ID, url);
    return parsedUrl.protocol === "ws:" || parsedUrl.protocol === "wss:";
  } catch {
    return false;
  }
}
