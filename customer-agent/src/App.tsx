import { useState, useEffect, useRef } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatHeader } from "@/components/ChatHeader";
import { HeroState } from "@/components/HeroState";
import { ChatMessage, type Message } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { AboutModal } from "@/components/AboutModal";

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(() => {
    return localStorage.getItem("octapus_session_id");
  });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [recentTopics, setRecentTopics] = useState<string[]>(() => {
    const saved = localStorage.getItem("octapus_recent_topics");
    return saved ? JSON.parse(saved) : [];
  });
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = localStorage.getItem("octapus_theme") as "dark" | "light";
    if (saved) return saved;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("octapus_theme", theme);
  }, [theme]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const handleSend = async (
    textToSend?: string,
    imageUrl?: string,
    audioUrl?: string,
    audioDuration?: string
  ) => {
    const rawQuery = (textToSend !== undefined ? textToSend : input).trim();
    const query =
      rawQuery ||
      (imageUrl
        ? "I have attached a project image for review. Can you provide information on what Octapus can build?"
        : audioUrl
        ? `Voice message (${audioDuration || "Audio"})`
        : "");
    if (!query && !imageUrl && !audioUrl) return;
    if (loading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      sender: "user",
      text: rawQuery || (imageUrl ? "Attached project visual" : audioUrl ? "Sent a voice note" : ""),
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      imageUrl,
      audioUrl,
      audioDuration,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // Save recent topic
    const topicSnippet = rawQuery || (imageUrl ? "Visual project requirement" : "Voice note consultation");
    setRecentTopics((prev) => {
      const updated = [topicSnippet, ...prev.filter((t) => t !== topicSnippet)].slice(0, 15);
      localStorage.setItem("octapus_recent_topics", JSON.stringify(updated));
      return updated;
    });

    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query, session_id: sessionId }),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      const data = await res.json();
      if (data.session_id) {
        setSessionId(data.session_id);
        localStorage.setItem("octapus_session_id", data.session_id);
      }

      const botMsg: Message = {
        id: crypto.randomUUID(),
        sender: "bot",
        text: data.reply || "I am available to assist you with any questions regarding Octapus LLC.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch {
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        sender: "bot",
        text: "I experienced a temporary network issue. Please ask again or reach out to our team at **info@octapus.ae**.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleClearChat = async () => {
    if (confirm("Start a new conversation with Octapus Coordinator?")) {
      if (sessionId) {
        try {
          await fetch("/chat/reset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId }),
          });
        } catch (_) {}
      }
      localStorage.removeItem("octapus_session_id");
      setSessionId(null);
      setMessages([]);
    }
  };

  return (
    <div className="flex h-screen h-[100dvh] w-full bg-background text-foreground overflow-hidden font-sans">
      {/* Sidebar */}
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={handleClearChat}
        onOpenAbout={() => setAboutOpen(true)}
        recentTopics={recentTopics}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Main Chat Workspace */}
      <div className="flex-1 flex flex-col h-full overflow-hidden relative">
        <ChatHeader
          onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
          onOpenAbout={() => setAboutOpen(true)}
          onClearChat={handleClearChat}
          theme={theme}
          onToggleTheme={toggleTheme}
        />

        {/* Scrollable messages container */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 scroll-smooth">
          {messages.length === 0 ? (
            <HeroState onSelectPrompt={(prompt) => handleSend(prompt)} />
          ) : (
            <div className="w-full max-w-3xl mx-auto space-y-6 pb-6">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {loading && (
                <div className="flex items-start gap-3 sm:gap-4 w-full animate-in fade-in duration-200">
                  <img
                    src="/horus.jpg"
                    alt="Horus Mascot"
                    className="w-8 h-8 sm:w-9 sm:h-9 rounded-2xl object-cover shrink-0 shadow-sm ring-1 ring-sky-400/50 shadow-sky-500/20 mt-1"
                  />
                  <div className="rounded-3xl rounded-tl-md px-5 py-3.5 bg-card border border-border/70 shadow-sm flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />
                    <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse [animation-delay:0.2s]" />
                    <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse [animation-delay:0.4s]" />
                    <span className="text-xs text-muted-foreground ml-2">Horus is preparing a response...</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Floating Input Capsule */}
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={(txt, img, aud, dur) => handleSend(txt, img, aud, dur)}
          isLoading={loading}
        />
      </div>

      {/* About Modal */}
      <AboutModal isOpen={aboutOpen} onClose={() => setAboutOpen(false)} />
    </div>
  );
}
