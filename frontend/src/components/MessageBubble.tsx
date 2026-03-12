import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage } from "../types";
import SkuCard from "./SkuCard";

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
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
          ) : (
            <>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
              {message.isStreaming && (
                <span className="inline-block w-0.5 h-4 bg-blue-500 ml-0.5 align-middle animate-blink" />
              )}
            </>
          )}
        </div>

        {message.skuResults && message.skuResults.length > 0 && (
          <div className="mt-3 grid grid-cols-1 gap-2">
            {message.skuResults.map((sku, i) => (
              <SkuCard key={sku.item_code} sku={sku} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
