/**
 * Jev via OpenRouter's Decisions API with @openrouter/sdk (template).
 *
 * Install: npm i @openrouter/sdk   Env: OPENROUTER_API_KEY
 * Endpoint: POST https://openrouter.ai/api/alpha/decisions (alpha; re-check docs before relying on new fields)
 * Differences from TypeSafe native: noul criteria need BOTH true and false if present; no null in score
 * criteria; response adds id, provider, usage.cost. The SDK uses camelCase (sessionId, usage.inputTokens).
 * Verified against @openrouter/sdk 1.3.19 on 2026-09-22.
 */
import { OpenRouter } from "@openrouter/sdk";

const MODEL = "typesafe/jev-1.13"; // pinned; "~typesafe/jev-latest" moves

const openRouter = new OpenRouter({ apiKey: process.env.OPENROUTER_API_KEY });

// Tool-call risk questions (illustrative; refine wording with the official typesafe-ai skill).
const QUESTIONS = {
  category: {
    type: "choice" as const,
    instructions: "What kind of effect does this shell command have?",
    criteria: {
      read_only: "Only reads files, state, or metadata",
      reversible_write: "Changes state in a way that is easy to undo",
      destructive: "Deletes data, rewrites history, or is otherwise hard to undo",
      exfiltration: "Sends local data or secrets to an external destination",
      unclear: "Effect cannot be determined from the command",
    },
  },
  irreversible: {
    type: "noul" as const,
    instructions: "The command deletes data, rewrites git history, force-pushes, drops tables, or touches production",
    // Decisions API: if you give criteria, give both sides.
    criteria: { true: "Hard or impossible to undo", false: "Easily undone or read-only" },
  },
};

// Placeholders until calibrated.
const IRREVERSIBLE_ASK_MIN = 0.3;
const CATEGORY_MIN_CONFIDENCE = 0.6;

export type GateDecision = "ask" | "deny" | "pass";

/** Returns "pass" (defer to normal permission flow), "ask", or "deny". Fails closed to "ask". */
export async function gateCommand(command: string, sessionId?: string): Promise<GateDecision> {
  try {
    const res = await openRouter.alpha.decisions.create(
      { decisionsRequest: { model: MODEL, state: { command }, questions: QUESTIONS, sessionId } },
      // RequestOptions shape taken from @openrouter/sdk 1.3.19 type declarations (alpha SDK; re-check on upgrade).
      { timeoutMs: 4000, retries: { strategy: "none" } },
    );
    const category = res.answers.category;
    const irreversible = res.answers.irreversible;
    if (category?.type !== "choice" || irreversible?.type !== "noul") return "ask"; // unexpected shape
    console.info("jev", { id: res.id, model: res.model, cost: res.usage.cost, category, irreversible });

    if (category.choice === "exfiltration") return "deny";
    if (irreversible.noul >= IRREVERSIBLE_ASK_MIN) return "ask";
    if (["destructive", "unclear"].includes(category.choice)) return "ask";
    if ((category.confidence ?? 0) < CATEGORY_MIN_CONFIDENCE) return "ask";
    return "pass";
  } catch (err) {
    // 402 = out of credits, 429/529 = overloaded, timeout, network: all fail closed.
    console.warn("jev gate unavailable, failing closed", err);
    return "ask";
  }
}
