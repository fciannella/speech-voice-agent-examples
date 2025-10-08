import { useState } from "react";

export interface ChatEntry {
  text: string;
  author: "us" | "them";
}
export default function useChatHistory() {
  const [entries, setEntries] = useState<ChatEntry[]>([]);

  function add(text: string, author: "us" | "them") {
    setEntries([...entries, { text, author }]);
  }

  // Shortcut for adding a message from the bot
  function addThem(text: string) {
    add(text, "them");
  }

  function addUs(text: string) {
    add(text, "us");
  }

  return { entries, add, addThem, addUs };
}
