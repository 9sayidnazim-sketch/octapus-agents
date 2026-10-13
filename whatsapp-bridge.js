import "dotenv/config";
import express from "express";

const app = express();
app.use(express.json({ limit: "50mb" }));
app.use(express.urlencoded({ extended: true, limit: "50mb" }));

// Configuration from environment or defaults
const GATEWAY = process.env.ORBIT_API_URL || process.env.GATEWAY_URL || "http://localhost:8098";
const API_KEY = process.env.ORBIT_INSTANCE_TOKEN || process.env.GATEWAY_API_KEY || process.env.WA_API_KEY || "";
const INSTANCE_ID = process.env.ORBIT_INSTANCE_ID || "";
const ACCOUNT_PHONE = process.env.ORBIT_PHONE_NUMBER || "";
const ADMIN_KEY = process.env.ORBIT_GLOBAL_API_KEY || process.env.ORBIT_ADMIN_KEY || "";
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

// Sanitize payload for safe logging (redact secrets/tokens/keys)
function sanitizePayloadForLog(obj) {
  if (!obj || typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map(sanitizePayloadForLog);
  const copy = {};
  for (const [k, v] of Object.entries(obj)) {
    const lk = k.toLowerCase();
    if (lk.includes("key") || lk.includes("token") || lk.includes("secret") || lk.includes("auth")) {
      copy[k] = typeof v === "string" && v.length > 8 ? `${v.slice(0, 4)}...[REDACTED]` : "[REDACTED]";
    } else {
      copy[k] = sanitizePayloadForLog(v);
    }
  }
  return copy;
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
    capabilities: ["text", "image", "audio_ptt", "document"],
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

    // 3. Extract message ID for deduplication
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

    // 8. Detect Message Type (text, image, audio/ptt, document, video, sticker)
    const msg = body.data?.Message || body.data?.message || body.message || {};
    const isImage = Boolean(msg.imageMessage);
    const isAudio = Boolean(msg.audioMessage);
    const isDoc = Boolean(msg.documentMessage);
    const isVideo = Boolean(msg.videoMessage);
    const isSticker = Boolean(msg.stickerMessage);
    const hasMedia = isImage || isAudio || isDoc || isVideo || isSticker;

    let detectedType = "text";
    if (isImage) detectedType = "image";
    else if (isAudio) detectedType = msg.audioMessage?.ptt ? "audio (ptt/voice note)" : "audio";
    else if (isDoc) detectedType = "document";
    else if (isVideo) detectedType = "video";
    else if (isSticker) detectedType = "sticker";

    // Extract text/caption if present
    const text =
      msg.conversation ||
      msg.extendedTextMessage?.text ||
      msg.imageMessage?.caption ||
      msg.videoMessage?.caption ||
      msg.documentMessage?.caption ||
      body.text ||
      (typeof body.message === "string" ? body.message : undefined);

    // Log the raw incoming payload safely (secrets removed)
    const sanitizedLog = sanitizePayloadForLog(body);
    console.log(
      `📩 [WhatsApp Ingest] [${cleanNumber}] Type: ${detectedType} | Payload: ${JSON.stringify(sanitizedLog).slice(0, 320)}...`
    );

    if (!text && !hasMedia) {
      return;
    }

    // 9. Serialize message processing per conversation queue
    const incomingToken = body.instanceToken || body.token || API_KEY;
    enqueueUserTask(cleanNumber, async () => {
      // Instantly trigger "typing..." presence on WhatsApp so the user gets immediate visual feedback
      sendPresence(cleanNumber, "composing", incomingToken);

      let reply = "";
      let audioUrl = null;

      // Call Horus Customer Agent's multimodal webhook endpoint
      try {
        const webhookUrl = `${AGENT_URL.replace("/chat", "")}/webhook`;
        const agentRes = await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (agentRes.ok) {
          const resData = await agentRes.json();
          if (resData.status === "ignored") {
            sendPresence(cleanNumber, "paused", incomingToken);
            return;
          }
          reply = resData.reply;
          audioUrl = resData.audio_url || null;
        } else {
          console.warn(`⚠️ [Agent Webhook HTTP ${agentRes.status}]`);
        }
      } catch (err) {
        console.error(`⚠️ [Agent Webhook Error for ${cleanNumber}]:`, err.message);
      }

      // Fallback if webhook didn't provide a reply
      if (!reply) {
        if (hasMedia) {
          reply = "I couldn't open that file, can you send it again?";
        } else if (text) {
          reply = await askAgent(cleanNumber, text.trim());
        }
      }

      if (reply) {
        console.log(`🤖 [Horus Reply] To: ${cleanNumber} | "${reply.slice(0, 100).replace(/\n/g, " ")}..."`);
        await sendGatewayReply(cleanNumber, reply, incomingToken);
      }

      if (audioUrl) {
        console.log(`🔊 [Horus Voice Reply] Sending voice note to ${cleanNumber}`);
        await sendGatewayMedia(cleanNumber, "audio", audioUrl, incomingToken);
      }

      // Clear presence once replied
      sendPresence(cleanNumber, "paused", incomingToken);
    });
  } catch (err) {
    console.error("💥 [Webhook Ingestion Error]:", err.message);
  }
});

let cachedActiveToken = null;
let lastTokenCheck = 0;

/**
 * Discovers the currently connected WhatsApp instance token from Orbit
 */
async function getActiveToken() {
  const now = Date.now();
  if (cachedActiveToken && now - lastTokenCheck < 15000) {
    return cachedActiveToken;
  }
  const adminKey = ADMIN_KEY;
  if (!adminKey) return API_KEY;
  try {
    const res = await fetch(`${GATEWAY}/instance/all`, {
      headers: { apikey: adminKey },
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      const instances = data.data || [];
      const connected = instances.find((i) => i.connected === true);
      if (connected && connected.token) {
        cachedActiveToken = connected.token;
        lastTokenCheck = now;
        return connected.token;
      }
    }
  } catch (err) {
    // Non-critical fallback
  }
  return API_KEY;
}

/**
 * Dispatches chat presence ("composing" / "paused") to Orbit Gateway
 * Non-blocking fire-and-forget for instant perception
 */
async function sendPresence(number, state = "composing", apiKey = API_KEY) {
  if (!number) return;
  try {
    const activeToken = await getActiveToken();
    fetch(`${GATEWAY}/message/presence`, {
      method: "POST",
      headers: {
        apikey: activeToken || apiKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        number: number,
        state: state,
        delay: 10000,
      }),
      signal: AbortSignal.timeout(3000),
    }).catch(() => {});
  } catch (err) {
    // ignore
  }
}

/**
 * Dispatches message via Orbit Gateway using bounded exponential retries
 * Automatically prioritizes currently connected WhatsApp instances
 */
async function sendGatewayReply(number, text, apiKey = API_KEY, maxRetries = 2) {
  const activeToken = await getActiveToken();
  const candidateKeys = Array.from(
    new Set([
      activeToken,
      apiKey,
      process.env.ORBIT_INSTANCE_TOKEN,
      process.env.GATEWAY_API_KEY,
      process.env.WA_API_KEY,
    ])
  ).filter(Boolean);

  for (const token of candidateKeys) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await fetch(`${GATEWAY}/send/text`, {
          method: "POST",
          headers: {
            apikey: token,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            number: number,
            text: text,
          }),
          signal: AbortSignal.timeout(4000),
        });

        if (response.ok) {
          console.log(`✅ [Gateway Sent] Delivered reply to ${number}`);
          return true;
        }

        const errText = await response.text();
        console.warn(`⚠️ [Gateway Status ${response.status} on key ${token.slice(0, 6)}...]: ${errText.slice(0, 100)}`);
      } catch (err) {
        console.warn(`⚠️ [Gateway Network Error on key ${token.slice(0, 6)}...]:`, err.message);
      }

      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, 150 * Math.pow(2, attempt - 1)));
      }
    }
  }

  console.error(`❌ [Gateway Send Failed] Delivery failed for ${number} after trying candidate tokens.`);
  return false;
}

/**
 * Dispatches media (audio/voice note, image, etc.) via Orbit Gateway
 */
async function sendGatewayMedia(number, type = "audio", url, apiKey = API_KEY, maxRetries = 2) {
  const activeToken = await getActiveToken();
  const candidateKeys = Array.from(
    new Set([
      activeToken,
      apiKey,
      process.env.ORBIT_INSTANCE_TOKEN,
      process.env.GATEWAY_API_KEY,
      process.env.WA_API_KEY,
    ])
  ).filter(Boolean);

  // Unwrap data URIs (e.g. data:audio/mpeg;base64,...) to raw base64 for Orbit Gateway
  let cleanUrl = url;
  if (typeof cleanUrl === "string" && cleanUrl.startsWith("data:") && cleanUrl.includes(";base64,")) {
    cleanUrl = cleanUrl.split(";base64,")[1];
  }

  for (const token of candidateKeys) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await fetch(`${GATEWAY}/send/media`, {
          method: "POST",
          headers: {
            apikey: token,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            number: number,
            type: type,
            url: cleanUrl,
            caption: "",
          }),
          signal: AbortSignal.timeout(15000),
        });

        if (response.ok) {
          console.log(`✅ [Gateway Sent] Delivered ${type} media to ${number}`);
          return true;
        }

        const errText = await response.text();
        console.warn(`⚠️ [Gateway Media Status ${response.status} on key ${token.slice(0, 6)}...]: ${errText.slice(0, 100)}`);
      } catch (err) {
        console.warn(`⚠️ [Gateway Media Network Error]:`, err.message);
      }

      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, 200 * Math.pow(2, attempt - 1)));
      }
    }
  }

  console.error(`❌ [Gateway Media Send Failed] Failed delivering ${type} to ${number}`);
  return false;
}

const server = app.listen(PORT, () => {
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
• Capabilities:     Text, Images (Vision/OCR), Voice Notes (STT), Docs (PDF/DOCX)
=============================================================
`);
});

server.on("error", (err) => {
  console.error(`❌ [Bridge Server Error]:`, err.message);
});
