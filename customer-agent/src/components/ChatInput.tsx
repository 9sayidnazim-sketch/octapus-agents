import React, { useRef, useEffect, useState } from "react";
import {
  ArrowUp,
  Paperclip,
  Image as ImageIcon,
  FileText,
  Video,
  Mic,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: (text?: string, imageUrl?: string, audioUrl?: string, audioDuration?: string) => void;
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
  const imageInputRef = useRef<HTMLInputElement>(null);

  // Image attachment state
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [imageName, setImageName] = useState<string>("");

  // Audio recording state
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<number | null>(null);
  const speechRecognitionRef = useRef<any>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [value]);

  // Clean up recording timer on unmount
  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
      if (speechRecognitionRef.current) {
        speechRecognitionRef.current.stop();
      }
    };
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleFinalSend();
    }
  };

  const handleFinalSend = () => {
    if (isLoading) return;
    const trimmed = value.trim();
    if (!trimmed && !selectedImage) return;

    onSend(trimmed || "Attached image for review.", selectedImage || undefined);
    setSelectedImage(null);
    setImageName("");
    onChange("");
  };

  // Image handling
  const handleImagePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImageName(file.name);
      const reader = new FileReader();
      reader.onload = () => {
        setSelectedImage(reader.result as string);
        textareaRef.current?.focus();
      };
      reader.readAsDataURL(file);
    }
  };

  // Audio Recording handling
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.start();
      setIsRecording(true);
      setRecordingSeconds(0);

      // Start duration counter
      timerIntervalRef.current = window.setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);

      // Web Speech API for real-time speech-to-text dictation
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";

        recognition.onresult = (event: any) => {
          let transcript = "";
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            transcript += event.results[i][0].transcript;
          }
          if (transcript) {
            onChange(transcript);
          }
        };

        recognition.onerror = () => {};
        recognition.start();
        speechRecognitionRef.current = recognition;
      }
    } catch (err) {
      alert("Microphone permission was denied or is unavailable in your browser.");
    }
  };

  const cancelRecording = () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
    }
    setIsRecording(false);
    setRecordingSeconds(0);
  };

  const stopAndSendRecording = () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
    }

    const durationStr = `${Math.floor(recordingSeconds / 60)}:${(recordingSeconds % 60).toString().padStart(2, "0")}`;

    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm;codecs=opus" });
        const audioUrl = URL.createObjectURL(audioBlob);
        mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());

        const query = value.trim() || `Voice Note (${durationStr})`;
        onSend(query, undefined, audioUrl, durationStr);

        setIsRecording(false);
        setRecordingSeconds(0);
        onChange("");
      };

      if (mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    } else {
      setIsRecording(false);
    }
  };

  const handleAttachmentClick = (actionName: string) => {
    if (actionName === "file") {
      fileInputRef.current?.click();
    } else if (actionName === "image") {
      imageInputRef.current?.click();
    } else if (actionName === "document") {
      onChange(value ? `${value}\n\n[Project Specification Document attached]` : "I would like to share our project specification for an individual quote.");
      textareaRef.current?.focus();
    } else if (actionName === "video") {
      onChange(value ? `${value}\n\n[Request consultation call]` : "Can we arrange a quick consultation call to discuss our UAE project?");
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

  const hasContent = value.trim().length > 0 || selectedImage !== null;

  return (
    <div className="w-full max-w-2xl mx-auto px-4 pb-5 pt-2">
      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFileChange}
      />
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleImagePick}
      />

      {/* Floating Card Container inspired by Iconly design */}
      <div className="group relative bg-white/95 dark:bg-slate-900/90 border border-slate-200/80 dark:border-slate-800/90 rounded-[28px] shadow-[0_14px_45px_-12px_rgba(15,23,42,0.08)] dark:shadow-[0_18px_50px_-12px_rgba(0,0,0,0.65)] backdrop-blur-xl transition-all duration-300 focus-within:border-sky-400/60 focus-within:ring-2 focus-within:ring-sky-400/20">
        
        {/* Image Attachment Preview Strip */}
        {selectedImage && (
          <div className="px-5 pt-3 flex items-center gap-2">
            <div className="relative group/img rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800">
              <img src={selectedImage} alt="Attachment" className="h-16 w-16 object-cover" />
              <button
                type="button"
                onClick={() => setSelectedImage(null)}
                className="absolute top-1 right-1 p-0.5 rounded-full bg-black/60 text-white hover:bg-black/80 transition-colors cursor-pointer"
                title="Remove image"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
            <div className="text-xs text-muted-foreground truncate max-w-[200px]">
              <span className="font-medium text-foreground block truncate">{imageName || "Image attached"}</span>
              <span>Ready to send with prompt</span>
            </div>
          </div>
        )}

        {/* Normal Mode vs Live Audio Recording Mode */}
        {!isRecording ? (
          <>
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
                  title="Upload / Add Image"
                  className="p-2 text-slate-400 dark:text-slate-500 hover:text-sky-500 dark:hover:text-sky-400 hover:bg-sky-50 dark:hover:bg-sky-950/40 rounded-xl transition-all cursor-pointer"
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

                {/* Microphone / Audio Recording Trigger */}
                <button
                  type="button"
                  onClick={startRecording}
                  title="Record Voice Note"
                  className="p-2 text-slate-400 dark:text-slate-500 hover:text-sky-500 dark:hover:text-sky-400 hover:bg-sky-50 dark:hover:bg-sky-950/40 rounded-xl transition-all cursor-pointer"
                >
                  <Mic className="w-[18px] h-[18px]" />
                </button>
              </div>

              {/* Signature Sky-Blue Gradient Capsule Send Button */}
              <Button
                type="button"
                variant="capsule"
                size="capsule"
                onClick={handleFinalSend}
                disabled={isLoading}
                className={`w-16 sm:w-20 h-10 px-0 flex items-center justify-center transition-all duration-300 ${
                  !hasContent && !isLoading ? "opacity-90 hover:opacity-100" : ""
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
          </>
        ) : (
          /* Live Audio Recording Panel */
          <div className="p-4 flex items-center justify-between gap-3 animate-in fade-in duration-200">
            <div className="flex items-center gap-3">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
              </span>

              <span className="font-mono text-sm font-semibold text-foreground">
                {Math.floor(recordingSeconds / 60)}:{(recordingSeconds % 60).toString().padStart(2, "0")}
              </span>

              {/* Equalizer animation */}
              <div className="flex items-center gap-1 h-5 px-2">
                {[60, 100, 40, 80, 50, 90, 70].map((h, idx) => (
                  <span
                    key={idx}
                    className="w-1 bg-sky-500 rounded-full animate-pulse"
                    style={{
                      height: `${h}%`,
                      animationDelay: `${idx * 0.1}s`,
                    }}
                  />
                ))}
              </div>

              <span className="text-xs text-muted-foreground hidden sm:inline">
                {value ? `"${value}"` : "Listening..."}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={cancelRecording}
                className="p-2 rounded-xl text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors cursor-pointer"
                title="Cancel recording"
              >
                <Trash2 className="w-4 h-4" />
              </button>

              <Button
                type="button"
                variant="capsule"
                size="sm"
                onClick={stopAndSendRecording}
                className="h-9 px-4 flex items-center gap-1.5"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Send Note</span>
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
