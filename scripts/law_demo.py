#!/usr/bin/env python3
"""
Law-domain demo for the Answer Engine (Bobby's request: test how it answers
attorney-style questions, and prove it stays accurate — cites real sources or
refuses instead of guessing).

Run this AFTER embeddings are live (n8n OpenAI connection working). It:
  1. Signs up a fresh demo tenant (or reuses one via --tenant/--key).
  2. Indexes authoritative, public-domain primary law (U.S. Constitution).
  3. Asks attorney-style questions that SHOULD be answerable from those sources.
  4. Asks control questions that are NOT covered — these SHOULD be refused,
     which is the whole point for legal/medical use: no made-up answers.

Uses only the Python standard library. No secrets in this file.

    python scripts/law_demo.py
    python scripts/law_demo.py --base https://web-production-c8c1.up.railway.app
    python scripts/law_demo.py --tenant <uuid> --key <ae_...>   # reuse a tenant
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

DEFAULT_BASE = "https://web-production-c8c1.up.railway.app"

# --- Sources to index: verbatim, public-domain primary law (trust tier 1) -----
SOURCES = [
    {
        "name": "U.S. Constitution — First Amendment",
        "title": "U.S. Constitution, Amendment I",
        "text": (
            "First Amendment. Congress shall make no law respecting an establishment of "
            "religion, or prohibiting the free exercise thereof; or abridging the freedom of "
            "speech, or of the press; or the right of the people peaceably to assemble, and to "
            "petition the Government for a redress of grievances."
        ),
    },
    {
        "name": "U.S. Constitution — Fourth Amendment",
        "title": "U.S. Constitution, Amendment IV",
        "text": (
            "Fourth Amendment. The right of the people to be secure in their persons, houses, "
            "papers, and effects, against unreasonable searches and seizures, shall not be "
            "violated, and no Warrants shall issue, but upon probable cause, supported by Oath "
            "or affirmation, and particularly describing the place to be searched, and the "
            "persons or things to be seized."
        ),
    },
    {
        "name": "U.S. Constitution — Fifth Amendment",
        "title": "U.S. Constitution, Amendment V",
        "text": (
            "Fifth Amendment. No person shall be held to answer for a capital, or otherwise "
            "infamous crime, unless on a presentment or indictment of a Grand Jury, except in "
            "cases arising in the land or naval forces, or in the Militia, when in actual "
            "service in time of War or public danger; nor shall any person be subject for the "
            "same offence to be twice put in jeopardy of life or limb; nor shall be compelled "
            "in any criminal case to be a witness against himself, nor be deprived of life, "
            "liberty, or property, without due process of law; nor shall private property be "
            "taken for public use, without just compensation."
        ),
    },
    {
        "name": "U.S. Constitution — Sixth Amendment",
        "title": "U.S. Constitution, Amendment VI",
        "text": (
            "Sixth Amendment. In all criminal prosecutions, the accused shall enjoy the right "
            "to a speedy and public trial, by an impartial jury of the State and district "
            "wherein the crime shall have been committed, which district shall have been "
            "previously ascertained by law, and to be informed of the nature and cause of the "
            "accusation; to be confronted with the witnesses against him; to have compulsory "
            "process for obtaining witnesses in his favor, and to have the Assistance of "
            "Counsel for his defence."
        ),
    },
    {
        "name": "U.S. Constitution — Fourteenth Amendment, Section 1",
        "title": "U.S. Constitution, Amendment XIV, Section 1",
        "text": (
            "Fourteenth Amendment, Section 1. All persons born or naturalized in the United "
            "States, and subject to the jurisdiction thereof, are citizens of the United States "
            "and of the State wherein they reside. No State shall make or enforce any law which "
            "shall abridge the privileges or immunities of citizens of the United States; nor "
            "shall any State deprive any person of life, liberty, or property, without due "
            "process of law; nor deny to any person within its jurisdiction the equal "
            "protection of the laws."
        ),
    },
]

# --- Questions -----------------------------------------------------------------
# expect="answer"  -> should return a cited answer from the indexed sources
# expect="refuse"  -> NOT covered by the sources; should refuse (no guessing)
QUESTIONS = [
    {"q": "What must the government establish before a search warrant can be issued?", "expect": "answer"},
    {"q": "Can a defendant be compelled to testify against themselves in a criminal case?", "expect": "answer"},
    {"q": "Does the Constitution guarantee the assistance of counsel in criminal prosecutions?", "expect": "answer"},
    {"q": "Can the government take private property for public use, and what is required if it does?", "expect": "answer"},
    {"q": "What freedoms does the First Amendment protect?", "expect": "answer"},
    {"q": "Are states required to provide due process and equal protection of the laws?", "expect": "answer"},
    {"q": "Is a person protected from being tried twice for the same offense?", "expect": "answer"},
    # --- Control: not in the indexed sources -> must refuse, not invent ---
    {"q": "What is the statute of limitations for a breach of contract claim in California?", "expect": "refuse"},
    {"q": "What is the current U.S. federal minimum wage?", "expect": "refuse"},
    {"q": "How many days does a defendant have to file an answer under the Federal Rules of Civil Procedure?", "expect": "refuse"},
]


def post(base, path, payload, api_key=None, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(base + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return e.code, {"_error": body}
    except Exception as e:  # noqa: BLE001
        return 0, {"_error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--tenant", help="reuse an existing tenant id")
    ap.add_argument("--key", help="reuse an existing api key (ae_...)")
    ap.add_argument("--email", default="angelo+lawdemo@groundstandard.com")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    tenant, key = args.tenant, args.key

    # 1. Tenant
    if not (tenant and key):
        st, r = post(base, "/v1/signup", {"email": args.email, "app_name": "Law Demo"})
        if st != 201:
            print("Signup failed:", st, r); sys.exit(1)
        tenant, key = r["tenant_id"], r["api_key"]
        print(f"New demo tenant: {tenant}")
    print(f"Base: {base}\n")

    # 2. Index sources
    print("=== Indexing authoritative legal sources ===")
    for s in SOURCES:
        st, r = post(base, "/v1/sources", {
            "tenant_id": tenant, "source_name": s["name"],
            "source_type": "document", "trust_tier": 1,
            "description": "Verbatim public-domain primary law",
        }, api_key=key)
        if st not in (200, 201) or "source_id" not in r:
            print(f"  ! source failed for {s['name']}: {st} {r}"); continue
        sid = r["source_id"]
        st, r = post(base, "/v1/documents/index", {
            "source_id": sid, "tenant_id": tenant,
            "content_type": "text/plain", "title": s["title"], "content": s["text"],
        }, api_key=key)
        status = r.get("indexing_status", r.get("_error", "?"))
        print(f"  - {s['name']}: {status} ({r.get('estimated_chunks', '?')} chunks)")
    print()

    # 3. Questions
    print("=== Attorney-style questions ===")
    passed = 0
    for i, item in enumerate(QUESTIONS, 1):
        st, r = post(base, "/v1/query", {
            "query": item["q"], "tenant_id": tenant, "domain_hint": "law",
        }, api_key=key)
        decision = (r.get("final_decision") or "").upper()
        answered = decision not in ("REFUSED", "") and not r.get("refusal_reason")
        cites = r.get("citations", []) or []
        expect = item["expect"]
        ok = (answered and cites and expect == "answer") or (not answered and expect == "refuse")
        passed += 1 if ok else 0
        print(f"\n[{i}] ({expect.upper():6}) {item['q']}")
        print(f"     decision : {decision or '(none)'}   citations: {len(cites)}   -> {'OK' if ok else 'CHECK'}")
        if r.get("refusal_reason"):
            print(f"     refusal  : {r['refusal_reason']}")
        resp = (r.get("response_text") or "").strip().replace("\n", " ")
        if resp:
            print(f"     answer   : {resp[:280]}")
        for c in cites[:3]:
            print(f"       cite  : {c.get('source_name')} (tier {c.get('trust_tier')})")

    print(f"\n=== {passed}/{len(QUESTIONS)} behaved as expected "
          f"(cited answers where evidence exists, refusals where it doesn't) ===")


if __name__ == "__main__":
    main()
