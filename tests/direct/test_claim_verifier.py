import json
from pathlib import Path
from gltest.direct import VMContext, deploy_contract


def test_verify_claim():
    vm = VMContext()

    vm.mock_web(
        r"https://example\.com/earth",
        {
            "status": 200,
            "body": "The Earth is round. This source confirms that the Earth is approximately spherical.",
        },
    )

    vm.mock_llm(
        r"The Earth is round",
        json.dumps(
            {
                "result": "VERIFIED",
                "explanation": "The supplied source evidence supports the claim.",
                "evidence_url": "https://example.com/earth",
            }
        ),
    )

    with vm.activate():
        contract = deploy_contract(
            Path("contracts/claim_verifier.py"),
            vm
        )

        result = contract.verify_claim(
            "The Earth is round.",
            "https://example.com/earth"
        )

        print("RESULT:", result)

        assert result is not None
        assert result["claim"] == "The Earth is round."
        assert result["result"] == "VERIFIED"
        assert result["evidence_url"] == "https://example.com/earth"
