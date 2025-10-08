/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { useRef, useState } from "react";
import logger from "../utils/logger";
import extractWavSampleRate from "../utils/extractWavSampleRate";
import pcmToWav from "../utils/pcmToWav";

interface Params {
  url: string;
  onError: (error: Error) => void;
  onAudioChunk: (chunk: AudioBuffer) => void;
  onTTS: (transcript: string) => void;
  onASR: (transcript: string) => void;
}

interface Output {
  connectionStatus: ConnectionStatus;
  connect: () => void;
  sendAudioChunk: (
    chunk: ArrayBuffer,
    sampleRate: number,
    numChannels: number
  ) => void;
}

type ConnectionStatus = "disconnected" | "connected" | "connecting";

interface TTSMessage {
  type: "tts_update";
  tts: string;
}

interface ASRMessage {
  type: "asr_update";
  asr: string;
}

export default function useACEController(params: Params): Output {
  const websocketRef = useRef<WebSocket>(null);
  const audioCtxRef = useRef<AudioContext>(null);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");

  function onError(error: Error) {
    setConnectionStatus("disconnected");
    params.onError(error);
    websocketRef.current?.close(1000);
    websocketRef.current = null;
  }

  function onOpen() {
    setConnectionStatus("connected");
  }

  function onClose(e: CloseEvent): void {
    if (e.wasClean) {
      onError(new Error("Websocket closed unexpectedly"));
    }

    setConnectionStatus("disconnected");
    websocketRef.current = null;
  }

  function onWindowUnload() {
    setConnectionStatus("disconnected");
    websocketRef.current?.close(1000);
  }

  async function handleAudioMessage(data: ArrayBuffer) {
    try {
      const sampleRate = extractWavSampleRate(data);
      if (
        !audioCtxRef.current ||
        audioCtxRef.current.sampleRate !== sampleRate
      ) {
        audioCtxRef.current = new AudioContext({ sampleRate });
      }
      const audioBuffer = await audioCtxRef.current.decodeAudioData(data);
      params.onAudioChunk(audioBuffer);
    } catch (error) {
      logger.warn("Error decoding audio chunk. The chunk was discarded", error);
    }
  }

  function handleTTSUpdate(data: TTSMessage) {
    params.onTTS(data.tts);
  }

  function handleASRUpdate(data: ASRMessage) {
    params.onASR(data.asr);
  }

  async function onMessage(event: MessageEvent): Promise<void> {
    if (event.data instanceof ArrayBuffer) {
      handleAudioMessage(event.data);
      return;
    }
    const data = JSON.parse(event.data);
    switch (data.type) {
      case "tts_update":
        handleTTSUpdate(data);
        break;
      case "asr_update":
        handleASRUpdate(data);
        break;
      default:
        logger.warn("Unrecognized message. Discarded", data);
    }
  }

  function connect() {
    if (!websocketRef.current) {
      setConnectionStatus("connecting");
      const ws = new WebSocket(params.url);
      websocketRef.current = ws;
      ws.binaryType = "arraybuffer";
      ws.onmessage = onMessage;
      ws.onopen = onOpen;
      ws.onclose = onClose;
      ws.onerror = () =>
        onError(
          new Error(
            `Failed to establish a websocket connection. Is the ACE Controller running at ${params.url}?`
          )
        );

      window.onbeforeunload = onWindowUnload;
    }
  }

  function sendAudioChunk(
    chunk: ArrayBuffer,
    sampleRate: number,
    numChannels: number
  ): void {
    if (websocketRef.current?.readyState !== WebSocket.OPEN) {
      logger.warn("Websocket is not open. Discarding audio chunk");
      return;
    }

    websocketRef.current.send(pcmToWav(chunk, sampleRate, numChannels));
  }

  return { connectionStatus, connect, sendAudioChunk };
}
