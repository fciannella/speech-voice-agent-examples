import { renderHook, act } from "@testing-library/react";
import useChatHistory from "../useChatHistory";

describe("useChatHistory", () => {
  test("should add chat entries", () => {
    const { result } = renderHook(() => useChatHistory());

    act(() => {
      result.current.add("Hello", "us");
    });

    expect(result.current.entries).toHaveLength(1);
    expect(result.current.entries[0]).toEqual({
      text: "Hello",
      author: "us",
    });
  });
});
