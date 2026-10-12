import React from "react";
import { Globe, CreditCard, Scissors, FileText, ArrowUpRight } from "lucide-react";

interface HeroStateProps {
  onSelectPrompt: (prompt: string) => void;
}

export const HeroState: React.FC<HeroStateProps> = ({ onSelectPrompt }) => {
  const cards = [
    {
      title: "Website & Web Apps",
      description: "Custom responsive web engineering tailored for Dubai & UAE businesses.",
      prompt: "What website and web app development services does Octapus provide?",
      icon: Globe,
      color: "text-blue-500",
    },
    {
      title: "Payment Integration",
      description: "Connect your payment provider or POS to your digital storefront.",
      prompt: "How does payment integration work for websites and POS systems?",
      icon: CreditCard,
      color: "text-emerald-500",
    },
    {
      title: "Tailoring Workshop ERP",
      description: "Specialized ERP software managing custom measurements and workflows.",
      prompt: "Tell me about ERP software for tailoring workshops in the UAE.",
      icon: Scissors,
      color: "text-indigo-500",
    },
    {
      title: "Request a Proposal",
      description: "Learn how individual project quotes and consultations work.",
      prompt: "How do I get an individual project quote from Octapus?",
      icon: FileText,
      color: "text-amber-500",
    },
  ];

  return (
    <div className="w-full max-w-3xl mx-auto my-auto py-8 px-4 flex flex-col items-center text-center animate-in fade-in duration-300">
      {/* Octapus Mascot Logo */}
      <div className="relative mb-6 group">
        <div className="absolute -inset-1 rounded-3xl bg-gradient-to-r from-sky-400 via-blue-500 to-indigo-500 opacity-40 blur-xl group-hover:opacity-70 transition duration-500" />
        <img
          src="/octapus-logo.jpg"
          alt="Octapus Mascot"
          className="relative w-20 h-20 rounded-3xl shadow-xl object-cover ring-2 ring-white/20"
        />
      </div>

      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-600 dark:text-sky-400 text-xs font-medium mb-3">
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        Octapus AI Coordinator • Dubai, UAE
      </div>

      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-foreground mb-3 font-outfit">
        Welcome to Octapus
      </h1>
      <p className="text-sm sm:text-base text-muted-foreground max-w-lg mb-8 leading-relaxed">
        I’m your digital coordinator. Whether you're planning custom web software, payment integrations, or enterprise ERP, I'm here to guide you.
      </p>

      {/* Suggestion Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 w-full text-left">
        {cards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <button
              key={idx}
              onClick={() => onSelectPrompt(card.prompt)}
              className="group relative p-4 rounded-2xl bg-card hover:bg-accent/40 border border-border/80 hover:border-sky-500/40 shadow-sm hover:shadow-md transition-all duration-200 flex flex-col justify-between h-32 cursor-pointer active:scale-[0.99]"
            >
              <div className="flex items-start justify-between w-full">
                <div className={`p-2 rounded-xl bg-muted/60 ${card.color} group-hover:scale-110 transition-transform duration-200`}>
                  <Icon className="w-4 h-4" />
                </div>
                <ArrowUpRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:text-sky-500 transition-all duration-200" />
              </div>
              <div>
                <h4 className="font-semibold text-sm text-foreground mb-1 group-hover:text-sky-500 transition-colors">
                  {card.title}
                </h4>
                <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
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
