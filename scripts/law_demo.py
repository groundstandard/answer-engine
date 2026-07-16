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

# --- Sources to index: accurate, public-domain primary law, split into
# clause-level passages so each topic has enough distinct evidence (the legal
# profile requires >= 3 supporting evidence items per answer). Indexed at
# trust_tier 5 (in this system HIGHER tier = MORE trusted; tier/5 must clear
# the 0.4 trust filter, so tiers 1-2 get filtered out). ------------------------
TRUST_TIER = 5

SOURCES = [
    # First Amendment — protected freedoms
    ("U.S. Constitution, Amendment I", "The First Amendment provides that Congress shall make no law respecting an establishment of religion."),
    ("U.S. Constitution, Amendment I", "The First Amendment protects the free exercise of religion."),
    ("U.S. Constitution, Amendment I", "The First Amendment protects the freedom of speech."),
    ("U.S. Constitution, Amendment I", "The First Amendment protects the freedom of the press."),
    ("U.S. Constitution, Amendment I", "The First Amendment protects the right of the people peaceably to assemble, and to petition the Government for a redress of grievances."),
    # Fourth Amendment — searches and warrants
    ("U.S. Constitution, Amendment IV", "The Fourth Amendment protects the right of the people to be secure in their persons, houses, papers, and effects against unreasonable searches and seizures."),
    ("U.S. Constitution, Amendment IV", "Under the Fourth Amendment, no warrants shall issue except upon probable cause."),
    ("U.S. Constitution, Amendment IV", "The Fourth Amendment requires that probable cause for a warrant be supported by oath or affirmation."),
    ("U.S. Constitution, Amendment IV", "The Fourth Amendment requires that a warrant particularly describe the place to be searched and the persons or things to be seized."),
    # Fifth Amendment — self-incrimination, double jeopardy, due process, takings
    ("U.S. Constitution, Amendment V", "The Fifth Amendment provides that no person shall be compelled in any criminal case to be a witness against himself."),
    ("U.S. Constitution, Amendment V", "Under the Fifth Amendment, no person shall be subject for the same offence to be twice put in jeopardy of life or limb."),
    ("U.S. Constitution, Amendment V", "The Fifth Amendment provides that no person shall be deprived of life, liberty, or property, without due process of law."),
    ("U.S. Constitution, Amendment V", "The Fifth Amendment provides that private property shall not be taken for public use, without just compensation."),
    # Sixth Amendment — criminal trial rights
    ("U.S. Constitution, Amendment VI", "The Sixth Amendment guarantees that in all criminal prosecutions the accused shall enjoy the right to the Assistance of Counsel for his defence."),
    ("U.S. Constitution, Amendment VI", "The Sixth Amendment guarantees the accused the right to a speedy and public trial."),
    ("U.S. Constitution, Amendment VI", "The Sixth Amendment guarantees the accused the right to an impartial jury of the State and district wherein the crime was committed."),
    ("U.S. Constitution, Amendment VI", "The Sixth Amendment guarantees the accused the right to be informed of the nature and cause of the accusation and to be confronted with the witnesses against him."),
    # Fourteenth Amendment, Section 1 — state due process and equal protection
    ("U.S. Constitution, Amendment XIV, Sec. 1", "The Fourteenth Amendment provides that no State shall deprive any person of life, liberty, or property, without due process of law."),
    ("U.S. Constitution, Amendment XIV, Sec. 1", "The Fourteenth Amendment provides that no State shall deny to any person within its jurisdiction the equal protection of the laws."),
    ("U.S. Constitution, Amendment XIV, Sec. 1", "The Fourteenth Amendment provides that all persons born or naturalized in the United States are citizens of the United States and of the State wherein they reside."),
    ("U.S. Constitution, Amendment XIV, Sec. 1", "The Fourteenth Amendment provides that no State shall make or enforce any law which shall abridge the privileges or immunities of citizens of the United States."),
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

    # 2. Index sources (each passage becomes its own trusted source)
    print(f"=== Indexing {len(SOURCES)} legal passages (trust_tier {TRUST_TIER}) ===")
    ok = 0
    for i, (title, textval) in enumerate(SOURCES):
        st, r = post(base, "/v1/sources", {
            "tenant_id": tenant, "source_name": f"{title} [{i}]",
            "source_type": "document", "trust_tier": TRUST_TIER,
            "description": "Accurate public-domain primary law",
        }, api_key=key)
        if st not in (200, 201) or "source_id" not in r:
            print(f"  ! source failed [{i}]: {st} {r}"); continue
        st, r = post(base, "/v1/documents/index", {
            "source_id": r["source_id"], "tenant_id": tenant,
            "content_type": "text/plain", "title": title, "content": textval,
        }, api_key=key)
        if r.get("indexing_status") == "indexed":
            ok += 1
    print(f"  indexed {ok}/{len(SOURCES)} passages\n")

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
