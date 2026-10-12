import React from "react";
import { Image as ImageIcon, FileText, Lightbulb } from "lucide-react";

interface HeroStateProps {
  onSelectPrompt: (prompt: string) => void;
}

export const HeroState: React.FC<HeroStateProps> = ({ onSelectPrompt }) => {
  const suggestions = [
    {
      title: "Create an image",
      icon: ImageIcon,
      prompt: "What website design, creative branding, and visual digital services does Octapus provide?",
    },
    {
      title: "Write something",
      icon: FileText,
      prompt: "Tell me about ERP software solutions by Octapus, including for tailoring workshops in the UAE.",
    },
    {
      title: "Explore an idea",
      icon: Lightbulb,
      prompt: "How does Octapus help connect payment gateways and POS systems to websites?",
    },
  ];

  return (
    <div className="w-full max-w-2xl mx-auto my-auto py-6 px-4 flex flex-col items-center text-center animate-in fade-in duration-300">
      
      {/* 1. Horus Mascot Logo matching mockup */}
      <div className="mb-6">
        <img
          src="/octapus-logo.jpg"
          alt="Horus Mascot"
          className="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl object-cover shadow-sm ring-1 ring-slate-200/50 dark:ring-slate-800"
        />
      </div>

      {/* 2. Main Headline matching mockup */}
      <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-2 font-outfit">
        <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-sky-400 bg-clip-text text-transparent">
          Hello, Alex
        </span>
      </h1>

      <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 dark:text-white tracking-tight mb-8 font-outfit">
        What can I help you with?
      </h2>

      {/* 3. Three Capability / Suggestion Pills in a horizontal row */}
      <div className="flex flex-wrap items-center justify-center gap-3 w-full">
        {suggestions.map((item, idx) => {
          const Icon = item.icon;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectPrompt(item.prompt)}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200/90 dark:border-slate-800 text-slate-700 dark:text-slate-200 text-sm font-medium shadow-xs hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-sm hover:scale-[1.02] active:scale-[0.98] transition-all cursor-pointer"
            >
              <Icon className="w-4 h-4 text-slate-700 dark:text-slate-300 stroke-[1.75]" />
              <span>{item.title}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
