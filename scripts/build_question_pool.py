"""Build a classified CLF-C02 question pool from the practice-exam markdown files.

Reads practice-exam/practice-exam-*.md, assigns each question to one of the four
exam domains, and writes assets/data/questions.json.

Domain weights match the CLF-C02 blueprint. A 32-question sitting cannot hit
those percentages on the nose, so the exam counts use the largest-remainder
method:

  Cloud Concepts          24% -> 8
  Security & Compliance   30% -> 9
  Technology & Services   34% -> 11
  Billing & Support       12% -> 4
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAM_DIR = ROOT / "practice-exam"
OUT_PATH = ROOT / "assets" / "data" / "questions.json"

EXAM_SIZE = 32
PASS_MARK = 0.70
OFFICIAL_QUESTIONS = 65
OFFICIAL_MINUTES = 90

DOMAINS = [
    {
        "id": "cloud-concepts",
        "name": "Cloud Concepts",
        "officialName": "Cloud Concepts",
        "weight": 0.24,
    },
    {
        "id": "security-compliance",
        "name": "Security & Compliance",
        "officialName": "Security and Compliance",
        "weight": 0.30,
    },
    {
        "id": "technology-services",
        "name": "Technology & Services",
        "officialName": "Cloud Technology and Services",
        "weight": 0.34,
    },
    {
        "id": "billing-support",
        "name": "Billing & Support",
        "officialName": "Billing, Pricing, and Support",
        "weight": 0.12,
    },
]

# Rule tuples: (domain id, weight, compiled regex, label)
# Weights are scored on the stem (x3), the correct choices (x2), and the
# distractors (x0.5). A weight of 8 is a strong phrase; 4 is a solid clue; 2 is weak.
Rule = tuple[str, int, re.Pattern[str], str]


def rule(domain: str, weight: int, pattern: str, label: str) -> Rule:
    return (domain, weight, re.compile(pattern, re.IGNORECASE), label)


def wb(phrase: str) -> str:
    """Case-insensitive phrase with non-alphanumeric boundaries."""
    return rf"(?<![A-Za-z0-9]){phrase}(?![A-Za-z0-9])"


RULES: list[Rule] = [
    # --- Billing, pricing, and support (Domain 4) ---
    rule("billing-support", 8, r"consolidated billing", "consolidated billing"),
    rule("billing-support", 8, r"cost explorer", "cost explorer"),
    rule("billing-support", 8, r"aws budgets?", "aws budgets"),
    rule("billing-support", 8, r"pricing calculator", "pricing calculator"),
    rule("billing-support", 8, r"tco calculator|total cost of ownership \(tco\) calculator|simple monthly calculator", "cost calculator"),
    rule("billing-support", 8, r"cost (?:and|&) usage reports?", "cost and usage report"),
    rule("billing-support", 8, r"cost allocation tags?", "cost allocation tags"),
    rule("billing-support", 8, r"support plans?|enterprise support|business support|developer support|basic support", "support plan"),
    rule("billing-support", 8, r"technical account manager|\btams?\b|support concierge", "tam or concierge"),
    rule("billing-support", 8, r"reserved instances?|\bris\b", "reserved instance"),
    rule("billing-support", 8, r"savings plans?", "savings plan"),
    rule("billing-support", 8, r"spot instances?", "spot instance"),
    rule("billing-support", 8, r"dedicated hosts?", "dedicated host"),
    rule("billing-support", 8, r"free tier", "free tier"),
    rule("billing-support", 8, r"billing alarms?|billing alerts?", "billing alarm"),
    rule("billing-support", 8, r"\binvoices?\b", "invoice"),
    rule("billing-support", 8, r"volume discounts?", "volume discount"),
    rule("billing-support", 8, r"aws marketplace", "aws marketplace"),
    rule("billing-support", 8, r"professional services", "professional services"),
    rule("billing-support", 8, r"partner network|\bapn\b|consulting partners?|technology partners?", "partner network"),
    rule("billing-support", 8, r"trusted advisor", "trusted advisor"),
    rule("billing-support", 8, r"pricing models?", "pricing model"),
    rule("billing-support", 8, r"knowledge center|re:post|aws health dashboard|personal health dashboard|service health dashboard", "support resource"),
    rule("billing-support", 8, r"on-demand instances?|on-demand pricing", "on-demand pricing"),
    rule("billing-support", 8, r"compute optimizer|cost anomaly", "cost tool"),
    rule("billing-support", 5, r"\bbilling\b", "billing"),
    rule("billing-support", 5, r"\bpricing\b|\bpriced\b", "pricing"),
    rule("billing-support", 4, r"\bdiscounts?\b", "discount"),
    rule("billing-support", 3, r"\bcosts?\b|\bprices?\b", "cost or price"),
    rule("cloud-concepts", 6, r"pay-as-you-go|pay only for what|only for what (?:is|you) use|long-term contracts?", "pay for use"),
    rule("cloud-concepts", 8, r"value proposition|hybrid cloud|public cloud|private cloud", "cloud deployment model"),
    rule("billing-support", 5, r"whitepapers?", "whitepaper"),
    rule("billing-support", 4, r"lowest[- ]cost|least cost|cost-effective|cost effective|minimize costs|minimise costs|save money|saving money", "cost savings wording"),
    # --- Security and compliance (Domain 2) ---
    rule("security-compliance", 8, r"shared responsibility", "shared responsibility"),
    rule("security-compliance", 8, r"identity and access management|\biam\b", "iam"),
    rule("security-compliance", 8, r"multi-factor|\bmfa\b", "mfa"),
    rule("security-compliance", 8, r"least privilege", "least privilege"),
    rule("security-compliance", 8, r"key management service|\bkms\b|cloudhsm|customer master key", "kms or cloudhsm"),
    rule("security-compliance", 8, r"aws shield|shield advanced", "aws shield"),
    rule("security-compliance", 8, r"web application firewall|\bwaf\b", "waf"),
    rule("security-compliance", 8, r"guardduty|amazon inspector|\bmacie\b|security hub|amazon detective|access analyzer", "threat and posture services"),
    rule("security-compliance", 8, r"aws artifact", "aws artifact"),
    rule("security-compliance", 8, r"\bcognito\b", "cognito"),
    rule("security-compliance", 8, r"secrets manager", "secrets manager"),
    rule("security-compliance", 8, r"certificate manager|\bacm\b", "certificate manager"),
    rule("security-compliance", 8, r"\bddos\b|denial of service", "ddos"),
    rule("security-compliance", 8, r"penetration test", "penetration test"),
    rule("security-compliance", 8, r"root user|root account", "root user"),
    rule("security-compliance", 8, r"\bcloudtrail\b", "cloudtrail"),
    rule("security-compliance", 8, r"aws config", "aws config"),
    rule("security-compliance", 8, r"security groups?", "security group"),
    rule("security-compliance", 8, r"network acls?|\bnacls?\b", "network acl"),
    rule("security-compliance", 8, r"security token service|\bsts\b", "sts"),
    rule("security-compliance", 8, r"iam roles?|iam users?|iam polic(?:y|ies)|user groups?", "iam object"),
    rule("security-compliance", 8, r"password polic|password complexity", "password policy"),
    rule("security-compliance", 8, r"\bencrypt(?:ion|ed|ing)?\b", "encryption"),
    rule("security-compliance", 8, r"\bsoc\b|\bpci\b|\bhipaa\b|\bgdpr\b|\bfedramp\b|\biso 27001\b|compliance reports?|compliance documents?", "compliance program"),
    rule("security-compliance", 8, r"bucket polic|resource-based polic", "resource policy"),
    rule("security-compliance", 8, r"service control polic|\bscps?\b", "scp"),
    rule("security-compliance", 8, r"control tower", "control tower"),
    rule("security-compliance", 8, r"who (?:took|performed|made|deleted|terminated|stopped|launched)|account activity", "audit who"),
    rule("security-compliance", 6, r"\bunauthorized\b|\bmalicious\b", "malicious or unauthorized"),
    rule("security-compliance", 6, r"\baudit(?:ing|ed)?\b", "audit"),
    rule("security-compliance", 5, r"\bfirewall\b", "firewall"),
    rule("security-compliance", 5, r"\bssl\b|\btls\b|https certificate|server certificates?", "certificate"),
    rule("security-compliance", 5, r"identity center|single sign-on|\bsso\b", "identity center"),
    rule("security-compliance", 5, r"directory service|active directory", "directory"),
    rule("security-compliance", 4, r"\bpermissions?\b|\bcredentials?\b", "permission or credential"),
    rule("security-compliance", 3, r"\bsecurity\b", "security"),
    rule("security-compliance", 3, r"\bcompliance\b", "compliance"),
    rule("security-compliance", 4, r"physical (?:and environmental )?controls|physical access|disk disposal|patching the guest", "responsibility boundary"),
    # --- Cloud concepts (Domain 1) ---
    rule("cloud-concepts", 8, r"economies of scale", "economies of scale"),
    rule("cloud-concepts", 8, r"capital expenditure|operational expenditure|\bcapex\b|\bopex\b|variable expense|upfront (?:capital|cost)", "capex opex"),
    rule("cloud-concepts", 8, r"design principles?", "design principle"),
    rule("cloud-concepts", 8, r"design for failure", "design for failure"),
    rule("cloud-concepts", 8, r"loose coupling|loosely coupl|decoupl", "decoupling"),
    rule("cloud-concepts", 8, r"well-architected", "well-architected"),
    rule("cloud-concepts", 8, r"six advantages|advantages? of (?:the )?(?:aws )?cloud|benefits? of (?:the )?(?:aws )?cloud|benefits? of cloud computing", "cloud benefits"),
    rule("cloud-concepts", 8, r"\bagility\b", "agility"),
    rule("cloud-concepts", 8, r"\belasticity\b", "elasticity"),
    rule("cloud-concepts", 8, r"horizontal scaling|vertical scaling|scale horizontally|scale vertically|scaling horizontally|scaling vertically", "scaling direction"),
    rule("cloud-concepts", 8, r"\biaas\b|\bpaas\b|\bsaas\b|\bnaas\b|infrastructure as a service|platform as a service|software as a service|cloud computing models?", "cloud model"),
    rule("cloud-concepts", 8, r"stop guessing capacity|guessing capacity", "stop guessing capacity"),
    rule("cloud-concepts", 8, r"go global in minutes", "go global"),
    rule("cloud-concepts", 8, r"trade (?:fixed|capital)|fixed expense", "trade fixed for variable"),
    rule("cloud-concepts", 8, r"cloud concepts?|cloud characteristic", "cloud concept"),
    rule("cloud-concepts", 5, r"high availability|highly available", "high availability"),
    rule("cloud-concepts", 5, r"fault toleran", "fault tolerance"),
    rule("cloud-concepts", 4, r"\breliability\b", "reliability"),
    rule("cloud-concepts", 4, r"\bscalability\b|\bscalable\b", "scalability"),
    rule("cloud-concepts", 3, r"on-premises", "on-premises comparison"),
    rule("cloud-concepts", 4, r"total cost of ownership|\btco\b", "tco concept"),
    rule("cloud-concepts", 5, r"monolithic", "monolithic"),
    rule("cloud-concepts", 4, r"business (?:value|outcomes|differentiation)|focus on (?:the )?business", "business focus"),
    rule("cloud-concepts", 6, r"benefits? of migrat|advantages? of migrat", "migration benefit"),
    rule("cloud-concepts", 2, r"\badvantages?\b|\bbenefits?\b", "advantage or benefit"),
    # --- Technology and services (Domain 3) ---
    rule("technology-services", 5, r"which (?:of the following )?(?:aws )?(?:services?|tools?|features?|offerings?)|most cost-effective service", "which service"),
    rule("technology-services", 7, r"management console|command line interface|\bcli\b|software development kit|\bsdk\b|\bapi\b", "access method"),
    rule("technology-services", 8, r"global infrastructure", "global infrastructure"),
    rule("technology-services", 6, r"edge locations?", "edge location"),
    rule("technology-services", 4, r"availability zones?", "availability zone"),
    rule("technology-services", 2, r"\bregions?\b", "region"),
    rule("technology-services", 6, r"amazon ec2|\bec2\b|elastic compute cloud", "ec2"),
    rule("technology-services", 6, r"aws lambda|\blambda\b", "lambda"),
    rule("technology-services", 6, r"elastic beanstalk|amazon lightsail|\blightsail\b|\bfargate\b|\becs\b|\beks\b|elastic container|aws batch", "compute platform"),
    rule("technology-services", 6, r"amazon s3|\bs3\b|simple storage service|glacier|s3 standard|s3 intelligent|object storage", "s3 or glacier"),
    rule("technology-services", 6, r"\bebs\b|elastic block store|\befs\b|elastic file system|\bfsx\b|storage gateway|snowball|snowmobile|snowcone|instance store", "storage service"),
    rule("technology-services", 6, r"\brds\b|relational database|amazon aurora|\baurora\b|dynamodb|dynamo db|elasticache|redshift|neptune|documentdb|\bqldb\b", "database"),
    rule("technology-services", 6, r"\bvpc\b|virtual private cloud|load balancer|auto scaling|route 53|cloudfront|global accelerator|direct connect|transit gateway|vpn|privatelink|api gateway", "network"),
    rule("technology-services", 6, r"\bsqs\b|simple queue|\bsns\b|simple notification|amazon mq|step functions|eventbridge|kinesis", "integration"),
    rule("technology-services", 6, r"cloudformation|\bcdk\b|cloud development kit|opsworks|systems manager|\bssm\b|elastic beanstalk", "deployment and ops"),
    rule("technology-services", 6, r"cloudwatch|\bx-ray\b|xray", "observability"),
    rule("technology-services", 6, r"cloudfront|route 53", "edge delivery"),
    rule("technology-services", 5, r"rekognition|transcribe|\bpolly\b|\btranslate\b|\blex\b|comprehend|sagemaker|forecast|kendra|personalize|textract", "ai service"),
    rule("technology-services", 5, r"athena|\bemr\b|quicksight|\bglue\b|opensearch|elasticsearch", "analytics"),
    rule("technology-services", 5, r"cloud9|codecommit|codebuild|codepipeline|codedeploy|codeartifact|codestar|codeguru", "developer tools"),
    rule("technology-services", 5, r"workspaces|appstream|iot core|device farm|backup|datasync|migration hub|database migration|application discovery|application migration|\bmgn\b|elastic disaster recovery|fault injection", "end user and migration services"),
    rule("technology-services", 5, r"quick start|service catalog|outposts|wavelength|local zones|amplify|appsync", "platform service"),
    rule("technology-services", 5, r"amazon connect|workdocs|workmail|chime|pinpoint|sumerian|elastic transcoder", "business app"),
    rule("technology-services", 4, r"deploy(?:ing|ment)?", "deploy"),
    rule("technology-services", 3, r"\bserverless\b|\bcontainers?\b|\bdocker\b", "compute style"),
    rule("technology-services", 3, r"\bsubnet\b|\brouting\b|\bdns\b", "networking detail"),
    rule("security-compliance", 8, r"shared controls?|access keys?|acceptable use|abuse team|account (?:has been )?compromised", "security governance"),
    rule("security-compliance", 8, r"cloud directory|fully responsible|user is responsible", "responsibility or directory"),
    rule("security-compliance", 6, r"manage aws access|access policies across", "cross-account access"),
    rule("cloud-concepts", 8, r"global reach|aws characteristic|shorten the time to provision|free up .{0,30}it resources|disaster recovery|scale up or down", "cloud characteristic"),
    rule("cloud-concepts", 6, r"best-practice when designing|designing solutions on aws", "design best practice"),
    rule("billing-support", 8, r"unexpected charges|aggregated bill|single bill|their bill", "bill hygiene"),
    rule("billing-support", 5, r"aws organizations|master account|member accounts?", "organizations account"),
    rule("technology-services", 6, r"infrastructure as code|resource groups?|database technology|provision and operate|eliminate human error", "operations choice"),
    rule("technology-services", 4, r"\btagging\b|tag editor", "tagging"),
]


STEM_OVERRIDES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"shared responsibility", re.I), "security-compliance", "override shared responsibility"),
    (re.compile(r"who (?:took|performed|made|deleted|terminated|stopped|launched)|determine who", re.I), "security-compliance", "override audit actor"),
    (re.compile(r"customer(?:'s|s)? responsibility|responsibility of the customer|responsibility of aws|aws(?:'s| is) responsible|fully responsible|user(?: is)? responsible|shared controls?", re.I), "security-compliance", "override responsibility split"),
    (re.compile(r"pricing models?|how (?:is|are) .{0,40}priced|support plans?|aws support\b|support concierge|technical account manager", re.I), "billing-support", "override pricing or support"),
    (re.compile(r"reserved instances?|savings plans?|spot instances?", re.I), "billing-support", "override purchasing option"),
    (re.compile(r"cost explorer|aws budgets?|pricing calculator|tco calculator|total cost of ownership \(tco\) calculator|cost and usage|cost allocation tags?", re.I), "billing-support", "override cost tool"),
    (re.compile(r"trusted advisor", re.I), "billing-support", "override trusted advisor"),
    (re.compile(r"design principles?|architecture principles?|well-architected pillar|pillar of the", re.I), "cloud-concepts", "override design principle"),
    (re.compile(r"economies of scale", re.I), "cloud-concepts", "override economies of scale"),
    (re.compile(r"\belasticity\b|loose coupling|loosely coupled|decoupl", re.I), "cloud-concepts", "override architecture concept"),
    (re.compile(r"horizontal scaling|vertical scaling|scaling horizontally|scaling vertically", re.I), "cloud-concepts", "override scaling concept"),
    (re.compile(r"\biaas\b|\bpaas\b|\bsaas\b", re.I), "cloud-concepts", "override service model"),
    (re.compile(r"what is an availability zone|what is an aws region|edge locations? (?:are|provide|are used)", re.I), "technology-services", "override infrastructure definition"),
]


# Overrides that must win only when the stem is about the concept, not when a
# later rule already pointed at a more specific service question.
CONCEPT_OVERRIDE_DOMAINS = {"cloud-concepts"}


QUESTION_RE = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")
CHOICE_RE = re.compile(r"^\s*-\s+([A-F])\.\s+(.*\S)\s*$")
DETAILS_RE = re.compile(r"^\s*<details\b", re.IGNORECASE)
DETAILS_END_RE = re.compile(r"^\s*</details>", re.IGNORECASE)
ANSWER_RE = re.compile(r"correct\s+answer\s*:\s*(.+)", re.IGNORECASE)
ANSWER_ONLY_RE = re.compile(r"^answer\s*:\s*(.+)", re.IGNORECASE)
TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
GENERIC_TAG_RE = re.compile(r"</?[^>]+>")
WS_RE = re.compile(r"\s+")
STEM_KEY_RE = re.compile(r"[^a-z0-9]+")


def clean_text(value: str) -> str:
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", value)
    text = TAG_RE.sub("\n", text)
    text = GENERIC_TAG_RE.sub("", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    lines = [WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def stem_key(value: str) -> str:
    flattened = clean_text(value).lower().replace("\n", " ")
    return STEM_KEY_RE.sub(" ", flattened).strip()


def parse_answers(raw: str) -> list[str]:
    raw = raw.strip().rstrip(".")
    if re.fullmatch(r"[A-F]{1,6}", raw, re.IGNORECASE):
        letters = list(raw.upper())
    elif re.fullmatch(r"[A-F](?:\s*(?:,|and|&|/)\s*[A-F])+", raw, re.IGNORECASE):
        letters = re.findall(r"[A-F]", raw.upper())
    else:
        letters = re.findall(r"\b([A-F])\b", raw.upper())
    seen: list[str] = []
    for letter in letters:
        if letter not in seen:
            seen.append(letter)
    return seen


def parse_exam(path: Path) -> tuple[list[dict], list[str]]:
    exam_number = int(re.search(r"(\d+)", path.stem).group(1))
    lines = path.read_text(encoding="utf-8").splitlines()
    questions: list[dict] = []
    errors: list[str] = []
    index = 0
    ordinal = 0
    while index < len(lines):
        match = QUESTION_RE.match(lines[index])
        if not match or lines[index].startswith(" "):
            index += 1
            continue
        ordinal += 1
        printed = int(match.group(1))
        stem_lines = [match.group(2)]
        index += 1
        choices: list[tuple[str, list[str]]] = []
        while index < len(lines) and not DETAILS_RE.match(lines[index]) and not QUESTION_RE.match(lines[index]):
            choice = CHOICE_RE.match(lines[index])
            if choice:
                choices.append((choice.group(1).upper(), [choice.group(2)]))
            elif choices and lines[index].strip() and not lines[index].strip().startswith("<"):
                choices[-1][1].append(lines[index].strip())
            elif lines[index].strip() and not choices:
                stem_lines.append(lines[index].strip())
            index += 1
        detail_lines: list[str] = []
        if index < len(lines) and DETAILS_RE.match(lines[index]):
            index += 1
            while index < len(lines) and not DETAILS_END_RE.match(lines[index]):
                detail_lines.append(lines[index])
                index += 1
            if index < len(lines) and DETAILS_END_RE.match(lines[index]):
                index += 1
        answers: list[str] = []
        explanation_lines: list[str] = []
        for line in detail_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("<summary") or stripped.startswith("</summary"):
                continue
            answer_match = ANSWER_RE.search(stripped) or ANSWER_ONLY_RE.search(stripped)
            if answer_match and not answers:
                answers = parse_answers(answer_match.group(1))
                continue
            if re.fullmatch(r"explanation:?|reference:?", stripped, re.IGNORECASE):
                continue
            stripped = re.sub(r"^(explanation|reference)\s*:\s*", "", stripped, flags=re.IGNORECASE)
            explanation_lines.append(stripped)
        record = {
            "exam": exam_number,
            "printedNumber": printed,
            "ordinal": ordinal,
            "stem": clean_text("\n".join(stem_lines)),
            "choices": [{"letter": letter, "text": clean_text(" ".join(parts))} for letter, parts in choices],
            "answers": answers,
            "explanation": clean_text("\n".join(explanation_lines)),
            "source": f"practice-exam/practice-exam-{exam_number}.md",
        }
        problem = validate(record)
        if problem:
            errors.append(f"exam {exam_number} #{printed} (ordinal {ordinal}): {problem}")
            continue
        questions.append(record)
    return questions, errors


def validate(record: dict) -> str | None:
    letters = [choice["letter"] for choice in record["choices"]]
    if len(letters) < 2:
        return "fewer than 2 choices"
    if len(letters) != len(set(letters)):
        return "duplicate choice letters"
    if not record["answers"]:
        return "missing answer"
    if any(letter not in letters for letter in record["answers"]):
        return f"answer {record['answers']} not in choices {letters}"
    if not record["stem"]:
        return "empty stem"
    return None


def score_text(text: str, multiplier: float) -> tuple[dict[str, float], list[tuple[float, str, str]]]:
    scores = {domain["id"]: 0.0 for domain in DOMAINS}
    hits: list[tuple[float, str, str]] = []
    if not text:
        return scores, hits
    for domain, weight, pattern, label in RULES:
        if pattern.search(text):
            points = weight * multiplier
            scores[domain] += points
            hits.append((points, domain, label))
    return scores, hits


BILLING_ANSWER = re.compile(
    r"consolidated billing|cost explorer|aws budgets?|pricing calculator|tco calculator|"
    r"cost (?:and|&) usage|cost allocation|reserved instance|savings plan|spot instance|"
    r"dedicated host|trusted advisor|aws marketplace|professional services|partner network|"
    r"support plan|support concierge|technical account manager|volume pricing|usage tier",
    re.IGNORECASE,
)
SECURITY_ANSWER = re.compile(
    r"\biam\b|identity and access|control tower|cloudtrail|guardduty|security hub|aws config|"
    r"macie|inspector|aws shield|\bwaf\b|kms|cloudhsm|cognito|secrets manager|artifact|"
    r"security group|network acl|service control polic|access analyzer|detective|"
    r"certificate manager|encrypt",
    re.IGNORECASE,
)
TECH_ANSWER = re.compile(
    r"\bs3\b|glacier|\bebs\b|\bec2\b|lambda|\brds\b|dynamodb|aurora|cloudfront|route 53|"
    r"\bvpc\b|\bsqs\b|\bsns\b|cloudformation|elastic beanstalk|snowball|redshift|athena|"
    r"kinesis|elasticache|efs|storage gateway|auto scaling|load balancer|cloudwatch|"
    r"api gateway|fargate|eks|ecs|emr|documentdb|neptune|quicksight|sagemaker|"
    r"cloudfront|direct connect|global accelerator|elastic file|elastic disaster recovery|resource groups",
    re.IGNORECASE,
)


def classify(record: dict) -> tuple[str, list[str], float]:
    choice_by_letter = {choice["letter"]: choice["text"] for choice in record["choices"]}
    correct_text = " ".join(choice_by_letter[letter] for letter in record["answers"])
    # Distractors are wrong on purpose, so they do not vote.
    scores = {domain["id"]: 0.0 for domain in DOMAINS}
    hits: list[tuple[float, str, str]] = []
    for text, multiplier in ((record["stem"], 3.0), (correct_text, 2.0)):
        part_scores, part_hits = score_text(text, multiplier)
        for domain_id, points in part_scores.items():
            scores[domain_id] += points
        hits.extend(part_hits)

    stem = record["stem"]
    asks_for_service = re.search(
        r"which (?:of the following )?(?:aws )?(?:services?|tools?|features?|offerings?)|"
        r"what (?:aws )?(?:service|tool)|most cost-effective service",
        stem,
        re.IGNORECASE,
    )
    override_domain = None
    override_label = None
    for pattern, domain, label in STEM_OVERRIDES:
        if not pattern.search(stem):
            continue
        if domain in CONCEPT_OVERRIDE_DOMAINS and asks_for_service:
            continue
        override_domain = domain
        override_label = label
        break

    ranking = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_domain, top_score = ranking[0]
    second_score = ranking[1][1]
    if override_domain:
        if (
            override_domain in CONCEPT_OVERRIDE_DOMAINS
            and top_domain == "security-compliance"
            and top_score >= 24
            and scores["cloud-concepts"] < top_score
        ):
            chosen = top_domain
        else:
            chosen = override_domain
            hits.append((100, chosen, override_label or "override"))
    elif top_score <= 0:
        chosen = "technology-services"
        hits.append((1, chosen, "default technology"))
    else:
        chosen = top_domain

    def prefer(domain: str, label: str) -> None:
        nonlocal chosen
        chosen = domain
        hits.append((100, domain, label))

    # How long a resource is billed, and other pricing mechanics.
    if re.search(r"\bbilled\b|billing increment|per[- ]second billing", stem, re.IGNORECASE):
        prefer("billing-support", "billed amount")

    # Consolidated billing is Domain 4 even when the stem says "advantage".
    if BILLING_ANSWER.search(stem) or BILLING_ANSWER.search(correct_text):
        if not (SECURITY_ANSWER.search(correct_text) and not BILLING_ANSWER.search(correct_text)):
            # A correct billing feature beats an incidental cloud-benefit word.
            if chosen == "cloud-concepts" or BILLING_ANSWER.search(stem):
                prefer("billing-support", "billing feature")

    # TCO as an economic concept stays in Cloud Concepts. The calculator tool does not.
    if re.search(r"total cost of ownership|\btco\b", stem, re.IGNORECASE) and not re.search(
        r"calculator|which tool|which service", stem, re.IGNORECASE
    ):
        prefer("cloud-concepts", "tco economics")

    # Choosing AWS, or pay-for-what-you-use, is a cloud benefit rather than a billing tool.
    if re.search(
        r"value proposition|why should a company choose aws|instead of a traditional|"
        r"benefits? of using aws|advantages? of (?:the )?(?:aws )?cloud|"
        r"paying only for what|only for what is used|pay-as-you-go",
        f"{stem} {correct_text}",
        re.IGNORECASE,
    ) and not re.search(
        r"pricing model|reserved instance|spot instance|savings plan|cost explorer|aws budgets?|calculator",
        stem,
        re.IGNORECASE,
    ):
        if chosen == "billing-support":
            prefer("cloud-concepts", "cloud economic benefit")

    # Hybrid / public / private cloud definitions are concepts.
    if re.search(r"what does it mean if|which of the following (?:is|describes|best describes)", stem, re.IGNORECASE):
        if re.search(r"hybrid cloud|public cloud|private cloud", f"{stem} {correct_text}", re.IGNORECASE):
            prefer("cloud-concepts", "cloud deployment model")

    # "Which service" follows the correct answer's catalog.
    # A security service wins over a technology word that only describes where it runs.
    if asks_for_service:
        security_answer = SECURITY_ANSWER.search(correct_text)
        billing_answer = BILLING_ANSWER.search(correct_text)
        technology_answer = TECH_ANSWER.search(correct_text)
        if security_answer and not billing_answer:
            prefer("security-compliance", "security service answer")
        elif billing_answer and not security_answer:
            prefer("billing-support", "billing service answer")
        elif technology_answer:
            prefer("technology-services", "technology service answer")

    # Cutting cost by scaling with demand is a cloud concept, not a billing product.
    if re.search(r"reduce .{0,40}costs?|most effectively reduce", stem, re.IGNORECASE) and re.search(
        r"on-demand resources|peak usage|elasticity|economies of scale|only for what",
        correct_text,
        re.IGNORECASE,
    ):
        prefer("cloud-concepts", "cost reduced by cloud concept")

    # Control Tower and IAM answers are security even if the stem says "well-architected" or "migrate".
    if re.search(r"control tower|\biam\b|identity and access management", correct_text, re.IGNORECASE):
        if not BILLING_ANSWER.search(correct_text):
            prefer("security-compliance", "identity or governance answer")

    # Trusted Advisor is a support tool, except when the question asks for a security check.
    if re.search(r"trusted advisor", f"{stem} {correct_text}", re.IGNORECASE):
        if re.search(r"secur|compliance|vulnerab", stem, re.IGNORECASE) and not re.search(
            r"\bcost\b|\bprice\b|\bbill\b|\bsave\b|\bsaving\b|\bmoney\b|\bperformance\b|\bfault\b|service quota|\blimits?\b",
            stem,
            re.IGNORECASE,
        ):
            prefer("security-compliance", "trusted advisor security")
        elif chosen != "security-compliance":
            prefer("billing-support", "trusted advisor")

    # Protecting stored data by encrypting it is a security task.
    if re.search(r"encrypt", correct_text, re.IGNORECASE) and re.search(
        r"\bsafe\b|\bsecure\b|protect", stem, re.IGNORECASE
    ):
        prefer("security-compliance", "protect data")

    # Organizations: billing features and account-unlink rules vs guardrails.
    if re.search(r"organizations|member account|linked account", f"{stem} {correct_text}", re.IGNORECASE):
        has_bill = re.search(
            r"consolidated billing|billing|invoice|volume|usage tier|standalone account|unlink",
            f"{stem} {correct_text}",
            re.IGNORECASE,
        )
        has_guard = re.search(r"service control|governance|guardrail|security polic", f"{stem} {correct_text}", re.IGNORECASE)
        if has_bill and not has_guard:
            prefer("billing-support", "organizations billing")
        elif has_guard and not has_bill:
            prefer("security-compliance", "organizations governance")

    # Cost-effective choice of a storage or compute service is still technology.
    if re.search(r"cost-effective|lowest[- ]cost|least expensive", stem, re.IGNORECASE) and TECH_ANSWER.search(correct_text):
        if not BILLING_ANSWER.search(correct_text) and not re.search(r"billing alarms?|billing alerts?", stem, re.IGNORECASE):
            prefer("technology-services", "cost-effective technology choice")

    # A billing alarm is a cost-management task even when the tool is CloudWatch.
    if re.search(r"billing alarms?|billing alerts?", stem, re.IGNORECASE):
        prefer("billing-support", "billing alarm")

    ranked_hits = sorted(hits, key=lambda item: item[0], reverse=True)
    signals: list[str] = []
    for _points, domain, label in ranked_hits:
        if domain == chosen and label not in signals:
            signals.append(label)
        if len(signals) == 4:
            break
    if not signals:
        signals = ["unscored"]
    margin = round(top_score - second_score, 1)
    return chosen, signals, margin


def question_id(key: str, answers: list[str]) -> str:
    digest = hashlib.sha1(f"{key}|{''.join(answers)}".encode("utf-8")).hexdigest()[:12]
    return f"q_{digest}"


def apportion(size: int, domains: list[dict]) -> dict[str, int]:
    raw = {domain["id"]: size * domain["weight"] for domain in domains}
    floors = {domain_id: int(value) for domain_id, value in raw.items()}
    left = size - sum(floors.values())
    order = sorted(raw, key=lambda domain_id: (raw[domain_id] - floors[domain_id], raw[domain_id]), reverse=True)
    for domain_id in order[:left]:
        floors[domain_id] += 1
    return floors


def dedupe(questions: list[dict]) -> tuple[list[dict], int, list[str]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for question in questions:
        grouped[stem_key(question["stem"])].append(question)
    unique: list[dict] = []
    conflicts: list[str] = []
    removed = 0
    for key, group in grouped.items():
        answer_groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
        for question in group:
            answer_groups[tuple(question["answers"])].append(question)
        if len(answer_groups) > 1:
            rendered = ", ".join("".join(answers) or "?" for answers in answer_groups)
            conflicts.append(f"{group[0]['stem'][:110]} :: {rendered}")
        for answers, items in answer_groups.items():
            items.sort(key=lambda item: (-len(item["explanation"]), item["exam"], item["ordinal"]))
            keeper = items[0]
            keeper["id"] = question_id(key, list(answers))
            keeper["stemKey"] = key
            keeper["alsoIn"] = [
                f"exam-{item['exam']}-q{item['printedNumber']}"
                for item in items[1:]
            ]
            unique.append(keeper)
            removed += len(items) - 1
    unique.sort(key=lambda item: (item["exam"], item["ordinal"]))
    return unique, removed, conflicts


def build() -> dict:
    files = sorted(EXAM_DIR.glob("practice-exam-*.md"), key=lambda path: int(re.search(r"(\d+)", path.stem).group(1)))
    parsed: list[dict] = []
    errors: list[str] = []
    for path in files:
        questions, file_errors = parse_exam(path)
        parsed.extend(questions)
        errors.extend(file_errors)
    unique, removed, conflicts = dedupe(parsed)
    counts = apportion(EXAM_SIZE, DOMAINS)
    for question in unique:
        domain, signals, margin = classify(question)
        question["domain"] = domain
        question["signals"] = signals
        question["margin"] = margin
    by_domain = {domain["id"]: 0 for domain in DOMAINS}
    for question in unique:
        by_domain[question["domain"]] += 1
    domains_out = []
    for domain in DOMAINS:
        domains_out.append(
            {
                **domain,
                "examCount": counts[domain["id"]],
                "poolCount": by_domain[domain["id"]],
            }
        )
    payload = {
        "meta": {
            "examCode": "CLF-C02",
            "examSize": EXAM_SIZE,
            "passMark": PASS_MARK,
            "officialQuestions": OFFICIAL_QUESTIONS,
            "officialMinutes": OFFICIAL_MINUTES,
            "officialPass": "700/1000",
            "minutes": round(OFFICIAL_MINUTES * EXAM_SIZE / OFFICIAL_QUESTIONS),
            "sourceFiles": len(files),
            "parsed": len(parsed),
            "unique": len(unique),
            "duplicatesRemoved": removed,
            "parseErrors": errors,
            "answerConflicts": conflicts,
            "domains": domains_out,
        },
        "questions": [
            {
                "id": question["id"],
                "exam": question["exam"],
                "number": question["printedNumber"],
                "stem": question["stem"],
                "choices": question["choices"],
                "answers": question["answers"],
                "explanation": question["explanation"],
                "domain": question["domain"],
                "stemKey": question["stemKey"],
                "signals": question["signals"],
                "source": question["source"],
                "alsoIn": question["alsoIn"],
            }
            for question in unique
        ],
    }
    return payload


def review(payload: dict) -> str:
    lines: list[str] = []
    meta = payload["meta"]
    lines.append(
        f"parsed={meta['parsed']} unique={meta['unique']} removed={meta['duplicatesRemoved']} "
        f"errors={len(meta['parseErrors'])} conflicts={len(meta['answerConflicts'])}"
    )
    for domain in meta["domains"]:
        lines.append(
            f"{domain['id']}: pool={domain['poolCount']} exam={domain['examCount']} weight={domain['weight']}"
        )
    if meta["parseErrors"]:
        lines.append("-- parse errors --")
        lines.extend(meta["parseErrors"][:40])
    if meta["answerConflicts"]:
        lines.append("-- answer conflicts --")
        lines.extend(meta["answerConflicts"][:20])
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for question in payload["questions"]:
        by_domain[question["domain"]].append(question)
    lines.append("-- samples --")
    for domain in DOMAINS:
        lines.append(f"## {domain['id']}")
        for question in by_domain[domain["id"]][:8]:
            lines.append(
                f"  [{''.join(question['answers'])}] {question['stem'][:180]} :: {', '.join(question['signals'])}"
            )
    return "\n".join(lines)


def main() -> None:
    payload = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(review(payload))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
