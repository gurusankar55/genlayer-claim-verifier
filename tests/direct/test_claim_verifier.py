from pathlib import Path
from gltest.direct import VMContext, deploy_contract

def test_verify_claim():
    vm = VMContext()
    vm.mock_llm(".*", "The claim is true. The Earth is round.")
    with vm.activate():
        contract = deploy_contract(Path("contracts/claim_verifier.py"), vm)
        result = contract.verify_claim("The Earth is round.")
        print("RESULT:", result)
        assert result is not None
