import "dotenv/config";
import express from "express";

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Configuration from environment or defaults
const GATEWAY = process.env.ORBIT_API_URL || process.env.GATEWAY_URL || "http://localhost:8098";
const API_KEY = process.env.ORBIT_INSTANCE_TOKEN || process.env.GATEWAY_API_KEY || "cc12f98a-6ed1-4722-9554-b2b7e5d05d3a";
const INSTANCE_ID = process.env.ORBIT_INSTANCE_ID || "a43800f4-96bc-4b9a-b588-de15137ef093";
const ACCOUNT_PHONE = process.env.ORBIT_PHONE_NUMBER || "639562441681";
const AGENT_URL = process.env.AGENT_URL || "http://localhost:8000/chat";
const PORT = process.env.BRIDGE_PORT || 3000;

// Message deduplication cache (bounded to 5,000 entries)
const processedMessageIds = new Set();
const MAX_DEDUP_CACHE = 5000;

function isDuplicateMessage(msgId) {
  if (!msgId) return false;
  if (processedMessageIds.has(msgId)) return true;
  processedMessageIds.add(msgId);
  if (processedMessageIds.size > MAX_DEDUP_CACHE) {
    const first = processedMessageIds.values().next().value;
    processedMessageIds.delete(first);
  }
  return false;
}

// Conversation serializer: serialize message processing per phone number
const conversationQueues = new Map();

function enqueueUserTask(userId, task) {
  const current = conversationQueues.get(userId) || Promise.resolve();
  const next = current.then(task, task).catch((err) => {
    console.error(`[Queue Error for ${userId}]:`, err.message);
  });
  conversationQueues.set(userId, next);
  return next;
}

// Health check endpoint
app.get("/health", async (req, res) => {
  let agentHealth = null;
  try {
    const healthUrl = AGENT_URL.replace("/chat", "/health");
    const agentRes = await fetch(healthUrl);
    if (agentRes.ok) {
      agentHealth = await agentRes.json();
    }
  } catch (err) {
    agentHealth = { status: "agent_offline", error: err.message };
  }

  res.json({
    status: "ok",
    service: "octapus-whatsapp-bridge",
    instance: {
      id: INSTANCE_ID,
      phone: ACCOUNT_PHONE,
      gateway: GATEWAY,
    },
    agent: {
      url: AGENT_URL,
      status: agentHealth?.status || "unknown",
    },
    dedup_cache_size: processedMessageIds.size,
    timestamp: new Date().toISOString(),
  });
});

// Incoming webhook from Orbit WhatsApp Gateway
app.post("/incoming", async (req, res) => {
  // Acknowledge Orbit immediately to prevent re-deliveries or gateway timeouts
  res.sendStatus(200);

  try {
    const body = req.body || {};

    // 1. Ignore non-Message events from Orbit (presence, call, qrcode, etc.)
    if (body.event && body.event.toUpperCase() !== "MESSAGE") {
      return;
    }

    // 2. Ignore history sync events
    if (
      body.event === "HistorySync" ||
      body.event === "HISTORY_SYNC" ||
      body.data?.messageType === "HistorySync"
    ) {
      return;
    }

    // 3. Flexible extraction supporting Orbit Gateway structures
    const messageId =
      body.data?.Info?.ID ||
      body.data?.Info?.Id ||
      body.data?.key?.id ||
      body.data?.info?.ID ||
      body.id ||
      body.messageId;

    if (messageId && isDuplicateMessage(messageId)) {
      console.log(`⏩ [Deduplicated] Skipping already processed message ID: ${messageId}`);
      return;
    }

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

    const fromMe = Boolean(
      body.data?.Info?.IsFromMe ||
      body.data?.Info?.MessageSource?.IsFromMe ||
      body.data?.info?.isFromMe ||
      body.data?.info?.IsFromMe ||
      body.data?.key?.fromMe ||
      body.fromMe ||
      body.isFromMe
    );

    // 4. Ignore status broadcasts
    if (
      String(rawSender).endsWith("@broadcast") ||
      String(rawSender).includes("status@broadcast")
    ) {
      return;
    }

    // 5. Ignore group chats
    const isGroup = Boolean(
      body.data?.Info?.IsGroup ||
      body.data?.Info?.MessageSource?.IsGroup ||
      String(rawSender).endsWith("@g.us")
    );

    if (isGroup) {
      return;
    }

    // 6. Clean and normalize phone number
    let cleanNumber = String(rawSender || "")
      .split("@")[0]
      .split(":")[0]
      .replace(/[^0-9]/g, "")
      .trim();

    if (cleanNumber.startsWith("05") && cleanNumber.length === 10) {
      cleanNumber = "971" + cleanNumber.slice(1);
    }

    // 7. Ignore self-messages and prevent loops
    if (fromMe || !cleanNumber || cleanNumber === ACCOUNT_PHONE) {
      return;
    }

    // 8. Extract incoming text content
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

    if (!text || !text.trim()) {
      return;
    }

    const cleanText = text.trim();
    console.log(`📩 [WhatsApp Ingest] [${cleanNumber}]: "${cleanText.replace(/\n/g, " ")}"`);

    // 9. Serialize message processing per conversation queue
    const incomingToken = body.instanceToken || body.token || API_KEY;
    enqueueUserTask(cleanNumber, async () => {
      // Query Horus AI Agent
      const reply = await askAgent(cleanNumber, cleanText);
      console.log(`🤖 [Horus Reply] To: ${cleanNumber} | "${reply.slice(0, 100).replace(/\n/g, " ")}..."`);

      // Dispatch reply via Orbit Gateway with bounded retries
      await sendGatewayReply(cleanNumber, reply, incomingToken);
    });
  } catch (err) {
    console.error("💥 [Webhook Ingestion Error]:", err.message);
  }
});

/**
 * Queries Horus AI Customer Agent API
 * Preserves persistent SQLite session history per phone number
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
    return data.reply || "Thank you for reaching out. How can I help you today?";
  } catch (err) {
    console.error(`⚠️ [Agent Call Error for ${userId}]:`, err.message);
    return "Thank you for reaching out to Octapus. Our assistant is momentarily checking information. Please leave your requirement or contact us at info@octapus.ae.";
  }
}

/**
 * Dispatches message via Orbit Gateway using bounded exponential retries
 */
async function sendGatewayReply(number, text, apiKey = API_KEY, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(`${GATEWAY}/send/text`, {
        method: "POST",
        headers: {
          apikey: apiKey,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          number: number,
          text: text,
        }),
      });

      if (response.ok) {
        console.log(`✅ [Gateway Sent] Delivered reply to ${number}`);
        return true;
      }

      const errText = await response.text();
      console.warn(`⚠️ [Gateway Retry ${attempt}/${maxRetries}] Status ${response.status}: ${errText.slice(0, 120)}`);
    } catch (err) {
      console.warn(`⚠️ [Gateway Error ${attempt}/${maxRetries}]:`, err.message);
    }

    if (attempt < maxRetries) {
      await new Promise((r) => setTimeout(r, 500 * Math.pow(2, attempt - 1)));
    }
  }

  console.error(`❌ [Gateway Send Failed] Delivery failed for ${number} after ${maxRetries} attempts.`);
  return false;
}

app.listen(PORT, () => {
  const maskedToken = API_KEY ? `${API_KEY.slice(0, 6)}...${API_KEY.slice(-4)}` : "NOT_SET";
  console.log(`
=============================================================
🚀 Octapus WhatsApp / Orbit Gateway Bridge Running
=============================================================
• Bridge Webhook:   http://localhost:${PORT}/incoming
• Health Check:     http://localhost:${PORT}/health
• Active Instance:  ${INSTANCE_ID} (${ACCOUNT_PHONE})
• Gateway URL:      ${GATEWAY}
• Gateway Token:    ${maskedToken}
• Agent Endpoint:   ${AGENT_URL}
=============================================================
`);
});
