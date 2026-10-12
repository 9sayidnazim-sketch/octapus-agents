import React, { useRef, useEffect } from "react";
import { ArrowUp, Paperclip, Image as ImageIcon, FileText, Video } from "lucide-react";
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
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleAttachmentClick = (actionName: string) => {
    if (actionName === "file" || actionName === "image") {
      fileInputRef.current?.click();
    } else if (actionName === "document") {
      onChange(value ? `${value}\n\n[Project Specification Document attached]` : "I would like to share my project specification for an individual quote.");
      textareaRef.current?.focus();
    } else if (actionName === "video") {
      onChange(value ? `${value}\n\n[Schedule consultation call]` : "Can we arrange a quick consultation call to discuss our UAE project?");
      textareaRef.current?.focus();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const note = `[Attached: ${file.name}]`;
      onChange(value ? `${value} ${note}` : `I have attached ${file.name} for our project requirements.`);
      textareaRef.current?.focus();
    }
  };

  const hasText = value.trim().length > 0;

  return (
    <div className="w-full max-w-2xl mx-auto px-4 pb-5 pt-2">
      {/* Hidden file input for attachment icons */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Floating Card Container inspired by Iconly design */}
      <div className="group relative bg-white/95 dark:bg-slate-900/90 border border-slate-200/80 dark:border-slate-800/90 rounded-[28px] shadow-[0_14px_45px_-12px_rgba(15,23,42,0.08)] dark:shadow-[0_18px_50px_-12px_rgba(0,0,0,0.65)] backdrop-blur-xl transition-all duration-300 focus-within:border-sky-400/60 focus-within:ring-2 focus-within:ring-sky-400/20">
        
        {/* Top Textarea Section */}
        <div className="px-5 pt-4 pb-2">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Horus..."
            rows={1}
            disabled={isLoading}
            className="w-full bg-transparent border-0 outline-none resize-none text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 text-[15px] sm:text-base leading-relaxed max-h-36 min-h-[28px]"
          />
        </div>

        {/* Faint Horizontal Divider Line */}
        <div className="h-px bg-slate-100 dark:bg-slate-800/80 mx-4" />

        {/* Bottom Actions Row */}
        <div className="px-4 py-2.5 flex items-center justify-between gap-3">
          {/* Action Icons */}
          <div className="flex items-center gap-1 sm:gap-2">
            <button
              type="button"
              onClick={() => handleAttachmentClick("file")}
              title="Attach File"
              className="p-2 text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100/80 dark:hover:bg-slate-800/70 rounded-xl transition-all cursor-pointer"
            >
              <Paperclip className="w-[18px] h-[18px]" />
            </button>

            <button
              type="button"
              onClick={() => handleAttachmentClick("image")}
              title="Upload Image"
              className="p-2 text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100/80 dark:hover:bg-slate-800/70 rounded-xl transition-all cursor-pointer"
            >
              <ImageIcon className="w-[18px] h-[18px]" />
            </button>

            <button
              type="button"
              onClick={() => handleAttachmentClick("document")}
              title="Attach Specification"
              className="p-2 text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100/80 dark:hover:bg-slate-800/70 rounded-xl transition-all cursor-pointer"
            >
              <FileText className="w-[18px] h-[18px]" />
            </button>

            <button
              type="button"
              onClick={() => handleAttachmentClick("video")}
              title="Request Video Consultation"
              className="p-2 text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100/80 dark:hover:bg-slate-800/70 rounded-xl transition-all cursor-pointer"
            >
              <Video className="w-[18px] h-[18px]" />
            </button>
          </div>

          {/* Signature Sky-Blue Gradient Capsule Send Button */}
          <Button
            type="button"
            variant="capsule"
            size="capsule"
            onClick={() => {
              if (hasText && !isLoading) {
                onSend();
              } else {
                textareaRef.current?.focus();
              }
            }}
            disabled={isLoading}
            className={`w-16 sm:w-20 h-10 px-0 flex items-center justify-center transition-all duration-300 ${
              !hasText && !isLoading ? "opacity-90 hover:opacity-100" : ""
            }`}
            aria-label="Send message"
          >
            {isLoading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <ArrowUp className="w-5 h-5 text-white stroke-[2.5]" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
