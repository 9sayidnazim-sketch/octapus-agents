import React, { useState } from "react";
import {
  Menu,
  Plus,
  Clock,
  Settings,
  X,
  MessageSquare,
  Info,
  Moon,
  Sun,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  onOpenAbout: () => void;
  recentTopics: string[];
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onToggle,
  onNewChat,
  onOpenAbout,
  recentTopics,
  theme,
  onToggleTheme,
}) => {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      {/* 1. Permanent Left Icon Rail matching mockup */}
      <aside className="w-16 bg-[#f5f6fb] dark:bg-slate-950 border-r border-slate-200/70 dark:border-slate-800 flex flex-col items-center py-4 justify-between shrink-0 z-30 select-none">
        {/* Top actions in rail */}
        <div className="flex flex-col items-center gap-4 w-full">
          {/* Hamburger Menu Icon */}
          <button
            type="button"
            onClick={onToggle}
            className="p-2 text-slate-700 dark:text-slate-300 hover:text-slate-950 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 rounded-xl transition-colors cursor-pointer"
            title="Toggle Menu & History"
            aria-label="Toggle Menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          {/* Indigo/Blue Square New Chat Button matching mockup */}
          <button
            type="button"
            onClick={onNewChat}
            className="w-10 h-10 rounded-2xl bg-indigo-600 dark:bg-blue-600 text-white flex items-center justify-center shadow-sm shadow-indigo-500/20 hover:scale-105 active:scale-95 transition-all cursor-pointer"
            title="New Chat"
            aria-label="New Chat"
          >
            <Plus className="w-5 h-5 stroke-[2.5]" />
          </button>

          {/* Clock / History Icon */}
          <button
            type="button"
            onClick={onToggle}
            className="p-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 rounded-xl transition-colors cursor-pointer mt-1"
            title="Conversation History"
            aria-label="History"
          >
            <Clock className="w-5 h-5" />
          </button>
        </div>

        {/* Bottom actions in rail */}
        <div className="flex flex-col items-center gap-3">
          {/* Settings Gear Icon */}
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="p-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 rounded-xl transition-colors cursor-pointer"
            title="Settings"
            aria-label="Settings"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </aside>

      {/* 2. Slide-out Drawer for History & Options */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-xs animate-in fade-in lg:hidden"
          onClick={onToggle}
        />
      )}

      <div
        className={`fixed left-16 top-0 bottom-0 z-40 w-72 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col shadow-xl transition-transform duration-300 ease-in-out ${
          isOpen ? "translate-x-0" : "-translate-x-full pointer-events-none"
        }`}
      >
        {/* Header */}
        <div className="p-4 flex items-center justify-between border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <img
              src="/octapus-logo.jpg"
              alt="Horus"
              className="w-7 h-7 rounded-xl object-cover shadow-sm"
            />
            <div>
              <h3 className="font-bold text-sm text-foreground font-outfit">Horus Coordinator</h3>
              <p className="text-[10px] text-muted-foreground">Octapus LLC • Dubai</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onToggle}
            className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-3">
          <Button
            variant="octapus"
            size="default"
            className="w-full justify-start text-xs font-semibold"
            onClick={() => {
              onNewChat();
              if (window.innerWidth < 1024) onToggle();
            }}
          >
            <Plus className="w-4 h-4 mr-2" />
            New Conversation
          </Button>
        </div>

        {/* History List */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
          <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Recent Conversations
          </div>

          {recentTopics.length === 0 ? (
            <div className="px-3 py-6 text-xs text-muted-foreground/70 text-center">
              No previous chats recorded.
            </div>
          ) : (
            recentTopics.map((topic, idx) => (
              <div
                key={idx}
                className="w-full text-left px-3 py-2 rounded-xl text-xs text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors flex items-center gap-2 truncate cursor-pointer"
              >
                <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-60" />
                <span className="truncate">{topic}</span>
              </div>
            ))
          )}
        </div>

        {/* Footer info & controls */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800 space-y-1">
          <button
            type="button"
            onClick={onOpenAbout}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <Info className="w-4 h-4" />
            <span>About Octapus LLC</span>
          </button>

          <button
            type="button"
            onClick={onToggleTheme}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            {theme === "dark" ? (
              <>
                <Sun className="w-4 h-4 text-amber-400" />
                <span>Light Theme</span>
              </>
            ) : (
              <>
                <Moon className="w-4 h-4 text-slate-700" />
                <span>Dark Theme</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Settings Modal */}
      {settingsOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in"
          onClick={() => setSettingsOpen(false)}
        >
          <div
            className="w-full max-w-sm bg-card border border-border rounded-3xl p-5 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <Settings className="w-4 h-4 text-sky-500" />
                <h3 className="font-bold text-sm text-foreground">Horus Preferences</h3>
              </div>
              <button
                onClick={() => setSettingsOpen(false)}
                className="p-1 rounded-lg text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-muted-foreground">
              <div className="flex items-center justify-between py-1">
                <span>Model Speed:</span>
                <span className="font-semibold text-foreground bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">
                  Fast (Default)
                </span>
              </div>
              <div className="flex items-center justify-between py-1">
                <span>Language & Persona:</span>
                <span className="font-semibold text-foreground">Dubai Coordinator</span>
              </div>
              <div className="flex items-center justify-between py-1">
                <span>Speech Synthesis:</span>
                <span className="text-emerald-500 font-semibold">Enabled (Natural)</span>
              </div>
            </div>

            <div className="pt-2">
              <Button
                variant="subtle"
                size="sm"
                className="w-full text-xs"
                onClick={() => setSettingsOpen(false)}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
