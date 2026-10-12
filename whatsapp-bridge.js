import "dotenv/config";
import express from "express";

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Configuration from environment or defaults
const GATEWAY = process.env.GATEWAY_URL || "http://localhost:8098";
const API_KEY = process.env.GATEWAY_API_KEY || "f358885b7f1f9ac6dd97201ee6323caa43e431a9b043e421a184f5246b9d5722";
const AGENT_URL = process.env.AGENT_URL || "http://localhost:8000/chat";
const PORT = process.env.BRIDGE_PORT || 3000;

// Health check endpoint
app.get("/health", async (req, res) => {
  let dbInfo = null;
  try {
    const healthUrl = AGENT_URL.replace("/chat", "/health");
    const agentRes = await fetch(healthUrl);
    if (agentRes.ok) {
      const data = await agentRes.json();
      dbInfo = data.database;
    }
  } catch (err) {
    dbInfo = { status: "agent_offline", error: err.message };
  }

  res.json({
    status: "ok",
    service: "octapus-whatsapp-bridge",
    gateway: GATEWAY,
    agent: AGENT_URL,
    database: dbInfo || { status: "connected", engine: "sqlite" },
    timestamp: new Date().toISOString(),
  });
});

// Incoming webhook from WhatsApp / Orbit Gateway
app.post("/incoming", async (req, res) => {
  // Acknowledge the gateway immediately to prevent re-deliveries or timeouts
  res.sendStatus(200);

  try {
    const body = req.body || {};

    // Ignore non-Message events from Orbit if event type is specified
    if (body.event && body.event !== "Message") {
      return;
    }

    // Flexible field extraction supporting Orbit Gateway and standard formats
    const rawSender =
      body.data?.Info?.Sender ||
      body.data?.Info?.Chat ||
      body.data?.info?.Sender ||
      body.data?.info?.Chat ||
      body.data?.Info?.MessageSource?.Sender ||
      body.data?.Info?.MessageSource?.Chat ||
      body.from ||
      body.number ||
      body.sender ||
      body.phone ||
      body.data?.key?.remoteJid ||
      body.data?.sender;

    const text =
      body.data?.Message?.conversation ||
      body.data?.Message?.extendedTextMessage?.text ||
      body.data?.Message?.imageMessage?.caption ||
      body.data?.Message?.videoMessage?.caption ||
      body.data?.Message?.documentMessage?.caption ||
      body.data?.message?.conversation ||
      body.data?.message?.extendedTextMessage?.text ||
      body.data?.message?.imageMessage?.caption ||
      body.text ||
      body.message?.conversation ||
      body.message?.text ||
      (typeof body.message === "string" ? body.message : undefined);

    const fromMe = Boolean(
      body.data?.Info?.IsFromMe ||
      body.data?.Info?.MessageSource?.IsFromMe ||
      body.data?.info?.isFromMe ||
      body.data?.info?.IsFromMe ||
      body.data?.key?.fromMe ||
      body.fromMe ||
      body.isFromMe
    );

    // Ignore group chats, empty messages, or messages sent by ourselves
    const isGroup = Boolean(
      body.data?.Info?.IsGroup ||
      body.data?.Info?.MessageSource?.IsGroup ||
      String(rawSender).endsWith("@g.us")
    );

    if (!text || fromMe || isGroup || !rawSender) {
      return;
    }

    // Clean and normalize phone number
    let cleanNumber = String(rawSender).split("@")[0].split(":")[0].replace(/[^0-9]/g, "").trim();
    if (cleanNumber.startsWith("05") && cleanNumber.length === 10) {
      cleanNumber = "971" + cleanNumber.slice(1);
    }

    if (!cleanNumber) {
      console.warn("⚠️ [WhatsApp Incoming] Could not extract valid phone number from:", rawSender);
      return;
    }

    console.log(`📩 [WhatsApp Incoming] From: ${cleanNumber} | Message: "${text}"`);

    // Ask the Octapus AI Customer Agent
    const reply = await askAgent(cleanNumber, text);

    console.log(`🤖 [Agent Reply] To: ${cleanNumber} | Reply: "${reply.slice(0, 80).replace(/\n/g, " ")}..."`);

    // Dispatch reply back through Orbit Gateway
    const response = await fetch(`${GATEWAY}/send/text`, {
      method: "POST",
      headers: {
        apikey: API_KEY,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        number: cleanNumber,
        text: reply,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      console.error(`❌ [Gateway Send Failed] Status: ${response.status} | Details: ${errText}`);
    } else {
      console.log(`✅ [Gateway Sent] Successfully delivered reply to ${cleanNumber}`);
    }
  } catch (err) {
    console.error("💥 [Webhook Error]:", err);
  }
});

/**
 * Queries the Octapus Customer Agent API
 * Uses the customer's phone number as the session_id to maintain persistent conversation history
 */
async function askAgent(userId, text) {
  try {
    const response = await fetch(AGENT_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: text,
        session_id: `whatsapp-${userId}`,
      }),
    });

    if (!response.ok) {
      throw new Error(`Customer Agent returned HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.reply || "Thank you for reaching out to Octapus LLC. How can I help you today?";
  } catch (err) {
    console.error(`⚠️ [Agent Call Error for ${userId}]:`, err.message);
    return "Thank you for reaching out to Octapus LLC. Our digital coordinator is temporarily unavailable. Please reach us directly at info@octapus.ae or try again shortly.";
  }
}

app.listen(PORT, () => {
  console.log(`
=============================================================
🚀 Octapus WhatsApp / Orbit Gateway Bridge Running
=============================================================
• Bridge Webhook:   http://localhost:${PORT}/incoming
• Health Check:     http://localhost:${PORT}/health
• Agent Endpoint:   ${AGENT_URL}
• Gateway Target:   ${GATEWAY}/send/text
• Gateway API Key:  ${API_KEY.slice(0, 8)}...${API_KEY.slice(-6)}
=============================================================
`);
});
