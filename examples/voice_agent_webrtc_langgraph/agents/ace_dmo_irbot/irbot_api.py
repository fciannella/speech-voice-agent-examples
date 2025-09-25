#!/usr/bin/env python3
"""
IRBOT API client

Endpoints (from your Postman collection):
- GET  /chatbot/irbot-app/healthcheck
- POST /chatbot/irbot-app/userquery
- POST /chatbot/irbot-app/feedback

Usage examples:
  export IRBOT_API_KEY="55f5f002-5eae-470e-90f4-87365f0f016f"
  python irbot_client.py healthcheck
  python irbot_client.py userquery --query "Show me a bar chart..." --session 54re53-3523er-35e-43ffd-fd43d4
  python irbot_client.py feedback \
    --question "What is 2020 revenue?" \
    --caption "Table showing the 2020 revenue, which amounted to $10,918 million." \
    --table-json '{"columns":["FY","REVENUE ($M)"],"values":[["2020","$10,918"]]}' \
    --chart-json '{}' \
    --feedback 1 \
    --response-type table \
    --session 54re53-3523er-35e-43ffd-fd4wd4
"""

import os
import json
import argparse
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_BASE_URL = "https://api-prod.nvidia.com"
DEFAULT_TIMEOUT = 20  # seconds


class IRBotClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        referer: Optional[str] = None,
        origin: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("IRBOT_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Missing API key. Set IRBOT_API_KEY env var or pass api_key=..."
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({"x-irbot-secure": self.api_key})

        # Optional headers (Feedback call in your Postman had these)
        if referer:
            self.session.headers.update({"Referer": referer})
        if origin:
            self.session.headers.update({"Origin": origin})

        # Robust retries for transient network/server errors
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    # -------- endpoints --------

    def healthcheck(self) -> Dict[str, Any]:
        url = f"{self.base_url}/chatbot/irbot-app/healthcheck"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        # Some healthchecks return plain text; try JSON then fallback
        try:
            return {"ok": True, "data": resp.json()}
        except ValueError:
            return {"ok": True, "data": resp.text}

    def userquery(self, query: str, session_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/chatbot/irbot-app/userquery"
        payload = {"query": query, "session_id": session_id}
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        _raise_for_json_error(resp)
        return resp.json()

    def feedback(
        self,
        question: str,
        caption: str,
        table_json: Dict[str, Any],
        chart_json: Dict[str, Any],
        feedback: int,
        response_type: str,
        session_id: str,
        data: str = "",
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        NOTE: The Postman example shows tableData and chartData as STRINGIFIED JSON.
        We follow that here to match the backend’s expectation.
        """
        url = f"{self.base_url}/chatbot/irbot-app/feedback"

        body = {
            "question": question,
            "data": data,  # raw string per your example
            "caption": caption,
            "tableData": json.dumps(table_json, separators=(",", ":")),
            "chartData": json.dumps(chart_json, separators=(",", ":")),
            "feedback": int(feedback),          # 1 for positive, 0 for negative?, depends on backend
            "reason": reason,                   # optional explanatory text
            "responseType": response_type,      # e.g., "table", "chart", "text"
            "session_id": session_id,
        }

        resp = self.session.post(url, json=body, timeout=self.timeout)
        _raise_for_json_error(resp)
        return resp.json()


# -------- helpers --------

def _raise_for_json_error(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        # Try to include JSON error details if present
        try:
            details = resp.json()
        except ValueError:
            details = resp.text
        raise requests.HTTPError(f"{e}\nResponse: {details}") from None


# -------- CLI --------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="IRBOT API client")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    p.add_argument("--api-key", default=None, help="x-irbot-secure; or set IRBOT_API_KEY")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    p.add_argument("--referer", default=None, help="Optional Referer header")
    p.add_argument("--origin", default=None, help="Optional Origin header")

    sub = p.add_subparsers(dest="cmd", required=True)

    # healthcheck
    sub.add_parser("healthcheck")

    # userquery
    q = sub.add_parser("userquery")
    q.add_argument("--query", required=True)
    q.add_argument("--session", required=True, help="session_id")

    # feedback
    f = sub.add_parser("feedback")
    f.add_argument("--question", required=True)
    f.add_argument("--caption", required=True)
    f.add_argument("--table-json", required=True, help="JSON string for tableData")
    f.add_argument("--chart-json", required=True, help="JSON string for chartData")
    f.add_argument("--feedback", type=int, required=True, help="e.g., 1 or 0")
    f.add_argument("--response-type", required=True, help='e.g., "table", "chart", "text"')
    f.add_argument("--session", required=True, help="session_id")
    f.add_argument("--data", default="", help="Optional raw string")
    f.add_argument("--reason", default="", help="Optional reason text")

    return p


def main():
    args = build_parser().parse_args()

    client = IRBotClient(
        api_key=args.api_key,
        base_url=args.base_url,
        timeout=args.timeout,
        referer=args.referer,
        origin=args.origin,
    )

    if args.cmd == "healthcheck":
        out = client.healthcheck()
        print(json.dumps(out, indent=2))

    elif args.cmd == "userquery":
        out = client.userquery(query=args.query, session_id=args.session)
        print(json.dumps(out, indent=2))

    elif args.cmd == "feedback":
        try:
            table_obj = json.loads(args.table_json)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--table-json is not valid JSON: {e}")

        try:
            chart_obj = json.loads(args.chart_json)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--chart-json is not valid JSON: {e}")

        out = client.feedback(
            question=args.question,
            caption=args.caption,
            table_json=table_obj,
            chart_json=chart_obj,
            feedback=args.feedback,
            response_type=args.response_type,
            session_id=args.session,
            data=args.data,
            reason=args.reason,
        )
        print(json.dumps(out, indent=2))

    else:
        raise SystemExit("Unknown command")


if __name__ == "__main__":
    main()
