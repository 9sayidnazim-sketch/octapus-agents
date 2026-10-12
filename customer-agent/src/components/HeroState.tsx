import React from "react";
import { Globe, CreditCard, Scissors, FileText, ArrowUpRight } from "lucide-react";

interface HeroStateProps {
  onSelectPrompt: (prompt: string) => void;
}

export const HeroState: React.FC<HeroStateProps> = ({ onSelectPrompt }) => {
  const cards = [
    {
      title: "Custom Web Engineering",
      description: "Modern, high-performance web software designed for UAE business scale.",
      prompt: "What website and web app development services does Octapus provide?",
      icon: Globe,
      color: "text-sky-500",
    },
    {
      title: "Payment Integration",
      description: "Connect payment gateways & POS directly with websites and accounting.",
      prompt: "How does payment integration work for websites and POS systems?",
      icon: CreditCard,
      color: "text-emerald-500",
    },
    {
      title: "Tailoring Workshop ERP",
      description: "Bespoke ERP software for custom tailor measurements, orders, and workflow.",
      prompt: "Tell me about ERP software for tailoring workshops in the UAE.",
      icon: Scissors,
      color: "text-indigo-500",
    },
    {
      title: "Individual Proposal",
      description: "Submit specs through our online requirement form or request an initial quote.",
      prompt: "How do I get an individual project quote from Octapus?",
      icon: FileText,
      color: "text-amber-500",
    },
  ];

  return (
    <div className="w-full max-w-2xl mx-auto my-auto py-8 px-4 flex flex-col items-center text-center animate-in fade-in duration-400">
      
      {/* Brand Header matching "HORUS by Octapus" */}
      <div className="mb-4 flex flex-col items-center">
        <h2 className="text-2xl sm:text-3xl font-bold tracking-[0.22em] text-foreground font-outfit uppercase">
          HORUS
        </h2>
        <span className="text-[11px] sm:text-xs tracking-[0.25em] font-medium text-sky-500 dark:text-sky-400 uppercase mt-0.5">
          by Octapus
        </span>
      </div>

      {/* Luminous Horus Mascot Artwork Container */}
      <div className="relative mb-5 group">
        {/* Ambient Radial Blue Backlight */}
        <div className="absolute -inset-3 bg-gradient-to-tr from-sky-500/30 via-blue-600/30 to-indigo-600/30 blur-2xl rounded-[36px] opacity-80 group-hover:opacity-100 transition-opacity duration-500" />
        
        {/* Crystal Squircle Frame */}
        <div className="relative w-32 h-32 sm:w-40 sm:h-40 rounded-[28px] sm:rounded-[34px] overflow-hidden shadow-[0_20px_50px_rgba(14,165,233,0.35)] ring-1 ring-sky-400/40 border border-sky-300/30 bg-slate-950">
          <img
            src="/horus.jpg"
            alt="HORUS by Octapus"
            className="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-500"
          />
        </div>
      </div>

      {/* Tagline matching reference poster */}
      <h1 className="text-xl sm:text-2xl font-normal tracking-wide text-foreground font-outfit mb-1">
        A brighter intelligence.
      </h1>

      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sky-500/10 border border-sky-500/20 text-[11px] font-medium text-sky-600 dark:text-sky-400 mb-6">
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        AI Coordinator • Dubai, UAE
      </div>

      {/* Quick Prompt Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full text-left">
        {cards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <button
              key={idx}
              onClick={() => onSelectPrompt(card.prompt)}
              className="group relative p-3.5 rounded-2xl bg-white/70 dark:bg-slate-900/60 hover:bg-white dark:hover:bg-slate-900 border border-slate-200/80 dark:border-slate-800/80 hover:border-sky-400/50 shadow-sm hover:shadow-md transition-all duration-200 flex flex-col justify-between h-28 cursor-pointer active:scale-[0.99] backdrop-blur-sm"
            >
              <div className="flex items-start justify-between w-full">
                <div className={`p-1.5 rounded-xl bg-slate-100 dark:bg-slate-800/80 ${card.color} group-hover:scale-110 transition-transform duration-200`}>
                  <Icon className="w-4 h-4" />
                </div>
                <ArrowUpRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:text-sky-500 transition-all duration-200" />
              </div>
              <div>
                <h4 className="font-semibold text-xs sm:text-sm text-foreground mb-0.5 group-hover:text-sky-500 transition-colors">
                  {card.title}
                </h4>
                <p className="text-[11px] text-muted-foreground line-clamp-1 leading-normal">
                  {card.description}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
