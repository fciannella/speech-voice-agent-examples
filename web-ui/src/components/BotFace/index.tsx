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

import useRealTimeVolume from "../../hooks/useRealTimeVolume";
import useRequestAnimationFrame from "../../hooks/useRequestAnimationFrame";
import Loading from "../Loading";
import "./index.css";

interface Props {
  audioSource: AudioNode;
  connectionStatus: "connected" | "connecting" | "disconnected";
}

export default function BotFace({ audioSource, connectionStatus }: Props) {
  const realTimeVolume = useRealTimeVolume(audioSource);
  useRequestAnimationFrame();

  const isBotActivelySpeaking = realTimeVolume !== 0;

  const styles: React.CSSProperties = {};
  if (isBotActivelySpeaking) {
    styles[
      "boxShadow"
    ] = `0 0 0px ${realTimeVolume}px var(--bot-volume-active-box-shadow-bg)`;
    styles["borderColor"] = "var(--active-audio-border-color)";
  }

  return (
    <div className="bot-face">
      <div className="bot-face-emoji-container">
        <div className="bot-face-emoji" style={styles}>
          {connectionStatus === "connected" && "🙂"}
          {connectionStatus === "connecting" && <Loading />}
          {connectionStatus === "disconnected" && (
            <span className="material-symbols-outlined">
              <span
                className="material-symbols-outlined disconnected"
                title="Enable microphone to connect"
              >
                signal_disconnected
              </span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
