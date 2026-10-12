import React from "react";
import { Plus, MessageSquare, Info, Moon, Sun, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onOpenAbout: () => void;
  recentTopics: string[];
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onClose,
  onNewChat,
  onOpenAbout,
  recentTopics,
  theme,
  onToggleTheme,
}) => {
  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden animate-in fade-in"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed lg:static top-0 bottom-0 left-0 z-40 w-72 bg-card border-r border-border/80 flex flex-col transition-transform duration-300 ease-in-out ${
          isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        } ${!isOpen ? "lg:hidden" : ""}`}
      >
        {/* Brand header */}
        <div className="p-4 flex items-center justify-between border-b border-border/60">
          <div className="flex items-center gap-3">
            <img
              src="/octapus-logo.jpg"
              alt="Octapus Mascot"
              className="w-8 h-8 rounded-xl object-cover shadow-sm ring-1 ring-border"
            />
            <div>
              <span className="font-semibold text-sm text-foreground">Octapus LLC</span>
              <p className="text-[10px] text-muted-foreground">Dubai Digital Partner</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="lg:hidden text-muted-foreground"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* New Chat Button */}
        <div className="p-4">
          <Button
            variant="octapus"
            className="w-full justify-start text-sm font-medium"
            onClick={() => {
              onNewChat();
              if (window.innerWidth < 1024) onClose();
            }}
          >
            <Plus className="w-4 h-4 mr-2" />
            New Conversation
          </Button>
        </div>

        {/* Recent topics */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
          <div className="px-3 py-1.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Recent Topics
          </div>
          {recentTopics.length === 0 ? (
            <div className="px-3 py-4 text-xs text-muted-foreground/70 text-center">
              No recent conversations yet.
            </div>
          ) : (
            recentTopics.map((topic, idx) => (
              <div
                key={idx}
                className="w-full text-left px-3 py-2.5 rounded-xl text-xs text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors flex items-center gap-2.5 truncate"
              >
                <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70" />
                <span className="truncate">{topic}</span>
              </div>
            ))
          )}
        </div>

        {/* Footer controls */}
        <div className="p-3 border-t border-border/60 space-y-1">
          <Button
            variant="ghost"
            className="w-full justify-start text-xs text-muted-foreground hover:text-foreground"
            onClick={onOpenAbout}
          >
            <Info className="w-4 h-4 mr-2.5" />
            About Octapus LLC
          </Button>

          <Button
            variant="ghost"
            className="w-full justify-start text-xs text-muted-foreground hover:text-foreground"
            onClick={onToggleTheme}
          >
            {theme === "dark" ? (
              <>
                <Sun className="w-4 h-4 mr-2.5 text-amber-400" /> Light Mode
              </>
            ) : (
              <>
                <Moon className="w-4 h-4 mr-2.5 text-slate-700" /> Dark Mode
              </>
            )}
          </Button>
        </div>
      </aside>
    </>
  );
};
