import React, { useRef, useEffect } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  isLoading: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  value,
  onChange,
  onSend,
  isLoading,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !isLoading) {
        onSend();
      }
    }
  };

  const hasText = value.trim().length > 0;

  return (
    <div className="w-full max-w-3xl mx-auto px-4 pb-4 pt-2">
      <div className="relative flex items-end gap-2 bg-card border border-border/80 focus-within:border-sky-500/80 focus-within:ring-2 focus-within:ring-sky-500/20 rounded-3xl p-2 sm:p-2.5 shadow-lg shadow-black/5 transition-all">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask our coordinator about our UAE services..."
          rows={1}
          disabled={isLoading}
          className="flex-1 bg-transparent border-0 outline-none resize-none text-foreground placeholder:text-muted-foreground text-sm sm:text-[15px] px-3 py-1.5 leading-relaxed max-h-36 min-h-[24px]"
        />

        <Button
          type="button"
          size="icon"
          variant={hasText ? "octapus" : "subtle"}
          onClick={onSend}
          disabled={!hasText || isLoading}
          className="shrink-0 rounded-2xl w-9 h-9 sm:w-10 sm:h-10 transition-all duration-200"
          aria-label="Send prompt"
        >
          {isLoading ? (
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <ArrowUp className="w-4 h-4" />
          )}
        </Button>
      </div>
    </div>
  );
};
