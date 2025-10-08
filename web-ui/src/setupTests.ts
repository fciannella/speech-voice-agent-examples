import "@testing-library/jest-dom";

// Mock AudioBuffer since it's not available in JSDOM
class MockAudioBuffer {
  length: number;
  sampleRate: number;
  numberOfChannels: number;
  private channelData: Float32Array[];

  constructor(options: {
    length: number;
    sampleRate: number;
    numberOfChannels: number;
  }) {
    this.length = options.length;
    this.sampleRate = options.sampleRate;
    this.numberOfChannels = options.numberOfChannels;
    this.channelData = Array(options.numberOfChannels)
      .fill(0)
      .map(() => new Float32Array(options.length));
  }

  getChannelData(channel: number): Float32Array {
    return this.channelData[channel];
  }
}

// Replace global AudioBuffer with our mock
global.AudioBuffer = MockAudioBuffer as unknown as typeof AudioBuffer;

// Mock the AudioContext and related APIs
class MockAudioContext {
  sampleRate: number = 44100;

  createBufferSource() {
    return {
      connect: jest.fn(),
      start: jest.fn(),
    };
  }

  createBuffer(numChannels: number, length: number, sampleRate: number) {
    return new MockAudioBuffer({
      numberOfChannels: numChannels,
      length,
      sampleRate,
    }) as unknown as AudioBuffer;
  }

  decodeAudioData() {
    return new MockAudioBuffer({
      numberOfChannels: 1,
      length: 3,
      sampleRate: this.sampleRate,
    }) as unknown as AudioBuffer;
  }
}

global.AudioContext = MockAudioContext as unknown as typeof AudioContext;

// Mock requestAnimationFrame
global.requestAnimationFrame = (callback: FrameRequestCallback): number => {
  return setTimeout(callback, 0) as unknown as number;
};

// Mock cancelAnimationFrame
global.cancelAnimationFrame = (id: number): void => {
  clearTimeout(id);
};
