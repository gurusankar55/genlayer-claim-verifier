# v0.2.17
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json
import re
import typing


class ClaimVerifier(gl.Contract):

    # Contract-enforced trusted source registry.
    # Each exact host maps to a publisher identity.
    TRUSTED_SOURCES = {
        "science.nasa.gov": "NASA",
        "www.nasa.gov": "NASA",
        "earthobservatory.nasa.gov": "NASA",
        "usgs.gov": "USGS",
        "www.usgs.gov": "USGS",
        "noaa.gov": "NOAA",
        "www.noaa.gov": "NOAA",
        "who.int": "WHO",
        "www.who.int": "WHO",
        "britannica.com": "BRITANNICA",
        "www.britannica.com": "BRITANNICA",
        "reuters.com": "REUTERS",
        "www.reuters.com": "REUTERS",
        "apnews.com": "AP",
        "www.apnews.com": "AP",
    }

    claim: str
    result: str
    explanation: str
    evidence_url: str
    verification_count: u256

    # Immutable versioned records.
    # Key format: <claim>::v<version>
    claim_versions: TreeMap[str, str]

    # Latest version number for each claim.
    claim_latest_version: TreeMap[str, u256]

    # Evidence stored separately for every version.
    claim_evidence_versions: TreeMap[str, str]

    def __init__(self):
        self.claim = ""
        self.result = "PENDING"
        self.explanation = ""
        self.evidence_url = ""
        self.verification_count = u256(0)


    def _normalize_url(self, url: str) -> str:
        url = url.strip()

        if not url:
            raise gl.vm.UserError("Source URL cannot be empty")

        if not re.match(
            r"^https?://",
            url,
            re.IGNORECASE
        ):
            raise gl.vm.UserError(
                "Source URL must use http:// or https://"
            )

        if re.match(
            r"^https?://[^/]*@",
            url,
            re.IGNORECASE
        ):
            raise gl.vm.UserError(
                "Source URL credentials are not allowed"
            )

        return url

    def _source_host(self, url: str) -> str:
        match = re.match(
            r"^https?://([^/:?#]+)",
            url,
            re.IGNORECASE
        )

        if not match:
            raise gl.vm.UserError(
                "Unable to determine source host"
            )

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
    ) -> typing.Dict[str, str]:

        claim = claim.strip()

        if not claim:
            raise gl.vm.UserError(
                "Claim cannot be empty"
            )

        # ---------------------------------------------------------
        # 1. Normalize source URLs
        # ---------------------------------------------------------

        urls = [
            self._normalize_url(source_url_1),
            self._normalize_url(source_url_2),
            self._normalize_url(source_url_3),
        ]

        if len(set(urls)) != 3:
            raise gl.vm.UserError(
                "Three distinct source URLs are required"
            )

        # ---------------------------------------------------------
        # 2. Enforce trusted and independent source publishers
        # ---------------------------------------------------------

        hosts = [
            self._source_host(url)
            for url in urls
        ]

        publisher_ids = [
            self.TRUSTED_SOURCES.get(host, "")
            for host in hosts
        ]

        if "" in publisher_ids:
            raise gl.vm.UserError(
                "All source hosts must belong to the trusted source registry"
            )

        if len(set(publisher_ids)) != 3:
            raise gl.vm.UserError(
                "Three independent trusted source publishers are required"
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

            # Remove scripts and styles
            text = re.sub(
                r"<script\b[^>]*>.*?</script>",
                " ",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )

            text = re.sub(
                r"<style\b[^>]*>.*?</style>",
                " ",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )

            # Remove HTML tags
            text = re.sub(r"<[^>]+>", " ", text)

            # Decode common HTML entities
            text = text.replace("&nbsp;", " ")
            text = text.replace("&amp;", "&")
            text = text.replace("&quot;", '"')
            text = text.replace("&#39;", "'")

            # Normalize whitespace
            text = re.sub(r"\s+", " ", text)

            return text.strip()

        # ---------------------------------------------------------
        # 3. Retrieve evidence inside nondeterministic block
        # ---------------------------------------------------------

        def fetch_sources() -> str:
            sources = []

            for item in provenance:
                url = item["url"]
                host = item["host"]
                publisher = item["publisher"]

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
                            "publisher": publisher,
                            "status": "FAILED",
                            "evidence": "",
                        })

                    elif not normalized:
                        sources.append({
                            "url": url,
                            "host": host,
                            "publisher": publisher,
                            "status": "EMPTY",
                            "evidence": "",
                        })

                    elif any(
                        marker in normalized.lower()
                        for marker in [
                            "just a moment",
                            "enable javascript",
                            "enable cookies",
                            "access denied",
                            "captcha",
                            "robot verification",
                            "verify you are human",
                            "checking your browser",
                        ]
                    ):
                        sources.append({
                            "url": url,
                            "host": host,
                            "publisher": publisher,
                            "status": "UNUSABLE",
                            "evidence": "",
                        })

                    else:
                        sources.append({
                            "url": url,
                            "host": host,
                            "publisher": publisher,
                            "status": "OK",
                            "evidence": normalized[:12000],
                        })

                except Exception:
                    sources.append({
                        "url": url,
                        "host": host,
                        "publisher": publisher,
                        "status": "FAILED",
                        "evidence": "",
                    })

            return json.dumps(
                sources,
                sort_keys=True,
                separators=(",", ":")
            )

        evidence_json = gl.eq_principle.prompt_comparative(
            fetch_sources,
            principle="""
The source records must represent the same requested URLs.

Each record must preserve exactly the same:
- source URL
- source host
- trusted publisher identity
- HTTP status

The trusted publisher identity is contract-assigned and must
not be changed, inferred, substituted, or invented by validators.

Small differences in HTML formatting, scripts, metadata,
whitespace, or dynamic webpage content are acceptable.

The underlying factual evidence relevant to the claim must
remain consistent across validators.

Do not invent evidence, URLs, hosts, publishers, or statuses.
"""
        )

        sources = json.loads(evidence_json)

        # Re-enforce contract-assigned publisher provenance
        # after consensus. Validators must not alter source identity.
        if len(sources) != 3:
            raise gl.vm.UserError(
                "Exactly three source records are required"
            )

        for index, source in enumerate(sources):
            if source.get("url") != urls[index]:
                raise gl.vm.UserError(
                    "Consensus changed a source URL"
                )

            if source.get("host") != hosts[index]:
                raise gl.vm.UserError(
                    "Consensus changed a source host"
                )

            if source.get("publisher") != publisher_ids[index]:
                raise gl.vm.UserError(
                    "Consensus changed a trusted publisher identity"
                )

        if len(
            set(
                source.get("publisher", "")
                for source in sources
            )
        ) != 3:
            raise gl.vm.UserError(
                "Consensus must preserve three independent trusted publishers"
            )

        usable_sources = [
            source
            for source in sources
            if source["status"] == "OK"
            and source["evidence"]
        ]

        if len(usable_sources) < 2:
            raise gl.vm.UserError(
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
        # 5. Parse consensus result
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
                        raise gl.vm.UserError(
                            "Invalid verification response"
                        )
                else:
                    raise gl.vm.UserError(
                        "Invalid verification response"
                    )

        if not isinstance(parsed, dict):
            raise gl.vm.UserError(
                "Invalid verification response"
            )

        verification_result = parsed.get("result")

        if verification_result not in [
            "VERIFIED",
            "NOT_VERIFIED",
            "UNCERTAIN"
        ]:
            raise gl.vm.UserError(
                "Invalid verification result"
            )

        explanation = parsed.get("explanation")
        evidence_url = parsed.get("evidence_url")

        if not explanation:
            raise gl.vm.UserError(
                "Missing explanation"
            )

        if not evidence_url:
            raise gl.vm.UserError(
                "Missing evidence URL"
            )

        # ---------------------------------------------------------
        # 6. Validate evidence URLs returned by the model
        # ---------------------------------------------------------

        evidence_urls = [
            item.strip()
            for item in evidence_url.split(",")
            if item.strip()
        ]

        retrieved_urls = [
            source["url"]
            for source in usable_sources
        ]

        for used_url in evidence_urls:
            if used_url not in retrieved_urls:
                raise gl.vm.UserError(
                    "Evidence URL was not retrieved by the contract"
                )

        # ---------------------------------------------------------
        # 7. Create immutable versioned claim record
        # ---------------------------------------------------------

        previous_version = self.claim_latest_version.get(
            claim,
            u256(0)
        )

        next_version = previous_version + u256(1)

        version_key = (
            claim
            + "::v"
            + str(next_version)
        )

        stored_result = json.dumps({
            "claim": claim,
            "version": str(next_version),
            "result": verification_result,
            "explanation": explanation,
            "evidence_url": evidence_url,
            "verification_count": str(
                self.verification_count + u256(1)
            ),
        })

        # IMPORTANT:
        # Every verification gets a new key.
        # Previous versions are never overwritten.

        self.claim_versions[version_key] = stored_result

        self.claim_evidence_versions[version_key] = (
            evidence_json
        )

        self.claim_latest_version[claim] = next_version

        # ---------------------------------------------------------
        # 8. Update latest public state
        # ---------------------------------------------------------

        self.claim = claim
        self.result = verification_result
        self.explanation = explanation
        self.evidence_url = evidence_url

        self.verification_count = (
            self.verification_count + u256(1)
        )

        return {
            "claim": self.claim,
            "result": self.result,
            "explanation": self.explanation,
            "evidence_url": self.evidence_url,
            "verification_count": str(
                self.verification_count
            ),
            "version": str(next_version),
        }

    @gl.public.view
    def get_result(self) -> typing.Dict[str, str]:
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
    def get_claim_result(
        self,
        claim: str
    ) -> str:

        latest_version = self.claim_latest_version.get(
            claim,
            u256(0)
        )

        if latest_version == u256(0):
            return ""

        version_key = (
            claim
            + "::v"
            + str(latest_version)
        )

        return self.claim_versions.get(
            version_key,
            ""
        )

    @gl.public.view
    def get_claim_version(
        self,
        claim: str,
        version: u256
    ) -> str:

        if version == u256(0):
            return ""

        version_key = (
            claim
            + "::v"
            + str(version)
        )

        return self.claim_versions.get(
            version_key,
            ""
        )

    @gl.public.view
    def get_claim_evidence(
        self,
        claim: str
    ) -> str:

        latest_version = self.claim_latest_version.get(
            claim,
            u256(0)
        )

        if latest_version == u256(0):
            return ""

        version_key = (
            claim
            + "::v"
            + str(latest_version)
        )

        return self.claim_evidence_versions.get(
            version_key,
            ""
        )

    @gl.public.view
    def get_claim_version_evidence(
        self,
        claim: str,
        version: u256
    ) -> str:

        if version == u256(0):
            return ""

        version_key = (
            claim
            + "::v"
            + str(version)
        )

        return self.claim_evidence_versions.get(
            version_key,
            ""
        )

    @gl.public.view
    def get_latest_version(
        self,
        claim: str
    ) -> str:

        return str(
            self.claim_latest_version.get(
                claim,
                u256(0)
            )
        )