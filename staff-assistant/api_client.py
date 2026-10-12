from __future__ import annotations

import os
from typing import Any, Optional
import httpx

DEFAULT_BASE_URL = "https://api.example.com/v1"
TIMEOUT_SECONDS = 10.0


class OctapusApiClient:
    """Client for interacting with Octapus external REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        raw_base = base_url or os.environ.get("OCTAPUS_API_BASE_URL", DEFAULT_BASE_URL)
        self.base_url = raw_base.rstrip("/")
        self.api_key = api_key or os.environ.get("OCTAPUS_API_KEY", "")
        self.transport = transport
        self._client = httpx.Client(transport=self.transport, timeout=TIMEOUT_SECONDS)

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = self._get_headers()
        try:
            response = self._client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
            )

            if response.status_code == 401:
                return {"error": "Authentication failed (401 Unauthorized). Please check the API key."}
            if response.status_code == 404:
                return {"error": f"Resource not found (404) at {path}."}
            if response.is_error:
                return {"error": f"API returned error status {response.status_code}: {response.text}"}

            try:
                data = response.json()
                if isinstance(data, dict):
                    return data
                return {"data": data}
            except Exception:
                return {"data": response.text}

        except httpx.TimeoutException:
            return {"error": "API request timed out (10s limit exceeded)."}
        except httpx.RequestError as exc:
            return {"error": f"Failed to connect to API: {str(exc)}"}
        except Exception as exc:
            return {"error": f"Unexpected error during API request: {str(exc)}"}

    def get_client(self, client_id: str) -> dict[str, Any]:
        """Fetch client by ID: GET /clients/{client_id}"""
        return self._request("GET", f"/clients/{client_id}")

    def get_projects(self, status: str = "open") -> dict[str, Any]:
        """Fetch projects by status: GET /projects?status={status}"""
        return self._request("GET", "/projects", params={"status": status})

    def create_lead(self, lead_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new lead: POST /leads"""
        return self._request("POST", "/leads", json_body=lead_data)
