# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: greenfield

As of this writing the repository contains only one file: the source paper
`Economic Links and Predictable Returns (Cohen & Frazzini 2006).pdf`. There is
no code, build system, dependency manifest, or test suite yet. Do not document
build/lint/test commands until they actually exist — add them here as they are
introduced.

This folder is **not** a git repository yet (the machine convention is one git
repo per project under `~/projects`). Consider `git init` (or `newrepo`) before
the first substantive commit.

## What this project is about

The goal is to implement and backtest the trading strategy from Cohen &
Frazzini, "Economic Links and Predictable Returns" (this draft dated
2006-02-23; later published in the *Journal of Finance*, 2008). Details below
were verified against the PDF text (extracted via `pdftotext`), not recalled
from memory.

Core finding: due to investor limited attention, stock prices do not promptly
incorporate news about *economically linked* firms, producing cross-firm return
predictability. The links used are **customer-supplier** relationships. Under
SFAS 131 (SFAS 14 before 1997), a firm must disclose the identity of any
customer representing **more than 10% of total sales**; in the linked sample the
average customer accounts for **~20%** of the supplier's sales.

The strategy: each month, go long suppliers whose principal customer had the
most positive stock return last month and short those whose customer had the
worst, then rebalance monthly. The headline result is a long/short monthly alpha
of **over 150 basis points (>18% per year)**. Baseline portfolios are
**equal-weighted**; value-weighted variants are also reported. Risk adjustment
uses a **4-factor (Carhart) model**. The Coastcast / Callaway pair (Section I)
is the motivating worked example.

Key data facts for replication:
- **Universe / returns**: CRSP/Compustat, U.S. common stocks (CRSP share codes
  10 and 11).
- **Link data**: firms' principal customers from the **Compustat segment
  files**, mapped to the customer's CRSP `permno`.
- **Sample period**: customer-supplier data cover **1980–2004**.

## Likely shape of the work (once code exists)

A faithful replication will generally need:

- **Link data**: customer-supplier relationships. In the paper this comes from
  Compustat segment files. If those are unavailable, a documented proxy /
  substitute source must be chosen and noted.
- **Returns data**: monthly equity returns (CRSP-style) for suppliers and their
  named customers.
- **Signal construction**: prior-month customer return → supplier trade signal.
- **Portfolio formation & backtest**: monthly rebalanced long-short book, with
  standard risk adjustment (e.g. CAPM / Fama-French factors) to report alpha.

When building these, keep the pipeline stages separable (data ingest → link
mapping → signal → portfolio → performance) so each can be verified against the
paper independently.

## Conventions

Follow the machine-global conventions in `~/.claude/CLAUDE.md` (concise commits
and push after meaningful changes, finance/quant framing, autonomy rules).
Prefer the standard library and well-established quant tooling (pandas, numpy)
over bespoke code or new dependencies.
