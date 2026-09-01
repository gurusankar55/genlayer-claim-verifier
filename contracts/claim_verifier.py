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

    # Versioned verification records.
    # IMPORTANT: records are never overwritten.
    claim_versions: TreeMap[str, str]

    # Latest version pointer for each claim.
    claim_latest_version: TreeMap[str, u256]

    # Versioned source evidence.
    claim_evidence_versions: TreeMap[str, str]

    def __init__(self):
        self.claim = ""
        self.result = "PENDING"
        self.explanation = ""
        self.evidence_url = ""
        self.verification_count = u256(0)

        self.claim_versions = TreeMap()
        self.claim_latest_version = TreeMap()
        self.claim_evidence_versions = TreeMap()

    def _normalize_url(self, url: str) -> str:
        url = url.strip()

        if not url:
            raise Exception("Source URL cannot be empty")

        if not re.match(r"^https?://", url, re.IGNORECASE):
            raise Exception(
                "Source URL must use http:// or https://"
            )

        # Reject URLs containing credentials.
        if re.match(
            r"^https?://[^/]*@",
            url,
            re.IGNORECASE
        ):
            raise Exception(
                "Source URL credentials are not allowed"
            )

        # Remove trailing whitespace/slashes only.
        url = url.rstrip()

        return url

    def _source_host(self, url: str) -> str:
        match = re.match(
            r"^https?://([^/:?#]+)",
            url,
            re.IGNORECASE
        )

        if not match:
            raise Exception("Unable to determine source host")

        host = match.group(1).lower()

        if host.startswith("www."):
            host = host[4:]

        return host

    @gl.public.write
    def verify_claim(
        self,
        claim: str,
        source_url_1: str,
        source_url_2: str,
        source_url_3: str
    ) -> typing.Any:

        claim = claim.strip()

        if not claim:
            raise Exception("Claim cannot be empty")

        # ---------------------------------------------------------
        # 1. Normalize and validate supplied source URLs
        # ---------------------------------------------------------

        urls = [
            self._normalize_url(source_url_1),
            self._normalize_url(source_url_2),
            self._normalize_url(source_url_3),
        ]

        # Exact URL duplicates are forbidden.
        if len(set(urls)) != 3:
            raise Exception(
                "Three distinct source URLs are required"
            )

        # ---------------------------------------------------------
        # 2. Enforce source provenance / independence
        # ---------------------------------------------------------

        hosts = [
            self._source_host(url)
            for url in urls
        ]

        # Same hostname cannot be counted as independent.
        if len(set(hosts)) != 3:
            raise Exception(
                "Three independent source domains are required"
            )

        provenance = [
            {
                "url": urls[0],
                "host": hosts[0],
            },
            {
                "url": urls[1],
                "host": hosts[1],
            },
            {
                "url": urls[2],
                "host": hosts[2],
            },
        ]

        def normalize_evidence(text: str) -> str:
            text = text.replace("\x00", " ")
            text = re.sub(r"\s+", " ", text)
            return text.strip()

        # ---------------------------------------------------------
        # 3. Fetch evidence inside nondeterministic block
        # ---------------------------------------------------------

        def fetch_sources() -> str:
            sources = []

            for item in provenance:
                url = item["url"]
                host = item["host"]

                try:
                    response = gl.nondet.web.get(url)

                    status = getattr(
                        response,
                        "status_code",
                        200
                    )

                    body = response.body.decode(
                        "utf-8",
                        errors="replace"
                    )

                    normalized = normalize_evidence(body)

                    if status >= 400:
                        sources.append({
                            "url": url,
                            "host": host,
                            "status": "FAILED",
                            "evidence": "",
                        })

                    elif not normalized:
                        sources.append({
                            "url": url,
                            "host": host,
                            "status": "EMPTY",
                            "evidence": "",
                        })

                    else:
                        sources.append({
                            "url": url,
                            "host": host,
                            "status": "OK",
                            "evidence": normalized[:12000],
                        })

                except Exception:
                    sources.append({
                        "url": url,
                        "host": host,
                        "status": "FAILED",
                        "evidence": "",
                    })

            return json.dumps(
                sources,
                sort_keys=True,
                separators=(",", ":")
            )

        evidence_json = gl.eq_principle.strict_eq(
            fetch_sources
        )

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

        # ---------------------------------------------------------
        # 4. Source-grounded claim evaluation
        # ---------------------------------------------------------

        def evaluate_claim() -> str:
            prompt = f"""
You are a claim verification expert.

CLAIM:
{claim}

RETRIEVED SOURCE EVIDENCE:
{evidence_for_prompt}

Verify the claim using ONLY the retrieved source evidence.

STRICT RULES:

1. Do not use model memory.
2. Do not invent facts.
3. Do not use information outside the supplied evidence.
4. Treat each retrieved source independently.
5. Only sources with status OK may be used.
6. If evidence conflicts, return UNCERTAIN.
7. If evidence is insufficient, return UNCERTAIN.
8. The explanation must be based only on supplied evidence.
9. evidence_url MUST contain only URLs from the retrieved
   source evidence.
10. Do not create or modify source URLs.

Return valid JSON only:

{{
  "result": "VERIFIED",
  "explanation": "short evidence-based explanation",
  "evidence_url": "URL or comma-separated URLs actually used"
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

The result must be exactly one of:
VERIFIED, NOT_VERIFIED, UNCERTAIN.

The explanation must be consistent with the retrieved
source evidence.

The evidence_url must contain only URLs that exist in
the retrieved source evidence.

Do not accept unsupported facts.

If evidence is insufficient or conflicting,
UNCERTAIN is the safe result.
"""
        )

        # ---------------------------------------------------------
        # 5. Parse and validate consensus result
        # ---------------------------------------------------------

        parsed = result

        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)

            except Exception:
                match = re.search(
                    r"\{.*\}",
                    parsed,
                    re.DOTALL
                )

                if match:
                    try:
                        parsed = json.loads(
                            match.group(0)
                        )
                    except Exception:
                        raise Exception(
                            "Invalid verification response"
                        )
                else:
                    raise Exception(
                        "Invalid verification response"
                    )

        if not isinstance(parsed, dict):
            raise Exception(
                "Invalid verification response"
            )

        verification_result = parsed.get("result")

        if verification_result not in [
            "VERIFIED",
            "NOT_VERIFIED",
            "UNCERTAIN"
        ]:
            raise Exception(
                "Invalid verification result"
            )

        explanation = parsed.get("explanation")
        evidence_url = parsed.get("evidence_url")

        if not explanation:
            raise Exception(
                "Missing explanation"
            )

        if not evidence_url:
            raise Exception(
                "Missing evidence URL"
            )

        # ---------------------------------------------------------
        # 6. Enforce evidence_url provenance
        # ---------------------------------------------------------

        reported_urls = [
            item.strip()
            for item in evidence_url.split(",")
            if item.strip()
        ]

        if not reported_urls:
            raise Exception(
                "No valid evidence URLs supplied"
            )

        supplied_url_set = set(urls)

        for reported_url in reported_urls:
            normalized_reported = self._normalize_url(
                reported_url
            )

            if normalized_reported not in supplied_url_set:
                raise Exception(
                    "Evidence URL is not one of the supplied sources"
                )

        canonical_evidence_url = ",".join(
            sorted(set(reported_urls))
        )

        # ---------------------------------------------------------
        # 7. Create immutable version
        # ---------------------------------------------------------

        next_version = (
            self.verification_count + u256(1)
        )

        version_key = (
            claim
            + "::version::"
            + str(next_version)
        )

        # The version key is generated by the contract.
        # The caller cannot choose it.
        if self.claim_versions.get(
            version_key,
            ""
        ):
            raise Exception(
                "Verification version already exists"
            )

        # ---------------------------------------------------------
        # 8. Build immutable verification record
        # ---------------------------------------------------------

        stored_result = json.dumps({
            "claim": claim,
            "version": str(next_version),
            "result": verification_result,
            "explanation": explanation,
            "evidence_url": canonical_evidence_url,
            "source_provenance": provenance,
        }, sort_keys=True)

        stored_evidence = json.dumps({
            "claim": claim,
            "version": str(next_version),
            "sources": sources,
        }, sort_keys=True)

        # ---------------------------------------------------------
        # 9. Write versioned records.
        #    NEVER overwrite previous verification records.
        # ---------------------------------------------------------

        self.claim_versions[version_key] = stored_result

        self.claim_evidence_versions[
            version_key
        ] = stored_evidence

        self.claim_latest_version[
            claim
        ] = next_version

        # Global immutable verification counter.
        self.verification_count = next_version

        # Current/latest convenience state.
        self.claim = claim
        self.result = verification_result
        self.explanation = explanation
        self.evidence_url = canonical_evidence_url

        return {
            "claim": claim,
            "version": str(next_version),
            "result": verification_result,
            "explanation": explanation,
            "evidence_url": canonical_evidence_url,
            "verification_count": str(
                self.verification_count
            ),
        }

    @gl.public.view
    def get_result(self) -> dict[str, str]:
        return {
            "claim": self.claim,
            "result": self.result,
            "explanation": self.explanation,
            "evidence_url": self.evidence_url,
            "verification_count": str(
                self.verification_count
            ),
        }

    @gl.public.view
    def get_claim_version(
        self,
        claim: str,
        version: u256
    ) -> str:

        version_key = (
            claim
            + "::version::"
            + str(version)
        )

        return self.claim_versions.get(
            version_key,
            ""
        )

    @gl.public.view
    def get_claim_evidence_version(
        self,
        claim: str,
        version: u256
    ) -> str:

        version_key = (
            claim
            + "::version::"
            + str(version)
        )

        return self.claim_evidence_versions.get(
            version_key,
            ""
        )

    @gl.public.view
    def get_latest_claim_version(
        self,
        claim: str
    ) -> str:

        version = self.claim_latest_version.get(
            claim,
            u256(0)
        )

        if version == u256(0):
            return ""

        version_key = (
            claim
            + "::version::"
            + str(version)
        )

        return self.claim_versions.get(
            version_key,
            ""
        )