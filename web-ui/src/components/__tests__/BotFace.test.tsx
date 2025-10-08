import { render, screen } from "@testing-library/react";
import BotFace from "../BotFace";

describe("BotFace", () => {
  const mockAnalyser = {
    getFloatFrequencyData: jest.fn((array) => {
      array[10] = -100;
    }),
  };

  const mockAudioContext = {
    createAnalyser: jest.fn(() => mockAnalyser),
  };

  const mockAudioNode = {
    context: mockAudioContext,
    connect: jest.fn(),
  } as unknown as AudioNode;

  test("renders loading state when connecting", () => {
    render(
      <BotFace audioSource={mockAudioNode} connectionStatus="connecting" />
    );
    expect(screen.getByTestId("loading-indicator")).toBeInTheDocument();
  });

  test("renders disconnected icon when disconnected", () => {
    render(
      <BotFace audioSource={mockAudioNode} connectionStatus="disconnected" />
    );
    expect(
      screen.getByTitle("Enable microphone to connect")
    ).toBeInTheDocument();
  });

  test("renders emoji when connected", () => {
    render(
      <BotFace audioSource={mockAudioNode} connectionStatus="connected" />
    );
    expect(screen.getByText("🙂")).toBeInTheDocument();
  });
});
