import json
import re
import requests
from browser_tools import Browser

SYSTEM = """You are Servejit AI Agent, a cautious Python browser assistant.
Reply with exactly one JSON object containing thought, action, arguments, done, answer.
Allowed actions:
open {url}
extract {}
click {text} or {selector}
fill {selector, value}
wait {seconds}
finish {answer}
Rules:
- Inspect the page before interacting.
- Do not bypass login, CAPTCHA, OTP, paywalls or security controls.
- If authentication is needed, ask the user to sign in manually.
- Never invent results or claim success without page evidence.
- Do not purchase, pay, transfer, send, delete, publish or submit important forms without user approval.
- Use only the listed browser actions. JSON only, no markdown."""

class Agent:
    def __init__(self):
        self.browser = Browser()

    def close(self):
        self.browser.close()

    def ask(self, base, model, messages):
        url = base.rstrip("/") + "/api/chat"
        response = requests.post(url, json={"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.1}}, timeout=180)
        response.raise_for_status()
        return response.json()["message"]["content"]

    def parse(self, text):
        cleaned = re.sub(r"^\s*```(?:json)?|\`\`\`\s*$", "", text.strip(), flags=re.I)
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.S)
            if not match:
                raise ValueError("The model did not return valid JSON. Try again.")
            return json.loads(match.group(0))

    def run(self, task, base, model, max_steps, headless, allow_actions, memory):
        self.browser.start(headless)
        history = memory.list_recent(4)
        prior = "\n".join(["- " + x["task"] + ": " + x["result"][:200] for x in history])
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Task: " + task + "\nRecent memory:\n" + prior + "\nConsequential actions approved: " + str(allow_actions) + "\nBrowser state: " + self.browser.describe()}
        ]
        log = []
        answer = "Stopped without a confirmed result."
        for number in range(1, max_steps + 1):
            raw = self.ask(base, model, messages)
            decision = self.parse(raw)
            action = decision.get("action", "")
            args = decision.get("arguments", {}) or {}
            if action == "finish" or decision.get("done"):
                answer = decision.get("answer", "Task finished.")
                log.append({"step": number, "action": "finish", "detail": decision.get("thought", "")})
                break
            result = self.browser.execute(action, args, allow_actions)
            log.append({"step": number, "action": action, "detail": result["message"]})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Tool result: " + json.dumps(result, ensure_ascii=False) + "\nCurrent page: " + self.browser.describe() + "\nChoose next action or finish. Return JSON only."})
            if result.get("blocked"):
                answer = result["message"]
                break
        else:
            answer = "Maximum steps reached. Review the log and give a more specific follow-up."
        memory.add(task, answer)
        return {"answer": answer, "log": log}
