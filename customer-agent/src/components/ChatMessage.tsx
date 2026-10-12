import React, { useState, useRef, useEffect } from "react";
import { Copy, Check, Volume2, VolumeX, ThumbsUp, ThumbsDown, Play, Pause, Maximize2, X } from "lucide-react";

export interface Message {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: string;
  imageUrl?: string;
  audioUrl?: string;
  audioDuration?: string;
}

interface ChatMessageProps {
  message: Message;
  autoSpeak?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [rated, setRated] = useState<"up" | "down" | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

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
    utterance.rate = 0.98;
    utterance.pitch = 1.0;

    // Pick warm natural English voice if available
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(
      (v) => v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Samantha") || v.name.includes("Google") || v.name.includes("Daniel"))
    );
    if (preferredVoice) {
      utterance.voice = preferredVoice;
    }

    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  const toggleAudioNote = () => {
    if (!audioRef.current) return;
    if (isPlayingAudio) {
      audioRef.current.pause();
      setIsPlayingAudio(false);
    } else {
      audioRef.current.play();
      setIsPlayingAudio(true);
    }
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
        <div className="max-w-[85%] sm:max-w-[75%] rounded-3xl rounded-tr-md p-4 sm:p-5 bg-gradient-to-r from-sky-500 to-blue-600 text-white shadow-md shadow-blue-500/15 text-sm sm:text-base leading-relaxed break-words space-y-2.5">
          
          {/* User Attached Image */}
          {message.imageUrl && (
            <div className="relative group cursor-pointer overflow-hidden rounded-2xl bg-black/20 border border-white/20 max-w-sm">
              <img
                src={message.imageUrl}
                alt="Attached visual"
                className="w-full max-h-64 object-cover rounded-2xl group-hover:scale-105 transition-transform duration-300"
                onClick={() => setLightboxOpen(true)}
              />
              <button
                type="button"
                onClick={() => setLightboxOpen(true)}
                className="absolute top-2 right-2 p-1.5 rounded-xl bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity backdrop-blur-sm"
                title="View full size"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* User Voice Note Player */}
          {message.audioUrl && (
            <div className="flex items-center gap-3 bg-white/15 backdrop-blur-md rounded-2xl p-2.5 border border-white/20 min-w-[200px]">
              <button
                type="button"
                onClick={toggleAudioNote}
                className="w-8 h-8 rounded-full bg-white text-sky-600 flex items-center justify-center shadow-sm shrink-0 hover:scale-105 active:scale-95 transition-transform cursor-pointer"
              >
                {isPlayingAudio ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
              </button>

              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-1 h-4">
                  {[40, 75, 55, 90, 60, 80, 45, 95, 70, 50, 85, 60, 40].map((h, i) => (
                    <span
                      key={i}
                      className={`w-1 rounded-full transition-all duration-200 ${
                        isPlayingAudio ? "bg-white animate-pulse" : "bg-white/60"
                      }`}
                      style={{
                        height: isPlayingAudio ? `${Math.max(20, Math.round(h * Math.random()))}%` : `${h}%`,
                        animationDelay: `${i * 0.05}s`,
                      }}
                    />
                  ))}
                </div>
                <div className="text-[10px] text-white/80 font-mono">
                  {message.audioDuration || "Voice note"}
                </div>
              </div>

              <audio
                ref={audioRef}
                src={message.audioUrl}
                onEnded={() => setIsPlayingAudio(false)}
                className="hidden"
              />
            </div>
          )}

          {/* Message Text */}
          {message.text && (
            <div>{message.text}</div>
          )}

          <div className="text-[10px] text-white/70 text-right">
            {message.timestamp}
          </div>
        </div>

        {/* Fullscreen Lightbox Modal */}
        {lightboxOpen && message.imageUrl && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in"
            onClick={() => setLightboxOpen(false)}
          >
            <div className="relative max-w-4xl max-h-[90vh]">
              <button
                onClick={() => setLightboxOpen(false)}
                className="absolute -top-10 right-0 p-2 text-white hover:text-slate-300 cursor-pointer"
              >
                <X className="w-6 h-6" />
              </button>
              <img
                src={message.imageUrl}
                alt="Enlarged visual"
                className="max-h-[85vh] max-w-full rounded-2xl shadow-2xl object-contain border border-white/20"
              />
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 sm:gap-4 w-full animate-in fade-in duration-200">
      {/* HORUS Mascot Avatar */}
      <img
        src="/horus.jpg"
        alt="Horus Coordinator"
        className="w-8 h-8 sm:w-9 sm:h-9 rounded-2xl object-cover shrink-0 shadow-sm ring-1 ring-sky-400/50 shadow-sky-500/20 mt-1"
      />

      <div className="flex-1 max-w-[calc(100%-48px)]">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-bold text-xs sm:text-sm text-foreground font-outfit tracking-wide">Horus</span>
          <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-sky-500/10 text-sky-500 border border-sky-500/20 uppercase">
            AI Coordinator
          </span>
          <span className="text-[11px] text-muted-foreground">{message.timestamp}</span>
        </div>

        <div className="rounded-3xl rounded-tl-md px-5 py-4 bg-card border border-border/70 shadow-sm text-sm sm:text-[15px] text-foreground leading-relaxed">
          {renderFormattedText(message.text)}
        </div>

        {/* Action Toolbar */}
        <div className="flex items-center gap-1.5 mt-2 text-muted-foreground">
          {/* Read Aloud Button with dynamic animated wave bars */}
          <button
            onClick={handleSpeak}
            className={`px-2 py-1 rounded-xl text-xs transition-all flex items-center gap-1.5 cursor-pointer border ${
              speaking
                ? "bg-sky-500/15 border-sky-500/40 text-sky-500 shadow-sm"
                : "hover:bg-accent hover:text-foreground border-transparent"
            }`}
            title={speaking ? "Stop reading" : "Read aloud (Audio)"}
          >
            {speaking ? (
              <>
                <VolumeX className="w-3.5 h-3.5 text-sky-500 animate-pulse" />
                <span className="flex items-center gap-0.5 h-3">
                  <span className="w-1 h-2.5 bg-sky-500 rounded-full animate-bounce [animation-delay:0.1s]" />
                  <span className="w-1 h-3.5 bg-sky-500 rounded-full animate-bounce [animation-delay:0.2s]" />
                  <span className="w-1 h-2 bg-sky-500 rounded-full animate-bounce [animation-delay:0.3s]" />
                </span>
                <span className="text-[11px] font-medium text-sky-500">Reading</span>
              </>
            ) : (
              <>
                <Volume2 className="w-3.5 h-3.5" />
                <span className="text-[11px]">Read aloud</span>
              </>
            )}
          </button>

          <button
            onClick={handleCopy}
            className="p-1.5 rounded-lg hover:bg-accent hover:text-foreground text-xs transition-colors inline-flex items-center gap-1 cursor-pointer"
            title="Copy response"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            <span className="text-[11px]">{copied ? "Copied" : "Copy"}</span>
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
