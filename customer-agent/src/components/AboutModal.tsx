import React from "react";
import { X, Globe, Mail, MapPin, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

interface AboutModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AboutModal: React.FC<AboutModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg bg-card text-card-foreground border border-border rounded-3xl p-6 shadow-2xl overflow-hidden scale-100 transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <img
              src="/octapus-logo.jpg"
              alt="Octapus Logo"
              className="w-10 h-10 rounded-xl object-cover shadow-sm"
            />
            <div>
              <h3 className="font-semibold text-lg text-foreground">Octapus LLC</h3>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <MapPin className="w-3 h-3 text-sky-500" /> Dubai, United Arab Emirates
              </p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close modal">
            <X className="w-5 h-5 text-muted-foreground hover:text-foreground" />
          </Button>
        </div>

        <div className="py-4 space-y-4 text-sm text-muted-foreground leading-relaxed">
          <p>
            <strong className="text-foreground">Octapus LLC</strong> is a Dubai-based software engineering and digital solutions company delivering premium technology across the UAE and GCC.
          </p>

          <div className="bg-muted/50 rounded-2xl p-4 border border-border/50 space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-foreground flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-sky-500" /> Core Capabilities
            </div>
            <ul className="list-disc list-inside space-y-1 text-xs text-muted-foreground">
              <li>High-Performance Website Design & Web Applications</li>
              <li>Payment Gateway & POS Integrations</li>
              <li>Bespoke Tailoring Workshop & Enterprise ERP</li>
              <li>WhatsApp Business Cloud API Automations</li>
              <li>Brand Identity, Creative Direction & Search Optimization</li>
            </ul>
          </div>

          <p className="text-xs">
            Every engagement is planned individually. Share your requirements to receive a personalized proposal.
          </p>
        </div>

        <div className="pt-2 flex flex-col sm:flex-row gap-2">
          <Button
            variant="octapus"
            className="flex-1"
            onClick={() => window.open("mailto:info@octapus.ae", "_blank")}
          >
            <Mail className="w-4 h-4 mr-2" /> Email info@octapus.ae
          </Button>
          <Button
            variant="outline"
            onClick={() => window.open("https://octapus.ae", "_blank")}
          >
            <Globe className="w-4 h-4 mr-2" /> octapus.ae
          </Button>
        </div>
      </div>
    </div>
  );
};
