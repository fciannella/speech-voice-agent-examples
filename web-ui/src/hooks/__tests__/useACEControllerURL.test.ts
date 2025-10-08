import { renderHook } from "@testing-library/react";
import useACEControllerURL from "../useACEControllerURL";

describe("useACEControllerURL", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    const mockLocation = new URL("http://localhost:3000");

    Object.defineProperty(window, "location", {
      writable: true,
      value: mockLocation,
    });
  });

  // Restore the original location after tests
  afterEach(() => {
    Object.defineProperty(window, "location", {
      writable: true,
      value: originalLocation,
    });
  });

  test("returns default URL when no query parameter is provided", () => {
    const onError = jest.fn();
    const { result } = renderHook(() => useACEControllerURL({ onError }));

    expect(result.current.baseUrl).toBe("ws://localhost:8100/ws/");
    expect(result.current.baseUrlWithStreamID).toMatch(
      /^ws:\/\/localhost:8100\/ws\/[a-z0-9]+$/
    );
    expect(onError).not.toHaveBeenCalled();
  });

  test("uses provided URL from query parameter when valid", () => {
    // Set up query parameter
    window.location.search = "?ace-controller-url=ws://example.com/websocket/";

    const onError = jest.fn();
    const { result } = renderHook(() => useACEControllerURL({ onError }));

    expect(result.current.baseUrl).toBe("ws://example.com/websocket/");
    expect(result.current.baseUrlWithStreamID).toMatch(
      /^ws:\/\/example\.com\/websocket\/[a-z0-9]+$/
    );
    expect(onError).not.toHaveBeenCalled();
  });

  test("uses wss protocol when provided", () => {
    // Set up query parameter with secure websocket
    window.location.search = "?ace-controller-url=wss://secure-example.com/ws/";

    const onError = jest.fn();
    const { result } = renderHook(() => useACEControllerURL({ onError }));

    expect(result.current.baseUrl).toBe("wss://secure-example.com/ws/");
    expect(result.current.baseUrlWithStreamID).toMatch(
      /^wss:\/\/secure-example\.com\/ws\/[a-z0-9]+$/
    );
    expect(onError).not.toHaveBeenCalled();
  });

  test("falls back to default URL when provided URL is invalid", () => {
    // Set up invalid query parameter
    window.location.search = "?ace-controller-url=http://invalid-protocol.com/";

    const onError = jest.fn();
    const { result } = renderHook(() => useACEControllerURL({ onError }));

    expect(result.current.baseUrl).toBe("ws://localhost:8100/ws/");
    expect(result.current.baseUrlWithStreamID).toMatch(
      /^ws:\/\/localhost:8100\/ws\/[a-z0-9]+$/
    );
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: expect.stringContaining("Invalid websocket URL"),
      })
    );
  });

  test("uses cached URL reference on subsequent renders", () => {
    const onError = jest.fn();

    // First render - should set the URL
    const { result, rerender } = renderHook(() =>
      useACEControllerURL({ onError })
    );
    const initialBaseUrl = result.current.baseUrl;
    const initialBaseUrlWithStreamID = result.current.baseUrlWithStreamID;

    // Change the URL in the query parameter, but it shouldn't affect the result
    window.location.search = "?ace-controller-url=ws://different-url.com/ws/";

    // Re-render the hook
    rerender();

    // Verify that the hook uses the cached value and doesn't update
    expect(result.current.baseUrl).toBe(initialBaseUrl);
    expect(result.current.baseUrlWithStreamID).toBe(initialBaseUrlWithStreamID);
    expect(onError).not.toHaveBeenCalled();
  });
});
