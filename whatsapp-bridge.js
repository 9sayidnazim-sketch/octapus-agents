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
app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    service: "octapus-whatsapp-bridge",
    gateway: GATEWAY,
    agent: AGENT_URL,
    timestamp: new Date().toISOString(),
  });
});

// Incoming webhook from WhatsApp / Orbit Gateway
app.post("/incoming", async (req, res) => {
  // Acknowledge the gateway immediately to prevent re-deliveries or timeouts
  res.sendStatus(200);

  try {
    const body = req.body || {};

    // Flexible field extraction supporting various WhatsApp gateway payload formats
    const from =
      body.from ||
      body.number ||
      body.sender ||
      body.phone ||
      body.data?.key?.remoteJid ||
      body.data?.sender;

    const text =
      body.text ||
      body.message?.conversation ||
      body.message?.text ||
      body.data?.message?.conversation ||
      body.data?.message?.extendedTextMessage?.text ||
      (typeof body.message === "string" ? body.message : undefined);

    const fromMe = Boolean(
      body.fromMe ||
      body.data?.key?.fromMe ||
      body.isFromMe
    );

    // Ignore empty messages or messages sent by ourselves to avoid infinite reply loops
    if (!text || fromMe) {
      return;
    }

    // Clean phone number (e.g. "971501234567@s.whatsapp.net" -> "971501234567")
    const cleanNumber = String(from).replace(/@.*$/, "").trim();

    console.log(`📩 [WhatsApp Incoming] From: ${cleanNumber} | Message: "${text}"`);

    // Ask the Octapus AI Customer Agent
    const reply = await askAgent(cleanNumber, text);

    console.log(`🤖 [Agent Reply] To: ${cleanNumber} | Reply: "${reply.slice(0, 80)}..."`);

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
