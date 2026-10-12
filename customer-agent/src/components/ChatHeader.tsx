import React from "react";
import { Menu, Moon, Sun, Trash2, Info } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatHeaderProps {
  onToggleSidebar: () => void;
  onOpenAbout: () => void;
  onClearChat: () => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  onToggleSidebar,
  onOpenAbout,
  onClearChat,
  theme,
  onToggleTheme,
}) => {
  return (
    <header className="h-16 px-4 sm:px-6 border-b border-border/80 bg-background/80 backdrop-blur-md flex items-center justify-between shrink-0 z-10">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
          className="text-muted-foreground hover:text-foreground"
        >
          <Menu className="w-5 h-5" />
        </Button>

        <div className="flex items-center gap-3">
          <img
            src="/octapus-logo.jpg"
            alt="Octapus Logo"
            className="w-9 h-9 rounded-2xl object-cover shadow-sm ring-1 ring-border"
          />
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-semibold text-sm sm:text-base text-foreground leading-tight">
                Octapus Coordinator
              </h2>
              <span className="hidden sm:inline-flex text-[10px] font-semibold px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-500 border border-sky-500/20">
                Official
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 leading-tight">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span>Online • Dubai, UAE</span>
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          onClick={onOpenAbout}
          title="About Octapus"
          aria-label="About Octapus"
          className="text-muted-foreground hover:text-foreground"
        >
          <Info className="w-4 h-4" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={onClearChat}
          title="Clear Conversation"
          aria-label="Clear Conversation"
          className="text-muted-foreground hover:text-foreground"
        >
          <Trash2 className="w-4 h-4" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleTheme}
          title="Toggle Theme"
          aria-label="Toggle Theme"
          className="text-muted-foreground hover:text-foreground"
        >
          {theme === "dark" ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
        </Button>
      </div>
    </header>
  );
};
