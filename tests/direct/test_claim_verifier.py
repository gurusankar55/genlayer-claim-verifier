import json
from pathlib import Path

from gltest.direct import VMContext, deploy_contract


def test_verify_claim():
    vm = VMContext()

    vm.mock_web(
        r"https://example\.com/earth",
        {
            "status": 200,
            "body": (
                "The Earth is round. "
                "This source confirms that the Earth is approximately spherical."
            ),
        },
    )

    vm.mock_web(
        r"https://example\.org/science",
        {
            "status": 200,
            "body": (
                "Scientific observations describe Earth as approximately spherical."
            ),
        },
    )

    vm.mock_web(
        r"https://example\.net/facts",
        {
            "status": 200,
            "body": (
                "Earth has a roughly spherical shape."
            ),
        },
    )

    vm.mock_llm(
        r"The Earth is round",
        json.dumps(
            {
                "result": "VERIFIED",
                "explanation": (
                    "The three supplied sources consistently "
                    "support the claim."
                ),
                "evidence_url": (
                    "https://example.com/earth,"
                    "https://example.org/science,"
                    "https://example.net/facts"
                ),
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
            "https://example.com/earth",
            "https://example.org/science",
            "https://example.net/facts",
        )

        print("RESULT:", result)

        assert result is not None
        assert result["claim"] == "The Earth is round."
        assert result["result"] == "VERIFIED"
        assert result["verification_count"] == "1"

        stored = contract.get_claim_result(
            "The Earth is round."
        )

        assert stored != ""
