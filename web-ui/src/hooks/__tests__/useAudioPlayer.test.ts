import { renderHook } from "@testing-library/react";
import useAudioPlayer from "../useAudioPlayer";

// We don't need to duplicate the MockAudioBuffer class here as it's already in setupTests.ts

describe("useAudioPlayer", () => {
  // Mock bufferSource for specific test needs
  const mockBufferSource = {
    connect: jest.fn(),
    start: jest.fn(),
  };

  // Store the original implementation
  const originalCreateBufferSource =
    global.AudioContext.prototype.createBufferSource;

  // Create a reusable audio buffer
  let audioBuffer: AudioBuffer;
  let shortAudioBuffer: AudioBuffer;

  beforeAll(() => {
    // Override the createBufferSource method for this test suite
    global.AudioContext.prototype.createBufferSource = jest
      .fn()
      .mockReturnValue(mockBufferSource);

    // Create the reusable audio buffers using the globally mocked AudioBuffer
    audioBuffer = new AudioBuffer({
      length: 40000,
      sampleRate: 44100,
      numberOfChannels: 1,
    });

    shortAudioBuffer = new AudioBuffer({
      length: 100,
      sampleRate: 44100,
      numberOfChannels: 1,
    });
  });

  afterAll(() => {
    // Restore the original implementation after tests
    global.AudioContext.prototype.createBufferSource =
      originalCreateBufferSource;
  });

  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();
  });

  test("plays audio chunks", () => {
    const { result } = renderHook(() => useAudioPlayer());

    result.current.play(audioBuffer);

    expect(mockBufferSource.start).toHaveBeenCalled();
  });

  test("doesn't start playing audio chunks until the existing chunks are long enough", () => {
    const { result } = renderHook(() => useAudioPlayer());

    result.current.play(shortAudioBuffer);

    expect(mockBufferSource.start).not.toHaveBeenCalled();

    // Add many chunks of audio, which makes the total buffered audio long enough to start
    for (let i = 0; i < 1000; i++) {
      result.current.play(shortAudioBuffer);
    }

    expect(mockBufferSource.start).toHaveBeenCalled();
  });
});
