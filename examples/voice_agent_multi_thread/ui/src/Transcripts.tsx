// SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD 2-Clause License

import { useEffect, useRef } from "react";

import { useState } from "react";

interface Props {
  websocket: WebSocket | null;
}

interface IncomingMessage {
  text: string;
  actor: string;
  message_id: string;
}

interface AugmentedMessage extends IncomingMessage {
  timestamp: Date;
}

export function Transcripts(props: Props) {
  const [transcripts, setTranscripts] = useState<AugmentedMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Clear transcripts when a new WebSocket connection is established
  useEffect(() => {
    if (props.websocket) {
      console.log("New WebSocket connection detected, clearing old transcripts");
      setTranscripts([]);
    }
  }, [props.websocket]);

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      const message = JSON.parse(event.data) as IncomingMessage;
      console.log(event.data, message);
      setTranscripts((prev) => {
        const existingMessage = prev.find(
          (t) =>
            t.actor === message.actor && t.message_id === message.message_id
        );
        if (existingMessage) {
          existingMessage.text = message.text;
        } else {
          prev.push({ ...message, timestamp: new Date() });
        }
        return [...prev];
      });
    }

    props.websocket?.addEventListener("message", onMessage);
    return () => {
      props.websocket?.removeEventListener("message", onMessage);
    };
  }, [props.websocket]);

  useEffect(() => {
    // Scroll to the bottom of the transcripts every time a new transcript is added
    bottomRef.current?.scrollIntoView();
  }, [transcripts]);

  const filteredTranscripts = transcripts.filter((transcript) => {
    const actor = transcript.actor?.toLowerCase()?.trim();
    const isSystem = actor === "system";
    return !isSystem;
  });
    
  return filteredTranscripts.map((transcript) => (
    <div
      className="font-mono text-lg flex items-start mb-2"
      key={transcript.actor + transcript.message_id}
    >
      {transcript.timestamp.toTimeString().slice(0, 8)}
      <div className="flex items-center ml-3 mr-3 min-w-[60px]">
        <div
          className={`rounded-lg text-white text-sm p-1 flex justify-center items-center min-w-full ${
            transcript.actor === "bot" ? "bg-nvidia" : "bg-cyan-700"
          }`}
        >
          {transcript.actor}
        </div>
      </div>
      <div>:</div>
      <div className="pl-3"> </div>
      <div className="flex-1">{transcript.text}</div>
      <div ref={bottomRef} />
    </div>
  ));
}
