# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json
import typing


class ClaimVerifier(gl.Contract):
    claim: str
    result: str
    explanation: str
    evidence_url: str
    verification_count: u256

    def __init__(self):
        self.claim = ""
        self.result = "PENDING"
        self.explanation = ""
        self.evidence_url = ""
        self.verification_count = u256(0)

    @gl.public.write
    def verify_claim(
        self,
        claim: str,
        source_url: str
    ) -> typing.Any:

        if not claim.strip():
            raise Exception("Claim cannot be empty")

        if not source_url.strip():
            raise Exception("Source URL cannot be empty")

        def evaluate_claim() -> str:
            response = gl.nondet.web.get(source_url)
            evidence = response.body.decode("utf-8")

            prompt = f"""
You are a claim verification expert.

CLAIM:
{claim}

SOURCE URL:
{source_url}

RETRIEVED SOURCE EVIDENCE:
{evidence}

Verify the claim using ONLY the retrieved source evidence.

Return valid JSON only:

{{
  "result": "VERIFIED",
  "explanation": "short evidence-based explanation",
  "evidence_url": "{source_url}"
}}

The result MUST be exactly one of:
VERIFIED
NOT_VERIFIED
UNCERTAIN

Do not invent facts.
Do not use model memory instead of the supplied evidence.
"""

            return gl.nondet.exec_prompt(prompt)

        result = gl.eq_principle.prompt_comparative(
            evaluate_claim,
            principle="""
The verification decision must agree.

The result field must be exactly the same:
VERIFIED, NOT_VERIFIED, or UNCERTAIN.

The explanation must be consistent with the retrieved
source evidence.

The evidence_url must identify the supplied source URL.

Do not accept unsupported facts.
"""
        )

        parsed = result

        if parsed["result"] not in [
            "VERIFIED",
            "NOT_VERIFIED",
            "UNCERTAIN"
        ]:
            raise Exception("Invalid verification result")

        self.claim = claim
        self.result = parsed["result"]
        self.explanation = parsed["explanation"]
        self.evidence_url = parsed["evidence_url"]
        self.verification_count = self.verification_count + u256(1)

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