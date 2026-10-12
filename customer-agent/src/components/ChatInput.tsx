import React, { useRef, useEffect, useState } from "react";
import {
  Send,
  Plus,
  Mic,
  ChevronDown,
  Trash2,
  Square,
  X,
  Image as ImageIcon,
  FileText,
  Video,
} from "lucide-react";

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

  // Attachment state
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [imageName, setImageName] = useState<string>("");
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const [modelSpeed, setModelSpeed] = useState("Fast");
  const [speedMenuOpen, setSpeedMenuOpen] = useState(false);

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

  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
      if (speechRecognitionRef.current) {
        try { speechRecognitionRef.current.stop(); } catch (_) {}
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
      e.target.value = "";
    }
  };

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onChange(value ? `${value} [Attached: ${file.name}]` : `I have attached ${file.name} for our project requirements.`);
      textareaRef.current?.focus();
      e.target.value = "";
    }
  };

  // Audio Recording handling
  const startRecording = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert("Audio recording is not supported on this browser.");
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      let mimeType = "";
      if (typeof MediaRecorder !== "undefined" && typeof MediaRecorder.isTypeSupported === "function") {
        if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
          mimeType = "audio/webm;codecs=opus";
        } else if (MediaRecorder.isTypeSupported("audio/webm")) {
          mimeType = "audio/webm";
        } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
          mimeType = "audio/mp4";
        }
      }

      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.start(250);
      setIsRecording(true);
      setRecordingSeconds(0);

      timerIntervalRef.current = window.setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);

      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        try {
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
        } catch (_) {}
      }
    } catch {
      alert("Microphone permission was denied or is unavailable.");
    }
  };

  const cancelRecording = () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream?.getTracks().forEach((track) => track.stop());
    }
    if (speechRecognitionRef.current) {
      try { speechRecognitionRef.current.stop(); } catch (_) {}
    }
    setIsRecording(false);
    setRecordingSeconds(0);
  };

  const stopAndSendRecording = () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    if (speechRecognitionRef.current) {
      try { speechRecognitionRef.current.stop(); } catch (_) {}
    }

    const durationStr = `${Math.floor(recordingSeconds / 60)}:${(recordingSeconds % 60).toString().padStart(2, "0")}`;

    if (mediaRecorderRef.current) {
      const mime = mediaRecorderRef.current.mimeType || "audio/webm";
      mediaRecorderRef.current.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mime });
        const audioUrl = URL.createObjectURL(audioBlob);
        mediaRecorderRef.current?.stream?.getTracks().forEach((track) => track.stop());

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

  const hasContent = value.trim().length > 0 || selectedImage !== null;

  return (
    <div className="w-full max-w-3xl mx-auto px-4 pb-3 pt-2">
      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFilePick}
      />
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleImagePick}
      />

      {/* Floating Card Container matching mockup */}
      <div className="relative bg-[#f4f5fa] dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-[28px] p-4 sm:p-5 shadow-xs transition-all focus-within:border-blue-400/80 focus-within:ring-2 focus-within:ring-blue-500/15">
        
        {/* Image Attachment Preview Strip */}
        {selectedImage && (
          <div className="mb-2 flex items-center gap-2">
            <div className="relative rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
              <img src={selectedImage} alt="Attachment" className="h-14 w-14 object-cover" />
              <button
                type="button"
                onClick={() => setSelectedImage(null)}
                className="absolute top-1 right-1 p-0.5 rounded-full bg-black/60 text-white hover:bg-black/80 cursor-pointer"
                title="Remove image"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
            <div className="text-xs text-muted-foreground truncate">
              <span className="font-medium text-foreground block truncate">{imageName || "Image attached"}</span>
              <span>Ready to submit</span>
            </div>
          </div>
        )}

        {!isRecording ? (
          <>
            {/* Top Textarea Section */}
            <div className="w-full">
              <textarea
                ref={textareaRef}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask Horus"
                rows={1}
                disabled={isLoading}
                className="w-full bg-transparent border-0 outline-none resize-none text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 text-base leading-relaxed max-h-36 min-h-[32px]"
              />
            </div>

            {/* Bottom Controls matching mockup */}
            <div className="flex items-center justify-between pt-3 relative">
              {/* Left: Circle + Button */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setAttachMenuOpen(!attachMenuOpen)}
                  className="w-9 h-9 rounded-full bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700 text-slate-600 dark:text-slate-300 shadow-xs flex items-center justify-center hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                  title="Add attachment"
                >
                  <Plus className="w-4 h-4" />
                </button>

                {/* Attachment Menu Popup */}
                {attachMenuOpen && (
                  <div
                    className="absolute left-0 bottom-12 w-48 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl p-1.5 z-50 animate-in fade-in"
                    onClick={() => setAttachMenuOpen(false)}
                  >
                    <button
                      type="button"
                      onClick={() => imageInputRef.current?.click()}
                      className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                    >
                      <ImageIcon className="w-4 h-4 text-sky-500" />
                      <span>Upload Image</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                    >
                      <FileText className="w-4 h-4 text-indigo-500" />
                      <span>Attach Document</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        onChange("Can we schedule a consultation call to discuss our UAE project?");
                        textareaRef.current?.focus();
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                    >
                      <Video className="w-4 h-4 text-emerald-500" />
                      <span>Book Consultation</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Right: Fast ⌵ + Mic + Send */}
              <div className="flex items-center gap-2">
                {/* Fast ⌵ Capsule Dropdown */}
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setSpeedMenuOpen(!speedMenuOpen)}
                    className="rounded-full px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700 shadow-xs flex items-center gap-1 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                  >
                    <span>{modelSpeed}</span>
                    <ChevronDown className="w-3 h-3 text-slate-400" />
                  </button>

                  {speedMenuOpen && (
                    <div
                      className="absolute right-0 bottom-10 w-32 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-lg p-1 z-50 animate-in fade-in"
                      onClick={() => setSpeedMenuOpen(false)}
                    >
                      <button
                        onClick={() => setModelSpeed("Fast")}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                      >
                        Fast
                      </button>
                      <button
                        onClick={() => setModelSpeed("Thinking")}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                      >
                        Thinking
                      </button>
                    </div>
                  )}
                </div>

                {/* Mic Audio Recording Circle */}
                <button
                  type="button"
                  onClick={startRecording}
                  className="w-9 h-9 rounded-full bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700 text-slate-600 dark:text-slate-300 shadow-xs flex items-center justify-center hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                  title="Voice Note"
                >
                  <Mic className="w-4 h-4" />
                </button>

                {/* Send Paper Plane Circle Button matching mockup */}
                <button
                  type="button"
                  onClick={handleFinalSend}
                  disabled={isLoading || !hasContent}
                  className={`w-10 h-10 rounded-full flex items-center justify-center transition-all cursor-pointer ${
                    hasContent && !isLoading
                      ? "bg-blue-600 text-white shadow-md shadow-blue-500/25 hover:bg-blue-700 active:scale-95"
                      : "bg-blue-600/70 text-white/80 cursor-default"
                  }`}
                  aria-label="Send"
                >
                  {isLoading ? (
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <Send className="w-4 h-4 ml-0.5 fill-current" />
                  )}
                </button>
              </div>
            </div>
          </>
        ) : (
          /* Live Audio Recording Panel */
          <div className="py-2 flex items-center justify-between gap-3 animate-in fade-in duration-200">
            <div className="flex items-center gap-3">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
              </span>

              <span className="font-mono text-sm font-semibold text-foreground">
                {Math.floor(recordingSeconds / 60)}:{(recordingSeconds % 60).toString().padStart(2, "0")}
              </span>

              <div className="flex items-center gap-1 h-5 px-2">
                {[60, 100, 40, 80, 50, 90, 70].map((h, idx) => (
                  <span
                    key={idx}
                    className="w-1 bg-blue-600 rounded-full animate-pulse"
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

              <button
                type="button"
                onClick={stopAndSendRecording}
                className="h-9 px-4 rounded-full bg-blue-600 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm hover:bg-blue-700 active:scale-95 cursor-pointer"
              >
                <Square className="w-3 h-3 fill-current" />
                <span>Send Note</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer Disclaimer matching mockup */}
      <p className="text-[11px] text-slate-400 dark:text-slate-500 text-center mt-2.5 pb-1 select-none">
        Horus can make mistakes. Check important details.
      </p>
    </div>
  );
};
