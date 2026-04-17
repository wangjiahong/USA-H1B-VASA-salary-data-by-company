"""Configuration for H1B salary report.

Each company has a human-readable name (`label`), a category, and one or more
`search_terms` passed to the h1bdata.info `em` query parameter. Using multiple
terms lets us cover historical names (e.g. Facebook -> Meta Platforms).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Company:
    key: str
    label: str
    category: str
    search_terms: List[str] = field(default_factory=list)


COMPANIES: List[Company] = [
    # FAANG / MAANG
    Company("google", "Google", "FAANG", ["Google"]),
    Company("meta", "Meta (Facebook)", "FAANG", ["Meta Platforms", "Facebook Inc"]),
    Company("amazon", "Amazon", "FAANG", ["Amazon"]),
    Company("apple", "Apple", "FAANG", ["Apple Inc"]),
    Company("netflix", "Netflix", "FAANG", ["Netflix"]),
    Company("microsoft", "Microsoft", "FAANG", ["Microsoft"]),

    # Semiconductor / Hardware
    Company("nvidia", "NVIDIA", "Semiconductor", ["Nvidia"]),
    Company("intel", "Intel", "Semiconductor", ["Intel Corp"]),
    Company("amd", "AMD", "Semiconductor", ["Advanced Micro Devices"]),
    Company("qualcomm", "Qualcomm", "Semiconductor", ["Qualcomm"]),
    Company("tesla", "Tesla", "Semiconductor", ["Tesla Inc", "Tesla Motors"]),

    # China-affiliated US companies
    Company("bytedance", "ByteDance / TikTok", "China-affiliated", ["Bytedance", "TikTok"]),
    Company("alibaba", "Alibaba", "China-affiliated", ["Alibaba"]),

    # Fintech
    Company("stripe", "Stripe", "Fintech", ["Stripe"]),
    Company("block", "Block (Square)", "Fintech", ["Block Inc", "Square Inc"]),
    Company("paypal", "PayPal", "Fintech", ["Paypal"]),
    Company("robinhood", "Robinhood", "Fintech", ["Robinhood"]),
    Company("coinbase", "Coinbase", "Fintech", ["Coinbase"]),

    # SaaS / Enterprise
    Company("salesforce", "Salesforce", "SaaS", ["Salesforce"]),
    Company("adobe", "Adobe", "SaaS", ["Adobe Inc", "Adobe Systems"]),
    Company("oracle", "Oracle", "SaaS", ["Oracle America"]),
    Company("snowflake", "Snowflake", "SaaS", ["Snowflake"]),
    Company("databricks", "Databricks", "SaaS", ["Databricks"]),
    Company("servicenow", "ServiceNow", "SaaS", ["Servicenow"]),
    Company("workday", "Workday", "SaaS", ["Workday"]),
    Company("palantir", "Palantir", "SaaS", ["Palantir"]),
    Company("cloudflare", "Cloudflare", "SaaS", ["Cloudflare"]),

    # Consumer / Social
    Company("uber", "Uber", "Consumer", ["Uber Technologies"]),
    Company("airbnb", "Airbnb", "Consumer", ["Airbnb"]),
    Company("lyft", "Lyft", "Consumer", ["Lyft"]),
    Company("doordash", "DoorDash", "Consumer", ["Doordash"]),
    Company("linkedin", "LinkedIn", "Consumer", ["Linkedin"]),
    Company("pinterest", "Pinterest", "Consumer", ["Pinterest"]),
    Company("snap", "Snap", "Consumer", ["Snap Inc"]),
    Company("reddit", "Reddit", "Consumer", ["Reddit"]),

    # AI-native
    Company("openai", "OpenAI", "AI-native", ["OpenAI"]),
    Company("anthropic", "Anthropic", "AI-native", ["Anthropic"]),
]


@dataclass(frozen=True)
class JobRole:
    key: str
    label: str
    search_term: str


JOBS: List[JobRole] = [
    JobRole("swe", "Software Engineer", "software engineer"),
    JobRole("ds", "Data Scientist", "data scientist"),
    JobRole("de", "Data Engineer", "data engineer"),
    JobRole("mle", "Machine Learning Engineer", "machine learning engineer"),
    JobRole("pm", "Product Manager", "product manager"),
    JobRole("rs", "Research Scientist", "research scientist"),
]


YEARS: List[str] = ["2021", "2022", "2023", "2024", "2025"]


# Amazon doesn't use the term "software engineer" -- uses "Software Development Engineer".
# Keeping the same override as the original notebook.
JOB_OVERRIDES = {
    ("amazon", "swe"): "software development engineer",
    ("amazon", "rs"): "applied scientist",  # Amazon's equivalent of research scientist
}


# BASE SALARY filtering: the original notebook capped at 400k, but post-2023 many
# senior base salaries exceed that. Use a wider but still sane band.
SALARY_MIN = 50_000
SALARY_MAX = 1_200_000


BASE_URL = "https://h1bdata.info/index.php"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
