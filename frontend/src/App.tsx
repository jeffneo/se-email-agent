import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { useSmoothStreaming } from "./useSmoothStreaming";
// uuid v4
import { v4 as uuidv4 } from "uuid";

// Define the shape of a message
type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

// Place this outside App or in a new file
const SmoothMessage = ({
  content,
  isStreaming,
  onScrollNeeded,
}: {
  content: string;
  isStreaming: boolean;
  onScrollNeeded: () => void;
}) => {
  // If we are actively streaming, use the hook.
  // If not (historic message), just show the full text instantly for performance.
  const smoothText = useSmoothStreaming(content, 15); // 15ms per char = ~400 WPM
  const textToShow = isStreaming ? smoothText : content;

  // The "Pin to Bottom" Effect
  useEffect(() => {
    // Whenever the text grows, ask parent to scroll
    if (isStreaming && onScrollNeeded) {
      onScrollNeeded();
    }
  }, [smoothText, isStreaming, onScrollNeeded]);

  return (
    <ReactMarkdown components={markdownComponents}>{textToShow}</ReactMarkdown>
  );
};

// 1. DEFINE STYLES OUTSIDE TO PREVENT RE-RENDERS
const markdownComponents = {
  a: ({ ...props }) => (
    <a
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-300 hover:text-blue-200 underline break-words"
    />
  ),
  code: ({ ...props }) => (
    <code
      {...props}
      className="bg-gray-800 rounded px-1 py-0.5 text-xs font-mono break-all"
    />
  ),
  p: ({ ...props }) => <p {...props} className="mb-2 last:mb-0" />,
  // Add lists too for good measure
  ul: ({ ...props }) => (
    <ul {...props} className="list-disc pl-4 mb-2 space-y-1" />
  ),
  ol: ({ ...props }) => (
    <ol {...props} className="list-decimal pl-4 mb-2 space-y-1" />
  ),
};

// Simple animated dots component
// interval = wait time between adding a dot (in ms)
const ThinkingDots = ({ interval = 500 }: { interval?: number }) => {
  const [dots, setDots] = useState(".");

  useEffect(() => {
    const timer = setInterval(() => {
      // setDots((prev) => (prev.length < 3 ? prev + "." : "."));
      setDots((prev) => prev + ".");
    }, interval);

    return () => clearInterval(timer);
  }, [interval]);

  return (
    <span className="animate-pulse text-gray-400 font-bold text-xl">
      {dots}
    </span>
  );
};

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const threadIdRef = useRef<string>(uuidv4()); // Generate a unique thread ID for this session

  // 1. The Mutex Lock
  // Prevents double-firing in React Strict Mode
  const isSubmittingRef = useRef(false);

  // Auto-scroll ref
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Guard Clause: Stop if already loading or empty
    if (isSubmittingRef.current || !input.trim()) return;

    // Lock the mutex
    isSubmittingRef.current = true;
    setIsLoading(true);

    // Capture current input and clear UI
    const userMessageContent = input;
    setInput("");

    // Create the new history log to send to the backend
    const userMessage: Message = {
      id: uuidv4(),
      role: "user",
      content: userMessageContent,
    };
    const newHistory = [...messages, userMessage];

    // Optimistic UI Update
    setMessages((prev) => [...prev, userMessage]);
    setMessages((prev) => [
      ...prev,
      { id: uuidv4(), role: "assistant", content: "" },
    ]);

    try {
      // 2. The Fetch Call
      // Note: We use a relative URL "/stream".
      // The Vite Proxy in vite.config.ts forwards this to http://127.0.0.1:8000
      const requestBody = JSON.stringify({
        messages: newHistory,
        threadId: threadIdRef.current,
      });
      console.log("Sending request body:", requestBody);
      const response = await fetch("/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: requestBody,
      });

      if (!response.body) throw new Error("No response body");

      // 3. The Streaming Engine
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let done = false;

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        const chunkValue = decoder.decode(value, { stream: true });

        // Immutable State Update
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastIndex = newMessages.length - 1;

          // Create a COPY of the last message object to avoid mutation
          const updatedLastMsg = {
            ...newMessages[lastIndex],
            content: newMessages[lastIndex].content + chunkValue,
          };

          // Swap it in
          newMessages[lastIndex] = updatedLastMsg;
          return newMessages;
        });
      }
    } catch (error) {
      console.error("Error streaming:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: uuidv4(),
          role: "assistant",
          content: "Error: Could not connect to the agent.",
        },
      ]);
    } finally {
      // Unlock the mutex
      isSubmittingRef.current = false;
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center bg-gray-900 text-gray-100 p-4 sm:p-8">
      {/* Main Chat Container */}
      <div className="flex w-full max-w-2xl flex-col h-[85vh] bg-gray-800 rounded-xl shadow-2xl overflow-hidden border border-gray-700">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 bg-gray-900/50 flex items-center justify-between">
          <h1 className="text-xl font-bold text-blue-400">Neo4j Agent</h1>
          <span className="text-xs text-gray-500">v1.0 • Vite + FastAPI</span>
        </div>

        {/* Message Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-transparent">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center text-gray-500 text-sm">
              Ask a question about the Neo4j Graph Database...
            </div>
          )}

          {messages.map((msg, idx) => {
            // Determine if this specific message is the one currently streaming
            const isLastMessage = idx === messages.length - 1;
            const isAssistant = msg.role === "assistant";
            const isStreaming = isLastMessage && isAssistant;

            return (
              <div
                key={idx}
                className={`flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-lg p-3 text-sm leading-relaxed shadow-sm overflow-hidden ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-700 text-gray-100 border border-gray-600"
                  }`}
                >
                  {/* Logic: 
                      1. If Bot + Empty -> Show Thinking Dots 
                      2. If Bot + Text -> Show Smooth Stream 
                      3. If User -> Show Text Normal 
                  */}

                  {isAssistant && msg.content === "" ? (
                    <ThinkingDots interval={400} />
                  ) : (
                    <SmoothMessage
                      content={msg.content}
                      isStreaming={isStreaming}
                      onScrollNeeded={() =>
                        messagesEndRef.current?.scrollIntoView({
                          behavior: "auto",
                        })
                      }
                    />
                  )}
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} className="pt-8" />
        </div>

        {/* Input Area */}
        <form
          onSubmit={handleSubmit}
          className="p-4 border-t border-gray-700 bg-gray-900/50"
        >
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="How do I optimize a MATCH query?"
              className="flex-1 bg-gray-950 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-white placeholder-gray-500 transition-all"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading}
              className={`font-bold py-2 px-6 rounded-lg transition-all ${
                isLoading
                  ? "bg-blue-800 text-gray-400 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-500 text-white shadow-lg hover:shadow-blue-500/20"
              }`}
            >
              {isLoading ? "..." : "Send"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default App;

// {messages.map((msg, idx) => (
//             <div
//               key={idx}
//               className={`flex ${
//                 msg.role === "user" ? "justify-end" : "justify-start"
//               }`}
//             >
//               <div
//                 className={`max-w-[85%] rounded-lg p-3 text-sm leading-relaxed shadow-sm overflow-hidden ${
//                   msg.role === "user"
//                     ? "bg-blue-600 text-white"
//                     : "bg-gray-700 text-gray-100 border border-gray-600"
//                 }`}
//               >
//                 {/* CONDITIONAL RENDERING */}
//                 {msg.role === "bot" && msg.content === "" ? (
//                   <ThinkingDots interval={500} />
//                 ) : (
//                   <ReactMarkdown components={markdownComponents}>
//                     {msg.content}
//                   </ReactMarkdown>
//                 )}
//               </div>
//             </div>
//           ))}
