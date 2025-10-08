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

import { useRef } from "react";
import logger from "../utils/logger";

const AUDIO_BUFFER_LENGTH_SEC = 120;
const INITIAL_SAMPLE_RATE = 16_000;

// Don't start the audio before the buffer has at least this much data.
// If we start immediately, the audio chunks arrive too late to play
// in real time and cause choppy audio, especially in high-latency environments.
const MIN_BUFFER_DURATION_BEFORE_START_SEC = 0.8;
class AudioPlayer {
  private timerID: ReturnType<typeof setTimeout> | null = null;
  private offset: number = 0;
  private currentAudioSequenceDuration: number = 0;
  private currentAudioSequenceStartedAt: number = 0;
  private audioBuffer: AudioBuffer;
  private source: AudioBufferSourceNode;
  private audioCtx = new AudioContext({ sampleRate: INITIAL_SAMPLE_RATE });
  private timeUntilAudioCompleted: number = 0;

  constructor() {
    this.audioBuffer = this.createNewAudioBuffer();
    this.source = this.audioCtx.createBufferSource();
    this.source.buffer = this.audioBuffer;
    this.source.connect(this.audioCtx.destination);
  }

  play(chunk: AudioBuffer): void {
    const channel = this.audioBuffer.getChannelData(0); // mono channel
    const buffer = chunk.getChannelData(0);
    if (chunk.sampleRate !== this.audioCtx.sampleRate) {
      this.audioCtx = new AudioContext({ sampleRate: chunk.sampleRate });
      logger.log(
        `New sample rate ${this.audioCtx.sampleRate}. Resetting buffer`
      );
      this.reset();
    }

    // We receive the data in unsigned 16-bit words. AudioBuffer must
    // be in 32-bit floats between -1.0 and 1.0. To convert, normalize
    // each sample
    for (let i = 0; i < buffer.length; i++) {
      channel[i + this.offset] = buffer[i];
    }
    this.offset += buffer.length;

    // We set a timer that will reset the audio buffer after the audio sequence has been
    // played. We cannot predetermine the duration of the audio sequence, because more
    // audio chunks may be added after the audio has started playing. For this reason,
    // every time a chunk is added to the buffer, we clear the existing timer, recompute
    // the duration of the audio sequence, and create a new timer with the appropriate
    // audio sequence duration.
    if (this.timerID) {
      clearTimeout(this.timerID);
    }
    const chunkDuration = buffer.length / this.audioCtx.sampleRate;
    this.currentAudioSequenceDuration += chunkDuration;

    // If this is the first chunk of audio since the player was last reset, immediately
    // start playing the source. Additional chunks will be appended to the buffer as
    // they come
    if (!this.currentAudioSequenceStartedAt) {
      if (
        this.currentAudioSequenceDuration < MIN_BUFFER_DURATION_BEFORE_START_SEC
      ) {
        logger.warn(
          `The current buffer is too short ${this.currentAudioSequenceDuration} seconds) to start the audio. Waiting for more chunks...`
        );
        return;
      }
      this.currentAudioSequenceStartedAt = performance.now();
      this.source.start();
    }

    const audioEllapsed =
      (performance.now() - this.currentAudioSequenceStartedAt) / 1000;

    this.timeUntilAudioCompleted =
      this.currentAudioSequenceDuration - audioEllapsed;
    this.timerID = setTimeout(() => {
      this.reset();
    }, this.timeUntilAudioCompleted * 1000);
  }

  private createNewAudioBuffer(): AudioBuffer {
    return this.audioCtx.createBuffer(
      1,
      this.audioCtx.sampleRate * AUDIO_BUFFER_LENGTH_SEC,
      this.audioCtx.sampleRate
    );
  }

  private reset(): void {
    logger.log("reset");
    if (this.source) {
      try {
        this.source.stop();
        this.source.disconnect();
      } catch {
        // Ignore errors if source was already stopped
      }
    }

    this.offset = 0;
    this.currentAudioSequenceDuration = 0;
    this.currentAudioSequenceStartedAt = 0;
    this.timeUntilAudioCompleted = 0;

    if (this.timerID) {
      clearTimeout(this.timerID);
      this.timerID = null;
    }

    this.audioBuffer = this.createNewAudioBuffer();
    this.source = this.audioCtx.createBufferSource();
    this.source.buffer = this.audioBuffer;
    this.source.connect(this.audioCtx.destination);
  }

  public getSource(): AudioBufferSourceNode {
    return this.source;
  }

  // Immediately stops playing audio. Audio left in the buffer is erased
  public interrupt(): void {
    if (this.timerID) {
      clearTimeout(this.timerID);
    }
    this.reset();
  }
}

export default function useAudioPlayer(): AudioPlayer {
  const audioPlayerRef = useRef<AudioPlayer>(null);
  if (!audioPlayerRef.current) {
    audioPlayerRef.current = new AudioPlayer();
  }
  return audioPlayerRef.current;
}
