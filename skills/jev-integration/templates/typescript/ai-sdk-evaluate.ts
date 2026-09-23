/**
 * Jev via Vercel AI SDK `experimental_evaluate` (template).
 *
 * Install: npm i ai@7.0.111 @ai-sdk/typesafe-ai   (pin: the evaluate API is experimental)
 * Model:
 *   - Gateway string "typesafe-ai/jev" needs ai >= 7.0.105 and AI_GATEWAY_API_KEY or `vercel env pull` (OIDC)
 *   - Direct: typeSafeAi.evaluationModel("jev-1.13.0") with TYPESAFE_AI_API_KEY (note: not TYPESAFE_API_KEY)
 *   - OpenRouter: openrouter.decisionModel("typesafe/jev-1.13") from @openrouter/ai-sdk-provider >= 3.1.0;
 *     confidence then lives at providerMetadata.openrouter.answers[id].confidence
 * Verified against ai 7.0.111 / @ai-sdk/typesafe-ai 3.0.4 on 2026-09-22.
 */
import { experimental_evaluate as evaluate } from "ai";
import { typeSafeAi } from "@ai-sdk/typesafe-ai";

// --- Questions (refine wording with the official typesafe-ai skill / docs) ----------------
export const QUESTIONS = {
  team: {
    type: "choice",
    instructions: "Which team should handle this support ticket?",
    criteria: {
      billing: "Charges, invoices, refunds, subscription changes",
      technical: "Bugs, outages, integration failures",
      account: "Login, permissions, profile changes",
      other: "Anything that does not clearly fit the teams above",
    },
  },
  severity: {
    type: "score",
    instructions: "How severe is the issue for the customer?",
    criteria: [
      "Cosmetic or informational question",
      "Degraded, but a workaround exists",
      "Blocking, no workaround",
      "Blocking and causing financial or data loss",
    ],
  },
  refundRequested: { type: "boolean", instructions: "The customer is asking for money back" },
} as const;

// --- Thresholds: placeholders until calibrated (see references/calibration-and-ops.md) ----
export const TEAM_AUTO_ROUTE_MIN_CONFIDENCE = 0.8; // TODO(calibrate)
export const REFUND_FLAG_MIN_PROB = 0.7; // TODO(calibrate)
export const SEVERITY_PAGE_MIN_SCORE = 2.5; // TODO(calibrate)

export type Route = "auto" | "review" | "human";
export interface Decision {
  route: Route;
  team?: string;
  pageOnCall: boolean;
  refundReview: boolean;
  reason: string;
}

type EvalResult = Awaited<ReturnType<typeof evaluate<typeof QUESTIONS>>>;

/** Pure policy: answers -> action. Unit-test with the mock model below. */
export function decide(result: EvalResult): Decision {
  const { team, severity, refundRequested } = result.answers;
  // Confidence is provider metadata, keyed by question id (choice/score only).
  const confidence = (result.providerMetadata?.typesafe?.confidence ?? {}) as Record<string, number | undefined>;
  const teamConf = confidence.team ?? 0; // missing confidence => treat as low, never as high

  const refundReview = refundRequested.probability >= REFUND_FLAG_MIN_PROB;
  const pageOnCall = severity.score >= SEVERITY_PAGE_MIN_SCORE;
  if (team.choice === "other") return { route: "human", team: team.choice, pageOnCall, refundReview, reason: "no team fits" };
  if (teamConf >= TEAM_AUTO_ROUTE_MIN_CONFIDENCE && !refundReview)
    return { route: "auto", team: team.choice, pageOnCall, refundReview, reason: `conf=${teamConf}` };
  return { route: "review", team: team.choice, pageOnCall, refundReview, reason: `conf=${teamConf}` };
}

/** Calls Jev with a hard deadline; fails to the human queue on any error. */
export async function triage(ticket: { subject: string; message: string }, deadlineMs = 3000): Promise<Decision> {
  try {
    const result = await evaluate({
      model: typeSafeAi.evaluationModel("jev-1.13.0"), // pinned; or "typesafe-ai/jev" via Gateway
      state: ticket,
      questions: QUESTIONS,
      maxRetries: 1,
      abortSignal: AbortSignal.timeout(deadlineMs),
      // Gateway only: providerOptions: { gateway: { zeroDataRetention: true } },
    });
    const decision = decide(result);
    console.info("jev", { decision, modelId: result.response?.modelId, usage: result.usage, answers: result.answers });
    return decision;
  } catch (err) {
    console.warn("jev unavailable, failing to human queue", err);
    return { route: "human", pageOnCall: false, refundReview: false, reason: "jev error" };
  }
}
