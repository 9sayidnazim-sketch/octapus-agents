import React, { useState } from "react";
import { Copy, Check, Volume2, ThumbsUp, ThumbsDown } from "lucide-react";

export interface Message {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: string;
}

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [rated, setRated] = useState<"up" | "down" | null>(null);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleSpeak = () => {
    if (!("speechSynthesis" in window)) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel();
    const cleanText = message.text.replace(/[*_#`]/g, "");
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  // Basic markdown parser
  const renderFormattedText = (raw: string) => {
    const lines = raw.split("\n");
    return lines.map((line, idx) => {
      let trimmed = line.trim();
      if (!trimmed) return <div key={idx} className="h-2" />;

      // Bullet points
      const isBullet = trimmed.startsWith("- ") || trimmed.startsWith("* ");
      if (isBullet) {
        trimmed = trimmed.substring(2);
      }

      // Inline formatting
      const parts = trimmed.split(/(\*\*.*?\*\*|`.*?`|\[.*?\]\(.*?\)|https?:\/\/[^\s]+|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g);

      const content = parts.map((part, pIdx) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={pIdx} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={pIdx} className="px-1.5 py-0.5 rounded bg-muted text-xs font-mono text-sky-600 dark:text-sky-400">
              {part.slice(1, -1)}
            </code>
          );
        }
        if (part.includes("@")) {
          return (
            <a key={pIdx} href={`mailto:${part}`} className="text-sky-500 hover:underline font-medium">
              {part}
            </a>
          );
        }
        if (part.startsWith("http")) {
          return (
            <a key={pIdx} href={part} target="_blank" rel="noopener noreferrer" className="text-sky-500 hover:underline">
              {part}
            </a>
          );
        }
        if (part.toLowerCase().includes("octapus.ae")) {
          return (
            <a key={pIdx} href="https://octapus.ae" target="_blank" rel="noopener noreferrer" className="text-sky-500 hover:underline font-medium">
              {part}
            </a>
          );
        }
        return part;
      });

      if (isBullet) {
        return (
          <div key={idx} className="flex items-start gap-2 ml-2 my-1">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-500 mt-2 shrink-0" />
            <span className="leading-relaxed">{content}</span>
          </div>
        );
      }

      return (
        <p key={idx} className="leading-relaxed mb-2 last:mb-0">
          {content}
        </p>
      );
    });
  };

  if (message.sender === "user") {
    return (
      <div className="flex justify-end w-full animate-in fade-in duration-200">
        <div className="max-w-[85%] sm:max-w-[75%] rounded-3xl rounded-tr-md px-5 py-3.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white shadow-md shadow-blue-500/15 text-sm sm:text-base leading-relaxed break-words">
          {message.text}
          <div className="text-[10px] text-white/70 text-right mt-1.5">
            {message.timestamp}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 sm:gap-4 w-full animate-in fade-in duration-200">
      {/* Octapus Coordinator Mascot Avatar */}
      <img
        src="/octapus-logo.jpg"
        alt="Octapus Coordinator"
        className="w-8 h-8 sm:w-9 sm:h-9 rounded-2xl object-cover shrink-0 shadow-sm ring-1 ring-border mt-1"
      />

      <div className="flex-1 max-w-[calc(100%-48px)]">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-semibold text-xs sm:text-sm text-foreground">Octapus Coordinator</span>
          <span className="text-[11px] text-muted-foreground">{message.timestamp}</span>
        </div>

        <div className="rounded-3xl rounded-tl-md px-5 py-4 bg-card border border-border/70 shadow-sm text-sm sm:text-[15px] text-foreground leading-relaxed">
          {renderFormattedText(message.text)}
        </div>

        {/* Action Toolbar */}
        <div className="flex items-center gap-1 mt-2 text-muted-foreground">
          <button
            onClick={handleCopy}
            className="p-1.5 rounded-lg hover:bg-accent hover:text-foreground text-xs transition-colors inline-flex items-center gap-1 cursor-pointer"
            title="Copy response"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            <span className="text-[11px]">{copied ? "Copied" : "Copy"}</span>
          </button>

          <button
            onClick={handleSpeak}
            className={`p-1.5 rounded-lg hover:bg-accent text-xs transition-colors cursor-pointer ${
              speaking ? "text-sky-500 bg-sky-500/10" : "hover:text-foreground"
            }`}
            title="Listen aloud"
          >
            <Volume2 className="w-3.5 h-3.5" />
          </button>

          <div className="h-3 w-px bg-border mx-1" />

          <button
            onClick={() => setRated(rated === "up" ? null : "up")}
            className={`p-1.5 rounded-lg hover:bg-accent text-xs transition-colors cursor-pointer ${
              rated === "up" ? "text-emerald-500" : "hover:text-foreground"
            }`}
            title="Good response"
          >
            <ThumbsUp className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setRated(rated === "down" ? null : "down")}
            className={`p-1.5 rounded-lg hover:bg-accent text-xs transition-colors cursor-pointer ${
              rated === "down" ? "text-red-500" : "hover:text-foreground"
            }`}
            title="Bad response"
          >
            <ThumbsDown className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
