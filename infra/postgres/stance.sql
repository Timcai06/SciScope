-- Stance persistence for verify_claim (roadmap Step 2: 矛盾即资产).
--
-- Each verify_claim run with an LLM stance judgement appends its per-evidence
-- labels here. One row per (claim, paper): re-verifying the same claim updates
-- the paper's stance instead of inflating counts. The contradictions view is
-- the seed of the 科学争议地图 — it grows on its own as claims get checked.

CREATE TABLE IF NOT EXISTS claim_evidence_stance (
    id BIGSERIAL PRIMARY KEY,
    claim TEXT NOT NULL,
    claim_norm TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    paper_title TEXT NOT NULL DEFAULT '',
    paper_year INTEGER,
    stance TEXT NOT NULL CHECK (stance IN ('SUPPORT', 'CONTRADICT', 'NEUTRAL')),
    similarity REAL,
    verdict TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (claim_norm, paper_id)
);

CREATE INDEX IF NOT EXISTS claim_evidence_stance_claim_idx
    ON claim_evidence_stance (claim_norm);
CREATE INDEX IF NOT EXISTS claim_evidence_stance_paper_idx
    ON claim_evidence_stance (paper_id);

-- Claims where the literature disagrees: at least one supporting and one
-- contradicting paper. Derived, so it stays consistent with the base table.
CREATE OR REPLACE VIEW contradictions AS
SELECT
    claim_norm,
    min(claim) AS claim,
    count(*) FILTER (WHERE stance = 'SUPPORT') AS support_count,
    count(*) FILTER (WHERE stance = 'CONTRADICT') AS contradict_count,
    count(DISTINCT paper_id) AS paper_count,
    max(created_at) AS last_seen
FROM claim_evidence_stance
GROUP BY claim_norm
HAVING count(*) FILTER (WHERE stance = 'SUPPORT') > 0
   AND count(*) FILTER (WHERE stance = 'CONTRADICT') > 0;
