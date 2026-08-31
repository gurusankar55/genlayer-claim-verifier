# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json
import re
import typing


class ClaimVerifier(gl.Contract):
    claim: str
    result: str
    explanation: str
    evidence_url: str
    verification_count: u256

    # Reusable claim-specific state
    claim_results: TreeMap[str, str]
    claim_evidence: TreeMap[str, str]

    def __init__(self):
        self.claim = ""
        self.result = "PENDING"
        self.explanation = ""
        self.evidence_url = ""
        self.verification_count = u256(0)

        self.claim_results = TreeMap()
        self.claim_evidence = TreeMap()

    @gl.public.write
    def verify_claim(
        self,
        claim: str,
        source_url_1: str,
        source_url_2: str,
        source_url_3: str
    ) -> typing.Any:

        if not claim.strip():
            raise Exception("Claim cannot be empty")

        urls = [
            source_url_1.strip(),
            source_url_2.strip(),
            source_url_3.strip(),
        ]

        if len(set(urls)) != 3:
            raise Exception("Three independent source URLs are required")

        for url in urls:
            if not url:
                raise Exception("Source URL cannot be empty")

        def normalize_evidence(text: str) -> str:
            text = text.replace("\x00", " ")
            text = re.sub(r"\s+", " ", text)
            return text.strip()

        def fetch_sources() -> str:
            sources = []

            for url in urls:
                try:
                    response = gl.nondet.web.get(url)

                    status = getattr(response, "status_code", 200)
                    body = response.body.decode("utf-8")

                    normalized = normalize_evidence(body)

                    if status >= 400:
                        sources.append({
                            "url": url,
                            "status": "FAILED",
                            "evidence": "",
                        })
                    elif not normalized:
                        sources.append({
                            "url": url,
                            "status": "EMPTY",
                            "evidence": "",
                        })
                    else:
                        sources.append({
                            "url": url,
                            "status": "OK",
                            "evidence": normalized[:12000],
                        })

                except Exception as exc:
                    sources.append({
                        "url": url,
                        "status": "FAILED",
                        "evidence": "",
                    })

            return json.dumps(
                sources,
                sort_keys=True,
                separators=(",", ":")
            )

        evidence_json = gl.eq_principle.strict_eq(fetch_sources)

        sources = json.loads(evidence_json)

        usable_sources = [
            source
            for source in sources
            if source["status"] == "OK"
            and source["evidence"]
        ]

        if len(usable_sources) < 2:
            raise Exception(
                "At least two usable independent sources are required"
            )

        evidence_for_prompt = json.dumps(
            usable_sources,
            sort_keys=True,
            separators=(",", ":")
        )

        def evaluate_claim() -> str:
            prompt = f"""
You are a claim verification expert.

CLAIM:
{claim}

RETRIEVED SOURCE EVIDENCE:
{evidence_for_prompt}

Verify the claim using ONLY the retrieved source evidence.

Important rules:

1. Do not use model memory.
2. Do not invent facts.
3. Treat each source independently.
4. Use only sources whose status is OK.
5. If the sources conflict or the evidence is insufficient,
   return UNCERTAIN.
6. The explanation must refer only to supplied evidence.
7. The evidence_url must identify the source URL(s) actually
   used for the decision.

Return valid JSON only:

{{
  "result": "VERIFIED",
  "explanation": "short evidence-based explanation",
  "evidence_url": "URL or comma-separated URLs used"
}}

The result MUST be exactly one of:

VERIFIED
NOT_VERIFIED
UNCERTAIN
"""

            return gl.nondet.exec_prompt(prompt)

        result = gl.eq_principle.prompt_comparative(
            evaluate_claim,
            principle="""
The verification decision must agree.

The result field must be exactly one of:
VERIFIED, NOT_VERIFIED, UNCERTAIN.

The explanation must be consistent with the retrieved
source evidence.

The evidence_url must identify URL(s) present in the
retrieved source evidence.

Do not accept unsupported facts.

If the evidence is insufficient or conflicting,
UNCERTAIN is the safe result.
"""
        )

        parsed = result

        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except Exception:
                match = re.search(r"\{.*\}", parsed, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                    except Exception:
                        raise Exception("Invalid verification response")
                else:
                    raise Exception("Invalid verification response")

        if not isinstance(parsed, dict):
            raise Exception("Invalid verification response")

        if parsed["result"] not in [
            "VERIFIED",
            "NOT_VERIFIED",
            "UNCERTAIN"
        ]:
            raise Exception("Invalid verification result")

        if not parsed.get("explanation"):
            raise Exception("Missing explanation")

        if not parsed.get("evidence_url"):
            raise Exception("Missing evidence URL")

        self.claim = claim
        self.result = parsed["result"]
        self.explanation = parsed["explanation"]
        self.evidence_url = parsed["evidence_url"]

        self.verification_count = (
            self.verification_count + u256(1)
        )

        stored_result = json.dumps({
            "claim": self.claim,
            "result": self.result,
            "explanation": self.explanation,
            "evidence_url": self.evidence_url,
            "verification_count": str(self.verification_count),
        })

        self.claim_results[claim] = stored_result
        self.claim_evidence[claim] = evidence_json

        return {
            "claim": self.claim,
            "result": self.result,
            "explanation": self.explanation,
            "evidence_url": self.evidence_url,
            "verification_count": str(self.verification_count),
        }

    @gl.public.view
    def get_result(self) -> dict[str, str]:
        return {
            "claim": self.claim,
            "result": self.result,
            "explanation": self.explanation,
            "evidence_url": self.evidence_url,
            "verification_count": str(self.verification_count),
        }

    @gl.public.view
    def get_claim_result(self, claim: str) -> str:
        return self.claim_results.get(claim, "")

    @gl.public.view
    def get_claim_evidence(self, claim: str) -> str:
        return self.claim_evidence.get(claim, "")