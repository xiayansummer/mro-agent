import { useState, useRef, KeyboardEvent } from "react";

interface Props {
  onSend: (message: string) => void;
  onStop: () => void;
  disabled: boolean;
  isLoading: boolean;
}

export default function ChatInput({ onSend, onStop, disabled, isLoading }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={disabled}
          rows={1}
          placeholder="描述您需要的产品，例如：M8不锈钢六角螺栓"
          className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-2.5 text-sm
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                     disabled:bg-gray-50 disabled:text-gray-400
                     placeholder:text-gray-400"
        />
        {isLoading ? (
          <button
            onClick={onStop}
            className="shrink-0 bg-red-500 text-white rounded-xl px-5 py-2.5 text-sm font-medium
                       hover:bg-red-600 active:bg-red-700 transition-colors"
          >
            停止
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="shrink-0 bg-blue-600 text-white rounded-xl px-5 py-2.5 text-sm font-medium
                       hover:bg-blue-700 active:bg-blue-800 transition-colors
                       disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            发送
          </button>
        )}
      </div>
    </div>
  );
}
