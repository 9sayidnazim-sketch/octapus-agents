import React, { useState } from "react";
import { ChevronDown, Moon, Sun, Trash2, Info, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatHeaderProps {
  onToggleSidebar: () => void;
  onOpenAbout: () => void;
  onClearChat: () => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  onOpenAbout,
  onClearChat,
  theme,
  onToggleTheme,
}) => {
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [activeModel, setActiveModel] = useState("Fast");
  const [profileOpen, setProfileOpen] = useState(false);

  return (
    <header className="h-16 px-6 bg-transparent flex items-center justify-between shrink-0 z-20 select-none">
      {/* Left: Horus ⌵ / by Octapus matching mockup */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
          className="text-left group cursor-pointer focus:outline-none"
        >
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-lg text-slate-900 dark:text-white font-outfit tracking-tight group-hover:text-blue-600 transition-colors">
              Horus
            </span>
            <ChevronDown className="w-4 h-4 text-slate-500 group-hover:text-blue-600 transition-colors" />
          </div>
          <p className="text-[11px] text-slate-400 font-medium tracking-wide">
            by Octapus
          </p>
        </button>

        {/* Model Selector Dropdown */}
        {modelDropdownOpen && (
          <div
            className="absolute left-0 mt-2 w-56 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl p-2 z-50 animate-in fade-in"
            onClick={() => setModelDropdownOpen(false)}
          >
            <div className="px-2 py-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              AI Persona & Engine
            </div>

            <button
              onClick={() => setActiveModel("Fast")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs transition-colors cursor-pointer ${
                activeModel === "Fast"
                  ? "bg-blue-50 dark:bg-blue-950/40 text-blue-600 font-semibold"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300"
              }`}
            >
              <div className="flex flex-col text-left">
                <span>Horus Fast</span>
                <span className="text-[10px] text-slate-400 font-normal">Real-time coordinator</span>
              </div>
              {activeModel === "Fast" && <Check className="w-4 h-4 text-blue-600" />}
            </button>

            <button
              onClick={() => setActiveModel("Pro")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs transition-colors cursor-pointer ${
                activeModel === "Pro"
                  ? "bg-blue-50 dark:bg-blue-950/40 text-blue-600 font-semibold"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300"
              }`}
            >
              <div className="flex flex-col text-left">
                <span>Horus Thinking</span>
                <span className="text-[10px] text-slate-400 font-normal">Deep solution analysis</span>
              </div>
              {activeModel === "Pro" && <Check className="w-4 h-4 text-blue-600" />}
            </button>
          </div>
        )}
      </div>

      {/* Right: Actions & User Avatar matching mockup */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={onClearChat}
          title="Clear Conversation"
          aria-label="Clear Conversation"
          className="text-slate-400 hover:text-slate-800 dark:hover:text-white"
        >
          <Trash2 className="w-4 h-4" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleTheme}
          title="Toggle Theme"
          aria-label="Toggle Theme"
          className="text-slate-400 hover:text-slate-800 dark:hover:text-white"
        >
          {theme === "dark" ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
        </Button>

        {/* User Profile Avatar with dropdown */}
        <div className="relative ml-2">
          <button
            type="button"
            onClick={() => setProfileOpen(!profileOpen)}
            className="w-9 h-9 rounded-full ring-2 ring-slate-200 dark:ring-slate-700 shadow-sm overflow-hidden flex items-center justify-center bg-gradient-to-tr from-blue-600 to-indigo-600 text-white font-bold text-xs hover:scale-105 active:scale-95 transition-transform cursor-pointer"
            title="User Profile"
          >
            <span>A</span>
          </button>

          {profileOpen && (
            <div
              className="absolute right-0 mt-2 w-48 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl p-2 z-50 animate-in fade-in"
              onClick={() => setProfileOpen(false)}
            >
              <div className="px-3 py-2 border-b border-slate-100 dark:border-slate-800">
                <p className="text-xs font-bold text-slate-900 dark:text-white">Alex</p>
                <p className="text-[11px] text-slate-400">Octapus Client</p>
              </div>

              <button
                onClick={onOpenAbout}
                className="w-full text-left px-3 py-2 rounded-xl text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors flex items-center gap-2 cursor-pointer mt-1"
              >
                <Info className="w-3.5 h-3.5" />
                <span>About Octapus</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
