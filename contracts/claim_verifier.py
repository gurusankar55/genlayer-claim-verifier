# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import typing


class ClaimVerifier(gl.Contract):
    claim: str
    result: str
    explanation: str
    verification_count: u256

    def __init__(self):
        self.claim = ""
        self.result = "PENDING"
        self.explanation = ""
        self.verification_count = u256(0)

    @gl.public.write
    def verify_claim(self, claim: str) -> typing.Any:
        if not claim.strip():
            raise Exception("Claim cannot be empty")

        def evaluate_claim() -> str:
            prompt = f"""
You are a claim verification expert.

Analyze the following claim:

<claim>
{claim}
</claim>

Determine whether the claim is:

VERIFIED
NOT_VERIFIED
UNCERTAIN

Return:
RESULT: one of VERIFIED, NOT_VERIFIED, UNCERTAIN
EXPLANATION: a concise explanation

Do not invent facts.
Use available evidence when necessary.
"""

            return gl.nondet.exec_prompt(prompt)

        result = gl.eq_principle.prompt_non_comparative(
            evaluate_claim,
            task="""
Evaluate the claim and classify it as VERIFIED,
NOT_VERIFIED, or UNCERTAIN.
Provide a concise evidence-based explanation.
""",
            criteria="""
The response must:

1. Clearly contain one classification:
   VERIFIED, NOT_VERIFIED, or UNCERTAIN.

2. Provide a meaningful explanation.

3. Base the conclusion on evidence or
   reasonable verification.

4. Do not invent unsupported facts.

5. Do not include unrelated information.
"""
        )

        self.claim = claim
        self.result = str(result)
        self.explanation = str(result)
        self.verification_count = self.verification_count + u256(1)
        return {
            "claim": self.claim,
            "result": self.result,
            "explanation": self.explanation,
            "verification_count": str(self.verification_count),
        }

    @gl.public.view
    def get_result(self) -> dict[str, str]:
        return {
            "claim": self.claim,
            "result": self.result,
            "explanation": self.explanation,
            "verification_count": str(self.verification_count),
        }