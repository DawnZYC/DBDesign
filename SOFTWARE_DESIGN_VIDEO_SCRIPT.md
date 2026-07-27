# Software Design — 5-Minute Video Script

Rubric: 1. Software design — a. Use case diagram · b. Class & sequence diagrams for
analysis *and* design of a **critical use case**, highlighting **(i) transition from
analysis to design** and **(ii) design patterns** · c. Data schemas and models.

**Approach.** This is a presentation of *our project*, not a UML lecture. The whole
video follows **one real question an analyst types into Strata** and shows how our
design answers it. The OOAD ideas — analysis vs design, the transition, the patterns
— come out of the concrete walkthrough, not the other way round. The running example:

> *"What was the emission factor for solar PV in 2030 — and where does that number
> come from?"*

That one question touches every part of the system, which is why UC11 is the use case
we go deep on.

Language: English. Style: talk over each diagram, one on screen at a time. Runs to **4:55**.

## Diagram order (open full-screen, in sequence)

1. `docs/diagrams/02_use_case_diagram.svg`
2. `docs/diagrams/1_analysis_class_diagram.png`
3. `docs/diagrams/2_analysis_sequence_diagram.png`
4. `docs/diagrams/3_design_class_diagram.png`
5. `docs/diagrams/4_design_sequence_diagram.png`
6. `docs/diagrams/DB schema.jpg`

---

## 0:00 – 0:40 · What the project is, and the question we'll follow (a)

**On screen:** `02_use_case_diagram.svg`.

> "This is **Strata** — a platform we built so energy analysts can work with the
> EcoTEA energy-model dataset by just asking questions in plain language.
>
> The use case diagram shows everything the platform does, in two halves. The green
> half is getting data *in* — an analyst converts a raw model file, imports it, and
> the system flags data-quality problems along the way. The blue half is getting
> insight *out* — and that's where our headline feature lives: use case 11, **ask a
> question in natural language**.
>
> On the right you can see we treat the LLM and the embedding service as *external
> actors* — deliberately, because we designed the system so any provider is swappable.
>
> For the rest of this video I'll follow one real question through use case 11 —
> *what was the emission factor for solar PV in 2030, and where did that number come
> from* — because answering it touches every layer we designed: understanding the
> question, running a safe query, explaining the result, drawing a chart, and proving
> where the figure came from."

**Covers:** a.

---

## 0:40 – 1:20 · How we first understood the problem — the analysis model (b)

**On screen:** `1_analysis_class_diagram.png`.

> "Before writing any code, we modelled the problem in the analyst's own language.
> Every box here is a word an energy analyst already uses — a `Question`, an
> `AnalysisPlan`, an `AnswerSet`, `DataPoint`s, a `Chart`. You'll notice there's no
> database, no API, no AI model in this picture. That's intentional: at this stage we
> only cared about *what the business is*, not how we'd build it.
>
> For our solar-PV question, the one relationship that shaped everything is this one —
> **every `DataPoint` links to exactly one `SourceCell`.** We decided up front that
> the emission-factor number the analyst gets back must always be traceable to the
> exact spreadsheet cell it came from. That single business rule ends up driving a lot
> of our design — keep an eye on it."

**Switch to `2_analysis_sequence_diagram.png`:**

> "This is the same question as a business process. The analyst asks about solar PV;
> the platform works out what's being asked, fetches the figures, explains what they
> mean, optionally charts them, and — bottom of the diagram — when the analyst clicks
> a value, reveals the source cell.
>
> Notice Strata is still one black box here, and these four lanes are *responsibilities*
> — understanding, retrieval, insight, visualisation — not classes yet. This is our
> analysis of the problem, before any technology choices."

**Covers:** b (analysis).

---

## 1:20 – 2:35 · How we turned that into a real design (b.i — the core of the talk)

**On screen:** `3_design_class_diagram.png`.

> "Now here's how we actually built it — and the rule we set ourselves was that
> **nothing in the design gets invented; every piece has to trace back to something in
> the analysis.**
>
> So the analyst's `Question` becomes a real `ChatRequest` coming into our controller.
> The `AnalysisPlan` and everything the pipeline produces become fields on one object,
> `AgentState`. The `AnswerSet` becomes a `QueryResult`. And that `SourceCell` we cared
> about becomes a real `RawRow` table plus an endpoint that serves it.
>
> Three design decisions are worth showing on our solar-PV example, because they only
> appear once you go from *what* to *how*:
>
> **One** — analysis had sixteen separate objects. In the build, they collapse into a
> single shared `AgentState` that flows through the pipeline, because we chose
> LangGraph to orchestrate the agents. The business concepts survive as *groups of
> fields* inside it.
>
> **Two** — that one 'Strata' black box splits in two: a controller that handles the
> web streaming, and a graph that decides which agent runs next. We split them so we
> can test the whole reasoning pipeline without a browser.
>
> **Three** — this is the payoff of that `SourceCell` rule. To answer *where did the
> solar-PV number come from*, we carry a `raw_row_id` through the query result, into
> the chart data, and out through a trace endpoint. One business rule from analysis
> turned into three concrete choices across three different layers of the build."

**Switch to `4_design_sequence_diagram.png` (~25 s):**

> "And this is our solar-PV question actually running through the real code. The one
> black box from before is now nine collaborators across every layer. Two things I'd
> point out: when we turn the plan into a query, we use structured output so the AI
> fills in *fields* — it physically cannot write raw SQL against our database. And the
> explanation streams back token by token, so the analyst sees the answer forming
> live. Same steps as the analysis diagram — now real calls."

**Covers:** b.i.

---

## 2:35 – 3:40 · The design patterns we leaned on, and why (b.ii)

**On screen:** stay on `3_design_class_diagram.png`; point to the yellow tags.

> "Those yellow tags mark the design patterns we used. I won't list all twelve — let
> me show the four that earned their place on our solar-PV example.
>
> Remember we made the LLM an external, swappable actor? That's a **Factory plus
> Registry**: `get_chat_model` looks a provider up in a registry, and all six vendors
> we support sit behind one interface. Adding a seventh is a single line — that's
> **Strategy** in action, and we use the same trick for the five pipeline steps.
>
> **Repository** — `run_sql` is the *only* way into our technology tables. Nothing
> above it touches SQL or a database session; callers just hand over a validated query
> object. That's also why the AI can't inject SQL — the query is a **Command object**,
> a validated value that literally has no field for raw SQL. Our injection-safety is a
> property of the design, not a filter we bolted on.
>
> And the live reasoning trace the analyst sees? That's **Blackboard plus Observer** —
> every agent writes to the shared `AgentState`, the graph publishes each write, and
> the frontend subscribes. One mechanism, and the trace UI came almost for free.
>
> The point isn't that we used patterns for their own sake — it's that each one
> bought us something specific: a new AI provider, a new tool, or a new chart type is
> always a small, local change."

**Covers:** b.ii.

---

## 3:40 – 4:35 · The data behind it all — schema and models (c)

**On screen:** `DB schema.jpg` (pan across, or three pre-zoomed crops).

> "Underneath everything is our PostgreSQL schema, and it's organised in three tiers.
>
> On the left is the **provenance tier** — `import_batch` and `raw_excel_row`. When
> the EcoTEA workbook is imported, every original row is kept here, cells and all.
> This is the physical home of that source-cell rule: the `raw_row_id` threads through
> the whole database so our solar-PV figure can always be traced home.
>
> In the middle are the **reference tables** — sector, geography, commodity, the
> technologies themselves — the dimensions we describe data by.
>
> On the right is the **fact tier**. `technology_year` is the heart of it — one row per
> technology per year, so 'solar PV in 2030' is literally one row — and it fans out to
> satellite tables for emission factors, cost parameters, and constraints. The
> emission factor our analyst asked about lives in `technology_year_ecotea_parameter`,
> right here.
>
> And `traceability_record` in the centre links each clean technology row back to the
> raw import row it came from. The audit trail isn't documentation — it's enforced by
> foreign keys in the schema itself."

**Covers:** c.

---

## 4:35 – 4:55 · Close

**On screen:** back to `3_design_class_diagram.png`.

> "So that's Strata through one real question: modelled first in the analyst's
> language, built as a layered design where every piece traces back to that model,
> held together by patterns that keep it easy to extend, and backed by a schema that
> never loses track of where a number came from. Thanks for watching."

---

## Time budget

| Segment | Length | Rubric |
|---|---|---|
| Project intro + use case | 0:40 | a |
| Analysis (class + sequence) | 0:40 | b |
| Analysis → design transition | 1:15 | b.i |
| Design patterns | 1:05 | b.ii |
| Data schema | 0:55 | c |
| Close | 0:20 | — |
| **Total** | **4:55** | |

## Recording notes

- Keep the **solar-PV question** on the tip of your tongue in every segment — it's the
  thread that turns six diagrams into one story. Every segment should refer back to it.
- **One diagram full-screen at a time**, zoomed to the region you're naming. The class
  and sequence PNGs are large; pre-crop the key areas so text stays legible. The DB
  schema JPG is very wide — use three pre-zoomed crops (provenance / reference / fact).
- Protect the **transition segment (1:20–2:35)** — the rubric calls it out explicitly.
  If you run over, trim the analysis-sequence detail and the Blackboard/Observer
  pattern first; never cut the three transition decisions or the source-cell thread.
- Don't read boxes aloud. Name only the elements the solar-PV story needs.
