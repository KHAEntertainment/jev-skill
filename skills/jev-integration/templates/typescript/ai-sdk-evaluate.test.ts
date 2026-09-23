/**
 * Offline tests for the policy in ai-sdk-evaluate.ts using the AI SDK mock evaluation model.
 * Run: npx vitest run   (no network, no key)
 */
import { describe, expect, it } from "vitest";
import { experimental_evaluate as evaluate } from "ai";
import { Experimental_EvaluationMockModelV4 as MockEvaluationModel } from "ai/test";
import { QUESTIONS, decide } from "./ai-sdk-evaluate.js";

// The AI SDK validates mock answers like real ones: a choice's `probabilities` must cover every
// option and sum to 1 (within rounding). Build a complete distribution, or omit `probabilities`.
function distribution(winner: string, p: number): Record<string, number> {
  const options = Object.keys(QUESTIONS.team.criteria);
  const rest = (1 - p) / (options.length - 1);
  return Object.fromEntries(options.map((o) => [o, o === winner ? p : rest]));
}

function mock(team: string, teamConfidence: number, refundP: number, severity = 1) {
  return new MockEvaluationModel({
    provider: "typesafe-ai",
    modelId: "jev-1.13.0",
    supportedQuestionTypes: ["choice", "score", "boolean"],
    doEvaluate: async () => ({
      answers: {
        team: { type: "choice", choice: team, probabilities: distribution(team, teamConfidence) },
        severity: { type: "score", score: severity },
        refundRequested: { type: "boolean", probability: refundP },
      },
      warnings: [],
      providerMetadata: { typesafe: { confidence: { team: teamConfidence, severity: 0.9 } } },
    }),
  });
}

const run = (model: MockEvaluationModel) =>
  evaluate({ model, state: { subject: "s", message: "m" }, questions: QUESTIONS });

describe("jev triage policy", () => {
  it("auto-routes confident, non-refund tickets", async () => {
    expect(decide(await run(mock("technical", 0.92, 0.05))).route).toBe("auto");
  });
  it("sends low-confidence tickets to review", async () => {
    expect(decide(await run(mock("billing", 0.55, 0.05))).route).toBe("review");
  });
  it("flags refunds for review even when team confidence is high", async () => {
    const d = decide(await run(mock("billing", 0.95, 0.9)));
    expect(d.route).toBe("review");
    expect(d.refundReview).toBe(true);
  });
  it("sends 'other' to a human", async () => {
    expect(decide(await run(mock("other", 0.99, 0.0))).route).toBe("human");
  });
  it("pages on-call for loss-level severity", async () => {
    expect(decide(await run(mock("technical", 0.9, 0.0, 3))).pageOnCall).toBe(true);
  });
});
