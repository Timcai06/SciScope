#!/usr/bin/env zsh
set -o pipefail

mkdir -p output/logs

{
  echo "[orchestrator] start $(date '+%Y-%m-%d %H:%M:%S')"
  echo "[orchestrator] phase 1: pubmed to 5300, two years at a time"
  for year in 2022 2023; do
    (
      make harvest-year BALANCE_SOURCE=pubmed BALANCE_YEAR="$year" BALANCE_LIMIT=5300 2>&1 \
        | tee "output/logs/harvest_pubmed_${year}_5300.log"
    ) &
  done
  wait
  echo "[orchestrator] phase 1 done $(date '+%Y-%m-%d %H:%M:%S')"

  echo "[orchestrator] phase 2: pubmed 2024-2025 to 5300, two years at a time"
  for year in 2024 2025; do
    (
      make harvest-year BALANCE_SOURCE=pubmed BALANCE_YEAR="$year" BALANCE_LIMIT=5300 2>&1 \
        | tee "output/logs/harvest_pubmed_${year}_5300.log"
    ) &
  done
  wait
  echo "[orchestrator] phase 2 done $(date '+%Y-%m-%d %H:%M:%S')"

  echo "[orchestrator] phase 3: pmc 2022-2026 to 5000, sequential for full-text stability"
  for year in 2022 2023 2024 2025 2026; do
    make harvest-year BALANCE_SOURCE=pmc BALANCE_YEAR="$year" BALANCE_LIMIT=5000 2>&1 \
      | tee "output/logs/harvest_pmc_${year}_5000.log"
  done
  echo "[orchestrator] phase 3 done $(date '+%Y-%m-%d %H:%M:%S')"

  echo "[orchestrator] phase 4: arxiv 2022-2025 to 5000, sequential to avoid 429"
  sleep 60
  for year in 2022 2023 2024 2025; do
    make harvest-year BALANCE_SOURCE=arxiv BALANCE_YEAR="$year" BALANCE_LIMIT=5000 2>&1 \
      | tee "output/logs/harvest_arxiv_${year}_5000.log"
    sleep 30
  done
  echo "[orchestrator] done $(date '+%Y-%m-%d %H:%M:%S')"
} 2>&1 | tee output/logs/backfill_5k_fulltext_orchestrator.log
