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

import "./App.css";
import useACEController from "./hooks/useACEController";
import useAudioPlayer from "./hooks/useAudioPlayer";
import useMicrophone from "./hooks/useMicrophone";
import useChatHistory from "./hooks/useChatHistory";
import ToastNotices from "./components/ToastNotices";
import useToastNotices from "./hooks/useToastNotices";
import BotFace from "./components/BotFace";
import UserSpeechInput from "./components/UserSpeechInput";
import ChatHistory from "./components/ChatHistory";
import useACEControllerURL from "./hooks/useACEControllerURL";

function App() {
  const toastNotices = useToastNotices();
  const websocketUrl = useACEControllerURL({ onError: toastNotices.fatal });

  const chatHistory = useChatHistory();
  const audioPlayer = useAudioPlayer();
  const aceController = useACEController({
    url: websocketUrl.baseUrlWithStreamID,
    onError: toastNotices.fatal,
    onAudioChunk: (chunk) => audioPlayer.play(chunk),
    onTTS: chatHistory.addThem,
    onASR: chatHistory.addUs,
  });
  const microphone = useMicrophone({
    onAudioChunkAvailable: aceController.sendAudioChunk,
    onError: toastNotices.fatal,
  });

  function onChangeURL() {
    const url = prompt("Enter the ACE Controller URL", websocketUrl.baseUrl);
    if (url) {
      window.location.href = `?ace-controller-url=${url}`;
    }
  }

  return (
    <div className="app-container">
      <h1 className="app-title">ACE Controller UI</h1>
      <p className="app-subtitle">
        ACE Controller URL: <code>{websocketUrl.baseUrl}</code> (
        <a href="#" onClick={onChangeURL}>
          change
        </a>
        )
      </p>
      <div className="app-stage">
        <div className="app-stage-section top">
          <BotFace
            audioSource={audioPlayer.getSource()}
            connectionStatus={aceController.connectionStatus}
          />
          <ChatHistory entries={chatHistory.entries} />
        </div>

        <div className="app-stage-section bottom">
          <UserSpeechInput
            micState={microphone.microphoneState}
            onEnableMic={() => {
              aceController.connect();
              microphone.startRecording();
            }}
            onDisableMic={microphone.stopRecording}
            audioSource={microphone.source}
          />
        </div>
      </div>
      <ToastNotices toasts={toastNotices.toasts} />
    </div>
  );
}

export default App;
