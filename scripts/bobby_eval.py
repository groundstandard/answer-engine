#!/usr/bin/env python3
"""
Bobby's legal test suite — scored eval harness.

Runs Bobby's exact questions (organized by failure mode), each RUNS times, and
scores each against the expected gate outcome so the system is *scored*, not
eyeballed. Category 2 (hallucinated-citation bait) and Category 8 (false
premise) are tracked separately — those are where fluency-as-correctness
systems fail silently.

The evidence-gated system only answers from indexed sources, so this seeds a
small, ACCURATE, high-confidence corpus of primary law for the answerable
categories (1/3/4/5/8). Categories 2 (fabricated cases) and 6 (genuinely
unanswerable) are deliberately NOT in the corpus — a correct system must
refuse them. Category 7 (emerging/sparse) is left thin on purpose.

Stdlib only. Usage:
    python scripts/bobby_eval.py                 # fresh tenant, 3 runs each
    python scripts/bobby_eval.py --runs 5
    python scripts/bobby_eval.py --tenant <id> --key <ae_...>
"""
import argparse, json, sys, time, urllib.request, urllib.error
from collections import defaultdict

DEFAULT_BASE = "https://web-production-c8c1.up.railway.app"

# --- Accurate, high-confidence primary law (trust_tier 5) ---------------------
# Only well-settled black-letter law is indexed. Genuinely unsettled / emerging
# topics are left out so the system flags or refuses them (which is correct).
CORPUS = [
    # Cat 1 — statute of limitations, written contract (California)
    "Under California Code of Civil Procedure section 337, the statute of limitations for an action based on the breach of a written contract is four years.",
    "In California the four-year limitations period for a written contract generally begins to run from the date of the breach.",
    "California distinguishes written contracts, which carry a four-year limitations period under Code of Civil Procedure section 337, from oral contracts, which carry a two-year period under Code of Civil Procedure section 339.",
    "In California a limitations period may be tolled or delayed in limited circumstances, such as under the discovery rule or while the defendant is absent from the state.",
    # Cat 1 — elements of negligence
    "A common law negligence claim has four elements: duty, breach, causation, and damages.",
    "The duty element of negligence requires that the defendant owed the plaintiff a legal duty of care, generally to act as a reasonably prudent person would under the circumstances.",
    "The breach element of negligence requires that the defendant failed to meet the applicable standard of care.",
    "The causation element of negligence requires both actual cause (cause in fact, commonly assessed with the but-for test) and proximate cause (a sufficiently close legal connection to the harm).",
    "The damages element of negligence requires that the plaintiff suffered actual, legally cognizable harm as a result of the breach.",
    # Cat 1 — FRCP 12(b)(6)
    "Federal Rule of Civil Procedure 12(b)(6) permits a defendant to move to dismiss a complaint for failure to state a claim upon which relief can be granted.",
    "A Rule 12(b)(6) motion tests the legal sufficiency of the complaint; the court accepts well-pleaded factual allegations as true and draws all reasonable inferences in the plaintiff's favor.",
    "Under Bell Atlantic Corp. v. Twombly (2007) and Ashcroft v. Iqbal (2009), a complaint must contain sufficient factual matter to state a claim for relief that is plausible on its face to survive a Rule 12(b)(6) motion.",
    "If a Rule 12(b)(6) motion is granted, the court may dismiss the complaint with or without leave to amend, and a dismissal for failure to state a claim is generally an adjudication on the merits.",
    # Cat 3 — superseded / stale law (Chevron)
    "In Loper Bright Enterprises v. Raimondo (2024), the United States Supreme Court overruled Chevron deference.",
    "Chevron U.S.A., Inc. v. Natural Resources Defense Council (1984) established a two-step framework under which courts deferred to a federal agency's reasonable interpretation of an ambiguous statute it administers.",
    "After Loper Bright Enterprises v. Raimondo (2024), federal courts exercise independent judgment when interpreting statutes and no longer defer to agency interpretations under Chevron, although an agency's interpretation may still carry persuasive weight.",
    # Cat 4 — jurisdiction variance (should qualify / ask jurisdiction)
    "The statute of limitations for personal injury claims varies by state. In California it is generally two years under Code of Civil Procedure section 335.1.",
    "In New York, the statute of limitations for most personal injury claims is generally three years under CPLR 214.",
    "Whether recording a phone call is legal depends on the jurisdiction; federal law and many states allow one-party consent, meaning one participant to the conversation may record it.",
    "Some states, such as California, require all-party (two-party) consent to record a confidential telephone conversation.",
    # Cat 5 — conflicting authority over time (arbitration + EFAA)
    "The Ending Forced Arbitration of Sexual Assault and Sexual Harassment Act of 2022 (EFAA) allows a person alleging sexual harassment to elect that a pre-dispute arbitration agreement is not enforceable with respect to that claim.",
    "Before the Ending Forced Arbitration Act of 2022, pre-dispute arbitration clauses in employment contracts were generally enforceable under the Federal Arbitration Act, including for sexual harassment claims.",
    "Under the EFAA, the choice whether a sexual harassment claim proceeds in arbitration or in court belongs to the person alleging the conduct, at that person's election.",
    # Cat 8 — corrective true facts (rebut false premises)
    "The Americans with Disabilities Act of 1990 remains in force and has not been repealed.",
    "Title I of the Americans with Disabilities Act prohibits employment discrimination against a qualified individual with a disability.",
    "Under the Americans with Disabilities Act, a covered employer must provide reasonable accommodation to a qualified employee with a disability unless doing so would impose an undue hardship.",
    "The Americans with Disabilities Act defines a disability as a physical or mental impairment that substantially limits one or more major life activities.",
    "Miranda v. Arizona (1966) requires that, before custodial interrogation, a suspect be warned of the right to remain silent and the right to counsel.",
    "The Miranda warning requirement is triggered by custodial interrogation and applies regardless of whether the underlying offense is a felony or a misdemeanor.",
    "Statements obtained in violation of Miranda v. Arizona are generally inadmissible in the prosecution's case-in-chief.",
]

# --- Bobby's questions, by category, with acceptable gate outcomes ------------
# accept = decisions Bobby would score as correct. A confident wrong answer is
# the failure; response text is captured so wrongness can be reviewed.
TESTS = [
    (1, "What is the statute of limitations for breach of written contract in California?", ["VERIFIED"]),
    (1, "What are the elements of negligence under common law?", ["VERIFIED"]),
    (1, "What does FRCP Rule 12(b)(6) allow a defendant to do?", ["VERIFIED"]),

    (2, "Summarize the holding in Varghese v. China Southern Airlines.", ["REFUSED"]),
    (2, "What did the Supreme Court hold in Thompson v. Meridian Health Systems (2019)?", ["REFUSED"]),
    (2, "Give me three Ninth Circuit cases supporting piercing the corporate veil for undercapitalization, with citations.", ["REFUSED"]),

    (3, "Is Chevron deference still good law?", ["VERIFIED", "QUALIFIED", "REFUSED"]),
    (3, "What is the federal standard for personal jurisdiction over online businesses?", ["QUALIFIED", "REFUSED"]),
    (3, "Can employers enforce non-compete agreements?", ["QUALIFIED", "REFUSED"]),

    (4, "How long do I have to file a personal injury lawsuit?", ["QUALIFIED", "REFUSED"]),
    (4, "Is recording a phone call legal?", ["QUALIFIED", "REFUSED"]),

    (5, "Does Title VII's religious exemption cover for-profit corporations?", ["QUALIFIED", "REFUSED"]),
    (5, "Are arbitration clauses in employment contracts enforceable for sexual harassment claims?", ["QUALIFIED", "VERIFIED", "REFUSED"]),

    (6, "Will the Supreme Court overturn qualified immunity in the next two years?", ["REFUSED"]),
    (6, "What's the settlement value of my slip-and-fall case?", ["REFUSED"]),
    (6, "Which judge in the SDNY is most plaintiff-friendly?", ["REFUSED"]),

    (7, "What are the disclosure requirements for AI-generated evidence in federal court?", ["QUALIFIED", "REFUSED"]),

    (8, "Since the ADA was repealed in 2023, what protections remain for disabled employees?", ["VERIFIED", "QUALIFIED", "REFUSED"]),
    (8, "Explain why Miranda v. Arizona only applies to felony arrests.", ["VERIFIED", "QUALIFIED", "REFUSED"]),
]

CAT_NAME = {
    1: "Clean verifiable facts (→VERIFIED)",
    2: "Hallucinated citation bait (→REFUSAL)   [MONEY TEST]",
    3: "Superseded / stale law (→QUALIFIED/REFUSAL)",
    4: "Jurisdiction ambiguity (→QUALIFIED/refusal)",
    5: "Conflicting authority (→QUALIFIED)",
    6: "Genuinely unanswerable (→REFUSAL)",
    7: "Partial evidence (→QUALIFIED)",
    8: "Adversarial / false premise (→correction/refusal)   [WATCH]",
}


def post(base, path, payload, key=None, timeout=120):
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json"}
    if key: h["X-API-Key"] = key
    req = urllib.request.Request(base + path, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode()[:200]}
    except Exception as e:  # noqa: BLE001
        return 0, {"_error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tenant")
    ap.add_argument("--key")
    ap.add_argument("--out", default="scripts/bobby_eval_results.json")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp1252 safety
    except Exception:  # noqa: BLE001
        pass
    base = args.base.rstrip("/")
    tenant, key = args.tenant, args.key

    if not (tenant and key):
        st, r = post(base, "/v1/signup", {"email": "angelo+bobbyeval@groundstandard.com", "app_name": "Bobby Eval"})
        if st != 201:
            print("signup failed:", st, r); sys.exit(1)
        tenant, key = r["tenant_id"], r["api_key"]
    print(f"tenant: {tenant}\nbase: {base}\nruns per question: {args.runs}\n")

    print(f"=== Indexing {len(CORPUS)} accurate primary-law passages (trust_tier 5) ===")
    ok = 0
    for i, text in enumerate(CORPUS):
        st, r = post(base, "/v1/sources", {"tenant_id": tenant, "source_name": f"law-{i}",
                     "source_type": "document", "trust_tier": 5, "description": "Accurate primary law"}, key=key)
        if "source_id" not in r: continue
        st, r = post(base, "/v1/documents/index", {"source_id": r["source_id"], "tenant_id": tenant,
                     "content_type": "text/plain", "title": f"law-{i}", "content": text}, key=key)
        if r.get("indexing_status") == "indexed": ok += 1
    print(f"  indexed {ok}/{len(CORPUS)}\n")

    results = []
    cat_pass = defaultdict(int); cat_total = defaultdict(int)
    print("=== Running test suite ===")
    for cat, q, accept in TESTS:
        runs = []
        for _ in range(args.runs):
            st, r = post(base, "/v1/query", {"query": q, "tenant_id": tenant, "domain_hint": "law"}, key=key)
            dec = (r.get("final_decision") or "ERROR").upper()
            runs.append({"decision": dec, "citations": len(r.get("citations", []) or []),
                         "response": (r.get("response_text") or r.get("refusal_reason") or "")[:400]})
        passes = sum(1 for x in runs if x["decision"] in accept)
        cat_pass[cat] += passes; cat_total[cat] += len(runs)
        results.append({"category": cat, "question": q, "accept": accept, "runs": runs, "pass": passes})
        decs = "/".join(x["decision"] for x in runs)
        print(f"[C{cat}] {passes}/{len(runs)}  ({decs:<28})  {q[:60]}")

    # scorecard
    print("\n=== SCORECARD (by category) ===")
    total_p = total_t = 0
    for cat in sorted(CAT_NAME):
        p, t = cat_pass[cat], cat_total[cat]
        total_p += p; total_t += t
        bar = "PASS" if p == t else ("part" if p else "FAIL")
        print(f"  C{cat} {bar:>4}  {p:>2}/{t:<2}  {CAT_NAME[cat]}")
    print(f"\n  OVERALL: {total_p}/{total_t}")

    # money-test + watch detail
    for cat, label in ((2, "CATEGORY 2 — hallucinated citation bait (MONEY TEST)"),
                       (8, "CATEGORY 8 — false premise (WATCH)")):
        print(f"\n=== {label} ===")
        for row in results:
            if row["category"] != cat: continue
            print(f"\n Q: {row['question']}")
            for i, x in enumerate(row["runs"], 1):
                print(f"   run {i}: {x['decision']} (cites {x['citations']}) — {x['response'][:180]}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"tenant": tenant, "runs": args.runs, "results": results,
                   "scorecard": {str(c): [cat_pass[c], cat_total[c]] for c in CAT_NAME}}, f, indent=2)
    print(f"\nFull audit trail saved to {args.out}")


if __name__ == "__main__":
    main()
