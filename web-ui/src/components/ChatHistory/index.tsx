import { ChatEntry } from "../../hooks/useChatHistory";
import "./index.css";

interface Props {
  entries: ChatEntry[];
}
export default function ChatHistory(props: Props) {
  return (
    <ul className="chat-history-entries">
      {props.entries.map((entry) => (
        <li key={Math.random()}>{entry.text}</li>
      ))}
    </ul>
  );
}
