"""Reply understanding skill: detects language, intent (question, complaint, order, other) and sentiment."""
from __future__ import annotations

import re
from typing import Any, Dict
from .base import BaseSkill


class ReplyUnderstandingSkill(BaseSkill):
    """Analyzes incoming messages to detect language, intent, and sentiment before answering."""

    @property
    def skill_id(self) -> str:
        return "understanding"

    @property
    def name(self) -> str:
        return "Reply understanding"

    @property
    def description(self) -> str:
        return "Detects language, categorizes intent (question, complaint, order, other), and gauges sentiment."

    def format_prompt_section(self, config: Dict[str, Any]) -> str:
        tone = config.get("tone", "Empathetic")
        extra = config.get("extra_instructions", "").strip()

        lines = [
            "### Skill: Reply Understanding & Intent Awareness",
            "- You will receive contextual metadata indicating the detected user language, intent, and sentiment.",
            "- Intended behavior by intent:",
            "  * 'question': Provide a direct, concise, verified answer.",
            "  * 'complaint': Acknowledge frustrations courteously, apologize for inconvenience, and provide reassurance or escalation steps.",
            "  * 'order': Guide the customer through booking or requirement submission with clear next steps.",
            "  * 'other': Be cordial, friendly, and helpful.",
            f"- Adaptive conversational tone: {tone}.",
        ]
        if extra:
            lines.append(f"- Extra understanding guidance: {extra}")
        return "\n".join(lines)

    def execute(self, input_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Classify message language, intent, and sentiment."""
        text = (input_data.get("text") or "").strip()
        lower = text.lower()

        # 1. Language Detection
        arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
        if arabic_chars > 3:
            detected_lang = "Arabic"
        elif any(w in lower for w in ["bonjour", "merci", "salut", "svp"]):
            detected_lang = "French"
        elif any(w in lower for w in ["hallo", "danke", "guten"]):
            detected_lang = "German"
        elif any(w in lower for w in ["kia", "kaise", "shukriya", "bhai"]):
            detected_lang = "Hindi/Urdu"
        else:
            detected_lang = "English"

        # 2. Intent Detection: question, complaint, order, other
        order_keywords = ["order", "buy", "purchase", "book", "quote", "pricing", "cost", "how much", "hire", "service", "start a project"]
        complaint_keywords = ["delay", "broken", "issue", "problem", "angry", "terrible", "worst", "unacceptable", "fix", "failed", "error", "cancel", "refund"]
        question_keywords = ["how", "what", "where", "when", "why", "who", "which", "can you", "do you", "is there", "?", "tell me"]

        if any(w in lower for w in complaint_keywords):
            detected_intent = "complaint"
        elif any(w in lower for w in order_keywords):
            detected_intent = "order"
        elif any(w in lower for w in question_keywords):
            detected_intent = "question"
        else:
            detected_intent = "other"

        # 3. Sentiment Detection: positive, neutral, negative
        pos_words = ["thank", "thanks", "great", "excellent", "awesome", "good", "perfect", "appreciate", "love", "nice"]
        neg_words = ["bad", "horrible", "terrible", "angry", "hate", "unhappy", "slow", "poor", "waste", "disappointed"]

        pos_count = sum(1 for w in pos_words if w in lower)
        neg_count = sum(1 for w in neg_words if w in lower)

        if detected_intent == "complaint" or neg_count > pos_count:
            sentiment = "negative"
        elif pos_count > 0 and neg_count == 0:
            sentiment = "positive"
        else:
            sentiment = "neutral"

        return {
            "language": detected_lang,
            "intent": detected_intent,
            "sentiment": sentiment,
            "summary": f"Language: {detected_lang} | Intent: {detected_intent} | Sentiment: {sentiment}",
        }
