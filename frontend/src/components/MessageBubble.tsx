import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage } from "../types";
import SkuCard from "./SkuCard";

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = message.content;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[85%] ${
          isUser
            ? "bg-blue-600 text-white rounded-2xl rounded-br-md px-4 py-2.5"
            : "bg-white text-gray-800 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm border border-gray-100"
        }`}
      >
        {!isUser && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <div className="w-5 h-5 bg-blue-100 rounded-full flex items-center justify-center">
              <span className="text-xs text-blue-600 font-bold">A</span>
            </div>
            <span className="text-xs text-gray-400 font-medium">AI 助手</span>
          </div>
        )}

        <div
          className={`text-sm leading-relaxed ${
            isUser ? "whitespace-pre-wrap" : "markdown-body"
          }`}
        >
          {message.isStreaming && !message.content ? (
            <span className="inline-flex items-center gap-1 py-1">
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" />
            </span>
          ) : isUser ? (
            message.content
          ) : message.isStreaming ? (
            <>
              <span className="whitespace-pre-wrap">{message.content}</span>
              <span className="inline-block w-0.5 h-4 bg-blue-500 ml-0.5 align-middle animate-blink" />
            </>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          )}
        </div>

        {message.skuResults && message.skuResults.length > 0 && (
          <div className="mt-3 grid grid-cols-1 gap-2">
            {message.skuResults.map((sku, i) => (
              <SkuCard key={sku.item_code} sku={sku} index={i} />
            ))}
          </div>
        )}

        {/* Copy button for assistant messages */}
        {!isUser && !message.isStreaming && message.content && (
          <div className="flex justify-end mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors px-1.5 py-0.5 rounded hover:bg-gray-50"
              title="复制内容"
            >
              {copied ? (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>已复制</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  <span>复制</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
