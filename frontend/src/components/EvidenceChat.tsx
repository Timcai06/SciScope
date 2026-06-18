"use client";

import { FormEvent, useMemo, useState } from "react";
import { askQuestion } from "@/api/client";
import type { ChatResponse } from "@/types";

const DEFAULT_QUESTION = "knowledge graph reasoning";

function isLowConfidence(confidence: string): boolean {
  return confidence.trim().toLowerCase().includes("low");
}

function confidenceLabel(confidence: string): string {
  const value = confidence.trim();
  return value ? value : "Unknown confidence";
}

export function EvidenceChat() {
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const normalizedQuestion = question.trim();
  const hasEvidence = (response?.evidence.length ?? 0) > 0;
  const hasLowConfidence = useMemo(() => (response ? isLowConfidence(response.confidence) : false), [response]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!normalizedQuestion || isLoading) {
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      setResponse(null);
      const chatResponse = await askQuestion(normalizedQuestion);
      setResponse(chatResponse);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to ask SciScope");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="border border-line bg-panel/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] sm:p-5">
      <div className="grid gap-5 lg:grid-cols-[minmax(18rem,0.78fr)_minmax(0,1.22fr)]">
        <form className="flex min-h-72 flex-col" onSubmit={handleSubmit}>
          <div className="border-b border-line pb-4">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyanSoft">Evidence Chat</p>
            <h2 className="mt-2 text-base font-semibold text-silver">Ask the indexed corpus</h2>
          </div>

          <label className="mt-5 text-xs font-medium uppercase tracking-[0.16em] text-silver/55" htmlFor="evidence-question">
            Question
          </label>
          <textarea
            className="mt-2 min-h-32 resize-y border border-line bg-graphite/70 px-3 py-3 text-sm leading-6 text-silver outline-none transition focus:border-cyanSoft/70 focus:bg-graphite disabled:cursor-not-allowed disabled:text-silver/45"
            disabled={isLoading}
            id="evidence-question"
            onChange={(event) => setQuestion(event.target.value)}
            value={question}
          />

          {error ? (
            <div className="mt-4 border border-signal/50 bg-signal/10 px-3 py-3 text-sm leading-6 text-silver/80">
              <span className="font-semibold text-signal">Chat API unavailable.</span> {error}
            </div>
          ) : null}

          <div className="mt-auto flex flex-col gap-3 pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-silver/45">Backend answers are shown with retrieved evidence when available.</p>
            <button
              className="border border-cyanSoft/50 bg-cyanSoft/10 px-4 py-2 text-sm font-semibold text-cyanSoft transition hover:bg-cyanSoft/15 disabled:cursor-not-allowed disabled:border-line disabled:bg-graphite/40 disabled:text-silver/35"
              disabled={!normalizedQuestion || isLoading}
              type="submit"
            >
              {isLoading ? "Asking..." : "Ask"}
            </button>
          </div>
        </form>

        <div className="min-h-72 border border-line bg-graphite/35 p-4 sm:p-5">
          {isLoading ? (
            <div className="grid h-full min-h-60 gap-4">
              <div className="h-28 animate-pulse bg-panel/80" />
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="h-28 animate-pulse bg-panel/80" />
                <div className="h-28 animate-pulse bg-panel/80" />
              </div>
            </div>
          ) : response ? (
            <div className="min-w-0">
              <div className="flex flex-col gap-3 border-b border-line pb-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase tracking-[0.2em] text-silver/55">Answer</p>
                  <p className="mt-3 min-w-0 break-words text-sm leading-7 text-silver/78 [overflow-wrap:anywhere]">
                    {response.answer || "No answer returned."}
                  </p>
                </div>
                <span
                  className={`shrink-0 border px-3 py-1 text-xs font-semibold ${
                    hasLowConfidence ? "border-signal/45 bg-signal/10 text-signal" : "border-cyanSoft/35 bg-cyanSoft/10 text-cyanSoft"
                  }`}
                >
                  {confidenceLabel(response.confidence)}
                </span>
              </div>

              {!hasEvidence || hasLowConfidence ? (
                <div className="mt-4 border border-dashed border-line bg-panel/50 px-3 py-3 text-sm leading-6 text-silver/55">
                  {!hasEvidence ? "No evidence cards were returned for this answer." : "Confidence is low; review the evidence before using this answer."}
                </div>
              ) : null}

              {hasEvidence ? (
                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  {response.evidence.map((item) => (
                    <article className="min-w-0 border border-line bg-panel/80 p-4" key={`${item.paper_id}-${item.title}`}>
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="min-w-0 break-words text-sm font-semibold leading-6 text-silver [overflow-wrap:anywhere]">
                          {item.title || "Untitled paper"}
                        </h3>
                        <span className="shrink-0 text-xs font-semibold text-cyanSoft">{item.year ?? "n/a"}</span>
                      </div>
                      <p className="mt-3 min-w-0 break-words text-sm leading-6 text-silver/58 [overflow-wrap:anywhere]">
                        {item.reason || "No evidence reason returned."}
                      </p>
                      <p className="mt-4 truncate border-t border-line pt-3 text-xs text-silver/38" title={item.paper_id}>
                        {item.paper_id || "Unknown paper id"}
                      </p>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="flex h-full min-h-60 items-center justify-center border border-dashed border-line bg-panel/45 px-4 text-center text-sm text-silver/45">
              Submit a question to inspect the answer and supporting evidence.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
