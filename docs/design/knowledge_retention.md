# Design Document: Knowledge Retention & Enhanced Summarization

## 1. Overview
This feature adds "Knowledge Retention" capabilities to the Technical Blog Monitor. It transforms the tool from a passive feed reader into an active learning aid.

## 2. Key Features

### 2.1. Enhanced Summarization (Meaningful Summaries)
**Goal:** Replace generic feed summaries with dense, insight-focused summaries generated from the full article content.

**Strategy:**
1.  **LLM Integration:** Integrate a Generative AI client (OpenAI/Ollama) separate from the Embedding client.
2.  **Prompt Engineering:**
    *   *Input:* Cleaned article text.
    *   *Instruction:* "Identify the unique technical contributions of this post. Exclude boilerplate, marketing fluff, and generic intros. Summarize the core architectural decisions, code patterns, or lessons learned."
3.  **Storage:** Store the generated summary in `BlogPost.metadata['ai_summary']`.
4.  **Trigger:** Run this pipeline after `extract_article_content`.

### 2.2. Spaced Repetition (Review System)
**Goal:** Ensure long-term retention of read articles through periodic resurfacing.

**Workflow:**
1.  **Mark as Read:** User clicks "Mark as Read" on an article.
    *   System records `read_at` timestamp.
    *   System schedules first review: `next_review_at = now + 30 days`.
    *   State changes to `READ`.
2.  **Review Queue:**
    *   Dashboard displays a "Review Queue" for items where `next_review_at <= now`.
    *   Items in review show the *Enhanced Summary* (short form) rather than the full text.
3.  **Progression:**
    *   **Stage 1 (30 days):** First review. If confirmed/reviewed, schedule Stage 2.
    *   **Stage 2 (90 days):** Second review.
    *   **Stage 3 (Archived):** Done.

## 3. Data Model Updates

### 3.1. BlogPost / Metadata
We will use the existing `metadata` JSONB field in `BlogPost` to store these fields to avoid immediate schema migrations if possible, or extend the schema if we want strict typing.

**New Metadata Fields:**
*   `ai_summary`: str (The generated insight summary)
*   `retention_policy`: dict
    *   `status`: "unread" | "read" | "review_due" | "archived"
    *   `read_at`: iso8601_timestamp
    *   `last_reviewed_at`: iso8601_timestamp
    *   `next_review_at`: iso8601_timestamp
    *   `review_stage`: int (0, 1, 2...)

## 4. Implementation Plan

### Phase 1: Infrastructure
*   [ ] Add `LLMConfig` to `monitor/config.py` (API keys, model names for generation).
*   [ ] Create `monitor/llm/` module with `GenerationClient`.

### Phase 2: Summarization
*   [ ] Implement `generate_summary` task.
*   [ ] Hook into `process_individual_article`.

### Phase 3: Retention Logic
*   [ ] Implement `mark_as_read` logic/API.
*   [ ] Implement `get_review_queue` logic/API.
*   [ ] Update Web Dashboard to show "Mark as Read" button and "Review" tab.
