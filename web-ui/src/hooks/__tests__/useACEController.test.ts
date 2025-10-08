import { renderHook, act } from "@testing-library/react";
import useACEController from "../useACEController";
import WS from "jest-websocket-mock";
import pcmToWav from "../../utils/pcmToWav";
import extractWavSampleRate from "../../utils/extractWavSampleRate";

describe("useACEController", () => {
  let server: WS;
  const url = "ws://localhost:1234";

  beforeEach(() => {
    server = new WS(url);
  });

  afterEach(() => {
    WS.clean();
  });

  test("connects to WebSocket server", async () => {
    const onError = jest.fn();
    const { result } = renderHook(() =>
      useACEController({
        url,
        onError,
        onAudioChunk: jest.fn(),
        onTTS: jest.fn(),
        onASR: jest.fn(),
      })
    );

    act(() => {
      result.current.connect();
    });

    await server.connected;
    expect(result.current.connectionStatus).toBe("connected");
  });

  test("handles audio chunks", async () => {
    const onAudioChunk = jest.fn();
    const { result } = renderHook(() =>
      useACEController({
        url,
        onError: jest.fn(),
        onAudioChunk,
        onTTS: jest.fn(),
        onASR: jest.fn(),
      })
    );

    // Connect to the WebSocket server first
    act(() => {
      result.current.connect();
    });

    await server.connected;

    // Create sample audio data
    const audioData = new Int16Array([1, 2, 3]);
    const wavBuffer = pcmToWav(audioData.buffer, 16_000);

    server.send(wavBuffer);

    // Wait for async operations to complete
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(onAudioChunk).toHaveBeenCalled();
  });

  test("sends audio chunk as WAV through WebSocket", async () => {
    const { result } = renderHook(() =>
      useACEController({
        url,
        onError: jest.fn(),
        onAudioChunk: jest.fn(),
        onTTS: jest.fn(),
        onASR: jest.fn(),
      })
    );

    // Connect to the WebSocket server first
    act(() => {
      result.current.connect();
    });

    await server.connected;

    // Create sample audio data and parameters
    const sampleRate = 16000;
    const numChannels = 1;
    const audioData = new Int16Array([1, 2, 3, 4, 5]);

    // Send the audio chunk
    act(() => {
      result.current.sendAudioChunk(audioData.buffer, sampleRate, numChannels);
    });

    // Wait for the message to be sent to the server
    const receivedData = (await server.nextMessage) as ArrayBuffer;

    // Verify the received data is a valid WAV file with the expected sample rate
    expect(receivedData).toBeInstanceOf(ArrayBuffer);
    const detectedSampleRate = extractWavSampleRate(receivedData);
    expect(detectedSampleRate).toBe(sampleRate);
  });
});
