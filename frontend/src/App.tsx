import { useState, useRef, useEffect } from "react";

// Define the shape of a message
type Message = {
  role: "user" | "bot";
  content: string;
};

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

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
    const userMessage: Message = { role: "user", content: userMessageContent };
    const newHistory = [...messages, userMessage];

    // Optimistic UI Update
    setMessages((prev) => [...prev, userMessage]);
    setMessages((prev) => [...prev, { role: "bot", content: "" }]);

    try {
      // 2. The Fetch Call
      // Note: We use a relative URL "/stream".
      // The Vite Proxy in vite.config.ts forwards this to http://127.0.0.1:8000
      const response = await fetch("/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: newHistory }),
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
        { role: "bot", content: "Error: Could not connect to the agent." },
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

          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[85%] rounded-lg p-3 text-sm leading-relaxed shadow-sm ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-700 text-gray-100 border border-gray-600"
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
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
