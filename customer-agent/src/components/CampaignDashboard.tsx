import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Send,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Users,
  MessageSquare,
  Radio,
  HelpCircle,
  Lock,
  Unlock,
  Check,
  Smartphone,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface Recipient {
  phone_number: string;
  clean_number: string;
  formatted: string;
  country: string;
  country_code: string;
  is_valid: boolean;
  validation_error?: string | null;
  role_or_note?: string | null;
}

interface LogEntry {
  id: string;
  campaign_id: string;
  phone_number: string;
  clean_number: string;
  country: string;
  is_test: number | boolean;
  status: string;
  attempts: number;
  error_details?: string | null;
  delivered_at?: string | null;
  created_at: string;
  updated_at?: string | null;
}

interface WorkflowState {
  campaign_id: string;
  name: string;
  status: string;
  test_mode: boolean;
  test_recipient: string | null;
  test_approved: boolean;
  tone: string;
  message_template: string;
  message_stats: {
    character_count: number;
    word_count: number;
    estimated_read_seconds: number;
  };
  recipients: Recipient[];
  gateway_status: {
    gateway_url: string;
    is_online: boolean;
    token_configured: boolean;
    connected_phone: string | null;
    instance_id: string | null;
    method: string;
  };
  stats: {
    total_recipients: number;
    test_messages_sent: number;
    delivered: number;
    failed: number;
    pending: number;
    skipped: number;
  };
  logs: LogEntry[];
  latest_test_result?: LogEntry | null;
  ready_for_rollout: boolean;
}

interface CampaignDashboardProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CampaignDashboard: React.FC<CampaignDashboardProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<"recipients" | "message" | "test" | "rollout" | "guide">(
    "recipients"
  );
  const [state, setState] = useState<WorkflowState | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form states
  const [editableTemplate, setEditableTemplate] = useState<string>("");
  const [selectedTone, setSelectedTone] = useState<string>("warm_professional");
  const [testNumberInput, setTestNumberInput] = useState<string>("");
  const [rolloutConfirmed, setRolloutConfirmed] = useState<boolean>(false);

  const fetchWorkflow = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await fetch("/api/campaign/workflow");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: WorkflowState = await res.json();
      setState(data);
      setEditableTemplate(data.message_template);
      setSelectedTone(data.tone || "warm_professional");
      if (data.test_recipient && !testNumberInput) {
        setTestNumberInput(data.test_recipient);
      }
    } catch (err: any) {
      setErrorMsg(`Failed to connect to Campaign API: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchWorkflow();
    }
  }, [isOpen]);

  const handleSaveTemplate = async () => {
    try {
      setActionLoading(true);
      setErrorMsg(null);
      const res = await fetch("/api/campaign/template", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template: editableTemplate, tone: selectedTone }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Save failed");
      }
      const updated = await res.json();
      setState(updated);
      setSuccessMsg("Message template and tone settings saved successfully.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleToneChange = async (toneKey: string) => {
    setSelectedTone(toneKey);
    try {
      setActionLoading(true);
      const res = await fetch("/api/campaign/template", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template: "", tone: toneKey }),
      });
      if (res.ok) {
        const updated = await res.json();
        setState(updated);
        setEditableTemplate(updated.message_template);
      }
    } catch (_) {
    } finally {
      setActionLoading(false);
    }
  };

  const handleSetTestRecipient = async (phone: string) => {
    try {
      setActionLoading(true);
      setErrorMsg(null);
      const res = await fetch("/api/campaign/test-recipient", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phone }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Validation failed");
      }
      setTestNumberInput(phone);
      await fetchWorkflow();
      setSuccessMsg(`Configured test recipient: ${phone}`);
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendTestMessage = async () => {
    if (!testNumberInput) {
      setErrorMsg("Please enter or select a test recipient phone number.");
      return;
    }
    try {
      setActionLoading(true);
      setErrorMsg(null);
      const res = await fetch("/api/campaign/send-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ test_number: testNumberInput }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Test delivery failed");
      }
      await fetchWorkflow();
      if (data.success) {
        setSuccessMsg(`Test message delivered to ${data.recipient}! Please review and approve.`);
      } else {
        setErrorMsg(`Test message failed: ${data.error_details || "Unknown gateway issue"}`);
      }
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleApproveTest = async () => {
    try {
      setActionLoading(true);
      setErrorMsg(null);
      const res = await fetch("/api/campaign/approve-test", {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Test approval rejected");
      }
      setState(data);
      setSuccessMsg("Test approved! Phase 3 Controlled Rollout is now unlocked.");
      setActiveTab("rollout");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleExecuteRollout = async () => {
    if (!rolloutConfirmed) {
      setErrorMsg("Please check the explicit rollout confirmation checkbox.");
      return;
    }
    try {
      setActionLoading(true);
      setErrorMsg(null);
      const res = await fetch("/api/campaign/rollout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, delay_seconds: 1.5 }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Rollout failed");
      }
      setState(data);
      if (data.aborted_reason) {
        setErrorMsg(`Rollout halted for safety: ${data.aborted_reason}`);
      } else {
        setSuccessMsg(`Rollout completed! Dispatched ${data.dispatched_count} individual messages.`);
      }
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResetCampaign = async () => {
    if (confirm("Reset campaign logs and approval status? This allows running a new test cycle.")) {
      try {
        setActionLoading(true);
        const res = await fetch("/api/campaign/reset", { method: "POST" });
        if (res.ok) {
          const updated = await res.json();
          setState(updated);
          setRolloutConfirmed(false);
          setSuccessMsg("Campaign state reset to initial Test Mode.");
          setTimeout(() => setSuccessMsg(null), 3000);
        }
      } catch (err: any) {
        setErrorMsg(err.message);
      } finally {
        setActionLoading(false);
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-5xl max-h-[92vh] flex flex-col rounded-3xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-2xl overflow-hidden text-foreground">
        {/* Top Header */}
        <div className="px-6 py-4.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-950/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-indigo-600 dark:bg-indigo-500 text-white flex items-center justify-center shadow-md shadow-indigo-500/20">
              <Radio className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base sm:text-lg font-bold tracking-tight">
                  Horus AI — WhatsApp Team Rollout
                </h2>
                <span className="px-2.5 py-0.5 text-[11px] font-semibold rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 flex items-center gap-1">
                  <ShieldAlert className="w-3 h-3" />
                  Test Mode Active
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Phase 1 Safety Verification & Automated Good Morning Introduction
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleResetCampaign}
              disabled={actionLoading}
              title="Reset campaign state for fresh test"
              className="p-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 rounded-xl hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 rounded-xl hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Gateway Connection Banner */}
        <div className="px-6 py-2.5 bg-slate-100/70 dark:bg-slate-950/40 border-b border-slate-200/60 dark:border-slate-800/60 flex flex-wrap items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                state?.gateway_status.is_online ? "bg-emerald-500 animate-ping" : "bg-rose-500"
              }`}
            />
            <span className="font-medium text-slate-700 dark:text-slate-300">
              Gateway:{" "}
              {state?.gateway_status.is_online ? (
                <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                  Orbit Connected ({state.gateway_status.connected_phone || "Active"})
                </span>
              ) : (
                <span className="text-rose-500 font-semibold">Orbit Gateway Offline (Port 8098)</span>
              )}
            </span>
          </div>
          <div className="flex items-center gap-4 text-muted-foreground">
            <span>
              Test Recipient:{" "}
              <strong className="text-foreground">
                {state?.test_recipient || "Not Configured Yet"}
              </strong>
            </span>
            <span>
              Approval:{" "}
              {state?.test_approved ? (
                <span className="text-emerald-500 font-semibold">✓ Approved</span>
              ) : (
                <span className="text-amber-500 font-semibold">Pending Approval</span>
              )}
            </span>
          </div>
        </div>

        {/* Global Notifications */}
        {errorMsg && (
          <div className="px-6 py-2.5 bg-rose-500/10 border-b border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-medium">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {errorMsg}
            </span>
            <button onClick={() => setErrorMsg(null)} className="underline text-[11px]">
              Dismiss
            </button>
          </div>
        )}
        {successMsg && (
          <div className="px-6 py-2.5 bg-emerald-500/10 border-b border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-medium">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              {successMsg}
            </span>
            <button onClick={() => setSuccessMsg(null)} className="underline text-[11px]">
              Dismiss
            </button>
          </div>
        )}

        {/* Tabs Bar */}
        <div className="px-6 pt-2 border-b border-slate-200 dark:border-slate-800 flex items-center gap-1 bg-white dark:bg-slate-900 overflow-x-auto">
          <button
            onClick={() => setActiveTab("recipients")}
            className={`px-3.5 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 whitespace-nowrap cursor-pointer ${
              activeTab === "recipients"
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400 bg-indigo-50/50 dark:bg-indigo-950/20"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            1. Team Contacts ({state?.recipients.length || 8})
          </button>

          <button
            onClick={() => setActiveTab("message")}
            className={`px-3.5 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 whitespace-nowrap cursor-pointer ${
              activeTab === "message"
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400 bg-indigo-50/50 dark:bg-indigo-950/20"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            2. Message & Tone
          </button>

          <button
            onClick={() => setActiveTab("test")}
            className={`px-3.5 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 whitespace-nowrap cursor-pointer ${
              activeTab === "test"
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400 bg-indigo-50/50 dark:bg-indigo-950/20"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            3. Phase 1 Test & Approval
            {state?.test_approved && (
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block ml-1" />
            )}
          </button>

          <button
            onClick={() => setActiveTab("rollout")}
            className={`px-3.5 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 whitespace-nowrap cursor-pointer ${
              activeTab === "rollout"
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400 bg-indigo-50/50 dark:bg-indigo-950/20"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {state?.test_approved ? (
              <Unlock className="w-3.5 h-3.5 text-emerald-500" />
            ) : (
              <Lock className="w-3.5 h-3.5 text-slate-400" />
            )}
            4. Phase 3 Controlled Rollout
          </button>

          <button
            onClick={() => setActiveTab("guide")}
            className={`px-3.5 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 whitespace-nowrap cursor-pointer ${
              activeTab === "guide"
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400 bg-indigo-50/50 dark:bg-indigo-950/20"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <HelpCircle className="w-3.5 h-3.5" />
            5. Gateway & Logs
          </button>
        </div>

        {/* Tab Content Container */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading && !state && (
            <div className="py-12 flex flex-col items-center justify-center gap-2 text-muted-foreground">
              <Radio className="w-6 h-6 animate-pulse text-indigo-500" />
              <span className="text-xs">Loading campaign state from gateway...</span>
            </div>
          )}

          {/* TAB 1: RECIPIENTS */}
          {activeTab === "recipients" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Validated Team Members (Phase 1 Review)
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    These 8 validated contacts are designated for the Horus AI introduction.
                    No messages will be sent without prior Phase 1 test approval.
                  </p>
                </div>
                <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
                  8 / 8 E.164 Validated
                </span>
              </div>

              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-50/40 dark:bg-slate-950/40">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-100 dark:bg-slate-900 text-muted-foreground font-semibold border-b border-slate-200 dark:border-slate-800">
                    <tr>
                      <th className="py-2.5 px-4">#</th>
                      <th className="py-2.5 px-4">Phone Number</th>
                      <th className="py-2.5 px-4">Country & Region</th>
                      <th className="py-2.5 px-4">Role / Destination</th>
                      <th className="py-2.5 px-4">Format Validation</th>
                      <th className="py-2.5 px-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                    {state?.recipients.map((r, idx) => (
                      <tr
                        key={r.phone_number}
                        className={`hover:bg-indigo-50/30 dark:hover:bg-indigo-950/20 transition-colors ${
                          state.test_recipient === r.phone_number
                            ? "bg-amber-500/10 dark:bg-amber-500/5 font-semibold"
                            : ""
                        }`}
                      >
                        <td className="py-3 px-4 text-muted-foreground">{idx + 1}</td>
                        <td className="py-3 px-4 font-mono font-semibold text-slate-900 dark:text-slate-100">
                          {r.formatted}
                          {state.test_recipient === r.phone_number && (
                            <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400">
                              Selected Test Target
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1.5">
                            <span>{r.country_code === "IN" ? "🇮🇳" : "🇦🇪"}</span>
                            <span>{r.country}</span>
                          </span>
                        </td>
                        <td className="py-3 px-4 text-muted-foreground">
                          {r.role_or_note || "Team Member"}
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Valid E.164
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-[11px] h-7 px-2.5"
                            onClick={() => {
                              handleSetTestRecipient(r.phone_number);
                              setActiveTab("test");
                            }}
                          >
                            Set as Test
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-3">
                <ShieldAlert className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                <div className="text-xs text-amber-900 dark:text-amber-300">
                  <p className="font-semibold">Safety Invariant Enforced:</p>
                  <p className="mt-0.5 opacity-90">
                    No automated messages are sent to this list on startup. The rollout remains locked
                    until you explicitly send and approve a Phase 1 test message.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: MESSAGE TEMPLATE & TONE */}
          {activeTab === "message" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Template Editor */}
              <div className="lg:col-span-7 space-y-4">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Horus AI Introduction Template & Tone
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Customize the introductory message or choose a curated tone preset.
                  </p>
                </div>

                {/* Tone Buttons */}
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => handleToneChange("warm_professional")}
                    className={`px-3 py-1.5 text-xs rounded-xl font-medium border transition-colors cursor-pointer ${
                      selectedTone === "warm_professional"
                        ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                        : "bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-muted-foreground"
                    }`}
                  >
                    Warm & Professional (Default)
                  </button>
                  <button
                    onClick={() => handleToneChange("energetic")}
                    className={`px-3 py-1.5 text-xs rounded-xl font-medium border transition-colors cursor-pointer ${
                      selectedTone === "energetic"
                        ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                        : "bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-muted-foreground"
                    }`}
                  >
                    Energetic & Dynamic 🚀
                  </button>
                  <button
                    onClick={() => handleToneChange("concise")}
                    className={`px-3 py-1.5 text-xs rounded-xl font-medium border transition-colors cursor-pointer ${
                      selectedTone === "concise"
                        ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                        : "bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-muted-foreground"
                    }`}
                  >
                    Concise & Focused
                  </button>
                </div>

                {/* Textarea */}
                <div className="space-y-1.5">
                  <textarea
                    rows={12}
                    value={editableTemplate}
                    onChange={(e) => setEditableTemplate(e.target.value)}
                    className="w-full p-3.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-xs font-sans leading-relaxed focus:ring-2 focus:ring-indigo-500/30 focus:outline-hidden"
                    placeholder="Type proposed WhatsApp message..."
                  />
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
                    <span>
                      Characters: <strong>{editableTemplate.length}</strong> | Words:{" "}
                      <strong>{editableTemplate.split(/\s+/).filter(Boolean).length}</strong>
                    </span>
                    <span>
                      Est. Read Time:{" "}
                      <strong>
                        {Math.ceil(editableTemplate.split(/\s+/).filter(Boolean).length / 3.5)}s
                      </strong>
                    </span>
                  </div>
                </div>

                <Button
                  onClick={handleSaveTemplate}
                  disabled={actionLoading}
                  className="w-full sm:w-auto text-xs font-semibold"
                >
                  <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                  Save Template Settings
                </Button>
              </div>

              {/* Right Column: WhatsApp Live Phone Mockup Preview */}
              <div className="lg:col-span-5 flex flex-col items-center justify-start">
                <div className="w-full max-w-sm rounded-[36px] p-3 bg-slate-900 border-4 border-slate-800 shadow-2xl relative">
                  {/* Phone Speaker Notch */}
                  <div className="w-24 h-4 bg-slate-800 rounded-full mx-auto mb-2" />

                  {/* Phone Screen Mockup */}
                  <div className="w-full rounded-[24px] bg-[#0b141a] text-white p-3 flex flex-col min-h-[380px] justify-between overflow-hidden relative">
                    {/* WhatsApp Chat Header */}
                    <div className="flex items-center gap-2.5 pb-2.5 border-b border-slate-800/80">
                      <img
                        src="/horus.jpg"
                        alt="Horus"
                        className="w-8 h-8 rounded-full object-cover ring-1 ring-emerald-500"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold truncate flex items-center gap-1">
                          Horus AI 🤖
                          <span className="text-[10px] text-emerald-400">✓ Official</span>
                        </div>
                        <div className="text-[10px] text-slate-400">Online</div>
                      </div>
                    </div>

                    {/* Chat Bubble */}
                    <div className="my-auto py-3">
                      <div className="max-w-[92%] bg-[#005c4b] text-slate-100 p-3 rounded-2xl rounded-tl-xs text-xs whitespace-pre-wrap leading-relaxed shadow-sm">
                        {editableTemplate}
                        <div className="text-[9px] text-emerald-200/70 text-right mt-1.5">
                          09:30 AM ✓✓
                        </div>
                      </div>
                    </div>

                    {/* Phone Bottom Footer */}
                    <div className="pt-2 text-center text-[10px] text-slate-500">
                      Horus AI Team WhatsApp Preview
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: PHASE 1 TEST EXECUTION & APPROVAL */}
          {activeTab === "test" && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  Phase 1: Test Mode (Mandatory)
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Configure your specific phone number to receive the single test message.
                  Review the result and approve before remaining team contacts can be rolled out.
                </p>
              </div>

              {/* Step 1: Configure Test Number */}
              <div className="p-4.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 space-y-3">
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                  <Smartphone className="w-3.5 h-3.5 text-indigo-500" />
                  Target Test Recipient (Your Number)
                </label>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="text"
                    value={testNumberInput}
                    onChange={(e) => setTestNumberInput(e.target.value)}
                    placeholder="+971508621612 or +91..."
                    className="flex-1 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono focus:ring-2 focus:ring-indigo-500/30"
                  />
                  <Button
                    variant="outline"
                    onClick={() => handleSetTestRecipient(testNumberInput)}
                    disabled={actionLoading || !testNumberInput}
                    className="text-xs"
                  >
                    Save Test Number
                  </Button>
                  <Button
                    onClick={handleSendTestMessage}
                    disabled={actionLoading || !testNumberInput}
                    className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
                  >
                    <Send className="w-3.5 h-3.5 mr-1.5" />
                    Send Test Message Now
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Quick Select: You can choose from the executive contacts:{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setTestNumberInput("+971508621612");
                      handleSetTestRecipient("+971508621612");
                    }}
                    className="text-indigo-600 dark:text-indigo-400 underline font-mono ml-1"
                  >
                    +971508621612 (UAE Executive)
                  </button>{" "}
                  or{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setTestNumberInput("+918157070717");
                      handleSetTestRecipient("+918157070717");
                    }}
                    className="text-indigo-600 dark:text-indigo-400 underline font-mono ml-1"
                  >
                    +918157070717 (India)
                  </button>
                </p>
              </div>

              {/* Step 2: Latest Test Execution Result */}
              <div className="p-4.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Latest Test Verification Result
                  </h4>
                  {state?.latest_test_result && (
                    <span
                      className={`px-2.5 py-0.5 text-[11px] font-semibold rounded-full ${
                        state.latest_test_result.status === "delivered"
                          ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                          : "bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30"
                      }`}
                    >
                      {state.latest_test_result.status === "delivered"
                        ? "✓ Gateway Confirmed Delivery"
                        : "✕ Delivery Failed"}
                    </span>
                  )}
                </div>

                {state?.latest_test_result ? (
                  <div className="space-y-2 text-xs">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-3 rounded-xl bg-slate-50 dark:bg-slate-950 font-mono text-[11px]">
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Recipient</span>
                        <strong className="text-foreground">
                          {state.latest_test_result.phone_number}
                        </strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Status</span>
                        <strong className="text-foreground">
                          {state.latest_test_result.status}
                        </strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Timestamp</span>
                        <strong className="text-foreground">
                          {new Date(state.latest_test_result.created_at).toLocaleTimeString()}
                        </strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Type</span>
                        <strong className="text-indigo-500">Phase 1 Test</strong>
                      </div>
                    </div>

                    {state.latest_test_result.error_details && (
                      <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 text-xs font-mono">
                        {state.latest_test_result.error_details}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
                    No test message has been dispatched yet. Click "Send Test Message Now" above.
                  </div>
                )}
              </div>

              {/* Step 3: Mandatory Approval Gate Button */}
              <div className="p-5 rounded-2xl bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-indigo-500/10 border border-indigo-500/20 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div>
                  <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-emerald-500" />
                    Manual Test Approval Gate
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Review your received WhatsApp test message. Click approve only after verifying
                    formatting and tone.
                  </p>
                </div>

                <Button
                  onClick={handleApproveTest}
                  disabled={
                    actionLoading ||
                    !state?.latest_test_result ||
                    state.latest_test_result.status !== "delivered" ||
                    state.test_approved
                  }
                  className={`text-xs font-semibold px-5 ${
                    state?.test_approved
                      ? "bg-emerald-600 text-white cursor-default"
                      : "bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-600/20"
                  }`}
                >
                  {state?.test_approved ? (
                    <>
                      <Check className="w-4 h-4 mr-1.5" />
                      Test Approved ✓
                    </>
                  ) : (
                    <>
                      <Unlock className="w-4 h-4 mr-1.5" />
                      Approve Test & Unlock Rollout
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* TAB 4: PHASE 3 CONTROLLED ROLLOUT */}
          {activeTab === "rollout" && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  Phase 3: Controlled Team Rollout
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Controlled, rate-limited distribution to the 8 validated team contacts with active
                  deduplication and restriction halt.
                </p>
              </div>

              {!state?.test_approved ? (
                <div className="p-8 text-center rounded-2xl border border-dashed border-amber-500/30 bg-amber-500/5 space-y-3">
                  <Lock className="w-8 h-8 text-amber-500 mx-auto" />
                  <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Phase 3 is Locked
                  </h4>
                  <p className="text-xs text-muted-foreground max-w-md mx-auto">
                    To protect our team and ensure high message quality, the full rollout cannot be
                    triggered until Phase 1 test message is sent and explicitly approved.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setActiveTab("test")}
                    className="text-xs"
                  >
                    Go to Phase 1 Test
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Safety checklist */}
                  <div className="p-4.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 space-y-2.5 text-xs">
                    <h4 className="font-bold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-emerald-500" />
                      Active Protection Safeguards:
                    </h4>
                    <ul className="space-y-1.5 text-muted-foreground pl-5 list-disc">
                      <li>
                        <strong>Strict Deduplication:</strong> Recipients who already received this
                        message during this campaign will be automatically skipped.
                      </li>
                      <li>
                        <strong>Automated Rate Pacing:</strong> 1.5-second pacing delay between individual
                        dispatches.
                      </li>
                      <li>
                        <strong>Circuit Breaker:</strong> Instantly halts the campaign if WhatsApp
                        reports rate limit (429) or account restriction (401/403).
                      </li>
                      <li>
                        <strong>No Contact Discovery:</strong> Strictly restricted to the 8 validated team
                        numbers.
                      </li>
                    </ul>

                    <div className="pt-2 border-t border-slate-200 dark:border-slate-800 flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="confirm_rollout"
                        checked={rolloutConfirmed}
                        onChange={(e) => setRolloutConfirmed(e.target.checked)}
                        className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                      />
                      <label
                        htmlFor="confirm_rollout"
                        className="text-xs font-semibold text-slate-800 dark:text-slate-200 cursor-pointer"
                      >
                        I have reviewed the test message and explicitly authorize the team rollout.
                      </label>
                    </div>
                  </div>

                  {/* Trigger Button */}
                  <div className="flex items-center gap-3">
                    <Button
                      onClick={handleExecuteRollout}
                      disabled={actionLoading || !rolloutConfirmed}
                      className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-6 py-2.5 h-auto"
                    >
                      <Send className="w-3.5 h-3.5 mr-1.5" />
                      Start Controlled Team Rollout
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      Target: 8 team members (India 🇮🇳 & UAE 🇦🇪)
                    </span>
                  </div>

                  {/* Summary Stats */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-center">
                      <span className="text-[10px] uppercase font-bold text-muted-foreground block">
                        Total Team
                      </span>
                      <strong className="text-lg text-slate-900 dark:text-slate-100">
                        {state.stats.total_recipients}
                      </strong>
                    </div>
                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-center">
                      <span className="text-[10px] uppercase font-bold text-muted-foreground block">
                        Delivered
                      </span>
                      <strong className="text-lg text-emerald-500">
                        {state.stats.delivered}
                      </strong>
                    </div>
                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-center">
                      <span className="text-[10px] uppercase font-bold text-muted-foreground block">
                        Pending
                      </span>
                      <strong className="text-lg text-amber-500">
                        {state.stats.pending}
                      </strong>
                    </div>
                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-center">
                      <span className="text-[10px] uppercase font-bold text-muted-foreground block">
                        Failed / Skipped
                      </span>
                      <strong className="text-lg text-slate-500">
                        {state.stats.failed + state.stats.skipped}
                      </strong>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 5: GATEWAY & DELIVERY LOGS */}
          {activeTab === "guide" && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  Authorized WhatsApp Gateway & Campaign Audit Logs
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Real-time audit log of all test and rollout messages.
                </p>
              </div>

              {/* Gateway Connection Details Card */}
              <div className="p-4.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 space-y-2 text-xs">
                <h4 className="font-bold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                  <Radio className="w-4 h-4 text-indigo-500" />
                  WhatsApp Gateway Architecture:
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-muted-foreground mt-2">
                  <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                    <span className="block font-semibold text-slate-800 dark:text-slate-200">
                      REST API Gateway Endpoint
                    </span>
                    <span className="font-mono text-[11px]">{state?.gateway_status.gateway_url}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                    <span className="block font-semibold text-slate-800 dark:text-slate-200">
                      Connected WhatsApp Account
                    </span>
                    <span className="font-mono text-[11px]">
                      +{state?.gateway_status.connected_phone || "Not connected"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Audit Logs Table */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Delivery Log Audit Records
                </h4>
                {state?.logs.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
                    No message attempts logged yet.
                  </div>
                ) : (
                  <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-slate-100 dark:bg-slate-900 text-muted-foreground font-semibold border-b border-slate-200 dark:border-slate-800">
                        <tr>
                          <th className="py-2 px-3">Type</th>
                          <th className="py-2 px-3">Phone</th>
                          <th className="py-2 px-3">Country</th>
                          <th className="py-2 px-3">Status</th>
                          <th className="py-2 px-3">Timestamp</th>
                          <th className="py-2 px-3">Details</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60">
                        {state?.logs.map((log) => (
                          <tr key={log.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                            <td className="py-2.5 px-3">
                              {log.is_test ? (
                                <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 font-semibold text-[10px]">
                                  Phase 1 Test
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 font-semibold text-[10px]">
                                  Rollout
                                </span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 font-mono font-medium">{log.phone_number}</td>
                            <td className="py-2.5 px-3">{log.country}</td>
                            <td className="py-2.5 px-3">
                              <span
                                className={`font-semibold ${
                                  log.status === "delivered"
                                    ? "text-emerald-500"
                                    : log.status === "skipped"
                                    ? "text-slate-400"
                                    : "text-rose-500"
                                }`}
                              >
                                {log.status}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-muted-foreground font-mono text-[11px]">
                              {new Date(log.created_at).toLocaleTimeString()}
                            </td>
                            <td className="py-2.5 px-3 text-muted-foreground truncate max-w-[200px]">
                              {log.error_details || "Confirmed delivered"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
